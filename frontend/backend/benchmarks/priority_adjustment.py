"""Reproducible local priority benchmarks, using fictional records only.

Run from frontend/backend with ../../.venv/bin/python benchmarks/priority_adjustment.py
--output /tmp/after.json. --optimizer-path loads an exact saved pre-change module;
--fallback explicitly benchmarks the heuristic separately from CP-SAT quality.
"""
import argparse
import hashlib
import importlib.util
import json
import platform
import random
import sys
import time
from collections import Counter
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ortools
from app.models import Activity, AllocationRequest, Configuration, FacultyMember, OptimizeRequest, Participant, SupportMember
from app.services.normalization import normalize_gender, normalize_university, participant_university_category

TEAM_ACTIVITIES = {"main", "quiz", "team"}


def benchmark_requests(time_limit=4):
    """Same seed, data, settings and limits for every before/after run."""
    specifications = [
        ("balanced27", 27, 14, 20, True, (6, 6, 6)),
        ("balanced30", 30, 15, 15, True, (6, 6, 6)),
        ("uneven30", 30, 26, 24, True, (6, 6, 6)),
        ("private_majority", 30, 15, 27, True, (6, 6, 6)),
        ("public_majority", 27, 14, 3, True, (6, 6, 6)),
        ("chemistry_disabled", 27, 14, 20, False, (6, 6, 6)),
        ("different_sizes", 27, 14, 20, True, (5, 7, 4)),
        ("same_university", 30, 15, 0, True, (6, 6, 6)),
        ("locked27", 27, 14, 20, True, (6, 6, 6)),
    ]
    private = ["GUC", "AUC", "Misr International University", "The British University in Egypt", "Misr University for Science and Technology"]
    public = ["Cairo University", "Ain Shams University", "Alexandria University", "Capital-Helwan University"]
    offerings = ["Cyber", "Customer", "Engineering", "AI & Data", "ET&P"]
    chemistry = ["Pioneer", "Driver", "Guardian", "Integrator"]
    for name, n, males, private_count, enabled, sizes in specifications:
        rng = random.Random(42)
        genders = ["Male"] * males + ["Female"] * (n-males)
        rng.shuffle(genders)
        people = [Participant(id=f"P{i:02d}", name=f"Fictional Hire {i:02d}", attributes={
            "Gender": genders[i],
            "University": "Cairo University" if name == "same_university" else private[i % len(private)] if i < private_count else public[i % len(public)],
            "L3 Offering": offerings[(i*3+i//4) % len(offerings)],
            "Primary Chemistry": chemistry[(i*3+i//2) % 4],
            "Secondary Chemistry": chemistry[(i+1) % 4],
        }) for i in range(n)]
        config = Configuration(activities=[Activity(id=key, name=title, mode="max_size", value=size)
            for (key, title), size in zip((("main", "Main Groups"), ("quiz", "Quiz Night"), ("team", "Team Building")), sizes)],
            seed=42, time_limit_seconds=time_limit, include_business_chemistry=enabled)
        support = [SupportMember(id=f"S{i}", name=f"Fictional Support {i}", gender="Male" if i % 2 == 0 else "Female",
            category="Support Lead" if i < (3 if name == "different_sizes" else 2) else "Analyst Support") for i in range(5)]
        request = OptimizeRequest(participants=people, configuration=config, support_members=support,
            faculty_members=[FacultyMember(id=f"F{i}", name=f"Fictional Faculty {i}", offering=offering) for i, offering in enumerate(offerings[:3])])
        if name == "locked27":
            locked = [p.id for p in people if p.attributes["Gender"] == "Female"][:5]
            locked += [next(p.id for p in people if p.attributes["Gender"] == "Male")]
            request.locked_assignments = {"main": {pid: "main-0" for pid in locked}}
        yield name, request


def measurements(request, allocation):
    from app.main import structural_errors
    from app.services.scoring import validate_allocation
    people = {p.id: p for p in request.participants}
    overall_gender = Counter(normalize_gender(p.attributes.get("Gender")) for p in people.values())
    overall_category = Counter(participant_university_category(p, request.configuration.custom_universities) for p in people.values())
    n = len(people)
    groups = {}; pair_counts = Counter(); university_pairs = offering_pairs = primary_pairs = secondary_pairs = 0
    gender_deviation = category_deviation = worst_deviation = max_imbalance = 0
    offering_distinct = []
    for activity in allocation.activities:
        if activity.activity_id not in TEAM_ACTIVITIES | {"bus"}: continue
        details = []
        for group in activity.groups:
            ids = [pid for pid in group.participant_ids if pid in people]
            gender = Counter(normalize_gender(people[pid].attributes.get("Gender")) for pid in ids)
            category = Counter(participant_university_category(people[pid], request.configuration.custom_universities) for pid in ids)
            local_gender = [abs(gender[key]*n-total*len(ids)) for key,total in overall_gender.items() if key]
            gender_deviation += sum(local_gender)
            worst_deviation = max(worst_deviation, max(local_gender, default=0))
            max_imbalance = max(max_imbalance, abs(gender["male"]-gender["female"]))
            category_deviation += sum(abs(category[key]*n-total*len(ids)) for key,total in overall_category.items() if key)
            counts = {}
            for attribute in ("University", "L3 Offering", "Primary Chemistry", "Secondary Chemistry"):
                values = [normalize_university(people[pid].attributes.get(attribute), request.configuration.custom_universities)
                          if attribute == "University" else people[pid].attributes.get(attribute) for pid in ids]
                counts[attribute] = sum(count*(count-1)//2 for value,count in Counter(values).items() if value)
            university_pairs += counts["University"]; offering_pairs += counts["L3 Offering"]
            primary_pairs += counts["Primary Chemistry"]; secondary_pairs += counts["Secondary Chemistry"]
            distinct = len({people[pid].attributes.get("L3 Offering") for pid in ids})
            offering_distinct.append(distinct)
            details.append({"group":group.name, "new_hires":len(ids), "male":gender["male"], "female":gender["female"],
                "public":category["public"], "private":category["private"], "same_university_pairs":counts["University"],
                "same_offering_pairs":counts["L3 Offering"], "distinct_offerings":distinct,
                "same_primary_pairs":counts["Primary Chemistry"], "same_secondary_pairs":counts["Secondary Chemistry"]})
            if activity.activity_id in TEAM_ACTIVITIES: pair_counts.update(tuple(sorted(pair)) for pair in combinations(ids, 2))
        groups[activity.activity_id] = details
    violations = validate_allocation(request.participants, request.configuration, allocation)
    check = AllocationRequest(participants=request.participants,configuration=request.configuration,allocation=allocation,
                              faculty_members=request.faculty_members,support_members=request.support_members)
    violations += structural_errors(check)
    main = next((a for a in allocation.activities if a.activity_id == "main"),None)
    main_for = {pid:g.id for g in main.groups for pid in g.participant_ids} if main else {}
    support = {member.id:member for member in request.support_members}
    for activity in allocation.activities:
        if activity.activity_id == "hotel":
            for room in activity.groups:
                if len(room.participant_ids) == 2:
                    left,right = room.participant_ids
                    gender = lambda pid: people[pid].attributes["Gender"] if pid in people else support[pid].gender
                    if gender(left) != gender(right): violations.append("Automatic mixed-gender hotel room")
                    if left in people and right in people and main_for[left] == main_for[right]: violations.append("Automatic hotel roommates in same Main Group")
        if activity.activity_id == "bus":
            for role in ("Support Lead","Analyst Support"):
                counts = [sum(support[pid].category == role for pid in g.participant_ids if pid in support) for g in activity.groups]
                if max(counts)-min(counts)>1: violations.append("BUS support role imbalance")
    return {"per_group":groups,"maximum_gender_gap":max_imbalance,
        "scaled_gender_deviation":gender_deviation,"worst_scaled_gender_deviation":worst_deviation,
        "scaled_category_deviation":category_deviation,"same_university_pairs":university_pairs,
        "repeated_teammates_three_activities":sum(max(0,count-1) for count in pair_counts.values()),
        "same_offering_pairs":offering_pairs,"average_distinct_offerings":round(sum(offering_distinct)/len(offering_distinct),3),
        "same_primary_pairs":primary_pairs,"same_secondary_pairs":secondary_pairs,
        "chemistry_objective_enabled":request.configuration.include_business_chemistry,
        "hard_constraint_violations":sorted(set(violations))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--optimizer-path",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--time-limit",type=float,default=4)
    parser.add_argument("--cases",default="")
    parser.add_argument("--fallback",action="store_true")
    args = parser.parse_args()
    if args.optimizer_path:
        spec = importlib.util.spec_from_file_location("saved_priority_optimizer",args.optimizer_path)
        module = importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    else:
        from app.services import optimizer as module
    from ortools.sat.python import cp_model
    original = cp_model.CpSolver.Solve
    stages = []
    def tracked(solver,model,*extra,**kwargs):
        status = original(solver,model,*extra,**kwargs)
        variable = model.Proto().variables[0].name if model.Proto().variables else "empty"
        stages.append({"first_variable":variable,"status":solver.StatusName(status),"solver_seconds":round(solver.WallTime(),4)})
        return status
    cp_model.CpSolver.Solve = tracked
    report = {"python":platform.python_version(),"ortools":ortools.__version__,"time_limit_seconds":args.time_limit,
        "seed":42,"mode":"forced_heuristic" if args.fallback else "cp_sat","runs":[]}
    try:
        for name,request in benchmark_requests(args.time_limit):
            if args.cases and name not in args.cases.split(","): continue
            digest = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
            stages.clear();start = time.perf_counter()
            allocation = module.fallback(request) if args.fallback else module.optimize(request)
            elapsed = time.perf_counter()-start
            result = {"case":name,"input_sha256":digest,"status":allocation.status,"fallback_used":allocation.status=="FEASIBLE_FALLBACK",
                "seconds":round(elapsed,4),"solver_stages":list(stages),**measurements(request,allocation)}
            report["runs"].append(result)
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(report,indent=2)+"\n")
            print(json.dumps({"case":name,"status":result["status"],"seconds":result["seconds"],
                "main_male_female":[f"{g['male']}:{g['female']}" for g in result["per_group"]["main"]],
                "violations":len(result["hard_constraint_violations"])}),flush=True)
    finally:
        cp_model.CpSolver.Solve = original


if __name__ == "__main__":main()
