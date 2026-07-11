from collections.abc import Mapping
from typing import TypedDict

from playwright.async_api import Browser

class ProxySettings(TypedDict):
	server: str

async def launch_async(
	*,
	headless: bool,
	humanize: bool,
	env: Mapping[str, str],
	proxy: ProxySettings | None = ...,
) -> Browser: ...
