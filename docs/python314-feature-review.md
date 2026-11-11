# Python 3.14 local feature review

This work is in `/tmp/aip-py314-study-20261111/candidate`. The reference project at
`/Users/desta/Deloitte_AIP_Project` is unchanged. Nothing was committed, pushed,
deployed, published, packaged for Windows, or sent to GitHub Actions. Windows
launchers and packaging configuration were preserved.

The local review app is already running at **http://127.0.0.1:3114**, with its
isolated Python 3.14 backend on **8114**. It uses a production Next.js build.

## 1. Upload Data

The heading now uses the Results typography, muted supporting text and spacing.
Upload cards use the same restrained borders, corner radii, icon sizes and visual
density as Results, with a quiet loaded-workbook state. Participant controls,
inputs, autocomplete, deletion, table spacing and Continue use the matching
button and field styling. Large tables keep their horizontal scrolling inside
the card. Import behavior and validation are unchanged.

## 2. Faculty & Support

Faculty, support and prayer settings use consistent card headings, input heights,
checkboxes, focus states and spacing. Support counts use compact numeric fields.
All three faculty entries, offerings, staff roles, genders, Excel import, prayer
selection and scheduling controls remain available with their original behavior.

## 3. Group Sizes and progress

The size cards are shorter, with compact plus/minus controls, clear numeric
values and subtle balanced-group information. Their calculations and bounds are
unchanged. The four existing steps retain their navigation behavior; setup-step
labels use consistent proportions and do not wrap on desktop.

## 4. Results preservation

All pre-existing Results CSS is preserved byte-for-byte. Eighteen standardized
screenshots of the unflagged Results views (six activities at 1440, 834 and 390px)
match the pre-change frontend pixel-for-pixel with identical allocation data.
Scroll position, pointer position, reduced motion and paint timing were held
constant for that comparison. Initial captures exposed transient hover/scroll
differences; the stabilized comparison isolates actual styling.

Results changes are limited to the requested indicator and hotel edit controls,
empty room destinations and their occupied cards. Existing room styling,
university dots, gender colors, Results tabs and non-hotel edit panels remain.

## 5–7. Accessibility Flags

The **Accessibility Flags** button appears beside participant-management controls
once participant rows exist. The native modal supports name/university search,
multiple selections, deselection, selected count, Cancel and Save Flags. Save
uses a simple toast; Cancel discards the modal's unsaved changes. Keyboard focus
is contained by the native dialog, and Escape cancels it.

Saved IDs live only in React application state. Nothing is selected by default.
Stable participant IDs preserve flags during renaming, step navigation,
generation, activity navigation and allocation editing. Deleting or trimming
rows removes their flags; Clear All removes all flags. Importing any replacement
cohort clears flags, including a file with matching names or IDs. No ambiguous
identity matching is attempted.

A small muted Lucide accessibility icon appears beside a flagged new hire's
university marker in all six Results views. Its tooltip and screen-reader label
are “Disability indicator — administrative awareness only.” Staff and faculty
never receive the indicator.

Flags are not participant attributes, configuration or allocation metadata.
They never enter optimizer, validation, editing or export payloads, logs,
telemetry, Excel or any PDF. The browser compared the actual flagged optimizer
request against the pre-feature unflagged request and found them identical.
Saving flags performs no API request. No Python optimization code changed.

## 8–10. Add Room and Move

**+ Add Room** appears only in **Hotel Rooms → Edit Teams**. Each click appends
an empty room to the existing edit draft, using a UUID and the next unused
display number. A session high-water number prevents accidental reuse after
Undo, removal or reordering. Existing rooms are not renumbered; gaps are valid.

Empty rooms use the existing premium neutral room card and a subtle “Drag a
participant here” destination. Dropping on a room card performs a MOVE; dropping
on an existing person performs the existing SWAP. A keyboard alternative uses
the first existing participant selector, a destination-room selector and
**Move Participant**. Available single-occupancy destinations are supported.

There is one allocation state model: generated snapshot, saved allocation and
edit draft. Manual rooms are ordinary groups with stable `hotel-manual-…` IDs;
there is no second room list or backend storage. Empty manual rooms survive
intermediate editing requests. Original rooms vacated by a move are removed;
empty manual rooms remain usable until removed or saved.

