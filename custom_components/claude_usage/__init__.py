"""Claude Usage integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import LocalClaudeCodeProvider, RemoteAnthropicProvider
from .const import PLATFORMS, PROVIDER_LOCAL, PROVIDER_REMOTE, CONF_PROVIDER
from .coordinator import ClaudeUsageCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Claude Usage from a config entry."""
    provider_name = entry.data.get(CONF_PROVIDER, PROVIDER_REMOTE)
    if provider_name == PROVIDER_LOCAL:
        provider = LocalClaudeCodeProvider(hass, entry)
    else:
        provider = RemoteAnthropicProvider(hass, entry)

    coordinator = ClaudeUsageCoordinator(hass, entry, provider)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

