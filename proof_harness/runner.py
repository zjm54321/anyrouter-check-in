from __future__ import annotations

import hashlib
from typing import Protocol

import httpx

from proof_harness.config import ProofConfig, ProxyMode
from proof_harness.json_types import parse_json, read_egress_identity
from proof_harness.models import BrowserSession, HttpObservation, ProgressStage, ProofResult, Stage, emit_progress

ALLOWED_COOKIE_NAMES = frozenset({'session', 'acw_tc', 'cdn_sec_tc', 'acw_sc__v2'})
ALREADY_SIGNED_KEYWORDS = ('已经签到', '已签到', '重复签到', 'already checked', 'already signed')


class BrowserBoundary(Protocol):
	def login(self, config: ProofConfig) -> BrowserSession: ...


def _hash(value: bytes) -> str:
	return hashlib.sha256(value).hexdigest()


def _salted_hash(salt: str, value: str | None) -> str | None:
	return _hash(f'{salt}\0{value}'.encode()) if value is not None else None


def _observe(stage: Stage, response: httpx.Response) -> HttpObservation:
	return HttpObservation(
		stage=stage,
		status=response.status_code,
		content_type=(response.headers['content-type'] if 'content-type' in response.headers else '')
		.split(';', maxsplit=1)[0]
		.lower(),
		http_version=response.http_version,
		body_sha256=_hash(response.content),
	)


def _verified_user_self(response: httpx.Response, expected_user: str) -> bool:
	if response.status_code != 200:
		return False
	try:
		payload = parse_json(response.content)
	except ValueError:
		return False
	if not isinstance(payload, dict):
		return False
	data = payload.get('data') if payload.get('success') is True else payload
	return isinstance(data, dict) and str(data.get('id', '')) == expected_user


def _sign_in_category(response: httpx.Response) -> str:
	if response.status_code != 200:
		return 'sign_in_http_status'
	try:
		payload = parse_json(response.content)
	except ValueError:
		return 'sign_in_non_json'
	if not isinstance(payload, dict):
		return 'sign_in_rejected'
	if payload.get('ret') == 1 or payload.get('code') == 0 or payload.get('success') is True:
		return 'sign_in_complete'
	message = payload.get('msg', payload.get('message'))
	if isinstance(message, str) and any(keyword in message.lower() for keyword in ALREADY_SIGNED_KEYWORDS):
		return 'already_signed'
	return 'sign_in_rejected'


def _failure(
	stage: Stage,
	category: str,
	session: BrowserSession,
	config: ProofConfig,
	observations: list[HttpObservation],
	http_egress: str | None = None,
) -> ProofResult:
	return ProofResult(
		ok=False,
		stage=stage,
		category=category,
		cookie_names=tuple(sorted(cookie.name for cookie in session.cookies if cookie.name in ALLOWED_COOKIE_NAMES)),
		browser_egress_sha256=_salted_hash(config.egress_salt, session.egress_identity),
		http_egress_sha256=_salted_hash(config.egress_salt, http_egress),
		http=tuple(observations),
	)


def run_proof(
	config: ProofConfig,
	browser: BrowserBoundary,
	*,
	transport: httpx.BaseTransport | None = None,
) -> ProofResult:
	session = browser.login(config)
	observations: list[HttpObservation] = []
	if session.egress_identity is None or not session.egress_identity.strip():
		return _failure(Stage.EGRESS, 'browser_egress_required', session, config, observations)
	headers = {
		'User-Agent': session.user_agent,
		'Accept': 'application/json, text/plain, */*',
		'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
		'Accept-Encoding': 'gzip, deflate, br, zstd',
		'Referer': config.base_url,
		'Origin': config.base_url,
		'Connection': 'keep-alive',
		'Sec-Fetch-Dest': 'empty',
		'Sec-Fetch-Mode': 'cors',
		'Sec-Fetch-Site': 'same-origin',
		'new-api-user': session.api_user,
	}
	proxy = config.proxy_url if config.proxy_mode is ProxyMode.MIHOMO else None
	with httpx.Client(
		http2=True,
		timeout=config.timeout_seconds,
		trust_env=False,
		transport=transport,
		proxy=proxy,
	) as client:
		for cookie in session.cookies:
			client.cookies.set(cookie.name, cookie.value, domain=cookie.domain, path=cookie.path)
		emit_progress(config.progress_enabled, ProgressStage.HTTP_EGRESS)
		egress_response = client.get(config.egress_url, headers=headers)
		observations.append(_observe(Stage.EGRESS, egress_response))
		if egress_response.http_version != 'HTTP/2':
			return _failure(Stage.EGRESS, 'http_protocol_required', session, config, observations)
		try:
			egress_payload = parse_json(egress_response.content)
		except ValueError:
			return _failure(Stage.EGRESS, 'egress_non_json', session, config, observations)
		http_egress = read_egress_identity(egress_payload)
		if http_egress is None:
			return _failure(Stage.EGRESS, 'http_egress_required', session, config, observations)
		if session.egress_identity != http_egress:
			return _failure(Stage.EGRESS, 'egress_mismatch', session, config, observations, http_egress)
		user_url = f'{config.base_url}/api/user/self'
		emit_progress(config.progress_enabled, ProgressStage.PRE_READ)
		pre = client.get(user_url, headers=headers)
		observations.append(_observe(Stage.PRE_READ, pre))
		if pre.http_version != 'HTTP/2':
			return _failure(Stage.PRE_READ, 'http_protocol_required', session, config, observations, http_egress)
		if not _verified_user_self(pre, session.api_user):
			category = 'pre_read_non_json' if observations[-1].content_type != 'application/json' else 'pre_read_unverified'
			return _failure(Stage.PRE_READ, category, session, config, observations, http_egress)
		sign_headers = {**headers, 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}
		emit_progress(config.progress_enabled, ProgressStage.SIGN_IN)
		sign_in = client.post(f'{config.base_url}/api/user/sign_in', headers=sign_headers)
		observations.append(_observe(Stage.SIGN_IN, sign_in))
		if sign_in.http_version != 'HTTP/2':
			return _failure(Stage.SIGN_IN, 'http_protocol_required', session, config, observations, http_egress)
		sign_in_category = _sign_in_category(sign_in)
		if sign_in_category not in {'sign_in_complete', 'already_signed'}:
			return _failure(Stage.SIGN_IN, sign_in_category, session, config, observations, http_egress)
		emit_progress(config.progress_enabled, ProgressStage.POST_READ)
		post = client.get(user_url, headers=headers)
		observations.append(_observe(Stage.POST_READ, post))
		if post.http_version != 'HTTP/2':
			return _failure(Stage.POST_READ, 'http_protocol_required', session, config, observations, http_egress)
		if not _verified_user_self(post, session.api_user):
			return _failure(Stage.POST_READ, 'post_read_unverified', session, config, observations, http_egress)
	emit_progress(config.progress_enabled, ProgressStage.COMPLETE)
	return ProofResult(
		ok=True,
		stage=Stage.COMPLETE,
		category='already_signed' if sign_in_category == 'already_signed' else 'complete',
		cookie_names=tuple(sorted(cookie.name for cookie in session.cookies if cookie.name in ALLOWED_COOKIE_NAMES)),
		browser_egress_sha256=_salted_hash(config.egress_salt, session.egress_identity),
		http_egress_sha256=_salted_hash(config.egress_salt, http_egress),
		http=tuple(observations),
	)
