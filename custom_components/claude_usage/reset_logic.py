"""Pure reset detection logic for Claude usage windows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .models import UsageWindow


@dataclass(frozen=True, slots=True)
class WindowSnapshot:
    """Persistable subset of a usage window."""

    used_percent: float | None
    reset_at: datetime | None


def reset_detected(
    previous: WindowSnapshot,
    current: UsageWindow,
    *,
    now: datetime | None = None,
) -> bool:
    """Return True only when evidence strongly indicates a window rollover."""
    now = now or datetime.now(UTC)
    prev_reset = previous.reset_at
    new_reset = current.reset_at
    prev_used = previous.used_percent
    new_used = current.used_percent

    usage_drop = (
        prev_used is not None
        and new_used is not None
        and (prev_used - new_used) >= 20.0
    )

    if prev_reset is not None and new_reset is not None:
        reset_advanced = new_reset > prev_reset + timedelta(seconds=60)
        old_window_due = now >= prev_reset - timedelta(minutes=5)
        if reset_advanced and (old_window_due or usage_drop):
            return True

    # Fallback for upstream payloads temporarily omitting reset timestamps.
    return bool(
        prev_reset is None
        and new_reset is None
        and prev_used is not None
        and new_used is not None
        and prev_used >= 90.0
        and new_used <= 20.0
        and (prev_used - new_used) >= 60.0
    )
