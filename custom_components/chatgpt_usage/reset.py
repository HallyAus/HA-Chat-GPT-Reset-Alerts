"""Conservative reset detection for ChatGPT usage windows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .models import PersistedWindowState, UsageWindow, parse_datetime


@dataclass(frozen=True, slots=True)
class ResetDetection:
    event_key: str
    confidence: str


def detect_reset(
    previous: PersistedWindowState,
    current: UsageWindow,
    now: datetime | None = None,
) -> ResetDetection | None:
    """Detect one real allowance rollover while avoiding startup/rounding noise."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    old_reset = parse_datetime(previous.reset_at)
    new_reset = current.reset_at
    old_used = previous.used_percent
    new_used = current.used_percent
    old_remaining = previous.remaining_percent
    new_remaining = current.remaining_percent

    reset_moved = bool(old_reset and new_reset and new_reset > old_reset + timedelta(minutes=1))
    old_window_due = bool(old_reset and now >= old_reset - timedelta(minutes=3))
    usage_drop = bool(
        old_used is not None and new_used is not None and old_used - new_used >= 20.0
    )
    remaining_jump = bool(
        old_remaining is not None
        and new_remaining is not None
        and new_remaining - old_remaining >= 20.0
    )
    very_strong_drop = bool(
        old_used is not None
        and new_used is not None
        and old_used >= 90.0
        and new_used <= 20.0
        and old_used - new_used >= 70.0
    )

    confidence: str | None = None
    if reset_moved and old_window_due:
        confidence = "timestamp_rollover"
    elif reset_moved and (usage_drop or remaining_jump):
        confidence = "timestamp_and_usage"
    elif old_reset is None and new_reset is None and very_strong_drop:
        confidence = "strong_usage_fallback"

    if confidence is None:
        return None
    basis = new_reset.isoformat() if new_reset else f"{now:%Y%m%d%H}"
    event_key = f"{current.id}:{basis}"
    if previous.last_event_key == event_key:
        return None
    return ResetDetection(event_key=event_key, confidence=confidence)
