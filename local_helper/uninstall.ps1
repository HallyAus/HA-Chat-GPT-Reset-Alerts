[CmdletBinding()]
param([int]$Port = 8766)

$ErrorActionPreference = "SilentlyContinue"
$TaskName = "Claude Usage Helper"
$InstallDir = "$env:ProgramData\ClaudeUsageHelper"
$FirewallName = "Claude Usage Helper TCP $Port"
$UrlPrefix = "http://+:$Port/"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "-Port", $Port)
    Start-Process powershell.exe -Verb RunAs -ArgumentList $args
    exit
}

Stop-ScheduledTask -TaskName $TaskName
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Get-NetFirewallRule -DisplayName $FirewallName | Remove-NetFirewallRule
& netsh http delete urlacl url=$UrlPrefix | Out-Null
Remove-Item -Path $InstallDir -Recurse -Force

Write-Host "Claude Usage Helper removed. Claude Code was not modified."
