# Python 3.14 sandbox comparison — historical baseline

This report describes the compatibility experiment before the subsequent UI,
Accessibility Flags and manual hotel-room changes. See
[the current local feature review](docs/python314-feature-review.md) for the
updated application's behavior and validation.

The reference project was left unchanged. The experimental copy runs successfully on standard CPython 3.14.10 on macOS arm64. Its optimizer source and application logic are identical to the reference; compatibility required three direct dependency upgrades. Native Windows execution and a new portable Windows build have not been tested.

## What changed

| File/package | Reference | Sandbox |
|---|---|---|
| frontend/.python-version | 3.12 | 3.14 |
| OR-Tools | 9.11.4210 | 9.15.6755 |
| pandas | 2.2.3 | 2.3.3 |
| Pydantic | 2.10.4 | 2.14.3 |

The old requirements do not have a usable set of Python 3.14 Windows wheels. The updated requirements resolve using prebuilt Windows x64 wheels. The generated Windows lock file is a dependency-resolution check, not proof of native Windows execution. FastAPI, Uvicorn, reportlab, pytest and the other direct pins were retained. Transitive versions, including pydantic-core and protobuf, are recorded in the environment freezes. No optimizer rewrite, objective-weight changes, added solver passes, frontend changes, release builds, commits, pushes or deployments were made.

## Controlled comparison

A: original source and original direct dependency pins on isolated Python 3.12.10. B: the updated dependencies on isolated Python 3.12.10. C: the same updated package versions on isolated Python 3.14.10. This separates the dependency upgrade from the interpreter change. A is a fresh installation of the project’s original requirements, rather than a copy of the reference computer’s Python 3.9 virtual environment; both freezes are retained.

Ten fictional scenarios were tested with seed 42: balanced 27, balanced 30, highly uneven gender, predominantly private, predominantly public, Chemistry disabled, different group sizes, one university, mandatory locks, and prayer-aware reflections. Balanced 27, balanced 30 and prayer-aware 27 were also repeated with seeds 17 and 93. That is 16 matched runs per environment, 48 allocation requests total.

All environments received byte-identical frozen inputs. Each main CP-SAT solve had a 20-second wall-clock budget and one search worker. Activity-specific BUS, reflection and hotel solves retained their existing settings. Heavy runs were sequential. Total request time includes those additional solves and model construction, and excludes process import/startup. A callback recorded the first incumbent using the same harness in every environment. Wall-clock cutoffs can change the final incumbent, even with the same seed.

| Environment | Python | OR-Tools | Mean request s | Median first main solution s | Fallbacks | Hard violations |
|---|---|---|---:|---:|---:|---:|
| original312 | 3.12.10 | 9.11.4210 | 25.057 | 1.533 | 0 / 16 | 0 |
| updated312 | 3.12.10 | 9.15.6755 | 23.77 | 0.998 | 0 / 16 | 0 |
| updated314 | 3.14.10 | 9.15.6755 | 23.689 | 1.013 | 0 / 16 | 0 |

All benchmark requests generated all six activities. Main solver status was FEASIBLE, not a certificate of global optimality. No benchmark exception or invalid model was hidden behind a fallback.

## Allocation quality

“Better” means lower cost under the existing priority order, not a subjective rating: (1) proportional gender + Public/Private deviation and worst gender deviation; (2) exact-university pairs; (3) repeated teammates + three times same-offering pairs; (4) three times same-primary + same-secondary pairs when Chemistry is enabled. BUS retains its separate proportional-deviation objective. Chemistry contributes zero when disabled.

| Python 3.14 vs original dependencies | Better | Equal | Worse |
|---|---:|---:|---:|
| Main / Quiz / Team objective | 11 | 0 | 5 |
| Top gender/category balance tier | 0 | 16 | 0 |
| BUS objective | 0 | 16 | 0 |

With the same updated dependencies, Python 3.14 versus Python 3.12 produced 1 better, 15 equal and 0 worse core objective results. Interpreter upgrades do not add a new allocation strategy; changes relative to the old application are principally associated with the newer OR-Tools/dependency stack. These finite fictional samples do not establish universal superiority.

| Core metrics across the same 16 requests | Original | Python 3.14 |
|---|---:|---:|
| Top balance penalty | 6894 | 6894 |
| Same-university pairs | 296 | 270 |
| Repeated teammates (original three activities only) | 418 | 457 |
| Same-offering pairs | 362 | 319 |
| Same-primary pairs (Chemistry enabled only) | 650 | 666 |
| Same-secondary pairs (Chemistry enabled only) | 683 | 683 |

Pair totals are diagnostic components; improvements in a lower tier do not offset deterioration in a higher tier. Mandatory locks and highly uneven cohorts remain valid reasons for unequal raw male/female counts. BUS gender/category metrics use new hires only.

### Representative Main Groups, seed 42

Public/Private columns show Public:Private. M/F columns show Male:Female. All group-level values for all activities and runs are retained in the JSON files.

