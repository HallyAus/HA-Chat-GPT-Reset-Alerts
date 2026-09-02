"""API providers for Claude Usage."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import time
from typing import Any, Protocol

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .const import (
    API_BETA_HEADER,
    CONF_ACCESS_TOKEN,
    CONF_ACCOUNT_ID,
    CONF_API_KEY,
    CONF_EXPIRES_AT,
    CONF_HOST,
    CONF_PORT,
    CONF_REFRESH_TOKEN,
    CONF_SUBSCRIPTION_LEVEL,
    CONF_USE_HTTPS,
    LOCAL_API_VERSION,
    LOCAL_HEALTH_PATH,
    LOCAL_USAGE_PATH,
    OAUTH_CLIENT_ID,
    OAUTH_TOKEN_URL,
    PROFILE_API_URL,
    USAGE_API_URL,
)
from .models import ClaudeUsageData, parse_anthropic_usage

_LOGGER = logging.getLogger(__name__)


class ClaudeUsageError(Exception):
    """Base integration API error."""


class ClaudeAuthError(ClaudeUsageError):
    """Authentication is invalid or expired."""


class ClaudeRateLimitError(ClaudeUsageError):
    """Anthropic has rate-limited the usage request."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ClaudeConnectionError(ClaudeUsageError):
    """Provider could not be reached."""


class ClaudePayloadError(ClaudeUsageError):
    """Provider response could not be safely parsed."""


class ClaudeUsageProvider(Protocol):
    """Common provider contract."""

    async def async_get_usage(self) -> ClaudeUsageData:
        """Return normalized Claude usage."""


async def async_exchange_oauth_code(
    hass: HomeAssistant,
    *,
    code: str,
    state: str,
    verifier: str,
    redirect_uri: str,
) -> dict[str, Any]:
    """Exchange an Anthropic authorization code for OAuth tokens."""
    session = aiohttp_client.async_get_clientsession(hass)
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "state": state,
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }
    try:
        async with asyncio.timeout(20):
            response = await session.post(OAUTH_TOKEN_URL, json=payload)
            if response.status >= 400:
                raise ClaudeAuthError(f"OAuth token exchange failed ({response.status})")
            data = await response.json()
    except (aiohttp.ClientError, TimeoutError) as err:
        raise ClaudeConnectionError("Unable to contact Anthropic OAuth service") from err
    if not isinstance(data, dict) or not data.get("access_token"):
        raise ClaudePayloadError("OAuth response did not contain an access token")
    return data


async def async_fetch_profile(hass: HomeAssistant, access_token: str) -> dict[str, Any]:
    """Fetch safe account metadata for title and deduplication."""
    session = aiohttp_client.async_get_clientsession(hass)
    try:
        async with asyncio.timeout(15):
            response = await session.get(
                PROFILE_API_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "anthropic-beta": API_BETA_HEADER,
                },
            )
            if response.status == 401:
                raise ClaudeAuthError("Anthropic rejected the OAuth token")
            if response.status >= 400:
                return {}
            data = await response.json()
    except (aiohttp.ClientError, TimeoutError) as err:
        raise ClaudeConnectionError("Unable to fetch Anthropic profile") from err
    return data if isinstance(data, dict) else {}


