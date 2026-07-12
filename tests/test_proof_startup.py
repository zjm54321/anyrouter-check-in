import os
import subprocess
import sys
import textwrap
from pathlib import Path


def test_invalid_config_exits_without_importing_browser_dependencies() -> None:
	# Given
	program = textwrap.dedent(
		"""
		import builtins
		import runpy

		original_import = builtins.__import__
		blocked = ('proof_harness.browser', 'cloakbrowser', 'playwright')

		def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
			if name.startswith(blocked):
				raise RuntimeError(f'blocked import: {name}')
			return original_import(name, globals, locals, fromlist, level)

		builtins.__import__ = guarded_import
		runpy.run_path('proof_checkin.py', run_name='__main__')
		"""
	)
	environment = os.environ.copy()
	for name in ('PROOF_MODE', 'ANYROUTER_ACCOUNTS', 'PROOF_EGRESS_URL', 'PROOF_EGRESS_SALT'):
		_ = environment.pop(name, None)
	expected = (
		'{"browser_egress_sha256":null,"category":"proof_mode_required","cookie_names":[],'
		'"http":[],"http_egress_sha256":null,"ok":false,"stage":"config"}\n'
	)

	# When
	completed = subprocess.run(
		[sys.executable, '-c', program],
		check=False,
		capture_output=True,
		text=True,
		env=environment,
		timeout=10,
	)

	# Then
	assert completed.returncode == 1
	assert completed.stdout == expected
	assert completed.stderr == ''


def test_proof_workflow_bounds_container_smoke_and_rejects_timeout_statuses() -> None:
	# Given
	workflow = Path('.github/workflows/proof-image.yml').read_text(encoding='utf-8')

	# When
	smoke = workflow.split('- name: Run credential-free fail-closed smoke test', 1)[1].split(
		'- name: Log in to GHCR',
		1,
	)[0]

	# Then
	assert 'timeout --signal=TERM --kill-after=5s 30s docker run' in smoke
	assert 'test "$status" -eq 1' in smoke
	assert '|| true' not in smoke
