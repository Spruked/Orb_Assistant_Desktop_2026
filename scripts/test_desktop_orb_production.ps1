param(
    [int]$TtsRuns = 3,
    [int]$TtsTimeoutSec = 120,
    [int]$LlmTimeoutSec = 30
)

$ErrorActionPreference = "Stop"

function New-Result {
    param(
        [string]$Name,
        [bool]$Ok,
        [long]$Ms = 0,
        [string]$Detail = "",
        [string]$Severity = "INFO"
    )
    [pscustomobject]@{
        name = $Name
        ok = $Ok
        ms = $Ms
        severity = $Severity
        detail = $Detail
    }
}

function Measure-Step {
    param(
        [string]$Name,
        [scriptblock]$Block,
        [string]$Severity = "ERROR"
    )
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        $detail = & $Block
        $sw.Stop()
        New-Result -Name $Name -Ok $true -Ms $sw.ElapsedMilliseconds -Detail ([string]$detail)
    } catch {
        $sw.Stop()
        New-Result -Name $Name -Ok $false -Ms $sw.ElapsedMilliseconds -Detail $_.Exception.Message -Severity $Severity
    }
}

function Test-RiffFile {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        return "missing"
    }
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 44) {
        return "too_short:$($bytes.Length)"
    }
    $riff = [Text.Encoding]::ASCII.GetString($bytes, 0, 4)
    $wave = [Text.Encoding]::ASCII.GetString($bytes, 8, 4)
    if ($riff -ne "RIFF" -or $wave -ne "WAVE") {
        return "invalid_header:$riff/$wave length=$($bytes.Length)"
    }
    return "riff_ok bytes=$($bytes.Length)"
}

function Invoke-QwenTtsSpeak {
    param(
        [string]$Body,
        [string]$OutFile,
        [int]$TimeoutSec,
        [int]$Retries = 4
    )
    $lastError = ""
    for ($attempt = 1; $attempt -le $Retries; $attempt++) {
        try {
            Invoke-WebRequest -Uri "http://127.0.0.1:9880/speak" -Method Post -ContentType "application/json" -Body $Body -TimeoutSec $TimeoutSec -OutFile $OutFile | Out-Null
            return "attempt=$attempt"
        } catch {
            $lastError = $_.Exception.Message
            if ($lastError -match "\(503\)|\(429\)" -and $attempt -lt $Retries) {
                Start-Sleep -Seconds ([Math]::Min(12, 2 * $attempt))
                continue
            }
            throw
        }
    }
    throw $lastError
}

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$results = New-Object System.Collections.Generic.List[object]
$tmpRoot = Join-Path $root ".orb-runtime\production-smoke"
New-Item -ItemType Directory -Force -Path $tmpRoot | Out-Null

$results.Add((Measure-Step "electron_process" {
    $procs = Get-CimInstance Win32_Process | Where-Object {
        $_.ExecutablePath -eq "R:\Orb_Assistant_Desktop\electron\node_modules\electron\dist\electron.exe"
    }
    if (-not $procs) { throw "Desktop ORB Electron process not running" }
    "processes=$($procs.Count)"
}))

$results.Add((Measure-Step "llamacpp_models" {
    $models = Invoke-RestMethod -Uri "http://127.0.0.1:40343/v1/models" -TimeoutSec 8
    $model = $models.data[0]
    if (-not $model -or $model.owned_by -ne "llamacpp") { throw "unexpected model payload" }
    "owned_by=$($model.owned_by) ftype=$($model.meta.ftype) params=$($model.meta.n_params)"
}))

$results.Add((Measure-Step "llamacpp_chat_latency" {
    $body = @{
        model = "Qwen/Qwen2.5-1.5B-Instruct-GGUF:Q4_K_M"
        messages = @(@{ role = "user"; content = "Reply with only this token and no other words: orb-production-ready" })
        max_tokens = 8
        temperature = 0
    } | ConvertTo-Json -Depth 6
    $reply = Invoke-RestMethod -Uri "http://127.0.0.1:40343/v1/chat/completions" -Method Post -ContentType "application/json" -Body $body -TimeoutSec $LlmTimeoutSec
    $text = [string]$reply.choices[0].message.content
    if ($text.Trim() -ne "orb-production-ready") { throw "unexpected reply: $text" }
    $text
}))

