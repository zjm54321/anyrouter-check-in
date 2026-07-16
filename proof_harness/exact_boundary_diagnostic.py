from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from enum import StrEnum
from typing import final
from unittest.mock import patch

from playwright.async_api import Page

import proof_harness.browser as browser_module
from proof_harness.config import ProofAccount, ProofConfig, ProxyMode
from proof_harness.models import ProgressStage


class Stage(StrEnum):
	BOUNDARY = 'boundary'
	PRE_NAVIGATION = 'pre_navigation'
	BROWSER_CLOSE = 'browser_close'


class Category(StrEnum):
	PRE_NAVIGATION = 'pre_navigation'
	BOUNDARY_FAILURE = 'boundary_failure'
	CLOSE_FAILURE = 'close_failure'


@dataclass(frozen=True, slots=True)
class ExactBoundaryResult:
	category: Category
	stage: Stage
	ok: bool
	closed: bool

	def to_json(self) -> str:
		return json.dumps(
			{
				'category': self.category.value,
				'closed': self.closed,
				'event': 'cloakbrowser_exact_boundary_smoke',
				'ok': self.ok,
				'stage': self.stage.value,
			},
			separators=(',', ':'),
			sort_keys=True,
		)


class PreNavigationSentinel(Exception):
	pass


@final
class BoundaryCapture:
	__slots__ = ('sentinel_reached', 'stages')

	def __init__(self) -> None:
		self.sentinel_reached = False
		self.stages: list[ProgressStage] = []

	def record_progress(self, enabled: bool, stage: ProgressStage) -> None:
		if enabled:
			self.stages.append(stage)

	async def stop_before_navigation(self, _page: Page, _login_url: str, _timeout_ms: int) -> None:
		self.sentinel_reached = True
		raise PreNavigationSentinel


def _fixed_config() -> ProofConfig:
	return ProofConfig(
		account=ProofAccount(email='placeholder', password='placeholder'),
		base_url='unused',
		egress_url='unused',
		egress_salt='placeholder',
		proxy_mode=ProxyMode.DIRECT,
		proxy_url=None,
		progress_enabled=True,
	)


def _failure_result(capture: BoundaryCapture) -> ExactBoundaryResult:
	close_started = ProgressStage.BROWSER_CLOSE_START in capture.stages
	close_completed = ProgressStage.BROWSER_CLOSE_END in capture.stages
	if close_started and not close_completed:
		return ExactBoundaryResult(Category.CLOSE_FAILURE, Stage.BROWSER_CLOSE, False, False)
	return ExactBoundaryResult(Category.BOUNDARY_FAILURE, Stage.BOUNDARY, False, close_completed)


def run_exact_boundary_smoke() -> ExactBoundaryResult:
	capture = BoundaryCapture()
	try:
		with (
			redirect_stdout(io.StringIO()),
			redirect_stderr(io.StringIO()),
			patch.object(browser_module, 'navigate_login_page', capture.stop_before_navigation),
			patch.object(browser_module, 'emit_progress', capture.record_progress),
		):
			_ = browser_module.CloakBrowserBoundary().login(_fixed_config())
	except PreNavigationSentinel:
		close_completed = ProgressStage.BROWSER_CLOSE_END in capture.stages
		if capture.sentinel_reached and close_completed:
			return ExactBoundaryResult(Category.PRE_NAVIGATION, Stage.PRE_NAVIGATION, True, True)
		return _failure_result(capture)
	except Exception:  # noqa: BLE001, BROAD_EXCEPT_OK
		return _failure_result(capture)
	return _failure_result(capture)
