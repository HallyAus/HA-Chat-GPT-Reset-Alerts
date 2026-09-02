from __future__ import annotations

from conftest import load_module

models = load_module("models")


def test_parses_legacy_windows():
    data = models.parse_anthropic_usage(
        {
            "five_hour": {"utilization": 82, "resets_at": "2026-09-02T14:32:00Z"},
            "seven_day": {"utilization": 91, "resets_at": "2026-09-07T08:14:00Z"},
        }
    )
    assert data.windows["session"].used_percent == 82
    assert data.windows["session"].remaining_percent == 18
    assert data.windows["weekly"].used_percent == 91
    assert data.windows["weekly"].remaining_percent == 9


def test_limits_override_legacy_and_dynamic_model_is_added():
    data = models.parse_anthropic_usage(
        {
            "five_hour": {"utilization": 10, "resets_at": "2026-09-02T14:00:00Z"},
            "limits": [
                {
                    "kind": "session",
                    "percent": 12,
                    "resets_at": "2026-09-02T15:00:00Z",
                    "is_active": True,
                    "scope": {},
                },
                {
                    "kind": "weekly_scoped",
                    "percent": 77,
                    "resets_at": "2026-09-07T08:00:00Z",
                    "scope": {"model": {"display_name": "Opus 4.1"}},
                },
            ],
        }
    )
    assert data.windows["session"].used_percent == 12
    assert data.windows["weekly_opus_4_1"].used_percent == 77
    assert data.windows["weekly_opus_4_1"].model == "Opus 4.1"


def test_spend_schema():
    data = models.parse_anthropic_usage(
        {
            "spend": {
                "enabled": True,
                "percent": 25,
                "used": {"amount_minor": 2500, "currency": "USD", "exponent": 2},
                "limit": {"amount_minor": 10000, "currency": "USD", "exponent": 2},
            }
        }
    )
    assert data.extra_usage is not None
    assert data.extra_usage.enabled is True
    assert data.extra_usage.used == 25
    assert data.extra_usage.limit == 100
    assert data.extra_usage.remaining == 75
