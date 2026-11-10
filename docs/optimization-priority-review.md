# Local optimization priority review

Fictional data; local development only. This compares the exact working optimizer immediately before this task with the revised version. Git HEAD was not the baseline because earlier authorized local changes were already present.

## Cause and targeted change

The previous joint objective was `WU × (10U + 3O + 3P + S) + WG × (G + C) + R`. Here U is same-university pairs, O same-offering pairs, P/S same Primary/Secondary Chemistry pairs, G/C proportional gender/category deviation, and R repeated teammates. `WG = repeat_upper + 1`; `WU = gender_upper × WG + repeat_upper + 1`. Because offering and both Chemistry factors shared WU, even one Secondary Chemistry improvement could outweigh every possible gender/category improvement. Gender was already evaluated per group; its position below that whole profile tier was the problem.

The revised single objective is `WB × (G + C + max_gender_deviation) + WU × U + WM × (R + 3O) + 3P + S`. No assignment quotas or extra solver passes were introduced. Existing pair and proportional-deviation variables remain. One soft maximum variable per relevant model adds attention to the worst individual group. Gender and Public/Private have equal coefficients within their shared highest tier.

Each group uses `abs(N × local_count − cohort_count × group_size)`, separately for each known gender and each of the two university categories. This uses actual cohort proportions, including very uneven cohorts. University aliases, normalization and classifications are unchanged.

Weights use upper bounds on feasible penalties, rather than arbitrary constants. If H bounds `3P+S`, M bounds `R+3O`, and Umax bounds university cost: `WM=H+1`; `L=WM×M+H`; `WU=L+1`; `WB=WU×Umax+L+1`. Thus one point in a higher tier outweighs all achievable lower-tier improvements. For core groups, the bounds use the sum of group pair capacities; repeat bounds use encounters minus the largest activity encounter count. For BUS, the existing proportional deviations remain, and their bounds use the cohort counts and bus capacities.

Actual coefficients in the 27-person, three-activity Chemistry-enabled fixture:

| Penalty unit | Before | After |
|---|---:|---:|
| Gender deviation | 703 | 86,261,161 |
| Public/Private deviation | 703 | 86,261,161 |
| Worst group gender deviation | absent | 86,261,161 |
| Same-university pair | 307,499,230 | 476,581 |
| Repeated teammate | 1 | 721 |
| Same-offering pair | 92,249,769 | 2,163 |
| Same Primary pair | 92,249,769 | 3 |
| Same Secondary pair | 30,749,923 | 1 |

Here H=720, M=660 and Umax=180. Coefficients change with capacities and enabled factors. Chemistry disabled means no Chemistry variables or contribution; a regression changes Chemistry attributes and verifies identical assignments and objective. Offering keeps coefficient 3 within the repeats/offering tier; Primary keeps a 3:1 preference over Secondary in the lowest tier.

BUS retains exactly two buses, balanced new-hire counts, independent Support Lead/Analyst distribution and at least one lead per bus. Only new hires enter diversity scoring. BUS previously combined university:gender:offering:category:Primary:Secondary as 5:4:3:4:3:1, followed by a history tie-break. It now uses the same ordered tiers. The BUS history tie-break and legacy Sports contributions to repeat scoring were removed to enforce the requested Main/Quiz/Team-only repeat scope. No repeat objective was removed from those three activities.

## Benchmark method

Python 3.9 / OR-Tools 9.11.4210; seed 42; one search worker. The nine paired cases use identical input SHA-256 values and identical limits. The core solve limit is four seconds, BUS remains three seconds, and unchanged list-mode faculty allocation remains five seconds. Reported elapsed time includes model construction, BUS, faculty and hotel allocation. All ordinary core results below are FEASIBLE, with no heuristic fallback and zero hard-constraint violations; FEASIBLE is not proof of optimality. Every solver stage and its status/time is recorded in the JSON.

