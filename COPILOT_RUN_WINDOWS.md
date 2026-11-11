# Copilot prompt — run the Python 3.14 app on Windows

Extract the GitHub source ZIP, open its root in VS Code, use Copilot Agent mode,
and paste this prompt. It applies to branch **python314-local-app**.

```text
Run this existing AIP Week 2 Allocator locally on this Windows computer.
This is the PYTHON 3.14 source app from branch python314-local-app.

Keep application code and optimizer behavior unchanged. Do not switch to Python
3.12, replace OR-Tools, change weights, build a Windows ZIP, run PyInstaller,
commit, push, deploy, or trigger GitHub Actions. Do not use the old portable
START.bat/start.ps1 launchers.

1. Find the project root, allowing for an extra extracted ZIP directory. Verify:
   frontend/package.json
   frontend/backend/app/main.py
   frontend/backend/app/services/optimizer.py
   frontend/backend/data/university_directory.json
   frontend/requirements-python314-windows.lock.txt
   packaging/windows/fixtures/allocation27.json
   The backend is inside frontend/backend. Do not invent a missing backend.

2. Check standard 64-bit CPython 3.14, Node.js and npm. Prefer `py -3.14` and
   Node.js 22.x or 24.x. If the Python launcher is unavailable, locate the
   installed Python 3.14 executable and verify its version and architecture.
   Do not use another Python version or a copied virtual environment. If a
   prerequisite is missing or company policy blocks it, report the exact issue;
   do not change security settings or bypass company restrictions.

3. From frontend, create and install the local environment:
   py -3.14 -m venv .venv314
   .\.venv314\Scripts\python.exe -m pip install --upgrade pip
   .\.venv314\Scripts\python.exe -m pip install --require-hashes -r requirements-python314-windows.lock.txt
   npm.cmd ci
   If .venv314 exists, verify its Python before reuse. Use npm.cmd on PowerShell.
   Activation and execution-policy changes are unnecessary. Use the Windows
   lock file, not the macOS freeze.

4. Using .venv314's Python, verify imports of FastAPI, pandas, Pydantic,
   openpyxl, reportlab and `from ortools.sat.python import cp_model`. Print
   Python and OR-Tools versions. Diagnose actual import errors; do not silently
   select a different backend.

5. Start the backend in a dedicated persistent terminal from frontend:
   .\.venv314\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

6. In a second persistent terminal, also from frontend:
   $env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"
   $env:NEXT_TELEMETRY_DISABLED = "1"
   npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
   Keep both servers running. If a port is occupied, identify the listener and
   reuse it only if it is this exact app. Otherwise choose free ports and update
   NEXT_PUBLIC_API_URL consistently. Do not kill unrelated processes.

7. Verify the frontend loads and the API responds, then submit a real fictional
   allocation request. Health endpoints alone do not prove generation works.
   POST packaging/windows/fixtures/allocation27.json to /api/optimize on the
   running backend, with an HTTP timeout of 180 seconds for the configured main
   solve plus secondary activity solves. Require HTTP 200 and all six activity
   IDs: main, quiz, team, bus, reflection, hotel. POST the same input plus the
   returned allocation to /api/allocations/validate and require valid=true.
   Confirm every new hire, support member and faculty member appears exactly
   once in the hotel manifest and each bus has a Support Lead.
   Report the actual solver status. FEASIBLE_FALLBACK is a heuristic fallback,
   not an optimized result. Do not disguise it or change constraints, solver
   limits or weights just to pass this check. For a 500/422, inspect the actual
   backend traceback and response body and report the cause.

8. If browser tooling is available, confirm the setup pages, Accessibility Flags
   control, six Results tabs and Hotel Rooms edit-mode Add Room control. Use
   fictional data only. Never send flags to optimizer or export endpoints.

9. Give me the frontend URL (normally http://127.0.0.1:3000), backend URL,
   Python/OR-Tools versions, real optimization/validation results and remaining
   errors. Leave both processes running so I can use the app.
```
