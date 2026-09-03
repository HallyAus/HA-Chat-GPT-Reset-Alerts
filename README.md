# AI Usage for Home Assistant

Home Assistant integrations for monitoring subscription usage and reset times for:

- **ChatGPT / Codex**
- **Claude / Claude Code**

The primary goal is to let Home Assistant notify you when an AI usage allowance resets.

Both integrations default to **one poll per hour** and persist reset state so restarting Home Assistant does not create a false reset alert.

> **Unofficial community project.** This repository is not affiliated with, endorsed by, or supported by OpenAI or Anthropic.

---

## Included integrations

| Integration | HA domain | Recommended method | Local method | Reset event |
|---|---|---|---|---|
| ChatGPT Usage | `chatgpt_usage` | Remote OpenAI device login | Official Codex app-server helper | `chatgpt_usage_reset` |
| Claude Usage | `claude_usage` | Remote Anthropic OAuth | Claude Code helper | `claude_usage_reset` |

You can install either or both.

---

# Installation

This repository is currently public, but it contains **two separate Home Assistant integrations**. The reliable installation method for this combined repository is manual copy.

Clone or download:

```text
https://github.com/HallyAus/HA-Chat-GPT-Reset-Alerts
```

For ChatGPT/Codex copy:

```text
custom_components/chatgpt_usage
```

to:

```text
/config/custom_components/chatgpt_usage
```

For Claude copy:

```text
custom_components/claude_usage
```

to:

```text
/config/custom_components/claude_usage
```

Do **not** copy the whole repository into `/config/custom_components`.

You should end up with paths such as:

```text
/config/custom_components/chatgpt_usage/manifest.json
/config/custom_components/chatgpt_usage/config_flow.py
/config/custom_components/claude_usage/manifest.json
/config/custom_components/claude_usage/config_flow.py
```

Then perform a full Home Assistant restart:

**Settings → System → Restart Home Assistant**

After restart:

**Settings → Devices & services → Add Integration**

Search for **ChatGPT Usage** and/or **Claude Usage**.

> `hacs.json` is included for development, but HACS distribution is cleaner as one integration per repository. This combined two-integration repository should be installed manually unless it is later split into dedicated HACS repositories or combined into one `ai_usage` domain.

---

# ChatGPT / Codex Usage

## Recommended method: Remote OpenAI

Remote OpenAI is the simplest option and continues working when your Windows PC is off.

```text
Home Assistant
      │
      ▼
OpenAI device-code login
      │
      ▼
ChatGPT / Codex usage service
      │
      ▼
5-hour + weekly + additional limits
      │
      ▼
chatgpt_usage_reset
```

## Remote OpenAI setup

1. Install `custom_components/chatgpt_usage` and restart Home Assistant.
2. Open **Settings → Devices & services → Add Integration → ChatGPT Usage**.
3. Select **Remote OpenAI**.
4. Home Assistant displays an OpenAI device-login URL and temporary code.
5. Open the URL on your phone or computer.
6. Sign into the ChatGPT account with Codex access.
7. Enter the temporary code when requested and approve access.
8. Return to Home Assistant and confirm sign-in is complete.
9. If OpenAI exposes multiple workspaces, select the workspace to monitor.
10. Home Assistant validates the usage service and creates the integration.

The integration stores its own OAuth credentials in Home Assistant config-entry storage and refreshes them automatically. Tokens are never exposed through entities, reset events or diagnostics.

## ChatGPT entities

The exact entities depend on what OpenAI returns for the account. Typical entities include:

```text
5 hour Usage
5 hour Remaining
5 hour Reset
5 hour Time remaining

Weekly Usage
Weekly Remaining
Weekly Reset
Weekly Time remaining

Plan
Credit balance
Reset credits available
Last successful update
Connected
Limit reached
Credits available
Refresh usage
```

Additional metered limits are created dynamically. Limits are identified by their actual duration, not by assuming `primary` always means five hours or `secondary` always means weekly.

## ChatGPT reset event

A confirmed allowance rollover fires:

```text
chatgpt_usage_reset
```

Example event:

```json
{
  "window_id": "weekly",
  "window": "Weekly",
  "limit_name": "Codex",
  "previous_used_percent": 98,
  "new_used_percent": 2,
  "remaining_percent": 98,
  "previous_reset_at": "2026-09-02T12:00:00+00:00",
  "new_reset_at": "2026-09-09T12:00:00+00:00",
  "confidence": "timestamp_rollover"
}
```

