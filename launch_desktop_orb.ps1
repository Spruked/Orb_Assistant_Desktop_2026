$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
. "$root\orb-instance.windows.ps1"
$localOverride = Join-Path $root "orb-instance.local.ps1"
if (Test-Path $localOverride) {
  . $localOverride
}

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
