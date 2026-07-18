from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Literal, NewType
from urllib.parse import urlsplit

import anyio
from cloakbrowser import launch_async
from playwright.async_api import Browser, Page, Response
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from proof_harness.navigation_models import (
	CloseStatus,
	DiagnosticResult,
	NavigationStatus,
	OverallResult,
	ShellStatus,
	Stage,
)
from utils.browser import prepare_browser_page

__all__ = (
	'CloseStatus',
	'DiagnosticResult',
	'NavigationStatus',
	'OverallResult',
	'ShellStatus',
	'Stage',
	'parse_base_url',
	'run_diagnostic',
)

CANONICAL_BASE_URL: Final = 'https://anyrouter.top'
BASE_URL_ENV: Final = 'ANYROUTER_DIAGNOSTIC_BASE_URL'
LAUNCH_TIMEOUT_SECONDS: Final = 20.0
SETUP_TIMEOUT_SECONDS: Final = 20.0
NAVIGATION_TIMEOUT_SECONDS: Final = 30.0
SHELL_TIMEOUT_SECONDS: Final = 30.0
CLOSE_TIMEOUT_SECONDS: Final = 20.0
_PROXY_NAMES: Final = frozenset({'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'})
_LOGIN_SHELL_SELECTOR: Final = '.semi-card, #username, button:has(.semi-icon-mail)'

BaseUrl = NewType('BaseUrl', str)


SetupStage = Literal[Stage.LAUNCH, Stage.CONTEXT, Stage.PAGE, Stage.PREPARE]


def parse_base_url(raw_value: str) -> BaseUrl | None:
	try:
		parsed = urlsplit(raw_value.strip())
		port = parsed.port
	except ValueError:
		return None
	if (
		parsed.scheme.lower() != 'https'
		or parsed.hostname != 'anyrouter.top'
		or port is not None
		or parsed.username is not None
		or parsed.password is not None
		or parsed.path not in {'', '/'}
		or parsed.query
		or parsed.fragment
	):
		return None
	return BaseUrl(CANONICAL_BASE_URL)


def _browser_env(env: Mapping[str, str]) -> dict[str, str]:
	return {key: value for key, value in env.items() if key.lower() not in _PROXY_NAMES}


def _navigation_status(response: Response | None) -> NavigationStatus:
	if response is None:
		return NavigationStatus.NO_RESPONSE
	status = response.status
	if 200 <= status < 300:
		return NavigationStatus.HTTP_2XX
	if 300 <= status < 400:
		return NavigationStatus.HTTP_3XX
	if 400 <= status < 500:
		return NavigationStatus.HTTP_4XX
	if 500 <= status < 600:
		return NavigationStatus.HTTP_5XX
	return NavigationStatus.HTTP_OTHER


async def _navigate(page: Page, url: str) -> NavigationStatus:
	try:
		with anyio.fail_after(NAVIGATION_TIMEOUT_SECONDS):
			response = await page.goto(
				url,
				wait_until='load',
				timeout=NAVIGATION_TIMEOUT_SECONDS * 1000,
			)
	except (TimeoutError, PlaywrightTimeoutError):
		return NavigationStatus.TIMEOUT
	except Exception:
		return NavigationStatus.TRANSPORT_FAILURE
	return _navigation_status(response)


async def _wait_for_login_shell(page: Page) -> ShellStatus:
	try:
		with anyio.fail_after(SHELL_TIMEOUT_SECONDS):
			_ = await page.wait_for_selector(
				_LOGIN_SHELL_SELECTOR,
				state='visible',
				timeout=SHELL_TIMEOUT_SECONDS * 1000,
			)
	except (TimeoutError, PlaywrightTimeoutError):
		return ShellStatus.TIMEOUT
	except Exception:
		return ShellStatus.FAILED
	return ShellStatus.READY


async def _close_browser(browser: Browser) -> CloseStatus:
	try:
		with anyio.fail_after(CLOSE_TIMEOUT_SECONDS, shield=True):
			await browser.close()
	except (TimeoutError, PlaywrightTimeoutError):
		return CloseStatus.TIMEOUT
	except Exception:
		return CloseStatus.FAILED
	return CloseStatus.CLOSED


def _setup_failure(stage: SetupStage, timed_out: bool) -> OverallResult:
	match stage:
		case Stage.LAUNCH:
			return OverallResult.LAUNCH_TIMEOUT if timed_out else OverallResult.LAUNCH_FAILED
		case Stage.CONTEXT:
			return OverallResult.CONTEXT_TIMEOUT if timed_out else OverallResult.CONTEXT_FAILED
		case Stage.PAGE:
			return OverallResult.PAGE_TIMEOUT if timed_out else OverallResult.PAGE_FAILED
		case Stage.PREPARE:
			return OverallResult.PREPARE_TIMEOUT if timed_out else OverallResult.PREPARE_FAILED


