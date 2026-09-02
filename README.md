# Claude Usage for Home Assistant

A Home Assistant custom integration for monitoring **Claude / Claude Code subscription usage** and firing an event when an allowance resets.

It supports two connection methods:

1. **Remote Anthropic** — Home Assistant connects directly to Anthropic. Your Windows PC does not need to be running.
2. **Local Claude Code** — Home Assistant reads sanitized usage information from a helper running on your Windows PC. Claude credentials stay on the PC.

> **Unofficial community integration.** This project is not affiliated with, endorsed by, or supported by Anthropic.

---

## What it does

The integration can expose:

- 5-hour/session usage percentage
- 5-hour/session remaining percentage
- 5-hour/session reset timestamp
- 5-hour/session time remaining
- weekly usage percentage
- weekly remaining percentage
- weekly reset timestamp
- weekly time remaining
- model-specific limits returned by Anthropic
- Extra Usage / spend information where available
- connection status
- last successful update
- manual refresh button
- reset detection that survives Home Assistant restarts
- `claude_usage_reset` Home Assistant events

Default polling is **once per hour**.

---

# Recommended setup

For most people, use **Remote Anthropic**.

| Method | Best for | PC must be on? | Claude credentials stored in HA? |
|---|---|---:|---:|
| **Remote Anthropic** | Easiest and most reliable monitoring | No | Yes, OAuth tokens |
| **Local Claude Code** | Keeping Claude OAuth credentials off HA | Yes | No |

If your only goal is:

> Alert me when my Claude usage resets

use **Remote Anthropic** unless you specifically want the local privacy model.

---

# Installation

## Important: this repository is private

HACS does not install private GitHub repositories in the normal custom-repository workflow.

While this repository remains private, install it manually.

The Home Assistant integration folder is:

```text
custom_components/claude_usage
```

It must end up on Home Assistant as:

```text
/config/custom_components/claude_usage
```

Your final Home Assistant filesystem should contain files such as:

```text
/config/custom_components/claude_usage/__init__.py
/config/custom_components/claude_usage/manifest.json
/config/custom_components/claude_usage/config_flow.py
/config/custom_components/claude_usage/coordinator.py
/config/custom_components/claude_usage/sensor.py
/config/custom_components/claude_usage/binary_sensor.py
/config/custom_components/claude_usage/button.py
/config/custom_components/claude_usage/translations/en.json
```

Do **not** copy the entire GitHub repository into `custom_components`.

Only copy the `claude_usage` integration folder.

---

## Step 1 — Download the repository

While signed into GitHub, open:

```text
https://github.com/HallyAus/HA_Ai_Usage
```

Then either clone it:

```bash
git clone https://github.com/HallyAus/HA_Ai_Usage.git
```

or use GitHub's **Code → Download ZIP** option.

Because this is a private repository, GitHub authentication is required.

---

## Step 2 — Copy the integration into Home Assistant

Copy:

```text
HA_Ai_Usage/custom_components/claude_usage
```

to:

```text
/config/custom_components/claude_usage
```

You can do this with whichever Home Assistant file-access method you already use, for example:

- Samba share
- SSH / SCP
- Studio Code Server add-on
- another Home Assistant file-management method

If `/config/custom_components` does not exist, create it.

The directory name must be exactly:

```text
claude_usage
```

---

## Step 3 — Restart Home Assistant

Perform a full Home Assistant restart:

**Settings → System → Restart Home Assistant**

After the restart, continue to configuration.

---

# Configuration

Open:

**Settings → Devices & services → Add Integration**

Search for:

```text
Claude Usage
```

The integration asks you to choose:

```text
Remote Anthropic
```

or:

```text
Local Claude Code
```

---

# Option A — Remote Anthropic

This is the recommended setup.

Architecture:

```text
Home Assistant
      │
      ▼
Anthropic OAuth
      │
      ▼
Claude subscription usage
      │
      ▼
Home Assistant entities
      │
      ▼
claude_usage_reset event
```

Your Windows PC does not need to be running.

## Remote setup — step by step

### 1. Add the integration

Go to:

**Settings → Devices & services → Add Integration → Claude Usage**

Select:

```text
Remote Anthropic
```

### 2. Open the authorization URL

Home Assistant displays an Anthropic authorization URL.

Open that URL in your browser.

Sign into the Claude account whose usage you want to monitor.

Approve the authorization request.

### 3. Copy the authorization code

Anthropic returns an authorization code.

