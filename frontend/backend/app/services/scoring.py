from collections import Counter, defaultdict
from itertools import combinations
from statistics import mean
from typing import Dict, List, Set, Tuple
from app.models import AllocationSnapshot, Configuration, Participant
from app.services.normalization import normalize_gender, normalize_university


def pair_sets(allocation: AllocationSnapshot) -> Dict[str, Set[Tuple[str, str]]]:
    result = {}
    for activity in allocation.activities:
        if activity.activity_id not in {"main", "quiz", "team", "sports"}: continue
        pairs = set()
        for group in activity.groups:
            pairs.update(tuple(sorted(pair)) for pair in combinations(group.participant_ids, 2))
        result[activity.activity_id] = pairs
    return result


def validate_allocation(participants: List[Participant], configuration: Configuration,
                        allocation: AllocationSnapshot) -> List[str]:
    expected = {p.id for p in participants}
    errors = []
    activity_map = {a.id: a for a in configuration.activities}
    for alloc in allocation.activities:
        ids = [pid for g in alloc.groups for pid in g.participant_ids]
        if alloc.activity_id == "bus":
            if not expected.issubset(set(ids)): errors.append("BUS Teams: one or more new hires are missing")
        elif set(ids) != expected:
            missing, extra = expected - set(ids), set(ids) - expected
            if missing: errors.append(f"{alloc.activity_name}: missing {sorted(missing)}")
            if extra: errors.append(f"{alloc.activity_name}: unknown {sorted(extra)}")
        duplicates = [pid for pid, count in Counter(ids).items() if count > 1]
        if duplicates: errors.append(f"{alloc.activity_name}: duplicate assignments {duplicates}")
        cfg = activity_map.get(alloc.activity_id)
        sizes = [len(g.participant_ids) for g in alloc.groups]
        if alloc.activity_id != "bus" and sizes and max(sizes) - min(sizes) > 1:
            errors.append(f"{alloc.activity_name}: group sizes are not balanced")
        if cfg and cfg.mode == "max_size" and sizes and max(sizes) > cfg.value:
            errors.append(f"{alloc.activity_name}: maximum group size {cfg.value} exceeded")
        if cfg and cfg.mode == "group_count" and len(sizes) != cfg.value:
            errors.append(f"{alloc.activity_name}: expected {cfg.value} groups")
    return errors


def score_allocation(participants: List[Participant], configuration: Configuration,
                     allocation: AllocationSnapshot) -> Dict:
    sets = pair_sets(allocation)
    counts = Counter(pair for pairs in sets.values() for pair in pairs)
    unique_pairs = len(counts)
    repeat_penalty = sum(max(0, count - 1) for count in counts.values())
    exposure = defaultdict(set)
    for a, b in counts:
        exposure[a].add(b); exposure[b].add(a)
    values = [len(exposure[p.id]) for p in participants]
    overlaps = {}
    for left, right in combinations(sets, 2):
        overlaps[f"{left}__{right}"] = len(sets[left] & sets[right])
    factor_scores = {}
    pmap = {p.id: p for p in participants}
    for factor in configuration.factors:
        if not factor.enabled or factor.strategy == "ignore": continue
        deviations = []
        overall = Counter(str(p.attributes.get(factor.source_column)) for p in participants
                          if p.attributes.get(factor.source_column) not in (None, ""))
        total = sum(overall.values()) or 1
        for activity in allocation.activities:
            if activity.activity_id not in sets: continue
            for group in activity.groups:
                known = [pmap[x].attributes.get(factor.source_column) for x in group.participant_ids]
                known = [str(x) for x in known if x not in (None, "")]
                if not known: continue
                local = Counter(known)
                deviations.extend(abs(local[k] / len(known) - v / total) for k, v in overall.items())
        factor_scores[factor.id] = round(max(0, 1 - (mean(deviations) if deviations else 0)), 4)
    university_duplicate_pairs = 0
    gender_deviation = 0.0
    known_genders = Counter(normalize_gender(p.attributes.get("Gender")) for p in participants)
    known_genders.pop(None, None)
    known_gender_total = sum(known_genders.values()) or 1
    activity_details = {}
    for activity in allocation.activities:
        if activity.activity_id not in sets: continue
        details = []
        for group in activity.groups:
            universities = [pmap[pid].attributes.get("UniversityId") or normalize_university(pmap[pid].attributes.get("University")) for pid in group.participant_ids]
            university_pairs = sum(1 for i, j in combinations(range(len(universities)), 2)
                                   if universities[i] and universities[i] == universities[j])
            university_duplicate_pairs += university_pairs
            gender_counts = Counter(normalize_gender(pmap[pid].attributes.get("Gender")) for pid in group.participant_ids)
            gender_counts.pop(None, None)
            if gender_counts:
                gender_deviation += sum(abs(gender_counts[g] / sum(gender_counts.values()) - total / known_gender_total)
                                        for g, total in known_genders.items())
            details.append({"group_id": group.id, "same_university_pairs": university_pairs,
                            "gender_counts": dict(gender_counts)})
        activity_details[activity.activity_id] = details
    encounters = sum(len(pairs) for pairs in sets.values())
    return {
        "total_participants": len(participants), "total_unique_pairs": unique_pairs,
        "total_teammate_encounters": encounters,
        "average_unique_teammates": round(mean(values), 2) if values else 0,
        "minimum_unique_teammates": min(values, default=0),
        "repeat_pairing_penalty": repeat_penalty,
        "normalized_unique_pair_rate": round(unique_pairs / encounters, 4) if encounters else 0,
        "pair_overlap": overlaps, "factor_balance_scores": factor_scores,
        "participant_exposure": {p.id: len(exposure[p.id]) for p in participants},
        "same_university_pairs": university_duplicate_pairs,
        "gender_balance_deviation": round(gender_deviation, 4),
        "activity_group_details": activity_details,
    }
