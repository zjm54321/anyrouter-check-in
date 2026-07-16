from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_real_launch_diagnostic_is_baked_into_image_and_workflow_is_credential_free() -> None:
	# Given
	dockerfile = (ROOT / 'Dockerfile.proof').read_text(encoding='utf-8')
	workflow = (ROOT / '.github' / 'workflows' / 'real-launch-diagnostic.yml').read_text(encoding='utf-8')

	# Then
	assert 'COPY checkin.py proof_checkin.py proof_browser_smoke.py proof_real_launch_smoke.py ./' in dockerfile
	assert "for value in ('full', 'allowlist', 'full')" in workflow
	assert "'--env', f'PROOF_ENV_MODE={value}'" in workflow
	assert "'--env', 'PROOF_HUMANIZE=false'" in workflow
	assert "'--network', 'none'" in workflow
	assert "'--read-only'" in workflow
	assert "'--tmpfs', '/home/cloak:rw,nosuid,nodev,size=64m'" in workflow
	assert 'secrets.' not in workflow
	assert 'docker login' not in workflow
	assert 'docker push' not in workflow
