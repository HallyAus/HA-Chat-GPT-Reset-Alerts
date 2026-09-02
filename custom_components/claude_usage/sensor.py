"""Sensor platform for Claude Usage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ClaudeUsageCoordinator
from .entity import ClaudeUsageEntity
from .models import UsageWindow


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up usage sensors and discover new dynamic buckets."""
    coordinator: ClaudeUsageCoordinator = entry.runtime_data
    seen: set[str] = set()

    static_entities: list[SensorEntity] = [
        ClaudePlanSensor(coordinator),
        ClaudeLastUpdateSensor(coordinator),
        ClaudeExtraUsageSensor(coordinator, "percent"),
        ClaudeExtraUsageSensor(coordinator, "used"),
        ClaudeExtraUsageSensor(coordinator, "remaining"),
        ClaudeExtraUsageSensor(coordinator, "limit"),
    ]
    async_add_entities(static_entities)

    @callback
    def discover_windows() -> None:
        if coordinator.data is None:
            return
        new_ids = [wid for wid in coordinator.data.windows if wid not in seen]
        if not new_ids:
            return
        entities: list[SensorEntity] = []
        for window_id in new_ids:
            seen.add(window_id)
            entities.extend(
                ClaudeWindowSensor(coordinator, window_id, metric)
                for metric in ("usage", "remaining", "reset", "time_remaining")
            )
        async_add_entities(entities)

    discover_windows()
    entry.async_on_unload(coordinator.async_add_listener(discover_windows))


class ClaudePlanSensor(ClaudeUsageEntity, SensorEntity):
    """Claude subscription plan."""

    _attr_name = "Plan"
    _attr_icon = "mdi:account-star"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ClaudeUsageCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_plan"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.plan if self.coordinator.data else None


class ClaudeLastUpdateSensor(ClaudeUsageEntity, SensorEntity):
    """Timestamp of the most recent successful provider response."""

    _attr_name = "Last update"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ClaudeUsageCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_last_update"

    @property
    def available(self) -> bool:
        return self.coordinator.data is not None

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.data.last_updated if self.coordinator.data else None


class ClaudeWindowSensor(ClaudeUsageEntity, SensorEntity):
    """One metric for a dynamic usage window."""

    def __init__(self, coordinator: ClaudeUsageCoordinator, window_id: str, metric: str) -> None:
        super().__init__(coordinator)
        self.window_id = window_id
        self.metric = metric
        initial = coordinator.data.windows.get(window_id) if coordinator.data else None
        label = initial.display_name if initial else window_id.replace("_", " ").title()
        names = {
            "usage": f"{label} usage",
            "remaining": f"{label} remaining",
            "reset": f"{label} reset",
            "time_remaining": f"{label} time remaining",
        }
        self._attr_name = names[metric]
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{window_id}_{metric}"
        if metric in ("usage", "remaining"):
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_icon = "mdi:chart-donut"
        elif metric == "reset":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
            self._attr_icon = "mdi:clock-refresh-outline"
        else:
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
            self._attr_icon = "mdi:timer-outline"

    @property
    def _window(self) -> UsageWindow | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.windows.get(self.window_id)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._window is not None

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
        return max(0, round((window.reset_at - datetime.now(UTC)).total_seconds()))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        window = self._window
        if window is None:
            return {}
        return {key: value for key, value in {
            "window_id": window.id,
            "kind": window.kind,
            "model": window.model,
            "surface": window.surface,
            "severity": window.severity,
            "is_active": window.is_active,
            "duration_seconds": window.duration_seconds,
        }.items() if value is not None}


class ClaudeExtraUsageSensor(ClaudeUsageEntity, SensorEntity):
    """Extra Usage spend metric."""

    def __init__(self, coordinator: ClaudeUsageCoordinator, metric: str) -> None:
        super().__init__(coordinator)
        self.metric = metric
        names = {
            "percent": "Extra Usage",
            "used": "Extra Usage spent",
            "remaining": "Extra Usage remaining",
            "limit": "Extra Usage limit",
        }
        self._attr_name = names[metric]
        self._attr_unique_id = f"{coordinator.entry.entry_id}_extra_{metric}"
        if metric == "percent":
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:credit-card-outline"

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None and self.coordinator.data.extra_usage is not None

    @property
    def native_value(self) -> float | None:
        extra = self.coordinator.data.extra_usage if self.coordinator.data else None
        if extra is None:
            return None
        if self.metric == "percent":
            return extra.percent
        if self.metric == "used":
            return extra.used
        if self.metric == "remaining":
            return extra.remaining
        return extra.limit

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        extra = self.coordinator.data.extra_usage if self.coordinator.data else None
        return {"currency": extra.currency} if extra and extra.currency else {}
