"""Sensors for ChatGPT Usage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ChatGPTUsageCoordinator
from .entity import ChatGPTUsageEntity
from .models import UsageWindow

_WINDOW_METRICS = ("usage", "remaining", "reset", "time_remaining")


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ChatGPTUsageCoordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def add_dynamic() -> None:
        data = coordinator.data
        if data is None:
            return
        entities: list[SensorEntity] = []
        for window in data.windows:
            for metric in _WINDOW_METRICS:
                key = f"window:{window.id}:{metric}"
                if key not in known:
                    known.add(key)
                    entities.append(ChatGPTWindowSensor(coordinator, window.id, metric))
        for key, factory in (
            ("last_update", ChatGPTLastUpdateSensor),
            ("plan", ChatGPTPlanSensor),
            ("credit_balance", ChatGPTCreditBalanceSensor),
            ("reset_credits", ChatGPTResetCreditsSensor),
        ):
            if key not in known:
                known.add(key)
                entities.append(factory(coordinator))
        if entities:
            async_add_entities(entities)

    add_dynamic()
    entry.async_on_unload(coordinator.async_add_listener(add_dynamic))


class ChatGPTWindowSensor(ChatGPTUsageEntity, SensorEntity):
    def __init__(self, coordinator: ChatGPTUsageCoordinator, window_id: str, metric: str) -> None:
        super().__init__(coordinator)
        self.window_id = window_id
        self.metric = metric
        initial = coordinator.data.window(window_id) if coordinator.data else None
        label = initial.display_name if initial else window_id.replace("_", " ").title()
        suffix = {
            "usage": "Usage",
            "remaining": "Remaining",
            "reset": "Reset",
            "time_remaining": "Time remaining",
        }[metric]
        self._attr_name = f"{label} {suffix}"
        identifier = self._entry.unique_id or self._entry.entry_id
        self._attr_unique_id = f"{identifier}_{window_id}_{metric}"
        if metric in ("usage", "remaining"):
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_icon = "mdi:gauge"
        elif metric == "reset":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
            self._attr_icon = "mdi:clock-refresh-outline"
        else:
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
            self._attr_icon = "mdi:timer-sand"

    @property
    def _window(self) -> UsageWindow | None:
        return self.coordinator.data.window(self.window_id) if self.coordinator.data else None

    @property
    def native_value(self) -> Any:
        window = self._window
        if window is None:
            return None
        if self.metric == "usage":
            return window.used_percent
        if self.metric == "remaining":
            return window.remaining_percent
        if self.metric == "reset":
            return window.reset_at
        if window.reset_at is None:
            return None
        return max(0, int((window.reset_at - datetime.now(UTC)).total_seconds()))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        window = self._window
        if window is None:
            return {}
        return {
            "window_id": window.id,
            "limit_name": window.limit_name,
            "window_seconds": window.duration_seconds,
            "allowed": window.allowed,
            "limit_reached": window.limit_reached,
        }


class ChatGPTLastUpdateSensor(ChatGPTUsageEntity, SensorEntity):
    _attr_name = "Last successful update"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:update"

    def __init__(self, coordinator: ChatGPTUsageCoordinator) -> None:
        super().__init__(coordinator)
        identifier = self._entry.unique_id or self._entry.entry_id
        self._attr_unique_id = f"{identifier}_last_successful_update"

    @property
    def available(self) -> bool:
        return self.coordinator.last_successful_update is not None

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.last_successful_update


class ChatGPTPlanSensor(ChatGPTUsageEntity, SensorEntity):
    _attr_name = "Plan"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:account-star-outline"

    def __init__(self, coordinator: ChatGPTUsageCoordinator) -> None:
        super().__init__(coordinator)
        identifier = self._entry.unique_id or self._entry.entry_id
        self._attr_unique_id = f"{identifier}_plan"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.plan if self.coordinator.data else None


class ChatGPTCreditBalanceSensor(ChatGPTUsageEntity, SensorEntity):
    _attr_name = "Credit balance"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:credit-card-outline"

    def __init__(self, coordinator: ChatGPTUsageCoordinator) -> None:
        super().__init__(coordinator)
        identifier = self._entry.unique_id or self._entry.entry_id
        self._attr_unique_id = f"{identifier}_credit_balance"

    @property
    def native_value(self) -> float | None:
        credits = self.coordinator.data.credits if self.coordinator.data else None
        return credits.balance if credits else None


class ChatGPTResetCreditsSensor(ChatGPTUsageEntity, SensorEntity):
    _attr_name = "Reset credits available"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:restore"

    def __init__(self, coordinator: ChatGPTUsageCoordinator) -> None:
        super().__init__(coordinator)
        identifier = self._entry.unique_id or self._entry.entry_id
        self._attr_unique_id = f"{identifier}_reset_credits_available"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.available_reset_credits if self.coordinator.data else None