Copy that code and paste it into the **Authorization code** field in Home Assistant.

Submit the form.

### 4. Confirm the integration loads

Home Assistant should create a device called approximately:

```text
Claude Usage
```

Within the device you should see the available usage entities returned by your account.

Not every Claude account exposes exactly the same limits.

Typical entities include:

```text
5 hour usage
5 hour remaining
5 hour reset
5 hour time remaining

Weekly usage
Weekly remaining
Weekly reset
Weekly time remaining
```

Additional model/surface-specific meters are created dynamically when Anthropic provides them.

### 5. Check polling interval

Open:

**Settings → Devices & services → Claude Usage → Configure**

Default:

```text
3600 seconds
```

which equals:

```text
1 hour
```

Supported options are intended to include:

```text
900     = 15 minutes
1800    = 30 minutes
3600    = 1 hour
7200    = 2 hours
14400   = 4 hours
```

For normal use, leave it at **3600**.

---

# Option B — Local Claude Code

Use this if you prefer that Home Assistant never receives your Claude OAuth token.

Architecture:

```text
Claude Code on Windows
        │
        ▼
Claude Usage Helper
        │
        │ LAN
        ▼
Home Assistant
        │
        ▼
Same entities and reset events
```

Claude's OAuth credentials remain on the Windows PC.

Home Assistant receives only sanitized usage metadata.

---

## Local mode prerequisites

You need:

- Windows 11 or compatible Windows installation
- Claude Code installed
- Claude Code already logged into your Claude account
- Home Assistant able to reach the Windows PC over your LAN
- PowerShell Administrator access for helper installation

The helper expects Claude Code's credentials under the normal Claude location such as:

```text
%USERPROFILE%\.claude\.credentials.json
```

---

## Step 1 — Copy the helper folder to Windows

From this repository, copy:

```text
local_helper
```

to the Windows PC running Claude Code.

For example:

```text
C:\ClaudeUsageHelper
```

The folder should contain:

```text
claude_usage_helper.ps1
install.ps1
uninstall.ps1
README.md
```

---

## Step 2 — Install the Windows helper

Open PowerShell in the helper directory.

Run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

The installer may elevate to Administrator.

It configures:

- a generated 256-bit helper API key
- a startup Scheduled Task
- Windows HTTP URL reservation
- a Windows Firewall rule restricted to `LocalSubnet`
- the default helper port

Default port:

```text
8766
```

To use another port:

```powershell
.\install.ps1 -Port 8877
```

---

## Step 3 — Record the values printed by the installer

At the end, the installer prints information similar to:

```text
Claude Usage Helper installed successfully.

Host:
192.168.1.50

Port:
8766

API key:
xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Save:

- Host/IP address
- Port
- API key

You need those values in Home Assistant.

---

## Step 4 — Add Local Claude Code to Home Assistant

Go to:

**Settings → Devices & services → Add Integration → Claude Usage**

Select:

```text
Local Claude Code
```

Enter:

```text
Host:      Windows PC LAN IP
Port:      8766
API key:   value printed by install.ps1
Use HTTPS: off
```

For a normal trusted home LAN, leave **Use HTTPS** disabled unless you have separately configured HTTPS for the helper.

Submit the form.

Home Assistant validates the helper before creating the config entry.

---

## Step 5 — Test the helper manually if needed

The helper exposes only:

```text
GET /api/v1/health
GET /api/v1/usage
```

Both are authenticated.

There is no remote command endpoint and no arbitrary file-read API.

The helper uses a separate bearer key for Home Assistant.

It never sends Claude OAuth credentials back to Home Assistant.

### Important local-token behaviour

The helper reads only Claude Code's current access token.

It deliberately does **not** consume or rotate Claude Code's refresh token.

This avoids the helper accidentally invalidating Claude Code's own authentication state.

If the Claude Code access token expires while Claude Code has been idle:

1. open/use Claude Code normally, or sign into Claude Code again;
2. Claude Code refreshes its own credentials;
3. the next Home Assistant poll should recover automatically.

---

# Usage entities

Home Assistant entity IDs depend on your installation and existing entity registry, so use the entity names shown in the UI rather than assuming exact IDs.

## Main session window

Typical entities:

```text
Claude 5 hour usage
Claude 5 hour remaining
Claude 5 hour reset
Claude 5 hour time remaining
```

## Weekly window

```text
Claude weekly usage
Claude weekly remaining
Claude weekly reset
Claude weekly time remaining
```

## Model-specific limits

Anthropic can return additional limit buckets.

The integration creates those dynamically, for example:

```text
Claude weekly Opus usage
Claude weekly Opus remaining
Claude weekly Opus reset
```

The exact model names depend on Anthropic's response.

## Extra Usage

If Anthropic exposes Extra Usage/spend data, the integration can create entities for:

```text
Extra Usage enabled
Extra Usage percentage
Extra Usage spent
Extra Usage remaining
Extra Usage limit
```

## General entities

Typical general entities include:

```text
Plan
Last update
Connected
Limit reached
Refresh
```

---

# How reset detection works

The integration stores a small non-sensitive snapshot of each usage window in Home Assistant storage.

It does not simply look for a percentage moving down by one point.

A reset is considered confirmed when the usage window clearly rolls over.

Signals include:

- reset timestamp moves forward to a new window;
- previous reset time has arrived;
- usage percentage falls significantly;
- remaining percentage increases significantly.

Example:

```text
Before
Weekly usage: 100%
Reset: 14:17

