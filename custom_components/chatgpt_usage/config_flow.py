"""Config flow for ChatGPT Usage."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client

from .api import (
    AvailableAccount,
    DeviceAuthorizationPending,
    DeviceAuthorizationUnavailable,
    DeviceCode,
    OpenAIAuthClient,
    OpenAICredentials,
    ProviderAuthError,
    ProviderConnectionError,
    ProviderError,
    ProviderSchemaError,
    credentials_to_entry_data,
)
from .const import (
    CONF_ACCOUNT_ID,
    CONF_API_KEY,
    CONF_HELPER_ID,
    CONF_HOST,
    CONF_PORT,
    CONF_PROVIDER,
    CONF_UPDATE_INTERVAL,
    CONF_USE_HTTPS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOCAL_API_VERSION,
    LOCAL_DEFAULT_PORT,
    LOCAL_HEALTH_PATH,
    LOCAL_USAGE_PATH,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
    POLL_OPTIONS,
    PROVIDER_LOCAL,
    PROVIDER_REMOTE,
)
from .parsing import UsageSchemaError, parse_helper_usage


class ChatGPTUsageConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up remote OpenAI or local Codex monitoring."""

    VERSION = 1

    def __init__(self) -> None:
        self._device_code: DeviceCode | None = None
        self._credentials: OpenAICredentials | None = None
        self._accounts: tuple[AvailableAccount, ...] = ()
        self._reauth_entry: ConfigEntry | None = None
        self._reauth = False

    @property
    def _auth_client(self) -> OpenAIAuthClient:
        return OpenAIAuthClient(aiohttp_client.async_get_clientsession(self.hass))

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            provider = user_input[CONF_PROVIDER]
            if provider == PROVIDER_LOCAL:
                return await self.async_step_local()
            return await self.async_step_remote()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROVIDER, default=PROVIDER_REMOTE): vol.In(
                        {PROVIDER_REMOTE: "Remote OpenAI", PROVIDER_LOCAL: "Local Codex"}
                    )
                }
            ),
        )

    async def async_step_remote(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Start OpenAI device-code authentication."""
        errors: dict[str, str] = {}
        if self._device_code is None:
            try:
                self._device_code = await self._auth_client.async_request_device_code()
            except DeviceAuthorizationUnavailable:
                errors["base"] = "device_auth_disabled"
            except ProviderConnectionError:
                errors["base"] = "cannot_connect"
            except ProviderError:
                errors["base"] = "unknown"
        if errors:
            return self.async_show_form(step_id="remote", data_schema=vol.Schema({}), errors=errors)
        return await self.async_step_device(user_input)

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._device_code is None:
            return self.async_abort(reason="device_flow_expired")
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                authorization = await self._auth_client.async_poll_device_code(self._device_code)
                credentials = await self._auth_client.async_exchange_device_code(authorization)
                return await self._prepare_workspace(credentials)
            except DeviceAuthorizationPending:
                errors["base"] = "authorization_pending"
            except ProviderAuthError:
                errors["base"] = "invalid_auth"
            except ProviderConnectionError:
                errors["base"] = "cannot_connect"
            except ProviderError:
                errors["base"] = "unknown"
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
            description_placeholders={
                "verification_url": self._device_code.verification_url,
                "user_code": self._device_code.user_code,
            },
            errors=errors,
        )

    async def _prepare_workspace(self, credentials: OpenAICredentials) -> ConfigFlowResult:
        try:
            accounts = await self._auth_client.async_get_accounts(credentials)
        except ProviderError:
            accounts = ()
        if self._reauth and self._reauth_entry is not None:
            existing_id = self._reauth_entry.data.get(CONF_ACCOUNT_ID)
            if isinstance(existing_id, str) and existing_id:
                return await self._finish_remote(replace(credentials, account_id=existing_id))
        if len(accounts) <= 1:
            selected = replace(credentials, account_id=accounts[0].account_id) if accounts else credentials
            return await self._finish_remote(selected)
        self._credentials = credentials
        self._accounts = accounts
        return await self.async_step_workspace()

    async def async_step_workspace(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        choices: dict[str, str] = {}
        for index, account in enumerate(self._accounts, start=1):
            label = account.name or f"Workspace {index}"
            if account.structure:
                label = f"{label} · {account.structure}"
            choices[account.account_id] = label
        if user_input is None:
            return self.async_show_form(
                step_id="workspace",
                data_schema=vol.Schema({vol.Required(CONF_ACCOUNT_ID): vol.In(choices)}),
            )
        if self._credentials is None:
            return self.async_abort(reason="device_flow_expired")
        return await self._finish_remote(
            replace(self._credentials, account_id=str(user_input[CONF_ACCOUNT_ID]))
        )

    async def _finish_remote(self, credentials: OpenAICredentials) -> ConfigFlowResult:
        try:
            _data, credentials = await self._auth_client.async_get_usage(credentials)
        except ProviderAuthError:
            return self.async_abort(reason="invalid_auth")
        except ProviderConnectionError:
            return self.async_abort(reason="cannot_connect")
        except ProviderError:
            return self.async_abort(reason="unknown")

        unique_id = f"remote:{credentials.account_id}:{credentials.user_id or 'account'}"
        await self.async_set_unique_id(unique_id)
        if self._reauth and self._reauth_entry is not None:
            self._abort_if_unique_id_mismatch()
            return self.async_update_reload_and_abort(
                self._reauth_entry,
                data_updates={CONF_PROVIDER: PROVIDER_REMOTE, **credentials_to_entry_data(credentials)},
            )
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="ChatGPT Usage",
            data={CONF_PROVIDER: PROVIDER_REMOTE, **credentials_to_entry_data(credentials)},
            options={CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL},
        )

    async def async_step_local(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                health = await _test_local(self.hass, user_input)
            except ProviderAuthError:
                errors[CONF_API_KEY] = "invalid_auth"
            except ProviderSchemaError:
                errors["base"] = "invalid_response"
            except ProviderConnectionError:
                errors["base"] = "cannot_connect"
            else:
                helper_id = str(health.get("helper_id") or "").strip()
                unique = helper_id or f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                await self.async_set_unique_id(f"local:{unique}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"ChatGPT Usage ({user_input[CONF_HOST]})",
                    data={
                        CONF_PROVIDER: PROVIDER_LOCAL,
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT: int(user_input[CONF_PORT]),
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_USE_HTTPS: bool(user_input[CONF_USE_HTTPS]),
                        CONF_HELPER_ID: helper_id or None,
                    },
                    options={CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL},
                )
        return self.async_show_form(
            step_id="local", data_schema=_local_schema(user_input), errors=errors
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        self._reauth_entry = self._get_reauth_entry()
        self._reauth = True
        if entry_data.get(CONF_PROVIDER) == PROVIDER_LOCAL:
            return await self.async_step_reauth_local()
        self._device_code = None
        return await self.async_step_remote()

    async def async_step_reauth_local(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._reauth_entry or self._get_reauth_entry()
        defaults = dict(entry.data)
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _test_local(self.hass, user_input)
            except ProviderAuthError:
                errors[CONF_API_KEY] = "invalid_auth"
            except ProviderSchemaError:
                errors["base"] = "invalid_response"
            except ProviderConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT: int(user_input[CONF_PORT]),
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_USE_HTTPS: bool(user_input[CONF_USE_HTTPS]),
                    },
                )
        return self.async_show_form(
            step_id="reauth_local", data_schema=_local_schema(defaults), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ChatGPTUsageOptionsFlow()


class ChatGPTUsageOptionsFlow(OptionsFlow):
    """Configure polling and local endpoint settings."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        provider = self.config_entry.data.get(CONF_PROVIDER, PROVIDER_REMOTE)
        errors: dict[str, str] = {}
        if user_input is not None:
            if provider == PROVIDER_LOCAL:
                candidate = {
                    CONF_HOST: user_input[CONF_HOST],
                    CONF_PORT: int(user_input[CONF_PORT]),
                    CONF_API_KEY: user_input[CONF_API_KEY],
                    CONF_USE_HTTPS: bool(user_input[CONF_USE_HTTPS]),
                }
                try:
                    await _test_local(self.hass, candidate)
                except ProviderAuthError:
                    errors[CONF_API_KEY] = "invalid_auth"
                except (ProviderConnectionError, ProviderSchemaError):
                    errors["base"] = "cannot_connect"
                else:
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data={**self.config_entry.data, **candidate},
                    )
            if not errors:
                return self.async_create_entry(
                    data={CONF_UPDATE_INTERVAL: int(user_input[CONF_UPDATE_INTERVAL])}
                )

        interval = int(self.config_entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
        if provider == PROVIDER_LOCAL:
            defaults = dict(self.config_entry.data)
            schema = {
                vol.Required(CONF_UPDATE_INTERVAL, default=interval): vol.In(POLL_OPTIONS),
                vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
                vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, LOCAL_DEFAULT_PORT)): vol.All(int, vol.Range(min=1, max=65535)),
                vol.Required(CONF_API_KEY, default=defaults.get(CONF_API_KEY, "")): str,
                vol.Required(CONF_USE_HTTPS, default=defaults.get(CONF_USE_HTTPS, False)): bool,
            }
        else:
            schema = {
                vol.Required(CONF_UPDATE_INTERVAL, default=interval): vol.All(
                    int, vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL)
                )
            }
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema), errors=errors)


