<#
.SYNOPSIS
  Remove the svtplay-dl Queue helper app and its browser registrations on Windows.

.DESCRIPTION
  Run it from the project folder:
    powershell -ExecutionPolicy Bypass -File uninstall.ps1 [-KeepData]

  Downloaded files are not touched.

.PARAMETER KeepData
  Keep the queue and settings, only remove the helper.
#>
param(
  [switch]$KeepData
)

$ErrorActionPreference = 'Stop'

$HostName = 'svtplay_dl_queue'
$Data = Join-Path $env:LOCALAPPDATA 'svtplay-dl-queue'

$keys = @(
  'HKCU:\Software\Google\Chrome\NativeMessagingHosts',
  'HKCU:\Software\Microsoft\Edge\NativeMessagingHosts',
  'HKCU:\Software\BraveSoftware\Brave-Browser\NativeMessagingHosts',
  'HKCU:\Software\Chromium\NativeMessagingHosts',
  'HKCU:\Software\Vivaldi\NativeMessagingHosts',
  'HKCU:\Software\Mozilla\NativeMessagingHosts'
)
foreach ($k in $keys) {
  $key = Join-Path $k $HostName
  if (Test-Path $key) {
    Remove-Item $key -Recurse -Force
    Write-Host "Removed: $key"
  }
}

# Stop a running worker (and the downloads it started).
$pidFile = Join-Path $Data 'worker.pid'
if (Test-Path $pidFile) {
  $workerPid = (Get-Content $pidFile -Raw).Trim()
  if ($workerPid) { & taskkill /T /F /PID $workerPid 2>$null | Out-Null }
  Start-Sleep -Milliseconds 500
}

if ($KeepData) {
  Remove-Item (Join-Path $Data 'bin') -Recurse -Force -ErrorAction SilentlyContinue
  Get-ChildItem $Data -Filter "$HostName.*.json" -ErrorAction SilentlyContinue | Remove-Item -Force
  Write-Host "Removed the helper. Queue and settings kept in: $Data"
} else {
  Remove-Item $Data -Recurse -Force -ErrorAction SilentlyContinue
  Write-Host "Removed: $Data"
}
Write-Host 'Downloaded files are not touched. Remove the extension from your browser separately.'
