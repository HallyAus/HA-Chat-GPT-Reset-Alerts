param(
    [ValidateRange(1,65535)]
    [int]$Port = 8765
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $args = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"{0}"' -f $PSCommandPath),'-Port',$Port)
    Start-Process powershell.exe -Verb RunAs -ArgumentList ($args -join ' ')
    exit
}

$codex = Get-Command codex -ErrorAction SilentlyContinue
if (-not $codex) { throw "Codex CLI was not found in PATH. Install Codex and run 'codex login' first." }

$TaskName = 'Codex Usage Helper'
$FirewallName = 'Codex Usage Helper'
$InstallDir = Join-Path $env:ProgramData 'CodexUsageHelper'
$HelperSource = Join-Path $PSScriptRoot 'codex_usage_helper.ps1'
$HelperPath = Join-Path $InstallDir 'codex_usage_helper.ps1'
$ConfigPath = Join-Path $InstallDir 'config.json'

if (-not (Test-Path -LiteralPath $HelperSource)) { throw "Helper script not found: $HelperSource" }
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -LiteralPath $HelperSource -Destination $HelperPath -Force

$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$apiKey = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
$helperId = [Guid]::NewGuid().ToString('D')
@{
    api_version = 1
    helper_id = $helperId
    port = $Port
    api_key = $apiKey
} | ConvertTo-Json | Set-Content -LiteralPath $ConfigPath -Encoding UTF8

$currentUser = "$env:USERDOMAIN\$env:USERNAME"
& icacls.exe $ConfigPath /inheritance:r /grant:r 'SYSTEM:F' 'Administrators:F' "${currentUser}:R" | Out-Null

$url = "http://+:$Port/"
& netsh.exe http delete urlacl url=$url 2>$null | Out-Null
& netsh.exe http add urlacl url=$url user="$currentUser" | Out-Null

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$HelperPath`" -ConfigPath `"$ConfigPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$settings = New-ScheduledTaskSettingsSet -RestartCount 20 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $taskPrincipal -Description 'Provides read-only Codex app-server rate-limit metadata to Home Assistant.' | Out-Null

Get-NetFirewallRule -DisplayName $FirewallName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $FirewallName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Private -RemoteAddress LocalSubnet | Out-Null

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 2
$healthOk = $false
try {
    $headers = @{ Authorization = "Bearer $apiKey" }
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/health" -Headers $headers -TimeoutSec 5
    $healthOk = $health.status -eq 'ok'
} catch { }

$addresses = @(Get-NetIPAddress -AddressFamily IPv4 -AddressState Preferred -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -ne '127.0.0.1' -and
        $_.IPAddress -notlike '169.254.*' -and
        $_.InterfaceAlias -notmatch 'Hyper-V|vEthernet|WSL|Docker|VPN|Loopback|Tailscale'
    } |
    Sort-Object InterfaceMetric |
    Select-Object -ExpandProperty IPAddress -Unique)

Write-Host ''
Write-Host 'Codex Usage Helper installed.' -ForegroundColor Green
Write-Host "Service:      $(if ($healthOk) { 'Running' } else { 'Installed - health check did not respond yet' })"
Write-Host "Port:         $Port"
Write-Host "API key:      $apiKey"
Write-Host 'Source:       codex app-server account/rateLimits/read'
Write-Host ''
if ($addresses.Count -gt 0) {
    Write-Host 'LAN address candidates:'
    foreach ($address in $addresses) { Write-Host "  $address" }
}
Write-Host ''
Write-Host 'Home Assistant:'
Write-Host '  Settings -> Devices & services -> Add Integration -> ChatGPT Usage -> Local Codex'
Write-Host ''
Write-Host 'The local API key can be recovered later from:'
Write-Host "  $ConfigPath"
