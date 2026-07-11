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