@dataclass(slots=True)
class RemoteAnthropicProvider:
    """Fetch subscription usage directly from Anthropic."""

    hass: HomeAssistant
    entry: ConfigEntry

    async def _async_refresh_token(self) -> None:
        refresh_token = self.entry.data.get(CONF_REFRESH_TOKEN)
        if not refresh_token:
            raise ClaudeAuthError("No OAuth refresh token is available")
        session = aiohttp_client.async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(20):
                response = await session.post(
                    OAUTH_TOKEN_URL,
                    json={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": OAUTH_CLIENT_ID,
                    },
                )
                if response.status in (400, 401, 403):
                    raise ClaudeAuthError("Anthropic OAuth refresh was rejected")
                if response.status >= 400:
                    raise ClaudeConnectionError(
                        f"Anthropic OAuth refresh failed ({response.status})"
                    )
                token_data = await response.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ClaudeConnectionError("Unable to refresh Anthropic OAuth token") from err

        new_token = token_data.get("access_token") if isinstance(token_data, dict) else None
        if not new_token:
            raise ClaudePayloadError("OAuth refresh response missing access_token")
        new_data = {
            **self.entry.data,
            CONF_ACCESS_TOKEN: new_token,
            CONF_REFRESH_TOKEN: token_data.get("refresh_token", refresh_token),
            CONF_EXPIRES_AT: time.time() + float(token_data.get("expires_in", 3600)),
        }
        self.hass.config_entries.async_update_entry(self.entry, data=new_data)

    async def _async_ensure_token(self) -> None:
        if time.time() < float(self.entry.data.get(CONF_EXPIRES_AT, 0)) - 60:
            return
        await self._async_refresh_token()

    async def async_get_usage(self) -> ClaudeUsageData:
        await self._async_ensure_token()
        access_token = self.entry.data.get(CONF_ACCESS_TOKEN)
        if not access_token:
            raise ClaudeAuthError("Missing Anthropic access token")
        session = aiohttp_client.async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(20):
                response = await session.get(
                    USAGE_API_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "anthropic-beta": API_BETA_HEADER,
                    },
                )
                if response.status == 401:
                    raise ClaudeAuthError("Anthropic authentication failed")
                if response.status == 429:
                    retry = response.headers.get("Retry-After")
                    raise ClaudeRateLimitError(
                        "Anthropic rate-limited usage polling",
                        int(retry) if retry and retry.isdigit() else None,
                    )
                if response.status >= 500:
                    raise ClaudeConnectionError(
                        f"Anthropic usage service returned {response.status}"
                    )
                if response.status >= 400:
                    raise ClaudeUsageError(
                        f"Anthropic usage request failed ({response.status})"
                    )
                raw = await response.json()
        except ClaudeUsageError:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ClaudeConnectionError("Unable to contact Anthropic usage service") from err

        if not isinstance(raw, dict):
            raise ClaudePayloadError("Anthropic usage response was not an object")
        return parse_anthropic_usage(
            raw,
            plan=self.entry.data.get(CONF_SUBSCRIPTION_LEVEL),
            account_id=self.entry.data.get(CONF_ACCOUNT_ID),
            source="remote",
        )


@dataclass(slots=True)
class LocalClaudeCodeProvider:
    """Fetch sanitized usage through the local Windows Claude helper."""

    hass: HomeAssistant
    entry: ConfigEntry

    def _value(self, key: str, default: Any = None) -> Any:
        return self.entry.options.get(key, self.entry.data.get(key, default))

    @property
    def _base_url(self) -> str:
        scheme = "https" if self._value(CONF_USE_HTTPS, False) else "http"
        return f"{scheme}://{self._value(CONF_HOST)}:{self._value(CONF_PORT)}"

    async def _async_request(self, path: str) -> dict[str, Any]:
        session = aiohttp_client.async_get_clientsession(self.hass)
        api_key = self._value(CONF_API_KEY)
        try:
            async with asyncio.timeout(15):
                response = await session.get(
                    f"{self._base_url}{path}",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if response.status in (401, 403):
                    raise ClaudeAuthError("Local helper API key was rejected")
                if response.status >= 500:
                    raise ClaudeConnectionError(
                        f"Local Claude helper reported an error ({response.status})"
                    )
                if response.status >= 400:
                    raise ClaudeUsageError(
                        f"Local Claude helper request failed ({response.status})"
                    )
                data = await response.json()
        except ClaudeUsageError:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ClaudeConnectionError("Unable to reach the local Claude helper") from err
        if not isinstance(data, dict):
            raise ClaudePayloadError("Local helper response was not an object")
        return data

    async def async_health(self) -> dict[str, Any]:
        data = await self._async_request(LOCAL_HEALTH_PATH)
        if data.get("api_version") != LOCAL_API_VERSION:
            raise ClaudePayloadError(
                f"Unsupported local helper API version: {data.get('api_version')}"
            )
        return data

    async def async_get_usage(self) -> ClaudeUsageData:
        data = await self._async_request(LOCAL_USAGE_PATH)
        if data.get("api_version") != LOCAL_API_VERSION:
            raise ClaudePayloadError(
                f"Unsupported local helper API version: {data.get('api_version')}"
            )
        raw = data.get("usage")
        if not isinstance(raw, dict):
            raise ClaudePayloadError("Local helper did not return a usage payload")
        return parse_anthropic_usage(
            raw,
            plan=data.get("subscription_level") if isinstance(data.get("subscription_level"), str) else None,
            account_id=None,
            source="local",
        )
