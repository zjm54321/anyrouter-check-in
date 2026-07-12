#!/usr/bin/env python3
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from proof_harness.config import ConfigFailure, ProofConfig, parse_proof_config
from proof_harness.models import ProofResult, Stage

if TYPE_CHECKING:
	def run_valid(_config: ProofConfig) -> ProofResult: ...


def _load_valid(config: ProofConfig) -> ProofResult:
	if not TYPE_CHECKING:
		from proof_harness.valid_runtime import run_valid

	return run_valid(config)


def main() -> int:
	config = parse_proof_config(os.environ)
	if isinstance(config, ConfigFailure):
		result = ProofResult(ok=False, stage=config.stage, category=config.category)
		print(result.model_dump_json())
		return 1
	try:
		result = _load_valid(config)
	except Exception:
		result = ProofResult(ok=False, stage=Stage.BROWSER_LOGIN, category='unexpected_runtime_failure')
	print(result.model_dump_json())
	return 0 if result.ok else 1


if __name__ == '__main__':
	raise SystemExit(main())
