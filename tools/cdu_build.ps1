param(
  [ValidateSet("build", "upload")]
  [string]$Action = "build"
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PLATFORMIO_PACKAGES_DIR = Join-Path $projectRoot ".pio-cdu-packages"
$pioExe = Join-Path $env:USERPROFILE ".platformio\penv\Scripts\platformio.exe"

if (-not (Test-Path $pioExe)) {
  throw "PlatformIO executable not found at $pioExe"
}

Push-Location $projectRoot
try {
  if ($Action -eq "upload") {
    & $pioExe run -e cdu_esp32c6 -t upload
  } else {
    & $pioExe run -e cdu_esp32c6
  }
} finally {
  Pop-Location
}
