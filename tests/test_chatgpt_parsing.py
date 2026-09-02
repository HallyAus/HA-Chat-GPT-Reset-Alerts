import pytest

from custom_components.chatgpt_usage.parsing import UsageSchemaError, parse_helper_usage, parse_openai_usage


def _window(used, reset, seconds):
    return {
        "used_percent": used,
        "reset_at": reset,
        "limit_window_seconds": seconds,
    }


def test_parses_five_hour_and_weekly_by_duration_not_position():
    data = parse_openai_usage(
        {
            "plan_type": "pro",
            "rate_limit": {
                "primary_window": _window(22, 1_800_000_000, 604800),
                "secondary_window": _window(44, 1_799_000_000, 18000),
            },
        },
        account_id="acct",
    )
    assert data.plan == "pro"
    assert data.account_id == "acct"
    assert data.window("weekly").used_percent == 22
    assert data.window("five_hour").used_percent == 44
    assert data.window("five_hour").remaining_percent == 56


def test_additional_limit_is_dynamic_and_stable():
    data = parse_openai_usage(
        {
            "rate_limit": {
                "primary_window": _window(1, 1_800_000_000, 18000),
                "secondary_window": _window(2, 1_800_100_000, 604800),
            },
            "additional_rate_limits": [
                {
                    "metered_feature": "code_review",
                    "limit_name": "Code review",
                    "rate_limit": {
                        "primary_window": _window(30, 1_800_200_000, 86400)
                    },
                }
            ],
        }
    )
    extra = [w for w in data.windows if w.limit_name == "Code review"]
    assert len(extra) == 1
    assert extra[0].id.startswith("code_review_1d_")
    assert extra[0].remaining_percent == 70


def test_credits_and_reset_credits_are_read_only_metadata():
    data = parse_openai_usage(
        {
            "rate_limit": {"primary_window": _window(5, 1_800_000_000, 18000)},
            "credits": {"has_credits": True, "unlimited": False, "balance": 12.5},
            "rate_limit_reset_credits": {"available_count": 2, "credits": [{"secret": "ignored"}]},
        }
    )
    assert data.credits.has_credits is True
    assert data.credits.balance == 12.5
    assert data.available_reset_credits == 2


def test_helper_requires_version_and_usage_object():
    payload = {
        "api_version": 1,
        "account_id": "acct",
        "plan": "pro",
        "usage": {
            "rate_limit": {"primary_window": _window(5, 1_800_000_000, 18000)}
        },
    }
    data = parse_helper_usage(payload)
    assert data.source == "local"
    assert data.plan == "pro"
    assert data.account_id == "acct"


def test_missing_windows_raises_instead_of_faking_zero():
    with pytest.raises(UsageSchemaError):
        parse_openai_usage({"plan_type": "pro"})


def test_invalid_percent_window_is_ignored():
    with pytest.raises(UsageSchemaError):
        parse_openai_usage(
            {"rate_limit": {"primary_window": _window(150, 1_800_000_000, 18000)}}
        )
