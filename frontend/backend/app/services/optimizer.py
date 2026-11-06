import math
import random
from collections import defaultdict
from itertools import combinations
from typing import Dict, List, Optional
from ortools.sat.python import cp_model
from app.models import (ActivityAllocation, AllocationSnapshot, Configuration,
                        Group, OptimizeRequest, Participant, ReflectionSession)
from app.services.normalization import display_offering, normalize_gender, normalize_university

CORE_ACTIVITY_IDS = {"main", "quiz", "team", "sports"}


def _minutes(value: str, label: str) -> int:
    try:
        hour, minute = (int(part) for part in value.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59): raise ValueError
        return hour * 60 + minute
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a valid time")


def _clock(value: int) -> str:
    hour, minute = divmod(value, 60); suffix = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    return f"{display_hour}:{minute:02d} {suffix}"


def reflection_capacity(configuration: Configuration, faculty_count: int) -> tuple[int, int]:
    settings = configuration.reflection_settings
    start = _minutes(settings.start_time, "My Reflections start time")
    deadline = _minutes(settings.prayer_deadline, "Friday prayer deadline")
    resume = _minutes(settings.resume_time, "Post-prayer resume time")
    if deadline <= start: raise ValueError("Friday prayer deadline must be after the My Reflections start time")
    if resume < deadline: raise ValueError("Post-prayer resume time cannot be before the prayer deadline")
    slots = (deadline - start) // settings.session_duration_minutes
    return slots, slots * faculty_count


def schedule_reflection(activity: ActivityAllocation, request: OptimizeRequest) -> list[ReflectionSession]:
    settings = request.configuration.reflection_settings
    if not settings.enabled: return []
    faculty = {member.id: member for member in request.faculty_members}
    people = {person.id: person for person in request.participants}
    selected = set(settings.selected_participant_ids)
    unknown = selected - set(people)
    if unknown: raise ValueError("One or more selected My Reflections participants no longer exist")
    non_male = [people[pid].name for pid in selected if people[pid].attributes.get("Gender") != "Male"]
    if non_male: raise ValueError("Friday prayer accommodation can only be selected from the displayed male participant checklist")
    slots_per_faculty, total_capacity = reflection_capacity(request.configuration, len(faculty))
    if len(selected) > total_capacity:
        shortfall = len(selected) - total_capacity
        raise ValueError(f"My Reflections pre-prayer capacity conflict: {len(selected)} participants selected, {total_capacity} slots available, shortfall {shortfall}")
    start = _minutes(settings.start_time, "My Reflections start time")
    deadline = _minutes(settings.prayer_deadline, "Friday prayer deadline")
    resume = _minutes(settings.resume_time, "Post-prayer resume time")
    duration = settings.session_duration_minutes
    sessions = []
    for group in activity.groups:
        member_ids = sorted(group.participant_ids, key=lambda pid: (pid not in selected, people[pid].name.casefold()))
        selected_count = sum(pid in selected for pid in member_ids)
        if selected_count > slots_per_faculty:
            raise ValueError(f"My Reflections pre-prayer capacity conflict for {group.name}: {selected_count} selected participants but only {slots_per_faculty} slots")
        pre_index = post_index = 0
        for pid in member_ids:
            if pre_index < slots_per_faculty:
                session_start = start + pre_index * duration; pre_index += 1
            else:
                session_start = resume + post_index * duration; post_index += 1
            session_end = session_start + duration
            if pid in selected and session_end > deadline:
                raise ValueError(f"{people[pid].name} cannot be scheduled before Friday prayer")
            participant_offering = (display_offering(people[pid].attributes.get("L3 Offering")) or "").casefold()
            faculty_offering = (display_offering(faculty.get(group.id).offering) or "").casefold() if faculty.get(group.id) else ""
            sessions.append(ReflectionSession(participant_id=pid, faculty_id=group.id,
                start_time=_clock(session_start), end_time=_clock(session_end),
                offering_match=bool(participant_offering and participant_offering == faculty_offering),
                before_prayer=session_end <= deadline))
    return sessions


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
    if request.configuration.include_business_chemistry:
        missing = [p.name for p in people if not p.attributes.get("Primary Chemistry") or not p.attributes.get("Secondary Chemistry")]
        if missing: raise ValueError("Every participant requires Primary and Secondary Business Chemistry when Chemistry allocation is enabled")
    previous = {a.activity_id: a for a in (request.existing_allocation.activities if request.existing_allocation else [])}
    regenerate = set(request.regenerate_activity_ids or [a.id for a in request.configuration.activities])
    fixed, to_solve = [], []
    for activity in request.configuration.activities:
        if activity.id not in CORE_ACTIVITY_IDS: continue
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
    profile_diversity_cost = []
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

    # Offering always contributes. Chemistry profiles contribute only when the
    # user explicitly enables them; missing Chemistry never becomes a category.
    profile_attributes = [("L3 Offering", 3)]
    if request.configuration.include_business_chemistry:
        profile_attributes.extend((("Primary Chemistry", 3), ("Secondary Chemistry", 1)))
    for attribute, weight in profile_attributes:
        values = [str(p.attributes.get(attribute, "")).casefold().strip() for p in people]
        for i, j in combinations(range(n), 2):
            if not values[i] or values[i] != values[j]: continue
            for a_idx, activity in enumerate(to_solve):
                for g in range(len(sizes_by_activity[activity.id])):
                    z = model.NewBoolVar(f"profile_{attribute}_{a_idx}_{i}_{j}_{g}")
                    model.Add(z <= variables[a_idx, i, g]); model.Add(z <= variables[a_idx, j, g])
                    model.Add(z >= variables[a_idx, i, g] + variables[a_idx, j, g] - 1)
                    profile_diversity_cost.extend([z] * weight)

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
        university_weight * (10 * sum(university_cost) + sum(profile_diversity_cost))
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
            groups.append(Group(id=f"{activity.id}-{g}", name=f"Group {g+1}", participant_ids=members))
        solved.append(ActivityAllocation(activity_id=activity.id, activity_name=activity.name, groups=groups, locked=activity.locked))
    order = {a.id: i for i, a in enumerate(request.configuration.activities)}
    all_activities = sorted(fixed + solved, key=lambda x: order.get(x.activity_id, 99))
    all_activities.extend(_special_allocations(request, all_activities))
    return AllocationSnapshot(activities=all_activities, status=names[status], objective_value=solver.ObjectiveValue(), seed=request.configuration.seed)


