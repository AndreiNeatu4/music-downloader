# Downloads the helper binaries the app bundles, so neither the dev machine nor
# the end user needs ffmpeg or a JavaScript runtime installed.
#   ffmpeg/ffprobe - audio extraction and conversion
#   qjs (QuickJS)  - yt-dlp needs a JS runtime to solve YouTube's challenges,
#                    otherwise every media request comes back as HTTP 403
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$tools = Join-Path $root "tools"

function Get-Ffmpeg {
    $dest = Join-Path $tools "ffmpeg"
    if ((Test-Path (Join-Path $dest "ffmpeg.exe")) -and (Test-Path (Join-Path $dest "ffprobe.exe"))) {
        Write-Host "ffmpeg already present"
        return
    }
    New-Item -ItemType Directory -Force $dest | Out-Null

    $url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    $tmp = Join-Path $env:TEMP "ffmpeg-essentials.zip"
    $extract = Join-Path $env:TEMP "ffmpeg-extract"

    Write-Host "Downloading ffmpeg ..."
    Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
    if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
    Expand-Archive -Path $tmp -DestinationPath $extract -Force

    foreach ($exe in @("ffmpeg.exe", "ffprobe.exe")) {
        $found = Get-ChildItem -Path $extract -Recurse -Filter $exe | Select-Object -First 1
        if ($null -eq $found) { throw "$exe not found in the downloaded archive" }
        Copy-Item $found.FullName (Join-Path $dest $exe) -Force
        Write-Host "  -> $exe"
    }
    Remove-Item -Recurse -Force $extract
    Remove-Item -Force $tmp
}

function Get-QuickJs {
    $dest = Join-Path $tools "qjs"
    if (Test-Path (Join-Path $dest "qjs.exe")) {
        Write-Host "qjs already present"
        return
    }
    New-Item -ItemType Directory -Force $dest | Out-Null

    Write-Host "Downloading QuickJS ..."
    $api = "https://api.github.com/repos/quickjs-ng/quickjs/releases/latest"
    $release = Invoke-RestMethod -Uri $api -UseBasicParsing -Headers @{ "User-Agent" = "fetch-tools" }
    $asset = $release.assets | Where-Object { $_.name -eq "qjs-windows-x86_64.exe" } | Select-Object -First 1
    if ($null -eq $asset) { throw "qjs-windows-x86_64.exe not found in the latest release" }

    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile (Join-Path $dest "qjs.exe") -UseBasicParsing
    Write-Host "  -> qjs.exe ($($release.tag_name))"
}

function Get-Wix {
    $dest = Join-Path $tools "wix"
    if (Test-Path (Join-Path $dest "candle.exe")) {
        Write-Host "WiX already present"
        return
    }
    New-Item -ItemType Directory -Force $dest | Out-Null

    Write-Host "Downloading WiX toolset ..."
    $url = "https://github.com/wixtoolset/wix3/releases/download/wix3141rtm/wix314-binaries.zip"
    $tmp = Join-Path $env:TEMP "wix314-binaries.zip"
    Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
    Expand-Archive -Path $tmp -DestinationPath $dest -Force
    Remove-Item -Force $tmp
    Write-Host "  -> candle.exe, light.exe, heat.exe"
}

Get-Ffmpeg
Get-QuickJs
Get-Wix
Write-Host "Done. Tools are in $tools"
