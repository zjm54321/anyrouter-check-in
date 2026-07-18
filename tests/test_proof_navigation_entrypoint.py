from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

import proof_navigation_smoke as entrypoint
from proof_harness.navigation_diagnostic import (
	CloseStatus,
	DiagnosticResult,
	NavigationStatus,
	OverallResult,
	ShellStatus,
	Stage,
)


def ready_result() -> DiagnosticResult:
	return DiagnosticResult(
		root_navigation=NavigationStatus.HTTP_2XX,
		login_navigation=NavigationStatus.HTTP_2XX,
		login_shell=ShellStatus.READY,
		stage=Stage.COMPLETE,
		close_status=CloseStatus.CLOSED,
		overall_result=OverallResult.READY,
		ok=True,
	)


def test_navigation_entrypoint_emits_exactly_one_sanitized_json_object(
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	# Given
	async def run_diagnostic(_env: Mapping[str, str]) -> DiagnosticResult:
		print('credential URL body header exception path cookie status text screenshot')
		return ready_result()

	monkeypatch.setattr(entrypoint, 'run_diagnostic', run_diagnostic)

	# When
	exit_code = entrypoint.main()

	# Then
	captured = capsys.readouterr()
	assert exit_code == 0
	assert captured.err == ''
	assert captured.out == (
		'{"close":"closed","event":"anyrouter_navigation_diagnostic",'
		'"login_navigation":"http_2xx","login_shell":"ready","ok":true,'
		'"result":"ready","root_navigation":"http_2xx","stage":"complete"}\n'
	)


def test_navigation_entrypoint_redacts_unexpected_exception(
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	# Given
	async def fail_diagnostic(_env: Mapping[str, str]) -> DiagnosticResult:
		raise RuntimeError('credential URL body header exception path cookie status text screenshot')

	monkeypatch.setattr(entrypoint, 'run_diagnostic', fail_diagnostic)

	# When
	exit_code = entrypoint.main()

	# Then
	captured = capsys.readouterr()
	assert exit_code == 1
	assert captured.err == ''
	assert captured.out == (
		'{"close":"not_started","event":"anyrouter_navigation_diagnostic",'
		'"login_navigation":"not_attempted","login_shell":"not_attempted","ok":false,'
		'"result":"launch_failed","root_navigation":"not_attempted","stage":"launch"}\n'
	)


def test_navigation_entrypoint_is_copied_into_proof_image() -> None:
	# Given
	dockerfile = Path('Dockerfile.proof').read_text(encoding='utf-8')

	# When / Then
	assert 'proof_navigation_smoke.py' in dockerfile
