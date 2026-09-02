[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [int]$Port = 8766,

    [Parameter(Mandatory = $true)]
    [string]$UserProfilePath,

    [Parameter(Mandatory = $false)]
    [string]$ConfigPath = "$env:ProgramData\ClaudeUsageHelper\config.json"
)

$ErrorActionPreference = "Stop"
$UsageUrl = "https://api.anthropic.com/api/oauth/usage"
$BetaHeader = "oauth-2025-04-20"
$ApiVersion = 1

function Write-Log {
    param([string]$Message)
    $logDir = Split-Path -Parent $ConfigPath
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    $line = "$(Get-Date -Format o) $Message"
    Add-Content -Path (Join-Path $logDir "helper.log") -Value $line
}

function Test-ConstantTimeEqual {
    param([string]$Expected, [string]$Actual)
    if ($null -eq $Expected) { $Expected = "" }
    if ($null -eq $Actual) { $Actual = "" }
    $a = [Text.Encoding]::UTF8.GetBytes($Expected)
    $b = [Text.Encoding]::UTF8.GetBytes($Actual)
    $max = [Math]::Max($a.Length, $b.Length)
    $diff = $a.Length -bxor $b.Length
    for ($i = 0; $i -lt $max; $i++) {
        $av = if ($i -lt $a.Length) { $a[$i] } else { 0 }
        $bv = if ($i -lt $b.Length) { $b[$i] } else { 0 }
        $diff = $diff -bor ($av -bxor $bv)
    }
    return $diff -eq 0
}

function Write-JsonResponse {
    param(
        [System.Net.HttpListenerContext]$Context,
        [int]$StatusCode,
        [hashtable]$Body
    )
    $json = $Body | ConvertTo-Json -Depth 20 -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($json)
    $Context.Response.StatusCode = $StatusCode
    $Context.Response.ContentType = "application/json; charset=utf-8"
    $Context.Response.ContentLength64 = $bytes.Length
    $Context.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    $Context.Response.OutputStream.Close()
}

function Get-ClaudeCredentialInfo {
    $credentialPath = Join-Path $UserProfilePath ".claude\.credentials.json"
    if (-not (Test-Path $credentialPath)) {
        return @{ Found = $false; Authenticated = $false; AccessToken = $null; SubscriptionType = $null }
    }
    try {
        $root = Get-Content -Raw -Path $credentialPath | ConvertFrom-Json
        $oauth = $root.claudeAiOauth
        if ($null -eq $oauth) { $oauth = $root }
        $accessToken = [string]$oauth.accessToken
        $subscriptionType = [string]$oauth.subscriptionType
        return @{
            Found = $true
            Authenticated = -not [string]::IsNullOrWhiteSpace($accessToken)
            AccessToken = $accessToken
            SubscriptionType = $subscriptionType
        }
    }
    catch {
        Write-Log "Credential file could not be parsed: $($_.Exception.GetType().Name)"
        return @{ Found = $true; Authenticated = $false; AccessToken = $null; SubscriptionType = $null }
    }
}

function Get-ClaudeUsage {
    $credential = Get-ClaudeCredentialInfo
    if (-not $credential.Found) {
        throw [System.InvalidOperationException]::new("claude_credentials_missing")
    }
    if (-not $credential.Authenticated) {
        throw [System.UnauthorizedAccessException]::new("claude_authentication_required")
    }

    $headers = @{
        Authorization = "Bearer $($credential.AccessToken)"
        "anthropic-beta" = $BetaHeader
    }
    try {
        $usage = Invoke-RestMethod -Method Get -Uri $UsageUrl -Headers $headers -TimeoutSec 20
        return @{
            Usage = $usage
            SubscriptionType = $credential.SubscriptionType
        }
    }
    catch {
        $status = $null
        try { $status = [int]$_.Exception.Response.StatusCode } catch { }
        if ($status -eq 401 -or $status -eq 403) {
            throw [System.UnauthorizedAccessException]::new("claude_access_token_expired")
        }
        throw [System.Net.WebException]::new("anthropic_usage_unavailable")
    }
}

if (-not (Test-Path $ConfigPath)) {
    throw "Helper config not found at $ConfigPath"
}
$config = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
$ApiKey = [string]$config.api_key
if ([string]::IsNullOrWhiteSpace($ApiKey)) {
    throw "Helper API key is missing"
}

$listener = [System.Net.HttpListener]::new()
$listener.Prefixes.Add("http://+:$Port/")
$listener.Start()
Write-Log "Claude Usage Helper started on port $Port"

try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        try {
            if ($context.Request.HttpMethod -ne "GET") {
                Write-JsonResponse $context 405 @{ status = "error"; error = "method_not_allowed"; api_version = $ApiVersion }
                continue
            }

            $auth = [string]$context.Request.Headers["Authorization"]
            $presented = if ($auth.StartsWith("Bearer ", [StringComparison]::OrdinalIgnoreCase)) { $auth.Substring(7) } else { "" }
            if (-not (Test-ConstantTimeEqual $ApiKey $presented)) {
                Write-JsonResponse $context 401 @{ status = "error"; error = "invalid_api_key"; api_version = $ApiVersion }
                continue
            }

            $path = $context.Request.Url.AbsolutePath.TrimEnd("/")
            if ($path -eq "/api/v1/health") {
                $credential = Get-ClaudeCredentialInfo
                Write-JsonResponse $context 200 @{
                    status = "ok"
                    api_version = $ApiVersion
                    claude_detected = $credential.Found
                    authenticated = $credential.Authenticated
                }
                continue
            }

            if ($path -eq "/api/v1/usage") {
                try {
                    $result = Get-ClaudeUsage
                    Write-JsonResponse $context 200 @{
                        status = "ok"
                        api_version = $ApiVersion
                        source = "claude_code"
                        timestamp = (Get-Date).ToUniversalTime().ToString("o")
                        subscription_level = $result.SubscriptionType
                        usage = $result.Usage
                    }
                }
                catch [System.UnauthorizedAccessException] {
                    Write-JsonResponse $context 503 @{
                        status = "error"
                        api_version = $ApiVersion
                        error = $_.Exception.Message
                    }
                }
                catch {
                    Write-Log "Usage request failed: $($_.Exception.Message)"
                    Write-JsonResponse $context 503 @{
                        status = "error"
                        api_version = $ApiVersion
                        error = "usage_unavailable"
                    }
                }
                continue
            }

            Write-JsonResponse $context 404 @{ status = "error"; error = "not_found"; api_version = $ApiVersion }
        }
        catch {
            Write-Log "Request handler error: $($_.Exception.GetType().Name)"
            try { Write-JsonResponse $context 500 @{ status = "error"; error = "internal_error"; api_version = $ApiVersion } } catch { }
        }
    }
}
finally {
    $listener.Stop()
    $listener.Close()
    Write-Log "Claude Usage Helper stopped"
}
