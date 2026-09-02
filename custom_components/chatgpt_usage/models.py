"""Normalized data models for ChatGPT/Codex usage."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class UsageWindow:
    """One usage allowance window."""

    id: str
    display_name: str
    used_percent: float | None = None
    remaining_percent: float | None = None
    reset_at: datetime | None = None
    duration_seconds: int | None = None
    limit_name: str = "Codex"
    kind: str = "usage"
    allowed: bool | None = None
    limit_reached: bool | None = None

    def to_safe_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reset_at"] = self.reset_at.isoformat() if self.reset_at else None
        return data


@dataclass(frozen=True, slots=True)
class CreditStatus:
    """Read-only credit information returned by the usage endpoint."""

    has_credits: bool = False
    unlimited: bool = False
    balance: float | None = None
    overage_limit_reached: bool | None = None


@dataclass(frozen=True, slots=True)
class ChatGPTUsageData:
    """Normalized provider response."""

    windows: tuple[UsageWindow, ...] = field(default_factory=tuple)
    plan: str | None = None
    account_id: str | None = None
    source: str = "unknown"
    credits: CreditStatus | None = None
    available_reset_credits: int | None = None
    blocker_reason: str | None = None
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))

    def window(self, window_id: str) -> UsageWindow | None:
        return next((window for window in self.windows if window.id == window_id), None)


@dataclass(slots=True)
class PersistedWindowState:
    """Minimal non-sensitive reset state."""

    reset_at: str | None = None
    used_percent: float | None = None
    remaining_percent: float | None = None
    last_event_key: str | None = None

    @classmethod
    def from_window(
        cls, window: UsageWindow, last_event_key: str | None = None
    ) -> "PersistedWindowState":
        return cls(
            reset_at=window.reset_at.isoformat() if window.reset_at else None,
            used_percent=window.used_percent,
            remaining_percent=window.remaining_percent,
            last_event_key=last_event_key,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PersistedWindowState":
        return cls(
            reset_at=data.get("reset_at"),
            used_percent=to_float(data.get("used_percent")),
            remaining_percent=to_float(data.get("remaining_percent")),
            last_event_key=data.get("last_event_key"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "reset_at": self.reset_at,
            "used_percent": self.used_percent,
            "remaining_percent": self.remaining_percent,
            "last_event_key": self.last_event_key,
        }


def parse_datetime(value: Any) -> datetime | None:
    """Parse ISO or epoch timestamps into aware UTC datetimes."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (ValueError, OSError, OverflowError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        if text.replace(".", "", 1).isdigit():
            return datetime.fromtimestamp(float(text), tz=UTC)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, OSError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def clamp_percent(value: Any) -> float | None:
    number = to_float(value)
    if number is None or number < 0 or number > 100:
        return None
    return round(number, 2)


def remaining_from_used(used: float | None) -> float | None:
    return None if used is None else round(max(0.0, 100.0 - used), 2)


def to_float(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
