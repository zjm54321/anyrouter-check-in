from __future__ import annotations

import io
import sys
from contextlib import redirect_stderr, redirect_stdout

from proof_harness.runner_boundary_diagnostic import (
	Category,
	RunnerBoundaryResult,
	Stage,
	run_runner_boundary_smoke,
)


def main() -> int:
	try:
		with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
			result = run_runner_boundary_smoke()
	except Exception:  # noqa: BLE001, BROAD_EXCEPT_OK
		result = RunnerBoundaryResult(
			category=Category.BOUNDARY_FAILURE,
			stage=Stage.BOUNDARY,
			ok=False,
			closed=False,
		)
	_ = sys.stdout.write(f'{result.to_json()}\n')
	return 0 if result.ok else 1


if __name__ == '__main__':
	raise SystemExit(main())
