# Claude Usage for Home Assistant

A Home Assistant custom integration for monitoring Claude / Claude Code subscription usage and firing an event when an allowance resets. The repository can remain private, with manual Home Assistant installation; HACS metadata is included for use if the repository is later made public.

> Unofficial community integration. Not affiliated with, endorsed by, or supported by Anthropic.

## Features

- Remote Anthropic OAuth mode: Home Assistant polls subscription usage directly.
- Local Claude Code mode: a small Windows helper reads Claude Code's current OAuth access token locally and exposes only sanitized usage data to Home Assistant.
- Default polling interval: **60 minutes**.
- Configurable 15 min / 30 min / 60 min / 2 h / 4 h polling.
- 5-hour/session usage, remaining percentage, reset time and time remaining.
- Weekly usage, remaining percentage, reset time and time remaining.
- Dynamic model/surface-specific `limits[]` buckets as Anthropic adds them.
- Extra Usage / spend support where Anthropic exposes it.
- Reset persistence across Home Assistant restarts.
- `claude_usage_reset` Home Assistant event fired once per confirmed rollover.
- Connected, limit-reached and Extra Usage binary sensors.
- Manual refresh button.
- Diagnostics with credentials redacted.

## Important limitation

Claude subscription usage is currently obtained from Anthropic's OAuth usage interface at `api.anthropic.com/api/oauth/usage`. This is used by the Claude ecosystem but is **not a documented stable third-party subscription-usage API**. Anthropic can change the endpoint, OAuth flow or response shape without notice.

The code isolates Anthropic parsing and requests so those changes can be repaired without rewriting the Home Assistant entity layer.

## Installation

### Private repository: manual installation required

HACS currently does **not** support private GitHub repositories. While this repository remains private, install it manually.

Copy:

```text
custom_components/claude_usage/
```

to:

```text
/config/custom_components/claude_usage/
```

Restart Home Assistant and add **Claude Usage** from **Settings → Devices & services → Add Integration**.

### If the repository is later made public: HACS

The repository already contains HACS metadata and validation. If it is made public:

1. In HACS, open the menu and choose **Custom repositories**.
2. Add `https://github.com/HallyAus/HA_Ai_Usage` as category **Integration**.
3. Install **Claude Usage**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add Integration → Claude Usage**.

# Connection methods

## Option A — Remote Anthropic

Recommended when you want monitoring to continue with your PC turned off.

```text
Home Assistant
      ↓
Anthropic OAuth
      ↓
Claude subscription usage
      ↓
DataUpdateCoordinator
      ↓
HA entities + reset event
```

Setup:

1. Add the integration.
2. Select **Remote Anthropic**.
3. Open the authorization URL shown by Home Assistant.
4. Sign in to Anthropic and approve the request.
5. Copy the returned authorization code into Home Assistant.

OAuth access and refresh tokens are stored in the Home Assistant config entry. They are redacted from diagnostics and never exposed as entity attributes or event data.

## Option B — Local Claude Code

Recommended if you do not want Claude account OAuth credentials stored in Home Assistant.

```text
Claude Code on Windows
        ↓
current access token stays on Windows
        ↓
Claude Usage Helper
        ↓ LAN + helper API key
Home Assistant
        ↓
HA entities + reset event
```

### Install Windows helper

Copy the `local_helper` directory to the Windows PC that runs Claude Code, then open PowerShell in it:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

The installer:

- installs a startup Scheduled Task running as SYSTEM;
- generates a random 256-bit helper API key;
- creates a Windows HTTP.sys URL reservation;
- opens the selected TCP port only to `LocalSubnet`;
- prints suitable LAN IP addresses;
- tests `/api/v1/health`.

Default port: `8766`.

Then add **Claude Usage → Local Claude Code** in Home Assistant and enter the host, port and generated API key.

### Local helper credential behaviour

The helper reads:

```text
%USERPROFILE%\.claude\.credentials.json
```

It uses only the current `accessToken` to request usage. It intentionally does **not** consume or rotate Claude Code's refresh token. This prevents the helper from invalidating Claude Code's own token rotation.

If Claude Code's access token expires while Claude Code is idle, Local mode can temporarily become unavailable. Use Claude Code normally or log in again; once Claude Code refreshes its credentials, Home Assistant recovers on the next poll.

### Local helper endpoints

Authenticated requests only:

```text
GET /api/v1/health
GET /api/v1/usage
```

There is no command endpoint and no arbitrary file access.

# Entities

The integration creates one **Claude Usage** device. Actual entity IDs can vary depending on Home Assistant naming and existing entities; use the entity names below rather than assuming exact IDs.

For the normal session window:

- **5 hour usage** — `%`
- **5 hour remaining** — `%`
- **5 hour reset** — timestamp
- **5 hour time remaining** — seconds/duration

For the normal weekly window:

- **Weekly usage**
- **Weekly remaining**
- **Weekly reset**
- **Weekly time remaining**

