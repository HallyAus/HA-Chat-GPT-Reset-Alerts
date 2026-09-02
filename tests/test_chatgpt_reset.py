from datetime import UTC, datetime, timedelta

from custom_components.chatgpt_usage.models import PersistedWindowState, UsageWindow
from custom_components.chatgpt_usage.reset import detect_reset


def _current(used, reset):
    return UsageWindow(
        id="weekly",
        display_name="Weekly",
        used_percent=used,
        remaining_percent=100 - used,
        reset_at=reset,
        duration_seconds=604800,
    )


def test_reset_detected_after_timestamp_rollover():
    now = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    previous = PersistedWindowState(
        reset_at=(now - timedelta(minutes=5)).isoformat(),
        used_percent=98,
        remaining_percent=2,
    )
    result = detect_reset(previous, _current(2, now + timedelta(days=7)), now)
    assert result is not None
    assert result.confidence == "timestamp_rollover"


def test_reset_detected_if_timestamp_moves_and_usage_drops_early():
    now = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    old_reset = now + timedelta(hours=2)
    previous = PersistedWindowState(
        reset_at=old_reset.isoformat(), used_percent=95, remaining_percent=5
    )
    result = detect_reset(previous, _current(3, old_reset + timedelta(days=7)), now)
    assert result is not None
    assert result.confidence == "timestamp_and_usage"


def test_rounding_change_is_not_reset():
    now = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    reset = now + timedelta(days=2)
    previous = PersistedWindowState(reset_at=reset.isoformat(), used_percent=51, remaining_percent=49)
    assert detect_reset(previous, _current(50, reset), now) is None


def test_same_event_key_is_not_emitted_twice():
    now = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    new_reset = now + timedelta(days=7)
    previous = PersistedWindowState(
        reset_at=(now - timedelta(minutes=1)).isoformat(),
        used_percent=100,
        remaining_percent=0,
        last_event_key=f"weekly:{new_reset.isoformat()}",
    )
    assert detect_reset(previous, _current(0, new_reset), now) is None


def test_no_false_event_without_previous_state_is_enforced_by_coordinator_pattern():
    now = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    current = _current(10, now + timedelta(days=7))
    previous = PersistedWindowState.from_window(current)
    assert detect_reset(previous, current, now) is None
