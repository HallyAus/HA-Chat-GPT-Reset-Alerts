"""Remote OpenAI and local Codex usage providers."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .const import (
    ACCOUNTS_API_URL,
    CONF_ACCESS_TOKEN,
    CONF_ACCOUNT_ID,
    CONF_API_KEY,
    CONF_EXPIRES_AT,
    CONF_FEDRAMP,
    CONF_HOST,
    CONF_ID_TOKEN,
    CONF_PLAN_TYPE,
    CONF_PORT,
    CONF_REFRESH_TOKEN,
    CONF_USE_HTTPS,
    CONF_USER_ID,
    DEVICE_CODE_URL,
    DEVICE_TOKEN_URL,
    DEVICE_VERIFICATION_URL,
    LOCAL_API_VERSION,
    LOCAL_HEALTH_PATH,
    LOCAL_USAGE_PATH,
    OAUTH_CLIENT_ID,
    OAUTH_DEVICE_REDIRECT_URI,
    OAUTH_TOKEN_URL,
    PROVIDER_REMOTE,
    REQUEST_TIMEOUT_SECONDS,
    USAGE_API_URL,
    USER_AGENT,
)
from .models import ChatGPTUsageData
from .parsing import UsageSchemaError, parse_helper_usage, parse_openai_usage


class ProviderError(Exception):
    """Base provider error."""


class ProviderAuthError(ProviderError):
    """Authentication failed."""


class ProviderConnectionError(ProviderError):
    """Provider could not be reached."""


class ProviderSchemaError(ProviderError):
    """Provider returned an unsupported payload."""


class ProviderRateLimited(ProviderError):
    """Provider rate limited requests."""

    def __init__(self, retry_after: int | None = None) -> None:
        super().__init__("OpenAI rate limited the usage request")
        self.retry_after = retry_after


class DeviceAuthorizationPending(ProviderError):
    """Device authorization has not been completed yet."""


class DeviceAuthorizationUnavailable(ProviderError):
    """Device authorization is disabled."""


@dataclass(frozen=True, slots=True)
class DeviceCode:
    device_auth_id: str
    user_code: str
    interval: int
    verification_url: str = DEVICE_VERIFICATION_URL


@dataclass(frozen=True, slots=True)
class OpenAICredentials:
    access_token: str
    refresh_token: str
    id_token: str
    expires_at: float
    account_id: str
    user_id: str | None = None
    plan_type: str | None = None
    fedramp: bool = False


@dataclass(frozen=True, slots=True)
class AvailableAccount:
    account_id: str
    name: str | None = None
    structure: str | None = None


class UsageProvider(Protocol):
    async def async_get_usage(self) -> ChatGPTUsageData: ...
    async def async_close(self) -> None: ...


def credentials_from_entry(entry: ConfigEntry) -> OpenAICredentials:
    return OpenAICredentials(
        access_token=str(entry.data.get(CONF_ACCESS_TOKEN) or ""),
        refresh_token=str(entry.data.get(CONF_REFRESH_TOKEN) or ""),
        id_token=str(entry.data.get(CONF_ID_TOKEN) or ""),
        expires_at=float(entry.data.get(CONF_EXPIRES_AT) or 0),
        account_id=str(entry.data.get(CONF_ACCOUNT_ID) or ""),
        user_id=entry.data.get(CONF_USER_ID),
        plan_type=entry.data.get(CONF_PLAN_TYPE),
        fedramp=bool(entry.data.get(CONF_FEDRAMP, False)),
    )


def credentials_to_entry_data(credentials: OpenAICredentials) -> dict[str, Any]:
    return {
        CONF_ACCESS_TOKEN: credentials.access_token,
        CONF_REFRESH_TOKEN: credentials.refresh_token,
        CONF_ID_TOKEN: credentials.id_token,
        CONF_EXPIRES_AT: credentials.expires_at,
        CONF_ACCOUNT_ID: credentials.account_id,
        CONF_USER_ID: credentials.user_id,
        CONF_PLAN_TYPE: credentials.plan_type,
        CONF_FEDRAMP: credentials.fedramp,
    }


def credentials_from_token_response(
    payload: Any,
    previous: OpenAICredentials | None = None,
) -> OpenAICredentials:
    if not isinstance(payload, dict):
        raise ProviderAuthError("OpenAI returned an invalid token response")
    access = payload.get("access_token") or (previous.access_token if previous else None)
    refresh = payload.get("refresh_token") or (previous.refresh_token if previous else None)
    id_token = payload.get("id_token") or (previous.id_token if previous else None)
    if not all(isinstance(value, str) and value for value in (access, refresh, id_token)):
        raise ProviderAuthError("OpenAI returned incomplete OAuth credentials")
    claims = _claims_from_tokens(id_token, access)
    return OpenAICredentials(
        access_token=access,
        refresh_token=refresh,
        id_token=id_token,
        expires_at=claims["expires_at"],
        account_id=previous.account_id if previous else claims["account_id"],
        user_id=claims.get("user_id") or (previous.user_id if previous else None),
        plan_type=claims.get("plan_type"),
        fedramp=bool(claims.get("fedramp", False)),
    )


class OpenAIAuthClient:
    """Device OAuth and read-only OpenAI API operations."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session

    async def async_request_device_code(self) -> DeviceCode:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                response = await self.session.post(
                    DEVICE_CODE_URL,
                    json={"client_id": OAUTH_CLIENT_ID},
                    headers={"User-Agent": USER_AGENT},
                    allow_redirects=False,
                )
                if response.status in (403, 404):
                    raise DeviceAuthorizationUnavailable
                if response.status >= 400:
                    raise ProviderError(f"Device authorization failed ({response.status})")
                payload = await response.json(content_type=None)
        except DeviceAuthorizationUnavailable:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ProviderConnectionError("Could not start OpenAI device login") from err
        try:
            return DeviceCode(
                device_auth_id=str(payload["device_auth_id"]),
                user_code=str(payload.get("user_code") or payload["usercode"]),
                interval=max(1, int(payload.get("interval", 5))),
            )
        except (KeyError, TypeError, ValueError) as err:
            raise ProviderSchemaError("OpenAI returned an invalid device-code response") from err

    async def async_poll_device_code(self, code: DeviceCode) -> dict[str, str]:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                response = await self.session.post(
                    DEVICE_TOKEN_URL,
                    json={"device_auth_id": code.device_auth_id, "user_code": code.user_code},
                    headers={"User-Agent": USER_AGENT},
                    allow_redirects=False,
                )
                if response.status in (403, 404):
                    raise DeviceAuthorizationPending
                if response.status >= 400:
                    raise ProviderAuthError(f"Device authorization failed ({response.status})")
                payload = await response.json(content_type=None)
        except (DeviceAuthorizationPending, ProviderAuthError):
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ProviderConnectionError("Could not complete OpenAI device login") from err
        if not isinstance(payload, dict) or not payload.get("authorization_code") or not payload.get("code_verifier"):
            raise ProviderSchemaError("OpenAI returned an invalid authorization response")
        return {
            "authorization_code": str(payload["authorization_code"]),
            "code_verifier": str(payload["code_verifier"]),
        }

    async def async_exchange_device_code(self, payload: dict[str, str]) -> OpenAICredentials:
        data = {
            "grant_type": "authorization_code",
            "code": payload["authorization_code"],
            "redirect_uri": OAUTH_DEVICE_REDIRECT_URI,
            "client_id": OAUTH_CLIENT_ID,
            "code_verifier": payload["code_verifier"],
        }
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                response = await self.session.post(
                    OAUTH_TOKEN_URL,
                    data=data,
                    headers={"User-Agent": USER_AGENT},
                    allow_redirects=False,
                )
                if response.status >= 400:
                    raise ProviderAuthError(f"Token exchange failed ({response.status})")
                token_payload = await response.json(content_type=None)
        except ProviderAuthError:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ProviderConnectionError("Could not exchange OpenAI device token") from err
        return credentials_from_token_response(token_payload)

    async def async_refresh(self, credentials: OpenAICredentials) -> OpenAICredentials:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                response = await self.session.post(
                    OAUTH_TOKEN_URL,
                    json={
                        "client_id": OAUTH_CLIENT_ID,
                        "grant_type": "refresh_token",
                        "refresh_token": credentials.refresh_token,
                    },
                    headers={"User-Agent": USER_AGENT},
                    allow_redirects=False,
                )
                if response.status in (400, 401, 403):
                    raise ProviderAuthError("The OpenAI session can no longer be refreshed")
                if response.status == 429:
                    raise ProviderRateLimited(_retry_after_seconds(response))
                if response.status >= 400:
                    raise ProviderError(f"OpenAI token refresh failed ({response.status})")
                payload = await response.json(content_type=None)
        except (ProviderAuthError, ProviderRateLimited, ProviderError):
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ProviderConnectionError("Could not refresh OpenAI credentials") from err
        return credentials_from_token_response(payload, credentials)

    async def async_get_usage(
        self, credentials: OpenAICredentials
    ) -> tuple[ChatGPTUsageData, OpenAICredentials]:
        current = credentials
        if current.expires_at <= time.time() + 300:
            current = await self.async_refresh(current)
        status, payload = await self._usage_request(current)
        if status == 401:
            current = await self.async_refresh(current)
            status, payload = await self._usage_request(current)
        if status in (401, 403):
            raise ProviderAuthError("OpenAI rejected the stored credentials")
        if status == 429:
            raise ProviderRateLimited()
        if status >= 500:
            raise ProviderConnectionError(f"OpenAI usage service returned HTTP {status}")
        if status >= 400:
            raise ProviderError(f"OpenAI usage request failed ({status})")
        try:
            return parse_openai_usage(
                payload, account_id=current.account_id, source=PROVIDER_REMOTE
            ), current
        except UsageSchemaError as err:
            raise ProviderSchemaError(str(err)) from err

    async def async_get_accounts(self, credentials: OpenAICredentials) -> tuple[AvailableAccount, ...]:
        headers = self._headers(credentials)
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                response = await self.session.get(ACCOUNTS_API_URL, headers=headers)
                if response.status in (403, 404):
                    return ()
                if response.status == 401:
                    raise ProviderAuthError("OpenAI rejected account discovery")
                if response.status >= 400:
                    return ()
                payload = await response.json(content_type=None)
        except ProviderAuthError:
            raise
        except (aiohttp.ClientError, TimeoutError):
            return ()
        return _parse_accounts(payload)

    async def _usage_request(self, credentials: OpenAICredentials) -> tuple[int, Any]:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                response = await self.session.get(
                    USAGE_API_URL, headers=self._headers(credentials)
                )
                status = response.status
                try:
                    payload = await response.json(content_type=None)
                except (aiohttp.ContentTypeError, json.JSONDecodeError, UnicodeDecodeError):
                    payload = None
                return status, payload
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ProviderConnectionError("Could not connect to OpenAI usage service") from err

    @staticmethod
    def _headers(credentials: OpenAICredentials) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {credentials.access_token}",
            "ChatGPT-Account-Id": credentials.account_id,
            "User-Agent": USER_AGENT,
            "Cache-Control": "no-store",
        }
        if credentials.fedramp:
            headers["X-OpenAI-Fedramp"] = "true"
        return headers


