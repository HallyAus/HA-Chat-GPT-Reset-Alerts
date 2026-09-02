"""Secret redaction helpers."""

from __future__ import annotations

from typing import Any

_SECRET_KEYS = {
    "access_token",
    "refresh_token",
    "id_token",
    "api_key",
    "authorization",
    "cookie",
}


def redact_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("**REDACTED**" if str(key).casefold() in _SECRET_KEYS else redact_mapping(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_mapping(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_mapping(item) for item in value)
    return value
