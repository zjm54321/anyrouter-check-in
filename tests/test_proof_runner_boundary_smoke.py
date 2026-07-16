import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import NoReturn

import httpx
import pytest

import proof_harness.browser as browser_module
import proof_harness.valid_runtime as valid_runtime
import proof_runner_boundary_smoke as entrypoint
from proof_harness.config import ProofConfig, ProxyMode
from proof_harness.runner_boundary_diagnostic import (
	Category,
	RunnerBoundaryResult,
	Stage,
	run_runner_boundary_smoke,
)


@dataclass(slots=True)
class FakePage:
	prepared: bool = False
	navigated: bool = False

	async def add_init_script(self, _script: str) -> None:
		self.prepared = True

	async def goto(self, _url: str, **_kwargs: str | float | None) -> NoReturn:
		self.navigated = True
		raise AssertionError('navigation must remain unreachable')


@dataclass(slots=True)
class FakeContext:
	page: FakePage

	async def new_page(self) -> FakePage:
		return self.page


@dataclass(slots=True)
class FakeBrowser:
	context: FakeContext
	close_fails: bool = False
	closed: bool = False
	viewport: dict[str, int] | None = None

	async def new_context(self, *, viewport: dict[str, int]) -> FakeContext:
		self.viewport = viewport
		return self.context

	async def close(self) -> None:
		if self.close_fails:
			raise RuntimeError('private close path and credential detail')
		self.closed = True


def test_runner_boundary_uses_real_valid_runtime_and_stops_before_network(
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	# Given
	page = FakePage()
	browser = FakeBrowser(FakeContext(page))
	observed_configs: list[ProofConfig] = []
	observed_env: list[Mapping[str, str]] = []
	real_run_valid = valid_runtime.run_valid

	def observe_run_valid(config: ProofConfig):
		observed_configs.append(config)
		return real_run_valid(config)

	async def launch(*, env: Mapping[str, str], headless: bool, humanize: bool) -> FakeBrowser:
		assert headless is False
		assert humanize is True
		observed_env.append(env)
		return browser

	def fail_http_client(
		**_kwargs: bool | float | str | httpx.BaseTransport | None,
	) -> NoReturn:
		raise AssertionError('HTTP client must remain unreachable')

	monkeypatch.setattr('proof_harness.runner_boundary_diagnostic.run_valid', observe_run_valid)
	monkeypatch.setattr(browser_module, 'launch_async', launch)
	monkeypatch.setattr(httpx, 'Client', fail_http_client)

	# When
	result = run_runner_boundary_smoke()
	captured = capsys.readouterr()

	# Then
	assert result.to_json() == (
		'{"category":"pre_navigation","closed":true,'
		'"event":"cloakbrowser_runner_boundary_smoke","ok":true,"stage":"pre_navigation"}'
	)
	assert len(observed_configs) == 1
	config = observed_configs[0]
	assert config.base_url == 'https://runner-boundary.invalid'
	assert config.egress_url == 'https://egress.runner-boundary.invalid/identity'
	assert config.proxy_mode is ProxyMode.DIRECT
	assert config.proxy_url is None
	assert config.progress_enabled is True
	assert page.prepared is True
	assert page.navigated is False
	assert browser.viewport == {'width': 1920, 'height': 1080}
	assert browser.closed is True
	assert len(observed_env) == 1
	assert captured.out == ''
	assert captured.err == ''


def test_runner_boundary_classifies_close_failure_without_raw_detail(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# Given
	browser = FakeBrowser(FakeContext(FakePage()), close_fails=True)

	async def launch(*, env: Mapping[str, str], headless: bool, humanize: bool) -> FakeBrowser:
		_ = env, headless, humanize
		return browser

	monkeypatch.setattr(browser_module, 'launch_async', launch)

	# When
	result = run_runner_boundary_smoke()

	# Then
	assert result.to_json() == (
		'{"category":"close_failure","closed":false,'
		'"event":"cloakbrowser_runner_boundary_smoke","ok":false,"stage":"browser_close"}'
	)
	assert all(value not in result.to_json() for value in ('private', 'path', 'credential'))


def test_runner_boundary_classifies_boundary_failure_without_sentinel_or_detail(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# Given
	async def launch(*, env: Mapping[str, str], headless: bool, humanize: bool) -> FakeBrowser:
		_ = env, headless, humanize
		raise RuntimeError('PreNavigationSentinel C:\\private\\path TOKEN=credential')

	monkeypatch.setattr(browser_module, 'launch_async', launch)

	# When
	result = run_runner_boundary_smoke()

	# Then
	assert result.to_json() == (
		'{"category":"boundary_failure","closed":false,'
		'"event":"cloakbrowser_runner_boundary_smoke","ok":false,"stage":"boundary"}'
	)
	assert all(
		value not in result.to_json() for value in ('PreNavigationSentinel', 'private', 'path', 'TOKEN', 'credential')
	)


def test_runner_boundary_entrypoint_emits_one_fixed_sanitized_result(
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	# Given
	result = RunnerBoundaryResult(
		category=Category.PRE_NAVIGATION,
		stage=Stage.PRE_NAVIGATION,
		ok=True,
		closed=True,
	)
	monkeypatch.setattr(entrypoint, 'run_runner_boundary_smoke', lambda: result)

	# When
	exit_code = entrypoint.main()

	# Then
	captured = capsys.readouterr()
	assert exit_code == 0
	assert captured.err == ''
	assert json.loads(captured.out) == {
		'category': 'pre_navigation',
		'closed': True,
		'event': 'cloakbrowser_runner_boundary_smoke',
		'ok': True,
		'stage': 'pre_navigation',
	}
	assert len(captured.out.splitlines()) == 1


def test_runner_boundary_entrypoint_sanitizes_unexpected_failure(
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	# Given
	def fail_diagnostic() -> RunnerBoundaryResult:
		raise RuntimeError('sentinel /env/path credential detail')

	monkeypatch.setattr(entrypoint, 'run_runner_boundary_smoke', fail_diagnostic)

	# When
	exit_code = entrypoint.main()

	# Then
	captured = capsys.readouterr()
	assert exit_code == 1
	assert captured.out == (
		'{"category":"boundary_failure","closed":false,'
		'"event":"cloakbrowser_runner_boundary_smoke","ok":false,"stage":"boundary"}\n'
	)
	assert captured.err == ''
	assert all(value not in captured.out for value in ('sentinel', '/env/path', 'credential', 'detail'))
