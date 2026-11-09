"""Fictional cohorts covering the integrated Week 2 optimizer policies."""
from collections import Counter
import pytest
from app.models import (Activity, ActivityAllocation, AllocationSnapshot, Configuration,
    CustomUniversity, FacultyMember, Group, OptimizeRequest, Participant,
    ReflectionSettings, SupportMember, TimeInterval)
from app.services.optimizer import (_bus_allocation, _hotel_allocation, _reflection_allocation,
    _session_minutes, _special_allocations, optimize, validate_reflection_sessions)


def cohort(count=6, genders=None):
    return [Participant(id=f"p{i}", name=f"Fictional Hire {i:02d}", attributes={
        "Gender": genders[i] if genders else "Male",
        "University": "Cairo University" if i % 2 else "German University in Cairo",
        "L3 Offering": ["Cyber", "Customer", "AI & Data"][i % 3]}) for i in range(count)]


def staff(leads=2, analysts=2, analyst_genders=None):
    return [SupportMember(id=f"s{i}", name=f"Fictional Support {i}",
        gender=(analyst_genders[i-leads] if analyst_genders and i >= leads else "Male"),
        category="Support Lead" if i < leads else "Analyst Support") for i in range(leads+analysts)]


def faculty():
    return [FacultyMember(id=f"f{i}", name=f"Fictional Faculty {i}", offering=offering)
        for i,offering in enumerate(("Cyber", "Customer", "AI & Data"))]


def main_groups(people):
    return ActivityAllocation(activity_id="main", activity_name="Main Groups", groups=[
        Group(id=f"main-{g}", name=f"Group {g+1}", participant_ids=[p.id for i,p in enumerate(people) if i % 2 == g])
        for g in range(2)])


def request(people=None, members=None, settings=None):
    return OptimizeRequest(participants=people or cohort(), faculty_members=faculty(),
        support_members=members if members is not None else staff(),
        configuration=Configuration(activities=[], time_limit_seconds=2,
            reflection_settings=settings or ReflectionSettings()))


@pytest.mark.parametrize("leads,analysts", [(2,2), (2,3), (3,2), (4,3)])
def test_bus_has_role_balanced_staff_and_two_balanced_new_hire_teams(leads, analysts):
    req = request(cohort(11), staff(leads, analysts))
    allocation = _bus_allocation(req, [main_groups(req.participants)])
    roles = {s.id:s.category for s in req.support_members}
    assert len(allocation.groups) == 2
    assigned = [pid for group in allocation.groups for pid in group.participant_ids]
    assert len(assigned) == len(set(assigned)) == 11+leads+analysts
    for role in ("Support Lead", "Analyst Support"):
        counts = [sum(roles.get(pid) == role for pid in g.participant_ids) for g in allocation.groups]
        assert max(counts)-min(counts) <= 1
        if role == "Support Lead": assert min(counts) >= 1
    hire_counts = [sum(pid.startswith("p") for pid in g.participant_ids) for g in allocation.groups]
    assert max(hire_counts)-min(hire_counts) <= 1
    assert all(not pid.startswith("f") for pid in assigned)


@pytest.mark.parametrize("leads", [0, 1])
def test_missing_support_leads_is_a_hard_error(leads):
    req = request(members=staff(leads, 3))
    with pytest.raises(ValueError, match="At least two Support Leads are required"):
        optimize(req)


def test_missing_legacy_support_gender_or_category_is_requested_without_guessing():
    req = request(members=[SupportMember(id="legacy", name="Fictional Legacy Support")])
    with pytest.raises(ValueError, match="Every support member requires"):
        optimize(req)


def test_categories_balance_proportionally_with_unique_universities_and_uneven_cohort():
    people = [Participant(id=f"p{i}", name=f"Fictional Hire {i}", attributes={
        "Gender":"Male", "University":f"Fictional University {i}",
        "University Category":"public" if i < 7 else "private"}) for i in range(27)]
    config = Configuration(activities=[Activity(id="main", name="Main Groups", mode="group_count", value=5)], time_limit_seconds=3)
    allocation = optimize(OptimizeRequest(participants=people, configuration=config))
    public = {p.id for p in people[:7]}
    counts = [sum(pid in public for pid in g.participant_ids) for g in allocation.activities[0].groups]
    assert sorted(counts) == [1,1,1,2,2]


def test_custom_aliases_share_exact_university_identity_despite_stale_ids():
    people = cohort(4)
    for index,name in enumerate(("Fictional College", "FC", "Cairo University", "German University in Cairo")):
        people[index].attributes.update({"University":name, "UniversityId":f"stale-{index}"})
    config = Configuration(activities=[Activity(id="main", name="Main Groups", mode="group_count", value=2)],
        custom_universities=[CustomUniversity(id="fictional-college", name="Fictional College", aliases=["FC"], category="other")], time_limit_seconds=3)
    allocation = optimize(OptimizeRequest(participants=people, configuration=config))
    group_for = {pid:g.id for g in allocation.activities[0].groups for pid in g.participant_ids}
    assert group_for["p0"] != group_for["p1"]