The nine cases include 27 hires (14M/13F), 30 hires (15M/15F), 26M/4F, 27-private/3-public, 24-public/3-private, Chemistry disabled, different activity sizes (5/7/4), a cohort entirely from one university, and a mandatory 1M/5F Main Group lock. Support-role variants are included. All names are fictional.

Run from `frontend/backend`: `../../.venv/bin/python benchmarks/priority_adjustment.py --output /tmp/priority-after.json`. The script also accepts `--optimizer-path`, `--time-limit`, `--cases`, and a separately labelled `--fallback` mode. Raw results and objective coefficients are in [the benchmark results directory](../frontend/backend/benchmarks/results/priority-adjustment/). The directory includes source hashes and the exact optimizer diff; reverse that diff on a temporary copy of the revised optimizer to reconstruct the frozen baseline. Both before and after use the same measurement code and the same original-three-activity repeat scope.

## Main Group distributions

Male:female counts, in group order:

| Case | Before | After |
|---|---|---|
| balanced27 | 4:2, 2:4, 3:2, 2:3, 3:2 | 3:3, 3:3, 3:2, 2:3, 3:2 |
| balanced30 | 2:4, 3:3, 3:3, 4:2, 3:3 | 3:3, 3:3, 3:3, 3:3, 3:3 |
| uneven30 | 5:1, 5:1, 5:1, 6:0, 5:1 | 5:1, 5:1, 5:1, 5:1, 6:0 |
| private_majority | 1:5, 3:3, 4:2, 3:3, 4:2 | 3:3, 3:3, 3:3, 3:3, 3:3 |
| public_majority | 3:3, 3:3, 2:3, 3:2, 3:2 | 3:3, 3:3, 2:3, 3:2, 3:2 |
| chemistry_disabled | 3:3, 3:3, 3:2, 3:2, 2:3 | 3:3, 3:3, 2:3, 3:2, 3:2 |
| different_sizes | 2:3, 3:2, 2:3, 2:2, 2:2, 3:1 | 3:2, 2:3, 3:2, 2:2, 2:2, 2:2 |
| same_university | 3:3, 3:3, 3:3, 4:2, 2:4 | 3:3, 3:3, 3:3, 3:3, 3:3 |
| locked27 | 1:5, 4:2, 3:2, 3:2, 3:2 | 1:5, 4:2, 3:2, 3:2, 3:2 |

Public/private counts in those same Main Groups:

| Case | Before | After |
|---|---|---|
| balanced27 | 1/5, 2/4, 1/4, 1/4, 2/3 | 2/4, 2/4, 1/4, 1/4, 1/4 |
| balanced30 | 3/3, 3/3, 3/3, 3/3, 3/3 | 3/3, 3/3, 3/3, 3/3, 3/3 |
| uneven30 | 1/5, 2/4, 0/6, 2/4, 1/5 | 1/5, 1/5, 1/5, 1/5, 2/4 |
| private_majority | 0/6, 1/5, 1/5, 0/6, 1/5 | 1/5, 0/6, 1/5, 1/5, 0/6 |
| public_majority | 4/2, 6/0, 5/0, 5/0, 4/1 | 5/1, 5/1, 4/1, 5/0, 5/0 |
| chemistry_disabled | 2/4, 2/4, 1/4, 1/4, 1/4 | 2/4, 2/4, 1/4, 1/4, 1/4 |
| different_sizes | 2/3, 2/3, 1/4, 1/3, 1/3, 0/4 | 2/3, 1/4, 1/4, 1/3, 1/3, 1/3 |
| same_university | 6/0, 6/0, 6/0, 6/0, 6/0 | 6/0, 6/0, 6/0, 6/0, 6/0 |
| locked27 | 0/6, 2/4, 0/5, 3/2, 2/3 | 0/6, 2/4, 2/3, 2/3, 1/4 |

## Diversity, constraints and execution time

Before → after. G/C are summed scaled proportional deviations across Main/Quiz/Team/BUS, excluding support. Lower is better. Maximum gap is the largest raw M/F difference across the original three activities; BUS counts appear separately in the raw per-group data. Perfect 15-person buses necessarily have a one-person difference in a 50/50 cohort.

