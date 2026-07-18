from __future__ import annotations

import io
import os
import sys
from contextlib import redirect_stderr, redirect_stdout

import anyio

from proof_harness.navigation_diagnostic import DiagnosticResult, OverallResult, Stage, run_diagnostic


def main() -> int:
	try:
		with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
			result = anyio.run(run_diagnostic, os.environ)
	except Exception:
		result = DiagnosticResult.failure(OverallResult.LAUNCH_FAILED, Stage.LAUNCH)
	_ = sys.stdout.write(f'{result.to_json()}\n')
	return 0 if result.ok else 1


if __name__ == '__main__':
	raise SystemExit(main())
