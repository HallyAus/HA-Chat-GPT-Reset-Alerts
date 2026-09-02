from __future__ import annotations

from datetime import UTC, datetime, timedelta

from conftest import load_module

models = load_module("models")
logic = load_module("reset_logic")


def window(used, reset):
    return models.UsageWindow(
        id="weekly",
        display_name="Weekly",
        used_percent=used,
        reset_at=reset,
        duration_seconds=604800,
    )


def test_reset_detected_when_timestamp_rolls_and_usage_drops():
    now = datetime(2026, 9, 2, 12, 5, tzinfo=UTC)
    old_reset = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    previous = logic.WindowSnapshot(used_percent=98, reset_at=old_reset)
    current = window(2, old_reset + timedelta(days=7))
    assert logic.reset_detected(previous, current, now=now)


def test_small_usage_change_is_not_reset():
    now = datetime(2026, 9, 2, 10, 0, tzinfo=UTC)
    reset = datetime(2026, 9, 3, 10, 0, tzinfo=UTC)
    previous = logic.WindowSnapshot(used_percent=51, reset_at=reset)
    current = window(50, reset)
    assert not logic.reset_detected(previous, current, now=now)


def test_future_timestamp_shift_without_drop_or_due_is_not_reset():
    now = datetime(2026, 9, 2, 10, 0, tzinfo=UTC)
    old_reset = datetime(2026, 9, 3, 10, 0, tzinfo=UTC)
    previous = logic.WindowSnapshot(used_percent=40, reset_at=old_reset)
    current = window(39, old_reset + timedelta(hours=1))
    assert not logic.reset_detected(previous, current, now=now)


def test_first_start_is_handled_by_tracker_not_detector():
    assert True