| Case | G | C | Maximum core gap | Same-university pairs | Repeats | Seconds |
|---|---:|---:|---:|---:|---:|---:|
| balanced27 | 484 → 292 | 356 → 328 | 3 → 1 | 18 → 15 | 27 → 25 | 6.09 → 6.05 |
| balanced30 | 540 → 60 | 660 → 60 | 4 → 0 | 26 → 19 | 35 → 28 | 14.68 → 15.13 |
| uneven30 | 288 → 288 | 384 → 288 | 6 → 6 | 31 → 33 | 37 → 31 | 8.04 → 7.93 |
| private_majority | 780 → 60 | 492 → 492 | 4 → 0 | 39 → 38 | 34 → 39 | 12.70 → 15.85 |
| public_majority | 444 → 292 | 504 → 408 | 3 → 1 | 44 → 44 | 25 → 30 | 5.24 → 5.02 |
| chemistry_disabled | 540 → 292 | 416 → 328 | 3 → 1 | 19 → 23 | 32 → 27 | 4.63 → 4.50 |
| different_sizes | 396 → 244 | 472 → 200 | 3 → 1 | 23 → 17 | 20 → 27 | 6.29 → 6.19 |
| same_university | 420 → 60 | 0 → 0 | 2 → 0 | 435 → 435 | 45 → 25 | 17.22 → 14.53 |
| locked27 | 592 → 432 | 736 → 432 | 4 → 4 | 27 → 17 | 28 → 29 | 5.99 → 5.74 |

University/profile pair counts include Main/Quiz/Team/BUS. Repeats include only Main/Quiz/Team. Profile collision counts are direct observations, including the disabled-Chemistry case for comparison; they are not all part of the objective when Chemistry is off.

| Case | Same-offering pairs | Average distinct offerings/group | Same Primary pairs | Same Secondary pairs |
|---|---:|---:|---:|---:|
| balanced27 | 51 → 47 | 3.882 → 4.118 | 67 → 67 | 73 → 72 |
| balanced30 | 60 → 68 | 4.294 → 4.0 | 82 → 100 | 85 → 85 |
| uneven30 | 69 → 58 | 4.0 → 4.412 | 82 → 90 | 89 → 98 |
| private_majority | 72 → 60 | 3.941 → 4.294 | 84 → 92 | 78 → 104 |
| public_majority | 52 → 54 | 3.882 → 3.765 | 70 → 71 | 64 → 64 |
| chemistry_disabled | 47 → 56 | 4.059 → 3.647 | 85 → 86 | 72 → 85 |
| different_sizes | 42 → 43 | 3.895 → 3.789 | 61 → 71 | 62 → 67 |
| same_university | 67 → 58 | 3.941 → 4.412 | 88 → 100 | 89 → 93 |
| locked27 | 44 → 43 | 4.176 → 4.353 | 66 → 68 | 66 → 76 |

Across these nine fixtures, repeated pairings fall from 283 to 261, offering collisions from 504 to 487, and exact-university collisions from 662 to 641. Individual cases worsen: repeats rise by 5 in each minority-category case, by 7 with different sizes, and by 1 in the locked case. Offering collisions rise in four cases, including 60 → 68 in balanced30. Chemistry collisions generally increase, as expected from moving Chemistry below the other priorities. These are measured tradeoffs, not guarantees that every lower-priority measure improves.

Total observed elapsed time is 80.89 → 80.94 seconds across nine runs. This is not a rigorous speed benchmark: background machine load and assignment-dependent hotel matching affect elapsed time. Core CP-SAT remains capped at the same four seconds and uses one solve; no significant aggregate runtime increase was observed in this sample. The private-majority case increases from 12.70 to 15.85 seconds, while the all-one-university case decreases from 17.22 to 14.53 seconds.

Additional paired runs with a 20-second core limit:

