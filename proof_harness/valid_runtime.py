import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	class HTTPError(Exception): ...
else:
	from httpx import HTTPError

from proof_harness.browser import BrowserFailure, CloakBrowserBoundary
from proof_harness.config import ProofConfig
from proof_harness.models import ProofResult, Stage
from proof_harness.runner import run_proof


def run_valid(config: ProofConfig) -> ProofResult:
	try:
		return run_proof(config, CloakBrowserBoundary())
	except BrowserFailure as error:
		return ProofResult(ok=False, stage=Stage.BROWSER_LOGIN, category=error.category)
	except (HTTPError, json.JSONDecodeError, TimeoutError):
		return ProofResult(ok=False, stage=Stage.PRE_READ, category='bounded_transport_failure')
