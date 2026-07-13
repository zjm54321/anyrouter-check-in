from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Final

PROGRESS_EVENT: Final = 'proof_progress'
_PROGRESS_OUTPUT: Final = sys.stdout


class Stage(str, Enum):
	CONFIG = 'config'
	BROWSER_LOGIN = 'browser_login'
	EGRESS = 'egress'
	PRE_READ = 'pre_read'
	SIGN_IN = 'sign_in'
	POST_READ = 'post_read'
	COMPLETE = 'complete'


class ProgressStage(str, Enum):
	BROWSER_LAUNCH = 'browser_launch'
	LOGIN_NAVIGATION = 'login_navigation'
	FORM_SUBMISSION = 'form_submission'
	LOGIN_VERIFICATION = 'login_verification'
	BROWSER_EGRESS = 'browser_egress'
	BROWSER_CLOSE_START = 'browser_close_start'
	BROWSER_CLOSE_END = 'browser_close_end'
	HTTP_EGRESS = 'http_egress'
	PRE_READ = 'pre_read'
	SIGN_IN = 'sign_in'
	POST_READ = 'post_read'
	COMPLETE = 'complete'


def emit_progress(enabled: bool, stage: ProgressStage) -> None:
	if not enabled:
		return
	record = json.dumps(
		{'event': PROGRESS_EVENT, 'stage': stage.value},
		separators=(',', ':'),
		sort_keys=True,
	)
	print(record, file=_PROGRESS_OUTPUT, flush=True)


@dataclass(frozen=True, slots=True)
class Cookie:
	name: str
	value: str
	domain: str
	path: str


@dataclass(frozen=True, slots=True)
class BrowserSession:
	cookies: tuple[Cookie, ...]
	api_user: str
	user_agent: str
	egress_identity: str | None


@dataclass(frozen=True, slots=True)
class HttpObservation:
	stage: Stage
	status: int
	content_type: str
	http_version: str
	body_sha256: str


@dataclass(frozen=True, slots=True)
class ProofResult:
	ok: bool
	stage: Stage
	category: str
	cookie_names: tuple[str, ...] = ()
	browser_egress_sha256: str | None = None
	http_egress_sha256: str | None = None
	http: tuple[HttpObservation, ...] = ()

	def model_dump_json(self) -> str:
		return json.dumps(asdict(self), separators=(',', ':'), sort_keys=True)
