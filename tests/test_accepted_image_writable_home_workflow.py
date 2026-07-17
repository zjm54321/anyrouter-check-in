import ast
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).parent.parent
WORKFLOW_PATH = ROOT / '.github' / 'workflows' / 'accepted-image-writable-home-diagnostic.yml'
IMAGE = (
	'ghcr.io/zjm54321/anyrouter-reference-proof:'
	'a21879410c6c0cd113d277162d800288951df650@'
	'sha256:30a077d3b372dd72b8a87f90e051f7a84cf517958dd9d4a517159638c4daedd6'
)


def test_writable_home_workflow_is_dispatch_only_and_digest_pinned() -> None:
	assert WORKFLOW_PATH.is_file(), 'writable-HOME diagnostic workflow is missing'
	workflow = WORKFLOW_PATH.read_text(encoding='utf-8')
	header = workflow.split('\njobs:\n', 1)[0]
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

	assert parsed.returncode == 0
	assert parsed.stderr == ''
	assert 'on:\n  workflow_dispatch:\n' in header
	assert 'permissions:\n  contents: read\n' in header
	assert all(trigger not in header for trigger in ('push:', 'pull_request:', 'schedule:'))
	assert workflow.count(IMAGE) == 2
	assert 'docker pull --platform linux/amd64 "$IMAGE" >/dev/null' in workflow
	assert 'grep -Fxq -- "$EXPECTED_REPO_DIGEST"' in workflow
	assert "--format '{{.Architecture}}'" in workflow
	assert 'docker build' not in workflow
	assert 'Dockerfile.proof' not in workflow

	action_refs = [
		line.strip().removeprefix('uses: ') for line in workflow.splitlines() if line.strip().startswith('uses: ')
	]
	assert action_refs == ['actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10']
	assert all(len(action_ref.rsplit('@', 1)[1]) == 40 for action_ref in action_refs)
	assert all(character in '0123456789abcdef' for character in action_refs[0].rsplit('@', 1)[1])


def test_writable_home_workflow_runs_fresh_hardened_aba_from_intended_inputs() -> None:
	assert WORKFLOW_PATH.is_file(), 'writable-HOME diagnostic workflow is missing'
	workflow = WORKFLOW_PATH.read_text(encoding='utf-8')
	embedded_python = dedent(workflow.split("python3 - <<'PY'\n", 1)[1].split('\n          PY', 1)[0])

	assert ast.parse(embedded_python).body
	assert 'def run_case(writable_home: bool)' in embedded_python
	assert 'home_arguments: list[str] = []' in embedded_python
	assert 'if writable_home:' in embedded_python
	assert "'--rm', '--network', 'none', '--read-only'" in embedded_python
	assert "'--tmpfs', '/tmp:rw,nosuid,nodev,size=256m'" in embedded_python
	assert "'--tmpfs', '/dev/shm:rw,nosuid,nodev,size=512m'" in embedded_python
	assert embedded_python.count("'--tmpfs', '/home/cloak:rw,nosuid,nodev,size=64m'") == 1
	assert embedded_python.count("'--env', 'HOME=/home/cloak'") == 1
	assert embedded_python.count("'--env', 'XDG_CONFIG_HOME=/home/cloak/.config'") == 1
	assert embedded_python.count("'--env', 'XDG_CACHE_HOME=/home/cloak/.cache'") == 1
	assert embedded_python.count("'--env', 'XDG_RUNTIME_DIR=/home/cloak/.runtime'") == 1
	assert embedded_python.count("'--env', 'TMPDIR=/home/cloak'") == 1
	assert '*home_arguments,' in embedded_python
	assert 'cases = (False, True, False)' in embedded_python
	assert 'results = [run_case(writable_home) for writable_home in cases]' in embedded_python
	assert 'assert results[0] == results[2]' in embedded_python
	assert 'assert results[0][2] != results[1][2]' in embedded_python
	assert 'assert payload == writable_home_expected' in embedded_python
	assert 'assert record in read_only_records' in embedded_python
	assert all(
		record in embedded_python
		for record in (
			"('browser_launch_failure', False, 'browser_launch', False)",
			"('boundary_failure', False, 'boundary', False)",
			"('boundary_failure', False, 'boundary', True)",
			"('close_failure', False, 'browser_close', False)",
		)
	)
	assert "'category': 'pre_navigation'" in embedded_python
	assert "'closed': True" in embedded_python
	assert "'event': 'accepted_image_browser_boundary_probe'" in embedded_python
	assert "'ok': True" in embedded_python
	assert "'stage': 'pre_navigation'" in embedded_python
	assert 'type=bind,src={probe_path},dst=/app/accepted_image_aba_probe.py,readonly' in embedded_python
	assert "'--entrypoint', '/usr/bin/timeout', image" in embedded_python
	assert "'--signal=TERM', '--kill-after=5s', '55s'" in embedded_python
	assert "'/usr/bin/xvfb-run', '-a', '.venv/bin/python'" in embedded_python
	assert "'accepted_image_aba_probe.py'" in embedded_python
	assert 'timeout=70' in embedded_python
	assert "assert completed.stderr == ''" in embedded_python
	assert 'assert len(lines) == 1' in embedded_python
	assert "set(payload) == {'category', 'closed', 'event', 'ok', 'stage'}" in embedded_python
	assert 'except Exception:' in embedded_python
	assert "'category': 'driver_failure'" in embedded_python
	assert "'event': 'accepted_image_writable_home_aba'" in embedded_python
	assert "'stage': 'driver'" in embedded_python
	assert 'raise SystemExit(main())' in embedded_python


def test_writable_home_workflow_has_no_sensitive_or_mutating_paths() -> None:
	assert WORKFLOW_PATH.is_file(), 'writable-HOME diagnostic workflow is missing'
	workflow = WORKFLOW_PATH.read_text(encoding='utf-8')
	forbidden = (
		'secrets.',
		'packages:',
		'docker login',
		'docker push',
		'upload-artifact',
		'ANYROUTER_',
		'http://',
		'https://',
		'proxy',
		'screenshot',
		'env |',
		'printenv',
		'--privileged',
		'--cap-add',
		'--security-opt',
		'--no-sandbox',
		'-ac',
		'kubectl',
		'k3s',
		'metapi',
	)

	assert all(value.lower() not in workflow.lower() for value in forbidden)
