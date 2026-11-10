# Portable Windows release

The portable release is built on Windows because the packaged OR-Tools backend and
other native Python dependencies must target Windows x64. A macOS build is not a
valid substitute.

## Recommended build

1. Push the intended `deployment/portable-windows` or `release/windows-final-*` branch to the existing repository. Push triggers one Windows build; do not also dispatch a redundant run. Review staged files for secrets and employee data before pushing, particularly when the repository is public.
2. Open **Actions → Build portable Windows ZIP → Run workflow**.
3. Download the `AIP-Week2-Allocator-Windows` artifact after the workflow succeeds. Feature branches can also be selected for a manual workflow run.
4. Extract `AIP-Week2-Allocator-Windows.zip` and test it on an IT-approved clean Windows x64 device.

The artifact contains an official checksum-verified Node.js Windows x64 runtime and
a PyInstaller-packaged Python backend. The recipient does not install Node.js,
Python, npm packages, or pip packages.

The workflow extracts the actual ZIP into a path with spaces and smoke-tests START/STOP, restart, duplicate start, stale process tracking, unrelated occupied ports 3000/8000, loopback-only listeners, and operation without global Node/Python on PATH. It also tests fictional Excel participant/support uploads, all six allocations, two BUS Support Leads, male-only prayer selection and continuation, complete hotel coverage, binary university categories, Capital-Helwan data, and PDF/Excel downloads through the standalone frontend API proxy.

`SHA256SUMS.txt` and `release-manifest.json` accompany the ZIP in the workflow artifact. `BUILD-INFO.json` inside the application records the build commit and source hashes. GitHub wraps these files in an artifact ZIP: extract that wrapper, then extract `AIP-Week2-Allocator-Windows.zip`, then open the application folder.

## Local Windows build

On a Windows x64 build machine with Node.js 22, Python 3.12, and internet access:

```powershell
./packaging/windows/build-release.ps1
```

The result is `release/AIP-Week2-Allocator-Windows.zip`.

## Security and operation

- Both servers bind to `127.0.0.1` only.
- The frontend proxies `/api` to the local backend only in the portable build.
- START/STOP call the bundled `allocator-launcher.exe` directly. No PowerShell
  script is shipped or executed at runtime, so the application's PowerShell
  Run-once confirmation is eliminated without changing execution policy.
- Startup is serialized with a per-folder file lock. Process ownership requires
  the exact bundled executable and creation timestamp, not just a PID or a
  generic HTTP 200 response. Duplicate start reopens the existing website.
- A supervisor joins a Windows job before spawning services. Descendants inherit
  the job; supervisor exit closes it and stops that application tree only.
  Normal STOP first requests graceful backend shutdown, allowing its one-file
  bootloader to clean its temporary directory. Stale tracking is cleared without
  terminating any process. No taskkill or broad Node/Python termination is used.
- Startup verifies backend identity, website readiness and the frontend API proxy
  using bounded HTTP/TCP checks. Required ports stay fixed to preserve the
  compiled proxy. Conflicts explicitly identify the occupied port; no unrelated
  listener is stopped and no alternative port is chosen silently.
- No firewall, registry, service, or administrator-level change is made.
- Application data is processed in memory and is not sent to an external API.
- Startup logs intentionally disable API access logging to avoid recording uploaded
  file names or participant-related request details.
- Backend data packaging is restricted to the university directory/data assets;
  backend tests and benchmark outputs are not bundled as application data.

The release task preserves the exact latest application implementation, including
the rebalanced CP-SAT objective. Changes are confined to Windows packaging,
launch supervision, build provenance, release tests and documentation. The
backend entry point adds a local stop-file watcher solely for graceful shutdown;
it does not change FastAPI endpoints or allocation behavior.

## Required acceptance testing

Before distribution, test on a clean company-equivalent Windows x64 environment:

- paths under Downloads, Desktop, and a folder containing spaces;
- no global Python or Node.js available to the user;
- no administrator privileges and no internet connection at runtime;
- all six allocations, both Excel upload modes, editing, My Reflections swaps,
  Excel/PDF export, stop/restart, duplicate start, and occupied ports 3000/8000.

Unsigned internal executables may be blocked by SmartScreen, Defender, WDAC,
AppLocker, or corporate endpoint controls. Do not bypass those controls. Submit the
ZIP, SHA-256 hash, PyInstaller version, Python version, Node.js version, dependency
lock files, and this build workflow to IT for approval or code signing.
