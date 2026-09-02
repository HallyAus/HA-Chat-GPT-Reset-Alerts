"""Diagnostics support for Claude Usage."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_API_KEY,
    CONF_REFRESH_TOKEN,
)
from .coordinator import ClaudeUsageCoordinator

_REDACT = {CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN, CONF_API_KEY}


def _redact(data: dict[str, Any]) -> dict[str, Any]:
    return {key: "REDACTED" if key in _REDACT and value else value for key, value in data.items()}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: ClaudeUsageCoordinator = entry.runtime_data
    usage = coordinator.data
    return {
        "entry": {
            "data": _redact(dict(entry.data)),
            "options": _redact(dict(entry.options)),
            "version": entry.version,
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": type(coordinator.last_exception).__name__ if coordinator.last_exception else None,
            "update_interval_seconds": coordinator.update_interval.total_seconds() if coordinator.update_interval else None,
        },
        "usage": None
        if usage is None
        else {
            "source": usage.source,
            "plan": usage.plan,
            "last_updated": usage.last_updated.isoformat(),
            "windows": {
                wid: {
                    "display_name": window.display_name,
                    "used_percent": window.used_percent,
                    "reset_at": window.reset_at.isoformat() if window.reset_at else None,
                    "duration_seconds": window.duration_seconds,
                    "kind": window.kind,
                    "model": window.model,
                    "surface": window.surface,
                }
                for wid, window in usage.windows.items()
            },
            "extra_usage_present": usage.extra_usage is not None,
        },
    }
