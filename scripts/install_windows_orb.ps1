[CmdletBinding()]
param(
  [string]$SourceRoot = (Split-Path -Parent $PSScriptRoot),
  [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "OrbAssistantDesktop"),
  [string]$DriveLetter = "O",
  [int]$DataSizeGB = 10,
  [switch]$RegisterStartup,
  [switch]$SkipDataDrive,
  [string]$PythonPath = "python"
)

$ErrorActionPreference = "Stop"

function Test-Administrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

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

function Ensure-OrbDataDrive {
  param(
    [string]$RequestedDriveLetter,
    [int]$RequestedSizeGB
  )

  $driveRoot = "{0}:\" -f $RequestedDriveLetter.TrimEnd(":")
  if (Test-Path $driveRoot) {
    return $driveRoot
  }

  if ($SkipDataDrive) {
    return $null
  }

  if (-not (Test-Administrator)) {
    Write-Warning "Skipping O: drive creation because this installer is not running as Administrator."
    return $null
  }

  $storageHost = Join-Path $env:ProgramData "OrbAssistantDesktop\storage"
  $vhdPath = Join-Path $storageHost "orb-data.vhdx"
  New-Item -ItemType Directory -Force -Path $storageHost | Out-Null

  if (-not (Test-Path $vhdPath)) {
    $diskpartScript = @(
      "create vdisk file=`"$vhdPath`" maximum=$($RequestedSizeGB * 1024) type=expandable",
      "select vdisk file=`"$vhdPath`"",
      "attach vdisk"
    )
    $diskpartFile = Join-Path $env:TEMP ("orb-create-vhd-{0}.txt" -f ([guid]::NewGuid().ToString("N")))
    try {
      Set-Content -Path $diskpartFile -Value $diskpartScript -Encoding ASCII
      & diskpart /s $diskpartFile | Out-Null
      if ($LASTEXITCODE -ne 0) {
        throw "diskpart failed while creating the orb data volume."
      }
    } finally {
      Remove-Item $diskpartFile -Force -ErrorAction SilentlyContinue
    }
  } else {
    Mount-DiskImage -ImagePath $vhdPath -ErrorAction SilentlyContinue | Out-Null
  }

  $diskImage = Get-DiskImage -ImagePath $vhdPath
  $disk = $diskImage | Get-Disk

  if ($disk.PartitionStyle -eq "RAW") {
    Initialize-Disk -Number $disk.Number -PartitionStyle GPT | Out-Null
  }

  $partition = Get-Partition -DiskNumber $disk.Number -ErrorAction SilentlyContinue |
    Where-Object { $_.Type -ne "Reserved" } |
    Select-Object -First 1

  if (-not $partition) {
    $partition = New-Partition -DiskNumber $disk.Number -UseMaximumSize -DriveLetter $RequestedDriveLetter
    Format-Volume -DriveLetter $RequestedDriveLetter -FileSystem NTFS -NewFileSystemLabel "ORB_DATA" -Confirm:$false | Out-Null
  } elseif ($partition.DriveLetter -ne $RequestedDriveLetter.TrimEnd(":")) {
    $partition | Set-Partition -NewDriveLetter $RequestedDriveLetter.TrimEnd(":") | Out-Null
  }

  return $driveRoot
}

$sourceRoot = (Resolve-Path $SourceRoot).Path
if (-not (Test-Path $sourceRoot)) {
  throw "Source root not found: $SourceRoot"
}

$installRootResolved = [System.IO.Path]::GetFullPath($InstallRoot)
New-Item -ItemType Directory -Force -Path $installRootResolved | Out-Null

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

Invoke-Robocopy -From $sourceRoot -To $installRootResolved -ExcludeDirs $excludeDirs -ExcludeFiles $excludeFiles

$dataDriveRoot = Ensure-OrbDataDrive -RequestedDriveLetter $DriveLetter -RequestedSizeGB $DataSizeGB
$dataRoot = if ($dataDriveRoot) {
  Join-Path $dataDriveRoot "OrbAssistantDesktop"
} else {
  Join-Path $installRootResolved "orb_data"
}

$userDataDir = Join-Path $dataRoot ".orb-assistant-desktop"
$systemRoot = Join-Path $dataRoot "system"
$sharedMeshRoot = if ($dataDriveRoot) {
  Join-Path $dataDriveRoot "orb_mesh"
} else {
  Join-Path $dataRoot "orb_mesh"
}

New-Item -ItemType Directory -Force -Path $dataRoot, $userDataDir, $systemRoot, $sharedMeshRoot | Out-Null

$localOverride = @"
`$env:ORB_INSTANCE_ID = "desktop"
`$env:ORB_PRODUCT_NAME = "Orb Assistant Desktop"
`$env:ORB_APP_ID = "com.orbassistant.desktop"
`$env:ORB_USER_DATA_DIR = "$userDataDir"
`$env:ORB_SYSTEM_ROOT = "$systemRoot"
`$env:ORB_SHARED_MESH_ROOT = "$sharedMeshRoot"
`$env:ORB_MESH_ROOT = "$sharedMeshRoot"
`$env:ORB_IDENTITY_PATH = "$(Join-Path $sharedMeshRoot "identity\bryan_spruk_identity.json")"
`$env:ORB_SINGLE_INSTANCE = "1"
`$env:ORB_PYTHON_PATH = "$PythonPath"
"@
Set-Content -Path (Join-Path $installRootResolved "orb-instance.local.ps1") -Value $localOverride -Encoding UTF8

if ($RegisterStartup) {
  $startupDir = [Environment]::GetFolderPath("Startup")
  $startupLauncher = Join-Path $startupDir "Launch Orb Assistant Desktop.bat"
  $startupContent = "@echo off`r`ncall `"$installRootResolved\launch_desktop_orb.bat`"`r`n"
  Set-Content -Path $startupLauncher -Value $startupContent -Encoding ASCII
}

$installManifest = @{
  installed_at = (Get-Date).ToString("o")
  source_root = $sourceRoot
  install_root = $installRootResolved
  data_root = $dataRoot
  user_data_dir = $userDataDir
  system_root = $systemRoot
  shared_mesh_root = $sharedMeshRoot
  startup_registered = [bool]$RegisterStartup
  data_drive = $dataDriveRoot
  python_path = $PythonPath
}
$installManifest | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $installRootResolved "install.manifest.json") -Encoding UTF8

Write-Output ("Orb installed to {0}" -f $installRootResolved)
Write-Output ("Orb data root: {0}" -f $dataRoot)
if ($RegisterStartup) {
  Write-Output "Startup registration created."
}
