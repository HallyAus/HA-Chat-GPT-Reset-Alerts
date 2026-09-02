"""Constants for ChatGPT Usage."""

from typing import Final

DOMAIN: Final = "chatgpt_usage"
NAME: Final = "ChatGPT Usage"
VERSION: Final = "0.1.0"

PROVIDER_REMOTE: Final = "remote"
PROVIDER_LOCAL: Final = "local"
CONF_PROVIDER: Final = "provider"

OAUTH_CLIENT_ID: Final = "app_EMoamEEZ73f0CkXaXp7hrann"
OAUTH_ISSUER: Final = "https://auth.openai.com"
DEVICE_CODE_URL: Final = f"{OAUTH_ISSUER}/api/accounts/deviceauth/usercode"
DEVICE_TOKEN_URL: Final = f"{OAUTH_ISSUER}/api/accounts/deviceauth/token"
DEVICE_VERIFICATION_URL: Final = f"{OAUTH_ISSUER}/codex/device"
OAUTH_TOKEN_URL: Final = f"{OAUTH_ISSUER}/oauth/token"
OAUTH_DEVICE_REDIRECT_URI: Final = f"{OAUTH_ISSUER}/deviceauth/callback"
USAGE_API_URL: Final = "https://chatgpt.com/backend-api/wham/usage"
ACCOUNTS_API_URL: Final = "https://chatgpt.com/backend-api/wham/accounts/check"

CONF_ACCESS_TOKEN: Final = "access_token"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_ID_TOKEN: Final = "id_token"
CONF_EXPIRES_AT: Final = "expires_at"
CONF_ACCOUNT_ID: Final = "account_id"
CONF_USER_ID: Final = "user_id"
CONF_EMAIL: Final = "email"
CONF_PLAN_TYPE: Final = "plan_type"
CONF_FEDRAMP: Final = "fedramp"

CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_API_KEY: Final = "api_key"
CONF_USE_HTTPS: Final = "use_https"
CONF_HELPER_ID: Final = "helper_id"

CONF_UPDATE_INTERVAL: Final = "update_interval"
DEFAULT_UPDATE_INTERVAL: Final = 3600
MIN_UPDATE_INTERVAL: Final = 900
MAX_UPDATE_INTERVAL: Final = 14400
POLL_OPTIONS: Final = (900, 1800, 3600, 7200, 14400)

LOCAL_API_VERSION: Final = 1
LOCAL_HEALTH_PATH: Final = "/api/v1/health"
LOCAL_USAGE_PATH: Final = "/api/v1/usage"
LOCAL_DEFAULT_PORT: Final = 8765

EVENT_USAGE_RESET: Final = "chatgpt_usage_reset"
STORAGE_VERSION: Final = 1
STORAGE_KEY_TEMPLATE: Final = "chatgpt_usage.reset_state.{entry_id}"

REQUEST_TIMEOUT_SECONDS: Final = 20
USER_AGENT: Final = "HomeAssistant-ChatGPTUsage/0.1.0"