$results.Add((Measure-Step "qwen_tts_health" {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:9880/health" -TimeoutSec 10
    if ($health.status -ne "ok") { throw "health status=$($health.status)" }
    "model=$($health.model) cuda=$($health.cuda) gpu=$($health.gpu) load_seconds=$($health.load_seconds)"
}))

for ($i = 1; $i -le $TtsRuns; $i++) {
    $results.Add((Measure-Step "qwen_tts_speak_$i" {
        $body = @{
            text = "Production voice latency pass $i."
            speaker = "cali"
            instruct = "A clear younger adult female voice with a warm, bright, natural tone."
            voice_profile = "R:\substrate\orb_voice\voice_profiles\cali\cali_voice.pt"
            voice_profile_metadata = "R:\substrate\orb_voice\voice_profiles\cali\cali_voice.json"
        } | ConvertTo-Json -Depth 5
        $outFile = Join-Path $tmpRoot "qwen_tts_$i.wav"
        $attemptInfo = Invoke-QwenTtsSpeak -Body $body -OutFile $outFile -TimeoutSec $TtsTimeoutSec
        $riff = Test-RiffFile -Path $outFile
        if ($riff -notlike "riff_ok*") { throw $riff }
        "$riff $attemptInfo"
    }))
}

$results.Add((Measure-Step "display_overlay" {
    $log = Join-Path $root "orb-render-diagnostics.log"
    $line = Select-String -Path $log -Pattern "\[display-sync\]" | Select-Object -Last 1
    if (-not $line -or $line.Line -notmatch "actualDisplays=3" -or $line.Line -notmatch "singleVirtual=true") {
        throw "missing three-display virtual overlay proof"
    }
    ($line.Line -replace "\s+", " ")
}))

$results.Add((Measure-Step "voice_config_invariants" {
    $config = Get-Content (Join-Path $root "orb-instance.local.ps1") -Raw
    $required = @(
        'ORB_TTS_PROVIDER = "qwen"',
        'ORB_PRIMARY_TTS_PROVIDER = "qwen"',
        'ORB_BACKUP_TTS_PROVIDER = "kokoro"',
        'ORB_ENABLE_KOKORO_FALLBACK = "1"',
        'ORB_STARTUP_VOICE_GREETING = "1"',
        'ORB_LAUNCH_GREETING_ENABLED = "1"',
        'ORB_BROWSER_ORB_VOICE_ENABLED = "0"',
        'ORB_BROWSER_TTS_ENABLED = "0"'
    )
    $missing = $required | Where-Object { $config -notmatch [regex]::Escape($_) }
    if ($missing) { throw "missing: $($missing -join ', ')" }
    "qwen_primary_kokoro_backup_browser_voice_off"
}))

$results.Add((Measure-Step "syntax_js" {
    Push-Location (Join-Path $root "electron")
    try {
        node --check "main/main.js" | Out-Null
        node --check "src/orb-renderer.js" | Out-Null
        node --check "src/ui/orb-dock-station.bundle.js" | Out-Null
    } finally {
        Pop-Location
    }
    "ok"
}))

$results.Add((Measure-Step "syntax_python" {
    Push-Location $root
    try {
        python -m py_compile "electron/src/cali_skg.py" "electron/src/core-bridges/cali.py" "mcp/orb_desktop_mcp/orb_pointer/pointer_plot_schema.py" | Out-Null
    } finally {
        Pop-Location
    }
    "ok"
}))

$tts = $results | Where-Object { $_.name -like "qwen_tts_speak_*" -and $_.ok }
$ttsMs = @($tts | ForEach-Object { [double]$_.ms })
$ttsAvg = if ($ttsMs.Count) { [math]::Round(($ttsMs | Measure-Object -Average).Average, 2) } else { 0 }
$ttsMax = if ($ttsMs.Count) { [math]::Round(($ttsMs | Measure-Object -Maximum).Maximum, 2) } else { 0 }

$failed = @($results | Where-Object { -not $_.ok })
$summary = [pscustomobject]@{
    ok = ($failed.Count -eq 0)
    failed_count = $failed.Count
    tts_runs = $ttsMs.Count
    tts_avg_ms = $ttsAvg
    tts_max_ms = $ttsMax
    generated_at = (Get-Date).ToString("o")
    results = $results
}

$outJson = Join-Path $tmpRoot "production_smoke_latest.json"
$summary | ConvertTo-Json -Depth 8 | Set-Content -Path $outJson -Encoding UTF8
$summary | ConvertTo-Json -Depth 8

if ($failed.Count -gt 0) {
    exit 1
}
