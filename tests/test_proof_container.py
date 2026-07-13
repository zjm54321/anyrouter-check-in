from pathlib import Path


def proof_dockerfile() -> str:
	return Path('Dockerfile.proof').read_text(encoding='utf-8')


def test_proof_image_installs_xvfb_run_runtime_dependencies() -> None:
	# Given
	dockerfile = proof_dockerfile()

	# When
	installed_packages = dockerfile.split('apt-get install -y --no-install-recommends', 1)[1].split(
		'&& rm -rf',
		1,
	)[0]

	# Then
	assert '\n\t\txauth \\' in installed_packages


def test_proof_image_verifies_container_timeout_binary() -> None:
	# Given
	dockerfile = proof_dockerfile()

	# When
	timeout_check = 'RUN test -x /usr/bin/timeout'

	# Then
	assert timeout_check in dockerfile


def test_proof_image_installs_chromium_runtime_dependencies_before_browser() -> None:
	# Given
	dockerfile = proof_dockerfile()

	# When
	dependency_install = dockerfile.find('playwright install-deps chromium')
	browser_install = dockerfile.find('ensure_binary()')

	# Then
	assert dependency_install >= 0
	assert dependency_install < browser_install


def test_proof_image_uses_fail_closed_programmatic_browser_installer() -> None:
	# Given
	dockerfile = proof_dockerfile()

	# When
	installer = dockerfile.split('RUN CLOAKBROWSER_AUTO_UPDATE=false', 1)[1]

	# Then
	assert 'CLOAKBROWSER_SKIP_CHECKSUM=false' in installer
	assert '.venv/bin/python' in installer
	assert 'uv run' not in installer
	assert 'python -m cloakbrowser install' not in dockerfile
	assert 'ensure_binary()' in installer
	assert 'binary_info()' in installer
	assert 'CLOAKBROWSER_BINARY_PATH' in installer
	assert 'raise RuntimeError' in installer


def test_proof_image_validates_installed_browser_contract() -> None:
	# Given
	dockerfile = proof_dockerfile()

	# When
	installer = dockerfile.split('RUN CLOAKBROWSER_AUTO_UPDATE=false', 1)[1]

	# Then
	assert 'isinstance(installed_path, str)' in installer
	assert 'is_absolute()' in installer
	assert 'resolve(strict=True)' in installer
	assert 'is_file()' in installer
	assert 'stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH' in installer
	assert 'os.access(resolved_path, os.X_OK)' in installer
	assert "binary_metadata['installed'] is not True" in installer
	assert "binary_metadata['binary_path']" in installer
	assert 'metadata_path.resolve(strict=True) != resolved_path' in installer
	assert "binary_metadata['version']" in installer
	assert "[str(resolved_path), '--version']" in installer
	assert 'timeout=' in installer
	assert 'check=True' in installer
	assert 'json.dumps(' in installer


def test_proof_image_keeps_supply_chain_and_failure_guards() -> None:
	# Given
	dockerfile = proof_dockerfile()

	# When
	from_lines = [line for line in dockerfile.splitlines() if line.startswith(('FROM ', 'COPY --from='))]

	# Then
	assert from_lines
	assert all('@sha256:' in line for line in from_lines)
	assert 'CLOAKBROWSER_SKIP_CHECKSUM=true' not in dockerfile
	assert '|| true' not in dockerfile


def test_proof_image_entrypoint_uses_venv_python_directly_under_xvfb() -> None:
	# Given
	dockerfile = proof_dockerfile()

	# When
	entrypoint = next(line for line in dockerfile.splitlines() if line.startswith('ENTRYPOINT '))

	# Then
	assert entrypoint == 'ENTRYPOINT ["xvfb-run", "-a", ".venv/bin/python", "proof_checkin.py"]'
	assert 'uv run' not in entrypoint


def test_proof_image_exposes_only_the_baked_browser_binary_at_runtime() -> None:
	# Given
	dockerfile = proof_dockerfile()

	# When
	runtime_contract = dockerfile.split("runtime_link = Path('/opt/cloakbrowser')", 1)[1]

	# Then
	assert "runtime_link.symlink_to(resolved_path.parent" in runtime_contract
	assert "runtime_path.resolve(strict=True) != resolved_path" in runtime_contract
	assert 'ENV CLOAKBROWSER_AUTO_UPDATE=false' in runtime_contract
	assert 'CLOAKBROWSER_BINARY_PATH=/opt/cloakbrowser/chrome' in runtime_contract
	assert 'COPY checkin.py proof_checkin.py proof_browser_smoke.py ./' in dockerfile


def test_credential_free_smoke_bypasses_browser_entrypoint() -> None:
	# Given
	workflow = Path('.github/workflows/proof-image.yml').read_text(encoding='utf-8')

	# When
	smoke_step = workflow.split('name: Run credential-free fail-closed smoke test', 1)[1].split(
		'- name: Log in to GHCR',
		1,
	)[0]

	# Then
	assert 'docker run --entrypoint .venv/bin/python' in smoke_step
	assert 'proof_checkin.py' in smoke_step


def test_browser_startup_smoke_uses_read_only_ab_with_writable_profile_acceptance() -> None:
	# Given
	workflow = Path('.github/workflows/proof-image.yml').read_text(encoding='utf-8')

	# When
	smoke_step = workflow.split('name: Run credential-free browser startup A/B/A smoke', 1)[1].split(
		'- name: Log in to GHCR',
		1,
	)[0]

	# Then
	assert "'--network', 'none'" in smoke_step
	assert "'--read-only'" in smoke_step
	assert "'--tmpfs', '/tmp:" in smoke_step
	assert "'--tmpfs', '/dev/shm:" in smoke_step
	assert "'--tmpfs', '/home/cloak:" in smoke_step
	assert 'HOME=/home/cloak' in smoke_step
	assert 'XDG_CONFIG_HOME=/home/cloak/.config' in smoke_step
	assert 'XDG_CACHE_HOME=/home/cloak/.cache' in smoke_step
	assert 'XDG_RUNTIME_DIR=/home/cloak/.runtime' in smoke_step
	assert 'TMPDIR=/home/cloak' in smoke_step
	assert 'proof_browser_smoke.py' in smoke_step
	assert 'timeout=' in smoke_step
	assert 'capture_output=True' in smoke_step
	assert "assert completed.stderr == ''" in smoke_step
	assert "print(json.dumps({'acceptance': acceptance_payload}, sort_keys=True))" in smoke_step
	assert 'smoke.stdout' not in smoke_step
	assert 'smoke.stderr' not in smoke_step


def test_browser_startup_smoke_repeats_baseline_after_acceptance() -> None:
	# Given
	workflow = Path('.github/workflows/proof-image.yml').read_text(encoding='utf-8')

	# When
	smoke_step = workflow.split('name: Run credential-free browser startup A/B/A smoke', 1)[1].split(
		'- name: Log in to GHCR',
		1,
	)[0]

	# Then
	baseline_position = smoke_step.index('baseline = run_smoke([])')
	acceptance_position = smoke_step.index('acceptance = run_smoke([')
	repeated_position = smoke_step.index('repeated_baseline = run_smoke([])')
	assert baseline_position < acceptance_position < repeated_position
	assert 'baseline_payload = payload(baseline)' in smoke_step
	assert 'assert repeated_baseline.returncode == baseline.returncode' in smoke_step
	assert 'assert payload(repeated_baseline) == baseline_payload' in smoke_step
