import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

import pytest


def real_diagnostic_module():
	import proof_harness.real_launch_diagnostic as diagnostic

	return diagnostic


class LaunchKwargs(TypedDict):
	args: tuple[str, ...]
	env: Mapping[str, str]
	headless: bool
	humanize: bool


@dataclass(slots=True)
class FakePage:
	prepared: bool = False


@dataclass(slots=True)
class FakeContext:
	page: FakePage
	viewport: dict[str, int] | None = None

	async def new_page(self) -> FakePage:
		return self.page


@dataclass(slots=True)
class FakeBrowser:
	context: FakeContext
	closed: bool = False

	async def new_context(self, *, viewport: dict[str, int]) -> FakeContext:
		self.context.viewport = viewport
		return self.context

	async def close(self) -> None:
		self.closed = True


def smoke_env(
	tmp_path: Path,
	humanize: str = 'true',
	fingerprint_mode: str = 'fixed',
	fingerprint_seed: str = '42424',
) -> dict[str, str]:
	home = tmp_path / 'home'
	return {
		'CLOAKBROWSER_BINARY_PATH': sys.executable,
		'DISPLAY': ':99',
		'HOME': str(home),
		'PATH': os.environ['PATH'],
		'PROOF_FINGERPRINT_MODE': fingerprint_mode,
		'PROOF_FINGERPRINT_SEED': fingerprint_seed,
		'PROOF_HUMANIZE': humanize,
		'TMPDIR': str(home / '.runtime'),
		'XAUTHORITY': str(tmp_path / 'xvfb-run' / 'Xauthority'),
		'XDG_CACHE_HOME': str(home / '.cache'),
		'XDG_CONFIG_HOME': str(home / '.config'),
		'XDG_RUNTIME_DIR': str(home / '.runtime'),
	}


@pytest.mark.asyncio
async def test_real_launch_smoke_reaches_prepare_without_navigation(
	monkeypatch: pytest.MonkeyPatch,
	tmp_path: Path,
) -> None:
	# Given
	diagnostic = real_diagnostic_module()
	page = FakePage()
	browser = FakeBrowser(FakeContext(page))
	calls: list[LaunchKwargs] = []

	async def launch(
		*,
		args: Sequence[str] | None,
		env: Mapping[str, str],
		headless: bool,
		humanize: bool,
	) -> FakeBrowser:
		calls.append({
			'args': tuple(args or ()),
			'env': env,
			'headless': headless,
			'humanize': humanize,
		})
		return browser

	async def prepare(_page: FakePage) -> None:
		page.prepared = True

	monkeypatch.setattr(diagnostic, 'launch_async', launch)
	monkeypatch.setattr(diagnostic, 'prepare_browser_page', prepare)
	env = smoke_env(tmp_path)

	# When
	result = await diagnostic.run_diagnostic(env)

	# Then
	expected_env = {
		key: value
		for key, value in env.items()
		if key.lower() not in {'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'}
	}
	assert result.to_json() == (
		'{"category":"ready","event":"cloakbrowser_proof_launch_smoke",'
		'"ok":true,"stage":"complete"}'
	)
	assert calls == [{
		'args': ('--fingerprint=42424',),
		'env': expected_env,
		'headless': False,
		'humanize': True,
	}]
	assert browser.context.viewport == {'width': 1920, 'height': 1080}
	assert page.prepared is True
	assert browser.closed is True


@pytest.mark.asyncio
async def test_real_launch_smoke_classifies_prepare_failure_without_leak(
	monkeypatch: pytest.MonkeyPatch,
	tmp_path: Path,
) -> None:
	# Given
	diagnostic = real_diagnostic_module()
	browser = FakeBrowser(FakeContext(FakePage()))

	async def launch(
		*,
		args: Sequence[str] | None,
		env: Mapping[str, str],
		headless: bool,
		humanize: bool,
	) -> FakeBrowser:
		_ = args, env, headless, humanize
		return browser

	async def prepare(_page: FakePage) -> None:
		raise RuntimeError('secret/path/credential')

	monkeypatch.setattr(diagnostic, 'launch_async', launch)
	monkeypatch.setattr(diagnostic, 'prepare_browser_page', prepare)

	# When
	result = await diagnostic.run_diagnostic(smoke_env(tmp_path))

	# Then
	assert result.to_json() == (
		'{"category":"prepare_failed","event":"cloakbrowser_proof_launch_smoke",'
		'"ok":false,"stage":"prepare"}'
	)
	assert 'credential' not in result.to_json()
	assert browser.closed is True


@pytest.mark.asyncio
async def test_real_launch_smoke_forwards_false_humanize_mode(
	monkeypatch: pytest.MonkeyPatch,
	tmp_path: Path,
) -> None:
	# Given
	diagnostic = real_diagnostic_module()
	browser = FakeBrowser(FakeContext(FakePage()))
	observed: list[bool] = []

	async def launch(
		*,
		args: Sequence[str] | None,
		env: Mapping[str, str],
		headless: bool,
		humanize: bool,
	) -> FakeBrowser:
		_ = args, env, headless
		observed.append(not humanize)
		return browser

	async def prepare(_page: FakePage) -> None:
		return None

	monkeypatch.setattr(diagnostic, 'launch_async', launch)
	monkeypatch.setattr(diagnostic, 'prepare_browser_page', prepare)

	# When
	result = await diagnostic.run_diagnostic(smoke_env(tmp_path, humanize='false'))

	# Then
	assert result.ok is True
	assert observed == [True]


