param(
  [string]$TaskName = "OrbVoiceStackStartup"
)

$ErrorActionPreference = "Stop"

$scriptPath = "R:\R_Drive_Substrate\Orb_Assistant_Desktop\scripts\Start-OrbVoiceStack.ps1"
if (-not (Test-Path $scriptPath)) {
  throw "Missing startup script: $scriptPath"
}

$argument = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Warmup -StartTunnel"

Write-Host "Registering startup task: $TaskName"

try {
  schtasks /Create /F /TN $TaskName /SC ONSTART /DELAY 0001:00 /RL LIMITED /TR "powershell.exe $argument" | Out-Null
  schtasks /Create /F /TN "$TaskName-Logon" /SC ONLOGON /RL LIMITED /TR "powershell.exe $argument" | Out-Null
} catch {
  Write-Host "Task Scheduler registration failed, falling back to Startup shortcut."
}

$startupDir = [Environment]::GetFolderPath("Startup")
$launcherPath = Join-Path $startupDir "Start-OrbVoiceStack.bat"
$launcher = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Warmup -StartTunnel`r`n"
Set-Content -Path $launcherPath -Value $launcher -Encoding ASCII
Write-Host "Startup launcher ensured: $launcherPath"

Write-Host "Startup registration requested:"
Write-Host " - $TaskName (ONSTART)"
Write-Host " - $TaskName-Logon (ONLOGON)"
