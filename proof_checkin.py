#!/usr/bin/env python3
from __future__ import annotations

import json
import os

import httpx

from proof_harness.browser import BrowserFailure, CloakBrowserBoundary
from proof_harness.config import ConfigFailure, parse_proof_config
from proof_harness.models import ProofResult, Stage
from proof_harness.runner import run_proof


def main() -> int:
	config = parse_proof_config(os.environ)
	if isinstance(config, ConfigFailure):
		result = ProofResult(ok=False, stage=config.stage, category=config.category)
		print(result.model_dump_json())
		return 1
	try:
		result = run_proof(config, CloakBrowserBoundary())
	except BrowserFailure as error:
		result = ProofResult(ok=False, stage=Stage.BROWSER_LOGIN, category=error.category)
	except (httpx.HTTPError, json.JSONDecodeError, TimeoutError):
		result = ProofResult(ok=False, stage=Stage.PRE_READ, category='bounded_transport_failure')
	except Exception:
		result = ProofResult(ok=False, stage=Stage.BROWSER_LOGIN, category='unexpected_runtime_failure')
	print(result.model_dump_json())
	return 0 if result.ok else 1


if __name__ == '__main__':
	raise SystemExit(main())
