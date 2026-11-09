import math
import random
from collections import defaultdict
from itertools import combinations
from typing import Dict, List, Optional
from ortools.sat.python import cp_model
from app.models import (ActivityAllocation, AllocationSnapshot, Configuration,
                        Group, OptimizeRequest, Participant, ReflectionSession)
from app.services.normalization import (display_offering, normalize_gender, normalize_university,
    participant_university_category, validate_university_classifications)

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
    """Pre-break information only; this is never a limit on prayer-aware people."""
    settings = configuration.reflection_settings
    start = _minutes(settings.start_time, "My Reflections start time")
    deadline = _minutes(settings.prayer_deadline, "Friday prayer start time")
    resume = _minutes(settings.resume_time, "Post-prayer resume time")
    if resume <= deadline: raise ValueError("Post-prayer resume time must be after Friday prayer starts")
    if settings.end_time and _minutes(settings.end_time, "My Reflections final end time") <= start:
        raise ValueError("My Reflections final end time must be after its start time")
    slots = max(0, (deadline - start) // settings.session_duration_minutes)
    return slots, slots * faculty_count


def _reflection_plan(request: OptimizeRequest, activity=None, ignore_final_end=False, earliest=False, solver_status=None):
    """Joint optional-interval model: assignment and actual time are both feasible.

    Faculty workloads differ by at most one. Offering and existing profile
    preferences are soft; availability, duration, prayer breaks and final end
    are hard constraints. University category and gender never enter this model.
    """
    settings = request.configuration.reflection_settings
    faculty = request.faculty_members
    people = request.participants
    if len(faculty) != 3: raise ValueError("Exactly three faculty members are required for My Reflections")
    reflection_capacity(request.configuration, len(faculty))
    selected = set(settings.selected_participant_ids)
    if selected - {p.id for p in people}:
        raise ValueError("One or more selected My Reflections participants no longer exist")
    start = _minutes(settings.start_time, "My Reflections start time")
    prayer = _minutes(settings.prayer_deadline, "Friday prayer start time")
    resume = _minutes(settings.resume_time, "Post-prayer resume time")
    duration = settings.session_duration_minutes
    final = 1439 if ignore_final_end or not settings.end_time else _minutes(settings.end_time, "My Reflections final end time")
    model = cp_model.CpModel(); choices = {}; starts = {}; ends = {}; faculty_intervals = defaultdict(list)
    fixed = {pid: group.id for group in activity.groups for pid in group.participant_ids} if activity else None
    if fixed is not None:
        assigned = [pid for group in activity.groups for pid in group.participant_ids]
        if set(assigned) != {p.id for p in people} or len(assigned) != len(set(assigned)):
            raise ValueError("My Reflections appointments must assign every participant exactly once")
        if set(fixed.values()) - {f.id for f in faculty}:
            raise ValueError("My Reflections contains an unknown faculty assignment")
    if start + duration > final: return None
    for i, person in enumerate(people):
        starts[i] = model.NewIntVar(start, final-duration, f"appointment_start_{i}")
        ends[i] = model.NewIntVar(start+duration, final, f"appointment_end_{i}")
        model.Add(ends[i] == starts[i] + duration)
        for f, member in enumerate(faculty):
            choice = choices[i, f] = model.NewBoolVar(f"faculty_{i}_{f}")
            if fixed is not None: model.Add(choice == int(fixed[person.id] == member.id))
            interval = model.NewOptionalIntervalVar(starts[i], duration, ends[i], choice, f"appointment_{i}_{f}")
            faculty_intervals[f].append(interval)
            available_from = getattr(member, "available_from", None)
            available_until = getattr(member, "available_until", None)
            if available_from: model.Add(starts[i] >= _minutes(available_from, "Faculty availability start")).OnlyEnforceIf(choice)
            if available_until: model.Add(ends[i] <= _minutes(available_until, "Faculty availability end")).OnlyEnforceIf(choice)
            if person.id in selected or getattr(member, "prayer_unavailable", True):
                before = model.NewBoolVar(f"prayer_before_{i}_{f}")
                model.Add(ends[i] <= prayer).OnlyEnforceIf([choice, before])
                model.Add(starts[i] >= resume).OnlyEnforceIf([choice, before.Not()])
        model.AddExactlyOne(choices[i, f] for f in range(3))
    low, extra = divmod(len(people), 3)
    for f, member in enumerate(faculty):
        workload = sum(choices[i, f] for i in range(len(people)))
        if fixed is None:
            model.Add(workload >= low); model.Add(workload <= low + bool(extra))
        for index, unavailable in enumerate(getattr(member, "unavailable_intervals", [])):
            left = _minutes(unavailable.start_time, "Faculty unavailable interval start")
            right = _minutes(unavailable.end_time, "Faculty unavailable interval end")
            if right <= left: raise ValueError("Faculty unavailable interval end must be after its start")
            faculty_intervals[f].append(model.NewIntervalVar(left, right-left, right, f"unavailable_{f}_{index}"))
        model.AddNoOverlap(faculty_intervals[f])
        # Identical prayer status means appointment order is interchangeable.
        # Stable ordering removes interval symmetry without using gender.
        ordered = sorted(range(len(people)), key=lambda i: (people[i].name.casefold(), people[i].id))
        for index, i in enumerate(ordered):
            for j in ordered[index+1:]:
                if (people[i].id in selected) == (people[j].id in selected):
                    model.Add(starts[i] <= starts[j]).OnlyEnforceIf([choices[i,f], choices[j,f]])
    mismatch = []
    for i, person in enumerate(people):
        offering = (display_offering(person.attributes.get("L3 Offering")) or "").casefold()
        for f, member in enumerate(faculty):
            if offering and offering != (display_offering(member.offering) or "").casefold(): mismatch.append(choices[i,f])
    diversity = []
    attributes = ["UniversityId"]
    if request.configuration.include_business_chemistry:
        attributes.extend(("Primary Chemistry", "Secondary Chemistry"))
    for attribute in attributes:
        values = [(normalize_university(p.attributes.get("University"), request.configuration.custom_universities) or p.attributes.get("UniversityId")) if attribute == "UniversityId" else p.attributes.get(attribute) for p in people]
        for i,j in combinations(range(len(people)), 2):
            if not values[i] or values[i] != values[j]: continue
            for f in range(3):
                together = model.NewBoolVar(f"reflection_profile_{attribute}_{i}_{j}_{f}")
                model.Add(together <= choices[i,f]); model.Add(together <= choices[j,f])
                model.Add(together >= choices[i,f] + choices[j,f] - 1)
                diversity.append(together)
    # Preserve the administrator's prayer-aware selection as a priority for
    # available pre-break appointments, while allowing every overflow after it.
    prayer_late = []
    for i,person in enumerate(people):
        if person.id not in selected: continue
        late = model.NewBoolVar(f"selected_after_prayer_{i}")
        model.Add(ends[i] <= prayer).OnlyEnforceIf(late.Not())
        model.Add(starts[i] >= resume).OnlyEnforceIf(late)
        prayer_late.append(late)
    completion = model.NewIntVar(start, final, "reflection_completion")
    model.AddMaxEquality(completion, list(ends.values()))
    # A one-minute completion improvement outweighs all start-time tie-breaks;
    # offering still dominates the existing profile preference.
    timing_upper = max(1, len(people) * 1440 + 1)
    if earliest:
        model.Minimize(completion * timing_upper + sum(starts.values()))
    else:
        model.Minimize(((1000 * sum(mismatch) + sum(diversity)) * (len(prayer_late)+1) + sum(prayer_late)) * (1441 * timing_upper)
                       + completion * timing_upper + sum(starts.values()))
    solver = cp_model.CpSolver(); solver.parameters.max_time_in_seconds = 10
    solver.parameters.random_seed = request.configuration.seed; solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    if solver_status is not None: solver_status["optimal"] = status == cp_model.OPTIMAL
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE): return None
    sessions = []
    for i, person in enumerate(people):
        f = next(f for f in range(3) if solver.Value(choices[i,f]))
        participant_offering = (display_offering(person.attributes.get("L3 Offering")) or "").casefold()
        faculty_offering = (display_offering(faculty[f].offering) or "").casefold()
        left, right = solver.Value(starts[i]), solver.Value(ends[i])
        sessions.append(ReflectionSession(participant_id=person.id, faculty_id=faculty[f].id,
            start_time=_clock(left), end_time=_clock(right),
            offering_match=bool(participant_offering and participant_offering == faculty_offering),
            before_prayer=right <= prayer))
    return sorted(sessions, key=lambda session: (session.faculty_id, _session_minutes(session.start_time)))


