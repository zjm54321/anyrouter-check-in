from __future__ import annotations

import io
import json
from collections.abc import Mapping
from contextlib import redirect_stdout
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import anyio
from cloakbrowser import launch_async
from playwright.async_api import Browser
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from proof_harness.startup_diagnostic import run_preflight
from utils.browser import prepare_browser_page

DIAGNOSTIC_TIMEOUT_SECONDS: Final = 20.0
_PROXY_NAMES: Final = frozenset({'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'})
_DEFAULT_FINGERPRINT_SEED: Final = 42424
_ALLOWLIST_ENV_NAMES: Final = (
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


class Stage(StrEnum):
	PATH = 'path'
	HOME = 'home'
	DISPLAY = 'display'
	LAUNCH = 'launch'
	CONTEXT = 'context'
	PAGE = 'page'
	PREPARE = 'prepare'
	CLOSE = 'close'
	COMPLETE = 'complete'


class Category(StrEnum):
	CONFIG_INVALID = 'config_invalid'
	BINARY_PATH_UNAVAILABLE = 'binary_path_unavailable'
	HOME_UNWRITABLE = 'home_unwritable'
	DISPLAY_UNAVAILABLE = 'display_unavailable'
	LAUNCH_TIMEOUT = 'launch_timeout'
	LAUNCH_FAILED = 'launch_failed'
	CONTEXT_TIMEOUT = 'context_timeout'
	CONTEXT_FAILED = 'context_failed'
	PAGE_TIMEOUT = 'page_timeout'
	PAGE_FAILED = 'page_failed'
	PREPARE_TIMEOUT = 'prepare_timeout'
	PREPARE_FAILED = 'prepare_failed'
	CLOSE_TIMEOUT = 'close_timeout'
	CLOSE_FAILED = 'close_failed'
	READY = 'ready'


class EnvironmentMode(StrEnum):
	FULL = 'full'
	ALLOWLIST = 'allowlist'


class FingerprintMode(StrEnum):
	FIXED = 'fixed'
	DEFAULT = 'default'


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
	category: Category
	stage: Stage
	ok: bool

	def to_json(self) -> str:
		return json.dumps(
			{
				'category': self.category.value,
				'event': 'cloakbrowser_proof_launch_smoke',
				'ok': self.ok,
				'stage': self.stage.value,
			},
			separators=(',', ':'),
			sort_keys=True,
		)


def _result(category: Category, stage: Stage, ok: bool = False) -> DiagnosticResult:
	return DiagnosticResult(category=category, stage=stage, ok=ok)


def _humanize_enabled(env: Mapping[str, str]) -> bool | None:
	value = env.get('PROOF_HUMANIZE', 'true')
	if value == 'true':
		return True
	if value == 'false':
		return False
	return None


def _environment_mode(env: Mapping[str, str]) -> EnvironmentMode | None:
	try:
		return EnvironmentMode(env.get('PROOF_ENV_MODE', 'full'))
	except ValueError:
		return None


def _fingerprint_mode(env: Mapping[str, str]) -> FingerprintMode | None:
	try:
		return FingerprintMode(env.get('PROOF_FINGERPRINT_MODE', 'fixed'))
	except ValueError:
		return None


def _fingerprint_seed(env: Mapping[str, str]) -> int | None:
	raw_seed = env.get('PROOF_FINGERPRINT_SEED', str(_DEFAULT_FINGERPRINT_SEED))
	try:
		seed = int(raw_seed)
	except ValueError:
		return None
	if 10000 <= seed <= 99999:
		return seed
	return None


def _fingerprint_args(
	mode: FingerprintMode,
	seed: int,
) -> tuple[str, ...] | None:
	match mode:
		case FingerprintMode.FIXED:
			return (f'--fingerprint={seed}',)
		case FingerprintMode.DEFAULT:
			return None


def _browser_env(env: Mapping[str, str], mode: EnvironmentMode) -> dict[str, str]:
	match mode:
		case EnvironmentMode.FULL:
			return {key: value for key, value in env.items() if key.lower() not in _PROXY_NAMES}
		case EnvironmentMode.ALLOWLIST:
			return {name: env[name] for name in _ALLOWLIST_ENV_NAMES if name in env}


def _preflight_result(env: Mapping[str, str]) -> DiagnosticResult | None:
	preflight = run_preflight(env)
	if preflight.ok:
		return None
	return DiagnosticResult(
		category=Category(preflight.category.value),
		stage=Stage(preflight.stage.value),
		ok=False,
	)


def _stage_failure(stage: Stage, timed_out: bool) -> DiagnosticResult:
	match stage:
		case Stage.LAUNCH:
			category = Category.LAUNCH_TIMEOUT if timed_out else Category.LAUNCH_FAILED
		case Stage.CONTEXT:
			category = Category.CONTEXT_TIMEOUT if timed_out else Category.CONTEXT_FAILED
		case Stage.PAGE:
			category = Category.PAGE_TIMEOUT if timed_out else Category.PAGE_FAILED
		case Stage.PREPARE:
			category = Category.PREPARE_TIMEOUT if timed_out else Category.PREPARE_FAILED
		case Stage.CLOSE:
			category = Category.CLOSE_TIMEOUT if timed_out else Category.CLOSE_FAILED
		case Stage.PATH:
			category = Category.BINARY_PATH_UNAVAILABLE
		case Stage.HOME:
			category = Category.HOME_UNWRITABLE
		case Stage.DISPLAY:
			category = Category.DISPLAY_UNAVAILABLE
		case Stage.COMPLETE:
			return _result(Category.READY, stage, ok=True)
	return _result(category, stage)


async def _close_browser(browser: Browser) -> DiagnosticResult:
	try:
		with anyio.fail_after(DIAGNOSTIC_TIMEOUT_SECONDS):
			await browser.close()
	except (TimeoutError, PlaywrightTimeoutError):
		return _stage_failure(Stage.CLOSE, timed_out=True)
	except Exception:  # noqa: BLE001, BROAD_EXCEPT_OK
		return _stage_failure(Stage.CLOSE, timed_out=False)
	return _result(Category.READY, Stage.COMPLETE, ok=True)


async def run_diagnostic(env: Mapping[str, str]) -> DiagnosticResult:
	preflight = _preflight_result(env)
	if preflight is not None:
		return preflight
	humanize = _humanize_enabled(env)
	environment_mode = _environment_mode(env)
	fingerprint_mode = _fingerprint_mode(env)
	fingerprint_seed = _fingerprint_seed(env)
	if (
		humanize is None
		or environment_mode is None
		or fingerprint_mode is None
		or fingerprint_seed is None
	):
		return _result(Category.CONFIG_INVALID, Stage.LAUNCH)
	fingerprint_args = _fingerprint_args(fingerprint_mode, fingerprint_seed)

	stage = Stage.LAUNCH
	browser: Browser | None = None
	result = _result(Category.READY, Stage.COMPLETE, ok=True)
	try:
		with anyio.fail_after(DIAGNOSTIC_TIMEOUT_SECONDS):
			launched_browser = await launch_async(
				args=fingerprint_args,
				headless=False,
				humanize=humanize,
				env=_browser_env(env, environment_mode),
			)
			browser = launched_browser
		stage = Stage.CONTEXT
		with anyio.fail_after(DIAGNOSTIC_TIMEOUT_SECONDS):
			context = await launched_browser.new_context(viewport={'width': 1920, 'height': 1080})
		stage = Stage.PAGE
		with anyio.fail_after(DIAGNOSTIC_TIMEOUT_SECONDS):
			page = await context.new_page()
		stage = Stage.PREPARE
		with anyio.fail_after(DIAGNOSTIC_TIMEOUT_SECONDS):
			with redirect_stdout(io.StringIO()):
				await prepare_browser_page(page)
	except (TimeoutError, PlaywrightTimeoutError):
		result = _stage_failure(stage, timed_out=True)
	except Exception:  # noqa: BLE001, BROAD_EXCEPT_OK
		result = _stage_failure(stage, timed_out=False)

	if browser is not None:
		close_result = await _close_browser(browser)
		if result.ok:
			result = close_result
	return result