## 11–13. State, singles and totals

- **Save:** validates and saves the current occupied manifest without running
  any optimizer. Unused empty rooms are discarded with a short notification.
- **Cancel:** restores the last saved allocation and discards all new draft
  rooms, moves, swaps and empty-room removals.
- **Undo:** restores the prior allocation and override records for Add Room,
  Move, Swap, Remove Room and Reset.
- **Reset to Generated in Hotel Rooms:** restores only the original hotel
  allocation. Unrelated manually edited activities and their overrides remain.
- **Remove Room:** available only for an empty manually created room. Occupied
  rooms have no deletion action.

Both people from an initially shared room may remain in separate single rooms,
without a reason field, special eligibility, roommate replacement or automatic
regeneration. Intentional manual singles do not produce optimization warnings.

Every saved guest must occur exactly once. Rooms have a hard two-person maximum,
including when policy override confirmations are enabled. This follows the new
requirement and supersedes the older manual three-person capacity exception.
Faculty and Support Leads stay single; Analyst Support may share only with one
eligible new hire. Existing same-gender policy approvals and same-Main-Group
roommate warning/override behavior remain in place.

Totals and occupancy categories are derived from occupied room groups, not
original optimizer counts or the highest display number. Empty draft rooms do
not count as bookings. Splitting one shared room produces two singles and
increases the room total by one. Category totals sum to the occupied room total.

Saved changes remain when switching Results tabs or reopening Edit Teams.
Earlier-step navigation follows existing application rules. Changing cohort
inputs or explicitly generating a new allocation invalidates/replaces the saved
allocation as before; no additional persistence or navigation system was added.

## 14–15. Exports

Excel, private hotel PDF and the UI use the same saved allocation object.
Export controls are absent while editing, and requests use the saved allocation,
never the draft. The private PDF shows every occupied room, the current room
number, names, role labels, single/shared occupancy and room total. General
participant PDFs continue to exclude hotel assignments. Editable Excel retains
its worksheets and formatting, using the updated Hotel Rooms and Hotel Summary
sheets without regenerating other activities.

The actual files downloaded by Chrome were parsed independently: **22 rooms,
37 unique occupants**, identical assignments and roles, with no empty rooms,
duplicate/missing guests or accessibility information. The example increased
the original room count by one after a shared room was split.

## 16. Source files changed

Modified:

- `frontend/app/page.tsx`
- `frontend/app/globals.css`
- `frontend/components/ParticipantIdentity.tsx`
- `frontend/components/ResultsPresentation.tsx`
- `frontend/components/hotelSummary.ts`
- `frontend/backend/app/main.py`
- `frontend/backend/app/services/excel.py`
- `frontend/backend/app/services/pdf_export.py`
- `frontend/backend/tests/test_api_improvements.py`
- `frontend/backend/tests/test_exports_improvements.py`
- `frontend/tests/results-responsive-review.cjs` (accepts an explicit test Python)
- `PYTHON314-RESULTS.md` (marks the earlier compatibility report as historical)

Added:

- `frontend/components/AccessibilityFlagsDialog.tsx`
- `frontend/components/hotelEditing.ts`
- `frontend/backend/tests/test_manual_hotel_rooms.py`
- `frontend/tests/manual-hotel-ui.test.cjs`
- `frontend/tests/accessibility-hotel-browser.cjs`
- `frontend/tests/verify-browser-exports.py`
- `docs/python314-feature-review.md`

`optimizer.py`, model schemas, scoring weights, university directory, automatic
hotel logic, requirements, package files, Windows launchers and workflows are
unchanged by this feature work. The source proxy configuration was restored
after using port 8114 for the isolated test build.

## 17. Validation evidence

- Python 3.14 backend: **144 passed** in 246.00 seconds.
- Frontend regression tests: **30 passed**.
- Frontend TypeScript: passed.
- ESLint for all changed TypeScript/TSX files: passed, using external sandbox
  tooling; no application dependency was added.
