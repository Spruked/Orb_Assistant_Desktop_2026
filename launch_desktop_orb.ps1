$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Import-OrbEnvFile {
  param([string]$Path)

  if (-not (Test-Path -LiteralPath $Path)) {
    return
  }

  Get-Content -LiteralPath $Path | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) {
      return
    }

    if ($line.StartsWith("export ")) {
      $line = $line.Substring(7).Trim()
    }

    $eq = $line.IndexOf("=")
    if ($eq -le 0) {
      return
    }

    $key = $line.Substring(0, $eq).Trim()
    $value = $line.Substring($eq + 1).Trim()
    if (
      ($value.StartsWith('"') -and $value.EndsWith('"')) -or
      ($value.StartsWith("'") -and $value.EndsWith("'"))
    ) {
      $value = $value.Substring(1, $value.Length - 2)
    }

    Set-Item -Path "Env:$key" -Value $value
  }
}

. "$root\orb-instance.windows.ps1"
$localOverride = Join-Path $root "orb-instance.local.ps1"
if (Test-Path $localOverride) {
  . $localOverride
}
$substrateRoot = Split-Path -Parent $root
$universalVoiceEnv = Join-Path $substrateRoot "substrate\orb_universal_config\orb_realtime_voice.env"
Import-OrbEnvFile -Path $universalVoiceEnv

$electronExe = Join-Path $root "electron\node_modules\electron\dist\electron.exe"
if (-not (Test-Path $electronExe)) {
  throw "Electron runtime not found at $electronExe"
}

Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue

Push-Location (Join-Path $root "electron")
try {
  & $electronExe . --disable-http-cache
} finally {
  Pop-Location
}
