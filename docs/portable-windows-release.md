# Portable Windows release

The portable release is built on Windows because the packaged OR-Tools backend and
other native Python dependencies must target Windows x64. A macOS build is not a
valid substitute.

## Recommended build

1. Push the `deployment/portable-windows` branch to an approved private GitHub repository.
2. Open **Actions → Build portable Windows ZIP → Run workflow**.
3. Download the `AIP-Week2-Allocator-Windows` artifact.
4. Extract `AIP-Week2-Allocator-Windows.zip` and test it on an IT-approved clean Windows x64 device.

The artifact contains an official checksum-verified Node.js Windows x64 runtime and
a PyInstaller-packaged Python backend. The recipient does not install Node.js,
Python, npm packages, or pip packages.

## Local Windows build

On a Windows x64 build machine with Node.js 22, Python 3.12, and internet access:

```powershell
./packaging/windows/build-release.ps1
```

The result is `release/AIP-Week2-Allocator-Windows.zip`.

## Security and operation

- Both servers bind to `127.0.0.1` only.
- The frontend proxies `/api` to the local backend only in the portable build.
- PID files identify the two packaged processes; `STOP.bat` verifies executable
  paths before stopping them.
- No firewall, registry, service, or administrator-level change is made.
- Application data is processed in memory and is not sent to an external API.
- Startup logs intentionally disable API access logging to avoid recording uploaded
  file names or participant-related request details.

## Required acceptance testing

Before distribution, test on a clean company-equivalent Windows x64 environment:

- paths under Downloads, Desktop, and a folder containing spaces;
- no global Python or Node.js available to the user;
- no administrator privileges and no internet connection at runtime;
- all six allocations, both Excel upload modes, editing, MyReflection swaps,
  Excel/PDF export, stop/restart, duplicate start, and occupied ports 3000/8000.

Unsigned internal executables may be blocked by SmartScreen, Defender, WDAC,
AppLocker, or corporate endpoint controls. Do not bypass those controls. Submit the
ZIP, SHA-256 hash, PyInstaller version, Python version, Node.js version, dependency
lock files, and this build workflow to IT for approval or code signing.
