param([switch]$Quiet)
$ErrorActionPreference = "SilentlyContinue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$State = Join-Path $Root ".runtime"

function StopOwned([string]$PidFile, [string]$ExpectedPath) {
  if (-not (Test-Path $PidFile)) { return $false }
  $savedPid = [int](Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  $process = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
  if ($process) {
    $actual = $process.Path
    if ($actual -and ([IO.Path]::GetFullPath($actual) -eq [IO.Path]::GetFullPath($ExpectedPath))) {
      # A PyInstaller one-file backend has a child with the same executable.
      # Stop only matching direct children of this already-verified owner.
      foreach ($child in @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $savedPid")) {
        $ownedChild = Get-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
        if ($ownedChild -and $ownedChild.Path -and ([IO.Path]::GetFullPath($ownedChild.Path) -eq [IO.Path]::GetFullPath($ExpectedPath))) {
          Stop-Process -Id $child.ProcessId -Force
        }
      }
      Stop-Process -Id $savedPid -Force
    } else {
      if (-not $Quiet) { Write-Host "Skipped process $savedPid because it does not belong to this application." -ForegroundColor Yellow }
      return $false
    }
  }
  Remove-Item $PidFile -Force
  return $true
}

$frontend = StopOwned (Join-Path $State "frontend.pid") (Join-Path $Root "runtimes\node\node.exe")
$backend = StopOwned (Join-Path $State "backend.pid") (Join-Path $Root "app\backend\allocator-backend.exe")
if (-not $Quiet) {
  if ($frontend -or $backend) { Write-Host "AIP Week 2 Allocator has been stopped." -ForegroundColor Green }
  else { Write-Host "The application was not running." -ForegroundColor Yellow }
}
exit 0