def prayer_settings(people, **changes):
    return ReflectionSettings(enabled=True, selected_participant_ids=[p.id for p in people],
        start_time="11:15", prayer_deadline="11:40", resume_time="13:00",
        session_duration_minutes=20).model_copy(update=changes)


def test_thirty_prayer_aware_people_continue_after_break_across_three_faculty():
    people = cohort(30, ["Male" if i % 2 else "Female" for i in range(30)])
    req = request(people, settings=prayer_settings(people))
    reflection = _reflection_allocation(req)
    assert len(reflection.sessions) == 30
    assert [len(group.participant_ids) for group in reflection.groups] == [10,10,10]
    assert validate_reflection_sessions(reflection, req) == []
    assert sum(session.before_prayer for session in reflection.sessions) == 3
    assert any(session.start_time == "1:00 PM" for session in reflection.sessions)
    assert max(_session_minutes(session.end_time) for session in reflection.sessions) == 16*60
    assert all(s.offering_match for s in reflection.sessions)


def test_selected_prayer_aware_people_keep_priority_for_available_pre_break_slots():
    people = cohort(9)
    req = request(people, settings=prayer_settings(people, selected_participant_ids=["p0", "p1", "p2"]))
    reflection = _reflection_allocation(req)
    by_person = {session.participant_id:session for session in reflection.sessions}
    assert all(by_person[pid].before_prayer for pid in ("p0", "p1", "p2"))
    assert validate_reflection_sessions(reflection, req) == []


def test_editable_prayer_resume_changes_actual_slots_and_fixed_end_reports_extension():
    people = cohort(6)
    req = request(people, settings=prayer_settings(people, resume_time="13:30"))
    reflection = _reflection_allocation(req)
    assert any(session.start_time == "1:30 PM" for session in reflection.sessions)
    fixed = req.model_copy(update={"configuration":req.configuration.model_copy(update={
        "reflection_settings":req.configuration.reflection_settings.model_copy(update={"end_time":"13:40"})})})
    with pytest.raises(ValueError, match="Earliest feasible completion is 1:50 PM; extend the final end time to 13:50"):
        _reflection_allocation(fixed)


def test_reflection_respects_faculty_availability_and_nonpraying_faculty_can_work_during_break():
    people = cohort(6)
    settings = prayer_settings(people, selected_participant_ids=["p0"])
    req = request(people, settings=settings)
    req.faculty_members[0].prayer_unavailable = False
    req.faculty_members[0].unavailable_intervals = [TimeInterval(start_time="11:15", end_time="11:35")]
    req.faculty_members[1].available_from = "13:20"
    reflection = _reflection_allocation(req)
    assert validate_reflection_sessions(reflection, req) == []
    assert all(_session_minutes(s.start_time) >= 13*60+20 for s in reflection.sessions if s.faculty_id == "f1")
    assert any(_session_minutes(s.start_time) < 13*60 and _session_minutes(s.end_time) > 11*60+40
        for s in reflection.sessions if s.faculty_id == "f0" and s.participant_id != "p0")


def test_reflection_assignment_and_times_are_independent_of_gender_and_category():
    people = cohort(6)
    req = request(people, settings=prayer_settings(people))
    first = _reflection_allocation(req)
    other_people = [p.model_copy(update={"attributes":{**p.attributes, "Gender":"Female", "University Category":"international"}}) for p in people]
    second = _reflection_allocation(req.model_copy(update={"participants":other_people}))
    assert first == second


def test_manual_reflection_validation_catches_partial_overlap_break_and_duration():
    people = cohort(6)
    req = request(people, settings=prayer_settings(people))
    reflection = _reflection_allocation(req)
    sessions = [s for s in reflection.sessions if s.faculty_id == "f0"]
    sessions[1].start_time = "11:25 AM"; sessions[1].end_time = "11:45 AM"
    errors = validate_reflection_sessions(reflection, req)
    assert any("overlapping" in error for error in errors)
    assert any("protected Friday prayer break" in error for error in errors)
    sessions[1].end_time = "11:50 AM"
    assert any("duration" in error for error in validate_reflection_sessions(reflection, req))


