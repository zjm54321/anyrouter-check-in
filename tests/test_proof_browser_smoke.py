import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import anyio
import pytest


def diagnostic_module():
	import proof_harness.startup_diagnostic as diagnostic

	return diagnostic


@dataclass(slots=True)
class FakePage:
	navigations: list[str] = field(default_factory=list)

	async def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
		_ = wait_until, timeout
		self.navigations.append(url)


@dataclass(slots=True)
class FakeContext:
	page: FakePage

	async def new_page(self) -> FakePage:
		return self.page


@dataclass(slots=True)
class FakeBrowser:
	context: FakeContext
	closed: bool = False

	async def new_context(self) -> FakeContext:
		return self.context

	async def close(self) -> None:
		self.closed = True


@dataclass(slots=True)
class SlowCloseBrowser:
	context: FakeContext

	async def new_context(self) -> FakeContext:
		return self.context

	async def close(self) -> None:
		await anyio.sleep(1)


def smoke_env(tmp_path: str, binary: str = sys.executable) -> dict[str, str]:
	home = os.path.join(tmp_path, 'home')
	return {
		'ANYROUTER_ACCOUNTS': 'credential-sentinel',
		'CHECKIN_PROXY_URL': 'proxy-sentinel',
		'CLOAKBROWSER_BINARY_PATH': binary,
		'DISPLAY': ':99',
		'HOME': home,
		'PATH': os.environ['PATH'],
		'PROVIDERS': 'application-sentinel',
		'TMPDIR': os.path.join(home, '.runtime'),
		'XAUTHORITY': os.path.join(tmp_path, 'xvfb-run.opaque', 'Xauthority'),
		'XDG_CACHE_HOME': os.path.join(home, '.cache'),
		'XDG_CONFIG_HOME': os.path.join(home, '.config'),
		'XDG_RUNTIME_DIR': os.path.join(home, '.runtime'),
	}


@pytest.mark.asyncio
async def test_startup_smoke_uses_about_blank_and_returns_canonical_success(
	monkeypatch: pytest.MonkeyPatch,
	tmp_path: os.PathLike[str],
) -> None:
	# Given
	diagnostic = diagnostic_module()
	page = FakePage()
	browser = FakeBrowser(FakeContext(page))
	calls: list[dict[str, bool | dict[str, str]]] = []
	forwarded_envs: list[dict[str, str]] = []

	async def launch(*, headless: bool, humanize: bool, env: dict[str, str]) -> FakeBrowser:
		calls.append({'env': env, 'headless': headless, 'humanize': humanize})
		forwarded_envs.append(env)
		return browser

	monkeypatch.setattr(diagnostic, 'launch_async', launch)
	env = smoke_env(str(tmp_path))
	expected_browser_env = {
		name: env[name]
		for name in (
			'DISPLAY',
			'HOME',
			'PATH',
			'TMPDIR',
			'XAUTHORITY',
			'XDG_CACHE_HOME',
			'XDG_CONFIG_HOME',
			'XDG_RUNTIME_DIR',
		)
	}

	# When
	result = await diagnostic.run_diagnostic(env)

	# Then
	assert result.to_json() == (
		'{"category":"ready","event":"cloakbrowser_startup_smoke","ok":true,"stage":"complete"}'
	)
	assert page.navigations == ['about:blank']
	assert browser.closed is True
	assert calls == [{'env': expected_browser_env, 'headless': False, 'humanize': False}]
	assert {'ANYROUTER_ACCOUNTS', 'CHECKIN_PROXY_URL', 'PROVIDERS'}.isdisjoint(forwarded_envs[0])


@pytest.mark.asyncio
async def test_startup_smoke_redacts_launch_exception_to_fixed_enum(
	monkeypatch: pytest.MonkeyPatch,
	tmp_path: os.PathLike[str],
) -> None:
	# Given
	diagnostic = diagnostic_module()

	async def launch(**_kwargs: bool | str | dict[str, str]) -> FakeBrowser:
		raise RuntimeError('secret/path/--unexpected-argument')

	monkeypatch.setattr(diagnostic, 'launch_async', launch)

	# When
	result = await diagnostic.run_diagnostic(smoke_env(str(tmp_path)))

	# Then
	assert result.to_json() == (
		'{"category":"launch_failed","event":"cloakbrowser_startup_smoke","ok":false,"stage":"launch"}'
	)
	assert 'secret/path' not in result.to_json()