| Case | Main M:F before | Main M:F after | Repeats | Elapsed seconds |
|---|---|---|---:|---:|
| balanced27 | 4:2, 3:3, 1:4, 4:1, 2:3 | 3:3, 3:3, 3:2, 2:3, 3:2 | 34 → 21 | 22.02 → 21.67 |
| same_university | 3:3, 3:3, 3:3, 2:4, 4:2 | 3:3, 3:3, 3:3, 3:3, 3:3 | 36 → 22 | 32.86 → 31.61 |

Both remain FEASIBLE, with no fallback and no hard violations. The 27-person before run includes 1:4 and 4:1 groups; the revised run balances every original-activity group to a difference of at most one. The all-one-university revised run also has 3:3 throughout all original activities.

## Fallback investigation

The core optimizer uses the heuristic only when CP-SAT returns no usable solution (normally UNKNOWN at its time limit). INFEASIBLE remains an error; MODEL_INVALID now raises an explicit model error instead of hiding it behind random assignments. Every normal benchmark above returned a CP-SAT incumbent and bypassed fallback.

The existing seeded fill is retained. A bounded deterministic exchange pass now improves proportional gender/category balance and worst-group deviation by swapping only unlocked participants. Capacities, uniqueness and mandatory locks remain intact. It does not optimize university/repeat/profile tiers or claim optimality. Status stays FEASIBLE_FALLBACK, objective stays null, and each generated activity has an explicit heuristic warning.

Explicitly forced fallback tests, separate from CP-SAT quality:

| Case | Main M:F before | Main M:F after | Elapsed seconds |
|---|---|---|---:|
| balanced27 | 4:2, 4:2, 3:2, 3:2, 0:5 | 3:3, 3:3, 3:2, 3:2, 2:3 | 1.87 → 1.63 |
| uneven30 | 6:0, 4:2, 5:1, 6:0, 5:1 | 5:1, 5:1, 5:1, 6:0, 5:1 | 3.75 → 3.56 |
| locked27 | 1:5, 4:2, 3:2, 4:1, 2:3 | 1:5, 4:2, 3:2, 3:2, 3:2 | 1.53 → 1.48 |

All forced runs report FEASIBLE_FALLBACK and zero hard violations. The forced 1:5 lock is preserved. A heuristic can stop at a local improvement and cannot guarantee the best feasible balance.

## Verification and limits

The complete backend suite passed: **127 tests in 95.17 seconds** (`../../.venv/bin/pytest -q` from `frontend/backend`). Ruff critical-error checks passed for both changed services, the new tests and benchmark script; `git diff --check` passed. The dedicated regressions cover per-group balance, uneven/all-male cohorts, minority category spread, disabled Chemistry, unavoidable locks, BUS staff independence, repeat scope, forced UNKNOWN and MODEL_INVALID statuses, all-group profile penalties, and model validation at 60 hires including objective integer ranges.

Only the existing optimizer, repeat-scoring activity scope, and the directly affected repeat test changed during this task; added files contain tests, benchmarks and this report. Source hashes confirm frontend, forms, manual edits, exports, university classification/normalization, packaging and workflows are untouched. AST comparison confirms all pre-existing optimizer functions except optimize, BUS allocation and fallback are unchanged, including My Reflections and hotel functions.

Remaining limits: balance is soft, so locks or competing top-tier category needs can prevent ideal ratios. A 26M/4F cohort legitimately requires 5:1 and 6:0 groups at size six. Finite-time FEASIBLE results may improve with longer time. Disabled Chemistry remains observable in diagnostics but contributes nothing to scoring. Existing saved/manual allocations retain their memberships until explicitly regenerated. No commits, pushes, deployment or packaging were performed.

The local backend was restarted with the revised optimizer. The frontend at http://127.0.0.1:3000 returned HTTP 200 and the backend health endpoint passed. A live fictional 27-person API request returned FEASIBLE, with every Main/Quiz/Team group differing by at most one male/female participant and BUS new-hire splits of 7:7 and 7:6. This request did not save or replace any existing allocation.