After
Weekly usage: 2%
Next reset: next week's timestamp
```

That is considered a genuine reset.

The following should **not** create reset alerts:

```text
51% → 50%
```

or:

- first integration startup
- Home Assistant restart
- temporary API failure
- temporary missing bucket
- bucket ordering change
- small rounding changes

Reset state is persisted so restarting Home Assistant does not repeatedly send the same reset notification.

---

# Create the reset notification

The integration fires this Home Assistant event:

```text
claude_usage_reset
```

when a reset is confirmed.

This is the recommended trigger for phone notifications.

---

## Notification for any Claude reset

Create a new automation in Home Assistant and use this YAML:

```yaml
alias: Claude usage reset
description: Notify when a Claude usage window resets
triggers:
  - trigger: event
    event_type: claude_usage_reset
conditions: []
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: Claude usage reset
      message: >-
        {{ trigger.event.data.window }} allowance has reset.
        {{ trigger.event.data.remaining_percent | default(100) | round(0) }}% remaining.
mode: queued
```

Replace:

```text
notify.mobile_app_your_phone
```

with your actual Home Assistant Companion App notify service.

You can find the correct service in Home Assistant under:

**Developer Tools → Actions**

and search for:

```text
notify.mobile_app
```

---

# Weekly reset notification only

If you only care about the weekly limit:

```yaml
alias: Claude weekly allowance reset
description: Notify only when the Claude weekly allowance resets
triggers:
  - trigger: event
    event_type: claude_usage_reset
conditions:
  - condition: template
    value_template: >-
      {{ trigger.event.data.window_id == 'weekly' }}
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: Claude weekly usage reset
      message: >-
        Your weekly Claude allowance is available again.
        {{ trigger.event.data.remaining_percent | default(100) | round(0) }}% remaining.
mode: queued
```

---

# Low remaining warning

You can also create a standard numeric-state automation using the generated **Weekly remaining** sensor.

Example:

```yaml
alias: Claude weekly usage low
triggers:
  - trigger: numeric_state
    entity_id: sensor.your_claude_weekly_remaining_entity
    below: 10
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: Claude usage
      message: Weekly Claude allowance is below 10%.