def _login_result(status: NavigationStatus) -> tuple[OverallResult, bool]:
	match status:
		case NavigationStatus.TIMEOUT:
			return OverallResult.LOGIN_NAVIGATION_TIMEOUT, False
		case NavigationStatus.TRANSPORT_FAILURE | NavigationStatus.NOT_ATTEMPTED:
			return OverallResult.LOGIN_TRANSPORT_FAILURE, False
		case NavigationStatus.NO_RESPONSE:
			return OverallResult.LOGIN_NO_RESPONSE, False
		case NavigationStatus.HTTP_OTHER:
			return OverallResult.LOGIN_HTTP_OTHER, False
		case NavigationStatus.HTTP_4XX:
			return OverallResult.LOGIN_HTTP_4XX, False
		case NavigationStatus.HTTP_5XX:
			return OverallResult.LOGIN_HTTP_5XX, False
		case NavigationStatus.HTTP_2XX | NavigationStatus.HTTP_3XX:
			return OverallResult.READY, True


def _shell_result(status: ShellStatus) -> tuple[OverallResult, bool]:
	match status:
		case ShellStatus.READY:
			return OverallResult.READY, True
		case ShellStatus.TIMEOUT:
			return OverallResult.LOGIN_SHELL_TIMEOUT, False
		case ShellStatus.FAILED | ShellStatus.NOT_ATTEMPTED:
			return OverallResult.LOGIN_SHELL_FAILED, False


async def run_diagnostic(env: Mapping[str, str]) -> DiagnosticResult:
	base_url = parse_base_url(env.get(BASE_URL_ENV, CANONICAL_BASE_URL))
	if base_url is None:
		return DiagnosticResult.failure(OverallResult.CONFIG_INVALID, Stage.CONFIG)

	root_navigation = NavigationStatus.NOT_ATTEMPTED
	login_navigation = NavigationStatus.NOT_ATTEMPTED
	login_shell = ShellStatus.NOT_ATTEMPTED
	close_status = CloseStatus.NOT_STARTED
	setup_stage: SetupStage = Stage.LAUNCH
	stage = Stage.LAUNCH
	overall_result = OverallResult.LAUNCH_FAILED
	candidate_ok = False
	browser: Browser | None = None
	try:
		with anyio.fail_after(LAUNCH_TIMEOUT_SECONDS):
			browser = await launch_async(headless=False, humanize=True, env=_browser_env(env))
		setup_stage = Stage.CONTEXT
		stage = Stage.CONTEXT
		with anyio.fail_after(SETUP_TIMEOUT_SECONDS):
			context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
		setup_stage = Stage.PAGE
		stage = Stage.PAGE
		with anyio.fail_after(SETUP_TIMEOUT_SECONDS):
			page = await context.new_page()
		setup_stage = Stage.PREPARE
		stage = Stage.PREPARE
		with anyio.fail_after(SETUP_TIMEOUT_SECONDS):
			await prepare_browser_page(page)
	except (TimeoutError, PlaywrightTimeoutError):
		overall_result = _setup_failure(setup_stage, timed_out=True)
	except Exception:
		overall_result = _setup_failure(setup_stage, timed_out=False)
	else:
		stage = Stage.ROOT_NAVIGATION
		root_navigation = await _navigate(page, base_url)
		stage = Stage.LOGIN_NAVIGATION
		login_navigation = await _navigate(page, f'{base_url}/login')
		overall_result, login_reached = _login_result(login_navigation)
		if login_reached:
			stage = Stage.LOGIN_SHELL
			login_shell = await _wait_for_login_shell(page)
			overall_result, candidate_ok = _shell_result(login_shell)

	if browser is not None:
		close_status = await _close_browser(browser)
		match close_status:
			case CloseStatus.CLOSED:
				if candidate_ok:
					stage = Stage.COMPLETE
			case CloseStatus.TIMEOUT:
				if candidate_ok:
					stage = Stage.CLOSE
					overall_result = OverallResult.CLOSE_TIMEOUT
				candidate_ok = False
			case CloseStatus.FAILED:
				if candidate_ok:
					stage = Stage.CLOSE
					overall_result = OverallResult.CLOSE_FAILED
				candidate_ok = False
			case CloseStatus.NOT_STARTED:
				candidate_ok = False
	return DiagnosticResult(
		root_navigation=root_navigation,
		login_navigation=login_navigation,
		login_shell=login_shell,
		stage=stage,
		close_status=close_status,
		overall_result=overall_result,
		ok=candidate_ok,
	)
