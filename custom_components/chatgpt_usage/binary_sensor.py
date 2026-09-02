"""Binary sensors for ChatGPT Usage."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ChatGPTUsageCoordinator
from .entity import ChatGPTUsageEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ChatGPTUsageCoordinator = entry.runtime_data
    async_add_entities(
        [
            ChatGPTConnectedBinarySensor(coordinator),
            ChatGPTLimitReachedBinarySensor(coordinator),
            ChatGPTCreditsAvailableBinarySensor(coordinator),
        ]
    )


class ChatGPTConnectedBinarySensor(ChatGPTUsageEntity, BinarySensorEntity):
    _attr_name = "Connected"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:connection"

    def __init__(self, coordinator: ChatGPTUsageCoordinator) -> None:
        super().__init__(coordinator)
        identifier = self._entry.unique_id or self._entry.entry_id
        self._attr_unique_id = f"{identifier}_connected"

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        return {"last_error_category": self.coordinator.last_error_category}


class ChatGPTLimitReachedBinarySensor(ChatGPTUsageEntity, BinarySensorEntity):
    _attr_name = "Limit reached"
    _attr_icon = "mdi:speedometer-slow"

    def __init__(self, coordinator: ChatGPTUsageCoordinator) -> None:
        super().__init__(coordinator)
        identifier = self._entry.unique_id or self._entry.entry_id
        self._attr_unique_id = f"{identifier}_limit_reached"

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data
        if data is None:
            return False
        return bool(
            data.blocker_reason == "usage_limit"
            or any(
                window.limit_reached is True or (window.used_percent or 0) >= 100
                for window in data.windows
            )
        )


class ChatGPTCreditsAvailableBinarySensor(ChatGPTUsageEntity, BinarySensorEntity):
    _attr_name = "Credits available"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:credit-card-check-outline"

    def __init__(self, coordinator: ChatGPTUsageCoordinator) -> None:
        super().__init__(coordinator)
        identifier = self._entry.unique_id or self._entry.entry_id
        self._attr_unique_id = f"{identifier}_credits_available"

    @property
    def is_on(self) -> bool:
        credits = self.coordinator.data.credits if self.coordinator.data else None
        return bool(credits and (credits.unlimited or credits.has_credits))