| Cohort / group | Original M/F | Python 3.14 M/F | Original Public/Private | Python 3.14 Public/Private |
|---|---|---|---|---|
| balanced27 / Group 1 | 3:3 | 3:3 | 2:4 | 2:4 |
| balanced27 / Group 2 | 3:3 | 3:3 | 2:4 | 2:4 |
| balanced27 / Group 3 | 3:2 | 3:2 | 1:4 | 1:4 |
| balanced27 / Group 4 | 2:3 | 3:2 | 1:4 | 1:4 |
| balanced27 / Group 5 | 3:2 | 2:3 | 1:4 | 1:4 |
| balanced30 / Group 1 | 3:3 | 3:3 | 3:3 | 3:3 |
| balanced30 / Group 2 | 3:3 | 3:3 | 3:3 | 3:3 |
| balanced30 / Group 3 | 3:3 | 3:3 | 3:3 | 3:3 |
| balanced30 / Group 4 | 3:3 | 3:3 | 3:3 | 3:3 |
| balanced30 / Group 5 | 3:3 | 3:3 | 3:3 | 3:3 |

### Per-run core comparison

Each vector follows the four priority tiers described above. Lower is better; compare from left to right.

| Case | Seed | Original tiers | Python 3.14 tiers | Outcome |
|---|---:|---|---|---|
| balanced27 | 42 | [568, 3, 81, 207] | [568, 0, 65, 153] | better |
| balanced30 | 42 | [0, 2, 112, 193] | [0, 4, 111, 174] | worse |
| uneven30 | 42 | [600, 3, 107, 204] | [600, 6, 91, 222] | worse |
| private_majority | 42 | [432, 12, 119, 210] | [432, 7, 113, 242] | better |
| public_majority | 42 | [640, 19, 121, 157] | [640, 13, 94, 130] | better |
| chemistry_disabled | 42 | [568, 2, 80, 0] | [568, 0, 69, 0] | better |
| different_sizes | 42 | [393, 3, 60, 163] | [393, 0, 68, 172] | better |
| same_university | 42 | [0, 225, 76, 185] | [0, 225, 105, 185] | worse |
| locked27 | 42 | [853, 2, 64, 165] | [853, 2, 58, 153] | better |
| prayer27 | 42 | [568, 3, 81, 207] | [568, 0, 65, 153] | better |
| balanced27 | 17 | [568, 1, 99, 149] | [568, 2, 85, 150] | worse |
| balanced27 | 93 | [568, 4, 85, 160] | [568, 0, 92, 182] | better |
| balanced30 | 17 | [0, 7, 113, 157] | [0, 6, 107, 212] | better |
| balanced30 | 93 | [0, 5, 122, 167] | [0, 3, 114, 221] | better |
| prayer27 | 17 | [568, 1, 99, 149] | [568, 2, 85, 150] | worse |
| prayer27 | 93 | [568, 4, 85, 160] | [568, 0, 92, 182] | better |

## Model and reference integrity

80 reference source files were checked by SHA-256; changed files: []. Git HEAD/status and the original environment’s installed dependency list are unchanged.

Model audit, A vs C: {"raw_inputs_identical": true, "validated_inputs_identical": true, "core_models_identical": true, "bus_models_identical": true, "individual_balance_penalties_identical": true}.
Model audit, B vs C: {"raw_inputs_identical": true, "validated_inputs_identical": true, "core_models_identical": true, "bus_models_identical": true, "individual_balance_penalties_identical": true}.

The model audit compares variable counts, constraint counts, objective coefficient signatures and model validation output for the core and BUS models. It is a structural/objective check, not a claim that protobuf serialization is identical across OR-Tools versions. Identical application source, validation tests and allocation audits verify the preserved constraints.

## Functional validation

- Original Python 3.12 environment: 128 backend tests passed in 258.94 seconds.
- Python 3.14 environment: 128 backend tests passed in 246.15 seconds. Deprecation warnings from the retained FastAPI/Starlette versions are recorded in the log.
- Frontend: TypeScript check, production build and all 21 frontend regression tests passed.
- Production frontend → Python 3.14 FastAPI: actual allocation generation for all six activities passed. The backend release regression also submitted the real fictional 27-person request and validated its output.
- Chrome workflow: master/support imports, saved university aliases and Public/Private confirmation, prayer selection, all six result tabs at desktop/tablet/mobile widths, same/cross-faculty dragging, protected swap rejection, Switch/Undo/Cancel/Reset/Save, Excel/public PDF/private hotel exports, and approved mixed-room warning all passed.
- The external browser harness needed a 100ms pause after drags because dnd-kit retains a capture-phase click blocker for 50ms. This fixed an automation click-timing issue without changing application code or weakening assertions. Failed attempts and the successful log are retained.
- Windows x64 Python 3.14 dependencies resolved with binary wheels only; actual Windows execution and PyInstaller packaging were not run.

## Files and reproduction

- `candidate/`: isolated experimental source copy.
- `candidate/PYTHON314-TEST-NOTES.md`: source setup instructions for a separate Windows folder.
- `python314-migration.patch`: the two-file compatibility change.
- `candidate/frontend/requirements-python314-windows.lock.txt`: Windows dependency lock with hashes.
- `inputs/`: frozen fictional cohort requests.
- `run_comparison.py`, `run_matrix.py`: common benchmark harness and exact matrix.
- `results/comparison.csv`: per-run measurements.
- `results/summary.json`: aggregate values and paired outcomes.
- `results/*-allocation.json`: complete generated allocations.
- `results/*-tests.log`, `results/browser314.log`, `results/browser-artifacts/`: validation evidence.
- `reference-snapshot.json`, `results/reference-integrity.json`: preservation evidence.

The sandbox app is served locally at http://127.0.0.1:3114 with its isolated backend on 8114. Only the test build’s proxy port was overridden; the candidate source configuration was restored afterward. The original app’s ports and servers were left alone. This experiment is in temporary storage; keep a copy before system cleanup if needed.
