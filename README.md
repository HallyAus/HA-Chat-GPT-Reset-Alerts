# AI Usage for Home Assistant

A private Home Assistant repository for monitoring subscription usage and reset times for:

- **ChatGPT / Codex**
- **Claude / Claude Code**

The primary purpose is simple: **notify Home Assistant when an AI usage allowance resets**.

Both integrations default to **one poll per hour** and support persistent reset detection so a Home Assistant restart does not generate a false reset event.

> **Unofficial community project.** This repository is not affiliated with, endorsed by, or supported by OpenAI or Anthropic.

---

## Included integrations

| Integration | HA domain | Recommended mode | Local mode | Reset event |
|---|---|---|---|---|
| ChatGPT Usage | `chatgpt_usage` | Remote OpenAI device login | Official Codex app-server helper | `chatgpt_usage_reset` |
| Claude Usage | `claude_usage` | Remote Anthropic OAuth | Claude Code helper | `claude_usage_reset` |

You can install either integration or both.

---

# Installation

## This repository is private

While `HallyAus/HA_Ai_Usage` remains private, install the custom components manually.

Clone or download:

```text
https://github.com/HallyAus/HA_Ai_Usage
```

Copy ChatGPT/Codex:

```text
custom_components/chatgpt_usage
```

to:

```text
/config/custom_components/chatgpt_usage
```

Copy Claude:

```text
custom_components/claude_usage
```

to:

```text
/config/custom_components/claude_usage
```

Do **not** copy the whole repository into `/config/custom_components`.

Your Home Assistant filesystem should contain paths such as:

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

> HACS metadata is included for development, but this private monorepo contains two integrations. Manual installation is the intended installation method while it remains private.

---

# ChatGPT / Codex Usage

## Recommended: Remote OpenAI

Use Remote OpenAI unless you specifically want OpenAI OAuth credentials to remain off Home Assistant.

```text
Home Assistant
      │
      ▼
OpenAI device-code login
      │
      ▼
ChatGPT/Codex usage service
      │
      ▼
5-hour / weekly / additional usage windows
      │
      ▼
chatgpt_usage_reset
```

Your Windows PC does **not** need to be on.

## Remote OpenAI setup

1. Install `custom_components/chatgpt_usage` and restart Home Assistant.
2. Open **Settings → Devices & services → Add Integration → ChatGPT Usage**.
3. Select **Remote OpenAI**.
4. Home Assistant displays an OpenAI device-login URL and temporary code.
5. Open the URL on your phone or computer.
6. Sign into the ChatGPT account that has Codex access.
7. Enter the temporary code when requested and approve access.
8. Return to Home Assistant and confirm that sign-in is complete.
9. If OpenAI exposes more than one workspace, select the workspace to monitor.
10. Home Assistant validates the usage service and creates the integration.

The integration stores its own OAuth credentials in Home Assistant config-entry storage and refreshes them automatically. Tokens are never exposed as entities, event data or diagnostics.

## ChatGPT entities

Depending on what OpenAI returns for your account, entities include:

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

Additional metered limits are created dynamically rather than hard-coded to one fixed model list.

If OpenAI only returns a weekly window, only the weekly entities are created. A weekly window is never guessed to be a five-hour window based on its position in the response.

## ChatGPT reset event

A confirmed allowance rollover fires:

```text
chatgpt_usage_reset
```

Example event data:

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

Reset state is persisted in Home Assistant storage. First startup, small rounding changes and temporary API failures do not count as resets.

## ChatGPT phone notification

Replace `notify.mobile_app_your_phone` with your actual Home Assistant mobile notification action.

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

## ChatGPT polling

Default:

```text
3600 seconds / 1 hour
```

Available options:

- 15 minutes
- 30 minutes
- 1 hour
- 2 hours
- 4 hours

With hourly polling, a reset at 14:17 may be detected at the 15:00 poll. The reset sensor still stores the exact timestamp returned by OpenAI/Codex.

---

# ChatGPT Local mode — Codex on Windows

Local mode is for users who want **no OpenAI OAuth credentials stored in Home Assistant**.

The current helper uses the **official Codex app-server**. It does not open Codex's `auth.json` and does not copy, refresh or return OAuth tokens.

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

OpenAI's current Codex app-server exposes the rate-limit snapshot through:

```text
account/rateLimits/read
```

The helper only forwards sanitized usage metadata from that RPC.

## Local Codex requirements

On the Windows PC:

```powershell
codex --version
```

must work.

Codex must already be signed into the ChatGPT account you want to monitor. If needed:

```powershell
codex login
```

Because Codex authentication belongs to your Windows user context, the helper runs when that user is logged in.

## Install the Codex helper

Copy this repository folder to the Windows PC:

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

- copies the helper to `%ProgramData%\CodexUsageHelper`;
- generates a random 256-bit helper API key;
- creates the required Windows HTTP URL reservation;
- creates a Scheduled Task named **Codex Usage Helper** under your logged-in Windows user;
- starts the helper when that user logs in;
- creates a Private-profile Windows Firewall rule restricted to `LocalSubnet`;
- prints suitable LAN IPv4 addresses, the port and API key.

