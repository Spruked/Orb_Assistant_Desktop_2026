[CmdletBinding()]
param(
  [string]$SourceRoot = (Split-Path -Parent $PSScriptRoot),
  [string]$OutputRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) "dist\windows-portable")
)

$ErrorActionPreference = "Stop"

function Invoke-Robocopy {
  param(
    [string]$From,
    [string]$To,
    [string[]]$ExcludeDirs,
    [string[]]$ExcludeFiles
  )

  $robocopyArgs = @(
    $From,
    $To,
    "/E",
    "/R:1",
    "/W:1",
    "/NFL",
    "/NDL",
    "/NJH",
    "/NJS",
    "/NP"
  )

  if ($ExcludeDirs.Count -gt 0) {
    $robocopyArgs += "/XD"
    $robocopyArgs += $ExcludeDirs
  }

  if ($ExcludeFiles.Count -gt 0) {
    $robocopyArgs += "/XF"
    $robocopyArgs += $ExcludeFiles
  }

  & robocopy @robocopyArgs | Out-Null
  if ($LASTEXITCODE -gt 7) {
    throw "Robocopy failed with exit code $LASTEXITCODE"
  }
}

$sourceRoot = (Resolve-Path $SourceRoot).Path
$outputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
$stageRoot = Join-Path $outputRoot "Orb_Assistant_Desktop"
$zipPath = Join-Path $outputRoot "Orb_Assistant_Desktop_Windows_Portable.zip"

if (Test-Path $stageRoot) {
  Remove-Item $stageRoot -Force -Recurse
}
if (Test-Path $zipPath) {
  Remove-Item $zipPath -Force
}
New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null

$excludeDirs = @(
  ".git",
  ".pytest_cache",
  "__pycache__",
  ".orb-assistant-desktop",
  ".orb-assistant-wsl",
  "dist",
  "system",
  "CALI_System\cache",
  "CALI_System\logs",
  "CALI_System\memory",
  "CALI_System\swarm_results",
  "CALI_System\voice_cache",
  "electron\audio_cache",
  "electron\src\audio_cache"
)

$excludeFiles = @(
  ".orb-launch.log",
  ".orb-start.stdout.log",
  ".orb-start.stderr.log"
)

Invoke-Robocopy -From $sourceRoot -To $stageRoot -ExcludeDirs $excludeDirs -ExcludeFiles $excludeFiles
Compress-Archive -Path (Join-Path $stageRoot "*") -DestinationPath $zipPath

Write-Output ("Portable package staged at {0}" -f $stageRoot)
Write-Output ("Portable zip created at {0}" -f $zipPath)
