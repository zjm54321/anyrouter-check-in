from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum


class Stage(str, Enum):
	CONFIG = 'config'
	BROWSER_LOGIN = 'browser_login'
	EGRESS = 'egress'
	PRE_READ = 'pre_read'
	SIGN_IN = 'sign_in'
	POST_READ = 'post_read'
	COMPLETE = 'complete'


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
