# AI Usage for Home Assistant

A private Home Assistant integration repository for monitoring subscription usage and reset times for:

- **Claude / Claude Code**
- **ChatGPT / Codex**

Both integrations are read-only. Their primary purpose is to let Home Assistant notify you when an AI allowance resets.

> **Unofficial community project.** This repository is not affiliated with, endorsed by, or supported by Anthropic or OpenAI.

---

## What is included

| Integration | Home Assistant domain | Remote mode | Local mode | Reset event |
|---|---|---|---|---|
| Claude Usage | `claude_usage` | Anthropic OAuth | Claude Code Windows helper | `claude_usage_reset` |
| ChatGPT Usage | `chatgpt_usage` | OpenAI device login | Codex Windows helper | `chatgpt_usage_reset` |

Both default to **one poll per hour**.

The repo also contains Windows helpers and basic Lovelace examples.

---

# Installation while this repository is private

HACS does not normally install private GitHub custom repositories. While `HallyAus/HA_Ai_Usage` remains private, install the integrations manually.

This repository also contains **two** Home Assistant integrations. HACS distribution is designed around one integration per repository, so if this project is later made public for HACS, split Claude and ChatGPT into separate repositories or merge them into one combined `ai_usage` integration first.

Clone or download:

```text
https://github.com/HallyAus/HA_Ai_Usage
```

For Claude, copy:

```text
custom_components/claude_usage
```

to:

```text
/config/custom_components/claude_usage
```

For ChatGPT/Codex, copy:

```text
custom_components/chatgpt_usage
```

to:

```text
/config/custom_components/chatgpt_usage
```

You can install either integration or both.

Then restart Home Assistant:

**Settings → System → Restart Home Assistant**

After restart, go to:

**Settings → Devices & services → Add Integration**

and search for **Claude Usage** and/or **ChatGPT Usage**.

---

# ChatGPT / Codex Usage

## Recommended method: Remote OpenAI

Use this unless you specifically want ChatGPT OAuth credentials to remain off Home Assistant.

Remote architecture:

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
5-hour + weekly usage / reset data
      │
      ▼
chatgpt_usage_reset event
```

Your Windows PC does **not** need to be running.

### Remote setup

1. Copy `custom_components/chatgpt_usage` into `/config/custom_components/chatgpt_usage`.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add Integration → ChatGPT Usage**.
4. Select **Remote OpenAI**.
5. Home Assistant displays an OpenAI device-login URL and temporary code.
6. Open the displayed URL on your phone/computer.
7. Sign into the ChatGPT account that has Codex access.
8. Enter the temporary code if OpenAI asks for it and approve access.
9. Return to Home Assistant and tick **I completed OpenAI sign-in**.
10. If the account exposes multiple ChatGPT workspaces, choose the one to monitor.
11. Home Assistant validates the usage endpoint and creates the integration.

The integration stores its own OAuth credentials in the Home Assistant config entry and refreshes them automatically.

### ChatGPT entities

Exact entity IDs depend on Home Assistant naming, but the integration creates entities equivalent to:

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

If OpenAI returns extra metered rate limits, additional window sensors are created dynamically.

### ChatGPT reset event

A confirmed allowance rollover fires:

```text
chatgpt_usage_reset
```

Example event payload:

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

The integration stores non-sensitive previous-window state so a Home Assistant restart does not fire a false reset notification.

### ChatGPT reset notification automation

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

Weekly only:

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

### Polling

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

With hourly polling, a reset that occurs at 14:17 may be detected at the 15:00 poll. The reset sensor still shows the exact reset timestamp returned by OpenAI.

---

## ChatGPT local method: Codex on Windows

Use this mode if you want the ChatGPT OAuth credentials to stay on the Windows PC that already runs Codex.

Architecture:

```text
Codex auth.json on Windows
        │
        ▼
Codex Usage Helper
        │
        │ authenticated LAN request
        ▼
Home Assistant
        │
        ▼
