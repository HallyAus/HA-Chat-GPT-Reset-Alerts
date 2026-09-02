"""Constants for the Claude Usage integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "claude_usage"
NAME = "Claude Usage"
VERSION = "0.1.0"

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]

PROVIDER_REMOTE = "remote"
PROVIDER_LOCAL = "local"

CONF_PROVIDER = "provider"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_EXPIRES_AT = "expires_at"
CONF_ACCOUNT_ID = "account_id"
CONF_ACCOUNT_NAME = "account_name"
CONF_SUBSCRIPTION_LEVEL = "subscription_level"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_API_KEY = "api_key"
CONF_USE_HTTPS = "use_https"

DEFAULT_UPDATE_INTERVAL = 3600
UPDATE_INTERVAL_OPTIONS = [900, 1800, 3600, 7200, 14400]
DEFAULT_LOCAL_PORT = 8766

OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
OAUTH_AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
OAUTH_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
OAUTH_REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
OAUTH_SCOPES = "user:profile"

USAGE_API_URL = "https://api.anthropic.com/api/oauth/usage"
PROFILE_API_URL = "https://api.anthropic.com/api/oauth/profile"
API_BETA_HEADER = "oauth-2025-04-20"

LOCAL_API_VERSION = 1
LOCAL_USAGE_PATH = "/api/v1/usage"
LOCAL_HEALTH_PATH = "/api/v1/health"

EVENT_USAGE_RESET = "claude_usage_reset"
RESET_STORE_VERSION = 1
