$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Logs = Join-Path $Root "logs"
$State = Join-Path $Root ".runtime"
$Backend = Join-Path $Root "app\backend\allocator-backend.exe"
$Node = Join-Path $Root "runtimes\node\node.exe"
$Server = Join-Path $Root "app\frontend\server.js"
New-Item -ItemType Directory -Force -Path $Logs, $State | Out-Null

function Fail([string]$Message) {
  $Message | Tee-Object -FilePath (Join-Path $Logs "launcher-error.log") -Append
  Write-Host ""
  Write-Host $Message -ForegroundColor Red
  Write-Host "See logs\launcher-error.log for details."
  exit 1
}
function Healthy([string]$Url) {
  try { return (Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri $Url).StatusCode -eq 200 } catch { return $false }
}
function PortInUse([int]$Port) {
  try { return $null -ne (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop | Select-Object -First 1) }
  catch { return (Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -WarningAction SilentlyContinue).TcpTestSucceeded }
}
function WaitHealthy([string]$Url, [int]$Seconds) {
  foreach ($attempt in 1..$Seconds) { if (Healthy $Url) { return $true }; Start-Sleep -Seconds 1 }
  return $false
}

foreach ($required in @($Backend, $Node, $Server)) { if (-not (Test-Path $required)) { Fail "A required application file is missing: $required" } }

$BackendPidFile = Join-Path $State "backend.pid"
$FrontendPidFile = Join-Path $State "frontend.pid"
if ((Healthy "http://127.0.0.1:8000/api/health") -and (Healthy "http://127.0.0.1:3000")) {
  Write-Host "AIP Week 2 Allocator is already running." -ForegroundColor Yellow
  if ($env:AIP_NO_BROWSER -ne "1") { Start-Process "http://localhost:3000" }
  exit 0
}
if (PortInUse 8000) { Fail "The application could not start because port 8000 is already in use. Please contact the application administrator." }
if (PortInUse 3000) { Fail "The application could not start because port 3000 is already in use. Please contact the application administrator." }

try {
  $backendProcess = Start-Process -FilePath $Backend -WorkingDirectory (Split-Path $Backend) -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Logs "backend.log") -RedirectStandardError (Join-Path $Logs "backend-error.log")
  Set-Content -Path $BackendPidFile -Value $backendProcess.Id
  if (-not (WaitHealthy "http://127.0.0.1:8000/api/health" 60)) { throw "The allocation service did not become ready. See logs\backend-error.log." }

  $env:HOSTNAME = "127.0.0.1"
  $env:PORT = "3000"
  $frontendProcess = Start-Process -FilePath $Node -ArgumentList "server.js" -WorkingDirectory (Split-Path $Server) -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Logs "frontend.log") -RedirectStandardError (Join-Path $Logs "frontend-error.log")
  Set-Content -Path $FrontendPidFile -Value $frontendProcess.Id
  if (-not (WaitHealthy "http://127.0.0.1:3000" 60)) { throw "The user interface did not become ready. See logs\frontend-error.log." }
} catch {
  & (Join-Path $PSScriptRoot "stop.ps1") -Quiet
  Fail $_.Exception.Message
}

Write-Host ""
Write-Host "AIP Week 2 Allocator is running." -ForegroundColor Green
Write-Host "Open http://localhost:3000 in your browser."
Write-Host "When finished, double-click STOP.bat."
if ($env:AIP_NO_BROWSER -ne "1") { Start-Process "http://localhost:3000" }
