param(
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ApiVersion = 1

function Write-HelperLog {
    param([string]$Message, [string]$Level = 'INFO')
    try {
        $logPath = Join-Path (Split-Path -Parent $ConfigPath) 'helper.log'
        Add-Content -LiteralPath $logPath -Value ('{0:o} [{1}] {2}' -f (Get-Date), $Level, $Message) -Encoding UTF8
    } catch { }
}

function Send-Json {
    param($Context, [int]$StatusCode, $Body)
    $json = $Body | ConvertTo-Json -Depth 30 -Compress
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

function Read-CodexRpcLine {
    param($Process, [DateTime]$Deadline)
    $remaining = [int][Math]::Max(1, ($Deadline - [DateTime]::UtcNow).TotalMilliseconds)
    $task = $Process.StandardOutput.ReadLineAsync()
    if (-not $task.Wait($remaining)) { throw 'Timed out waiting for Codex app-server response.' }
    return $task.Result
}

function Invoke-CodexRateLimits {
    $codex = Get-Command codex -ErrorAction SilentlyContinue
    if (-not $codex) { throw 'Codex CLI was not found in PATH.' }

    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = $codex.Source
    $psi.Arguments = 'app-server --stdio'
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true

    $proc = New-Object Diagnostics.Process
    $proc.StartInfo = $psi
    if (-not $proc.Start()) { throw 'Unable to start Codex app-server.' }

    try {
        $proc.StandardInput.WriteLine('{"id":1,"method":"initialize","params":{"clientInfo":{"name":"ha_ai_usage","title":"Home Assistant AI Usage","version":"0.1.0"}}}')
        $proc.StandardInput.Flush()
        $deadline = [DateTime]::UtcNow.AddSeconds(15)
        $initialized = $false
        while ([DateTime]::UtcNow -lt $deadline) {
            $line = Read-CodexRpcLine -Process $proc -Deadline $deadline
            if ($null -eq $line) { break }
            try { $obj = $line | ConvertFrom-Json } catch { continue }
            if ($obj.id -eq 1) {
                if ($null -ne $obj.error) { throw "Codex app-server initialization failed: $($obj.error.message)" }
                $initialized = $true
                break
            }
        }
        if (-not $initialized) { throw 'Codex app-server initialization timed out.' }

        $proc.StandardInput.WriteLine('{"method":"initialized","params":{}}')
        $proc.StandardInput.WriteLine('{"id":2,"method":"account/rateLimits/read","params":{}}')
        $proc.StandardInput.Flush()

        $rateLimits = $null
        $deadline = [DateTime]::UtcNow.AddSeconds(20)
        while ([DateTime]::UtcNow -lt $deadline -and $null -eq $rateLimits) {
            $line = Read-CodexRpcLine -Process $proc -Deadline $deadline
            if ($null -eq $line) { break }
            try { $obj = $line | ConvertFrom-Json } catch { continue }
            if ($obj.id -eq 2) {
                if ($null -ne $obj.error) { throw "Codex rate-limit RPC failed: $($obj.error.message)" }
                $rateLimits = $obj.result
            }
        }
        if ($null -eq $rateLimits) { throw 'Codex app-server returned no rate-limit result.' }

        $plan = $null
        if ($null -ne $rateLimits.rateLimits -and $rateLimits.rateLimits.planType) {
            $plan = [string]$rateLimits.rateLimits.planType
        }

        return [pscustomobject]@{
            RateLimits = $rateLimits
            Plan = $plan
        }
    }
    finally {
        try { $proc.StandardInput.Close() } catch { }
        if (-not $proc.HasExited) { try { $proc.Kill() } catch { } }
        try { $proc.Dispose() } catch { }
    }
}

if (-not (Test-Path -LiteralPath $ConfigPath)) { throw "Configuration file not found: $ConfigPath" }
$config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$port = [int]$config.port
$apiKey = [string]$config.api_key

$listener = New-Object Net.HttpListener
$listener.Prefixes.Add("http://+:$port/")
$listener.Start()
Write-HelperLog "Codex Usage Helper started on port $port using codex app-server."

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
                $codex = Get-Command codex -ErrorAction SilentlyContinue
                Send-Json $context 200 ([ordered]@{
                    status = 'ok'
                    api_version = $ApiVersion
                    helper_id = $config.helper_id
                    codex_detected = ($null -ne $codex)
                    source = 'codex_app_server'
                })
                continue
            }

            if ($path -eq '/api/v1/usage') {
                try {
                    $result = Invoke-CodexRateLimits
                    Send-Json $context 200 ([ordered]@{
                        status = 'ok'
                        api_version = $ApiVersion
                        source = 'codex_app_server'
                        helper_id = $config.helper_id
                        timestamp = [DateTimeOffset]::UtcNow.ToString('o')
                        plan = $result.Plan
                        app_server_result = $result.RateLimits
                    })
                } catch {
                    $message = $_.Exception.Message
                    Write-HelperLog "Usage fetch failed: $message" 'WARN'
                    Send-Json $context 503 @{ status = 'error'; api_version = $ApiVersion; message = $message }
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