@pytest.mark.parametrize("genders,analyst_genders,expected_shared", [
    (["Male"]*6, ["Male","Female"], 0),
    (["Male"]*5, ["Male","Female"], 1),
    (["Male"]*3+["Female"]*3, ["Male","Female"], 2),
    (["Male"]*3+["Female"]*3, ["Male","Male"], 1),
])
def test_hotel_full_manifest_parity_analyst_exception_and_exact_counts(genders, analyst_genders, expected_shared):
    people = cohort(len(genders), genders)
    req = request(people, members=staff(2, 2, analyst_genders))
    main = main_groups(people)
    hotel = _hotel_allocation(req, main)
    assigned = [pid for room in hotel.groups for pid in room.participant_ids]
    all_ids = {p.id for p in people} | {s.id for s in req.support_members} | {f.id for f in req.faculty_members}
    assert len(assigned) == len(set(assigned)) == len(all_ids)
    assert set(assigned) == all_ids
    assert hotel.room_summary["new_hire_analyst_shared_rooms"] == expected_shared
    assert hotel.room_summary["single_support_lead_rooms"] == 2
    assert hotel.room_summary["single_faculty_rooms"] == 3
    assert hotel.room_summary["total_rooms"] == len(hotel.groups)
    assert sum(value for key,value in hotel.room_summary.items() if key != "total_rooms") == len(hotel.groups)
    staff_map = {s.id:s for s in req.support_members}
    hire_map = {p.id:p for p in people}
    main_for = {pid:g.id for g in main.groups for pid in g.participant_ids}
    for room in hotel.groups:
        if any(pid.startswith("f") or (pid in staff_map and staff_map[pid].category == "Support Lead") for pid in room.participant_ids):
            assert len(room.participant_ids) == 1
        if len(room.participant_ids) == 2:
            recorded_gender = [hire_map[pid].attributes["Gender"] if pid in hire_map else staff_map[pid].gender for pid in room.participant_ids]
            assert len(set(recorded_gender)) == 1
            if all(pid in hire_map for pid in room.participant_ids):
                assert main_for[room.participant_ids[0]] != main_for[room.participant_ids[1]]
    assert len(hotel.warnings) == hotel.room_summary["single_new_hire_rooms"]


def test_regenerating_one_activity_preserves_all_existing_special_manual_allocations():
    req = request()
    main = main_groups(req.participants)
    originals = _special_allocations(req, [main])
    req.existing_allocation = AllocationSnapshot(activities=[main, *originals])
    req.regenerate_activity_ids = ["main"]
    preserved = _special_allocations(req, [main])
    assert preserved == originals
    assert all(new is old for new,old in zip(preserved, originals))


def test_fallback_preserves_locked_members_and_exact_group_capacities():
    from app.services.optimizer import fallback
    people = cohort(7)
    config = Configuration(activities=[Activity(id="main", name="Main Groups", mode="max_size", value=3)])
    req = OptimizeRequest(participants=people, configuration=config,
        locked_assignments={"main":{"p0":"main-2", "p1":"main-0", "p2":"main-0", "p3":"main-1"}})
    result = fallback(req)
    assigned = {pid:g.id for g in result.activities[0].groups for pid in g.participant_ids}
    assert all(assigned[pid] == group for pid,group in req.locked_assignments["main"].items())
    assert [len(g.participant_ids) for g in result.activities[0].groups] == [3,2,2]
    assert set(assigned) == {p.id for p in people}


@pytest.mark.parametrize("locks,expected_error", [
    ({"unknown":"main-0"}, "Locked participant unknown not found"),
    ({"p0":"main-9"}, "Invalid locked group"),
    ({"p0":"main--1"}, "Invalid locked group"),
    ({"p0":"quiz-0"}, "Invalid locked group"),
    ({"p0":"main-0", "p1":"main-0", "p2":"main-0", "p3":"main-0"}, "exceed the capacity"),
])
def test_cp_and_fallback_reject_invalid_or_infeasible_locks(locks, expected_error):
    from app.services.optimizer import fallback
    config = Configuration(activities=[Activity(id="main", name="Main Groups", mode="max_size", value=3)])
    req = OptimizeRequest(participants=cohort(), configuration=config, locked_assignments={"main":locks})
    for allocator in (fallback, optimize):
        with pytest.raises(ValueError, match=expected_error): allocator(req)


def test_fallback_rejects_preserved_allocations_conflicting_with_explicit_locks():
    from app.services.optimizer import fallback
    people = cohort()
    config = Configuration(activities=[Activity(id="main", name="Main Groups", mode="group_count", value=2)])
    req = OptimizeRequest(participants=people, configuration=config, locked_assignments={"main":{"p0":"main-1"}})
    with pytest.raises(ValueError, match="infeasible with current locks"):
        fallback(req, [main_groups(people)])


def test_reflection_does_not_wrap_a_midnight_end_into_a_noon_appointment():
    people = cohort(3)
    settings = prayer_settings(people, start_time="23:40")
    req = request(people, settings=settings)
    with pytest.raises(ValueError, match="same-day faculty availability. Start earlier"):
        _reflection_allocation(req)
    req.configuration.reflection_settings.start_time = "23:39"
    reflection = _reflection_allocation(req)
    assert all(session.start_time == "11:39 PM" and session.end_time == "11:59 PM" for session in reflection.sessions)
    assert validate_reflection_sessions(reflection, req) == []
