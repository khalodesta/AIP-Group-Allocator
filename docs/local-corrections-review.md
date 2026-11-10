# Final corrections: local Mac review

These local source changes supersede the earlier seven-improvement release report.
They remain on `feature/week2-seven-improvements`. No commit, push, Windows build,
PyInstaller run, GitHub Actions run, release, or deployment is part of this task.
Existing Windows packages represent the earlier application and do not include
these corrections.

## Implemented changes

1. **Two university grouping categories.** Public and Private are the only
   selectable values, optimizer categories, result markers, and confirmed mapping
   values. Known reliable mappings are automatic. Institutions whose official
   classification does not establish a confident binary grouping require explicit
   administrator confirmation. Their legal metadata, names, aliases, and stable
   identity remain unchanged. Capital-Helwan aliases still resolve together;
   Helwan National University stays separate.
2. **Classification review and persistence.** One confirmed category applies to
   every participant from that university. Conflicting imported categories require
   review. Local corrections and JSON transfer remain available. Older unsupported
   saved categories require a new Public/Private confirmation while retaining their
   institution identity and aliases; they are never silently converted to Private.
3. **Explicit male-only prayer selection.** The checklist contains only recorded
   males, stale/ineligible selections are removed, and API validation rejects
   invalid selections. Names and university background do not determine observance.
   Gender is excluded from faculty matching, workload objectives, and appointment
   quality calculations.
4. **Global faculty availability and valid idle gaps.** All three faculty use the
   global scheduling period. Individual availability controls and model fields are
   removed; legacy request fields cannot restrict the schedule. Only selected
   participants are unavailable during the protected prayer interval. Unselected
   participants continue normally, and different faculty may have different idle
   gaps until the editable resume time. Offering matching, balanced workloads,
   duration, nonoverlap, unique assignments, and explicit fixed-end restrictions
   remain enforced.
5. **Simplified My Reflections results.** Faculty headers show names alone. The
   chronological-order subtitle is removed, and the only summary statistics are
   Participants and the latest actual appointment end time. Participant details,
   appointment tables, matching data, and editing controls remain available.
6. **Results colors.** Full participant rows use light blue for Male and light pink
   for Female. A separate gold/green marker indicates Private/Public, with an
   accessible label, tooltip, and compact legend. Support uses recorded gender and
   role without an invented university category. Faculty gender remains unknown.
7. **Whole hotel room colors.** The entire room card uses one occupant-gender tint.
   Approved mixed-gender exceptions and rooms with unrecorded gender use a neutral
   appearance and explanation. Room numbers, occupants, roles, counts, private
   manifest, and editable Excel remain intact.

Existing BUS lead coverage, independent support-role balancing, hotel single-room
rules and analyst exception, six allocation types, optional Business Chemistry,
drag-and-drop, Switch/Swap, Save/Cancel/Undo/Reset, and exports remain in use.
The existing diversity priority and coefficients are unchanged; the category
factor now balances the two confirmed cohort proportions only.

## Files

- `frontend/app/page.tsx`, `globals.css`, and `frontend/types/index.ts`.
- `frontend/components/ParticipantIdentity.tsx`, `UniversityReview.tsx`,
  `universityClassification.ts`, `ReflectionResultsSummary.tsx`, and `reflectionUi.ts`.
- Backend `app/models.py`, `services/normalization.py`, and `services/optimizer.py`.
- `backend/data/generate_universities.py` and `university_directory.json`.
- Backend regression tests: `test_core.py`, `test_university_improvements.py`,
  `test_optimizer_improvements.py`, `test_api_improvements.py`, and
  `test_exports_improvements.py`.
- `frontend/tests/results-ui.test.cjs` and `browser-review.cjs`, plus review docs.

The pre-existing generated `frontend/next-env.d.ts` edit is preserved. Windows
packaging scripts and workflows are unchanged.

## Launch on this Mac

Keep these commands running in separate terminals.

Backend:

```sh
cd /Users/desta/Deloitte_AIP_Project
.venv/bin/python -m uvicorn app.main:app --app-dir frontend/backend --host 127.0.0.1 --port 8000
```

Frontend:

```sh
cd /Users/desta/Deloitte_AIP_Project/frontend
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Open <http://localhost:3000>. Stop a server with Ctrl+C in its terminal. If these
ports are already running from this review session, open the URL directly rather
than starting duplicate servers.

## Browser checklist

- Import or manually enter a cohort. Confirm that university review offers only
  Public/Private, asks once per institution, retains aliases after confirmation,
  supports corrections, and keeps Capital-Helwan separate from Helwan National.
- Review the three faculty names/offerings and support roles/genders. Confirm
  there are no per-faculty availability controls.
- Enable prayer scheduling at 11:15, duration 20 minutes, prayer 11:40, resume
  13:00. Select the relevant males explicitly; female names must be absent.
- Generate all six activities. Check that unselected people continue during the
  break, selected people do not overlap it, and genuine idle gaps resume correctly.
- In My Reflections, check the two summary statistics and name-only faculty headers.
- Check full-row colors and gold/green markers across every Results tab. In Hotel
  Rooms, check whole-room tint, role labels, neutral exceptions, and exact totals.
- Test same/cross-faculty swaps, rejection of a protected-break conflict, and
  Save/Cancel/Undo/Reset. Verify saved times in Excel and PDF.
- Check both BUS Teams retain a Support Lead. Download the private hotel PDF and
  confirm hotel assignments remain absent from the general participant PDF.

## Verification and limits

Local verification includes the complete backend suite, React component tests,
TypeScript, frontend critical-error/hooks/ARIA lint, Python critical-error lint,
Git whitespace checks, a normal Next.js production build, and isolated Chrome
testing with fictional participants and staff. Final results are recorded in the
handoff message after the browser checks finish.

Scheduling remains within one calendar day. Reusable mappings are local to the
browser profile unless exported. Institutions without a reliable binary grouping
need administrator confirmation by design. Windows compatibility of these local
corrections has not been built or tested in this task.
