import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from typing_extensions import override

from proof_harness.config import ProofConfig, parse_proof_config
from proof_harness.runner import run_proof
from tests.test_proof_harness import FakeBrowser, browser_session, valid_env


def test_local_http_server_protocol_failure_sends_no_sign_in() -> None:
	# Given
	paths: list[str] = []

	class Handler(BaseHTTPRequestHandler):
		def do_GET(self) -> None:
			paths.append(self.path)
			body = json.dumps({'identity': '198.51.100.10'}).encode()
			_ = self.send_response(200)
			self.send_header('Content-Type', 'application/json')
			self.send_header('Content-Length', str(len(body)))
			self.end_headers()
			_ = self.wfile.write(body)

		def do_POST(self) -> None:
			paths.append(self.path)
			_ = self.send_response(500)
			self.end_headers()

		@override
		def log_message(self, format: str, *args: object) -> None:
			return

	server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
	thread = threading.Thread(target=server.serve_forever, daemon=True)
	thread.start()
	base_url = f'http://127.0.0.1:{server.server_port}'
	env = valid_env()
	env['PROOF_BASE_URL'] = base_url
	env['PROOF_EGRESS_URL'] = f'{base_url}/identity'
	config = parse_proof_config(env)
	assert isinstance(config, ProofConfig)

	try:
		# When
		result = run_proof(config, FakeBrowser(browser_session()))
	finally:
		server.shutdown()
		server.server_close()
		thread.join()

	# Then
	assert result.category == 'http_protocol_required'
	assert paths == ['/identity']
	assert '/api/user/sign_in' not in paths
