# Builds dist\MusicDownloader-<version>.msi - a per-user installer, no admin rights needed.
#
# Steps: fetch tools -> PyInstaller onedir build -> heat harvests the files ->
# candle compiles -> light links the MSI.
param(
    [string]$Version = "1.0.0"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

& (Join-Path $PSScriptRoot "fetch_tools.ps1")

$wix = Join-Path $root "tools\wix"
foreach ($tool in @("heat.exe", "candle.exe", "light.exe")) {
    if (-not (Test-Path (Join-Path $wix $tool))) { throw "$tool missing - run scripts\fetch_tools.ps1" }
}

Write-Host "Installing Python dependencies ..."
python -m pip install --quiet --disable-pip-version-check --upgrade -r (Join-Path $root "requirements.txt")

Push-Location $root
try {
    Write-Host "Building the app (onedir) ..."
    $env:BUILD_ONEDIR = "1"
    python -m PyInstaller --noconfirm --clean --distpath "dist\onedir" "build.spec"
    Remove-Item Env:\BUILD_ONEDIR

    $appDir = Join-Path $root "dist\onedir\MusicDownloader"
    if (-not (Test-Path (Join-Path $appDir "MusicDownloader.exe"))) { throw "PyInstaller build failed" }

    $obj = Join-Path $root "build\msi"
    New-Item -ItemType Directory -Force $obj | Out-Null

    Write-Host "Harvesting application files ..."
    & (Join-Path $wix "heat.exe") dir $appDir `
        -cg AppFiles -dr INSTALLFOLDER -gg -g1 -sfrag -srd -sreg -scom `
        -var var.SourceDir -out (Join-Path $obj "AppFiles.wxs")
    if ($LASTEXITCODE -ne 0) { throw "heat failed" }

    Write-Host "Compiling installer ..."
    & (Join-Path $wix "candle.exe") `
        -nologo -arch x64 `
        -dSourceDir="$appDir" `
        -dProductVersion="$Version" `
        -dIconFile="$(Join-Path $root 'installer\app.ico')" `
        -dLicenseFile="$(Join-Path $root 'installer\License.rtf')" `
        -out "$obj\\" `
        (Join-Path $root "installer\Product.wxs") (Join-Path $obj "AppFiles.wxs")
    if ($LASTEXITCODE -ne 0) { throw "candle failed" }

    $msi = Join-Path $root "dist\MusicDownloader-$Version.msi"
    Write-Host "Linking MSI (this compresses ~300 MB, give it a minute) ..."
    & (Join-Path $wix "light.exe") `
        -nologo -ext WixUIExtension -ext WixUtilExtension `
        -sice:ICE38 -sice:ICE43 -sice:ICE57 -sice:ICE61 -sice:ICE64 -sice:ICE91 `
        -out $msi `
        (Join-Path $obj "Product.wixobj") (Join-Path $obj "AppFiles.wixobj")
    if ($LASTEXITCODE -ne 0) { throw "light failed" }

    Write-Host ("Done: {0} ({1:N0} MB)" -f $msi, ((Get-Item $msi).Length / 1MB))
} finally {
    Pop-Location
}