def _local_schema(values: dict[str, Any] | None) -> vol.Schema:
    values = values or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=values.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=values.get(CONF_PORT, LOCAL_DEFAULT_PORT)): vol.All(int, vol.Range(min=1, max=65535)),
            vol.Required(CONF_API_KEY, default=values.get(CONF_API_KEY, "")): str,
            vol.Required(CONF_USE_HTTPS, default=values.get(CONF_USE_HTTPS, False)): bool,
        }
    )


async def _test_local(hass: Any, values: dict[str, Any]) -> dict[str, Any]:
    scheme = "https" if values.get(CONF_USE_HTTPS, False) else "http"
    base_url = f"{scheme}://{values[CONF_HOST]}:{int(values[CONF_PORT])}"
    headers = {"Authorization": f"Bearer {values[CONF_API_KEY]}"}
    session = aiohttp_client.async_get_clientsession(hass)
    try:
        async with asyncio.timeout(15):
            health_response = await session.get(f"{base_url}{LOCAL_HEALTH_PATH}", headers=headers)
            if health_response.status in (401, 403):
                raise ProviderAuthError("Invalid helper API key")
            if health_response.status >= 400:
                raise ProviderConnectionError("Local helper health check failed")
            health = await health_response.json(content_type=None)
            if not isinstance(health, dict) or health.get("api_version") != LOCAL_API_VERSION:
                raise ProviderSchemaError("Unsupported helper API version")
            usage_response = await session.get(f"{base_url}{LOCAL_USAGE_PATH}", headers=headers)
            if usage_response.status in (401, 403):
                raise ProviderAuthError("Invalid helper API key")
            if usage_response.status >= 400:
                raise ProviderConnectionError("Local helper usage check failed")
            usage = await usage_response.json(content_type=None)
            try:
                parse_helper_usage(usage)
            except UsageSchemaError as err:
                raise ProviderSchemaError(str(err)) from err
            return health
    except (ProviderAuthError, ProviderConnectionError, ProviderSchemaError):
        raise
    except (aiohttp.ClientError, TimeoutError) as err:
        raise ProviderConnectionError("Could not connect to local Codex helper") from err
