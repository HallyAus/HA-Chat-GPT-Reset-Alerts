"""Reset state persistence and event generation."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, EVENT_USAGE_RESET, RESET_STORE_VERSION
from .models import ClaudeUsageData, UsageWindow, parse_datetime
from .reset_logic import WindowSnapshot, reset_detected

_LOGGER = logging.getLogger(__name__)


class ResetTracker:
    """Persist previous windows and fire one event per confirmed rollover."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.store: Store[dict[str, Any]] = Store(
            hass,
            RESET_STORE_VERSION,
            f"{DOMAIN}.{entry_id}.reset_state",
        )
        self._loaded = False
        self._state: dict[str, Any] = {"windows": {}, "event_keys": []}

    async def async_load(self) -> None:
        if self._loaded:
            return
        stored = await self.store.async_load()
        if isinstance(stored, dict):
            self._state = stored
        self._state.setdefault("windows", {})
        self._state.setdefault("event_keys", [])
        self._loaded = True

    def _snapshot_from_saved(self, saved: dict[str, Any]) -> WindowSnapshot:
        used = saved.get("used_percent")
        return WindowSnapshot(
            used_percent=float(used) if isinstance(used, (int, float)) else None,
            reset_at=parse_datetime(saved.get("reset_at")),
        )

    @staticmethod
    def _serialize_window(window: UsageWindow) -> dict[str, Any]:
        return {
            "used_percent": window.used_percent,
            "reset_at": window.reset_at.isoformat() if window.reset_at else None,
        }

    async def async_process(self, data: ClaudeUsageData) -> list[dict[str, Any]]:
        await self.async_load()
        previous_windows = self._state.get("windows", {})
        event_keys = set(self._state.get("event_keys", []))
        events: list[dict[str, Any]] = []
        now = datetime.now(UTC)

        for window_id, window in data.windows.items():
            saved = previous_windows.get(window_id)
            if not isinstance(saved, dict):
                continue
            previous = self._snapshot_from_saved(saved)
            if not reset_detected(previous, window, now=now):
                continue
            marker = window.reset_at.isoformat() if window.reset_at else data.last_updated.strftime("%Y%m%dT%H")
            event_key = f"{window_id}:{marker}"
            if event_key in event_keys:
                continue
            event = {
                "entry_id": self.entry_id,
                "window_id": window.id,
                "window": window.display_name,
                "kind": window.kind,
                "model": window.model,
                "surface": window.surface,
                "previous_used_percent": previous.used_percent,
                "new_used_percent": window.used_percent,
                "remaining_percent": window.remaining_percent,
                "previous_reset_at": previous.reset_at.isoformat() if previous.reset_at else None,
                "new_reset_at": window.reset_at.isoformat() if window.reset_at else None,
                "detected_at": now.isoformat(),
            }
            events.append(event)
            event_keys.add(event_key)
            self.hass.bus.async_fire(EVENT_USAGE_RESET, event)
            _LOGGER.info("Detected Claude usage reset for %s", window.display_name)

        self._state = {
            "windows": {
                window_id: self._serialize_window(window)
                for window_id, window in data.windows.items()
            },
            # Bound storage growth while preserving plenty of recent rollovers.
            "event_keys": list(event_keys)[-100:],
        }
        await self.store.async_save(self._state)
        return events
