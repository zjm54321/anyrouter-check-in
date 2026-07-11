
import httpx
import pytest

from proof_harness.config import ConfigFailure, ProofConfig, parse_proof_config
from proof_harness.models import BrowserSession, Stage
from proof_harness.runner import run_proof
from tests.test_proof_harness import FakeBrowser, browser_session, valid_env


def test_config_requires_explicit_valid_egress_url() -> None:
	# Given
	missing = valid_env()
	del missing['PROOF_EGRESS_URL']
	invalid = valid_env()
	invalid['PROOF_EGRESS_URL'] = 'file:///secret'

	# When
	missing_result = parse_proof_config(missing)
	invalid_result = parse_proof_config(invalid)

	# Then
	assert missing_result == ConfigFailure(Stage.CONFIG, 'egress_url_required')
	assert invalid_result == ConfigFailure(Stage.CONFIG, 'egress_url_invalid')


@pytest.mark.parametrize('missing_side', ['browser', 'http'])
def test_runner_requires_both_egress_identities(missing_side: str) -> None:
	# Given
	config = parse_proof_config(valid_env())
	assert isinstance(config, ProofConfig)
	session = browser_session()
	if missing_side == 'browser':
		session = BrowserSession(session.cookies, session.api_user, session.user_agent, None)
	requests: list[str] = []

	def handler(request: httpx.Request) -> httpx.Response:
		requests.append(request.url.path)
		identity = None if missing_side == 'http' else '198.51.100.10'
		return httpx.Response(200, json={'identity': identity}, extensions={'http_version': b'HTTP/2'})

	# When
	result = run_proof(config, FakeBrowser(session), transport=httpx.MockTransport(handler))

	# Then
	assert result.ok is False
	assert result.category == f'{missing_side}_egress_required'
	expected_paths = ['/identity'] if missing_side == 'http' else []
	assert requests == expected_paths
	assert '/api/user/sign_in' not in requests


@pytest.mark.parametrize(
	'status,payload,content_type,expected',
	[
		(403, {'success': True}, 'application/json', 'sign_in_http_status'),
		(200, '<html>WAF secret</html>', 'text/html', 'sign_in_non_json'),
		(200, {'success': False, 'message': 'upstream secret'}, 'application/json', 'sign_in_rejected'),
	],
)
def test_failed_sign_in_stops_before_post_read(
	status: int,
	payload: dict[str, bool | str] | str,
	content_type: str,
	expected: str,
) -> None:
	# Given
	config = parse_proof_config(valid_env())
	assert isinstance(config, ProofConfig)
	paths: list[str] = []

	def handler(request: httpx.Request) -> httpx.Response:
		paths.append(request.url.path)
		if request.url.path == '/identity':
			return httpx.Response(200, json={'identity': '198.51.100.10'}, extensions={'http_version': b'HTTP/2'})
		if request.url.path == '/api/user/self':
			return httpx.Response(200, json={'success': True, 'data': {'id': 12345}}, extensions={'http_version': b'HTTP/2'})
		if isinstance(payload, str):
			return httpx.Response(status, text=payload, headers={'content-type': content_type}, extensions={'http_version': b'HTTP/2'})
		return httpx.Response(status, json=payload, extensions={'http_version': b'HTTP/2'})

	# When
	result = run_proof(config, FakeBrowser(browser_session()), transport=httpx.MockTransport(handler))

	# Then
	assert result.ok is False
	assert result.category == expected
	assert paths == ['/identity', '/api/user/self', '/api/user/sign_in']
	serialized = result.model_dump_json()
	assert 'WAF secret' not in serialized
	assert 'upstream secret' not in serialized


def test_already_signed_json_is_bounded_success_and_performs_post_read() -> None:
	# Given
	config = parse_proof_config(valid_env())
	assert isinstance(config, ProofConfig)
	paths: list[str] = []

	def handler(request: httpx.Request) -> httpx.Response:
		paths.append(request.url.path)
		if request.url.path == '/identity':
			return httpx.Response(200, json={'identity': '198.51.100.10'}, extensions={'http_version': b'HTTP/2'})
		if request.url.path == '/api/user/sign_in':
			return httpx.Response(200, json={'success': False, 'message': 'Already signed in today: upstream secret'}, extensions={'http_version': b'HTTP/2'})
		return httpx.Response(200, json={'success': True, 'data': {'id': 12345}}, extensions={'http_version': b'HTTP/2'})

	# When
	result = run_proof(config, FakeBrowser(browser_session()), transport=httpx.MockTransport(handler))

	# Then
	assert result.ok is True
	assert result.category == 'already_signed'
	assert paths[-1] == '/api/user/self'
	assert 'upstream secret' not in result.model_dump_json()
