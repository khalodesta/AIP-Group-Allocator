# Original packaging restoration review

The latest application baseline is commit `f66bce3`, including the earlier local
UI, university, staffing, scheduling, hotel and optimization-priority improvements.
`4d17b4f` supplies packaging files only. No frontend component, stylesheet, model,
optimizer, normalization rule, export implementation or dependency version was
reverted. A pre-edit SHA-256 snapshot covers all 26 application/dependency files;
all remain identical. The one shared configuration edit is the API proxy deadline.

| File | Original 4d17b4f | Previous release | Restored release |
|---|---|---|---|
| START.bat / STOP.bat | PowerShell scripts | Executable supervisor | Exact original files |
| start.ps1 | Backend then frontend, health checks and PID files | Removed | Exact original file |
| stop.ps1 | Verify executable path, stop recorded PIDs | Removed | Original logic plus matching direct-child cleanup for a one-file backend |
| backend_launcher.py | Simple loopback Uvicorn entry point | Background stop watcher | Exact original file |
| backend.spec | Current full backend tree and collected dependencies | University-data-only assets | Exact original specification, pointed at current source |
| build-release.ps1 | Standalone frontend, one backend executable, portable Node, scripts, Compress-Archive | Additional supervisor build and different ZIP API | Original build/startup/archive approach; retained current tests, source hashes, checksum manifest and Node license |
| next.config.ts | Standalone output and local API rewrite | Same | Same rewrite and output; 180-second proxy deadline |
| portable-windows.yml | Windows 2022 build and health smoke | More tests/diagnostics | Same Windows foundation, original launch, current test suite and real 27-person proxy smoke |
| README.txt / release docs | Original startup instructions | Executable-supervisor instructions | Batch/PowerShell instructions, optional Run-once confirmation, current logs/data guidance |

The separate launcher executable/specification, Win32 supervisor helper and its
unit tests were removed. The restored scripts do not change PowerShell execution
policy or bypass Windows or company protections. A PowerShell Run-once prompt is
acceptable. Source and dependencies always come from the current release branch.

## HTTP 500 evidence

The first fictional 27-person request used the UI's 20-second core solve budget
and returned all six activities locally in roughly 25 seconds. Increasing only
the supported request budget to 30 seconds reproduced the failure:

- Existing Next proxy: HTTP 500 after 30.013 seconds; the frontend trace reports
  `Failed to proxy ... Error: socket hang up`, `code: ECONNRESET`.
- Identical direct FastAPI request: HTTP 200 after 34.869 seconds, FEASIBLE core
  solution, OPTIMAL BUS/reflection/hotel stages, all six activities returned.
- No Python exception, invalid CP-SAT model, missing import/resource or schema
  error occurred in this reproduction. FastAPI continued after the proxy aborted.

Next's installed `proxy-request.js` selects a 30,000ms timeout when configuration
omits one. The application's core budget supports up to 120 seconds, with further
activity solves after it. A fixed 180,000ms transport budget permits those existing
solves to finish and still bounds a stalled proxy. This configuration fix does not
change any solver budget, weights or allocation constraints. Restoring an older
launcher alone cannot correct the deadline.

The affected laptop's private logs/request were requested separately and were not
available for this reproduction. The identified defect is independently reproduced
with fictional data and exercised in a real Windows package regression test.

## Local checks before upload

- Full current backend suite: **128 passed in 258.14 seconds**.
- TypeScript and an isolated current Next.js production build: passed.
- Existing UI component tests plus proxy regression: **21 passed**.
- PowerShell syntax and critical Python lint/whitespace checks: passed.
- Live standalone frontend -> FastAPI with the real 27-person fixture:
  20-second core/Chemistry on: HTTP 200 in 25.34s;
  30-second core/Chemistry on: HTTP 200 in 34.83s;
  30-second core/Chemistry off: HTTP 200 in 31.29s.
  All six activities validated in each response.
- Source preservation and upload review: passed; added cohort/staff are fictional.

The new Windows workflow extracts the actual ZIP to a path with spaces, invokes
its restored batch/PowerShell entry points and runs these same real requests
through localhost:3000. It checks all assignments, appointments, BUS leads and
hotel compatibility/counts, existing Excel/PDF operations and stop/restart. The
application artifact is gated on these checks, and failure logs retain backend
tracebacks. Windows results and artifact identity are reported after the run;
local health or source-only tests are not treated as package acceptance.
