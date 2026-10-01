# Builds dist\MusicDownloader.exe - a single self-contained file.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

& (Join-Path $PSScriptRoot "fetch_tools.ps1")

Write-Host "Installing Python dependencies ..."
python -m pip install --quiet --disable-pip-version-check --upgrade -r (Join-Path $root "requirements.txt")

Write-Host "Running PyInstaller ..."
Push-Location $root
try {
    python -m PyInstaller --noconfirm --clean "build.spec"
} finally {
    Pop-Location
}

$exe = Join-Path $root "dist\MusicDownloader.exe"
if (-not (Test-Path $exe)) { throw "build failed - $exe not found" }
Write-Host ("Done: {0} ({1:N0} MB)" -f $exe, ((Get-Item $exe).Length / 1MB))
