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
