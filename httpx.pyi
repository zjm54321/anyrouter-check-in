from collections.abc import Callable, Mapping
from typing import Self

from proof_harness.json_types import JsonValue

class HTTPError(Exception): ...
class BaseTransport: ...

class URL:
	path: str

class Headers:
	def __contains__(self, key: str) -> bool: ...
	def __getitem__(self, key: str) -> str: ...

class Request:
	url: URL
	headers: Headers
	content: bytes
	method: str

class Response:
	status_code: int
	headers: Headers
	http_version: str
	content: bytes
	def __init__(
		self,
		status_code: int,
		*,
		json: JsonValue | Mapping[str, JsonValue] = ...,
		text: str = ...,
		headers: Mapping[str, str] = ...,
		extensions: Mapping[str, bytes] = ...,
	) -> None: ...

class Cookies:
	def set(self, name: str, value: str, *, domain: str, path: str) -> None: ...

class Client:
	cookies: Cookies
	def __init__(
		self,
		*,
		http2: bool,
		timeout: float,
		trust_env: bool,
		transport: BaseTransport | None,
		proxy: str | None,
	) -> None: ...
	def __enter__(self) -> Self: ...
	def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: object) -> None: ...
	def get(self, url: str, *, headers: Mapping[str, str]) -> Response: ...
	def post(self, url: str, *, headers: Mapping[str, str]) -> Response: ...

class MockTransport(BaseTransport):
	def __init__(self, handler: Callable[[Request], Response]) -> None: ...
