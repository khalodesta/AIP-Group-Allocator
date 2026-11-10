"""Fictional regression cases for the bounded diversity priority adjustment."""
from collections import Counter

import pytest
from ortools.sat.python import cp_model

from app.models import ActivityAllocation, AllocationSnapshot, Group
from app.services import optimizer
from app.services.scoring import score_allocation, validate_allocation
from benchmarks.priority_adjustment import benchmark_requests


def request_for(name="balanced27", seconds=4):
    return dict(benchmark_requests(seconds))[name]


def core_request(name="balanced27"):
    # Quality regressions use the application's normal solve budget. Four-second
    # benchmark runs can exhaust presolve on shared Windows CI before any CP-SAT
    # incumbent exists; the separate benchmark keeps that short limit unchanged.
    request = request_for(name, seconds=20)
    request.faculty_members = []  # Exercise the joint model without unrelated scheduling.
    return request


@pytest.mark.parametrize("case", ["balanced27", "balanced30", "chemistry_disabled"])
def test_balanced_cohorts_balance_every_core_group(case):
    request = core_request(case)
    result = optimizer.optimize(request)
    assert result.status in {"OPTIMAL", "FEASIBLE"}
    assert not validate_allocation(request.participants, request.configuration, result)
    people = {p.id: p for p in request.participants}
    for activity in result.activities:
        for group in activity.groups:
            genders = Counter(people[pid].attributes["Gender"] for pid in group.participant_ids)
            assert abs(genders["Male"]-genders["Female"]) <= 1


@pytest.mark.parametrize("case,maximum", [("private_majority", 1), ("public_majority", 1)])
def test_minority_university_category_is_spread_across_groups(case, maximum):
    from app.services.normalization import participant_university_category
    request = core_request(case)
    result = optimizer.optimize(request)
    assert result.status in {"OPTIMAL", "FEASIBLE"}
    minority = "public" if case == "private_majority" else "private"
    ids = {p.id for p in request.participants if participant_university_category(p) == minority}
    for activity in result.activities:
        assert max(sum(pid in ids for pid in group.participant_ids) for group in activity.groups) <= maximum


def test_uneven_cohort_uses_available_gender_proportions_without_quotas():
    request = core_request("uneven30")
    result = optimizer.optimize(request)
    females = {p.id for p in request.participants if p.attributes["Gender"] == "Female"}
    assert result.status in {"OPTIMAL", "FEASIBLE"}
    for activity in result.activities:
        assert sorted(sum(pid in females for pid in g.participant_ids) for g in activity.groups) == [0, 1, 1, 1, 1]
    for person in request.participants:
        person.attributes["Gender"] = "Male"
    assert optimizer.optimize(request).status in {"OPTIMAL", "FEASIBLE"}


def test_extreme_mandatory_lock_remains_feasible():
    request = core_request("locked27")
    result = optimizer.optimize(request)
    assert result.status in {"OPTIMAL", "FEASIBLE"}
    assigned = {pid: g.id for a in result.activities if a.activity_id == "main" for g in a.groups for pid in g.participant_ids}
    assert all(assigned[pid] == group for pid, group in request.locked_assignments["main"].items())


def test_disabled_chemistry_has_no_effect_on_assignments():
    request = core_request("chemistry_disabled")
    request.participants = request.participants[:8]
    request.configuration.activities = request.configuration.activities[:1]
    request.configuration.activities[0].value = 4
    first = optimizer.optimize(request)
    for i, person in enumerate(request.participants):
        person.attributes["Primary Chemistry"] = "Pioneer" if i % 2 else "Driver"
        person.attributes["Secondary Chemistry"] = "Guardian"
    second = optimizer.optimize(request)
    assert first.status == second.status == "OPTIMAL"
    assert first.activities == second.activities
    assert first.objective_value == second.objective_value


def test_repeat_statistics_exclude_bus_sports_reflection_and_hotel():
    request = core_request()
    groups = [Group(id="g", name="Fictional Group", participant_ids=["P00", "P01"])]
    result = AllocationSnapshot(activities=[ActivityAllocation(activity_id=key, activity_name=key, groups=groups)
        for key in ("main", "quiz", "team", "bus", "sports", "reflection", "hotel")])
    assert score_allocation(request.participants, request.configuration, result)["repeat_pairing_penalty"] == 2


def test_bus_balances_hires_independently_of_support_gender_and_core_history():
    request = request_for("balanced27")
    first = optimizer._bus_allocation(request, [])
    people = {p.id: p for p in request.participants}
    for group in first.groups:
        genders = Counter(people[pid].attributes["Gender"] for pid in group.participant_ids if pid in people)
        assert abs(genders["Male"]-genders["Female"]) <= 1
        assert any(s.id in group.participant_ids and s.category == "Support Lead" for s in request.support_members)
    for member in request.support_members:
        member.gender = "Female"
    history = [ActivityAllocation(activity_id="main", activity_name="Main", groups=first.groups)]
    assert optimizer._bus_allocation(request, history) == first


def test_unknown_status_uses_honest_balanced_fallback_preserving_locks(monkeypatch):
    request = core_request("locked27")
    monkeypatch.setattr(cp_model.CpSolver, "Solve", lambda *_args, **_kwargs: cp_model.UNKNOWN)
    result = optimizer.optimize(request)
    assert result.status == "FEASIBLE_FALLBACK"
    assert result.objective_value is None
    assert not validate_allocation(request.participants, request.configuration, result)
    for activity in result.activities:
        assert any("heuristic" in warning and "not an optimized result" in warning for warning in activity.warnings)
        assigned = {pid: g.id for g in activity.groups for pid in g.participant_ids}
        assert all(assigned[pid] == group for pid, group in request.locked_assignments.get(activity.activity_id, {}).items())
    balanced = optimizer.optimize(core_request())
    people = {p.id: p for p in request.participants}
    for activity in balanced.activities:
        for group in activity.groups:
            genders = Counter(people[pid].attributes["Gender"] for pid in group.participant_ids)
            assert abs(genders["Male"]-genders["Female"]) <= 1


def test_invalid_model_is_not_disguised_as_fallback(monkeypatch):
    monkeypatch.setattr(cp_model.CpSolver, "Solve", lambda *_args, **_kwargs: cp_model.MODEL_INVALID)
    with pytest.raises(ValueError, match="model is invalid"):
        optimizer.optimize(core_request())


def test_all_groups_receive_offering_and_chemistry_costs_and_large_models_validate(monkeypatch):
    class Inspected(Exception):
        pass

    def inspect(_solver, model):
        assert model.Validate() == ""  # Includes signed 64-bit objective-domain checks.
        proto = model.Proto()
        coefficients = dict(zip(proto.objective.vars, proto.objective.coeffs))
        profiles = [(v.name, coefficients.get(i, 0)) for i, v in enumerate(proto.variables) if v.name.startswith("profile_")]
        assert profiles and all(weight > 0 for _, weight in profiles)
        primary = {weight for name, weight in profiles if "Primary Chemistry" in name}
        secondary = {weight for name, weight in profiles if "Secondary Chemistry" in name}
        assert primary == {3} and secondary == {1}
        raise Inspected

    monkeypatch.setattr(cp_model.CpSolver, "Solve", inspect)
    request = core_request("balanced30")
    request.participants += [p.model_copy(update={"id":p.id+"copy", "name":p.name+" Copy"}) for p in request.participants]
    with pytest.raises(Inspected):
        optimizer.optimize(request)
