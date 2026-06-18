$ErrorActionPreference = "SilentlyContinue"

$startupDir = [Environment]::GetFolderPath("Startup")
$launcherPath = Join-Path $startupDir "Start-OrbVoiceStack.bat"

if (Test-Path $launcherPath) {
  Remove-Item -LiteralPath $launcherPath -Force
  Write-Host "Removed startup launcher: $launcherPath"
} else {
  Write-Host "Startup launcher not present."
}
