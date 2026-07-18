from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import anyio
import pytest

import proof_harness.navigation_diagnostic as diagnostic


@dataclass(slots=True)
class FakeResponse:
	status: int

	async def body(self) -> bytes:
		raise AssertionError('response bodies are forbidden')


@dataclass(slots=True)
class TimedPage:
	responses: list[FakeResponse | None]
	navigation_delays: list[float] = field(default_factory=lambda: [0.0, 0.0])
	shell_delay: float = 0.0
	shell_error: Exception | None = None
	navigations: list[str] = field(default_factory=list)
	shell_checks: int = 0

	async def goto(self, url: str, *, wait_until: str, timeout: float) -> FakeResponse | None:
		_ = wait_until, timeout
		self.navigations.append(url)
		await anyio.sleep(self.navigation_delays.pop(0))
		return self.responses.pop(0)

	async def wait_for_selector(self, selector: str, *, state: str, timeout: float) -> None:
		_ = selector, state, timeout
		self.shell_checks += 1
		await anyio.sleep(self.shell_delay)
		if self.shell_error is not None:
			raise self.shell_error


@dataclass(slots=True)
class TimedContext:
	page: TimedPage

	async def new_page(self) -> TimedPage:
		return self.page


@dataclass(slots=True)
class TimedBrowser:
	context: TimedContext
	close_delay: float = 0.0
	close_error: Exception | None = None
	closed: bool = False

	async def new_context(self, *, viewport: Mapping[str, int]) -> TimedContext:
		assert viewport == {'width': 1920, 'height': 1080}
		return self.context

	async def close(self) -> None:
		await anyio.sleep(self.close_delay)
		if self.close_error is not None:
			raise self.close_error
		self.closed = True


def env() -> dict[str, str]:
	return {'ANYROUTER_DIAGNOSTIC_BASE_URL': 'https://anyrouter.top'}


def install(
	monkeypatch: pytest.MonkeyPatch,
	page: TimedPage,
	*,
	close_delay: float = 0.0,
	close_error: Exception | None = None,
) -> TimedBrowser:
	browser = TimedBrowser(TimedContext(page), close_delay=close_delay, close_error=close_error)

	async def launch(*, env: Mapping[str, str], headless: bool, humanize: bool) -> TimedBrowser:
		_ = env
		assert headless is False
		assert humanize is True
		return browser

	async def prepare(_page: TimedPage) -> None:
		return None

	monkeypatch.setattr(diagnostic, 'launch_async', launch)
	monkeypatch.setattr(diagnostic, 'prepare_browser_page', prepare)
	return browser


@pytest.mark.parametrize(
	('status', 'navigation', 'shell', 'overall', 'ok'),
	(
		(302, diagnostic.NavigationStatus.HTTP_3XX, diagnostic.ShellStatus.READY, diagnostic.OverallResult.READY, True),
		(
			404,
			diagnostic.NavigationStatus.HTTP_4XX,
			diagnostic.ShellStatus.NOT_ATTEMPTED,
			diagnostic.OverallResult.LOGIN_HTTP_4XX,
			False,
		),
		(
			503,
			diagnostic.NavigationStatus.HTTP_5XX,
			diagnostic.ShellStatus.NOT_ATTEMPTED,
			diagnostic.OverallResult.LOGIN_HTTP_5XX,
			False,
		),
	),
)
@pytest.mark.asyncio
async def test_login_http_class_determines_overall_result(
	monkeypatch: pytest.MonkeyPatch,
	status: int,
	navigation: diagnostic.NavigationStatus,
	shell: diagnostic.ShellStatus,
	overall: diagnostic.OverallResult,
	ok: bool,
) -> None:
	# Given
	page = TimedPage([FakeResponse(200), FakeResponse(status)])
	_ = install(monkeypatch, page)

	# When
	result = await diagnostic.run_diagnostic(env())

	# Then
	assert result.login_navigation is navigation
	assert result.login_shell is shell
	assert result.overall_result is overall
	assert result.ok is ok
	assert page.shell_checks == int(status < 400)


@pytest.mark.asyncio
async def test_login_navigation_timeout_is_bounded_and_browser_closes(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# Given
	page = TimedPage(
		[FakeResponse(200), FakeResponse(200)],
		navigation_delays=[0.0, 1.0],
	)
	browser = install(monkeypatch, page)
	monkeypatch.setattr(diagnostic, 'NAVIGATION_TIMEOUT_SECONDS', 0.01)

	# When
	result = await diagnostic.run_diagnostic(env())

	# Then
	assert result.login_navigation is diagnostic.NavigationStatus.TIMEOUT
	assert result.overall_result is diagnostic.OverallResult.LOGIN_NAVIGATION_TIMEOUT
	assert result.stage is diagnostic.Stage.LOGIN_NAVIGATION
	assert browser.closed is True


@pytest.mark.asyncio
async def test_login_shell_timeout_is_bounded_and_sanitized(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# Given
	page = TimedPage([FakeResponse(200), FakeResponse(200)], shell_delay=1.0)
	_ = install(monkeypatch, page)
	monkeypatch.setattr(diagnostic, 'SHELL_TIMEOUT_SECONDS', 0.01)

	# When
	result = await diagnostic.run_diagnostic(env())

	# Then
	assert result.login_shell is diagnostic.ShellStatus.TIMEOUT
	assert result.overall_result is diagnostic.OverallResult.LOGIN_SHELL_TIMEOUT
	assert result.stage is diagnostic.Stage.LOGIN_SHELL


@pytest.mark.asyncio
async def test_close_timeout_is_bounded_after_successful_shell(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# Given
	page = TimedPage([FakeResponse(200), FakeResponse(200)])
	_ = install(monkeypatch, page, close_delay=1.0)
	monkeypatch.setattr(diagnostic, 'CLOSE_TIMEOUT_SECONDS', 0.01)

	# When
	result = await diagnostic.run_diagnostic(env())

	# Then
	assert result.close_status is diagnostic.CloseStatus.TIMEOUT
	assert result.overall_result is diagnostic.OverallResult.CLOSE_TIMEOUT
	assert result.stage is diagnostic.Stage.CLOSE


@pytest.mark.asyncio
async def test_close_failure_never_overwrites_prior_login_failure(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# Given
	page = TimedPage([FakeResponse(200), FakeResponse(500)])
	_ = install(monkeypatch, page, close_error=RuntimeError('close secret/path'))

	# When
	result = await diagnostic.run_diagnostic(env())

	# Then
	assert result.close_status is diagnostic.CloseStatus.FAILED
	assert result.overall_result is diagnostic.OverallResult.LOGIN_HTTP_5XX
	assert result.stage is diagnostic.Stage.LOGIN_NAVIGATION
	assert 'secret' not in result.to_json()
	assert 'path' not in result.to_json()
