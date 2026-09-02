"""DataUpdateCoordinator and reset persistence for ChatGPT Usage."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    LocalCodexProvider,
    ProviderAuthError,
    ProviderConnectionError,
    ProviderError,
    ProviderRateLimited,
    ProviderSchemaError,
    RemoteOpenAIProvider,
    UsageProvider,
)
from .const import (
    CONF_PROVIDER,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    EVENT_USAGE_RESET,
    PROVIDER_LOCAL,
    STORAGE_KEY_TEMPLATE,
    STORAGE_VERSION,
)
from .models import ChatGPTUsageData, PersistedWindowState, UsageWindow
from .reset import detect_reset

_LOGGER = logging.getLogger(__name__)


class ChatGPTUsageCoordinator(DataUpdateCoordinator[ChatGPTUsageData]):
    """Coordinate polling and exactly-once reset events."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        interval = int(entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}:{entry.entry_id}",
            update_interval=timedelta(seconds=interval),
            config_entry=entry,
            always_update=False,
        )
        self.provider: UsageProvider = (
            LocalCodexProvider(hass, entry)
            if entry.data.get(CONF_PROVIDER) == PROVIDER_LOCAL
            else RemoteOpenAIProvider(hass, entry)
        )
        self._store = Store[dict[str, Any]](
            hass, STORAGE_VERSION, STORAGE_KEY_TEMPLATE.format(entry_id=entry.entry_id)
        )
        self._window_state: dict[str, PersistedWindowState] = {}
        self._backoff_until: datetime | None = None
        self.last_successful_update: datetime | None = None
        self.last_error_category: str | None = None

    async def async_initialize(self) -> None:
        stored = await self._store.async_load() or {}
        raw = stored.get("windows") or {}
        if isinstance(raw, dict):
            self._window_state = {
                str(window_id): PersistedWindowState.from_dict(state)
                for window_id, state in raw.items()
                if isinstance(state, dict)
            }

    async def _async_update_data(self) -> ChatGPTUsageData:
        now = datetime.now(UTC)
        if self._backoff_until and now < self._backoff_until:
            seconds = int((self._backoff_until - now).total_seconds())
            raise UpdateFailed(f"Provider backoff active for another {seconds} seconds")
        try:
            data = await self.provider.async_get_usage()
        except ProviderAuthError as err:
            self.last_error_category = "authentication"
            raise ConfigEntryAuthFailed(str(err)) from err
        except ProviderRateLimited as err:
            self.last_error_category = "rate_limited"
            backoff = max(300, int(err.retry_after or 900))
            self._backoff_until = now + timedelta(seconds=min(backoff, 14400))
            raise UpdateFailed(
                f"OpenAI usage endpoint rate limited requests; backing off for {backoff} seconds"
            ) from err
        except ProviderSchemaError as err:
            self.last_error_category = "schema"
            raise UpdateFailed(str(err)) from err
        except ProviderConnectionError as err:
            self.last_error_category = "connection"
            raise UpdateFailed(str(err)) from err
        except ProviderError as err:
            self.last_error_category = "provider"
            raise UpdateFailed(str(err)) from err

        self._backoff_until = None
        self.last_error_category = None
        self.last_successful_update = data.last_updated
        await self._process_resets(data, now)
        return data

    async def _process_resets(self, data: ChatGPTUsageData, now: datetime) -> None:
        changed = False
        for window in data.windows:
            previous = self._window_state.get(window.id)
            if previous is None:
                self._window_state[window.id] = PersistedWindowState.from_window(window)
                changed = True
                continue
            detection = detect_reset(previous, window, now)
            last_event_key = previous.last_event_key
            if detection is not None:
                last_event_key = detection.event_key
                event = _reset_event_data(previous, window, detection.confidence)
                self.hass.bus.async_fire(EVENT_USAGE_RESET, event)
                _LOGGER.info(
                    "Detected ChatGPT/Codex usage reset for %s (%s)",
                    window.display_name,
                    detection.confidence,
                )
            new_state = PersistedWindowState.from_window(window, last_event_key)
            if new_state != previous:
                self._window_state[window.id] = new_state
                changed = True
        if changed:
            await self._store.async_save(
                {"windows": {key: value.as_dict() for key, value in self._window_state.items()}}
            )

    async def async_shutdown(self) -> None:
        await self.provider.async_close()


def _reset_event_data(previous: PersistedWindowState, current: UsageWindow, confidence: str) -> dict[str, Any]:
    return {
        "window_id": current.id,
        "window": current.display_name,
        "limit_name": current.limit_name,
        "previous_used_percent": previous.used_percent,
        "new_used_percent": current.used_percent,
        "previous_remaining_percent": previous.remaining_percent,
        "new_remaining_percent": current.remaining_percent,
        "remaining_percent": current.remaining_percent,
        "previous_reset_at": previous.reset_at,
        "new_reset_at": current.reset_at.isoformat() if current.reset_at else None,
        "confidence": confidence,
    }
