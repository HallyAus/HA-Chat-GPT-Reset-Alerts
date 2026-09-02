# Claude Usage Helper for Windows

This optional helper lets Home Assistant read Claude subscription usage from a Windows PC where Claude Code is already authenticated.

## Security model

- Home Assistant authenticates to the helper with a random 256-bit bearer key.
- The firewall rule accepts connections only from `LocalSubnet`.
- The helper exposes only `/api/v1/health` and `/api/v1/usage`.
- No command execution or file-reading endpoint is exposed.
- Claude OAuth credentials are never returned to Home Assistant.
- The helper **does not use Claude Code's refresh token**. It reads only the current access token and calls Anthropic's usage endpoint. This avoids consuming a rotating refresh token and interfering with Claude Code.

If Claude Code's access token has expired, use Claude Code normally or sign in again. Once Claude Code refreshes its credentials, the next Home Assistant poll will recover.

## Install

Open PowerShell from this directory:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

The installer elevates to Administrator because it creates a startup task, a URL reservation and a narrow Windows Firewall rule.

Default port: `8766`.

To choose another port:

```powershell
.\install.ps1 -Port 8877
```

The installer prints the host candidates, port and generated API key required by Home Assistant.

## Uninstall

```powershell
.\uninstall.ps1
```

If you used a non-default port, pass it to the uninstaller as well.