def _session_minutes(value: str) -> int:
    from datetime import datetime
    try: return _minutes(value, "Appointment time")
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%I:%M %p")
            return parsed.hour * 60 + parsed.minute
        except ValueError: raise ValueError("Appointment time must be valid")


def _planned_reflection(request: OptimizeRequest, activity=None):
    sessions = _reflection_plan(request, activity)
    if sessions is not None: return sessions
    settings = request.configuration.reflection_settings
    if settings.end_time:
        status = {}
        earliest_sessions = _reflection_plan(request, activity, ignore_final_end=True, earliest=True, solver_status=status)
        if earliest_sessions:
            finish = max(_session_minutes(session.end_time) for session in earliest_sessions)
            label = "Earliest feasible completion" if status.get("optimal") else "A feasible completion"
            raise ValueError(f"My Reflections cannot fit by {_clock(_minutes(settings.end_time, 'Final end time'))}. "
                f"{label} is {_clock(finish)}; extend the final end time to {finish//60:02d}:{finish%60:02d} or later.")
    raise ValueError("My Reflections cannot fit within the configured same-day faculty availability. Start earlier, extend faculty availability within this day, or adjust the appointment duration.")


def schedule_reflection(activity: ActivityAllocation, request: OptimizeRequest) -> list[ReflectionSession]:
    if not request.configuration.reflection_settings.enabled: return []
    return _planned_reflection(request, activity)


