import json
from typing import NoReturn

import pytest

import proof_checkin
from proof_harness.config import ProofConfig, parse_proof_config
from tests.test_proof_harness import valid_env


def test_unexpected_exception_is_one_bounded_sanitized_result(
	monkeypatch: pytest.MonkeyPatch,
	capsys: pytest.CaptureFixture[str],
) -> None:
	# Given
	secret = 'runtime-secret-that-must-not-escape'
	config = parse_proof_config(valid_env())
	assert isinstance(config, ProofConfig)
	def parsed_config(_env: dict[str, str]) -> ProofConfig:
		return config

	monkeypatch.setattr(proof_checkin, 'parse_proof_config', parsed_config)

	def fail(_config: ProofConfig) -> NoReturn:
		raise RuntimeError(secret)

	monkeypatch.setattr(proof_checkin, '_load_valid', fail)

	# When
	exit_code = proof_checkin.main()
	output = capsys.readouterr()

	# Then
	assert exit_code == 1
	assert output.err == ''
	assert secret not in output.out
	assert json.loads(output.out)['category'] == 'unexpected_runtime_failure'
