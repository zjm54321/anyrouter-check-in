import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

import proof_harness.browser as browser_module

PROBE_PATH = Path(__file__).parent.parent / 'accepted_image_aba_probe.py'
EMAIL_SENTINEL = 'ab-email-sentinel@example.invalid'
PASSWORD_SENTINEL = 'ab-password-sentinel-not-a-credential'


@dataclass(slots=True)
class FakePage:
	prepared: bool = False

	async def add_init_script(self, _script: str) -> None:
		self.prepared = True

	async def goto(self, _url: str, **_kwargs: str | float | None) -> None:
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

	async def new_context(self, *, viewport: dict[str, int]) -> FakeContext:
		assert viewport == {'width': 1920, 'height': 1080}
		return self.context

	async def close(self) -> None:
		if self.close_fails:
			raise RuntimeError(f'{EMAIL_SENTINEL}/{PASSWORD_SENTINEL}/path/cookies')
		self.closed = True


def test_probe_runs_real_sync_boundary_and_stops_before_navigation(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# Given
	assert PROBE_PATH.is_file(), 'accepted-image probe script is missing'
	import accepted_image_aba_probe as probe

	page = FakePage()
	browser = FakeBrowser(FakeContext(page))
	forwarded_envs: list[Mapping[str, str]] = []

	async def launch(*, env: Mapping[str, str], headless: bool, humanize: bool) -> FakeBrowser:
		assert headless is False
		assert humanize is True
		forwarded_envs.append(env)
		return browser

	monkeypatch.setenv('ANYROUTER_EMAIL', EMAIL_SENTINEL)
	monkeypatch.setenv('ANYROUTER_PASSWORD', PASSWORD_SENTINEL)
	monkeypatch.setattr(browser_module, 'launch_async', launch)

	# When
	result = probe.run_probe()

	# Then
	assert result.to_json() == (
		'{"category":"pre_navigation","closed":true,'
		'"event":"accepted_image_browser_boundary_probe","ok":true,"stage":"pre_navigation"}'
	)
	assert page.prepared is True
	assert browser.closed is True
	assert len(forwarded_envs) == 1
	assert forwarded_envs[0]['ANYROUTER_EMAIL'] == EMAIL_SENTINEL
	assert forwarded_envs[0]['ANYROUTER_PASSWORD'] == PASSWORD_SENTINEL
	assert all(name.lower() not in {'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'} for name in forwarded_envs[0])
	assert all(value not in result.to_json() for value in (EMAIL_SENTINEL, PASSWORD_SENTINEL))


def test_probe_classifies_launch_failure_without_raw_detail(monkeypatch: pytest.MonkeyPatch) -> None:
	# Given
	assert PROBE_PATH.is_file(), 'accepted-image probe script is missing'
	import accepted_image_aba_probe as probe

	async def launch(*, env: Mapping[str, str], headless: bool, humanize: bool) -> FakeBrowser:
		_ = env, headless, humanize
		raise RuntimeError(f'{EMAIL_SENTINEL}/{PASSWORD_SENTINEL}/{os.getcwd()}/cookies')

	monkeypatch.setattr(browser_module, 'launch_async', launch)

	# When
	result = probe.run_probe()

	# Then
	assert result.to_json() == (
		'{"category":"browser_launch_failure","closed":false,'
		'"event":"accepted_image_browser_boundary_probe","ok":false,"stage":"browser_launch"}'
	)
	assert all(value not in result.to_json() for value in (EMAIL_SENTINEL, PASSWORD_SENTINEL, os.getcwd(), 'cookies'))


def test_probe_classifies_close_failure_without_raw_detail(monkeypatch: pytest.MonkeyPatch) -> None:
	# Given
	assert PROBE_PATH.is_file(), 'accepted-image probe script is missing'
	import accepted_image_aba_probe as probe

	browser = FakeBrowser(FakeContext(FakePage()), close_fails=True)

	async def launch(*, env: Mapping[str, str], headless: bool, humanize: bool) -> FakeBrowser:
		_ = env, headless, humanize
		return browser

	monkeypatch.setattr(browser_module, 'launch_async', launch)

	# When
	result = probe.run_probe()

	# Then
	assert result.to_json() == (
		'{"category":"close_failure","closed":false,'
		'"event":"accepted_image_browser_boundary_probe","ok":false,"stage":"browser_close"}'
	)
	assert all(value not in result.to_json() for value in (EMAIL_SENTINEL, PASSWORD_SENTINEL, 'path', 'cookies'))


def test_probe_entrypoint_fails_closed_with_one_fixed_json_line(
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	# Given
	assert PROBE_PATH.is_file(), 'accepted-image probe script is missing'
	import accepted_image_aba_probe as probe

	def fail_probe() -> probe.ProbeResult:
		raise RuntimeError(f'{EMAIL_SENTINEL}/{PASSWORD_SENTINEL}/{os.getcwd()}/cookies')

	monkeypatch.setattr(probe, 'run_probe', fail_probe)

	# When
	exit_code = probe.main()

	# Then
	captured = capsys.readouterr()
	assert exit_code == 1
	assert captured.out == (
		'{"category":"boundary_failure","closed":false,'
		'"event":"accepted_image_browser_boundary_probe","ok":false,"stage":"boundary"}\n'
	)
	assert captured.err == ''
	assert all(value not in captured.out for value in (EMAIL_SENTINEL, PASSWORD_SENTINEL, os.getcwd(), 'cookies'))
