param(
  [ValidateSet("build", "upload")]
  [string]$Action = "build",
  [string]$RackR00Port = "",
  [string]$RackR07Port = "",
  [string]$CduPort = ""
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$pioExe = Join-Path $env:USERPROFILE ".platformio\penv\Scripts\platformio.exe"
$cduPackagesDir = Join-Path $projectRoot ".pio-cdu-packages"

if (-not (Test-Path $pioExe)) {
  throw "PlatformIO executable not found at $pioExe"
}

function Invoke-PioTarget {
  param(
    [Parameter(Mandatory = $true)]
    [string]$EnvName,
    [Parameter(Mandatory = $true)]
    [string]$ActionName,
    [string]$UploadPort = ""
  )

  $pioArgs = @("run", "-e", $EnvName)
  if ($ActionName -eq "upload") {
    $pioArgs += @("-t", "upload")
    if (-not [string]::IsNullOrWhiteSpace($UploadPort)) {
      $pioArgs += @("--upload-port", $UploadPort)
    }
  }

  $previousPackagesDir = $env:PLATFORMIO_PACKAGES_DIR
  try {
    if ($EnvName -like "cdu_*") {
      $env:PLATFORMIO_PACKAGES_DIR = $cduPackagesDir
    } elseif ([string]::IsNullOrWhiteSpace($previousPackagesDir)) {
      Remove-Item Env:PLATFORMIO_PACKAGES_DIR -ErrorAction SilentlyContinue
    }

    Write-Host "==> $ActionName $EnvName" -ForegroundColor Cyan
    & $pioExe @pioArgs
    if ($LASTEXITCODE -ne 0) {
      throw "PlatformIO failed for $EnvName"
    }
  } finally {
    if ([string]::IsNullOrWhiteSpace($previousPackagesDir)) {
      Remove-Item Env:PLATFORMIO_PACKAGES_DIR -ErrorAction SilentlyContinue
    } else {
      $env:PLATFORMIO_PACKAGES_DIR = $previousPackagesDir
    }
  }
}

$targets = @(
  @{ Env = "rack_r00"; Port = $RackR00Port }
  @{ Env = "rack_r07"; Port = $RackR07Port }
  @{ Env = "cdu_esp32c6"; Port = $CduPort }
)

Push-Location $projectRoot
try {
  foreach ($target in $targets) {
    Invoke-PioTarget -EnvName $target.Env -ActionName $Action -UploadPort $target.Port
  }
} finally {
  Pop-Location
}
