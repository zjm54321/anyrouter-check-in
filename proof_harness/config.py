from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit

from proof_harness.json_types import parse_json
from proof_harness.models import Stage


class ProxyMode(str, Enum):
	DIRECT = 'direct'
	MIHOMO = 'mihomo'


@dataclass(frozen=True, slots=True)
class ProofAccount:
	email: str
	password: str


@dataclass(frozen=True, slots=True)
class ProofConfig:
	account: ProofAccount
	base_url: str
	egress_url: str
	egress_salt: str
	proxy_mode: ProxyMode
	proxy_url: str | None
	progress_enabled: bool = False
	timeout_seconds: float = 30.0


@dataclass(frozen=True, slots=True)
class ConfigFailure:
	stage: Stage
	category: str


def parse_proof_config(env: Mapping[str, str]) -> ProofConfig | ConfigFailure:
	if env.get('PROOF_MODE', '').strip().lower() != 'true':
		return ConfigFailure(Stage.CONFIG, 'proof_mode_required')
	progress_input = env.get('PROOF_PROGRESS')
	if progress_input not in {None, 'false', 'true'}:
		return ConfigFailure(Stage.CONFIG, 'progress_invalid')
	accounts_input = env.get('ANYROUTER_ACCOUNTS')
	email_input = env.get('ANYROUTER_EMAIL')
	password_input = env.get('ANYROUTER_PASSWORD')
	separate_input_present = email_input is not None or password_input is not None
	if accounts_input is not None and separate_input_present:
		return ConfigFailure(Stage.CONFIG, 'credential_modes_conflict')
	if separate_input_present:
		if not email_input or not password_input:
			return ConfigFailure(Stage.CONFIG, 'credentials_required')
		proof_account = ProofAccount(email=email_input, password=password_input)
	else:
		try:
			accounts = parse_json(accounts_input or '')
		except ValueError:
			return ConfigFailure(Stage.CONFIG, 'accounts_invalid')
		if not isinstance(accounts, list) or len(accounts) != 1:
			return ConfigFailure(Stage.CONFIG, 'single_account_required')
		account = accounts[0]
		if not isinstance(account, dict):
			return ConfigFailure(Stage.CONFIG, 'account_invalid')
		email = account.get('email')
		password = account.get('password')
		if not isinstance(email, str) or not email or not isinstance(password, str) or not password:
			return ConfigFailure(Stage.CONFIG, 'credentials_required')
		proof_account = ProofAccount(email=email, password=password)
	base_url = env.get('PROOF_BASE_URL', 'https://anyrouter.top').rstrip('/')
	parsed_base = urlsplit(base_url)
	if parsed_base.scheme not in {'http', 'https'} or not parsed_base.netloc:
		return ConfigFailure(Stage.CONFIG, 'base_url_invalid')
	egress_url = env.get('PROOF_EGRESS_URL', '').strip()
	if not egress_url:
		return ConfigFailure(Stage.CONFIG, 'egress_url_required')
	parsed_egress = urlsplit(egress_url)
	if parsed_egress.scheme not in {'http', 'https'} or not parsed_egress.netloc:
		return ConfigFailure(Stage.CONFIG, 'egress_url_invalid')
	try:
		proxy_mode = ProxyMode(env.get('PROOF_PROXY_MODE', 'direct').strip().lower())
	except ValueError:
		return ConfigFailure(Stage.CONFIG, 'proxy_mode_invalid')
	proxy_url = env.get('CHECKIN_PROXY_URL', '').strip() or None
	if proxy_mode is ProxyMode.MIHOMO and proxy_url is None:
		return ConfigFailure(Stage.CONFIG, 'proxy_required')
	egress_salt = env.get('PROOF_EGRESS_SALT', '').strip()
	if not egress_salt:
		return ConfigFailure(Stage.CONFIG, 'egress_salt_required')
	return ProofConfig(
		account=proof_account,
		base_url=base_url,
		egress_url=egress_url,
		egress_salt=egress_salt,
		proxy_mode=proxy_mode,
		proxy_url=proxy_url,
		progress_enabled=progress_input == 'true',
	)
