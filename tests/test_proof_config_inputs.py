import pytest

from proof_harness.config import ConfigFailure, ProofAccount, ProofConfig, parse_proof_config
from proof_harness.models import Stage
from tests.test_proof_harness import valid_env

EMAIL = 'separate-user@example.test'
PASSWORD = 'separate-super-secret-password'


def test_parse_config_accepts_complete_separate_credentials_as_same_account() -> None:
	# Given
	env = valid_env()
	del env['ANYROUTER_ACCOUNTS']
	env.update({'ANYROUTER_EMAIL': EMAIL, 'ANYROUTER_PASSWORD': PASSWORD})

	# When
	result = parse_proof_config(env)

	# Then
	assert isinstance(result, ProofConfig)
	assert result.account == ProofAccount(email=EMAIL, password=PASSWORD)


def test_parse_config_preserves_json_mode_when_separate_credentials_are_absent() -> None:
	# Given
	env = valid_env()

	# When
	result = parse_proof_config(env)

	# Then
	assert isinstance(result, ProofConfig)
	assert result.account == ProofAccount(email='user@example.test', password='super-secret-password')


@pytest.mark.parametrize(
	'separate_input',
	[
		{'ANYROUTER_EMAIL': EMAIL},
		{'ANYROUTER_PASSWORD': PASSWORD},
		{'ANYROUTER_EMAIL': '', 'ANYROUTER_PASSWORD': PASSWORD},
		{'ANYROUTER_EMAIL': EMAIL, 'ANYROUTER_PASSWORD': ''},
	],
)
def test_parse_config_rejects_partial_separate_credentials(
	separate_input: dict[str, str],
	caplog: pytest.LogCaptureFixture,
	capsys: pytest.CaptureFixture[str],
) -> None:
	# Given
	env = valid_env()
	del env['ANYROUTER_ACCOUNTS']
	env.update(separate_input)

	# When
	result = parse_proof_config(env)

	# Then
	assert result == ConfigFailure(Stage.CONFIG, 'credentials_required')
	captured = capsys.readouterr()
	emitted = caplog.text + captured.out + captured.err
	assert EMAIL not in emitted
	assert PASSWORD not in emitted


@pytest.mark.parametrize(
	'separate_input',
	[
		{'ANYROUTER_EMAIL': EMAIL},
		{'ANYROUTER_PASSWORD': PASSWORD},
		{'ANYROUTER_EMAIL': EMAIL, 'ANYROUTER_PASSWORD': PASSWORD},
	],
)
def test_parse_config_rejects_mixed_credential_modes(
	separate_input: dict[str, str],
	caplog: pytest.LogCaptureFixture,
	capsys: pytest.CaptureFixture[str],
) -> None:
	# Given
	env = valid_env()
	env.update(separate_input)

	# When
	result = parse_proof_config(env)

	# Then
	assert result == ConfigFailure(Stage.CONFIG, 'credential_modes_conflict')
	captured = capsys.readouterr()
	emitted = caplog.text + captured.out + captured.err
	assert EMAIL not in emitted
	assert PASSWORD not in emitted
