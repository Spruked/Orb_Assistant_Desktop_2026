$ErrorActionPreference = "Stop"

$startupDir = [Environment]::GetFolderPath("Startup")
$launcherPath = Join-Path $startupDir "Start-OrbVoiceStack.bat"
$psScript = "R:\R_Drive_Substrate\Orb_Assistant_Desktop\scripts\Start-OrbVoiceStack.ps1"

if (-not (Test-Path $psScript)) {
  throw "Missing script: $psScript"
}

$content = @"
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$psScript" -Warmup -StartTunnel
"@

Set-Content -Path $launcherPath -Value $content -Encoding ASCII
Write-Host "Startup launcher created: $launcherPath"
