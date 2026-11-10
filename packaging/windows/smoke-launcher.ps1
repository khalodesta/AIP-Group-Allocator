# Validate the actual ZIP with the original batch/PowerShell launch method.
param([string]$Zip = 'release/AIP-Week2-Allocator-Windows.zip')
$ErrorActionPreference = 'Stop'
$OriginalPath = $env:PATH
$env:AIP_NO_BROWSER = '1'
# PowerShell is an OS component; Node/Python must come from the package.
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\WindowsPowerShell\v1.0"
$TestRoot = Join-Path $env:RUNNER_TEMP 'Downloads\AIP original packaging test'
$Package = Join-Path $TestRoot 'AIP-Week2-Allocator'
$Diagnostic = Join-Path $env:RUNNER_TEMP 'AIP-launcher-diagnostics'
New-Item -ItemType Directory -Force $Diagnostic | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::ExtractToDirectory((Resolve-Path $Zip).Path, $TestRoot)

function Run-Batch([string]$Name, [string]$Label) {
  # Original PowerShell startup can leave inherited console handles open in
  # descendants. Stream to CI directly instead of reading a locked capture file.
  Write-Host "Running $Name ($Label)"
  $Process = Start-Process -FilePath $env:ComSpec -ArgumentList "/d /c call `"$(Join-Path $Package $Name)`"" -PassThru -NoNewWindow
  $null = $Process.Handle
  if (-not $Process.WaitForExit(180000)) { $Process.Kill(); throw "$Name exceeded its startup/shutdown time bound" }
  $Process.Refresh()
  if ($Process.ExitCode -ne 0) { throw "$Name failed with exit code $($Process.ExitCode); see packaged startup logs" }
}
function Assert-Healthy {
  foreach ($Base in @('http://127.0.0.1:8000','http://127.0.0.1:3000')) {
    $Health = Invoke-RestMethod "$Base/api/health" -TimeoutSec 10
    if ($Health.service -ne 'allocator-api' -or $Health.status -ne 'healthy') { throw "Backend/API proxy identity failed" }
  }
  if ((Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:3000' -TimeoutSec 10).StatusCode -ne 200) { throw 'Frontend unavailable' }
  if (@(Get-NetTCPConnection -State Listen -LocalPort 3000,8000 | Where-Object { $_.LocalAddress -notin @('127.0.0.1','::1') }).Count) { throw 'Services must bind only to loopback' }
}
function Assert-Stopped {
  $Deadline = [DateTime]::UtcNow.AddSeconds(15)
  do {
    $Listeners = @(Get-NetTCPConnection -State Listen -LocalPort 3000,8000 -ErrorAction SilentlyContinue)
    if (-not $Listeners.Count) { break }
    Start-Sleep -Milliseconds 200
  } while ([DateTime]::UtcNow -lt $Deadline)
  if ($Listeners.Count) { throw 'A packaged service survived STOP.bat' }
}
try {
  if ((Get-Command node.exe -ErrorAction SilentlyContinue) -or (Get-Command python.exe -ErrorAction SilentlyContinue)) { throw 'Runtime PATH must not contain global Node/Python' }
  foreach ($Name in @('START.bat','STOP.bat')) {
    if ((Get-Content (Join-Path $Package $Name) -Raw) -notmatch 'powershell.exe -NoProfile -File') { throw 'Original PowerShell entry point was not restored' }
  }
  if (Test-Path (Join-Path $Package 'app\launcher\allocator-launcher.exe')) { throw 'Executable supervisor must not be shipped' }
  $Info = Get-Content (Join-Path $Package 'BUILD-INFO.json') -Raw | ConvertFrom-Json
  if ($Info.commit -ne $env:GITHUB_SHA) { throw 'ZIP does not identify the current release commit' }
  Run-Batch 'START.bat' 'start'
  Assert-Healthy
  $BackendPid = Get-Content (Join-Path $Package '.runtime\backend.pid')
  $FrontendPid = Get-Content (Join-Path $Package '.runtime\frontend.pid')
  Run-Batch 'START.bat' 'duplicate-start'
  if ($BackendPid -ne (Get-Content (Join-Path $Package '.runtime\backend.pid')) -or $FrontendPid -ne (Get-Content (Join-Path $Package '.runtime\frontend.pid'))) { throw 'Duplicate start replaced running processes' }
  # Real requests through the packaged frontend, not direct Python/health only.
  & (Join-Path $PSScriptRoot 'smoke-allocation27.ps1') -DiagnosticDirectory $Diagnostic
  & (Join-Path $PSScriptRoot 'smoke-allocations.ps1')
  Run-Batch 'STOP.bat' 'stop'
  Assert-Stopped
  Run-Batch 'START.bat' 'restart'
  Assert-Healthy
  Run-Batch 'STOP.bat' 'restart-stop'
  Assert-Stopped
  Write-Host 'Original batch/PowerShell launcher, real 27-person six-activity proxy requests, uploads/exports, duplicate start, stop/restart, spaces and bundled runtimes passed.'
} finally {
  try { Run-Batch 'STOP.bat' 'cleanup-stop' } catch { Write-Warning $_ }
  if (Test-Path (Join-Path $Package 'logs')) {
    Copy-Item (Join-Path $Package 'logs') $Diagnostic -Recurse -Force
    foreach ($Name in @('backend-error.log','frontend-error.log','launcher-error.log')) {
      $Log = Join-Path $Package "logs\$Name"
      if ((Test-Path $Log) -and (Get-Item $Log).Length) { Write-Host "Captured $Name"; Get-Content $Log -Tail 60 | Write-Host }
    }
  }
  $env:PATH = $OriginalPath
}
