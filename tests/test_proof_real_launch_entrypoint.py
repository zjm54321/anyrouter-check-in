import asyncio
from collections.abc import Awaitable, Callable, Coroutine, Mapping

import anyio
import pytest

import proof_real_launch_smoke as entrypoint
from proof_harness.real_launch_diagnostic import Category, DiagnosticResult, Stage


@pytest.mark.parametrize(
	('mode', 'expected_runner'),
	((None, 'asyncio'), ('asyncio', 'asyncio'), ('anyio', 'anyio')),
)
def test_entrypoint_uses_requested_loop_runner(
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
	mode: str | None,
	expected_runner: str,
) -> None:
	# Given
	asyncio_run = asyncio.run
	anyio_run = anyio.run
	observed: list[str] = []

	async def run_diagnostic(_env: Mapping[str, str]) -> DiagnosticResult:
		return DiagnosticResult(category=Category.READY, stage=Stage.COMPLETE, ok=True)

	def run_with_asyncio(coroutine: Coroutine[None, None, DiagnosticResult]) -> DiagnosticResult:
		observed.append('asyncio')
		return asyncio_run(coroutine)

	def run_with_anyio(
		function: Callable[[Mapping[str, str]], Awaitable[DiagnosticResult]],
		env: Mapping[str, str],
	) -> DiagnosticResult:
		observed.append('anyio')
		return anyio_run(function, env)

	if mode is None:
		monkeypatch.delenv('PROOF_LOOP_MODE', raising=False)
	else:
		monkeypatch.setenv('PROOF_LOOP_MODE', mode)
	monkeypatch.setattr(entrypoint, 'run_diagnostic', run_diagnostic)
	monkeypatch.setattr(asyncio, 'run', run_with_asyncio)
	monkeypatch.setattr(anyio, 'run', run_with_anyio)

	# When
	exit_code = entrypoint.main()

	# Then
	assert exit_code == 0
	assert observed == [expected_runner]
	assert capsys.readouterr().out == (
		'{"category":"ready","event":"cloakbrowser_proof_launch_smoke",'
		'"ok":true,"stage":"complete"}\n'
	)


def test_entrypoint_rejects_unknown_loop_mode_without_running_diagnostic(
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	# Given
	observed: list[str] = []

	def run_with_asyncio(_coroutine: Coroutine[None, None, DiagnosticResult]) -> DiagnosticResult:
		observed.append('asyncio')
		return DiagnosticResult(category=Category.READY, stage=Stage.COMPLETE, ok=True)

	def run_with_anyio(
		_function: Callable[[Mapping[str, str]], Awaitable[DiagnosticResult]],
		_env: Mapping[str, str],
	) -> DiagnosticResult:
		observed.append('anyio')
		return DiagnosticResult(category=Category.READY, stage=Stage.COMPLETE, ok=True)

	monkeypatch.setenv('PROOF_LOOP_MODE', 'unknown')
	monkeypatch.setattr(asyncio, 'run', run_with_asyncio)
	monkeypatch.setattr(anyio, 'run', run_with_anyio)

	# When
	exit_code = entrypoint.main()

	# Then
	assert exit_code == 1
	assert observed == []
	assert capsys.readouterr().out == (
		'{"category":"config_invalid","event":"cloakbrowser_proof_launch_smoke",'
		'"ok":false,"stage":"launch"}\n'
	)