same sensors + chatgpt_usage_reset event
```

### Windows requirement

Codex must be signed in using your **ChatGPT account** rather than only an OpenAI API key.

The helper normally reads:

```text
%USERPROFILE%\.codex\auth.json
```

If `CODEX_HOME` is set, it uses:

```text
%CODEX_HOME%\auth.json
```

### Install the Codex helper

Copy this repo directory to the Windows machine:

```text
local_helper_codex
```

Open PowerShell in that folder and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

Default port:

```text
8765
```

The installer:

- copies the helper into `%ProgramData%\CodexUsageHelper`;
- creates a random 256-bit local API key;
- installs a Scheduled Task called **Codex Usage Helper**;
- starts it at Windows boot;
- creates a Private-profile Windows Firewall rule limited to `LocalSubnet`;
- finds likely LAN IPv4 addresses;
- prints the host, port and API key for Home Assistant.

Custom port:

```powershell
.\install.ps1 -Port 8875
```

Custom auth path:

```powershell
.\install.ps1 -AuthPath "D:\Codex\auth.json"
```

### Add Local Codex to Home Assistant

Go to:

**Settings → Devices & services → Add Integration → ChatGPT Usage → Local Codex**

Enter the values printed by `install.ps1`:

```text
Host:      Windows PC LAN IP
Port:      8765
API key:   generated key
Use HTTPS: Off
```

Give the Windows PC a DHCP reservation/static LAN address so the Home Assistant connection does not break when its IP changes.

### Local helper security

The helper exposes only:

```text
GET /api/v1/health
GET /api/v1/usage
```

It does **not** expose:

- prompts or conversation history;
- Codex project files;
- arbitrary filesystem reads;
- arbitrary command execution;
- OAuth access/refresh/id tokens.

The helper can refresh Codex OAuth credentials when the access token expires. Before writing `auth.json`, it re-reads the file and will not overwrite a newer refresh token written by Codex concurrently.

To remove it:

```powershell
.\uninstall.ps1
```

---

# Claude Usage

## Recommended method: Remote Anthropic

1. Copy `custom_components/claude_usage` into `/config/custom_components/claude_usage`.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add Integration → Claude Usage**.
4. Select **Remote Anthropic**.
5. Open the authorization URL shown by Home Assistant.
6. Sign into Claude and approve access.
7. Copy the returned authorization code into Home Assistant.

The integration exposes the normal 5-hour/session and weekly allowance windows plus model-specific limits and Extra Usage where Anthropic returns them.

A reset fires:

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

## Claude local method

Copy:

```text
local_helper
```

to the Windows PC running Claude Code, then run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

Claude's helper defaults to port:

```text
8766
```

Then choose:

**Settings → Devices & services → Add Integration → Claude Usage → Local Claude Code**

and enter the host, port and API key printed by its installer.

---

# Dashboard

Example card YAML files are included in:

```text
dashboards/claude_usage.yaml
dashboards/chatgpt_usage.yaml
```

Home Assistant may choose slightly different entity IDs. Adjust the YAML after installation using the entity IDs created on your system.

A useful combined dashboard contains:

| AI | 5-hour/session | Weekly | Next reset |
|---|---:|---:|---|
| ChatGPT / Codex | Remaining % | Remaining % | timestamp |
| Claude | Remaining % | Remaining % | timestamp |

---

# Diagnostics and troubleshooting

For either integration:

**Settings → Devices & services → integration → three-dot menu → Download diagnostics**

Diagnostics intentionally redact credentials.

## Integration not shown after manual installation

Check the folder path carefully:

```text
/config/custom_components/claude_usage/manifest.json
/config/custom_components/chatgpt_usage/manifest.json
```

Then perform a full Home Assistant restart.

## ChatGPT Remote says authentication failed

Remove/re-authenticate the config entry and repeat the OpenAI device-code flow. Device-code login can also be disabled by a workspace administrator.

## ChatGPT Local cannot connect

On Windows check:

```powershell
Get-ScheduledTask -TaskName "Codex Usage Helper"
Get-NetFirewallRule -DisplayName "Codex Usage Helper"
```

Test locally using the API key from:

```text
%ProgramData%\CodexUsageHelper\config.json
```

Then:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8765/api/v1/health `
  -Headers @{ Authorization = "Bearer YOUR_KEY" }
```

## ChatGPT Local says Codex authentication is missing

Run:

```powershell
codex login
```

and use ChatGPT/device-code sign-in. The local helper does not monitor API-key billing usage.

---

# Privacy and security

## Remote modes

Remote mode stores OAuth tokens in Home Assistant's config-entry storage and sends HTTPS requests directly to Anthropic/OpenAI.

Tokens are not exposed through sensors, reset events or diagnostics.

## Local modes

Local mode keeps the service OAuth credentials on the Windows PC. Home Assistant gets a separate randomly generated helper API key and only sanitized usage metadata.

The default helper HTTP connection is LAN-only and authenticated but **not encrypted**. If the LAN is untrusted, place the helper behind an HTTPS reverse proxy and enable `Use HTTPS` in Home Assistant.

---

# Important API limitations

Claude subscription usage and ChatGPT/Codex usage are currently obtained through interfaces used by their respective first-party ecosystems, but these are not guaranteed stable third-party APIs.

The provider-specific request/parsing code is isolated so upstream endpoint or schema changes can be repaired without rewriting the Home Assistant entity/reset layers.

OpenAI Platform API-key billing is a different product and is **not** what the ChatGPT integration monitors.

---

# Updating

Because this is a private repo/manual install:

1. pull/download the latest repository;
2. replace the relevant `/config/custom_components/...` directory;
3. restart Home Assistant.

Do not replace your Home Assistant `.storage` directory. Reset history is persisted there by Home Assistant automatically.

---

# Development

Tests cover normalization, dynamic limits, reset detection and secret redaction.

```bash
python -m compileall custom_components tests
pytest -q
ruff check custom_components tests
```

---

# Attribution

The Claude implementation references concepts from Patrick van Staveren's MIT-licensed `trickv/hass-claude-usage` project.

The ChatGPT/Codex implementation verifies device-auth and usage protocol behaviour against OpenAI's open-source Codex client and the MIT-licensed `LucaFSmart/codex-usage` project.

See `NOTICE.md` and `NOTICE_CHATGPT.md`.
