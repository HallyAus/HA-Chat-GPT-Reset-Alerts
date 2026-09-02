# Codex Usage Helper for Windows

This optional helper lets the `ChatGPT Usage` Home Assistant integration read your ChatGPT/Codex subscription allowance from a Windows PC where the official Codex CLI/app is already authenticated.

## Security model

- Home Assistant authenticates to the helper with a separately generated 256-bit bearer key.
- The Windows firewall rule allows only `LocalSubnet` on the selected port.
- Only `GET /api/v1/health` and `GET /api/v1/usage` exist.
- The helper returns only sanitized usage metadata. It never returns OAuth tokens, prompts, conversations, projects or files.
- The helper can refresh the existing Codex OAuth token when needed. Before writing `auth.json`, it re-reads the file and refuses to overwrite a refresh token that Codex changed concurrently.

## Requirement

Codex must be signed in with your **ChatGPT account**, not an OpenAI API key.

The default credential path is:

```text
%USERPROFILE%\.codex\auth.json
```

If `CODEX_HOME` is defined, the installer uses `%CODEX_HOME%\auth.json` instead.

## Install

Open PowerShell in this directory:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

Default port: `8765`.

Custom port or auth path:

```powershell
.\install.ps1 -Port 8875
.\install.ps1 -AuthPath "D:\Codex\auth.json"
```

The installer prints the host candidates, port and generated API key to enter in Home Assistant.

## Home Assistant

Choose:

```text
Settings → Devices & services → Add integration → ChatGPT Usage → Local Codex
```

## Uninstall

```powershell
.\uninstall.ps1
```