The integration persists non-sensitive previous-window state. First startup, small rounding changes and temporary failures do not count as resets.

## ChatGPT reset notification

Replace `notify.mobile_app_your_phone` with your actual mobile notification action.

```yaml
alias: ChatGPT usage reset
triggers:
  - trigger: event
    event_type: chatgpt_usage_reset
conditions: []
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: ChatGPT usage reset
      message: >-
        {{ trigger.event.data.window }} allowance has reset.
        {{ trigger.event.data.remaining_percent | default(100) | round(0) }}% remaining.
mode: queued
```

### Weekly ChatGPT reset only

```yaml
alias: ChatGPT weekly allowance reset
triggers:
  - trigger: event
    event_type: chatgpt_usage_reset
conditions:
  - condition: template
    value_template: "{{ trigger.event.data.window_id == 'weekly' }}"
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: ChatGPT weekly usage reset
      message: >-
        Your weekly ChatGPT/Codex allowance is available again.
        {{ trigger.event.data.remaining_percent | default(100) | round(0) }}% remaining.
mode: queued
```

## Polling

Default:

```text
3600 seconds / 1 hour
```

Options:

- 15 minutes
- 30 minutes
- 1 hour
- 2 hours
- 4 hours

With hourly polling, a reset at 14:17 may be detected at the 15:00 poll. The reset entity still contains the exact upstream reset timestamp.

---

# ChatGPT Local method — official Codex app-server

Use Local Codex if you want **no OpenAI OAuth credentials stored in Home Assistant**.

The helper uses the official Codex local app-server and does **not** open `%USERPROFILE%\.codex\auth.json`.

```text
Codex CLI on Windows
      │
      ▼
codex app-server --stdio
      │
      ▼
account/rateLimits/read
      │
      ▼
Codex Usage Helper
      │ authenticated LAN request
      ▼
Home Assistant
      │
      ▼
same entities + chatgpt_usage_reset
```

The current official Codex app-server exposes rate-limit information through:

```text
account/rateLimits/read
```

The helper forwards only the sanitized rate-limit result.

## Requirements

On the Windows PC:

```powershell
codex --version
```

must work.

Codex must already be signed into the ChatGPT account you want to monitor. If required:

```powershell
codex login
```

The helper runs in your logged-in Windows user context because that is where Codex authentication is available.

## Install Local Codex helper

Copy this repository directory to the Windows PC:

```text
local_helper_codex
```

Open PowerShell inside it:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

Default port:

```text
8765
```

Custom port:

```powershell
.\install.ps1 -Port 8875
```

The installer:

- locates the Windows Codex launcher, including npm `codex.cmd` installs;
- copies the helper to `%ProgramData%\CodexUsageHelper`;
- generates a random 256-bit helper API key;
- creates the Windows HTTP URL reservation;
- creates a Scheduled Task named **Codex Usage Helper** for your Windows user;
- starts the helper when that user logs in;
- creates a Private-profile firewall rule restricted to `LocalSubnet`;
- prints suitable LAN addresses, port and API key.

## Add Local Codex to Home Assistant

**Settings → Devices & services → Add Integration → ChatGPT Usage → Local Codex**

Enter:

```text
Host:      Windows PC LAN IP
Port:      8765
API key:   generated by install.ps1
Use HTTPS: Off
```

Give the Windows PC a DHCP reservation/static LAN IP so the Home Assistant endpoint stays stable.

## Local helper security

Authenticated endpoints only:

```text
GET /api/v1/health
GET /api/v1/usage
```

The helper does not expose or manage:

- OpenAI/Codex OAuth tokens;
- `auth.json`;
- prompts or conversations;
- Codex project files;
- arbitrary filesystem reads;
- arbitrary command execution.

The default connection is authenticated LAN HTTP and is not encrypted. If the LAN is untrusted, put the helper behind HTTPS and enable **Use HTTPS** in Home Assistant.

## Test the helper

The helper API key is stored in:

```text
%ProgramData%\CodexUsageHelper\config.json
```

