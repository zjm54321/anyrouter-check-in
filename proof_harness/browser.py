from __future__ import annotations

import asyncio
import io
import os
from contextlib import redirect_stdout
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from cloakbrowser import launch_async
from playwright.async_api import Page, Response
from typing_extensions import override

from proof_harness.config import ProofConfig, ProxyMode
from proof_harness.json_types import parse_json, read_egress_identity
from proof_harness.models import BrowserSession, Cookie, ProgressStage, emit_progress

if TYPE_CHECKING:
	from proof_harness.json_types import JsonObject

	async def prepare_browser_page(_page: Page) -> None: ...
	async def navigate_login_page(_page: Page, _login_url: str, _timeout_ms: int) -> None: ...
	async def login_with_email_form(_page: Page, _email: str, _password: str, _timeout_ms: int) -> None: ...
	async def verify_browser_login(_page: Page, _console_url: str, _timeout_ms: int) -> JsonObject | None: ...
else:
	from utils.browser import (
		login_with_email_form,
		navigate_login_page,
		prepare_browser_page,
		verify_browser_login,
	)


class ProofPage(Protocol):
	async def evaluate(self, expression: str) -> str: ...
	async def goto(
		self,
		url: str,
		*,
		wait_until: Literal['commit', 'domcontentloaded', 'load', 'networkidle'] | None = None,
		timeout: float | None = None,
	) -> Response | None: ...


async def _read_user_agent(page: ProofPage) -> str:
	return await page.evaluate('() => navigator.userAgent')


@dataclass(frozen=True, slots=True)
class BrowserFailure(Exception):
	category: str

	@override
	def __str__(self) -> str:
		return self.category


class CloakBrowserBoundary:
	def login(self, config: ProofConfig) -> BrowserSession:
		return asyncio.run(self.login_async(config))

	async def login_async(self, config: ProofConfig) -> BrowserSession:
		browser_env = {
			key: value
			for key, value in os.environ.items()
			if key.lower() not in {'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'}
		}
		emit_progress(config.progress_enabled, ProgressStage.BROWSER_LAUNCH)
		if config.proxy_mode is ProxyMode.MIHOMO and config.proxy_url is not None:
			browser = await launch_async(
				headless=False,
				humanize=True,
				env=browser_env,
				proxy={'server': config.proxy_url},
			)
		else:
			browser = await launch_async(headless=False, humanize=True, env=browser_env)
		try:
			context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
			page = await context.new_page()
			proof_page: ProofPage = page
			with redirect_stdout(io.StringIO()):
				await prepare_browser_page(page)
				emit_progress(config.progress_enabled, ProgressStage.LOGIN_NAVIGATION)
				await navigate_login_page(page, f'{config.base_url}/login', 30_000)
				emit_progress(config.progress_enabled, ProgressStage.FORM_SUBMISSION)
				await login_with_email_form(
					page,
					config.account.email,
					config.account.password,
					30_000,
				)
				emit_progress(config.progress_enabled, ProgressStage.LOGIN_VERIFICATION)
				profile = await verify_browser_login(page, f'{config.base_url}/console', 30_000)
			if not isinstance(profile, dict) or not profile.get('id'):
				raise BrowserFailure('user_self_unverified')
			emit_progress(config.progress_enabled, ProgressStage.BROWSER_EGRESS)
			egress_page: ProofPage = await context.new_page()
			egress_response = await egress_page.goto(config.egress_url, wait_until='load', timeout=30_000)
			if egress_response is None or egress_response.status != 200:
				raise BrowserFailure('browser_egress_http_failure')
			try:
				egress_payload = parse_json(await egress_response.body())
			except ValueError as error:
				raise BrowserFailure('browser_egress_non_json') from error
			egress_identity = read_egress_identity(egress_payload)
			if egress_identity is None:
				raise BrowserFailure('browser_egress_required')
			user_agent = await _read_user_agent(proof_page)
			cookies = await context.cookies()
			parsed_cookies: list[Cookie] = []
			for item in cookies:
				name = item.get('name')
				value = item.get('value')
				if name and value:
					parsed_cookies.append(
						Cookie(name=name, value=value, domain=item.get('domain', ''), path=item.get('path', '/'))
					)
			return BrowserSession(
				cookies=tuple(parsed_cookies),
				api_user=str(profile['id']),
				user_agent=str(user_agent),
				egress_identity=egress_identity,
			)
		finally:
			emit_progress(config.progress_enabled, ProgressStage.BROWSER_CLOSE_START)
			await browser.close()
			emit_progress(config.progress_enabled, ProgressStage.BROWSER_CLOSE_END)
