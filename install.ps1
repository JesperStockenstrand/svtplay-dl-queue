<#
.SYNOPSIS
  Install the svtplay-dl Queue helper app (native messaging host) on Windows.

.DESCRIPTION
  Copies the helper to %LOCALAPPDATA%\svtplay-dl-queue and registers it with
  Chrome, Edge, Brave, Chromium, Vivaldi and Firefox for the current user.
  No administrator rights are needed.

  Run it from the project folder:
    powershell -ExecutionPolicy Bypass -File install.ps1

.PARAMETER ExtensionId
  Also allow these Chromium extension IDs (e.g. a Chrome Web Store build).
  The ID of the unpacked extension in this repo is always allowed.
#>
param(
  [string[]]$ExtensionId = @()
)

$ErrorActionPreference = 'Stop'

$HostName  = 'svtplay_dl_queue'
$App       = 'svtplay-dl-queue'
$ChromeIds = @('oonjepebfihcafficfecahlgfafinoee') + $ExtensionId  # fixed by "key" in manifest.json
$FirefoxId = 'svtplay-dl-queue@svtplay-dl-queue'
$RepoDir   = $PSScriptRoot
$Data      = Join-Path $env:LOCALAPPDATA $App
$Bin       = Join-Path $Data 'bin'

# Registry keys where each browser looks for native messaging hosts.
$Browsers = [ordered]@{
  'Google Chrome' = 'HKCU:\Software\Google\Chrome\NativeMessagingHosts'
  'Microsoft Edge' = 'HKCU:\Software\Microsoft\Edge\NativeMessagingHosts'
  'Brave' = 'HKCU:\Software\BraveSoftware\Brave-Browser\NativeMessagingHosts'
  'Chromium' = 'HKCU:\Software\Chromium\NativeMessagingHosts'
  'Vivaldi' = 'HKCU:\Software\Vivaldi\NativeMessagingHosts'
  'Firefox' = 'HKCU:\Software\Mozilla\NativeMessagingHosts'
}

function Write-Utf8NoBom([string]$Path, [string]$Text) {
  [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding $false))
}

# 1. Find a real Python 3.8+ (not the Microsoft Store placeholder).
function Find-Python {
  $candidates = @(
    @('py', '-3'),
    @('python'),
    @('python3')
  )
  foreach ($c in $candidates) {
    if (-not (Get-Command $c[0] -ErrorAction SilentlyContinue)) { continue }
    $pyArgs = @($c | Select-Object -Skip 1) + @('-c', 'import sys; print(sys.executable); print(sys.version_info >= (3, 8))')
    try {
      $out = @(& $c[0] @pyArgs 2>$null)
    } catch { continue }
    if ($LASTEXITCODE -eq 0 -and $out.Count -ge 2 -and $out[1] -eq 'True' -and (Test-Path $out[0])) {
      return $out[0]
    }
  }
  return $null
}

$Python = Find-Python
if (-not $Python) {
  Write-Error ("Python 3.8 or later is required but wasn't found. Install it from " +
    "https://www.python.org/downloads/ or with: winget install Python.Python.3.13")
  exit 1
}

# 2. Copy the helper to a stable location, so the repo can be moved or deleted.
New-Item -ItemType Directory -Force -Path $Bin | Out-Null
Copy-Item (Join-Path $RepoDir 'host\svtdl_queue.py') (Join-Path $Bin 'svtdl_queue.py') -Force

# The browser starts this .bat file. It must print nothing but the helper's
# output, hence @echo off. Written in the console code page so paths with
# letters like å, ä, ö work.
$Launcher = Join-Path $Bin 'svtdl-queue.bat'
$bat = "@echo off`r`n`"$Python`" `"%~dp0svtdl_queue.py`" %*`r`n"
$oem = [Text.Encoding]::GetEncoding([Globalization.CultureInfo]::CurrentCulture.TextInfo.OEMCodePage)
[IO.File]::WriteAllText($Launcher, $bat, $oem)

# 3. Write the host manifests and register them.
$chromeManifest = Join-Path $Data "$HostName.chrome.json"
$firefoxManifest = Join-Path $Data "$HostName.firefox.json"

Write-Utf8NoBom $chromeManifest ([ordered]@{
  name = $HostName
  description = 'svtplay-dl Queue helper'
  path = $Launcher
  type = 'stdio'
  allowed_origins = @($ChromeIds | ForEach-Object { "chrome-extension://$_/" })
} | ConvertTo-Json)

Write-Utf8NoBom $firefoxManifest ([ordered]@{
  name = $HostName
  description = 'svtplay-dl Queue helper'
  path = $Launcher
  type = 'stdio'
  allowed_extensions = @($FirefoxId)
} | ConvertTo-Json)

foreach ($browser in $Browsers.Keys) {
  $key = Join-Path $Browsers[$browser] $HostName
  $manifest = if ($browser -eq 'Firefox') { $firefoxManifest } else { $chromeManifest }
  New-Item -Path $key -Value $manifest -Force | Out-Null  # sets the key's default value
  Write-Host "Registered with: $browser"
}

Write-Host ''
Write-Host "Helper installed in: $Data"
Write-Host "Using Python: $Python"

# 4. Check for svtplay-dl the same way the helper will.
$svt = & $Python -I -c "import sys; sys.path.insert(0, r'$Bin'); import svtdl_queue as q; print(q.find_binary(q.load_config()) or '')"
if (-not $svt) {
  Write-Host ''
  Write-Host "Note: svtplay-dl wasn't found. Install it with 'pipx install svtplay-dl' (or"
  Write-Host "'pip install svtplay-dl'), or set its path in the extension settings. It also"
  Write-Host "needs ffmpeg: winget install Gyan.FFmpeg"
} else {
  Write-Host "Found svtplay-dl: $svt"
}

Write-Host ''
Write-Host "Next: load the 'extension' folder in your browser (see README.md),"
Write-Host 'then restart the browser if it was already running.'
