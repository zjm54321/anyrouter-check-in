import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

import proof_exact_boundary_smoke as entrypoint
import proof_harness.browser as browser_module
from proof_harness.exact_boundary_diagnostic import Category, ExactBoundaryResult, Stage, run_exact_boundary_smoke


@dataclass(slots=True)
class FakePage:
	prepared: bool = False

	async def add_init_script(self, _script: str) -> None:
		self.prepared = True


@dataclass(slots=True)
class FakeContext:
	page: FakePage

	async def new_page(self) -> FakePage:
		return self.page


@dataclass(slots=True)
class FakeBrowser:
	context: FakeContext
	close_fails: bool = False
	closed: bool = False

	async def new_context(self, *, viewport: dict[str, int]) -> FakeContext:
		assert viewport == {'width': 1920, 'height': 1080}
		return self.context

	async def close(self) -> None:
		if self.close_fails:
			raise RuntimeError('secret close detail')
		self.closed = True


def test_exact_boundary_smoke_reaches_sentinel_and_completes_close(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# Given
	page = FakePage()
	browser = FakeBrowser(FakeContext(page))
	observed_env: list[Mapping[str, str]] = []

	async def launch(*, env: Mapping[str, str], headless: bool, humanize: bool) -> FakeBrowser:
		assert headless is False
		assert humanize is True
		observed_env.append(env)
		return browser

	monkeypatch.setattr(browser_module, 'launch_async', launch)

	# When
	result = run_exact_boundary_smoke()

	# Then
	assert result.to_json() == (
		'{"category":"pre_navigation","closed":true,'
		'"event":"cloakbrowser_exact_boundary_smoke","ok":true,"stage":"pre_navigation"}'
	)
	assert page.prepared is True
	assert browser.closed is True
	assert len(observed_env) == 1
	assert all(name.lower() not in {'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'} for name in observed_env[0])


def test_exact_boundary_smoke_classifies_close_failure_without_detail(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# Given
	browser = FakeBrowser(FakeContext(FakePage()), close_fails=True)

	async def launch(*, env: Mapping[str, str], headless: bool, humanize: bool) -> FakeBrowser:
		_ = env, headless, humanize
		return browser

	monkeypatch.setattr(browser_module, 'launch_async', launch)

	# When
	result = run_exact_boundary_smoke()

	# Then
	assert result.to_json() == (
		'{"category":"close_failure","closed":false,'
		'"event":"cloakbrowser_exact_boundary_smoke","ok":false,"stage":"browser_close"}'
	)
	assert 'secret' not in result.to_json()


def test_exact_boundary_smoke_classifies_boundary_failure_without_detail(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	# Given
	async def launch(*, env: Mapping[str, str], headless: bool, humanize: bool) -> FakeBrowser:
		_ = env, headless, humanize
		raise RuntimeError('credential path URL')

	monkeypatch.setattr(browser_module, 'launch_async', launch)

	# When
	result = run_exact_boundary_smoke()

	# Then
	assert result.to_json() == (
		'{"category":"boundary_failure","closed":false,'
		'"event":"cloakbrowser_exact_boundary_smoke","ok":false,"stage":"boundary"}'
	)
	assert all(value not in result.to_json() for value in ('credential', 'path', 'URL'))


def test_exact_boundary_entrypoint_emits_one_sanitized_result(
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	# Given
	result = ExactBoundaryResult(
		category=Category.PRE_NAVIGATION,
		stage=Stage.PRE_NAVIGATION,
		ok=True,
		closed=True,
	)
	monkeypatch.setattr(entrypoint, 'run_exact_boundary_smoke', lambda: result)

	# When
	exit_code = entrypoint.main()

	# Then
	captured = capsys.readouterr()
	lines = captured.out.splitlines()
	assert exit_code == 0
	assert len(lines) == 1
	assert captured.err == ''
	assert json.loads(lines[0]) == {
		'category': 'pre_navigation',
		'closed': True,
		'event': 'cloakbrowser_exact_boundary_smoke',
		'ok': True,
		'stage': 'pre_navigation',
	}


def test_exact_boundary_entrypoint_converts_invalid_setup_to_fixed_failure(
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	# Given
	def fail_setup() -> ExactBoundaryResult:
		raise RuntimeError('secret setup detail')

	monkeypatch.setattr(entrypoint, 'run_exact_boundary_smoke', fail_setup)

	# When
	exit_code = entrypoint.main()

	# Then
	captured = capsys.readouterr()
	assert exit_code == 1
	assert captured.out == (
		'{"category":"boundary_failure","closed":false,'
		'"event":"cloakbrowser_exact_boundary_smoke","ok":false,"stage":"boundary"}\n'
	)
	assert captured.err == ''


def test_exact_boundary_smoke_is_baked_into_image_and_workflow_is_identical_aba() -> None:
	# Given
	root = Path(__file__).parent.parent
	dockerfile = (root / 'Dockerfile.proof').read_text(encoding='utf-8')
	workflow = (root / '.github' / 'workflows' / 'exact-boundary-diagnostic.yml').read_text(encoding='utf-8')

	# Then
	assert 'proof_exact_boundary_smoke.py' in dockerfile
	assert "results = [run_case() for run_label in ('A', 'B', 'A')]" in workflow
	assert "assert results[0] == results[1] == results[2]" in workflow
	assert "'--network', 'none'" in workflow
	assert "'--read-only'" in workflow
	assert "'--tmpfs', '/tmp:rw,nosuid,nodev,size=256m'" in workflow
	assert "'--tmpfs', '/dev/shm:rw,nosuid,nodev,size=512m'" in workflow
	assert "'--tmpfs', '/home/cloak:rw,nosuid,nodev,size=64m'" in workflow
	assert "'proof_exact_boundary_smoke.py'" in workflow
	assert 'assert payload == expected' in workflow
	assert 'secrets.' not in workflow
	assert 'docker login' not in workflow
	assert 'docker push' not in workflow
	assert 'upload-artifact' not in workflow
