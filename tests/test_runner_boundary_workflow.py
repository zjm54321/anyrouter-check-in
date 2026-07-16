import ast
from pathlib import Path
from textwrap import dedent


def test_runner_boundary_smoke_is_baked_into_proof_image() -> None:
	# Given
	dockerfile = Path('Dockerfile.proof').read_text(encoding='utf-8')

	# Then
	assert 'COPY proof_runner_boundary_smoke.py ./' in dockerfile


def test_runner_boundary_workflow_is_dispatch_only_identical_image_aba() -> None:
	# Given
	workflow = Path('.github/workflows/runner-boundary-diagnostic.yml').read_text(encoding='utf-8')
	header = workflow.split('\njobs:\n', 1)[0]
	embedded_python = dedent(workflow.split("python3 - <<'PY'\n", 1)[1].split('\n          PY', 1)[0])

	# Then
	assert 'on:\n  workflow_dispatch:\n' in header
	assert 'permissions:\n  contents: read\n' in header
	assert all(trigger not in header for trigger in ('push:', 'pull_request:', 'schedule:'))
	assert 'docker build --platform linux/amd64 --file Dockerfile.proof' in workflow
	assert "['docker', 'image', 'inspect', '--format', '{{.Id}}', image]" in workflow
	assert "results = [run_case() for _run_label in ('A', 'B', 'A')]" in workflow
	assert 'assert results[0] == results[1] == results[2]' in workflow
	assert 'assert inspect_image_id() == image_id' in workflow
	assert "'--rm', '--network', 'none', '--read-only'" in workflow
	assert "'--tmpfs', '/tmp:rw,nosuid,nodev,size=256m'" in workflow
	assert "'--tmpfs', '/dev/shm:rw,nosuid,nodev,size=512m'" in workflow
	assert "'--tmpfs', '/home/cloak:rw,nosuid,nodev,size=64m'" in workflow
	assert all(
		value in workflow
		for value in (
			'HOME=/home/cloak',
			'XDG_CONFIG_HOME=/home/cloak/.config',
			'XDG_CACHE_HOME=/home/cloak/.cache',
			'XDG_RUNTIME_DIR=/home/cloak/.runtime',
			'TMPDIR=/home/cloak',
		)
	)
	assert "'--entrypoint', '/usr/bin/timeout', image_id" in workflow
	assert "'--signal=TERM', '--kill-after=5s', '55s'" in workflow
	assert "'/usr/bin/xvfb-run', '-a', '.venv/bin/python'" in workflow
	assert "'proof_runner_boundary_smoke.py'" in workflow
	assert 'timeout=70' in workflow
	assert 'assert completed.returncode == 0' in workflow
	assert "assert completed.stderr == ''" in workflow
	assert 'assert len(lines) == 1' in workflow
	assert "'event': 'cloakbrowser_runner_boundary_smoke'" in workflow
	assert 'assert payload == expected' in workflow
	assert all(
		forbidden not in workflow
		for forbidden in (
			'secrets.',
			'packages:',
			'docker login',
			'docker push',
			'upload-artifact',
			'http://',
			'https://',
		)
	)
	assert 'proxy' not in workflow.lower()
	_ = ast.parse(embedded_python)
