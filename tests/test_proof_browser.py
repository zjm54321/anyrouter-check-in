import json
from dataclasses import dataclass, field
from typing import final

import pytest

from proof_harness.browser import BrowserFailure, CloakBrowserBoundary
from proof_harness.config import ProofConfig, parse_proof_config
from tests.test_proof_harness import valid_env


@dataclass(frozen=True, slots=True)
class FakeResponse:
	status: int
	payload: str | dict[str, str]

	async def body(self) -> bytes:
		if isinstance(self.payload, str):
			return self.payload.encode()
		return json.dumps(self.payload).encode()


@dataclass(slots=True)
class FakePage:
	name: str
	response: FakeResponse | None = None
	evaluations: list[str] = field(default_factory=list)
	navigations: list[str] = field(default_factory=list)

	async def evaluate(self, expression: str) -> str:
		self.evaluations.append(expression)
		return 'fake-agent'

	async def goto(self, url: str, *, wait_until: str, timeout: int) -> FakeResponse | None:
		_ = wait_until, timeout
		self.navigations.append(url)
		return self.response


@final
class FakeContext:
	def __init__(self, login_page: FakePage, egress_page: FakePage) -> None:
		self.pages: list[FakePage] = [login_page, egress_page]

	async def new_page(self) -> FakePage:
		return self.pages.pop(0)

	async def cookies(self) -> list[dict[str, str]]:
		return [{'name': 'session', 'value': 'secret', 'domain': 'proof.invalid', 'path': '/'}]


@final
class FakeLaunchedBrowser:
	def __init__(self, context: FakeContext) -> None:
		self.context: FakeContext = context
		self.closed: bool = False

	async def new_context(self, **_kwargs: bool | dict[str, int]) -> FakeContext:
		return self.context

	async def close(self) -> None:
		self.closed = True


@pytest.mark.asyncio
async def test_browser_boundary_uses_reference_flow_and_second_egress_page(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# Given
	config = parse_proof_config(valid_env())
	assert isinstance(config, ProofConfig)
	login_page = FakePage('login')
	egress_page = FakePage('egress', FakeResponse(200, {'ip': '198.51.100.10'}))
	browser = FakeLaunchedBrowser(FakeContext(login_page, egress_page))
	calls: list[tuple[str, str]] = []

	async def launch(**_kwargs: bool | str | dict[str, str]) -> FakeLaunchedBrowser:
		return browser

	async def prepare(_page: FakePage) -> None:
		calls.append(('prepare', 'page'))

	async def navigate(_page: FakePage, url: str, _timeout: int) -> None:
		calls.append(('navigate', url))

	async def login(_page: FakePage, _email: str, _password: str, _timeout: int) -> None:
		calls.append(('login', 'form'))

	async def verify(_page: FakePage, url: str, _timeout: int) -> dict[str, int]:
		calls.append(('verify', url))
		return {'id': 12345}

	monkeypatch.setattr('proof_harness.browser.launch_async', launch)
	monkeypatch.setattr('proof_harness.browser.prepare_browser_page', prepare)
	monkeypatch.setattr('proof_harness.browser.navigate_login_page', navigate)
	monkeypatch.setattr('proof_harness.browser.login_with_email_form', login)
	monkeypatch.setattr('proof_harness.browser.verify_browser_login', verify)

	# When
	session = await CloakBrowserBoundary().login_async(config)

	# Then
	assert calls == [
		('prepare', 'page'),
		('navigate', 'https://proof.invalid/login'),
		('login', 'form'),
		('verify', 'https://proof.invalid/console'),
	]
	assert egress_page.navigations == ['https://egress.invalid/identity']
	assert login_page.evaluations == ['() => navigator.userAgent']
	assert egress_page.evaluations == []
	assert session.egress_identity == '198.51.100.10'
	assert browser.closed is True


@pytest.mark.parametrize(
	'response,category',
	[
		(None, 'browser_egress_http_failure'),
		(FakeResponse(503, {'identity': '198.51.100.10'}), 'browser_egress_http_failure'),
		(FakeResponse(200, 'secret invalid json'), 'browser_egress_non_json'),
		(FakeResponse(200, {}), 'browser_egress_required'),
	],
)
@pytest.mark.asyncio
async def test_browser_egress_failure_is_bounded(
	monkeypatch: pytest.MonkeyPatch,
	response: FakeResponse | None,
	category: str,
) -> None:
	# Given
	config = parse_proof_config(valid_env())
	assert isinstance(config, ProofConfig)
	browser = FakeLaunchedBrowser(FakeContext(FakePage('login'), FakePage('egress', response)))

	async def launch(**_kwargs: bool | str | dict[str, str]) -> FakeLaunchedBrowser:
		return browser

	async def no_action(*_args: FakePage | str | int) -> None:
		return None

	async def verify(_page: FakePage, _url: str, _timeout: int) -> dict[str, int]:
		return {'id': 12345}

	monkeypatch.setattr('proof_harness.browser.launch_async', launch)
	monkeypatch.setattr('proof_harness.browser.prepare_browser_page', no_action)
	monkeypatch.setattr('proof_harness.browser.navigate_login_page', no_action)
	monkeypatch.setattr('proof_harness.browser.login_with_email_form', no_action)
	monkeypatch.setattr('proof_harness.browser.verify_browser_login', verify)

	# When / Then
	with pytest.raises(BrowserFailure) as captured:
		_ = await CloakBrowserBoundary().login_async(config)
	assert captured.value.category == category
	assert 'secret invalid json' not in str(captured.value)
