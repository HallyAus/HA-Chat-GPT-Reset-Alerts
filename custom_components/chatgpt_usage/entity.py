"""Base entity for ChatGPT Usage."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_PROVIDER, DOMAIN, NAME, PROVIDER_LOCAL
from .coordinator import ChatGPTUsageCoordinator


class ChatGPTUsageEntity(CoordinatorEntity[ChatGPTUsageCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: ChatGPTUsageCoordinator) -> None:
        super().__init__(coordinator)
        self._entry = coordinator.entry

    @property
    def device_info(self) -> DeviceInfo:
        provider = self._entry.data.get(CONF_PROVIDER)
        connection = "Local Codex" if provider == PROVIDER_LOCAL else "Remote OpenAI"
        identifier = self._entry.unique_id or self._entry.entry_id
        return DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            name=NAME,
            manufacturer="OpenAI",
            model=f"ChatGPT / Codex Usage Monitor ({connection})",
        )