class RemoteOpenAIProvider:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.client = OpenAIAuthClient(aiohttp_client.async_get_clientsession(hass))

    async def async_get_usage(self) -> ChatGPTUsageData:
        current = credentials_from_entry(self.entry)
        data, refreshed = await self.client.async_get_usage(current)
        if refreshed != current:
            self.hass.config_entries.async_update_entry(
                self.entry,
                data={**self.entry.data, **credentials_to_entry_data(refreshed)},
            )
        return data

    async def async_close(self) -> None:
        return None


class LocalCodexProvider:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.session = aiohttp_client.async_get_clientsession(hass)

    @property
    def base_url(self) -> str:
        scheme = "https" if self.entry.data.get(CONF_USE_HTTPS, False) else "http"
        return f"{scheme}://{self.entry.data[CONF_HOST]}:{int(self.entry.data[CONF_PORT])}"

    async def async_get_usage(self) -> ChatGPTUsageData:
        headers = {"Authorization": f"Bearer {self.entry.data[CONF_API_KEY]}"}
        try:
            async with asyncio.timeout(15):
                response = await self.session.get(
                    f"{self.base_url}{LOCAL_USAGE_PATH}", headers=headers
                )
                if response.status in (401, 403):
                    raise ProviderAuthError("Local Codex helper rejected the API key")
                if response.status == 429:
                    raise ProviderRateLimited(_retry_after_seconds(response))
                if response.status >= 500:
                    raise ProviderConnectionError(
                        f"Local Codex helper returned HTTP {response.status}"
                    )
                if response.status >= 400:
                    raise ProviderError(f"Local Codex helper returned HTTP {response.status}")
                payload = await response.json(content_type=None)
        except (ProviderAuthError, ProviderRateLimited, ProviderConnectionError, ProviderError):
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ProviderConnectionError("Could not connect to local Codex helper") from err
        try:
            return parse_helper_usage(payload)
        except UsageSchemaError as err:
            raise ProviderSchemaError(str(err)) from err

    async def async_health(self) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.entry.data[CONF_API_KEY]}"}
        try:
            async with asyncio.timeout(10):
                response = await self.session.get(
                    f"{self.base_url}{LOCAL_HEALTH_PATH}", headers=headers
                )
                if response.status in (401, 403):
                    raise ProviderAuthError("Local Codex helper rejected the API key")
                if response.status >= 400:
                    raise ProviderConnectionError("Local Codex helper health check failed")
                payload = await response.json(content_type=None)
        except (ProviderAuthError, ProviderConnectionError):
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ProviderConnectionError("Could not connect to local Codex helper") from err
        if not isinstance(payload, dict) or payload.get("api_version") != LOCAL_API_VERSION:
            raise ProviderSchemaError("Unsupported local Codex helper API version")
        return payload

    async def async_close(self) -> None:
        return None


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("invalid JWT")
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        result = json.loads(decoded)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error) as err:
        raise ProviderAuthError("OpenAI returned an invalid token") from err
    if not isinstance(result, dict):
        raise ProviderAuthError("OpenAI returned invalid token claims")
    return result


