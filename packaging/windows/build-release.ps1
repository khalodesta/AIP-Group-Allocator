param(
  [string]$NodeVersion = "22.14.0",
  [string]$OutputDirectory = "release"
)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Frontend = Join-Path $Repo "frontend"
$Output = Join-Path $Repo $OutputDirectory
$PackageRoot = Join-Path $Output "AIP-Week2-Allocator"
$Zip = Join-Path $Output "AIP-Week2-Allocator-Windows.zip"

Write-Host "Building frontend..."
Push-Location $Frontend
$env:PORTABLE_WINDOWS_BUILD = "1"
npm ci
if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
npm run typecheck
if ($LASTEXITCODE -ne 0) { throw "Frontend type check failed" }
npm run build
if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
Pop-Location

Write-Host "Testing and packaging backend..."
python -m pip install --disable-pip-version-check -r (Join-Path $Frontend "requirements.txt") "pyinstaller==6.16.0"
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed" }
Push-Location $Repo
python -m pytest -c frontend/backend/pytest.ini frontend/backend/tests packaging/windows/tests -q
if ($LASTEXITCODE -ne 0) { throw "Backend tests failed" }
python -m PyInstaller --noconfirm --clean --distpath (Join-Path $Output "pyinstaller") --workpath (Join-Path $Output "pyinstaller-work") packaging/windows/backend.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller backend packaging failed" }
python -m PyInstaller --noconfirm --clean --distpath (Join-Path $Output "pyinstaller") --workpath (Join-Path $Output "pyinstaller-work") packaging/windows/launcher.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller launcher packaging failed" }
Pop-Location

Remove-Item $PackageRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $Zip -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path `
  (Join-Path $PackageRoot "app\frontend"), `
  (Join-Path $PackageRoot "app\backend"), `
  (Join-Path $PackageRoot "app\launcher"), `
  (Join-Path $PackageRoot "runtimes\node"), `
  (Join-Path $PackageRoot "logs") | Out-Null

Copy-Item (Join-Path $Frontend ".next\standalone\*") (Join-Path $PackageRoot "app\frontend") -Recurse -Force
New-Item -ItemType Directory -Force -Path (Join-Path $PackageRoot "app\frontend\.next") | Out-Null
Copy-Item (Join-Path $Frontend ".next\static") (Join-Path $PackageRoot "app\frontend\.next\static") -Recurse -Force
if (Test-Path (Join-Path $Frontend "public")) { Copy-Item (Join-Path $Frontend "public") (Join-Path $PackageRoot "app\frontend\public") -Recurse -Force }
Copy-Item (Join-Path $Output "pyinstaller\allocator-backend.exe") (Join-Path $PackageRoot "app\backend\allocator-backend.exe") -Force
Copy-Item (Join-Path $Output "pyinstaller\allocator-launcher.exe") (Join-Path $PackageRoot "app\launcher\allocator-launcher.exe") -Force
Copy-Item (Join-Path $PSScriptRoot "START.bat"), (Join-Path $PSScriptRoot "STOP.bat"), (Join-Path $PSScriptRoot "README.txt") $PackageRoot -Force

Write-Host "Downloading official portable Node.js runtime..."
$NodeArchive = Join-Path $Output "node-v$NodeVersion-win-x64.zip"
$NodeUrl = "https://nodejs.org/dist/v$NodeVersion/node-v$NodeVersion-win-x64.zip"
$Checksums = (Invoke-WebRequest -UseBasicParsing "https://nodejs.org/dist/v$NodeVersion/SHASUMS256.txt").Content
$ExpectedLine = ($Checksums -split "`n" | Where-Object { $_ -match " node-v$([regex]::Escape($NodeVersion))-win-x64.zip$" } | Select-Object -First 1)
if (-not $ExpectedLine) { throw "Official Node.js checksum was not found." }
Invoke-WebRequest -UseBasicParsing $NodeUrl -OutFile $NodeArchive
$Expected = ($ExpectedLine -split "\s+")[0].ToLowerInvariant()
$Actual = (Get-FileHash $NodeArchive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Expected -ne $Actual) { throw "Portable Node.js checksum verification failed." }
$NodeExtract = Join-Path $Output "node-extracted"
Remove-Item $NodeExtract -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive $NodeArchive $NodeExtract -Force
Copy-Item (Join-Path $NodeExtract "node-v$NodeVersion-win-x64\node.exe") (Join-Path $PackageRoot "runtimes\node\node.exe") -Force
Copy-Item (Join-Path $NodeExtract "node-v$NodeVersion-win-x64\LICENSE") (Join-Path $PackageRoot "runtimes\node\LICENSE.txt") -Force
Set-Content (Join-Path $PackageRoot "runtimes\node\VERSION.txt") "Official Node.js v$NodeVersion win-x64"

Set-Content (Join-Path $PackageRoot "logs\README.txt") "Startup and runtime logs are written here. Do not share logs without reviewing them."
$Commit = (git -C $Repo rev-parse HEAD).Trim()
$SourceFiles = @("frontend/app", "frontend/components", "frontend/lib", "frontend/types", "frontend/backend/app", "frontend/backend/data")
$SourceHashes = @{}
foreach ($SourcePath in $SourceFiles) {
  Get-ChildItem (Join-Path $Repo $SourcePath) -File -Recurse | Where-Object { $_.FullName -notmatch '__pycache__|\.pyc$' } | ForEach-Object {
    $Relative = $_.FullName.Substring($Repo.Length + 1).Replace('\', '/')
    $SourceHashes[$Relative] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
  }
}
@{commit=$Commit; branch=$env:GITHUB_REF_NAME; node=$NodeVersion; sources=$SourceHashes} | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $PackageRoot "BUILD-INFO.json") -Encoding UTF8
# .NET ZIP includes .next dot-directories; Compress-Archive can omit hidden files.
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($PackageRoot, $Zip, [IO.Compression.CompressionLevel]::Optimal, $true)
$ZipHash = (Get-FileHash $Zip -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content (Join-Path $Output "SHA256SUMS.txt") "$ZipHash  AIP-Week2-Allocator-Windows.zip" -Encoding UTF8
@{commit=$Commit; branch=$env:GITHUB_REF_NAME; zip="AIP-Week2-Allocator-Windows.zip"; bytes=(Get-Item $Zip).Length; sha256=$ZipHash} | ConvertTo-Json | Set-Content (Join-Path $Output "release-manifest.json") -Encoding UTF8
Write-Host "Created $Zip" -ForegroundColor Green
