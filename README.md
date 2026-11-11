# AIP Week 2 Allocator — Python 3.14 local app

This branch, **`python314-local-app`**, contains the reviewed Python 3.14 app
with the unified setup pages, Accessibility Flags and manual hotel-room creation.
The original working version remains on `release/windows-original-packaging`.

This is the complete source application. The backend is in
**`frontend/backend`**, alongside the Next.js frontend. Python and Node.js are
required; this branch does not include a bundled Windows executable.

## Download on Windows

1. Open [the Python 3.14 branch](https://github.com/khalodesta/AIP-Group-Allocator/tree/python314-local-app).
2. Select **Code → Download ZIP**, then **Extract All** in File Explorer.
3. Open the extracted project root in VS Code. It contains `frontend`, `docs`,
   `packaging`, `sample-data` and `COPILOT_RUN_WINDOWS.md`.
4. Copy [the Copilot startup prompt](COPILOT_RUN_WINDOWS.md) into Copilot Agent
   mode to configure and start this source version.

Do not use the older portable ZIP or its START.bat/start.ps1 launchers for this
branch. Python 3.12 is not required.

## Windows setup by hand

Use **standard 64-bit CPython 3.14** and Node.js **22.x or 24.x**. Local source
tests used Python 3.14.10 and Node.js 24.15.0; the previous Windows frontend
build used Node.js 22.14.0.

Open a VS Code PowerShell terminal inside the extracted `frontend` folder:

```powershell
py -3.14 --version
node --version
npm.cmd --version
py -3.14 -m venv .venv314
.\.venv314\Scripts\python.exe -m pip install --upgrade pip
.\.venv314\Scripts\python.exe -m pip install --require-hashes -r requirements-python314-windows.lock.txt
npm.cmd ci
```

Start the backend there and leave the terminal open:

```powershell
.\.venv314\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

In a **second** terminal, also inside `frontend`:

```powershell
$env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"
$env:NEXT_TELEMETRY_DISABLED = "1"
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

Open **http://127.0.0.1:3000**. API documentation is at
http://127.0.0.1:8000/docs. Keep both terminals open; Ctrl+C stops a server.
Virtual-environment activation or execution-policy changes are unnecessary.
Do not reuse an environment copied from a different computer.

Use **requirements-python314-windows.lock.txt** on Windows. It pins dependencies
with hashes and resolves to Python 3.14 Windows x64 wheels. The other freeze file,
`requirements-python314.lock.txt`, records the macOS test environment.

## Included functionality

- Upload, Faculty & Support, and Group Sizes pages styled to match Results.
- Public/Private university classification, normalized identities and aliases.
- Main Groups, Quiz Night, Team Building, exactly two BUS Teams, My Reflections,
  and Hotel Rooms, preserving support, faculty and prayer constraints.
- Gender and university-category balance, exact-university diversity,
  repeat/offering diversity and optional Primary/Secondary Business Chemistry.
- Session-only Accessibility Flags, visible in all six administrative Results
  views and excluded from APIs, optimization and exports.
- Hotel edit mode: Add Room, drag/keyboard MOVE, SWAP, valid single rooms,
  two-person capacity, Undo, Cancel, Save and hotel-only Reset to Generated.
- Private hotel PDF and editable Excel from the same saved manifest. General
  participant PDFs exclude hotel assignments.

The feature work preserved the optimizer source and weights. Python 3.14 uses
OR-Tools 9.15.6755, pandas 2.3.3 and Pydantic 2.14.3. See the historical
[compatibility comparison](PYTHON314-RESULTS.md) and
[feature review](docs/python314-feature-review.md) for details.

## Verification

- 144 backend tests and 30 frontend tests passed locally on Python 3.14.
- TypeScript, changed-source lint checks and production build passed.
- Actual browser generation, imports, prayer-aware editing, accessibility,
  manual rooms, saved exports and all six Results tabs passed.
- Business Chemistry-enabled and disabled browser workflows passed.
- 18 standardized unflagged Results screenshots matched the original frontend.
- Downloaded PDF/Excel matched the fictional saved manifest: 22 occupied rooms,
  37 unique occupants, no accessibility flags and no empty draft rooms.

Native Windows execution of this Python 3.14 source version has not been tested
here. The Copilot prompt performs a real 27-person optimization and validation
on your Windows computer; health responses alone are insufficient.

From `frontend/backend`, run backend tests with:

```powershell
..\.venv314\Scripts\python.exe -m pytest -q
```

From `frontend`, run frontend checks with:

```powershell
npm.cmd run typecheck
node --test tests/results-ui.test.cjs tests/proxy-timeout.test.cjs tests/manual-hotel-ui.test.cjs
```

## Session state

Participant data, allocations and accessibility selections remain in browser
application state. A full reload clears that state. Export saved assignments
before closing; flags intentionally remain absent from exports. University
directory settings retain their existing storage behavior.

The application has no sign-in system. Localhost is not an authentication
boundary; the UI is for authorized administrators on their own computer.

This branch does not trigger the portable Windows packaging workflow. No
Windows ZIP, PyInstaller build, deployment or release was requested.