- Ruff undefined/unused-name and syntax checks on changed backend Python files:
  passed.
- Next.js production build: passed.
- Existing Chrome workflow: passed through the production frontend proxy,
  including imports, all six activities, faculty/prayer scheduling, protected
  edit rejection, dragging, save/undo/cancel/reset, policy override and exports.
- Existing Chemistry-enabled workflow: passed with a 27-person cohort, actual
  Chemistry workbook upload/matching, all six views at desktop/tablet/mobile,
  keyboard focus, selected edit state and unchanged saved export assignments.
- New Chrome feature workflow: passed in development and the final production
  build, including every flag lifecycle operation, actual drag MOVE, keyboard
  MOVE, one-person destinations, multiple rooms, all undo operations, Cancel,
  save cleanup, hotel-only reset and saved export payloads.
- Downloaded Excel/private PDF/general PDF: independently verified.
- Results screenshot comparison: **18/18 pixel-identical** under standardized
  conditions with flags off; flagged views were checked in all six activities.
- Desktop, tablet and mobile setup screenshots: captured and inspected.

Final test runs have no failures. During implementation, an export test needed
whitespace normalization for wrapped PDF text, and the legacy browser test caught
an unnecessary heading wrapper, which was removed. A proxy test was also rerun
after the temporary test port override was restored. The two older assertions
requiring capacity-three approval and review warnings for intentional singles
were updated to the new requirements.

Logs, screenshots, frozen visual data and downloaded files are under
`/tmp/aip-py314-study-20261111/ui-review/`. In particular:

- `backend-full.log`, `frontend-tests.log`, `frontend-lint.log`, `backend-lint.log`
- `production-build.log`, `typecheck.log`
- `existing-browser.log`, `feature-browser-final.log`
- `chemistry-browser.log`
- `results-visual-comparison.json`, `before-stable/`, `after-stable/`
- `features-final/` (setup/modal/room screenshots, saved manifest and exports)

## 18. Limits

Flags disappear on a full browser reload, as intended for frontend session
state. The existing administrative application has no sign-in system; this work
does not add authentication or treat localhost as an authorization boundary.
Flags are visible only in that administrative UI, not shared reports.

Native Windows execution and portable packaging were not run. The workspace
is temporary storage, so keep a separate copy before system cleanup. No new
Windows ZIP or other release artifact was created for this task.

## 19. Run locally on this Mac

The review instance is already available at **http://127.0.0.1:3114**.

For source development after stopping the sandbox preview processes, use two
terminals. Do not stop or replace the original reference app on ports 3000/8000.

Backend:

```sh
cd /tmp/aip-py314-study-20261111/candidate/frontend/backend
/tmp/aip-py314-study-20261111/env314/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8114
```

Frontend:

```sh
cd /tmp/aip-py314-study-20261111/candidate/frontend
NEXT_PUBLIC_API_URL=http://127.0.0.1:8114 NEXT_TELEMETRY_DISABLED=1 npm run dev -- --hostname 127.0.0.1 --port 3115
```

Open **http://127.0.0.1:3115** for development. Dependencies and the Python 3.14
environment are already installed in the sandbox. Ctrl+C stops a server started
in your terminal. Do not start a second process on an already occupied port.

## 20. Short manual browser checklist

1. Upload or enter fictional participants; inspect all three setup steps at
   desktop and narrow widths.
2. Open Accessibility Flags, search/select two people and Save. Reopen, change
   a selection and Cancel; confirm the saved selection remains.
3. Generate all six activities. Check the small icons beside the correct names,
   including after swapping people.
4. Open Hotel Rooms → Edit Teams → Add Room. Drag one person out of a shared
   room into the empty room. Confirm both people remain alone; try Undo and the
   Move Participant controls.
5. Add another unused room and Save. Confirm the unused empty room disappears
   and the room total increases by one for the occupied private room.
6. Download Editable Excel and the private Hotel Rooms PDF. Check room numbers,
   both singles, totals and absence of accessibility flags. The general PDF must
   omit hotel assignments.
7. Reopen editing; test Cancel and hotel-only Reset to Generated. Unrelated
   saved activity edits must remain.
