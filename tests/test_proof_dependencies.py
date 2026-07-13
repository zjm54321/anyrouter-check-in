from pathlib import Path


def test_project_declares_anyio_as_a_runtime_dependency() -> None:
	# Given
	pyproject = Path('pyproject.toml').read_text(encoding='utf-8')
	project_dependencies = pyproject.split('dependencies = [', 1)[1].split(']', 1)[0]

	# When
	declared = '"anyio>=4.0.0"' in project_dependencies

	# Then
	assert declared is True


def test_lock_records_anyio_as_the_root_runtime_dependency() -> None:
	# Given
	lockfile = Path('uv.lock').read_text(encoding='utf-8')
	root_package = lockfile.split('name = "anyrouter-check-in"', 1)[1].split('[[package]]', 1)[0]

	# When
	root_dependencies = root_package.split('dependencies = [', 1)[1].split(']', 1)[0]
	metadata = root_package.split('[package.metadata]', 1)[1].split('[package.metadata.requires-dev]', 1)[0]

	# Then
	assert '{ name = "anyio" }' in root_dependencies
	assert '{ name = "anyio", specifier = ">=4.0.0" }' in metadata
