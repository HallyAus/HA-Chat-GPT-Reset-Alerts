"""Binary sensor platform for Claude Usage."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    async_add_entities(
        [
            ClaudeConnectedBinarySensor(coordinator),
            ClaudeLimitReachedBinarySensor(coordinator),
            ClaudeExtraUsageEnabledBinarySensor(coordinator),
        ]
    )


class ClaudeConnectedBinarySensor(ClaudeUsageEntity, BinarySensorEntity):
    _attr_name = "Connected"
    _attr_icon = "mdi:cloud-check"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ClaudeUsageCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_connected"

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success


class ClaudeLimitReachedBinarySensor(ClaudeUsageEntity, BinarySensorEntity):
    _attr_name = "Limit reached"
    _attr_icon = "mdi:speedometer-slow"

    def __init__(self, coordinator: ClaudeUsageCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_limit_reached"

    @property
    def is_on(self) -> bool:
        if self.coordinator.data is None:
            return False
        return any(
            window.used_percent is not None and window.used_percent >= 100
            for window in self.coordinator.data.windows.values()
        )


class ClaudeExtraUsageEnabledBinarySensor(ClaudeUsageEntity, BinarySensorEntity):
    _attr_name = "Extra Usage enabled"
    _attr_icon = "mdi:credit-card-check-outline"

    def __init__(self, coordinator: ClaudeUsageCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_extra_usage_enabled"

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self.coordinator.data.extra_usage is not None
        )

    @property
    def is_on(self) -> bool:
        extra = self.coordinator.data.extra_usage if self.coordinator.data else None
        return bool(extra and extra.enabled)