def validate_reflection_sessions(activity: ActivityAllocation, request: OptimizeRequest) -> list[str]:
    """Validate saved/manual slots without changing any appointment or running CP-SAT."""
    errors = []; settings = request.configuration.reflection_settings
    if not settings.enabled and not activity.sessions: return []
    expected = {p.id for p in request.participants}
    ids = [session.participant_id for session in activity.sessions]
    if set(ids) != expected or len(ids) != len(set(ids)):
        errors.append("My Reflections appointments must assign every participant exactly once")
    faculty = {f.id: f for f in request.faculty_members}
    if len(faculty) != 3: errors.append("Exactly three faculty members are required for My Reflections")
    groups = {pid: group.id for group in activity.groups for pid in group.participant_ids}
    intervals = defaultdict(list)
    try:
        start = _minutes(settings.start_time, "My Reflections start time")
        prayer = _minutes(settings.prayer_deadline, "Friday prayer start time")
        resume = _minutes(settings.resume_time, "Post-prayer resume time")
        final = _minutes(settings.end_time, "My Reflections final end time") if settings.end_time else 1439
        selected = set(settings.selected_participant_ids)
        for session in activity.sessions:
            member = faculty.get(session.faculty_id)
            if not member or groups.get(session.participant_id) != session.faculty_id:
                errors.append("My Reflections appointment faculty does not match the saved assignment"); continue
            left, right = _session_minutes(session.start_time), _session_minutes(session.end_time)
            if right-left != settings.session_duration_minutes: errors.append("My Reflections appointment duration must match the configured duration")
            if settings.enabled and (left < start or right > final): errors.append("My Reflections appointment is outside the configured schedule")
            if settings.enabled and (session.participant_id in selected or member.prayer_unavailable) and left < resume and right > prayer:
                errors.append("My Reflections appointment crosses the protected Friday prayer break")
            if member.available_from and left < _minutes(member.available_from, "Faculty availability start"):
                errors.append("My Reflections appointment starts before faculty availability")
            if member.available_until and right > _minutes(member.available_until, "Faculty availability end"):
                errors.append("My Reflections appointment ends after faculty availability")
            for interval in member.unavailable_intervals:
                if left < _minutes(interval.end_time, "Faculty unavailable end") and right > _minutes(interval.start_time, "Faculty unavailable start"):
                    errors.append("My Reflections appointment overlaps faculty unavailability")
            intervals[session.faculty_id].append((left, right))
        for slots in intervals.values():
            ordered = sorted(slots)
            if any(right > following_left for (_, right),(following_left, _) in zip(ordered, ordered[1:])):
                errors.append("A faculty member cannot have overlapping My Reflections appointments")
    except ValueError as exc: errors.append(str(exc))
    return list(dict.fromkeys(errors))


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
    requested = set(request.regenerate_activity_ids or [a.id for a in request.configuration.activities])
    if request.faculty_members:
        if len(request.faculty_members) != 3: raise ValueError("Exactly three faculty members are required")
        if request.regenerate_activity_ids is None or requested & {"bus", "hotel"}:
            _validate_support(request)
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
    if any(activity.id in {"main", "quiz", "team"} for activity in to_solve):
        validate_university_classifications(people, request.configuration.custom_universities)
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
        locked_members = _locked_members(activity, sizes, ids, request.locked_assignments.get(activity.id, {}))
        for g,members in enumerate(locked_members):
            for pid in members: model.Add(variables[a_idx, ids.index(pid), g] == 1)
    university_cost = []
    university_category_cost = []
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
    universities = [normalize_university(p.attributes.get("University"), request.configuration.custom_universities) or p.attributes.get("UniversityId") for p in people]
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

    # University categories share the proportional-balance tier with gender.
    # Actual cohort proportions determine targets; equality is never a hard rule.
    university_categories = [participant_university_category(p, request.configuration.custom_universities) for p in people]
    for a_idx, activity in enumerate(to_solve):
        if activity.id not in {"main", "quiz", "team"}: continue
        for g, size in enumerate(sizes_by_activity[activity.id]):
            for category in sorted({value for value in university_categories if value}):
                members = [i for i,value in enumerate(university_categories) if value == category]
                deviation = model.NewIntVar(0, n*n, f"university_category_dev_{a_idx}_{g}_{category}")
                model.AddAbsEquality(deviation, sum(variables[a_idx,i,g] for i in members)*n - len(members)*size)
                university_category_cost.append(deviation)

    # Safe data-dependent scaling gives lexicographic weighted behavior:
    # one university-pair improvement outweighs every possible lower-priority
    # change, and one gender-deviation point outweighs every repeat change.
    repeat_upper = max(1, len(repeat_cost) * max(1, len(request.configuration.activities) - 1))
    gender_upper = max(1, (len(gender_cost) + len(university_category_cost)) * n * n)
    gender_weight = repeat_upper + 1
    university_weight = gender_upper * gender_weight + repeat_upper + 1
    model.Minimize(
        university_weight * (10 * sum(university_cost) + sum(profile_diversity_cost))
        + gender_weight * (sum(gender_cost) + sum(university_category_cost))
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


def _validate_support(request: OptimizeRequest):
    for member in request.support_members:
        if not member.name.strip() or member.gender not in {"Male", "Female"} or member.category not in {"Support Lead", "Analyst Support"}:
            raise ValueError("Every support member requires a name, gender (Male / Female), and support category (Support Lead / Analyst Support). Complete the missing information before generating allocations.")
    if sum(member.category == "Support Lead" for member in request.support_members) < 2:
        raise ValueError("At least two Support Leads are required so that each BUS Team has an experienced support member.")
    all_ids = [p.id for p in request.participants] + [f.id for f in request.faculty_members] + [s.id for s in request.support_members]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("New-hire, support and faculty IDs must be unique")


def _bus_allocation(request: OptimizeRequest, core: List[ActivityAllocation]):
    validate_university_classifications(request.participants, request.configuration.custom_universities)
    people = request.participants; ids = [p.id for p in people]; n = len(people)
    model = cp_model.CpModel(); variables = {(i,t): model.NewBoolVar(f"bus_{i}_{t}") for i in range(n) for t in range(2)}
    for i in range(n): model.AddExactlyOne(variables[i,t] for t in range(2))
    targets = [(n+1)//2, n//2]
    for t,target in enumerate(targets): model.Add(sum(variables[i,t] for i in range(n)) == target)
    costs = []
    attributes = [("UniversityId", 5), ("Gender", 4), ("L3 Offering", 3), ("University Category", 4)]
    if request.configuration.include_business_chemistry:
        attributes.extend((("Primary Chemistry", 3), ("Secondary Chemistry", 1)))
    for attribute,weight in attributes:
        if attribute == "University Category":
            values = [participant_university_category(p, request.configuration.custom_universities) for p in people]
        else:
            values = [str((normalize_university(p.attributes.get("University"), request.configuration.custom_universities) or p.attributes.get("UniversityId") or "") if attribute == "UniversityId" else (p.attributes.get(attribute) or "")).casefold().strip() for p in people]
        for value in sorted({x for x in values if x}):
            members = [i for i,x in enumerate(values) if x == value]
            for t,target in enumerate(targets):
                deviation = model.NewIntVar(0, n*n, f"bus_dev_{attribute}_{value}_{t}")
                model.AddAbsEquality(deviation, sum(variables[i,t] for i in members)*n-len(members)*target)
                costs.extend([deviation]*weight)
    # Preserve teammate-exposure preference without overruling the existing
    # university/profile/gender balance weights.
    repeat_costs = []
    pair_history = defaultdict(int)
    for activity in core:
        for group in activity.groups:
            for pair in combinations(sorted(group.participant_ids), 2): pair_history[pair] += 1
    for i,j in combinations(range(n), 2):
        previous = pair_history[tuple(sorted((ids[i],ids[j])))]
        if not previous: continue
        for t in range(2):
            together = model.NewBoolVar(f"bus_repeat_{i}_{j}_{t}")
            model.Add(together <= variables[i,t]); model.Add(together <= variables[j,t])
            model.Add(together >= variables[i,t]+variables[j,t]-1)
            repeat_costs.extend([together]*previous)
    model.Minimize((len(repeat_costs)+1)*sum(costs)+sum(repeat_costs))
    solver = cp_model.CpSolver(); solver.parameters.max_time_in_seconds = 3
    solver.parameters.random_seed = request.configuration.seed; solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE): raise ValueError("BUS Teams could not be balanced; try generating again with a longer solver time limit")
    members = [[ids[i] for i in range(n) if solver.Value(variables[i,t])] for t in range(2)]
    # Staff roles are balanced independently, while the lower-total bus receives
    # the next odd remainder. Two leads therefore always mean exactly one each.
    for role in ("Support Lead", "Analyst Support"):
        staff = sorted((m for m in request.support_members if m.category == role), key=lambda m: (m.name.casefold(), m.id))
        start_bus = 0 if len(members[0]) <= len(members[1]) else 1
        for index,member in enumerate(staff): members[(start_bus+index)%2].append(member.id)
    return ActivityAllocation(activity_id="bus", activity_name="BUS Teams", groups=[
        Group(id=f"bus-{t}", name=f"BUS Team {t+1}", participant_ids=group) for t,group in enumerate(members)])


def _reflection_allocation(request: OptimizeRequest):
    if request.configuration.reflection_settings.enabled:
        sessions = _planned_reflection(request)
        groups = [Group(id=f.id, name=f.name, participant_ids=[s.participant_id for s in sessions if s.faculty_id == f.id]) for f in request.faculty_members]
        return ActivityAllocation(activity_id="reflection", activity_name="My Reflections", groups=groups, sessions=sessions)
    # Legacy list-only mode retains offering matching, balanced workloads and
    # profile preferences, with no gender or university-category factor.
    people = request.participants; model = cp_model.CpModel(); variables = {}
    for i in range(len(people)):
        for f in range(3): variables[i,f] = model.NewBoolVar(f"reflection_{i}_{f}")
        model.AddExactlyOne(variables[i,f] for f in range(3))
    low, extra = divmod(len(people), 3)
    for f in range(3):
        model.Add(sum(variables[i,f] for i in range(len(people))) == low + (f < extra))
    mismatches = []
    for i,person in enumerate(people):
        offering = (display_offering(person.attributes.get("L3 Offering")) or "").casefold()
        for f,member in enumerate(request.faculty_members):
            if offering and offering != (display_offering(member.offering) or "").casefold(): mismatches.append(variables[i,f])
    diversity = []
    attributes = ["UniversityId"]
    if request.configuration.include_business_chemistry: attributes.extend(("Primary Chemistry", "Secondary Chemistry"))
    for attribute in attributes:
        values = [(normalize_university(p.attributes.get("University"), request.configuration.custom_universities) or p.attributes.get("UniversityId")) if attribute == "UniversityId" else p.attributes.get(attribute) for p in people]
        for i,j in combinations(range(len(people)), 2):
            if not values[i] or values[i] != values[j]: continue
            for f in range(3):
                together = model.NewBoolVar(f"reflection_div_{attribute}_{i}_{j}_{f}")
                model.Add(together <= variables[i,f]); model.Add(together <= variables[j,f])
                model.Add(together >= variables[i,f]+variables[j,f]-1); diversity.append(together)
    model.Minimize(1000*sum(mismatches)+sum(diversity)); solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5; solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = request.configuration.seed
    if solver.Solve(model) not in (cp_model.OPTIMAL, cp_model.FEASIBLE): raise ValueError("Faculty assignments could not be balanced")
    return ActivityAllocation(activity_id="reflection", activity_name="My Reflections", groups=[
        Group(id=member.id, name=member.name, participant_ids=[people[i].id for i in range(len(people)) if solver.Value(variables[i,f])])
        for f,member in enumerate(request.faculty_members)])


def _hotel_allocation(request: OptimizeRequest, main: ActivityAllocation):
    people = request.participants
    main_group = {pid:group.id for group in main.groups for pid in group.participant_ids}
    if any(p.attributes.get("Gender") not in {"Male", "Female"} for p in people):
        raise ValueError("Every new hire needs a valid Male or Female gender before hotel rooms can be assigned")
    if set(main_group) != {p.id for p in people}: raise ValueError("Main Groups must assign every new hire before hotel rooms can be allocated")
    rooms = []; warnings = []; staff_used = set()
    summary = {"total_rooms":0, "new_hire_shared_rooms":0, "new_hire_analyst_shared_rooms":0,
        "single_new_hire_rooms":0, "single_support_lead_rooms":0,
        "single_analyst_support_rooms":0, "single_faculty_rooms":0}
    def add_room(occupants, kind):
        number = len(rooms)+1
        name = f"Room {number}" + (" — Single Occupancy" if len(occupants) == 1 else "")
        rooms.append(Group(id=f"hotel-{number}", name=name, participant_ids=occupants)); summary[kind] += 1
    for gender in ("Male", "Female"):
        members = [p for p in people if p.attributes.get("Gender") == gender]
        model = cp_model.CpModel(); edges = {}
        for i,j in combinations(range(len(members)), 2):
            if main_group[members[i].id] != main_group[members[j].id]: edges[i,j] = model.NewBoolVar(f"room_{gender}_{i}_{j}")
        for i in range(len(members)): model.Add(sum(edge for (left,right),edge in edges.items() if i in (left,right)) <= 1)
        preferences = []
        attributes = ["UniversityId", "L3 Offering"]
        if request.configuration.include_business_chemistry: attributes.extend(("Primary Chemistry", "Secondary Chemistry"))
        for (i,j),edge in edges.items():
            differences = sum(str(members[i].attributes.get(a,"")) != str(members[j].attributes.get(a,"")) for a in attributes)
            preferences.extend([edge]*differences)
        # Maximum matching must dominate every profile tie-break even for larger
        # cohorts; do not create extra single rooms to improve a soft preference.
        model.Maximize((len(preferences)+1)*sum(edges.values())+sum(preferences))
        solver = cp_model.CpSolver(); solver.parameters.num_search_workers = 1
        if solver.Solve(model) not in (cp_model.OPTIMAL, cp_model.FEASIBLE): raise ValueError("Hotel room matching could not be completed")
        used = set()
        for (i,j),edge in edges.items():
            if solver.Value(edge):
                add_room([members[i].id, members[j].id], "new_hire_shared_rooms"); used.update((i,j))
        analysts = [s for s in request.support_members if s.category == "Analyst Support" and s.gender == gender]
        for i,person in enumerate(members):
            if i in used: continue
            analyst = next((s for s in analysts if s.id not in staff_used), None)
            if analyst:
                add_room([person.id, analyst.id], "new_hire_analyst_shared_rooms"); staff_used.add(analyst.id)
            else:
                add_room([person.id], "single_new_hire_rooms")
                warnings.append(f"{person.name} requires a single room: no unused same-gender Analyst Support member is available. Add an eligible Analyst Support member or reserve this single room.")
    for member in request.support_members:
        if member.id not in staff_used:
            add_room([member.id], "single_support_lead_rooms" if member.category == "Support Lead" else "single_analyst_support_rooms")
    for member in request.faculty_members: add_room([member.id], "single_faculty_rooms")
    summary["total_rooms"] = len(rooms)
    return ActivityAllocation(activity_id="hotel", activity_name="Hotel Rooms", groups=rooms, warnings=warnings, room_summary=summary)


def _special_allocations(request: OptimizeRequest, core: List[ActivityAllocation]) -> List[ActivityAllocation]:
    """Build only requested fixed-purpose allocations and preserve manual work."""
    if not request.faculty_members: return []  # Backward-compatible legacy workflow.
    if len(request.faculty_members) != 3: raise ValueError("Exactly three faculty members are required")
    previous = {a.activity_id:a for a in request.existing_allocation.activities} if request.existing_allocation else {}
    requested = set(request.regenerate_activity_ids) if request.regenerate_activity_ids is not None else None
    preserved = {activity_id:previous[activity_id] for activity_id in ("bus", "reflection", "hotel")
        if activity_id in previous and (previous[activity_id].locked or (requested is not None and activity_id not in requested))}
    if {"bus", "hotel"} - set(preserved): _validate_support(request)
    main = next((a for a in core if a.activity_id == "main"), None)
    if "hotel" not in preserved and not main: raise ValueError("Main Groups are required before hotel rooms can be assigned")
    result = []
    for activity_id, build in (("bus", lambda: _bus_allocation(request, core)),
                              ("reflection", lambda: _reflection_allocation(request)),
                              ("hotel", lambda: _hotel_allocation(request, main))):
        result.append(preserved[activity_id] if activity_id in preserved else build())
    return result


def _locked_members(activity, sizes, ids, locks):
    """Resolve the same explicit group locks for CP-SAT and its safe fallback."""
    group_indexes = {f"{activity.id}-{g}":g for g in range(len(sizes))}
    members = [[] for _ in sizes]
    for pid,group_id in locks.items():
        if pid not in ids: raise ValueError(f"Locked participant {pid} not found")
        if group_id not in group_indexes: raise ValueError(f"Invalid locked group {group_id}")
        g = group_indexes[group_id]; members[g].append(pid)
        if len(members[g]) > sizes[g]:
            raise ValueError(f"Configuration is infeasible: locked assignments exceed the capacity of {group_id}")
    return members


def fallback(request: OptimizeRequest, fixed: Optional[List[ActivityAllocation]] = None) -> AllocationSnapshot:
    """Seeded feasible grouping that preserves every hard assignment constraint."""
    rng = random.Random(request.configuration.seed); ids = [p.id for p in request.participants]
    if len(ids) != len(set(ids)): raise ValueError("Participant IDs must be unique")
    activities = list(fixed or []); existing = {a.activity_id for a in activities}
    configurations = {a.id:a for a in request.configuration.activities}
    for allocation in activities:
        assigned = [pid for group in allocation.groups for pid in group.participant_ids]
        if set(assigned) != set(ids) or len(assigned) != len(ids):
            raise ValueError(f"{allocation.activity_name}: preserved allocation must assign every participant exactly once")
        actual = {pid:group.id for group in allocation.groups for pid in group.participant_ids}
        for pid,group_id in request.locked_assignments.get(allocation.activity_id, {}).items():
            if pid not in actual: raise ValueError(f"Locked participant {pid} not found")
            if actual[pid] != group_id: raise ValueError("Configuration is infeasible with current locks")
        configured = configurations.get(allocation.activity_id)
        if configured and configured.mode == "max_size" and any(len(group.participant_ids) > configured.value for group in allocation.groups):
            raise ValueError(f"{allocation.activity_name}: preserved allocation exceeds the configured capacity")
        if configured and configured.mode == "group_count" and len(allocation.groups) != configured.value:
            raise ValueError(f"{allocation.activity_name}: preserved allocation has an incompatible group count")
    for activity in request.configuration.activities:
        if activity.id not in CORE_ACTIVITY_IDS or activity.id in existing: continue
        sizes = group_sizes(len(ids), activity.mode, activity.value)
        members = _locked_members(activity, sizes, ids, request.locked_assignments.get(activity.id, {}))
        locked = {pid for group in members for pid in group}
        remaining = [pid for pid in ids if pid not in locked]; rng.shuffle(remaining)
        offset = 0; groups = []
        for g,size in enumerate(sizes):
            needed = size-len(members[g]); occupants = members[g]+remaining[offset:offset+needed]; offset += needed
            groups.append(Group(id=f"{activity.id}-{g}", name=f"Group {g+1}", participant_ids=occupants))
        activities.append(ActivityAllocation(activity_id=activity.id, activity_name=activity.name, groups=groups, locked=activity.locked))
    activities.extend(_special_allocations(request, activities))
    return AllocationSnapshot(activities=activities, status="FEASIBLE_FALLBACK", seed=request.configuration.seed)
