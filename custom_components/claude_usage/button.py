"""Button platform for Claude Usage."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ClaudeUsageCoordinator
from .entity import ClaudeUsageEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: ClaudeUsageCoordinator = entry.runtime_data
    async_add_entities([ClaudeRefreshButton(coordinator)])


class ClaudeRefreshButton(ClaudeUsageEntity, ButtonEntity):
    """Manually request one coordinator refresh."""

    _attr_name = "Refresh"
    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ClaudeUsageCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_refresh"

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
