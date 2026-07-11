from __future__ import annotations

import json
from collections.abc import Callable
from typing import TypeAlias

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list['JsonValue'] | dict[str, 'JsonValue']
JsonObject: TypeAlias = dict[str, JsonValue]

_loads: Callable[[str | bytes | bytearray], JsonValue] = json.loads


def parse_json(data: str | bytes | bytearray) -> JsonValue:
	return _loads(data)


def read_egress_identity(payload: JsonValue) -> str | None:
	if not isinstance(payload, dict):
		return None
	for key in ('identity', 'ip'):
		value = payload.get(key)
		if isinstance(value, str) and value.strip():
			return value
	return None
