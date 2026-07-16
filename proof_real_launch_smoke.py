from __future__ import annotations

import asyncio
import io
import os
import sys
from contextlib import redirect_stderr, redirect_stdout

import anyio

from proof_harness.real_launch_diagnostic import Category, DiagnosticResult, Stage, run_diagnostic


def main() -> int:
	result: DiagnosticResult
	try:
		with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
			match os.environ.get('PROOF_LOOP_MODE', 'asyncio'):
				case 'asyncio':
					result = asyncio.run(run_diagnostic(os.environ))
				case 'anyio':
					result = anyio.run(run_diagnostic, os.environ)
				case _:
					result = DiagnosticResult(category=Category.CONFIG_INVALID, stage=Stage.LAUNCH, ok=False)
	except Exception:  # noqa: BLE001, BROAD_EXCEPT_OK
		result = DiagnosticResult(category=Category.LAUNCH_FAILED, stage=Stage.LAUNCH, ok=False)
	_ = sys.stdout.write(f'{result.to_json()}\n')
	return 0 if result.ok else 1


if __name__ == '__main__':
	raise SystemExit(main())
