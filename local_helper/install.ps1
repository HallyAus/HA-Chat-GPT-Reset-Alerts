[CmdletBinding()]
param(
    [int]$Port = 8766
)

$ErrorActionPreference = "Stop"
$TaskName = "Claude Usage Helper"
$InstallDir = "$env:ProgramData\ClaudeUsageHelper"
$ConfigPath = Join-Path $InstallDir "config.json"
$TargetScript = Join-Path $InstallDir "claude_usage_helper.ps1"
$FirewallName = "Claude Usage Helper TCP $Port"
$UrlPrefix = "http://+:$Port/"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdministrator)) {
    $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "-Port", $Port)
    Start-Process powershell.exe -Verb RunAs -ArgumentList $args
    exit
}

$UserProfilePath = $env:USERPROFILE
$CredentialPath = Join-Path $UserProfilePath ".claude\.credentials.json"
if (-not (Test-Path $CredentialPath)) {
    Write-Warning "Claude Code credentials were not found at: $CredentialPath"
    Write-Warning "Run Claude Code and sign in before testing Local mode. The helper can still be installed."
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
Copy-Item -Path (Join-Path $PSScriptRoot "claude_usage_helper.ps1") -Destination $TargetScript -Force

$random = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($random)
$ApiKey = [Convert]::ToBase64String($random).TrimEnd("=").Replace("+", "-").Replace("/", "_")
@{
    api_key = $ApiKey
    port = $Port
    user_profile = $UserProfilePath
    installed_at = (Get-Date).ToUniversalTime().ToString("o")
} | ConvertTo-Json | Set-Content -Path $ConfigPath -Encoding UTF8

icacls $ConfigPath /inheritance:r /grant:r "SYSTEM:F" "Administrators:F" "$env:USERNAME:R" | Out-Null
& netsh http delete urlacl url=$UrlPrefix 2>$null | Out-Null
& netsh http add urlacl url=$UrlPrefix user="NT AUTHORITY\SYSTEM" | Out-Null

Get-NetFirewallRule -DisplayName $FirewallName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $FirewallName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -RemoteAddress LocalSubnet | Out-Null

$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$TargetScript`" -Port $Port -UserProfilePath `"$UserProfilePath`" -ConfigPath `"$ConfigPath`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 3650)
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 2

$healthOk = $false
try {
    $headers = @{ Authorization = "Bearer $ApiKey" }
    $health = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:$Port/api/v1/health" -Headers $headers -TimeoutSec 5
    $healthOk = $health.status -eq "ok"
} catch { }

$addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -ne "127.0.0.1" -and
        -not $_.IPAddress.StartsWith("169.254.") -and
        $_.AddressState -eq "Preferred"
    } |
    ForEach-Object {
        $adapter = Get-NetAdapter -InterfaceIndex $_.InterfaceIndex -ErrorAction SilentlyContinue
        [PSCustomObject]@{ IP = $_.IPAddress; Adapter = $adapter.InterfaceDescription }
    } |
    Where-Object {
        $_.Adapter -notmatch "Hyper-V|vEthernet|WSL|Docker|VPN|Tailscale|WireGuard"
    }

Write-Host ""
Write-Host "Claude Usage Helper installed."
Write-Host ""
Write-Host "Service:        $TaskName"
Write-Host "Status:         $(if ($healthOk) { 'Running' } else { 'Installed - health check pending/failed' })"
Write-Host "Port:           $Port"
Write-Host "API key:        $ApiKey"
Write-Host ""
Write-Host "LAN address candidates:"
if ($addresses) {
    $addresses | ForEach-Object { Write-Host "  $($_.IP)  [$($_.Adapter)]" }
} else {
    Write-Host "  No normal LAN IPv4 address was detected. Run: Get-NetIPAddress -AddressFamily IPv4"
}
Write-Host ""
Write-Host "Home Assistant: Settings > Devices & services > Add Integration > Claude Usage > Local Claude Code"
Write-Host ""
