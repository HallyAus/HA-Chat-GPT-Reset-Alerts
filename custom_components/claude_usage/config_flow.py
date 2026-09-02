"""Config flow for Claude Usage."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlencode

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    OptionsFlowWithReload,
)
from homeassistant.core import callback

from .api import (
    ClaudeAuthError,
    ClaudeConnectionError,
    ClaudePayloadError,
    ClaudeUsageError,
    LocalClaudeCodeProvider,
    async_exchange_oauth_code,
    async_fetch_profile,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ACCOUNT_ID,
    CONF_ACCOUNT_NAME,
    CONF_API_KEY,
    CONF_EXPIRES_AT,
    CONF_HOST,
    CONF_PORT,
    CONF_PROVIDER,
    CONF_REFRESH_TOKEN,
    CONF_SUBSCRIPTION_LEVEL,
    CONF_UPDATE_INTERVAL,
    CONF_USE_HTTPS,
    DEFAULT_LOCAL_PORT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    OAUTH_AUTHORIZE_URL,
    OAUTH_REDIRECT_URI,
    OAUTH_CLIENT_ID,
    OAUTH_SCOPES,
    PROVIDER_LOCAL,
    PROVIDER_REMOTE,
    UPDATE_INTERVAL_OPTIONS,
)


class ClaudeUsageConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure Claude Usage."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._provider: str | None = None
        self._pkce_verifier: str | None = None
        self._pkce_challenge: str | None = None
        self._state: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._provider = user_input[CONF_PROVIDER]
            if self._provider == PROVIDER_LOCAL:
                return await self.async_step_local()
            return await self.async_step_remote()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROVIDER, default=PROVIDER_REMOTE): vol.In(
                        {
                            PROVIDER_REMOTE: "Remote Anthropic",
                            PROVIDER_LOCAL: "Local Claude Code",
                        }
                    )
                }
            ),
        )

    def _oauth_url(self) -> str:
        if self._pkce_verifier is None:
            self._pkce_verifier, self._pkce_challenge = generate_pkce()
            self._state = secrets.token_urlsafe(32)
        params = urlencode(
            {
                "code": "true",
                "client_id": OAUTH_CLIENT_ID,
                "response_type": "code",
                "redirect_uri": OAUTH_REDIRECT_URI,
                "scope": OAUTH_SCOPES,
                "code_challenge": self._pkce_challenge,
                "code_challenge_method": "S256",
                "state": self._state,
            }
        )
        return f"{OAUTH_AUTHORIZE_URL}?{params}"

    async def async_step_remote(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        oauth_url = self._oauth_url()
        if user_input is not None:
            supplied = user_input.get("auth_code", "").strip()
            if not supplied:
                errors["auth_code"] = "missing_code"
            else:
                code, _, returned_state = supplied.partition("#")
                if returned_state and returned_state != self._state:
                    errors["auth_code"] = "state_mismatch"
                else:
                    try:
                        token = await async_exchange_oauth_code(
                            self.hass,
                            code=code,
                            state=returned_state,
                            verifier=self._pkce_verifier or "",
                            redirect_uri=OAUTH_REDIRECT_URI,
                        )
                        profile = await async_fetch_profile(self.hass, token["access_token"])
                    except ClaudeAuthError:
                        errors["auth_code"] = "exchange_failed"
                    except (ClaudeConnectionError, ClaudePayloadError):
                        errors["base"] = "cannot_connect"
                    else:
                        account = profile.get("account") if isinstance(profile.get("account"), dict) else {}
                        account_id = account.get("uuid") or account.get("id") or account.get("email")
                        account_name = account.get("display_name") or account.get("full_name")
                        plan = "Max" if account.get("has_claude_max") else "Pro" if account.get("has_claude_pro") else None
                        if account_id:
                            await self.async_set_unique_id(f"remote:{account_id}")
                            self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=f"Claude Usage ({account_name or plan or 'Remote'})",
                            data={
                                CONF_PROVIDER: PROVIDER_REMOTE,
                                CONF_ACCESS_TOKEN: token["access_token"],
                                CONF_REFRESH_TOKEN: token.get("refresh_token", ""),
                                CONF_EXPIRES_AT: time.time() + float(token.get("expires_in", 3600)),
                                CONF_ACCOUNT_ID: account_id,
                                CONF_ACCOUNT_NAME: account_name,
                                CONF_SUBSCRIPTION_LEVEL: plan,
                            },
                            options={CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL},
                        )
        return self.async_show_form(
            step_id="remote",
            data_schema=vol.Schema({vol.Required("auth_code"): str}),
            description_placeholders={"url": oauth_url},
            errors=errors,
        )

    async def async_step_local(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            temp_data = {CONF_PROVIDER: PROVIDER_LOCAL, **user_input}
            temp_entry = SimpleNamespace(data=temp_data, options={})
            try:
                provider = LocalClaudeCodeProvider(self.hass, temp_entry)  # type: ignore[arg-type]
                await provider.async_health()
                await provider.async_get_usage()
            except ClaudeAuthError:
                errors["base"] = "invalid_auth"
            except (ClaudeConnectionError, ClaudePayloadError, ClaudeUsageError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(
                    f"local:{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Claude Usage ({user_input[CONF_HOST]})",
                    data=temp_data,
                    options={CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL},
                )
        return self.async_show_form(
            step_id="local",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_PORT, default=DEFAULT_LOCAL_PORT): vol.All(int, vol.Range(min=1, max=65535)),
                    vol.Required(CONF_API_KEY): str,
                    vol.Required(CONF_USE_HTTPS, default=False): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        if entry.data.get(CONF_PROVIDER) == PROVIDER_LOCAL:
            return await self.async_step_reauth_local()
        return await self.async_step_reauth_remote()

    async def async_step_reauth_remote(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        oauth_url = self._oauth_url()
        if user_input is not None:
            supplied = user_input.get("auth_code", "").strip()
            code, _, returned_state = supplied.partition("#")
            if returned_state and returned_state != self._state:
                errors["auth_code"] = "state_mismatch"
            else:
                try:
                    token = await async_exchange_oauth_code(
                        self.hass,
                        code=code,
                        state=returned_state,
                        verifier=self._pkce_verifier or "",
                        redirect_uri=OAUTH_REDIRECT_URI,
                    )
                    profile = await async_fetch_profile(self.hass, token["access_token"])
                except (ClaudeAuthError, ClaudeConnectionError, ClaudePayloadError):
                    errors["auth_code"] = "exchange_failed"
                else:
                    account = profile.get("account") if isinstance(profile.get("account"), dict) else {}
                    entry = self._get_reauth_entry()
                    new_data = {
                        **entry.data,
                        CONF_ACCESS_TOKEN: token["access_token"],
                        CONF_REFRESH_TOKEN: token.get("refresh_token", ""),
                        CONF_EXPIRES_AT: time.time() + float(token.get("expires_in", 3600)),
                        CONF_ACCOUNT_ID: account.get("uuid") or account.get("id") or account.get("email"),
                        CONF_ACCOUNT_NAME: account.get("display_name") or account.get("full_name"),
                        CONF_SUBSCRIPTION_LEVEL: "Max" if account.get("has_claude_max") else "Pro" if account.get("has_claude_pro") else None,
                    }
                    return self.async_update_reload_and_abort(entry, data_updates=new_data)
        return self.async_show_form(
            step_id="reauth_remote",
            data_schema=vol.Schema({vol.Required("auth_code"): str}),
            description_placeholders={"url": oauth_url},
            errors=errors,
        )

    async def async_step_reauth_local(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            new_data = {**entry.data, CONF_API_KEY: user_input[CONF_API_KEY]}
            temp_entry = SimpleNamespace(data=new_data, options=entry.options)
            try:
                provider = LocalClaudeCodeProvider(self.hass, temp_entry)  # type: ignore[arg-type]
                await provider.async_health()
            except ClaudeAuthError:
                errors["base"] = "invalid_auth"
            except ClaudeUsageError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(entry, data_updates=new_data)
        return self.async_show_form(
            step_id="reauth_local",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ClaudeUsageOptionsFlow()


class ClaudeUsageOptionsFlow(OptionsFlowWithReload):
    """Configure polling and local connection overrides and reload safely."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        provider_name = self.config_entry.data.get(CONF_PROVIDER, PROVIDER_REMOTE)
        if user_input is not None:
            if provider_name == PROVIDER_LOCAL:
                temp_entry = SimpleNamespace(data=self.config_entry.data, options=user_input)
                try:
                    provider = LocalClaudeCodeProvider(self.hass, temp_entry)  # type: ignore[arg-type]
                    await provider.async_health()
                except ClaudeAuthError:
                    errors["base"] = "invalid_auth"
                except ClaudeUsageError:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(title="", data=user_input)
            else:
                return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options
        schema: dict[Any, Any] = {
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=current.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): vol.In(UPDATE_INTERVAL_OPTIONS)
        }
        if provider_name == PROVIDER_LOCAL:
            schema.update(
                {
                    vol.Required(CONF_HOST, default=current.get(CONF_HOST, self.config_entry.data.get(CONF_HOST))): str,
                    vol.Required(CONF_PORT, default=current.get(CONF_PORT, self.config_entry.data.get(CONF_PORT, DEFAULT_LOCAL_PORT))): vol.All(int, vol.Range(min=1, max=65535)),
                    vol.Required(CONF_API_KEY, default=current.get(CONF_API_KEY, self.config_entry.data.get(CONF_API_KEY))): str,
                    vol.Required(CONF_USE_HTTPS, default=current.get(CONF_USE_HTTPS, self.config_entry.data.get(CONF_USE_HTTPS, False))): bool,
                }
            )
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema), errors=errors)


def generate_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge
