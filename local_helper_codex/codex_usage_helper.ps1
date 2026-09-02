param(
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ApiVersion = 1
$UsageUrl = 'https://chatgpt.com/backend-api/wham/usage'
$TokenUrl = 'https://auth.openai.com/oauth/token'
$OAuthClientId = 'app_EMoamEEZ73f0CkXaXp7hrann'
$UserAgent = 'codex-cli'

function Write-HelperLog {
    param([string]$Message, [string]$Level = 'INFO')
    try {
        $logPath = Join-Path (Split-Path -Parent $ConfigPath) 'helper.log'
        Add-Content -LiteralPath $logPath -Value ('{0:o} [{1}] {2}' -f (Get-Date), $Level, $Message) -Encoding UTF8
    } catch { }
}

function Send-Json {
    param($Context, [int]$StatusCode, $Body)
    $json = $Body | ConvertTo-Json -Depth 20 -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($json)
    $Context.Response.StatusCode = $StatusCode
    $Context.Response.ContentType = 'application/json; charset=utf-8'
    $Context.Response.ContentLength64 = $bytes.Length
    $Context.Response.Headers['Cache-Control'] = 'no-store'
    $Context.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    $Context.Response.OutputStream.Close()
}

function Test-FixedTimeSecret {
    param([string]$A, [string]$B)
    if ($null -eq $A -or $null -eq $B) { return $false }
    $aBytes = [Text.Encoding]::UTF8.GetBytes($A)
    $bBytes = [Text.Encoding]::UTF8.GetBytes($B)
    $max = [Math]::Max($aBytes.Length, $bBytes.Length)
    $diff = $aBytes.Length -bxor $bBytes.Length
    for ($i = 0; $i -lt $max; $i++) {
        $av = if ($i -lt $aBytes.Length) { $aBytes[$i] } else { 0 }
        $bv = if ($i -lt $bBytes.Length) { $bBytes[$i] } else { 0 }
        $diff = $diff -bor ($av -bxor $bv)
    }
    return $diff -eq 0
}

function ConvertFrom-JwtPayload {
    param([string]$Token)
    if (-not $Token) { return $null }
    $parts = $Token.Split('.')
    if ($parts.Count -ne 3) { return $null }
    $payload = $parts[1].Replace('-', '+').Replace('_', '/')
    switch ($payload.Length % 4) {
        2 { $payload += '==' }
        3 { $payload += '=' }
    }
    try {
        $bytes = [Convert]::FromBase64String($payload)
        return ([Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json)
    } catch { return $null }
}

function Get-CodexAuth {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Codex auth file not found at $Path. Run 'codex login' using ChatGPT sign-in."
    }
    $root = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    $tokens = $root.tokens
    if ($null -eq $tokens -or -not $tokens.access_token -or -not $tokens.refresh_token) {
        throw 'Codex auth.json does not contain ChatGPT OAuth tokens. Run codex login and choose ChatGPT/device-code sign-in.'
    }
    $accessClaims = ConvertFrom-JwtPayload -Token ([string]$tokens.access_token)
    $idClaims = ConvertFrom-JwtPayload -Token ([string]$tokens.id_token)
    $accountId = [string]$tokens.account_id
    if (-not $accountId -and $null -ne $accessClaims -and $accessClaims.chatgpt_account_id) {
        $accountId = [string]$accessClaims.chatgpt_account_id
    }
    if (-not $accountId -and $null -ne $idClaims -and $idClaims.chatgpt_account_id) {
        $accountId = [string]$idClaims.chatgpt_account_id
    }
    if (-not $accountId -and $null -ne $idClaims) {
        $authClaim = $idClaims.'https://api.openai.com/auth'
        if ($null -ne $authClaim -and $authClaim.chatgpt_account_id) { $accountId = [string]$authClaim.chatgpt_account_id }
    }
    if (-not $accountId) { throw 'Codex OAuth tokens do not contain a ChatGPT account/workspace id.' }

    $plan = $null
    if ($null -ne $idClaims) {
        $authClaim = $idClaims.'https://api.openai.com/auth'
        if ($null -ne $authClaim -and $authClaim.chatgpt_plan_type) { $plan = [string]$authClaim.chatgpt_plan_type }
    }
    $expiresAt = $null
    if ($null -ne $accessClaims -and $accessClaims.exp) {
        try { $expiresAt = [int64]$accessClaims.exp } catch { }
    }
    return [pscustomobject]@{
        Root = $root
        Tokens = $tokens
        AccountId = $accountId
        Plan = $plan
        ExpiresAt = $expiresAt
    }
}

function Save-RefreshedCodexAuth {
    param([string]$Path, [string]$OriginalRefreshToken, $TokenData)
    $current = Get-CodexAuth -Path $Path
    if ([string]$current.Tokens.refresh_token -ne $OriginalRefreshToken) {
        Write-HelperLog 'Codex refreshed credentials concurrently; using the newer auth.json.' 'DEBUG'
        return $current
    }
    $current.Tokens.access_token = [string]$TokenData.access_token
    if ($TokenData.refresh_token) { $current.Tokens.refresh_token = [string]$TokenData.refresh_token }
    if ($TokenData.id_token) { $current.Tokens.id_token = [string]$TokenData.id_token }
    $now = [DateTimeOffset]::UtcNow.ToString('o')
    if ($current.Root.PSObject.Properties.Name -contains 'last_refresh') {
        $current.Root.last_refresh = $now
    } else {
        $current.Root | Add-Member -NotePropertyName last_refresh -NotePropertyValue $now
    }
    $json = $current.Root | ConvertTo-Json -Depth 30
    [IO.File]::WriteAllText($Path, $json, [Text.UTF8Encoding]::new($false))
    return Get-CodexAuth -Path $Path
}

function Refresh-CodexAuth {
    param([string]$AuthPath, $Auth)
    $refresh = [string]$Auth.Tokens.refresh_token
    if (-not $refresh) { throw 'Codex refresh token is unavailable. Run codex login.' }
    $body = @{
        client_id = $OAuthClientId
        grant_type = 'refresh_token'
        refresh_token = $refresh
    } | ConvertTo-Json -Compress
    try {
        $tokenData = Invoke-RestMethod -Method Post -Uri $TokenUrl -ContentType 'application/json' -Body $body -TimeoutSec 20
    } catch {
        throw "Codex OAuth refresh failed: $($_.Exception.Message)"
    }
    if (-not $tokenData.access_token) { throw 'OpenAI refresh response omitted access_token.' }
    return Save-RefreshedCodexAuth -Path $AuthPath -OriginalRefreshToken $refresh -TokenData $tokenData
}

function Ensure-FreshCodexAuth {
    param([string]$AuthPath)
    $auth = Get-CodexAuth -Path $AuthPath
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    if ($null -ne $auth.ExpiresAt -and [int64]$auth.ExpiresAt -le ($now + 300)) {
        Write-HelperLog 'Refreshing Codex OAuth access token before expiry.' 'DEBUG'
        $auth = Refresh-CodexAuth -AuthPath $AuthPath -Auth $auth
    }
    return $auth
}

function Invoke-CodexUsage {
    param([string]$AuthPath)
    $auth = Ensure-FreshCodexAuth -AuthPath $AuthPath
    $headers = @{
        Authorization = "Bearer $($auth.Tokens.access_token)"
        'ChatGPT-Account-Id' = $auth.AccountId
        'User-Agent' = $UserAgent
        'Cache-Control' = 'no-store'
    }
    try {
        $raw = Invoke-RestMethod -Method Get -Uri $UsageUrl -Headers $headers -TimeoutSec 20
        return [pscustomobject]@{ Raw = $raw; Auth = $auth }
    } catch {
        $status = $null
        try { $status = [int]$_.Exception.Response.StatusCode } catch { }
        if ($status -eq 401) {
            Write-HelperLog 'OpenAI usage returned 401; refreshing Codex token once.' 'DEBUG'
            $auth = Refresh-CodexAuth -AuthPath $AuthPath -Auth $auth
            $headers.Authorization = "Bearer $($auth.Tokens.access_token)"
            $raw = Invoke-RestMethod -Method Get -Uri $UsageUrl -Headers $headers -TimeoutSec 20
            return [pscustomobject]@{ Raw = $raw; Auth = $auth }
        }
        throw
    }
}

function Copy-Window {
    param($Window)
    if ($null -eq $Window) { return $null }
    return [ordered]@{
        used_percent = $Window.used_percent
        reset_at = $Window.reset_at
        reset_after_seconds = $Window.reset_after_seconds
        limit_window_seconds = $Window.limit_window_seconds
    }
}

function Copy-RateLimit {
    param($RateLimit)
    if ($null -eq $RateLimit) { return $null }
    return [ordered]@{
        allowed = $RateLimit.allowed
        limit_reached = $RateLimit.limit_reached
        primary_window = Copy-Window $RateLimit.primary_window
        secondary_window = Copy-Window $RateLimit.secondary_window
    }
}

function Convert-SafeUsage {
    param($Raw)
    $additional = @()
    foreach ($item in @($Raw.additional_rate_limits)) {
        if ($null -eq $item) { continue }
        $additional += [ordered]@{
            metered_feature = $item.metered_feature
            limit_name = $item.limit_name
            rate_limit = Copy-RateLimit $item.rate_limit
        }
    }
    $credits = $null
    if ($null -ne $Raw.credits) {
        $credits = [ordered]@{
            has_credits = $Raw.credits.has_credits
            unlimited = $Raw.credits.unlimited
            balance = $Raw.credits.balance
            overage_limit_reached = $Raw.credits.overage_limit_reached
        }
    }
    $resetCredits = $null
    if ($null -ne $Raw.rate_limit_reset_credits) {
        $resetCredits = [ordered]@{ available_count = $Raw.rate_limit_reset_credits.available_count }
    }
    $reachedType = $null
    if ($null -ne $Raw.rate_limit_reached_type) {
        $reachedType = [ordered]@{ type = $Raw.rate_limit_reached_type.type }
    }
    return [ordered]@{
        plan_type = $Raw.plan_type
        rate_limit = Copy-RateLimit $Raw.rate_limit
        additional_rate_limits = $additional
        credits = $credits
        rate_limit_reset_credits = $resetCredits
        rate_limit_reached_type = $reachedType
    }
}

if (-not (Test-Path -LiteralPath $ConfigPath)) { throw "Configuration file not found: $ConfigPath" }
$config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$port = [int]$config.port
$apiKey = [string]$config.api_key
$authPath = [Environment]::ExpandEnvironmentVariables([string]$config.auth_path)

$listener = [Net.HttpListener]::new()
$listener.Prefixes.Add("http://+:$port/")
$listener.Start()
Write-HelperLog "Codex Usage Helper started on port $port."

try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        try {
            if ($context.Request.HttpMethod -ne 'GET') {
                Send-Json $context 405 @{ status = 'error'; message = 'Method not allowed' }
                continue
            }
            $authHeader = [string]$context.Request.Headers['Authorization']
            $provided = if ($authHeader.StartsWith('Bearer ', [StringComparison]::OrdinalIgnoreCase)) { $authHeader.Substring(7) } else { '' }
            if (-not (Test-FixedTimeSecret $provided $apiKey)) {
                Send-Json $context 401 @{ status = 'error'; message = 'Unauthorized' }
                continue
            }
            $path = $context.Request.Url.AbsolutePath.TrimEnd('/')
            if ($path -eq '/api/v1/health') {
                $present = Test-Path -LiteralPath $authPath
                $authenticated = $false
                $plan = $null
                $expiresAt = $null
                if ($present) {
                    try {
                        $auth = Get-CodexAuth -Path $authPath
                        $authenticated = [bool]$auth.Tokens.access_token
                        $plan = $auth.Plan
                        $expiresAt = $auth.ExpiresAt
                    } catch { }
                }
                Send-Json $context 200 ([ordered]@{
                    status = 'ok'
                    api_version = $ApiVersion
                    helper_id = $config.helper_id
                    codex_detected = [bool](Get-Command codex -ErrorAction SilentlyContinue)
                    auth_file_present = $present
                    authenticated = $authenticated
                    plan = $plan
                    access_token_expires_at = $expiresAt
                })
                continue
            }
            if ($path -eq '/api/v1/usage') {
                try {
                    $result = Invoke-CodexUsage -AuthPath $authPath
                    $safeUsage = Convert-SafeUsage -Raw $result.Raw
                    Send-Json $context 200 ([ordered]@{
                        status = 'ok'
                        api_version = $ApiVersion
                        source = 'codex'
                        helper_id = $config.helper_id
                        timestamp = [DateTimeOffset]::UtcNow.ToString('o')
                        account_id = $result.Auth.AccountId
                        plan = $result.Auth.Plan
                        usage = $safeUsage
                    })
                } catch {
                    $message = $_.Exception.Message
                    Write-HelperLog "Usage fetch failed: $message" 'WARN'
                    $statusCode = if ($message -match '429|rate') { 429 } elseif ($message -match '401|403|login|token|auth') { 503 } else { 502 }
                    Send-Json $context $statusCode @{ status = 'error'; api_version = $ApiVersion; message = $message }
                }
                continue
            }
            Send-Json $context 404 @{ status = 'error'; message = 'Not found' }
        } catch {
            Write-HelperLog "Request handling error: $($_.Exception.Message)" 'ERROR'
            try { Send-Json $context 500 @{ status = 'error'; message = 'Internal helper error' } } catch { }
        }
    }
} finally {
    $listener.Stop()
    $listener.Close()
    Write-HelperLog 'Codex Usage Helper stopped.'
}