def _claims_from_tokens(id_token: str, access_token: str) -> dict[str, Any]:
    id_claims = _decode_jwt_payload(id_token)
    access_claims = _decode_jwt_payload(access_token)
    auth = id_claims.get("https://api.openai.com/auth") or {}
    if not isinstance(auth, dict):
        auth = {}
    account_id = (
        access_claims.get("chatgpt_account_id")
        or id_claims.get("chatgpt_account_id")
        or auth.get("chatgpt_account_id")
    )
    if not account_id:
        raise ProviderAuthError("OpenAI login did not include a ChatGPT workspace")
    exp = access_claims.get("exp")
    try:
        expires_at = float(exp)
    except (TypeError, ValueError):
        expires_at = time.time() + 3600
    return {
        "account_id": str(account_id),
        "user_id": str(auth.get("chatgpt_user_id") or auth.get("user_id") or "") or None,
        "plan_type": str(auth.get("chatgpt_plan_type") or "") or None,
        "fedramp": bool(auth.get("chatgpt_account_is_fedramp", False)),
        "expires_at": expires_at,
    }


def _parse_accounts(payload: Any) -> tuple[AvailableAccount, ...]:
    if not isinstance(payload, dict):
        return ()
    raw = payload.get("accounts")
    candidates: list[tuple[str | None, Any]] = []
    if isinstance(raw, list):
        candidates.extend((None, item) for item in raw)
    elif isinstance(raw, dict):
        candidates.extend((str(key), item) for key, item in raw.items())
    else:
        return ()
    result: list[AvailableAccount] = []
    seen: set[str] = set()
    for fallback_id, item in candidates:
        if not isinstance(item, dict):
            continue
        nested = item.get("account")
        if isinstance(nested, dict):
            item = nested
        account_id = item.get("id") or item.get("account_id") or fallback_id
        if not isinstance(account_id, str) or not account_id or account_id in seen:
            continue
        seen.add(account_id)
        result.append(
            AvailableAccount(
                account_id=account_id,
                name=item.get("name") if isinstance(item.get("name"), str) else None,
                structure=item.get("structure") if isinstance(item.get("structure"), str) else None,
            )
        )
    return tuple(result)


def _retry_after_seconds(response: aiohttp.ClientResponse) -> int | None:
    value = response.headers.get("Retry-After")
    try:
        return max(0, int(value)) if value is not None else None
    except ValueError:
        return None
