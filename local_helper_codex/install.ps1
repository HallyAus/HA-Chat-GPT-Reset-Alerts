param(
    [ValidateRange(1,65535)]
    [int]$Port = 8765,
    [string]$AuthPath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $args = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"{0}"' -f $PSCommandPath),'-Port',$Port)
    if ($AuthPath) { $args += @('-AuthPath',('"{0}"' -f $AuthPath)) }
    Start-Process powershell.exe -Verb RunAs -ArgumentList ($args -join ' ')
    exit
}

$TaskName = 'Codex Usage Helper'
$FirewallName = 'Codex Usage Helper'
$InstallDir = Join-Path $env:ProgramData 'CodexUsageHelper'
$HelperSource = Join-Path $PSScriptRoot 'codex_usage_helper.ps1'
$HelperPath = Join-Path $InstallDir 'codex_usage_helper.ps1'
$ConfigPath = Join-Path $InstallDir 'config.json'

if (-not $AuthPath) {
    if ($env:CODEX_HOME) {
        $AuthPath = Join-Path $env:CODEX_HOME 'auth.json'
    } else {
        $AuthPath = Join-Path $env:USERPROFILE '.codex\auth.json'
    }
}
$AuthPath = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($AuthPath))

if (-not (Test-Path -LiteralPath $HelperSource)) { throw "Helper script not found: $HelperSource" }
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -LiteralPath $HelperSource -Destination $HelperPath -Force

$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$apiKey = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
$helperId = [Guid]::NewGuid().ToString('D')
$config = [ordered]@{
    api_version = 1
    helper_id = $helperId
    port = $Port
    api_key = $apiKey
    auth_path = $AuthPath
}
$config | ConvertTo-Json | Set-Content -LiteralPath $ConfigPath -Encoding UTF8

$currentUser = "$env:USERDOMAIN\$env:USERNAME"
& icacls.exe $ConfigPath /inheritance:r /grant:r 'SYSTEM:F' 'Administrators:F' "${currentUser}:R" | Out-Null

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$HelperPath`" -ConfigPath `"$ConfigPath`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 20 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
$taskPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $taskPrincipal -Description 'Provides read-only ChatGPT/Codex usage metadata to Home Assistant over an authenticated LAN API.' | Out-Null

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
Write-Host ''
Write-Host "Service:      $(if ($healthOk) { 'Running' } else { 'Installed - health check did not respond yet' })"
Write-Host "Port:         $Port"
Write-Host "Codex auth:   $AuthPath"
Write-Host "API key:      $apiKey"
Write-Host ''
if ($addresses.Count -gt 0) {
    Write-Host 'LAN address candidates:'
    foreach ($address in $addresses) { Write-Host "  $address" }
} else {
    Write-Host 'No normal LAN IPv4 address was automatically detected.'
}
Write-Host ''
if (-not (Test-Path -LiteralPath $AuthPath)) {
    Write-Warning "Codex auth.json is not present at $AuthPath. Run 'codex login' as your normal user and choose ChatGPT/device-code sign-in."
}
Write-Host 'Home Assistant:'
Write-Host '  Settings -> Devices & services -> Add integration -> ChatGPT Usage -> Local Codex'
Write-Host ''
Write-Host 'The local API key can be recovered later from:'
Write-Host "  $ConfigPath"