```powershell
$Config = Get-Content "$env:ProgramData\CodexUsageHelper\config.json" -Raw | ConvertFrom-Json

Invoke-RestMethod `
  -Uri "http://127.0.0.1:$($Config.port)/api/v1/health" `
  -Headers @{ Authorization = "Bearer $($Config.api_key)" }

Invoke-RestMethod `
  -Uri "http://127.0.0.1:$($Config.port)/api/v1/usage" `
  -Headers @{ Authorization = "Bearer $($Config.api_key)" }
```

The `/usage` response contains the official Codex result under:

```text
app_server_result
```

## Remove Local Codex helper

```powershell
.\uninstall.ps1
```

---

# Claude Usage

## Recommended method: Remote Anthropic

1. Install `custom_components/claude_usage` and restart Home Assistant.
2. Open **Settings → Devices & services → Add Integration → Claude Usage**.
3. Select **Remote Anthropic**.
4. Open the authorization URL shown by Home Assistant.
5. Sign into Claude and approve access.
6. Copy the returned authorization code into Home Assistant.

Claude Usage exposes the normal session/five-hour and weekly allowance windows plus model-specific limits and Extra Usage when Anthropic provides them.

A confirmed reset fires:

```text
claude_usage_reset
```

Example notification:

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
        {{ trigger.event.data.new_remaining_percent | default(100) | round(0) }}% remaining.
mode: queued
```

## Claude Local method

Copy:

```text
local_helper
```

to the Windows PC running Claude Code and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

Default Claude helper port:

```text
8766
```

Then select:

**Settings → Devices & services → Add Integration → Claude Usage → Local Claude Code**

and enter the host, port and API key printed by the installer.

---

# Dashboard

Example Lovelace YAML is included in:

```text
dashboards/chatgpt_usage.yaml
dashboards/claude_usage.yaml
dashboards/ai_usage.yaml
```

Home Assistant may generate slightly different entity IDs depending on your existing entity registry. Adjust the examples to match the entities created on your installation.

---

# Troubleshooting

## Integration does not appear

Verify:

```text
/config/custom_components/chatgpt_usage/manifest.json
/config/custom_components/claude_usage/manifest.json
```

Then perform a full Home Assistant restart.

## ChatGPT Remote authentication fails

Repeat the OpenAI device-code flow. Device-code authentication can also be disabled by a workspace administrator.

## ChatGPT Local cannot connect

```powershell
Get-ScheduledTask -TaskName "Codex Usage Helper"
Get-NetFirewallRule -DisplayName "Codex Usage Helper"
codex --version
```

Then run the local health check shown above.

## ChatGPT Local usage fails

Test Codex itself:

```powershell
codex
```

If necessary:

```powershell
codex login
```

The helper uses Codex's authenticated app-server rather than managing credentials itself.

## Diagnostics

**Settings → Devices & services → integration → three-dot menu → Download diagnostics**

Secrets are redacted from diagnostics.

---

# Updating

For manual installations:

1. pull/download the latest repository;
2. replace the relevant `/config/custom_components/...` folder;
3. restart Home Assistant.

If using a Windows helper, rerun its `install.ps1` after helper changes so `%ProgramData%` receives the new helper version.

Do not replace Home Assistant's `.storage` directory. Reset history is persisted there automatically.

---

# API limitations

Remote ChatGPT/Codex mode currently uses interfaces used by the Codex ecosystem, including an undocumented ChatGPT usage endpoint. OpenAI may change that endpoint without notice.

Local ChatGPT/Codex mode is less coupled to the web endpoint because it reads the official open-source Codex app-server `account/rateLimits/read` RPC.

Claude subscription monitoring similarly relies on interfaces used by the Claude ecosystem that are not guaranteed as stable third-party APIs.

OpenAI Platform API-key billing is a separate product and is **not** what ChatGPT Usage monitors.

---

# Development

Tests cover normalization, dynamic limits, official Codex app-server parsing, reset detection and secret redaction.

```bash
python -m compileall custom_components tests
pytest -q
ruff check custom_components tests
```

---

# Attribution

The Claude implementation references concepts from Patrick van Staveren's MIT-licensed `trickv/hass-claude-usage` project.

The ChatGPT/Codex implementation verifies device-auth and usage behaviour against OpenAI's open-source Codex client and the MIT-licensed `LucaFSmart/codex-usage` project.

See `NOTICE.md` and `NOTICE_CHATGPT.md`.
