from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TypedDict

import httpx
import pytest

import proof_harness.navigation_diagnostic as diagnostic


@dataclass(slots=True)
class FakeResponse:
	status: int
	body_reads: int = 0

	async def body(self) -> bytes:
		self.body_reads += 1
		raise AssertionError('response bodies are forbidden')


@dataclass(slots=True)
class FakePage:
	responses: list[FakeResponse | None | Exception]
	prepared: bool = False
	interactions: list[str] = field(default_factory=list)

	async def goto(self, url: str, *, wait_until: str, timeout: float) -> FakeResponse | None:
		_ = wait_until, timeout
		self.interactions.append(f'goto:{url}')
		match self.responses.pop(0):
			case Exception() as error:
				raise error
			case FakeResponse() | None as response:
				return response

	async def wait_for_selector(self, selector: str, *, state: str, timeout: float) -> None:
		_ = selector, state, timeout
		self.interactions.append('wait_for_selector')


@dataclass(slots=True)
class FakeContext:
	page: FakePage
	viewport: Mapping[str, int] | None = None

	async def new_page(self) -> FakePage:
		return self.page


@dataclass(slots=True)
class FakeBrowser:
	context: FakeContext
	closed: bool = False

	async def new_context(self, *, viewport: Mapping[str, int]) -> FakeContext:
		self.context.viewport = viewport
		return self.context

	async def close(self) -> None:
		self.closed = True


class LaunchCall(TypedDict):
	env: Mapping[str, str]
	headless: bool
	humanize: bool


@dataclass(slots=True)
class BrowserRig:
	page: FakePage
	browser: FakeBrowser = field(init=False)
	launch_calls: list[LaunchCall] = field(default_factory=list)

	def __post_init__(self) -> None:
		self.browser = FakeBrowser(FakeContext(self.page))

	async def launch(
		self,
		*,
		env: Mapping[str, str],
		headless: bool,
		humanize: bool,
	) -> FakeBrowser:
		self.launch_calls.append({'env': env, 'headless': headless, 'humanize': humanize})
		return self.browser

	async def prepare(self, page: FakePage) -> None:
		page.prepared = True


def runtime_env() -> dict[str, str]:
	return {
		'ANYROUTER_ACCOUNTS': 'credential-sentinel',
		'ANYROUTER_DIAGNOSTIC_BASE_URL': 'https://anyrouter.top/',
		'DISPLAY': ':99',
		'HTTP_PROXY': 'proxy-sentinel',
		'HTTPS_PROXY': 'proxy-sentinel',
		'HOME': '/home/cloak',
		'NO_PROXY': 'proxy-sentinel',
		'PATH': '/usr/bin',
	}


def install_rig(monkeypatch: pytest.MonkeyPatch, rig: BrowserRig) -> None:
	monkeypatch.setattr(diagnostic, 'launch_async', rig.launch)
	monkeypatch.setattr(diagnostic, 'prepare_browser_page', rig.prepare)


@pytest.mark.asyncio
async def test_navigation_diagnostic_uses_exact_browser_configuration_without_sensitive_actions(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# Given
	root_response = FakeResponse(503)
	login_response = FakeResponse(204)
	rig = BrowserRig(FakePage([root_response, login_response]))
	install_rig(monkeypatch, rig)

	def forbidden_http_client() -> None:
		raise AssertionError('HTTPX clients are forbidden')

	monkeypatch.setattr(httpx, 'Client', forbidden_http_client)
	monkeypatch.setattr(httpx, 'AsyncClient', forbidden_http_client)
	env = runtime_env()

	# When
	result = await diagnostic.run_diagnostic(env)

	# Then
	assert result.to_json() == (
		'{"close":"closed","event":"anyrouter_navigation_diagnostic",'
		'"login_navigation":"http_2xx","login_shell":"ready","ok":true,'
		'"result":"ready","root_navigation":"http_5xx","stage":"complete"}'
	)
	assert rig.launch_calls == [
		{
			'env': {key: value for key, value in env.items() if 'proxy' not in key.lower()},
			'headless': False,
			'humanize': True,
		}
	]
	assert rig.browser.context.viewport == {'width': 1920, 'height': 1080}
	assert rig.page.prepared is True
	assert rig.page.interactions == [
		'goto:https://anyrouter.top',
		'goto:https://anyrouter.top/login',
		'wait_for_selector',
	]
	assert root_response.body_reads == 0
	assert login_response.body_reads == 0
	assert rig.browser.closed is True


@pytest.mark.asyncio
async def test_root_transport_failure_is_observed_but_login_is_still_attempted(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# Given
	rig = BrowserRig(FakePage([RuntimeError('root secret'), FakeResponse(200)]))
	install_rig(monkeypatch, rig)

	# When
	result = await diagnostic.run_diagnostic(runtime_env())

	# Then
	assert result.root_navigation is diagnostic.NavigationStatus.TRANSPORT_FAILURE
	assert result.login_navigation is diagnostic.NavigationStatus.HTTP_2XX
	assert result.overall_result is diagnostic.OverallResult.READY
	assert rig.page.interactions[:2] == [
		'goto:https://anyrouter.top',
		'goto:https://anyrouter.top/login',
	]
	assert 'root secret' not in result.to_json()


@pytest.mark.parametrize(
	'value',
	('https://anyrouter.top', 'https://anyrouter.top/', ' HTTPS://ANYROUTER.TOP/ '),
)
def test_base_url_boundary_normalizes_only_the_canonical_origin(value: str) -> None:
	# When / Then
	assert diagnostic.parse_base_url(value) == 'https://anyrouter.top'


@pytest.mark.parametrize(
	'value',
	(
		'http://anyrouter.top',
		'https://anyrouter.top:443',
		'https://anyrouter.top/login',
		'https://anyrouter.top?query=secret',
		'https://user:anyrouter@anyrouter.top',
		'https://evil.example',
	),
)
def test_base_url_boundary_rejects_every_noncanonical_origin(value: str) -> None:
	# When / Then
	assert diagnostic.parse_base_url(value) is None


@pytest.mark.asyncio
async def test_invalid_runtime_base_url_fails_before_browser_launch(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# Given
	rig = BrowserRig(FakePage([]))
	install_rig(monkeypatch, rig)
	env = runtime_env()
	env['ANYROUTER_DIAGNOSTIC_BASE_URL'] = 'https://evil.example/credential'

	# When
	result = await diagnostic.run_diagnostic(env)

	# Then
	assert result.to_json() == (
		'{"close":"not_started","event":"anyrouter_navigation_diagnostic",'
		'"login_navigation":"not_attempted","login_shell":"not_attempted","ok":false,'
		'"result":"config_invalid","root_navigation":"not_attempted","stage":"config"}'
	)
	assert rig.launch_calls == []
	assert 'evil' not in result.to_json()
	assert 'credential' not in result.to_json()
