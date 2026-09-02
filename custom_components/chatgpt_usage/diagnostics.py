"""Privacy-safe diagnostics."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, VERSION
from .coordinator import ChatGPTUsageCoordinator
from .security import redact_mapping


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: ChatGPTUsageCoordinator = entry.runtime_data
    data = coordinator.data
    return {
        "integration_version": VERSION,
        "config": redact_mapping(entry.data),
        "poll_interval_seconds": int(
            entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        ),
        "last_update_success": coordinator.last_update_success,
        "last_successful_update": (
            coordinator.last_successful_update.isoformat()
            if coordinator.last_successful_update
            else None
        ),
        "last_error_category": coordinator.last_error_category,
        "source": data.source if data else entry.data.get("provider"),
        "plan": data.plan if data else None,
        "usage_window_count": len(data.windows) if data else 0,
        "windows": [window.to_safe_dict() for window in data.windows] if data else [],
        "credits": (
            {
                "has_credits": data.credits.has_credits,
                "unlimited": data.credits.unlimited,
                "balance": data.credits.balance,
                "overage_limit_reached": data.credits.overage_limit_reached,
            }
            if data and data.credits
            else None
        ),
        "available_reset_credits": data.available_reset_credits if data else None,
        "blocker_reason": data.blocker_reason if data else None,
    }
