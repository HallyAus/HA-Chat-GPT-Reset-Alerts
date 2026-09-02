"""Defensive parsing for OpenAI Codex usage payloads."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from .models import (
    ChatGPTUsageData,
    CreditStatus,
    UsageWindow,
    clamp_percent,
    parse_datetime,
    remaining_from_used,
    to_float,
)


class UsageSchemaError(ValueError):
    """The provider payload is not usable."""


def parse_openai_usage(
    raw: Any,
    *,
    account_id: str | None = None,
    source: str = "remote",
) -> ChatGPTUsageData:
    """Normalize the current wham/usage schema without trusting unknown fields."""
    if not isinstance(raw, dict):
        raise UsageSchemaError("OpenAI usage response was not an object")

    windows: list[UsageWindow] = []
    main = raw.get("rate_limit")
    if isinstance(main, dict):
        windows.extend(_parse_limit_windows("codex", "Codex", main, main_limit=True))

    additional = raw.get("additional_rate_limits")
    if isinstance(additional, list):
        for index, item in enumerate(additional[:50]):
            if not isinstance(item, dict):
                continue
            limit_id = _safe_text(item.get("metered_feature"), 80) or _safe_text(
                item.get("limit_name"), 80
            ) or f"additional_{index + 1}"
            name = _safe_text(item.get("limit_name"), 120) or limit_id.replace("_", " ").title()
            rate_limit = item.get("rate_limit")
            if isinstance(rate_limit, dict):
                windows.extend(_parse_limit_windows(limit_id, name, rate_limit, main_limit=False))

    legacy_review = raw.get("code_review_rate_limit")
    if isinstance(legacy_review, dict):
        detail = legacy_review.get("rate_limit", legacy_review)
        if isinstance(detail, dict):
            windows.extend(_parse_limit_windows("code_review", "Code review", detail, False))

    if not windows:
        raise UsageSchemaError("OpenAI usage response contained no usable rate-limit windows")

    credits = None
    credits_raw = raw.get("credits")
    if isinstance(credits_raw, dict):
        credits = CreditStatus(
            has_credits=bool(credits_raw.get("has_credits", False)),
            unlimited=bool(credits_raw.get("unlimited", False)),
            balance=to_float(credits_raw.get("balance")),
            overage_limit_reached=(
                credits_raw.get("overage_limit_reached")
                if isinstance(credits_raw.get("overage_limit_reached"), bool)
                else None
            ),
        )

    reset_count = None
    reset_raw = raw.get("rate_limit_reset_credits")
    if isinstance(reset_raw, dict):
        value = reset_raw.get("available_count")
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            reset_count = value

    blocker_reason = _parse_blocker(raw)
    plan = _safe_text(raw.get("plan_type"), 80)

    return ChatGPTUsageData(
        windows=tuple(_dedupe_windows(windows)),
        plan=plan,
        account_id=account_id,
        source=source,
        credits=credits,
        available_reset_credits=reset_count,
        blocker_reason=blocker_reason,
        last_updated=datetime.now(UTC),
    )


def parse_app_server_rate_limits(
    raw: Any,
    *,
    plan: str | None = None,
    account_id: str | None = None,
) -> ChatGPTUsageData:
    """Normalize the official Codex app-server account/rateLimits/read response."""
    if not isinstance(raw, dict):
        raise UsageSchemaError("Codex app-server rate-limit response was not an object")

    windows: list[UsageWindow] = []
    main = raw.get("rateLimits") or raw.get("rate_limits")
    if isinstance(main, dict):
        windows.extend(_parse_app_snapshot("codex", "Codex", main, main_limit=True))

    many = raw.get("rateLimitsByLimitId") or raw.get("rate_limits_by_limit_id")
    if isinstance(many, dict):
        for key, snapshot in list(many.items())[:50]:
            if not isinstance(snapshot, dict):
                continue
            limit_id = _safe_text(snapshot.get("limitId"), 80) or _safe_text(key, 80) or "additional"
            if _slug(limit_id) == "codex" and isinstance(main, dict):
                continue
            name = _safe_text(snapshot.get("limitName"), 120) or limit_id.replace("_", " ").title()
            windows.extend(_parse_app_snapshot(limit_id, name, snapshot, main_limit=False))

    if not windows:
        raise UsageSchemaError("Codex app-server returned no usable rate-limit windows")

    credits = _parse_app_credits(main) if isinstance(main, dict) else None
    reset_count = None
    reset_raw = raw.get("rateLimitResetCredits") or raw.get("rate_limit_reset_credits")
    if isinstance(reset_raw, dict):
        value = reset_raw.get("availableCount", reset_raw.get("available_count"))
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            reset_count = value

    app_plan = _safe_text(plan, 80)
    if app_plan is None and isinstance(main, dict):
        app_plan = _safe_text(main.get("planType") or main.get("plan_type"), 80)

    blocker = None
    if isinstance(main, dict) and main.get("rateLimitReachedType") is not None:
        blocker = "usage_limit"

    return ChatGPTUsageData(
        windows=tuple(_dedupe_windows(windows)),
        plan=app_plan,
        account_id=account_id or _safe_text(raw.get("accountId") or raw.get("account_id"), 160),
        source="local",
        credits=credits,
        available_reset_credits=reset_count,
        blocker_reason=blocker,
        last_updated=datetime.now(UTC),
    )


def parse_helper_usage(raw: Any) -> ChatGPTUsageData:
    """Parse the versioned local-helper response."""
    if not isinstance(raw, dict):
        raise UsageSchemaError("Local helper returned invalid JSON")
    if raw.get("api_version") != 1:
        raise UsageSchemaError("Unsupported local helper API version")

    app_result = raw.get("app_server_result")
    if isinstance(app_result, dict):
        return parse_app_server_rate_limits(
            app_result,
            plan=_safe_text(raw.get("plan"), 80),
            account_id=_safe_text(raw.get("account_id"), 160),
        )

    # Backward compatibility with v0.1 helpers that proxied a sanitized WHAM payload.
    usage = raw.get("usage")
    if not isinstance(usage, dict):
        raise UsageSchemaError("Local helper response omitted usage data")
    data = parse_openai_usage(
        usage,
        account_id=_safe_text(raw.get("account_id"), 160),
        source="local",
    )
    plan = _safe_text(raw.get("plan"), 80) or data.plan
    return ChatGPTUsageData(
        windows=data.windows,
        plan=plan,
        account_id=data.account_id,
        source="local",
        credits=data.credits,
        available_reset_credits=data.available_reset_credits,
        blocker_reason=data.blocker_reason,
        last_updated=datetime.now(UTC),
    )


def _parse_limit_windows(
    limit_id: str,
    name: str,
    payload: dict[str, Any],
    main_limit: bool,
) -> list[UsageWindow]:
    windows: list[UsageWindow] = []
    allowed = payload.get("allowed") if isinstance(payload.get("allowed"), bool) else None
    reached = payload.get("limit_reached") if isinstance(payload.get("limit_reached"), bool) else None
    if allowed is False:
        reached = True

    for position in ("primary", "secondary"):
        raw_window = payload.get(f"{position}_window")
        window = _parse_window(raw_window)
        if window is None:
            continue
        duration_key, duration_label = _duration_identity(window[2])
        if main_limit and duration_key in ("five_hour", "weekly"):
            window_id = duration_key
            display_name = "5 hour" if duration_key == "five_hour" else "Weekly"
        else:
            clean_limit = _slug(limit_id) or "additional"
            window_id = f"{clean_limit}_{duration_key}_{position}"
            display_name = f"{name} {duration_label}"
        windows.append(
            UsageWindow(
                id=window_id,
                display_name=display_name,
                used_percent=window[0],
                remaining_percent=remaining_from_used(window[0]),
                reset_at=window[1],
                duration_seconds=window[2],
                limit_name=name,
                kind="usage",
                allowed=allowed,
                limit_reached=reached,
            )
        )
    return windows


def _parse_app_snapshot(
    limit_id: str,
    name: str,
    snapshot: dict[str, Any],
    main_limit: bool,
) -> list[UsageWindow]:
    windows: list[UsageWindow] = []
    reached = snapshot.get("rateLimitReachedType") is not None
    for position in ("primary", "secondary"):
        raw = snapshot.get(position)
        if not isinstance(raw, dict):
            continue
        used = clamp_percent(raw.get("usedPercent", raw.get("used_percent")))
        if used is None:
            continue
        minutes = _positive_int(raw.get("windowDurationMins", raw.get("window_minutes")))
        seconds = minutes * 60 if minutes is not None else None
        reset = parse_datetime(raw.get("resetsAt", raw.get("resets_at")))
        duration_key, duration_label = _duration_identity(seconds)
        if main_limit and duration_key in ("five_hour", "weekly"):
            window_id = duration_key
            display_name = "5 hour" if duration_key == "five_hour" else "Weekly"
        else:
            clean_limit = _slug(limit_id) or "additional"
            window_id = f"{clean_limit}_{duration_key}_{position}"
            display_name = f"{name} {duration_label}"
        windows.append(
            UsageWindow(
                id=window_id,
                display_name=display_name,
                used_percent=used,
                remaining_percent=remaining_from_used(used),
                reset_at=reset,
                duration_seconds=seconds,
                limit_name=name,
                kind="usage",
                allowed=None,
                limit_reached=reached if reached else None,
            )
        )
    return windows


def _parse_app_credits(snapshot: dict[str, Any]) -> CreditStatus | None:
    raw = snapshot.get("credits")
    if not isinstance(raw, dict):
        return None
    return CreditStatus(
        has_credits=bool(raw.get("hasCredits", raw.get("has_credits", False))),
        unlimited=bool(raw.get("unlimited", False)),
        balance=to_float(raw.get("balance")),
        overage_limit_reached=None,
    )


def _parse_window(raw: Any) -> tuple[float, datetime | None, int | None] | None:
    if not isinstance(raw, dict):
        return None
    used = clamp_percent(raw.get("used_percent"))
    if used is None:
        return None
    seconds = _positive_int(raw.get("limit_window_seconds"))
    reset = parse_datetime(raw.get("reset_at"))
    if reset is None:
        after = to_float(raw.get("reset_after_seconds"))
        if after is not None and 0 <= after <= 10 * 365 * 24 * 3600:
            reset = datetime.now(UTC) + timedelta(seconds=after)
    return used, reset, seconds


def _duration_identity(seconds: int | None) -> tuple[str, str]:
    if seconds is None:
        return "unknown", "window"
    if 17100 <= seconds <= 18900:
        return "five_hour", "5 hour"
    if 574560 <= seconds <= 635040:
        return "weekly", "Weekly"
    if seconds % 86400 == 0:
        days = seconds // 86400
        return f"{days}d", f"{days} day"
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return f"{hours}h", f"{hours} hour"
    minutes = max(1, round(seconds / 60))
    return f"{minutes}m", f"{minutes} minute"


def _parse_blocker(raw: dict[str, Any]) -> str | None:
    value = raw.get("rate_limit_reached_type")
    if isinstance(value, dict):
        value = value.get("type")
    if not isinstance(value, str):
        return None
    normalized = value.casefold()
    if "spend" in normalized:
        return "spend"
    if "credit" in normalized:
        return "credits"
    if "usage" in normalized or "rate_limit" in normalized or "rate-limit" in normalized:
        return "usage_limit"
    return "unknown"


def _dedupe_windows(windows: list[UsageWindow]) -> list[UsageWindow]:
    seen: set[str] = set()
    result: list[UsageWindow] = []
    for window in windows:
        if window.id in seen:
            continue
        seen.add(window.id)
        result.append(window)
    return result


def _safe_text(value: Any, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if text and len(text) <= max_length else None


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
