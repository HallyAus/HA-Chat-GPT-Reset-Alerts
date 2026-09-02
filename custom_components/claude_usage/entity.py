"""Base entities for Claude Usage."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VERSION
from .coordinator import ClaudeUsageCoordinator


class ClaudeUsageEntity(CoordinatorEntity[ClaudeUsageCoordinator]):
    """Base coordinator entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ClaudeUsageCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.entry
        provider = entry.data.get("provider", "remote")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Claude Usage",
            manufacturer="Anthropic",
            model=f"Claude Subscription Usage Monitor ({provider})",
            sw_version=VERSION,
        )