@pytest.mark.asyncio
async def test_real_launch_smoke_omits_fingerprint_argument_in_default_mode(
	monkeypatch: pytest.MonkeyPatch,
	tmp_path: Path,
) -> None:
	# Given
	diagnostic = real_diagnostic_module()
	browser = FakeBrowser(FakeContext(FakePage()))
	observed: list[tuple[str, ...]] = []

	async def launch(
		*,
		args: Sequence[str] | None,
		env: Mapping[str, str],
		headless: bool,
		humanize: bool,
	) -> FakeBrowser:
		_ = env, headless, humanize
		observed.append(tuple(args or ()))
		return browser

	async def prepare(_page: FakePage) -> None:
		return None

	monkeypatch.setattr(diagnostic, 'launch_async', launch)
	monkeypatch.setattr(diagnostic, 'prepare_browser_page', prepare)

	# When
	result = await diagnostic.run_diagnostic(
		smoke_env(tmp_path, humanize='false', fingerprint_mode='default'),
	)

	# Then
	assert result.ok is True
	assert observed == [()]


@pytest.mark.asyncio
async def test_real_launch_smoke_uses_requested_fingerprint_seed(
	monkeypatch: pytest.MonkeyPatch,
	tmp_path: Path,
) -> None:
	# Given
	diagnostic = real_diagnostic_module()
	browser = FakeBrowser(FakeContext(FakePage()))
	observed: list[tuple[str, ...]] = []

	async def launch(
		*,
		args: Sequence[str] | None,
		env: Mapping[str, str],
		headless: bool,
		humanize: bool,
	) -> FakeBrowser:
		_ = env, headless, humanize
		observed.append(tuple(args or ()))
		return browser

	async def prepare(_page: FakePage) -> None:
		return None

	monkeypatch.setattr(diagnostic, 'launch_async', launch)
	monkeypatch.setattr(diagnostic, 'prepare_browser_page', prepare)

	# When
	result = await diagnostic.run_diagnostic(
		smoke_env(tmp_path, fingerprint_seed='12345'),
	)

	# Then
	assert result.ok is True
	assert observed == [('--fingerprint=12345',)]


@pytest.mark.asyncio
async def test_real_launch_smoke_rejects_out_of_range_fingerprint_seed(
	tmp_path: Path,
) -> None:
	# Given
	env = smoke_env(tmp_path, fingerprint_seed='9999')

	# When
	result = await real_diagnostic_module().run_diagnostic(env)

	# Then
	assert result.to_json() == (
		'{"category":"config_invalid","event":"cloakbrowser_proof_launch_smoke",'
		'"ok":false,"stage":"launch"}'
	)


@pytest.mark.asyncio
async def test_real_launch_smoke_uses_strict_allowlist_when_requested(
	monkeypatch: pytest.MonkeyPatch,
	tmp_path: Path,
) -> None:
	# Given
	diagnostic = real_diagnostic_module()
	browser = FakeBrowser(FakeContext(FakePage()))
	observed: list[Mapping[str, str]] = []

	async def launch(
		*,
		args: Sequence[str] | None,
		env: Mapping[str, str],
		headless: bool,
		humanize: bool,
	) -> FakeBrowser:
		_ = args, headless, humanize
		observed.append(env)
		return browser

	async def prepare(_page: FakePage) -> None:
		return None

	monkeypatch.setattr(diagnostic, 'launch_async', launch)
	monkeypatch.setattr(diagnostic, 'prepare_browser_page', prepare)
	env = smoke_env(tmp_path, humanize='false')
	env['PROOF_ENV_MODE'] = 'allowlist'
	env['UNRELATED_SENTINEL'] = 'not-forwarded'

	# When
	result = await diagnostic.run_diagnostic(env)

	# Then
	assert result.ok is True
	expected_names = (
		'DISPLAY',
		'HOME',
		'LANG',
		'LC_ALL',
		'PATH',
		'TMPDIR',
		'XAUTHORITY',
		'XDG_CACHE_HOME',
		'XDG_CONFIG_HOME',
		'XDG_RUNTIME_DIR',
	)
	assert observed == [{
		name: env[name]
		for name in expected_names
		if name in env
	}]
	assert 'UNRELATED_SENTINEL' not in observed[0]


@pytest.mark.asyncio
async def test_real_launch_smoke_rejects_unknown_environment_mode(
	tmp_path: Path,
) -> None:
	# Given
	env = smoke_env(tmp_path)
	env['PROOF_ENV_MODE'] = 'unknown'

	# When
	result = await real_diagnostic_module().run_diagnostic(env)

	# Then
	assert result.to_json() == (
		'{"category":"config_invalid","event":"cloakbrowser_proof_launch_smoke",'
		'"ok":false,"stage":"launch"}'
	)
