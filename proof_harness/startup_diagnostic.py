from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

import anyio
from cloakbrowser import launch_async
from playwright.async_api import Browser
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

DIAGNOSTIC_TIMEOUT_SECONDS: Final = 15.0
_BINARY_ENV: Final = 'CLOAKBROWSER_BINARY_PATH'
_PROFILE_ENV_NAMES: Final = (
	'HOME',
	'XDG_CONFIG_HOME',
	'XDG_CACHE_HOME',
	'XDG_RUNTIME_DIR',
)
_BROWSER_ENV_NAMES: Final = (
	'DISPLAY',
	'HOME',
	'LANG',
	'LC_ALL',
	'PATH',
	'TMPDIR',
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
	NAVIGATION = 'navigation'
	CLOSE = 'close'
	COMPLETE = 'complete'


class Category(StrEnum):
	BINARY_PATH_UNAVAILABLE = 'binary_path_unavailable'
	HOME_UNWRITABLE = 'home_unwritable'
	DISPLAY_UNAVAILABLE = 'display_unavailable'
	LAUNCH_TIMEOUT = 'launch_timeout'
	LAUNCH_FAILED = 'launch_failed'
	CONTEXT_TIMEOUT = 'context_timeout'
	CONTEXT_FAILED = 'context_failed'
	PAGE_TIMEOUT = 'page_timeout'
	PAGE_FAILED = 'page_failed'
	NAVIGATION_TIMEOUT = 'navigation_timeout'
	NAVIGATION_FAILED = 'navigation_failed'
	CLOSE_TIMEOUT = 'close_timeout'
	CLOSE_FAILED = 'close_failed'
	READY = 'ready'


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
	category: Category
	stage: Stage
	ok: bool

	def to_json(self) -> str:
		return json.dumps(
			{
				'category': self.category.value,
				'event': 'cloakbrowser_startup_smoke',
				'ok': self.ok,
				'stage': self.stage.value,
			},
			separators=(',', ':'),
			sort_keys=True,
		)


def _result(category: Category, stage: Stage, ok: bool = False) -> DiagnosticResult:
	return DiagnosticResult(category=category, stage=stage, ok=ok)


def _binary_path_is_ready(env: Mapping[str, str]) -> bool:
	value = env.get(_BINARY_ENV)
	if not value:
		return False
	try:
		path = Path(value)
		return path.is_absolute() and path.is_file() and os.access(path, os.X_OK)
	except (OSError, ValueError):
		return False


def _profile_is_writable(env: Mapping[str, str]) -> bool:
	home_value = env.get('HOME')
	if not home_value:
		return False
	paths = [home_value]
	paths.extend(value for name in _PROFILE_ENV_NAMES[1:] if (value := env.get(name)))
	try:
		for value in paths:
			path = Path(value)
			if not path.is_absolute():
				return False
			path.mkdir(parents=True, exist_ok=True)
			with TemporaryDirectory(dir=path):
				pass
	except (OSError, ValueError):
		return False
	return True


def run_preflight(env: Mapping[str, str]) -> DiagnosticResult:
	if not _binary_path_is_ready(env):
		return _result(Category.BINARY_PATH_UNAVAILABLE, Stage.PATH)
	if not _profile_is_writable(env):
		return _result(Category.HOME_UNWRITABLE, Stage.HOME)
	if not env.get('DISPLAY'):
		return _result(Category.DISPLAY_UNAVAILABLE, Stage.DISPLAY)
	return _result(Category.READY, Stage.LAUNCH, ok=True)


def _browser_env(env: Mapping[str, str]) -> dict[str, str]:
	return {name: env[name] for name in _BROWSER_ENV_NAMES if name in env}


def _stage_failure(stage: Stage, timed_out: bool) -> DiagnosticResult:
	match stage:
		case Stage.PATH:
			return _result(Category.BINARY_PATH_UNAVAILABLE, stage)
		case Stage.HOME:
			return _result(Category.HOME_UNWRITABLE, stage)
		case Stage.DISPLAY:
			return _result(Category.DISPLAY_UNAVAILABLE, stage)
		case Stage.LAUNCH:
			category = Category.LAUNCH_TIMEOUT if timed_out else Category.LAUNCH_FAILED
		case Stage.CONTEXT:
			category = Category.CONTEXT_TIMEOUT if timed_out else Category.CONTEXT_FAILED
		case Stage.PAGE:
			category = Category.PAGE_TIMEOUT if timed_out else Category.PAGE_FAILED
		case Stage.NAVIGATION:
			category = Category.NAVIGATION_TIMEOUT if timed_out else Category.NAVIGATION_FAILED
		case Stage.CLOSE:
			category = Category.CLOSE_TIMEOUT if timed_out else Category.CLOSE_FAILED
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
	preflight = run_preflight(env)
	if not preflight.ok:
		return preflight

	stage = Stage.LAUNCH
	browser: Browser | None = None
	result = _result(Category.READY, Stage.COMPLETE, ok=True)
	try:
		with anyio.fail_after(DIAGNOSTIC_TIMEOUT_SECONDS):
			browser = await launch_async(headless=False, humanize=False, env=_browser_env(env))
		stage = Stage.CONTEXT
		with anyio.fail_after(DIAGNOSTIC_TIMEOUT_SECONDS):
			context = await browser.new_context()
		stage = Stage.PAGE
		with anyio.fail_after(DIAGNOSTIC_TIMEOUT_SECONDS):
			page = await context.new_page()
		stage = Stage.NAVIGATION
		with anyio.fail_after(DIAGNOSTIC_TIMEOUT_SECONDS):
			_ = await page.goto(
				'about:blank',
				wait_until='load',
				timeout=int(DIAGNOSTIC_TIMEOUT_SECONDS * 1000),
			)
	except (TimeoutError, PlaywrightTimeoutError):
		result = _stage_failure(stage, timed_out=True)
	except Exception:  # noqa: BLE001, BROAD_EXCEPT_OK
		result = _stage_failure(stage, timed_out=False)

	if browser is not None:
		close_result = await _close_browser(browser)
		if result.ok:
			result = close_result
	return result