## Add Local Codex to Home Assistant

Go to:

**Settings → Devices & services → Add Integration → ChatGPT Usage → Local Codex**

Enter:

```text
Host:      Windows PC LAN IP
Port:      8765
API key:   generated by install.ps1
Use HTTPS: Off
```

Give the Windows PC a DHCP reservation/static LAN IP so Home Assistant can continue reaching it.

## Local Codex security

The helper exposes only:

```text
GET /api/v1/health
GET /api/v1/usage
```

It does not expose:

- OAuth tokens;
- `auth.json`;
- prompts or conversations;
- Codex projects;
- arbitrary filesystem reads;
- arbitrary command execution.

Home Assistant uses a separate random bearer key to access the helper.

The default helper connection is authenticated LAN HTTP, not encrypted HTTP. On a trusted home LAN this is normally sufficient. For an untrusted network, put it behind HTTPS and enable **Use HTTPS** in the integration.

## Test Local Codex helper

The helper API key is stored in:

```text
%ProgramData%\CodexUsageHelper\config.json
```

Health check:

```powershell
$Config = Get-Content "$env:ProgramData\CodexUsageHelper\config.json" -Raw | ConvertFrom-Json
Invoke-RestMethod `
  -Uri "http://127.0.0.1:$($Config.port)/api/v1/health" `
  -Headers @{ Authorization = "Bearer $($Config.api_key)" }
```

Usage check:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:$($Config.port)/api/v1/usage" `
  -Headers @{ Authorization = "Bearer $($Config.api_key)" }
```

The usage response contains the official Codex app-server rate-limit result under:

```text
app_server_result
```

## Remove Local Codex helper

From `local_helper_codex`:

```powershell
.\uninstall.ps1
```

---

# Claude Usage

## Recommended: Remote Anthropic

1. Install `custom_components/claude_usage` and restart Home Assistant.
2. Go to **Settings → Devices & services → Add Integration → Claude Usage**.
3. Select **Remote Anthropic**.
4. Open the authorization URL shown by Home Assistant.
5. Sign into Claude and approve access.
6. Copy the returned authorization code into Home Assistant.

The integration exposes the session/five-hour and weekly allowance windows, model-specific limits, and Extra Usage when Anthropic provides them.

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

## Claude Local mode

Copy:

```text
local_helper
```

to the Windows PC running Claude Code, then run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

Claude helper default port:

```text
8766
```

Then choose:

**Settings → Devices & services → Add Integration → Claude Usage → Local Claude Code**

and enter the host, port and API key printed by the installer.

---

# Dashboard

Example Lovelace cards are included in:

```text
dashboards/chatgpt_usage.yaml
dashboards/claude_usage.yaml
dashboards/ai_usage.yaml
```

Home Assistant may generate slightly different entity IDs depending on your existing entity registry. Adjust the YAML after installation if needed.

A useful combined view is:

| AI | Short window | Weekly | Next reset |
|---|---:|---:|---|
| ChatGPT / Codex | Remaining % | Remaining % | timestamp |
| Claude | Remaining % | Remaining % | timestamp |

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

Repeat the OpenAI device-code flow. Workspace administrators can disable device-code authentication.

## ChatGPT Local cannot connect

On Windows:

```powershell
Get-ScheduledTask -TaskName "Codex Usage Helper"
Get-NetFirewallRule -DisplayName "Codex Usage Helper"
codex --version
```

Then run the health check above.

## ChatGPT Local usage returns an error

First test Codex itself:

```powershell
codex
```

If authentication is required:

```powershell
codex login
```

The helper uses Codex's own authenticated app-server rather than managing credentials itself.

## Download diagnostics

For either integration:

**Settings → Devices & services → integration → three-dot menu → Download diagnostics**

Credentials are redacted from diagnostics.

---

# Updating

Because this is currently a private/manual installation:

1. pull or download the latest repository;
2. replace the relevant `/config/custom_components/...` folder;
3. restart Home Assistant.

If using a Windows helper, rerun its `install.ps1` after helper changes so the copy under `%ProgramData%` is updated.

Do not replace Home Assistant's `.storage` directory. Reset history is persisted there automatically.

---

# Important API limitations

Remote ChatGPT/Codex usage currently relies on OpenAI interfaces used by the Codex ecosystem, including an undocumented ChatGPT usage endpoint. OpenAI can change that interface without notice.

Local ChatGPT/Codex mode is less coupled to that web endpoint because it uses the official open-source Codex app-server `account/rateLimits/read` RPC.

Claude subscription usage similarly depends on interfaces used by the Claude ecosystem that are not guaranteed as stable third-party APIs.

OpenAI Platform API-key billing is a different product and is **not** what ChatGPT Usage monitors.

---

# Development

Tests cover usage normalization, dynamic limits, official Codex app-server response parsing, reset detection and secret redaction.

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
