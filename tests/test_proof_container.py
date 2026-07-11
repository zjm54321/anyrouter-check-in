from pathlib import Path


def test_proof_image_installs_xvfb_run_runtime_dependencies() -> None:
	# Given
	dockerfile = Path('Dockerfile.proof').read_text(encoding='utf-8')

	# When
	installed_packages = dockerfile.split('apt-get install -y --no-install-recommends', 1)[1].split(
		'&& rm -rf',
		1,
	)[0]

	# Then
	assert '\n\t\txauth \\' in installed_packages


def test_proof_image_installs_chromium_runtime_dependencies_before_browser() -> None:
	# Given
	dockerfile = Path('Dockerfile.proof').read_text(encoding='utf-8')

	# When
	dependency_install = dockerfile.find('playwright install-deps chromium')
	browser_install = dockerfile.find('python -m cloakbrowser install')

	# Then
	assert dependency_install >= 0
	assert dependency_install < browser_install
