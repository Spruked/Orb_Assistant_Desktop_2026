param(
  [string]$TaskName = "OrbVoiceStackStartup"
)

$ErrorActionPreference = "Continue"

schtasks /Delete /F /TN $TaskName | Out-Null
schtasks /Delete /F /TN "$TaskName-Logon" | Out-Null

Write-Host "Removed tasks:"
Write-Host " - $TaskName"
Write-Host " - $TaskName-Logon"
