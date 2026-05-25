$ErrorActionPreference = "Stop"

$dandyRoot = "C:\Users\bryan\Downloads\dandy_merge\Phil_and_Jim_Dandy_Show"
$backendRoot = Join-Path $dandyRoot "backend"
$frontendRoot = Join-Path $dandyRoot "frontend"
$ffmpegBin = Join-Path $dandyRoot "staging\ffmpeg\ffmpeg-master-latest-win64-gpl\bin"
$obsExe = "C:\Program Files\obs-studio\bin\64bit\obs64.exe"

if (-not (Test-Path $dandyRoot)) {
  throw "Dandy Studio root not found: $dandyRoot"
}

if (-not (Test-Path $backendRoot)) {
  throw "Backend root not found: $backendRoot"
}

if (-not (Test-Path $frontendRoot)) {
  throw "Frontend root not found: $frontendRoot"
}

$backendCommand = @"
`$env:PATH = "$ffmpegBin;`$env:PATH"
Set-Location "$backendRoot"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
"@

$frontendCommand = @"
Set-Location "$frontendRoot"
npm run dev -- --host 0.0.0.0 --port 5173
"@

Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $backendCommand -WorkingDirectory $backendRoot | Out-Null
Start-Sleep -Seconds 2
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $frontendCommand -WorkingDirectory $frontendRoot | Out-Null

if (Test-Path $obsExe) {
  Start-Process $obsExe | Out-Null
}

Start-Sleep -Seconds 3
Start-Process "http://127.0.0.1:5173" | Out-Null
