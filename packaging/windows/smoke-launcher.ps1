# Windows CI only. Tests the actual ZIP extracted under a path with spaces.
param([string]$Zip = "release/AIP-Week2-Allocator-Windows.zip")
$ErrorActionPreference = "Stop"
$OriginalPath = $env:PATH
$env:AIP_NO_BROWSER = "1"
$env:AIP_NO_PAUSE = "1"
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
$TestRoot = Join-Path $env:RUNNER_TEMP "Downloads\AIP Windows release test"
$Package = Join-Path $TestRoot "AIP-Week2-Allocator"
$Diagnostic = Join-Path $env:RUNNER_TEMP "AIP-launcher-diagnostics"
New-Item -ItemType Directory -Force $Diagnostic | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::ExtractToDirectory((Resolve-Path $Zip).Path, $TestRoot)
$StateFile = Join-Path $Package ".runtime\launcher.json"

function Run-Batch([string]$Name, [int]$Expected = 0, [string]$Label = "") {
  if (-not $Label) { $Label = $Name.Replace('.bat', '') }
  $Out = Join-Path $Diagnostic "$Label.out.txt"
  $Err = Join-Path $Diagnostic "$Label.err.txt"
  $Process = Start-Process -FilePath $env:ComSpec -ArgumentList "/d /c call `"$(Join-Path $Package $Name)`"" -PassThru -WindowStyle Hidden -RedirectStandardOutput $Out -RedirectStandardError $Err
  $null = $Process.Handle
  if (-not $Process.WaitForExit(170000)) { $Process.Kill(); throw "$Name did not finish within its time bound" }
  $Process.Refresh()
  $Text = [IO.File]::ReadAllText($Out) + [IO.File]::ReadAllText($Err)
  Write-Host $Text
  if ($Process.ExitCode -ne $Expected) { throw "$Name returned $($Process.ExitCode), expected $Expected. $Text" }
  return $Text
}

function Assert-Healthy {
  $Backend = Invoke-RestMethod "http://127.0.0.1:8000/api/health" -TimeoutSec 5
  $Proxy = Invoke-RestMethod "http://127.0.0.1:3000/api/health" -TimeoutSec 5
  if ($Backend.service -ne 'allocator-api' -or $Proxy.service -ne 'allocator-api') { throw "API identity/proxy check failed" }
  if ((Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:3000" -TimeoutSec 5).StatusCode -ne 200) { throw "Website unavailable" }
  $Listeners = @(Get-NetTCPConnection -State Listen -LocalPort 3000,8000)
  if ($Listeners.Count -lt 2 -or @($Listeners | Where-Object { $_.LocalAddress -notin @('127.0.0.1','::1') }).Count) { throw "Services must listen on loopback only" }
}

function Assert-Stopped {
  foreach ($Port in @(3000,8000)) {
    $Deadline = [DateTime]::UtcNow.AddSeconds(15)
    do {
      $Listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
      if (-not $Listeners.Count) { break }
      Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $Deadline)
    if ($Listeners.Count) { throw "Owned service on port $Port survived STOP.bat" }
  }
  if (Test-Path $StateFile) { throw "Process tracking was not cleaned" }
}

try {
  if ((Get-Command node.exe -ErrorAction SilentlyContinue) -or (Get-Command python.exe -ErrorAction SilentlyContinue)) { throw "Runtime test PATH must contain no global Node/Python" }
  foreach ($Name in @('START.bat', 'STOP.bat')) {
    if ((Get-Content (Join-Path $Package $Name) -Raw) -match '(?i)powershell|\.ps1') { throw "Batch entry point invokes PowerShell" }
  }
  if (@(Get-ChildItem $Package -Recurse -Filter '*.ps1').Count) { throw "The runtime ZIP must not contain PowerShell launch scripts" }
  $Info = Get-Content (Join-Path $Package 'BUILD-INFO.json') -Raw | ConvertFrom-Json
  if ($Info.commit -ne $env:GITHUB_SHA) { throw "ZIP source commit does not match the workflow commit" }
  $Directory = $null
  Run-Batch 'STOP.bat' 0 'already-stopped' | Out-Null
  New-Item -ItemType Directory -Force (Split-Path $StateFile) | Out-Null
  Set-Content $StateFile '{"supervisor":{"pid":99999999,"created":1,"path":"unrelated.exe"}}'
  Run-Batch 'START.bat' 0 'stale-start' | Out-Null
  Assert-Healthy
  $First = Get-Content $StateFile -Raw | ConvertFrom-Json
  Run-Batch 'START.bat' 0 'duplicate-start' | Out-Null
  $Second = Get-Content $StateFile -Raw | ConvertFrom-Json
  if ($First.supervisor.created -ne $Second.supervisor.created -or $First.backend.pid -ne $Second.backend.pid -or $First.frontend.pid -ne $Second.frontend.pid) { throw "Duplicate start created extra processes" }
  $Directory = Invoke-RestMethod "http://127.0.0.1:3000/api/universities" -TimeoutSec 10
  if ($Directory.count -lt 130 -or @($Directory.universities | Where-Object { $_.category -notin @('public','private') }).Count) { throw "Offline Public/Private university directory is incomplete" }
  if (-not @($Directory.universities | Where-Object { $_.official_english_name -eq 'Capital-Helwan University' }).Count) { throw "Latest Capital-Helwan source data missing" }
  & (Join-Path $PSScriptRoot 'smoke-allocations.ps1')
  Run-Batch 'STOP.bat' 0 'first-stop' | Out-Null
  Assert-Stopped
  Run-Batch 'STOP.bat' 0 'second-stop' | Out-Null
  # Reused PID tracking must never cause STOP to terminate the CI host.
  Set-Content $StateFile (@{supervisor=@{pid=$PID;created=1;path='unrelated.exe'}} | ConvertTo-Json)
  Run-Batch 'STOP.bat' 0 'unrelated-pid' | Out-Null
  if (Test-Path $StateFile) { throw "Stale tracking was not cleared" }
  foreach ($Port in @(8000,3000)) {
    $Listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $Port)
    $Listener.Start()
    try {
      $Text = Run-Batch 'START.bat' 1 "occupied-$Port"
      if ($Text -notmatch "Port $Port is occupied") { throw "Port conflict did not identify $Port" }
      Run-Batch 'STOP.bat' 0 "conflict-stop-$Port" | Out-Null
      if (-not $Listener.Server.IsBound) { throw "STOP affected an unrelated listener" }
    } finally { $Listener.Stop() }
  }
  Run-Batch 'START.bat' 0 'restart' | Out-Null
  Assert-Healthy
  Run-Batch 'STOP.bat' 0 'restart-stop' | Out-Null
  Assert-Stopped
  Write-Host "Windows ZIP startup, stop, duplicate start, restart, stale PID, occupied ports, spaces, loopback and bundled runtimes passed."
} finally {
  try { Run-Batch 'STOP.bat' 0 'cleanup-stop' | Out-Null } catch { Write-Warning $_ }
  if (Test-Path (Join-Path $Package 'logs')) { Copy-Item (Join-Path $Package 'logs') $Diagnostic -Recurse -Force }
  $env:PATH = $OriginalPath
}
