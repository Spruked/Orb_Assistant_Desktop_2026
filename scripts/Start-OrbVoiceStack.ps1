param(
  [switch]$Warmup = $true,
  [switch]$StartTunnel = $true
)

$ErrorActionPreference = "Stop"

function Wait-ForPath {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [int]$TimeoutSec = 120
  )
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $Path) {
      return $true
    }
    Start-Sleep -Milliseconds 900
  }
  return $false
}

function Ensure-WSLReady {
  try {
    wsl.exe -e sh -lc "echo wsl_ready" | Out-Null
    return $true
  } catch {
    return $false
  }
}

function Start-OllamaIfNeeded {
  $listening = netstat -ano -p tcp | Select-String ":11434\s+.*LISTENING"
  if ($listening) {
    Write-Host "Ollama already listening on 11434."
    return
  }
  Write-Host "Starting Ollama..."
  Start-Process -FilePath "ollama.exe" -ArgumentList "serve" -WindowStyle Hidden
}

function Start-WSLOllamaIfNeeded {
  $listening = netstat -ano -p tcp | Select-String ":11434\s+.*LISTENING"
  if ($listening) {
    return
  }
  try {
    wsl.exe -e sh -lc "pgrep -f 'ollama serve' >/dev/null || (nohup ollama serve >/tmp/orb_ollama.log 2>&1 &)"
  } catch {}
}

function Start-QwenBridgeIfNeeded {
  $listening = netstat -ano -p tcp | Select-String ":8020\s+.*LISTENING"
  if ($listening) {
    Write-Host "Qwen bridge already listening on 8020."
    return
  }
  $bridgeScript = "C:\dev\Desktop\PLATFORM\dandy_qwen_tts_ui\scripts\Start-QwenTTSBridge.ps1"
  if (-not (Test-Path $bridgeScript)) {
    throw "Missing bridge launcher: $bridgeScript"
  }
  Write-Host "Starting Qwen bridge..."
  Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile","-ExecutionPolicy","Bypass","-File",$bridgeScript) -WindowStyle Hidden
}

function Start-QwenWslProxyIfNeeded {
  $listening = netstat -ano -p tcp | Select-String ":8021\s+.*LISTENING"
  if ($listening) {
    Write-Host "Qwen WSL proxy already listening on 8021."
    return
  }
  try {
    wsl.exe -e sh -lc "nohup python3 /mnt/r/R_Drive_Substrate/Orb_Assistant_Desktop/scripts/qwen_tts_wsl_proxy.py >/tmp/orb_qwen_tts_wsl_proxy.log 2>&1 &"
    Write-Host "Started Qwen WSL proxy on 8021."
  } catch {
    Write-Host "Qwen WSL proxy start skipped."
  }
}

function Resolve-CloudflaredPath {
  $candidates = @(
    "$env:ProgramFiles\cloudflared\cloudflared.exe",
    "$env:ProgramFiles(x86)\cloudflared\cloudflared.exe",
    "$env:USERPROFILE\scoop\apps\cloudflared\current\cloudflared.exe",
    "$env:USERPROFILE\.local\bin\cloudflared.exe"
  )
  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) {
      return $candidate
    }
  }
  return $null
}

function Start-TunnelIfNeeded {
  $running = Get-Process -Name cloudflared -ErrorAction SilentlyContinue
  if ($running) {
    Write-Host "Cloudflared already running."
    return
  }

  $cloudflared = Resolve-CloudflaredPath
  $customCommand = $env:ORB_TUNNEL_COMMAND
  if ($customCommand) {
    Write-Host "Starting cloudflared using ORB_TUNNEL_COMMAND."
    Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile","-ExecutionPolicy","Bypass","-Command",$customCommand) -WindowStyle Hidden
    return
  }

  if ($cloudflared) {
    $configPath = Join-Path $env:USERPROFILE ".cloudflared\config.yml"
    if (Test-Path -LiteralPath $configPath) {
      Write-Host "Starting cloudflared tunnel from Windows config."
      Start-Process -FilePath $cloudflared -ArgumentList @("tunnel","--config",$configPath,"run") -WindowStyle Hidden
      return
    }
  }

  try {
    $wslConfigCheck = wsl.exe -e sh -lc "test -f ~/.cloudflared/config.yml && echo yes || echo no"
    if (($wslConfigCheck | Out-String).Trim() -eq "yes") {
      Write-Host "Starting cloudflared tunnel from WSL config."
      wsl.exe -e sh -lc "nohup cloudflared tunnel --config ~/.cloudflared/config.yml run >/tmp/orb_cloudflared.log 2>&1 &" | Out-Null
      return
    }
  } catch {}

  if (-not $cloudflared) {
    Write-Host "Cloudflared binary not found on Windows; tunnel autostart skipped."
    return
  }

  Write-Host "Cloudflared config not found; tunnel autostart skipped."
}

function Wait-ForEndpoint {
  param(
    [Parameter(Mandatory = $true)][string]$Url,
    [int]$TimeoutSec = 45
  )
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $resp = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 4
      if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {
        return $true
      }
    } catch {}
    Start-Sleep -Milliseconds 900
  }
  return $false
}

function Warmup-Voice {
  Write-Host "Warming up TTS..."
  $body = @{
    text = "voice warmup"
    instruct = "A calm, middle-aged male voice with a deep, clear, professional tone."
  } | ConvertTo-Json
  try {
    $result = Invoke-RestMethod -Uri "http://127.0.0.1:8020/generate" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 90
    if ($result -and $result.audio_path) {
      Write-Host "Warmup audio generated."
      return
    }
  } catch {}

  try {
    $fallback = @{
      text = "voice warmup"
      speaker = "host"
      format = "wav"
    } | ConvertTo-Json
    Invoke-RestMethod -Uri "http://127.0.0.1:8020/synthesize" -Method Post -ContentType "application/json" -Body $fallback -TimeoutSec 90 | Out-Null
    Write-Host "Warmup synth route used."
  } catch {
    Write-Host "Warmup skipped: bridge route unavailable."
  }
}

if (-not (Wait-ForPath -Path "R:\R_Drive_Substrate" -TimeoutSec 180)) {
  throw "R drive substrate path not available after timeout."
}

if (-not (Ensure-WSLReady)) {
  Write-Host "WSL not immediately ready; retrying..."
  Start-Sleep -Seconds 3
  if (-not (Ensure-WSLReady)) {
    throw "WSL did not become ready."
  }
}

Start-OllamaIfNeeded
Start-WSLOllamaIfNeeded
Start-QwenBridgeIfNeeded
Start-QwenWslProxyIfNeeded

[void](Wait-ForEndpoint -Url "http://127.0.0.1:11434/api/tags" -TimeoutSec 45)
[void](Wait-ForEndpoint -Url "http://127.0.0.1:8020/health" -TimeoutSec 60)
[void](Wait-ForEndpoint -Url "http://127.0.0.1:8021/health" -TimeoutSec 20)

if ($Warmup) {
  Warmup-Voice
}

if ($StartTunnel) {
  Start-TunnelIfNeeded
}

Write-Host "Orb voice stack startup complete."
