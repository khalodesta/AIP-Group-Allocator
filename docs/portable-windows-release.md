# Portable Windows release using the original launcher

The application is built from the latest release source. Commit `4d17b4f` is the
packaging reference only; its older frontend, backend and optimizer are not used.

The original `START.bat`, `STOP.bat`, `start.ps1`, backend entry point and backend
PyInstaller specification are restored. `stop.ps1` retains the original PID-file
and executable-path checks and also stops a matching direct child of an owned
one-file backend so it cannot leave the Python service behind. No executable
supervisor or extra launcher executable is built or shipped. The original
standalone Next.js build, official portable Windows Node runtime, one-file backend,
PowerShell startup order and fixed loopback ports 3000/8000 remain.

The existing PowerShell Run-once confirmation is acceptable. Neither batch file
changes an execution policy, disables protection, elevates, or adds an exclusion.

## Allocation HTTP 500 investigation

A valid fictional 27-person request with a 30-second CP-SAT budget reproduced the
failure using the installed Next.js proxy: HTTP 500 at 30.013 seconds with
`ECONNRESET: socket hang up`. The identical direct FastAPI request returned HTTP
200 at 34.869 seconds, a FEASIBLE solver result and all six activities. Its solver
stages were feasible/optimal and no Python exception was raised. A 20-second core
budget completed locally in about 25 seconds; slower Windows processing and the
additional BUS, reflection and hotel stages can cross the proxy deadline.

The existing Next.js rewrite used its default 30-second transport timeout. The
supported core solver budget alone can reach 120 seconds. The packaging/shared
Next configuration now allows 180 seconds for the proxy, including subsequent
activity solves and serialization. This does not change solver weights, solver
limits, university classifications, scheduling or hotel behavior. Returning to
the original launcher alone would retain that timeout and would not fix it.

The affected laptop's private request and logs were requested but were not
available for this reproduction. The release tests reproduce the timeout boundary
with fictional data and verify the correction in the actual frozen application.

## Verification and artifact

The workflow builds on Windows, tests the current Python backend and frontend,
extracts the actual ZIP to a path with spaces and starts it using its original
batch/PowerShell scripts. Global Node and Python are absent from the runtime PATH.
The packaged frontend submits real 27-person requests with Chemistry enabled and
disabled, each taking over 30 seconds. Tests require HTTP 200, a non-fallback CP-SAT
result, all six activities, unique/complete assignments, valid appointments, BUS
Support Leads, compatible hotel rooms and matching room counts. Existing fictional
Excel uploads, exports, duplicate start and stop/restart tests also run. Failures
preserve and display backend/frontend tracebacks; health alone cannot pass the run.

The original build script behavior is retained, with the latest tests, Node license,
source hashes and checksum manifest kept as release verification improvements.
No dependency versions were reverted. The workflow uploads
`AIP-Week2-Allocator-Windows-Original-Packaging`, containing the Windows ZIP,
`SHA256SUMS.txt` and `release-manifest.json`. `BUILD-INFO.json` inside the application
records its exact commit and source hashes. Only a successful functional run can
upload the application artifact. Push the intended release branch once; do not
also dispatch a duplicate build.

Extract GitHub's outer artifact ZIP, then extract the application ZIP, open its
folder and double-click START.bat. Press R if required. Save exported results,
then use STOP.bat and press R if required. Both services bind to loopback only.

A Deloitte-managed laptop, its default browser, offline execution, standard-user
policy and endpoint controls require a separate manual acceptance test. Respect
IT restrictions; this package does not bypass them.
