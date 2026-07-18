from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum


class NavigationStatus(StrEnum):
	NOT_ATTEMPTED = 'not_attempted'
	TIMEOUT = 'timeout'
	TRANSPORT_FAILURE = 'transport_failure'
	NO_RESPONSE = 'no_response'
	HTTP_OTHER = 'http_other'
	HTTP_2XX = 'http_2xx'
	HTTP_3XX = 'http_3xx'
	HTTP_4XX = 'http_4xx'
	HTTP_5XX = 'http_5xx'


class ShellStatus(StrEnum):
	NOT_ATTEMPTED = 'not_attempted'
	READY = 'ready'
	TIMEOUT = 'timeout'
	FAILED = 'failed'


class CloseStatus(StrEnum):
	NOT_STARTED = 'not_started'
	CLOSED = 'closed'
	TIMEOUT = 'timeout'
	FAILED = 'failed'


class Stage(StrEnum):
	CONFIG = 'config'
	LAUNCH = 'launch'
	CONTEXT = 'context'
	PAGE = 'page'
	PREPARE = 'prepare'
	ROOT_NAVIGATION = 'root_navigation'
	LOGIN_NAVIGATION = 'login_navigation'
	LOGIN_SHELL = 'login_shell'
	CLOSE = 'close'
	COMPLETE = 'complete'


class OverallResult(StrEnum):
	CONFIG_INVALID = 'config_invalid'
	LAUNCH_TIMEOUT = 'launch_timeout'
	LAUNCH_FAILED = 'launch_failed'
	CONTEXT_TIMEOUT = 'context_timeout'
	CONTEXT_FAILED = 'context_failed'
	PAGE_TIMEOUT = 'page_timeout'
	PAGE_FAILED = 'page_failed'
	PREPARE_TIMEOUT = 'prepare_timeout'
	PREPARE_FAILED = 'prepare_failed'
	LOGIN_NAVIGATION_TIMEOUT = 'login_navigation_timeout'
	LOGIN_TRANSPORT_FAILURE = 'login_transport_failure'
	LOGIN_NO_RESPONSE = 'login_no_response'
	LOGIN_HTTP_OTHER = 'login_http_other'
	LOGIN_HTTP_4XX = 'login_http_4xx'
	LOGIN_HTTP_5XX = 'login_http_5xx'
	LOGIN_SHELL_TIMEOUT = 'login_shell_timeout'
	LOGIN_SHELL_FAILED = 'login_shell_failed'
	CLOSE_TIMEOUT = 'close_timeout'
	CLOSE_FAILED = 'close_failed'
	READY = 'ready'


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
	root_navigation: NavigationStatus
	login_navigation: NavigationStatus
	login_shell: ShellStatus
	stage: Stage
	close_status: CloseStatus
	overall_result: OverallResult
	ok: bool

	@classmethod
	def failure(cls, overall_result: OverallResult, stage: Stage) -> DiagnosticResult:
		return cls(
			root_navigation=NavigationStatus.NOT_ATTEMPTED,
			login_navigation=NavigationStatus.NOT_ATTEMPTED,
			login_shell=ShellStatus.NOT_ATTEMPTED,
			stage=stage,
			close_status=CloseStatus.NOT_STARTED,
			overall_result=overall_result,
			ok=False,
		)

	def to_json(self) -> str:
		return json.dumps(
			{
				'close': self.close_status.value,
				'event': 'anyrouter_navigation_diagnostic',
				'login_navigation': self.login_navigation.value,
				'login_shell': self.login_shell.value,
				'ok': self.ok,
				'result': self.overall_result.value,
				'root_navigation': self.root_navigation.value,
				'stage': self.stage.value,
			},
			separators=(',', ':'),
			sort_keys=True,
		)
