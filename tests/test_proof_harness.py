import json
from dataclasses import dataclass

import httpx
import pytest

from proof_harness.config import ConfigFailure, ProofConfig, parse_proof_config
from proof_harness.models import BrowserSession, Cookie, Stage
from proof_harness.runner import run_proof

FORBIDDEN = (
	'user@example.test',
	'super-secret-password',
	'session-secret',
	'raw-browser-agent',
	'http://proxy-user:proxy-pass@proxy.test:7890',
	'account-label',
)


@dataclass
class FakeBrowser:
	session: BrowserSession
	calls: int = 0

	def login(self, config: ProofConfig) -> BrowserSession:
		_ = config
		self.calls += 1
		return self.session


def valid_env() -> dict[str, str]:
	return {
		'PROOF_MODE': 'true',
		'ANYROUTER_ACCOUNTS': json.dumps(
			[
				{
					'name': 'account-label',
					'email': 'user@example.test',
					'password': 'super-secret-password',
				}
			]
		),
		'PROOF_BASE_URL': 'https://proof.invalid',
		'PROOF_EGRESS_URL': 'https://egress.invalid/identity',
		'PROOF_EGRESS_SALT': 'test-salt',
		'PROOF_PROXY_MODE': 'direct',
	}


def browser_session(*, egress_identity: str = '198.51.100.10') -> BrowserSession:
	return BrowserSession(
		cookies=(
			Cookie(name='session', value='session-secret', domain='proof.invalid', path='/'),
			Cookie(name='acw_tc', value='waf-secret', domain='proof.invalid', path='/'),
			Cookie(name='forbidden-cookie', value='never-output', domain='proof.invalid', path='/'),
		),
		api_user='12345',
		user_agent='raw-browser-agent',
		egress_identity=egress_identity,
	)


def test_parse_config_fails_closed_without_proof_mode() -> None:
	# Given
	env = valid_env()
	del env['PROOF_MODE']

	# When
	result = parse_proof_config(env)

	# Then
	assert result == ConfigFailure(stage=Stage.CONFIG, category='proof_mode_required')


def test_parse_config_requires_exactly_one_account() -> None:
	# Given
	empty_env = valid_env()
	empty_env['ANYROUTER_ACCOUNTS'] = '[]'
	multiple_env = valid_env()
	multiple_env['ANYROUTER_ACCOUNTS'] = '[{},{}]'

	# When
	empty_result = parse_proof_config(empty_env)
	multiple_result = parse_proof_config(multiple_env)

	# Then
	expected = ConfigFailure(stage=Stage.CONFIG, category='single_account_required')
	assert empty_result == expected
	assert multiple_result == expected


def test_parse_config_requires_proxy_for_mihomo() -> None:
	# Given
	env = valid_env()
	env['PROOF_PROXY_MODE'] = 'mihomo'

	# When
	result = parse_proof_config(env)

	# Then
	assert result == ConfigFailure(stage=Stage.CONFIG, category='proxy_required')


def test_runner_emits_one_sanitized_result_for_reference_flow() -> None:
	# Given
	config = parse_proof_config(valid_env())
	assert isinstance(config, ProofConfig)
	requests: list[httpx.Request] = []

	def handler(request: httpx.Request) -> httpx.Response:
		requests.append(request)
		if request.url.path == '/proof/egress':
			return httpx.Response(200, json={'identity': '198.51.100.10'}, extensions={'http_version': b'HTTP/2'})
		if request.url.path == '/identity':
			return httpx.Response(200, json={'ip': '198.51.100.10'}, extensions={'http_version': b'HTTP/2'})
		if request.url.path == '/api/user/self':
			return httpx.Response(
				200,
				json={'success': True, 'data': {'id': 12345, 'quota': 100, 'used_quota': 20}},
				extensions={'http_version': b'HTTP/2'},
			)
		assert request.url.path == '/api/user/sign_in'
		assert request.content == b''
		assert request.headers['new-api-user'] == '12345'
		assert request.headers['user-agent'] == 'raw-browser-agent'
		assert request.headers['content-type'] == 'application/json'
		assert request.headers['x-requested-with'] == 'XMLHttpRequest'
		return httpx.Response(200, json={'success': True}, extensions={'http_version': b'HTTP/2'})

	# When
	result = run_proof(
		config,
		FakeBrowser(browser_session()),
		transport=httpx.MockTransport(handler),
	)
	serialized = result.model_dump_json()

	# Then
	assert result.ok is True
	assert [request.url.path for request in requests] == [
		'/identity',
		'/api/user/self',
		'/api/user/sign_in',
		'/api/user/self',
	]
	assert result.cookie_names == ('acw_tc', 'session')
	assert serialized.count('body_sha256') == 4
	assert all(value not in serialized for value in FORBIDDEN)


@pytest.mark.parametrize(
	'browser_identity,http_identity,category',
	[
		('198.51.100.10', '198.51.100.11', 'egress_mismatch'),
		('198.51.100.10', '198.51.100.10', 'http_protocol_required'),
	],
)
def test_runner_sends_no_sign_in_after_precondition_failure(
	browser_identity: str,
	http_identity: str,
	category: str,
) -> None:
	# Given
	config = parse_proof_config(valid_env())
	assert isinstance(config, ProofConfig)
	requests: list[httpx.Request] = []

	def handler(request: httpx.Request) -> httpx.Response:
		requests.append(request)
		version = b'HTTP/1.1' if category == 'http_protocol_required' and request.url.path == '/api/user/self' else b'HTTP/2'
		if request.url.path == '/identity':
			return httpx.Response(200, json={'identity': http_identity}, extensions={'http_version': version})
		return httpx.Response(
			200,
			json={'success': True, 'data': {'id': 12345}},
			extensions={'http_version': version},
		)

	# When
	result = run_proof(
		config,
		FakeBrowser(browser_session(egress_identity=browser_identity)),
		transport=httpx.MockTransport(handler),
	)
	serialized = result.model_dump_json()

	# Then
	assert result.ok is False
	assert result.category == category
	assert all(request.url.path != '/api/user/sign_in' for request in requests)
	assert all(value not in serialized for value in FORBIDDEN)


def test_runner_rejects_non_json_pre_read_without_sign_in() -> None:
	# Given
	config = parse_proof_config(valid_env())
	assert isinstance(config, ProofConfig)
	requests: list[httpx.Request] = []

	def handler(request: httpx.Request) -> httpx.Response:
		requests.append(request)
		if request.url.path == '/identity':
			return httpx.Response(200, json={'identity': '198.51.100.10'}, extensions={'http_version': b'HTTP/2'})
		return httpx.Response(200, text='secret response body', extensions={'http_version': b'HTTP/2'})

	# When
	result = run_proof(config, FakeBrowser(browser_session()), transport=httpx.MockTransport(handler))

	# Then
	assert result.ok is False
	assert result.category == 'pre_read_non_json'
	assert all(request.url.path != '/api/user/sign_in' for request in requests)
	assert 'secret response body' not in result.model_dump_json()