def _special_allocations(request: OptimizeRequest, core: List[ActivityAllocation]) -> List[ActivityAllocation]:
    """Build fixed-purpose Week 2 allocations after the joint core solve."""
    if not request.faculty_members:
        return []  # Backward-compatible legacy workflow.
    if len(request.faculty_members) != 3: raise ValueError("Exactly three faculty members are required")
    people = request.participants; ids = [p.id for p in people]
    invalid_gender=[p.name for p in people if p.attributes.get("Gender") not in {"Male","Female"}]
    if invalid_gender: raise ValueError("Every new hire needs a valid Male or Female gender before hotel rooms can be assigned")
    pmap = {p.id: p for p in people}
    main = next((a for a in core if a.activity_id == "main"), None)
    if not main: raise ValueError("Main Groups are required before hotel rooms can be assigned")
    main_group = {pid: group.id for group in main.groups for pid in group.participant_ids}

    # Two balanced BUS teams. New hires and support members are balanced independently.
    bus_model=cp_model.CpModel(); bv={(i,t):bus_model.NewBoolVar(f"bus_{i}_{t}") for i in range(len(people)) for t in range(2)}
    for i in range(len(people)): bus_model.AddExactlyOne(bv[i,t] for t in range(2))
    bus_targets=[(len(people)+1)//2,len(people)//2]
    for t,target in enumerate(bus_targets): bus_model.Add(sum(bv[i,t] for i in range(len(people)))==target)
    bus_cost=[]
    bus_attributes = [("UniversityId",5),("Gender",4),("L3 Offering",3)]
    if request.configuration.include_business_chemistry:
        bus_attributes.extend((("Primary Chemistry",3),("Secondary Chemistry",1)))
    for attribute,weight in bus_attributes:
        values=[str((p.attributes.get(attribute) or (normalize_university(p.attributes.get("University")) if attribute=="UniversityId" else ""))).casefold().strip() for p in people]
        for value in {x for x in values if x}:
            members=[i for i,x in enumerate(values) if x==value]
            for t,target in enumerate(bus_targets):
                deviation=bus_model.NewIntVar(0,len(people)*len(people),f"bus_dev_{attribute}_{value}_{t}")
                bus_model.AddAbsEquality(deviation,sum(bv[i,t] for i in members)*len(people)-len(members)*target)
                bus_cost.extend([deviation]*weight)
    bus_model.Minimize(sum(bus_cost));bs=cp_model.CpSolver();bs.parameters.max_time_in_seconds=3;bs.Solve(bus_model)
    bus_members = [[ids[i] for i in range(len(people)) if bs.Value(bv[i,t])] for t in range(2)]
    for index, member in enumerate(request.support_members): bus_members[index % 2].append(member.id)
    bus = ActivityAllocation(activity_id="bus", activity_name="BUS Teams", groups=[
        Group(id=f"bus-{i}", name=f"BUS Team {i+1}", participant_ids=members)
        for i, members in enumerate(bus_members)
    ])

    # Balanced one-to-one reflection lists; offering matches are preferred without
    # allowing workload differences greater than one.
    reflection_model = cp_model.CpModel(); rv = {}
    low, extra = divmod(len(people), 3)
    targets = [low + (1 if i < extra else 0) for i in range(3)]
    for i, person in enumerate(people):
        for f in range(3): rv[i, f] = reflection_model.NewBoolVar(f"reflection_{i}_{f}")
        reflection_model.AddExactlyOne(rv[i, f] for f in range(3))
    for f, target in enumerate(targets): reflection_model.Add(sum(rv[i, f] for i in range(len(people))) == target)
    reflection_settings = request.configuration.reflection_settings
    if reflection_settings.enabled:
        selected = set(reflection_settings.selected_participant_ids)
        unknown = selected - set(ids)
        if unknown: raise ValueError("One or more selected My Reflections participants no longer exist")
        non_male = [p.name for p in people if p.id in selected and p.attributes.get("Gender") != "Male"]
        if non_male: raise ValueError("Friday prayer accommodation can only be selected from the displayed male participant checklist")
        slots_per_faculty, total_capacity = reflection_capacity(request.configuration, len(request.faculty_members))
        if len(selected) > total_capacity:
            shortfall = len(selected) - total_capacity
            raise ValueError(f"My Reflections pre-prayer capacity conflict: {len(selected)} participants selected, {total_capacity} slots available, shortfall {shortfall}")
        selected_indexes = [i for i,p in enumerate(people) if p.id in selected]
        for f in range(3): reflection_model.Add(sum(rv[i,f] for i in selected_indexes) <= slots_per_faculty)
    mismatch = []
    for i, person in enumerate(people):
        offering = (display_offering(person.attributes.get("L3 Offering")) or "").casefold()
        for f, faculty in enumerate(request.faculty_members):
            if offering and offering != (display_offering(faculty.offering) or "").casefold(): mismatch.append(rv[i, f])
    reflection_diversity=[]
    # MyReflection deliberately never considers gender. Faculty offering match
    # remains the dominant objective, followed by university and optional Chemistry.
    reflection_attributes = ["UniversityId"]
    if request.configuration.include_business_chemistry:
        reflection_attributes.extend(("Primary Chemistry", "Secondary Chemistry"))
    for attribute in reflection_attributes:
        values=[str((p.attributes.get(attribute) or (normalize_university(p.attributes.get("University")) if attribute=="UniversityId" else ""))).casefold().strip() for p in people]
        for i,j in combinations(range(len(people)),2):
            if not values[i] or values[i]!=values[j]: continue
            for f in range(3):
                together=reflection_model.NewBoolVar(f"reflection_div_{attribute}_{i}_{j}_{f}")
                reflection_model.Add(together<=rv[i,f]);reflection_model.Add(together<=rv[j,f]);reflection_model.Add(together>=rv[i,f]+rv[j,f]-1)
                reflection_diversity.append(together)
    reflection_model.Minimize(1000*sum(mismatch)+sum(reflection_diversity)); rs = cp_model.CpSolver(); rs.parameters.max_time_in_seconds = 5
    if rs.Solve(reflection_model) not in (cp_model.OPTIMAL, cp_model.FEASIBLE): raise ValueError("Faculty assignments could not be balanced")
    reflection = ActivityAllocation(activity_id="reflection", activity_name="MyReflection", groups=[
        Group(id=faculty.id, name=faculty.name, participant_ids=[ids[i] for i in range(len(people)) if rs.Value(rv[i, f])])
        for f, faculty in enumerate(request.faculty_members)
    ])
    reflection.sessions = schedule_reflection(reflection, request)

    # Maximum same-gender matching across different Main Groups. Unmatched people
    # become visible single rooms; no hard hotel rule is ever relaxed.
    hotel_groups = []; room_number = 1
    for gender in ("Male", "Female"):
        members = [p for p in people if p.attributes.get("Gender") == gender]
        hm = cp_model.CpModel(); edges = {}
        for i, j in combinations(range(len(members)), 2):
            if main_group[members[i].id] != main_group[members[j].id]: edges[i, j] = hm.NewBoolVar(f"room_{gender}_{i}_{j}")
        for i in range(len(members)): hm.Add(sum(v for (a, b), v in edges.items() if i in (a, b)) <= 1)
        preference=[]
        hotel_preference_attributes = ["UniversityId", "L3 Offering"]
        if request.configuration.include_business_chemistry:
            hotel_preference_attributes.extend(("Primary Chemistry", "Secondary Chemistry"))
        for (i,j),edge in edges.items():
            difference=sum(str(members[i].attributes.get(a,""))!=str(members[j].attributes.get(a,"")) for a in hotel_preference_attributes)
            preference.extend([edge]*difference)
        hm.Maximize(1000*sum(edges.values())+sum(preference)); hs = cp_model.CpSolver(); hs.Solve(hm)
        used = set()
        for (i, j), variable in edges.items():
            if hs.Value(variable):
                hotel_groups.append(Group(id=f"hotel-{room_number}", name=f"Room {room_number}", participant_ids=[members[i].id, members[j].id])); room_number += 1; used.update((i, j))
        for i, person in enumerate(members):
            if i not in used: hotel_groups.append(Group(id=f"hotel-{room_number}", name=f"Room {room_number} — Single Occupancy", participant_ids=[person.id])); room_number += 1
    hotel = ActivityAllocation(activity_id="hotel", activity_name="Hotel Room Pairing", groups=hotel_groups)
    return [bus, reflection, hotel]


def fallback(request: OptimizeRequest, fixed: Optional[List[ActivityAllocation]] = None) -> AllocationSnapshot:
    rng = random.Random(request.configuration.seed); ids = [p.id for p in request.participants]
    activities = list(fixed or []); existing = {a.activity_id for a in activities}
    for activity in request.configuration.activities:
        if activity.id in existing: continue
        shuffled = ids[:]; rng.shuffle(shuffled); sizes = group_sizes(len(ids), activity.mode, activity.value); groups=[]; start=0
        for g, size in enumerate(sizes):
            groups.append(Group(id=f"{activity.id}-{g}", name=f"Group {g+1}", participant_ids=shuffled[start:start+size])); start += size
        activities.append(ActivityAllocation(activity_id=activity.id, activity_name=activity.name, groups=groups))
    activities.extend(_special_allocations(request, activities))
    return AllocationSnapshot(activities=activities, status="FEASIBLE_FALLBACK", seed=request.configuration.seed)
