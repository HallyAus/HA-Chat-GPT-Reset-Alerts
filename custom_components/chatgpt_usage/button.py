"""Manual refresh button."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ChatGPTUsageCoordinator
from .entity import ChatGPTUsageEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ChatGPTRefreshButton(entry.runtime_data)])


class ChatGPTRefreshButton(ChatGPTUsageEntity, ButtonEntity):
    _attr_name = "Refresh usage"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: ChatGPTUsageCoordinator) -> None:
        super().__init__(coordinator)
        identifier = self._entry.unique_id or self._entry.entry_id
        self._attr_unique_id = f"{identifier}_refresh"

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
