"""Normalized Claude usage models and Anthropic payload parsing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import re
from typing import Any


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return value or "unknown"


def parse_datetime(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp or epoch seconds into an aware datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class UsageWindow:
    """One Claude subscription usage window."""

    id: str
    display_name: str
    used_percent: float | None
    reset_at: datetime | None
    duration_seconds: int | None = None
    kind: str | None = None
    model: str | None = None
    surface: str | None = None
    severity: str | None = None
    is_active: bool | None = None

    @property
    def remaining_percent(self) -> float | None:
        if self.used_percent is None:
            return None
        return round(max(0.0, 100.0 - self.used_percent), 3)


@dataclass(frozen=True, slots=True)
class ExtraUsage:
    """Claude Extra Usage / spend information."""

    enabled: bool
    used: float | None = None
    limit: float | None = None
    percent: float | None = None
    currency: str | None = None

    @property
    def remaining(self) -> float | None:
        if self.used is None or self.limit is None:
            return None
        return max(0.0, self.limit - self.used)


@dataclass(frozen=True, slots=True)
class ClaudeUsageData:
    """Normalized state returned by every provider."""

    windows: dict[str, UsageWindow] = field(default_factory=dict)
    extra_usage: ExtraUsage | None = None
    plan: str | None = None
    account_id: str | None = None
    source: str = "unknown"
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))


def _legacy_window(
    payload: dict[str, Any] | None,
    *,
    window_id: str,
    display_name: str,
    duration_seconds: int,
    kind: str,
    model: str | None = None,
) -> UsageWindow | None:
    if not isinstance(payload, dict):
        return None
    used = _number(payload.get("utilization"))
    reset_at = parse_datetime(payload.get("resets_at"))
    if used is None and reset_at is None:
        return None
    return UsageWindow(
        id=window_id,
        display_name=display_name,
        used_percent=used,
        reset_at=reset_at,
        duration_seconds=duration_seconds,
        kind=kind,
        model=model,
        is_active=True,
    )


def _limit_window(entry: dict[str, Any]) -> UsageWindow | None:
    kind = entry.get("kind")
    if not isinstance(kind, str) or not kind:
        return None
    scope = entry.get("scope") if isinstance(entry.get("scope"), dict) else {}
    model_obj = scope.get("model") if isinstance(scope.get("model"), dict) else {}
    model = model_obj.get("display_name") if isinstance(model_obj.get("display_name"), str) else None
    model_id = model_obj.get("id") if isinstance(model_obj.get("id"), str) else None
    surface = scope.get("surface") if isinstance(scope.get("surface"), str) else None

    if kind == "session":
        window_id = "session"
        display = "5 hour"
        duration = 5 * 60 * 60
    elif kind == "weekly_all":
        window_id = "weekly"
        display = "Weekly"
        duration = 7 * 24 * 60 * 60
    elif kind == "weekly_scoped":
        scope_name = model or model_id or "scoped"
        parts = ["weekly", _slug(scope_name)]
        if surface:
            parts.append(_slug(surface))
        window_id = "_".join(parts)
        display = f"Weekly {scope_name}"
        if surface:
            display += f" ({surface})"
        duration = 7 * 24 * 60 * 60
    else:
        parts = [_slug(kind)]
        if model or model_id:
            parts.append(_slug(model or model_id or "model"))
        if surface:
            parts.append(_slug(surface))
        window_id = "_".join(parts)
        display = kind.replace("_", " ").title()
        if model:
            display += f" {model}"
        if surface:
            display += f" ({surface})"
        duration = None

    used = _number(entry.get("percent"))
    if used is None:
        used = _number(entry.get("utilization"))
    reset_at = parse_datetime(entry.get("resets_at"))
    if used is None and reset_at is None:
        return None

    return UsageWindow(
        id=window_id,
        display_name=display,
        used_percent=used,
        reset_at=reset_at,
        duration_seconds=duration,
        kind=kind,
        model=model,
        surface=surface,
        severity=entry.get("severity") if isinstance(entry.get("severity"), str) else None,
        is_active=entry.get("is_active") if isinstance(entry.get("is_active"), bool) else None,
    )


def _parse_extra_usage(raw: dict[str, Any]) -> ExtraUsage | None:
    extra = raw.get("extra_usage")
    if isinstance(extra, dict):
        enabled = bool(extra.get("is_enabled"))
        divisor = 10 ** int(extra.get("decimal_places", 2) or 2)
        used_minor = _number(extra.get("used_credits"))
        limit_minor = _number(extra.get("monthly_limit"))
        return ExtraUsage(
            enabled=enabled,
            used=used_minor / divisor if used_minor is not None else None,
            limit=limit_minor / divisor if limit_minor is not None else None,
            percent=_number(extra.get("utilization")),
            currency=extra.get("currency") if isinstance(extra.get("currency"), str) else None,
        )

    spend = raw.get("spend")
    if isinstance(spend, dict):
        enabled = bool(spend.get("enabled"))
        used_obj = spend.get("used") if isinstance(spend.get("used"), dict) else {}
        limit_obj = spend.get("limit") if isinstance(spend.get("limit"), dict) else {}

        def money(obj: dict[str, Any]) -> float | None:
            amount = _number(obj.get("amount_minor"))
            if amount is None:
                return None
            exponent = int(obj.get("exponent", 2) or 2)
            return amount / (10**exponent)

        currency = used_obj.get("currency") or limit_obj.get("currency")
        return ExtraUsage(
            enabled=enabled,
            used=money(used_obj),
            limit=money(limit_obj),
            percent=_number(spend.get("percent")),
            currency=currency if isinstance(currency, str) else None,
        )
    return None


def parse_anthropic_usage(
    raw: dict[str, Any],
    *,
    plan: str | None = None,
    account_id: str | None = None,
    source: str = "remote",
) -> ClaudeUsageData:
    """Normalize the current Anthropic OAuth usage response."""
    windows: dict[str, UsageWindow] = {}

    legacy = [
        _legacy_window(
            raw.get("five_hour"),
            window_id="session",
            display_name="5 hour",
            duration_seconds=5 * 60 * 60,
            kind="session",
        ),
        _legacy_window(
            raw.get("seven_day"),
            window_id="weekly",
            display_name="Weekly",
            duration_seconds=7 * 24 * 60 * 60,
            kind="weekly_all",
        ),
        _legacy_window(
            raw.get("seven_day_sonnet"),
            window_id="weekly_sonnet",
            display_name="Weekly Sonnet",
            duration_seconds=7 * 24 * 60 * 60,
            kind="weekly_scoped",
            model="Sonnet",
        ),
    ]
    for window in legacy:
        if window is not None:
            windows[window.id] = window

    limits = raw.get("limits")
    if isinstance(limits, list):
        for item in limits:
            if not isinstance(item, dict):
                continue
            window = _limit_window(item)
            if window is not None:
                windows[window.id] = window

    return ClaudeUsageData(
        windows=windows,
        extra_usage=_parse_extra_usage(raw),
        plan=plan,
        account_id=account_id,
        source=source,
        last_updated=datetime.now(UTC),
    )
