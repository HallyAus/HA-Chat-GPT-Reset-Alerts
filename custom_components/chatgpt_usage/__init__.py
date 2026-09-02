"""ChatGPT Usage integration."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from .const import CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: "HomeAssistant", entry: "ConfigEntry") -> bool:
    from homeassistant.const import Platform
    from .coordinator import ChatGPTUsageCoordinator

    platforms = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]
    coordinator = ChatGPTUsageCoordinator(hass, entry)
    await coordinator.async_initialize()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: "HomeAssistant", entry: "ConfigEntry") -> bool:
    from homeassistant.const import Platform

    platforms = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok


async def _async_update_listener(hass: Any, entry: Any) -> None:
    interval = int(entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
    entry.runtime_data.update_interval = timedelta(seconds=interval)
