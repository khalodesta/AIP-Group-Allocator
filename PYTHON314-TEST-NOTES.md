# Separate Python 3.14 test copy

This folder is an experimental copy. The protected project in
`/Users/desta/Deloitte_AIP_Project` has not been migrated.

The application source, optimizer objectives, solver time limits, university
directory, activity constraints, UI and export logic are unchanged. Only these
direct Python dependencies changed:

| Dependency | Reference | Python 3.14 test |
|---|---|---|
| OR-Tools | 9.11.4210 | 9.15.6755 |
| pandas | 2.2.3 | 2.3.3 |
| Pydantic | 2.10.4 | 2.14.3 |

`frontend/.python-version` selects 3.14 in this copy. Transitive dependencies
also change; they are recorded in the lock files and experiment results.

## Windows source setup

Use a **new folder** and standard **64-bit Python 3.14**. Do not copy a virtual
environment from another computer or overwrite your working application.
The Windows dependency file resolves to prebuilt Python 3.14 x64 wheels;
native Windows runtime and portable packaging have not been tested here.

In a VS Code PowerShell terminal opened in this copy's `frontend` folder:

```powershell
py -3.14 -m venv .venv314
.\.venv314\Scripts\python.exe -m pip install --upgrade pip
.\.venv314\Scripts\python.exe -m pip install --require-hashes -r requirements-python314-windows.lock.txt
cd backend
..\.venv314\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Keep that terminal open. In a second terminal in `frontend` (with Node.js/npm
installed):

```powershell
npm ci
npm run dev
```

Open http://localhost:3000. This setup uses source execution and does not use
the old portable build's bundled Python executable or `start.bat`.

For backend tests from `frontend/backend`:

```powershell
..\.venv314\Scripts\python.exe -m pytest -q
```

The macOS freeze file is a record of the measured environment. Use the
Windows lock file above on Windows; it includes Windows-specific dependencies
and excludes the macOS-only uvloop wheel.

Full methods, raw allocation outputs and measured optimizer comparisons are
kept separately in `/tmp/aip-py314-study-20261111` on the reference computer.