@pytest.mark.asyncio
async def test_startup_smoke_bounds_launch_timeout(
	monkeypatch: pytest.MonkeyPatch,
	tmp_path: os.PathLike[str],
) -> None:
	# Given
	diagnostic = diagnostic_module()

	async def launch(**_kwargs: bool | str | dict[str, str]) -> FakeBrowser:
		await anyio.sleep(1)
		raise AssertionError('unreachable')

	monkeypatch.setattr(diagnostic, 'launch_async', launch)
	monkeypatch.setattr(diagnostic, 'DIAGNOSTIC_TIMEOUT_SECONDS', 0.01)

	# When
	result = await diagnostic.run_diagnostic(smoke_env(str(tmp_path)))

	# Then
	assert result.to_json() == (
		'{"category":"launch_timeout","event":"cloakbrowser_startup_smoke","ok":false,"stage":"launch"}'
	)


@pytest.mark.asyncio
async def test_startup_smoke_bounds_browser_close_timeout(
	monkeypatch: pytest.MonkeyPatch,
	tmp_path: os.PathLike[str],
) -> None:
	# Given
	diagnostic = diagnostic_module()
	browser = SlowCloseBrowser(FakeContext(FakePage()))

	async def launch(**_kwargs: bool | str | dict[str, str]) -> SlowCloseBrowser:
		return browser

	monkeypatch.setattr(diagnostic, 'launch_async', launch)
	monkeypatch.setattr(diagnostic, 'DIAGNOSTIC_TIMEOUT_SECONDS', 0.01)

	# When
	result = await diagnostic.run_diagnostic(smoke_env(str(tmp_path)))

	# Then
	assert result.to_json() == (
		'{"category":"close_timeout","event":"cloakbrowser_startup_smoke","ok":false,"stage":"close"}'
	)


def test_startup_smoke_classifies_unwritable_home_before_display(
	tmp_path: os.PathLike[str],
) -> None:
	# Given
	diagnostic = diagnostic_module()
	blocked_parent = os.path.join(tmp_path, 'blocked')
	with open(blocked_parent, 'w', encoding='utf-8') as blocked:
		_ = blocked.write('x')
	env = smoke_env(str(tmp_path))
	env['HOME'] = os.path.join(blocked_parent, 'home')

	# When
	result = diagnostic.run_preflight(env)

	# Then
	assert result.to_json() == (
		'{"category":"home_unwritable","event":"cloakbrowser_startup_smoke","ok":false,"stage":"home"}'
	)


def test_startup_smoke_classifies_missing_display_without_launch(
	tmp_path: os.PathLike[str],
) -> None:
	# Given
	diagnostic = diagnostic_module()
	env = smoke_env(str(tmp_path))
	_ = env.pop('DISPLAY')

	# When
	result = diagnostic.run_preflight(env)

	# Then
	assert result.to_json() == (
		'{"category":"display_unavailable","event":"cloakbrowser_startup_smoke","ok":false,"stage":"display"}'
	)


def test_startup_smoke_classifies_missing_binary_without_fallback(
	tmp_path: os.PathLike[str],
) -> None:
	# Given
	diagnostic = diagnostic_module()
	env = smoke_env(str(tmp_path), binary=os.path.join(str(tmp_path), 'missing-browser'))

	# When
	result = diagnostic.run_preflight(env)

	# Then
	assert result.to_json() == (
		'{"category":"binary_path_unavailable","event":"cloakbrowser_startup_smoke","ok":false,"stage":"path"}'
	)


def test_startup_smoke_entrypoint_emits_only_one_safe_json_line() -> None:
	# Given
	env = os.environ.copy()
	_ = env.pop('CLOAKBROWSER_BINARY_PATH', None)
	_ = env.pop('DISPLAY', None)

	# When
	completed = subprocess.run(
		[sys.executable, 'proof_browser_smoke.py'],
		check=False,
		capture_output=True,
		text=True,
		env=env,
		cwd=Path(__file__).parent.parent,
		timeout=10,
	)

	# Then
	assert completed.returncode == 1
	assert completed.stderr == ''
	assert completed.stdout == (
		'{"category":"binary_path_unavailable","event":"cloakbrowser_startup_smoke","ok":false,"stage":"path"}\n'
	)
