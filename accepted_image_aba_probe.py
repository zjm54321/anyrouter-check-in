from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, final
from unittest.mock import patch

from playwright.async_api import Page

import proof_harness.browser as browser_module
from proof_harness.browser import CloakBrowserBoundary
from proof_harness.config import ProofAccount, ProofConfig, ProxyMode
from proof_harness.models import ProgressStage

_EVENT: Final = 'accepted_image_browser_boundary_probe'
_NAVIGATION_SENTINEL: Final = 'navigation-sentinel'
_BLANK_URL: Final = 'about:blank'


class Stage(StrEnum):
	BROWSER_LAUNCH = 'browser_launch'
	BOUNDARY = 'boundary'
	PRE_NAVIGATION = 'pre_navigation'
	BROWSER_CLOSE = 'browser_close'


class Category(StrEnum):
	BROWSER_LAUNCH_FAILURE = 'browser_launch_failure'
	BOUNDARY_FAILURE = 'boundary_failure'
	PRE_NAVIGATION = 'pre_navigation'
	CLOSE_FAILURE = 'close_failure'


@dataclass(frozen=True, slots=True)
class ProbeResult:
	category: Category
	stage: Stage
	ok: bool
	closed: bool

	def to_json(self) -> str:
		return json.dumps(
			{
				'category': self.category.value,
				'closed': self.closed,
				'event': _EVENT,
				'ok': self.ok,
				'stage': self.stage.value,
			},
			separators=(',', ':'),
			sort_keys=True,
		)


class _PreNavigationSentinel(Exception):
	pass


@final
class _BoundaryCapture:
	__slots__ = ('sentinel_reached', 'stages')

	def __init__(self) -> None:
		self.sentinel_reached = False
		self.stages: list[ProgressStage] = []

	def record_progress(self, enabled: bool, stage: ProgressStage) -> None:
		if enabled:
			self.stages.append(stage)

	async def stop_before_navigation(self, _page: Page, _login_url: str, _timeout_ms: int) -> None:
		self.sentinel_reached = True
		raise _PreNavigationSentinel


def _fixed_config() -> ProofConfig:
	return ProofConfig(
		account=ProofAccount(email=_NAVIGATION_SENTINEL, password=_NAVIGATION_SENTINEL),
		base_url=_BLANK_URL,
		egress_url=_BLANK_URL,
		egress_salt=_NAVIGATION_SENTINEL,
		proxy_mode=ProxyMode.DIRECT,
		proxy_url=None,
		progress_enabled=True,
	)


def _failure_result(capture: _BoundaryCapture) -> ProbeResult:
	close_started = ProgressStage.BROWSER_CLOSE_START in capture.stages
	close_completed = ProgressStage.BROWSER_CLOSE_END in capture.stages
	if close_started and not close_completed:
		return ProbeResult(Category.CLOSE_FAILURE, Stage.BROWSER_CLOSE, False, False)
	if capture.stages == [ProgressStage.BROWSER_LAUNCH]:
		return ProbeResult(Category.BROWSER_LAUNCH_FAILURE, Stage.BROWSER_LAUNCH, False, False)
	return ProbeResult(Category.BOUNDARY_FAILURE, Stage.BOUNDARY, False, close_completed)


def run_probe() -> ProbeResult:
	capture = _BoundaryCapture()
	try:
		with (
			redirect_stdout(io.StringIO()),
			redirect_stderr(io.StringIO()),
			patch.object(browser_module, 'navigate_login_page', capture.stop_before_navigation),
			patch.object(browser_module, 'emit_progress', capture.record_progress),
		):
			_ = CloakBrowserBoundary().login(_fixed_config())
	except _PreNavigationSentinel:
		close_completed = ProgressStage.BROWSER_CLOSE_END in capture.stages
		if capture.sentinel_reached and close_completed:
			return ProbeResult(Category.PRE_NAVIGATION, Stage.PRE_NAVIGATION, True, True)
		return _failure_result(capture)
	except Exception:  # noqa: BLE001, BROAD_EXCEPT_OK
		return _failure_result(capture)
	return _failure_result(capture)


def main() -> int:
	try:
		with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
			result = run_probe()
	except Exception:  # noqa: BLE001, BROAD_EXCEPT_OK
		result = ProbeResult(Category.BOUNDARY_FAILURE, Stage.BOUNDARY, False, False)
	_ = sys.stdout.write(f'{result.to_json()}\n')
	return 0 if result.ok else 1


if __name__ == '__main__':
	raise SystemExit(main())
