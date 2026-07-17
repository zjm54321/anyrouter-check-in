import ast
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).parent.parent
WORKFLOW_PATH = ROOT / '.github' / 'workflows' / 'accepted-image-credential-env-diagnostic.yml'
IMAGE = (
	'ghcr.io/zjm54321/anyrouter-reference-proof:'
	'a21879410c6c0cd113d277162d800288951df650@'
	'sha256:30a077d3b372dd72b8a87f90e051f7a84cf517958dd9d4a517159638c4daedd6'
)


def test_accepted_image_workflow_is_dispatch_only_and_digest_pinned() -> None:
	# Given
	assert WORKFLOW_PATH.is_file(), 'accepted-image diagnostic workflow is missing'
	workflow = WORKFLOW_PATH.read_text(encoding='utf-8')
	header = workflow.split('\njobs:\n', 1)[0]

	# When
	parsed = subprocess.run(
		[
			sys.executable,
			'-c',
			'import sys, yaml; assert yaml.compose(sys.stdin.read()) is not None',
		],
		input=workflow,
		capture_output=True,
		text=True,
		check=False,
	)

	# Then
	assert parsed.returncode == 0
	assert parsed.stderr == ''
	assert 'on:\n  workflow_dispatch:\n' in header
	assert 'permissions:\n  contents: read\n' in header
	assert all(trigger not in header for trigger in ('push:', 'pull_request:', 'schedule:'))
	assert IMAGE in workflow
	assert 'docker pull --platform linux/amd64 "$IMAGE"' in workflow
	assert 'grep -Fx -- "$EXPECTED_REPO_DIGEST"' in workflow
	assert "--format '{{.Architecture}}'" in workflow
	assert 'docker build' not in workflow
	assert 'Dockerfile.proof' not in workflow
	assert 'packages:' not in workflow

	action_refs = [
		line.strip().removeprefix('uses: ') for line in workflow.splitlines() if line.strip().startswith('uses: ')
	]
	assert action_refs == ['actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10']
	assert all(len(action_ref.rsplit('@', 1)[1]) == 40 for action_ref in action_refs)
	assert all(character in '0123456789abcdef' for character in action_refs[0].rsplit('@', 1)[1])


def test_accepted_image_workflow_runs_fresh_hardened_credential_env_aba() -> None:
	# Given
	assert WORKFLOW_PATH.is_file(), 'accepted-image diagnostic workflow is missing'
	workflow = WORKFLOW_PATH.read_text(encoding='utf-8')
	embedded_python = dedent(workflow.split("python3 - <<'PY'\n", 1)[1].split('\n          PY', 1)[0])

	# When
	parsed_python = ast.parse(embedded_python)

	# Then
	assert parsed_python.body
	assert 'cases = (False, True, False)' in embedded_python
	assert 'assert results[0] == results[2]' in embedded_python
	assert 'assert results[0] == results[1]' not in embedded_python
	assert 'return completed.returncode, completed.stdout, payload' in embedded_python
	assert 'for _, _, payload in results:' in embedded_python
	assert "'--rm', '--network', 'none', '--read-only'" in embedded_python
	assert "'--tmpfs', '/tmp:rw,nosuid,nodev,size=256m'" in embedded_python
	assert "'--tmpfs', '/dev/shm:rw,nosuid,nodev,size=512m'" in embedded_python
	assert "'--tmpfs', '/home/cloak:rw,nosuid,nodev,size=64m'" in embedded_python
	assert 'type=bind,src={probe_path},dst=/app/accepted_image_aba_probe.py,readonly' in embedded_python
	assert "'ANYROUTER_EMAIL=ab-email-sentinel@example.invalid'" in embedded_python
	assert "'ANYROUTER_PASSWORD=ab-password-sentinel-not-a-credential'" in embedded_python
	assert "set(payload) == {'category', 'closed', 'event', 'ok', 'stage'}" in embedded_python
	assert "payload['event'] == 'accepted_image_browser_boundary_probe'" in embedded_python
	assert 'assert forbidden not in completed.stdout' in embedded_python
	assert 'assert forbidden not in completed.stderr' in embedded_python
	assert "assert completed.stderr == ''" in embedded_python
	assert 'assert len(lines) == 1' in embedded_python
	assert "'accepted_image_aba_probe.py'" in embedded_python
	assert "'--entrypoint', '/usr/bin/timeout', image" in embedded_python
	assert "'--signal=TERM', '--kill-after=5s', '55s'" in embedded_python
	assert 'timeout=70' in embedded_python
	assert 'except Exception:' in embedded_python
	assert "'category': 'driver_failure'" in embedded_python
	assert "'event': 'accepted_image_credential_env_aba'" in embedded_python
	assert "'stage': 'driver'" in embedded_python
	assert 'raise SystemExit(main())' in embedded_python


def test_accepted_image_workflow_has_no_secret_or_mutating_paths() -> None:
	# Given
	assert WORKFLOW_PATH.is_file(), 'accepted-image diagnostic workflow is missing'
	workflow = WORKFLOW_PATH.read_text(encoding='utf-8')

	# Then
	assert all(
		forbidden not in workflow
		for forbidden in (
			'secrets.',
			'docker login',
			'docker push',
			'upload-artifact',
			'--no-sandbox',
			'anyrouter.top',
			'kubectl',
			'k3s',
			'metapi',
		)
	)
