import math
import random
from collections import defaultdict
from itertools import combinations
from typing import Dict, List, Optional
from ortools.sat.python import cp_model
from app.models import (ActivityAllocation, AllocationSnapshot, Configuration,
                        Group, OptimizeRequest, Participant)
from app.services.normalization import normalize_gender, normalize_university


def group_sizes(n: int, mode: str, value: int) -> List[int]:
    if n < 2: raise ValueError("At least two participants are required")
    if mode == "max_size":
        if value < 2: raise ValueError("Maximum group size must be at least 2")
        count = math.ceil(n / value)
    elif mode == "group_count":
        count = value
        if count > n: raise ValueError("Number of groups cannot exceed participants")
    else: raise ValueError(f"Unknown group mode: {mode}")
    base, remainder = divmod(n, count)
    return [base + (1 if i < remainder else 0) for i in range(count)]


def optimize(request: OptimizeRequest) -> AllocationSnapshot:
    people = request.participants
    if len({p.id for p in people}) != len(people): raise ValueError("Participant IDs must be unique")
    previous = {a.activity_id: a for a in (request.existing_allocation.activities if request.existing_allocation else [])}
    regenerate = set(request.regenerate_activity_ids or [a.id for a in request.configuration.activities])
    fixed, to_solve = [], []
    for activity in request.configuration.activities:
        if activity.id in previous and (activity.locked or activity.id not in regenerate): fixed.append(previous[activity.id])
        else: to_solve.append(activity)
    prior_pairs = defaultdict(int)
    for alloc in fixed:
        for group in alloc.groups:
            for pair in combinations(sorted(group.participant_ids), 2): prior_pairs[pair] += 1
    model = cp_model.CpModel(); n = len(people); ids = [p.id for p in people]
    variables = {}; sizes_by_activity = {}
    for a_idx, activity in enumerate(to_solve):
        sizes = group_sizes(n, activity.mode, activity.value); sizes_by_activity[activity.id] = sizes
        for i in range(n):
            for g in range(len(sizes)): variables[a_idx, i, g] = model.NewBoolVar(f"x_{a_idx}_{i}_{g}")
            model.AddExactlyOne(variables[a_idx, i, g] for g in range(len(sizes)))
        for g, size in enumerate(sizes): model.Add(sum(variables[a_idx, i, g] for i in range(n)) == size)
        locks = request.locked_assignments.get(activity.id, {})
        for pid, group_id in locks.items():
            if pid not in ids: raise ValueError(f"Locked participant {pid} not found")
            try: g = int(group_id.rsplit("-", 1)[-1])
            except ValueError: raise ValueError(f"Invalid locked group {group_id}")
            if g >= len(sizes): raise ValueError(f"Locked group {group_id} is incompatible")
            model.Add(variables[a_idx, ids.index(pid), g] == 1)
    university_cost = []
    gender_cost = []
    repeat_cost = []
    for i, j in combinations(range(n), 2):
        pair = tuple(sorted((ids[i], ids[j]))); pair_vars = []
        for a_idx, activity in enumerate(to_solve):
            group_vars = []
            for g in range(len(sizes_by_activity[activity.id])):
                z = model.NewBoolVar(f"z_{a_idx}_{i}_{j}_{g}")
                model.Add(z <= variables[a_idx, i, g]); model.Add(z <= variables[a_idx, j, g])
                model.Add(z >= variables[a_idx, i, g] + variables[a_idx, j, g] - 1); group_vars.append(z)
            t = model.NewBoolVar(f"t_{a_idx}_{i}_{j}"); model.Add(t == sum(group_vars)); pair_vars.append(t)
        if pair_vars:
            repeat = model.NewIntVar(0, len(pair_vars) + prior_pairs[pair], f"r_{i}_{j}")
            model.Add(repeat >= sum(pair_vars) + prior_pairs[pair] - 1)
            repeat_cost.append(repeat)

    # Priority 1: every same-university teammate pair has a cost. Unknown values
    # are excluded rather than treated as a meaningful shared category.
    universities = [p.attributes.get("UniversityId") or normalize_university(p.attributes.get("University")) for p in people]
    for i, j in combinations(range(n), 2):
        if not universities[i] or universities[i] != universities[j]:
            continue
        for a_idx, activity in enumerate(to_solve):
            for g in range(len(sizes_by_activity[activity.id])):
                z = model.NewBoolVar(f"university_pair_{a_idx}_{i}_{j}_{g}")
                model.Add(z <= variables[a_idx, i, g])
                model.Add(z <= variables[a_idx, j, g])
                model.Add(z >= variables[a_idx, i, g] + variables[a_idx, j, g] - 1)
                university_cost.append(z)

    # Priority 2: minimize proportional gender deviation. Every recorded value
    # (including respectful non-binary/other labels) is balanced independently.
    genders = [normalize_gender(p.attributes.get("Gender")) for p in people]
    categories = sorted({value for value in genders if value})
    for a_idx, activity in enumerate(to_solve):
        for g, size in enumerate(sizes_by_activity[activity.id]):
            for category in categories:
                members = [i for i, value in enumerate(genders) if value == category]
                count = sum(variables[a_idx, i, g] for i in members)
                deviation = model.NewIntVar(0, n * n, f"gender_dev_{a_idx}_{g}_{category}")
                model.AddAbsEquality(deviation, count * n - len(members) * size)
                gender_cost.append(deviation)

    # Safe data-dependent scaling gives lexicographic weighted behavior:
    # one university-pair improvement outweighs every possible lower-priority
    # change, and one gender-deviation point outweighs every repeat change.
    repeat_upper = max(1, len(repeat_cost) * max(1, len(request.configuration.activities) - 1))
    gender_upper = max(1, len(gender_cost) * n * n)
    gender_weight = repeat_upper + 1
    university_weight = gender_upper * gender_weight + repeat_upper + 1
    model.Minimize(
        university_weight * sum(university_cost)
        + gender_weight * sum(gender_cost)
        + sum(repeat_cost)
    ); solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = request.configuration.time_limit_seconds
    solver.parameters.random_seed = request.configuration.seed; solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    names = {cp_model.OPTIMAL: "OPTIMAL", cp_model.FEASIBLE: "FEASIBLE",
             cp_model.INFEASIBLE: "INFEASIBLE", cp_model.UNKNOWN: "UNKNOWN"}
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        if status == cp_model.INFEASIBLE: raise ValueError("Configuration is infeasible with current locks")
        return fallback(request, fixed)
    solved = []
    for a_idx, activity in enumerate(to_solve):
        groups = []
        for g in range(len(sizes_by_activity[activity.id])):
            members = [ids[i] for i in range(n) if solver.Value(variables[a_idx, i, g])]
            groups.append(Group(id=f"{activity.id}-{g}", name=f"Group {chr(65+g)}", participant_ids=members))
        solved.append(ActivityAllocation(activity_id=activity.id, activity_name=activity.name, groups=groups, locked=activity.locked))
    order = {a.id: i for i, a in enumerate(request.configuration.activities)}
    all_activities = sorted(fixed + solved, key=lambda x: order[x.activity_id])
    return AllocationSnapshot(activities=all_activities, status=names[status], objective_value=solver.ObjectiveValue(), seed=request.configuration.seed)


def fallback(request: OptimizeRequest, fixed: Optional[List[ActivityAllocation]] = None) -> AllocationSnapshot:
    rng = random.Random(request.configuration.seed); ids = [p.id for p in request.participants]
    activities = list(fixed or []); existing = {a.activity_id for a in activities}
    for activity in request.configuration.activities:
        if activity.id in existing: continue
        shuffled = ids[:]; rng.shuffle(shuffled); sizes = group_sizes(len(ids), activity.mode, activity.value); groups=[]; start=0
        for g, size in enumerate(sizes):
            groups.append(Group(id=f"{activity.id}-{g}", name=f"Group {chr(65+g)}", participant_ids=shuffled[start:start+size])); start += size
        activities.append(ActivityAllocation(activity_id=activity.id, activity_name=activity.name, groups=groups))
    return AllocationSnapshot(activities=activities, status="FEASIBLE_FALLBACK", seed=request.configuration.seed)
