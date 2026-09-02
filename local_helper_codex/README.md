# Codex Usage Helper for Windows

This optional helper lets the `ChatGPT Usage` Home Assistant integration read your ChatGPT/Codex subscription allowance from a Windows PC where the official Codex CLI is already authenticated.

## How it works

The helper does **not** read or copy Codex OAuth credentials. It launches the official local Codex app-server and requests the read-only RPC:

```text
account/rateLimits/read
```

It also calls:

```text
account/read
```

only to confirm the local Codex account type and obtain the plan name when available.

Home Assistant receives only sanitized account/rate-limit metadata returned by Codex app-server.

## Security model

- Home Assistant authenticates to the helper with a separately generated 256-bit bearer key.
- The Windows firewall rule allows only `LocalSubnet` on the selected port.
- Only `GET /api/v1/health` and `GET /api/v1/usage` exist.
- No arbitrary command or filesystem endpoint is exposed.
- The helper never returns OAuth tokens, prompts, conversations, projects or files.
- The helper never opens `%USERPROFILE%\.codex\auth.json`.

## Requirements

- Windows PC with Codex CLI installed.
- `codex` available in PATH.
- Codex signed in with the ChatGPT account whose allowance you want to monitor.
- The Windows user must be logged in while Local mode is running, because Codex authentication belongs to that user context.

Verify before installing:

```powershell
codex --version
```

If needed, sign in:

```powershell
codex login
```

## Install

Open PowerShell in this directory:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

The installer requests Administrator permission to create the HTTP URL reservation, firewall rule and scheduled task.

Default port:

```text
8765
```

Custom port:

```powershell
.\install.ps1 -Port 8875
```

The installer creates a Scheduled Task named **Codex Usage Helper** that runs when your Windows user logs in. It prints the host candidates, port and generated API key to enter in Home Assistant.

## Home Assistant

Choose:

```text
Settings → Devices & services → Add Integration → ChatGPT Usage → Local Codex
```

Enter:

```text
Host:      Windows PC LAN IP
Port:      8765
API key:   key printed by install.ps1
Use HTTPS: Off
```

Give the Windows PC a DHCP reservation/static LAN address so Home Assistant keeps reaching the same IP.

## API

Authenticated endpoints:

```text
GET /api/v1/health
GET /api/v1/usage
```

The usage response carries the `account/rateLimits/read` result under `app_server_result`.

## Uninstall

```powershell
.\uninstall.ps1
```
