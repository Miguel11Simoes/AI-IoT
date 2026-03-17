param(
  [ValidateSet("build", "upload")]
  [string]$Action = "build",
  [ValidateSet("stage1", "full")]
  [string]$Profile = "stage1",
  [string]$UploadPort = ""
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PLATFORMIO_PACKAGES_DIR = Join-Path $projectRoot ".pio-cdu-packages"
$pioExe = Join-Path $env:USERPROFILE ".platformio\penv\Scripts\platformio.exe"

if (-not (Test-Path $pioExe)) {
  throw "PlatformIO executable not found at $pioExe"
}

Push-Location $projectRoot
try {
  $envName = if ($Profile -eq "full") { "cdu_esp32c6_full" } else { "cdu_esp32c6" }
  if ($Action -eq "upload") {
    if ([string]::IsNullOrWhiteSpace($UploadPort)) {
      & $pioExe run -e $envName -t upload
    } else {
      & $pioExe run -e $envName -t upload --upload-port $UploadPort
    }
  } else {
    & $pioExe run -e $envName
  }
} finally {
  Pop-Location
}