mode: single
```

Replace the placeholder entity with your actual generated entity ID.

---

# Dashboard

A basic dashboard example is included at:

```text
dashboards/claude_usage.yaml
```

Because Home Assistant assigns entity IDs, edit the example after setup to match your actual entities.

A simple Entities card can contain:

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

---

# Manual refresh

The integration creates a **Refresh** button entity.

Press it from the device page when you want an immediate update rather than waiting for the next scheduled coordinator poll.

Normal scheduled polling should remain at one hour unless you have a reason to change it.

---

# Troubleshooting

## Claude Usage does not appear in Add Integration

Check that this exact path exists:

```text
/config/custom_components/claude_usage/manifest.json
```

Then restart Home Assistant again.

Also inspect:

**Settings → System → Logs**

for `claude_usage` errors.

---

## Remote mode says authentication failed

Remove/reconfigure the integration and repeat the Anthropic authorization flow.

Make sure you authorize the same Claude account you want to monitor.

OAuth authorization codes are short-lived and generally should be pasted into Home Assistant immediately.

---

## Remote mode becomes unavailable

Possible causes include:

- Anthropic outage
- expired/invalid OAuth token
- temporary rate limiting
- Anthropic changing the undocumented usage interface

The integration will not fabricate a zero value when data cannot be retrieved.

The **Last update** entity can help identify stale data.

---

## Local mode cannot connect

Check:

1. the Windows PC is powered on;
2. its LAN IP has not changed;
3. the helper Scheduled Task is running;
4. Windows Firewall still allows the selected helper port;
5. Home Assistant is on a network that can reach the PC;
6. the Home Assistant API key matches the key printed/generated by the helper installer.

If your PC receives IP addresses by DHCP, consider creating a DHCP reservation in your router so its address remains stable.

---

## Local mode says Claude is not authenticated

Open Claude Code on Windows and confirm it is logged in.

Use Claude Code once so it can refresh its access token if necessary.

Then press the Home Assistant **Refresh** button or wait for the next poll.

---

## Usage entities are missing

Anthropic does not necessarily expose every bucket to every plan/account.

The integration creates entities based on what the account actually returns.

For example, a model-specific weekly limit may not exist until Anthropic provides that bucket for the account.

---

# Diagnostics

In Home Assistant:

**Settings → Devices & services → Claude Usage → three-dot menu → Download diagnostics**

Diagnostics can include safe information such as:

- integration version
- provider type
- polling interval
- last update
- window IDs
- usage percentages
- reset timestamps
- helper API version

The integration redacts credentials such as:

- Anthropic access token
- Anthropic refresh token
- helper API key
- Authorization header

---

# Security

## Remote Anthropic

- Anthropic requests use HTTPS.
- OAuth credentials are stored in the Home Assistant config entry.
- Tokens are not exposed as normal entity attributes.
- Diagnostics redact authentication values.

## Local Claude Code

- Claude OAuth credentials stay on the Windows PC.
- Home Assistant uses a separate random bearer API key.
- The helper exposes usage-only endpoints.
- The helper has no remote command execution API.
- The default Windows firewall rule is restricted to `LocalSubnet`.
- Plain HTTP is used on the LAN by default.

The bearer key authenticates requests but does not encrypt LAN traffic.

If the LAN is untrusted, place the helper behind HTTPS and enable **Use HTTPS** in the integration.

---

# Updating the integration

Because the repository is private, updates are manual while private.

1. Download/pull the latest repository version.
2. Replace:

```text
/config/custom_components/claude_usage
```

with the newer repository version.

3. Restart Home Assistant.

Do not delete the Home Assistant config entry unless an update specifically requires reconfiguration.

Your stored config and reset state live in Home Assistant, not inside the integration source folder.

---

# Uninstalling

## Remove from Home Assistant

Go to:

**Settings → Devices & services → Claude Usage**

Remove the config entry.

Then delete:

```text
/config/custom_components/claude_usage
```

Restart Home Assistant.

## Remove Local Claude Code helper

On the Windows PC, open PowerShell in the helper folder:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\uninstall.ps1
```

If you installed using a non-default port, use the corresponding port option required by the uninstall script.

The uninstaller removes the helper task/firewall/URL reservation configuration.

It does not uninstall or modify Claude Code itself.

---

# If the repository is later made public

The repository contains:

```text
hacs.json
```

and Home Assistant/HACS validation metadata.

If the repository is made public, you can add it to HACS as a custom integration repository:

```text
https://github.com/HallyAus/HA_Ai_Usage
```

Then HACS can manage installation/update of the Home Assistant component.

While it remains private, use the manual installation process above.

---

# Known limitation

Claude subscription usage is currently obtained from Anthropic's OAuth usage interface:

```text
https://api.anthropic.com/api/oauth/usage
```

This is used in the Claude ecosystem but is **not documented as a stable public third-party subscription-usage API**.

Anthropic may change:

- endpoint path
- OAuth behaviour
- response schema
- available buckets
- rate-limit representation

without notice.

The integration keeps Anthropic request/parsing logic separate from Home Assistant entities so upstream changes can be repaired without rebuilding the entire integration.

---

# Development

Local checks:

```bash
python -m compileall custom_components tests
pytest -q
ruff check custom_components tests
```

The repository also contains a GitHub Actions validation workflow for:

- Ruff
- pytest
- Home Assistant hassfest
- HACS validation

---

# Attribution

This project was independently structured for dual Remote/Local Home Assistant monitoring, while referencing current OAuth/usage behaviour and concepts from Patrick van Staveren's MIT-licensed `trickv/hass-claude-usage` project.

See:

```text
NOTICE.md
LICENSE
```
