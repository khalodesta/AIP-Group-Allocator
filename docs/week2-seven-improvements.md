# Week 2 improvements: implementation and verification

Implemented on `feature/week2-seven-improvements`, branched from the fetched
`origin/deployment/portable-windows` application. The starting working tree was
clean. The existing six-activity UI, stateless API, internal IDs, browser editing
history, and portable Windows architecture remain in use.

## University classification and diversity

The 133-entry offline directory keeps its stable IDs, original aliases, legal
classifications, and source metadata. Each entry now also has one of five
`diversity_category` values: `public`, `private`, `national`, `international`, or
`other`. Technological universities retain their corresponding public/private
ownership group; Ahleya institutions remain distinct from private universities.
AUC retains its international-agreement legal classification while its diversity
category is Private. Official references include the
[Supreme Council of Universities private list](https://scu.eg/accredited-private-universities/),
[SCU Ahleya list](https://scu.eg/الجامعات-المصرية-الأهلية/), and
[AUC's institutional description](https://www1.aucegypt.edu/catalog06/catalog06.pdf).

Unknown universities require explicit classification before group generation.
The review lists each unique institution once, supports corrections and aliases,
and stores reusable mappings in browser local storage. Administrators can export
and import the directory as JSON. Configuration snapshots also carry mappings;
explicit confirmed categories in editable Excel survive reimport. Conflicting
custom aliases and attempts to merge different known institutions are rejected.
Nothing requires an internet connection at runtime.

The new soft cost for Main Groups, Quiz Night, Team Building, and BUS Teams uses
actual cohort proportions: for each category/group, minimize
`abs(group_category_count * cohort_size - cohort_category_count * group_size)`.
Category equality is never a hard constraint. My Reflections and hotel allocation
exclude this objective. Internal quality metrics include category distributions
and proportional deviation, including BUS new hires while excluding staff.

## Optimization weights and constraints

The joint group solver retains its existing top-level cost
`10 * exact_university_pairs + offering_profile_costs`, including the existing
Business Chemistry primary/secondary coefficients of 3/1. Category deviation joins
gender deviation at the existing gender-balance tier. The gender-to-repeat weight
relationship is unchanged; the top-tier bound expands to cover the added category
cost. Thus the existing hierarchy remains profile/exact-university, then
gender/category balance, then repeated teammate encounters.

BUS retains existing university/gender/offering coefficients 5/4/3 and Chemistry
3/1, adds category coefficient 4, and uses repeat encounters as a lower-priority
tie-break. It always has exactly two teams with balanced new-hire counts. Support
Leads and Analyst Support are distributed independently with role counts differing
by at most one; at least one lead per bus is mandatory. Fewer than two leads or
missing staff name/gender/category yields a clear validation error. Manual edits
cannot remove a bus's only lead. Faculty never enter BUS assignments.

## Prayer-aware My Reflections

An optional-interval CP-SAT schedule jointly chooses faculty and actual appointment
times. Exactly three faculty members receive balanced workloads; offering matching
and existing profile preferences remain. Gender and university category do not
enter scheduling or its quality calculations. Explicitly selected prayer-aware
participants receive available pre-break priority, and overflow continues after
the editable resume time. Faculty prayer unavailability, availability bounds, and
additional unavailable intervals are explicit inputs.

Appointments retain the configured duration and unique participant assignment.
Protected breaks and faculty appointment overlap are hard constraints. An optional
fixed final end is never silently extended. When it cannot fit, the scheduler
computes an unrestricted completion and the UI offers an explicit extension
button. It says "earliest" only when the solver proves that minimum; otherwise it
reports a feasible completion. The application uses same-day scheduling.

Manual swaps exchange the two existing time/faculty slots, recalculate offering
matches, and validate actual intervals without rerunning optimization or adding
unrelated diversity warnings. Existing Save, Cancel, Undo, Reset, and export paths
use the edited snapshot. Limited regeneration preserves unrelated activities.

## Complete hotel manifest

Automatic rooming maximizes same-gender new-hire pairings across different Main
Groups before applying soft roommate preferences. Each unmatched hire can use one
unused same-gender Analyst Support member. This handles odd counts independently
for each gender, including even-sized cohorts. Remaining hires receive single
rooms with actionable warnings; remaining analysts, every Support Lead, and every
faculty member receive single rooms. Staff IDs are globally distinct and each
person appears exactly once in the manifest.

The seven standard summary values count total rooms, new-hire shared rooms,
hire/analyst shared rooms, single hires, single leads, single analysts, and single
faculty. Counts derive from actual unique rooms and are recalculated after edits.
Existing explicitly enabled accommodation-policy overrides remain available; an
additional manual-arrangements count keeps totals exact for such rooms. Faculty
and lead single occupancy and identity integrity cannot be overridden.

The private hotel PDF contains room numbers, occupants, roles, totals, and the
occupancy breakdown. Editable Excel contains participant attributes, support roles
and gender, faculty, the full manifest, and a summary. Support Excel import accepts
legacy name-only files while leaving missing fields for administrator completion.
General participant PDFs continue to exclude hotels and do not gain gender or
university-category labels. Export routes validate saved allocation integrity.

## Naming and results UI

`eg-capital-university` now displays as **Capital-Helwan University**. Capital,
Helwan, Capital-Helwan, and the specified Arabic aliases resolve to that stable ID;
Helwan National University retains its own ID and national category.

All user-facing activity labels and worksheet/PDF titles use **My Reflections**;
the internal `reflection` activity ID remains unchanged. A reusable identity
component renders subdued blue/rose recorded-gender name treatments and a separate
five-color university-category marker across all results tabs, with an accessible
legend, keyboard focus, tooltips, and labels. Support uses recorded gender and role;
faculty receives no inferred gender or university classification.

## Files changed

- UI: `frontend/app/page.tsx`, `frontend/app/globals.css`, `frontend/types/index.ts`.
- Shared components: `UniversityAutocomplete.tsx`, `ParticipantIdentity.tsx`,
  `UniversityReview.tsx`, `universityClassification.ts`, `hotelSummary.ts` in
  `frontend/components/`.
- Backend: `frontend/backend/app/models.py`, `main.py`, and services
  `normalization.py`, `optimizer.py`, `scoring.py`, `excel.py`, `pdf_export.py`.
- Directory: `frontend/backend/data/generate_universities.py` and
  `university_directory.json`.
- Automated checks: the updated `test_core.py`, new `test_api_improvements.py`,
  `test_exports_improvements.py`, `test_optimizer_improvements.py`,
  `test_university_improvements.py`, `test_portable_directory.py`, and
  `frontend/tests/results-ui.test.cjs`.
- Release validation: `.github/workflows/portable-windows.yml`,
  `packaging/windows/smoke-allocations.ps1`, and release/implementation documentation.

## Verification and release status

The release verification commands are:

```sh
cd frontend/backend
../../.venv/bin/pytest -q
cd ..
npm run typecheck
node --test tests/results-ui.test.cjs
PORTABLE_WINDOWS_BUILD=1 npm run build
```

Final local verification passed: **90 backend tests**, **9 React component tests**,
TypeScript checking, Python critical-error lint, Git whitespace checks, and the
production build with `PORTABLE_WINDOWS_BUILD=1`. No final local checks failed.
Live Chrome acceptance passed with 30 fictional hires, five support members, and
three faculty: classification and reusable alias persistence, support import and
navigation, fixed-end failure and explicit extension, all six Results tabs, 30
prayer-aware appointments, the 38-person hotel manifest, appointment swapping,
Undo, and Save. Route tests also verify same/cross-faculty swaps and PDF/Excel
consistency and privacy.

The PyInstaller spec, portable Node runtime, START/STOP launchers, and standalone
Next.js output are preserved. A frozen-runtime fallback resolves the directory
from the existing bundled `backend/data` layout. Windows CI now checks that
directory, all six allocations, prayer continuation, hotel coverage, and PDF/Excel
downloads through the packaged frontend proxy. A local macOS production build
does not establish Windows compatibility; the Windows workflow must pass before
claiming the ZIP is ready.

The [Windows workflow](https://github.com/khalodesta/AIP-Group-Allocator/actions/runs/42626750855)
completed successfully for application commit `c450cf1` on 2026-11-09. Its Windows
Python 3.12 run passed all **90 backend tests**, all **9 component tests**, and the
bundled six-allocation/export smoke test. Four dependency deprecation warnings
(Starlette, ReportLab and protobuf) did not affect these checks. The updated
[Windows artifact](https://github.com/khalodesta/AIP-Group-Allocator/actions/runs/42626750855/artifacts/13679246730)
contains `AIP-Week2-Allocator-Windows.zip`.

Confirmed mappings depend on the current browser profile unless exported.
Schedules remain within one calendar day. The CI smoke test does not replace a
clean company-device check of endpoint controls, offline startup, and distribution
paths before delivery to administrators.