Model-specific limits are created dynamically, for example:

- **Weekly Opus 4.1 usage**
- **Weekly Opus 4.1 remaining**
- **Weekly Opus 4.1 reset**

Other entities:

- **Plan**
- **Last update**
- **Connected**
- **Limit reached**
- **Extra Usage enabled**
- **Extra Usage**
- **Extra Usage spent**
- **Extra Usage remaining**
- **Extra Usage limit**
- **Refresh**

# Reset detection

The integration stores a small, non-sensitive snapshot of each usage window in Home Assistant storage.

A reset is considered confirmed when the reported reset timestamp moves to the next window and either:

- the previous reset time has arrived, or
- usage drops by at least 20 percentage points.

A fallback handles a very large `90%+ → 20%-` usage drop if Anthropic temporarily omits reset timestamps.

This deliberately avoids treating these as resets:

- first integration startup;
- Home Assistant restart;
- `51% → 50%` rounding movement;
- a temporary missing API payload;
- bucket ordering changes.

# Reset event

A confirmed rollover fires:

```text
claude_usage_reset
```

Example event data:

```json
{
  "window_id": "weekly",
  "window": "Weekly",
  "previous_used_percent": 98,
  "new_used_percent": 2,
  "remaining_percent": 98,
  "previous_reset_at": "2026-09-02T12:00:00+00:00",
  "new_reset_at": "2026-09-09T12:00:00+00:00"
}
```

# Phone notification automation

```yaml
alias: Claude usage reset
triggers:
  - trigger: event
    event_type: claude_usage_reset
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: Claude usage reset
      message: >-
        {{ trigger.event.data.window }} allowance reset.
        {{ trigger.event.data.remaining_percent | round(0) }}% remaining.
mode: queued
```

## Weekly only

```yaml
alias: Claude weekly usage reset
triggers:
  - trigger: event
    event_type: claude_usage_reset
conditions:
  - condition: template
    value_template: "{{ trigger.event.data.window_id == 'weekly' }}"
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: Claude weekly usage reset
      message: "Your weekly Claude allowance is available again."
```

# Low remaining warning

Select your generated **Weekly remaining** entity in the UI or use an automation equivalent to:

```yaml
triggers:
  - trigger: numeric_state
    entity_id: sensor.your_claude_weekly_remaining_entity
    below: 10
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: Claude usage
      message: "Weekly Claude allowance is below 10%."
```

# Dashboard

A basic Lovelace example is in `dashboards/claude_usage.yaml`. Because entity IDs are assigned by Home Assistant, adjust those IDs after setup.

A simple card can also be built in the UI using an Entities card with:

```text
5 hour usage
5 hour remaining
5 hour reset
Weekly usage
Weekly remaining
Weekly reset
Extra Usage
Last update
Connected
```

# Polling

Default: **3600 seconds (1 hour)**.

Available options:

- 900 seconds
- 1800 seconds
- 3600 seconds
- 7200 seconds
- 14400 seconds

Anthropic can rate-limit aggressive polling of the subscription usage endpoint. The one-hour default is intentionally conservative.

With hourly polling, a reset at 14:17 may be detected at the 15:00 poll. The reset timestamp entity still shows the precise timestamp Anthropic supplied.

# Diagnostics

**Settings → Devices & services → Claude Usage → three-dot menu → Download diagnostics**

Diagnostics include provider type, polling interval, window IDs, percentages and reset timestamps. They redact:

- Anthropic access tokens;
- Anthropic refresh tokens;
- local helper API keys.

# Security notes

## Remote mode

- Anthropic requests use HTTPS.
- OAuth credentials remain in Home Assistant config storage.
- Tokens are not logged by this integration.
- Diagnostics redact secrets.

## Local mode

- Claude OAuth credentials never leave the Windows PC.
- A separate random bearer key authenticates Home Assistant to the helper.
- The default firewall rule is restricted to the local subnet.
- The helper has no remote command API.
- HTTP is used on the LAN by default. The bearer key protects access but does not encrypt traffic. For an untrusted LAN, place the helper behind a local HTTPS reverse proxy and enable **Use HTTPS** in Home Assistant.

# Uninstall

Home Assistant:

1. Remove the Claude Usage config entry.
2. Remove the repository from HACS if desired.

Windows Local mode:

```powershell
.\uninstall.ps1
```

The uninstaller removes the task, firewall rule, URL reservation and helper config. It does not modify or uninstall Claude Code.

# Development

Local lightweight checks:

```bash
python -m compileall custom_components tests
pytest -q
ruff check custom_components tests
```

GitHub Actions runs:

- Ruff
- pytest
- Home Assistant hassfest
- HACS validation

# Attribution

This project was independently structured for dual Remote/Local Home Assistant monitoring, but references concepts and current OAuth/usage behaviour from Patrick van Staveren's MIT-licensed `trickv/hass-claude-usage` project. See `NOTICE.md` and `LICENSE`.
