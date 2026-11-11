"""Route-level regression checks using fictional cohorts and staff only."""
import copy
import io
from datetime import datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from pypdf import PdfReader

from app.main import app


def pdf_text(data):
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)


@pytest.fixture(scope="module")
def generated():
    universities = ["Cairo University", "Ain Shams University", "German University in Cairo", "American University in Cairo"]
    offerings = ["Cyber", "Customer", "Engineering"]
    payload = {
        "participants": [{"id": f"P{i}", "name": f"Integration Hire {i}", "attributes": {
            "Gender": "Male" if i < 7 else "Female", "University": universities[i % 4],
            "L3 Offering": offerings[i % 3]}} for i in range(12)],
        "faculty_members": [{"id": f"F{i}", "name": f"Integration Faculty {i}", "offering": offering}
                            for i, offering in enumerate(offerings)],
        "support_members": [
            {"id": "S0", "name": "Integration Lead One", "gender": "Male", "category": "Support Lead"},
            {"id": "S1", "name": "Integration Lead Two", "gender": "Female", "category": "Support Lead"},
            {"id": "S2", "name": "Integration Analyst One", "gender": "Male", "category": "Analyst Support"},
            {"id": "S3", "name": "Integration Analyst Two", "gender": "Female", "category": "Analyst Support"},
        ],
        "configuration": {
            "activities": [{"id": key, "name": title, "mode": "max_size", "value": 4}
                           for key, title in [("main", "Main Groups"), ("quiz", "Quiz Night"), ("team", "Team Building")]],
            "time_limit_seconds": 2,
            "reflection_settings": {"enabled": True, "start_time": "11:15", "prayer_deadline": "11:40",
                                    "resume_time": "13:10", "session_duration_minutes": 20,
                                    "selected_participant_ids": [f"P{i}" for i in range(7)]},
        },
    }
    response = TestClient(app).post("/api/optimize", json=payload)
    assert response.status_code == 200, response.text
    return {**payload, "allocation": response.json()["allocation"]}


def test_all_six_allocations_validate_and_export_together(generated):
    client = TestClient(app)
    by_id = {activity["activity_id"]: activity for activity in generated["allocation"]["activities"]}
    assert set(by_id) == {"main", "quiz", "team", "bus", "reflection", "hotel"}
    validation = client.post("/api/allocations/validate", json=generated)
    assert validation.status_code == 200 and validation.json()["valid"], validation.text
    hotel = by_id["hotel"]
    occupants = [pid for room in hotel["groups"] for pid in room["participant_ids"]]
    expected_ids = {person["id"] for key in ("participants", "faculty_members", "support_members") for person in generated[key]}
    assert set(occupants) == expected_ids and len(occupants) == len(expected_ids)
    assert hotel["room_summary"]["total_rooms"] == len(hotel["groups"]) == 12
    assert hotel["room_summary"]["new_hire_analyst_shared_rooms"] == 2
    reflection = by_id["reflection"]
    assert reflection["activity_name"] == "My Reflections"
    assert len(reflection["groups"]) == 3 and len(reflection["sessions"]) == 12
    starts = [datetime.strptime(session["start_time"], "%I:%M %p") for session in reflection["sessions"]]
    assert any(start.hour == 11 and start.minute == 15 for start in starts)
    assert any(start.hour == 13 and start.minute == 10 for start in starts)
    assert len({(session["faculty_id"], session["start_time"]) for session in reflection["sessions"]}) == 12

    public = client.post("/api/export/pdf", json=generated)
    assert public.status_code == 200
    public_text = pdf_text(public.content)
    assert "My Reflections" in public_text
    assert "HOTEL" not in public_text and "Room 1" not in public_text
    assert "Cairo University" not in public_text and "Female" not in public_text
    private = client.post("/api/export/hotel-pdf", json=generated)
    assert private.status_code == 200
    private_text = pdf_text(private.content)
    assert "Total rooms required: 12" in private_text
    assert "PRIVATE HOTEL ROOM MANIFEST" in private_text
    for person in [*generated["participants"], *generated["faculty_members"], *generated["support_members"]]:
        assert person["name"] in private_text
    for activity_id in by_id:
        individual = client.post(f"/api/export/pdf/{activity_id}", json=generated)
        assert individual.status_code == 200, (activity_id, individual.text)
    for path in ("/api/export/editable", "/api/export"):
        excel = client.post(path, json=generated)
        assert excel.status_code == 200, excel.text
        book = load_workbook(io.BytesIO(excel.content))
        assert {"Main Groups", "Quiz Night", "Team Building", "BUS Teams", "My Reflections", "Hotel Rooms"}.issubset(book.sheetnames)
    editable = client.post("/api/export/editable", json=generated)
    upload = client.post("/api/upload/support", files={"file": ("fictional-staff.xlsx", editable.content)})
    assert upload.status_code == 200
    assert upload.json()["support_members"] == generated["support_members"]


@pytest.mark.parametrize("use_swap", [False, True])
def test_bus_edit_cannot_remove_only_lead_by_move_or_analyst_swap(generated, use_swap):
    bus = next(activity for activity in generated["allocation"]["activities"] if activity["activity_id"] == "bus")
    source = next(group for group in bus["groups"] if "S0" in group["participant_ids"])
    target = next(group for group in bus["groups"] if group["id"] != source["id"])
    edit = {**generated, "activity_id": "bus", "participant_id": "S0", "target_group_id": target["id"], "allow_override": True}
    if use_swap:
        analyst = next(pid for pid in target["participant_ids"] if pid in {"S2", "S3"})
        edit["swap_with_id"] = analyst
    response = TestClient(app).post("/api/allocations/edit", json=edit)
    assert response.status_code == 422 and "at least one Support Lead" in response.text
    if use_swap:
        response = TestClient(app).post("/api/allocations/swap", json={
            **generated, "activity_id": "bus", "participant_a": "S0", "participant_b": analyst})
        assert response.status_code == 422 and "at least one Support Lead" in response.text


@pytest.mark.parametrize("member_id", ["S0", "F0"])
def test_hotel_manual_edit_preserves_lead_and_faculty_single_rooms(generated, member_id):
    hotel = next(activity for activity in generated["allocation"]["activities"] if activity["activity_id"] == "hotel")
    target = next(room for room in hotel["groups"] if len(room["participant_ids"]) == 2)
    response = TestClient(app).post("/api/allocations/edit", json={
        **generated, "activity_id": "hotel", "participant_id": member_id,
        "target_group_id": target["id"], "allow_override": True})
    assert response.status_code == 422 and "single-occupancy" in response.text


def test_hotel_valid_staff_swap_is_unique_and_does_not_regenerate_other_activities(generated):
    hotel = next(activity for activity in generated["allocation"]["activities"] if activity["activity_id"] == "hotel")
    analyst_room = next(room for room in hotel["groups"] if "S2" in room["participant_ids"])
    hires = {person["id"]: person for person in generated["participants"]}
    target = next(room for room in hotel["groups"] if room["id"] != analyst_room["id"]
                  and len(room["participant_ids"]) == 2 and all(pid in hires and hires[pid]["attributes"]["Gender"] == "Male" for pid in room["participant_ids"]))
    response = TestClient(app).post("/api/allocations/edit", json={
        **generated, "activity_id": "hotel", "participant_id": "S2", "target_group_id": target["id"],
        "swap_with_id": target["participant_ids"][0], "allow_override": True})
    assert response.status_code == 200, response.text
    after = response.json()["allocation"]
    for old, new in zip(generated["allocation"]["activities"], after["activities"]):
        if old["activity_id"] != "hotel":
            assert old == new
    validation = TestClient(app).post("/api/allocations/validate", json={**generated, "allocation": after})
    assert validation.json()["valid"], validation.text


def test_two_person_capacity_is_enforced_even_with_manual_policy_approval(generated):
    payload = copy.deepcopy(generated)
    payload["configuration"]["allow_accommodation_policy_overrides"] = True
    hotel = next(activity for activity in payload["allocation"]["activities"] if activity["activity_id"] == "hotel")
    hires = {person["id"]: person for person in payload["participants"]}
    rooms = [room for room in hotel["groups"] if len(room["participant_ids"]) == 2
             and all(pid in hires and hires[pid]["attributes"]["Gender"] == "Male" for pid in room["participant_ids"])]
    assert len(rooms) >= 2
    response = TestClient(app).post("/api/allocations/edit", json={
        **payload, "activity_id": "hotel", "participant_id": rooms[0]["participant_ids"][0],
        "target_group_id": rooms[1]["id"], "allow_override": True})
    assert response.status_code == 422
    assert "maximum capacity of two" in response.text


def test_hotel_duplicates_missing_staff_and_empty_rooms_are_invalid(generated):
    for mutation in ("duplicate", "missing", "empty"):
        payload = copy.deepcopy(generated)
        hotel = next(activity for activity in payload["allocation"]["activities"] if activity["activity_id"] == "hotel")
        if mutation == "duplicate":
            hotel["groups"][0]["participant_ids"].append("S0")
        elif mutation == "missing":
            hotel["groups"] = [room for room in hotel["groups"] if "F0" not in room["participant_ids"]]
        else:
            hotel["groups"].append({"id": "empty-room", "name": "Empty Room", "participant_ids": []})
        validation = TestClient(app).post("/api/allocations/validate", json=payload)
        assert validation.status_code == 200 and not validation.json()["valid"], (mutation, validation.text)
        for path in ("/api/export/hotel-pdf", "/api/export/editable", "/api/export"):
            response = TestClient(app).post(path, json=payload)
            assert response.status_code == 422, (mutation, path, response.status_code)


def test_analyst_can_share_with_only_one_new_hire_even_with_capacity_override(generated):
    payload=copy.deepcopy(generated)
    payload["configuration"]["allow_accommodation_policy_overrides"]=True
    hotel=next(activity for activity in payload["allocation"]["activities"] if activity["activity_id"]=="hotel")
    analyst_room=next(room for room in hotel["groups"] if "S2" in room["participant_ids"])
    hires={person["id"] for person in payload["participants"]}
    source=next(room for room in hotel["groups"] if room["id"]!=analyst_room["id"] and any(pid in hires for pid in room["participant_ids"]))
    person=next(pid for pid in source["participant_ids"] if pid in hires)
    response=TestClient(app).post("/api/allocations/edit",json={**payload,"activity_id":"hotel",
        "participant_id":person,"target_group_id":analyst_room["id"],"allow_override":True})
    assert response.status_code==422 and "only with one new hire" in response.text


def test_hotel_exports_reject_unapproved_mixed_gender_rooms(generated):
    payload = copy.deepcopy(generated)
    hotel = next(activity for activity in payload["allocation"]["activities"] if activity["activity_id"] == "hotel")
    hires = {person["id"]: person for person in payload["participants"]}
    male = next(room for room in hotel["groups"] if len(room["participant_ids"]) == 2 and all(pid in hires and hires[pid]["attributes"]["Gender"] == "Male" for pid in room["participant_ids"]))
    female = next(room for room in hotel["groups"] if len(room["participant_ids"]) == 2 and all(pid in hires and hires[pid]["attributes"]["Gender"] == "Female" for pid in room["participant_ids"]))
    male["participant_ids"][0], female["participant_ids"][0] = female["participant_ids"][0], male["participant_ids"][0]
    for path in ("/api/export/hotel-pdf", "/api/export/editable", "/api/export"):
        response = TestClient(app).post(path, json=payload)
        assert response.status_code == 422, (path, response.status_code)


def test_support_upload_keeps_legacy_missing_values_and_generation_requests_them(generated):
    output = io.BytesIO()
    pd.DataFrame([{"Name": "Fictional Unspecified Support"}]).to_excel(output, index=False)
    client = TestClient(app)
    upload = client.post("/api/upload/support", files={"file": ("fictional-legacy.xlsx", output.getvalue())})
    assert upload.status_code == 200
    member = upload.json()["support_members"][0]
    assert member["gender"] is None and member["category"] is None
    response = client.post("/api/optimize", json={**generated, "support_members": [*generated["support_members"], member]})
    assert response.status_code == 422 and "missing information" in response.text


def test_unknown_classification_blocks_generation_and_reusable_aliases_resolve():
    payload = {"participants": [{"id": f"P{i}", "name": f"Fictional Alias Hire {i}", "attributes": {
        "Gender": "Male", "University": "Fictional College" if i % 2 else "FC"}} for i in range(4)],
        "configuration": {"activities": [{"id": "main", "name": "Main Groups", "mode": "group_count", "value": 2}], "time_limit_seconds": 1}}
    client = TestClient(app)
    unknown = client.post("/api/optimize", json=payload)
    assert unknown.status_code == 422 and "University classification required" in unknown.text
    payload["configuration"]["custom_universities"] = [{"id": "fictional-college", "name": "Fictional College", "aliases": ["FC"], "category": "public"}]
    classified = client.post("/api/optimize", json=payload)
    assert classified.status_code == 200, classified.text
    result = classified.json()
    assert result["metrics"]["same_university_pairs"] == 2
    assert result["metrics"]["factor_balance_scores"]["university_category"] == 1
    assert all(group["university_category_counts"] == {"public": 2}
               for group in result["metrics"]["activity_group_details"]["main"])


def test_official_nonbinary_university_requires_administrator_binary_confirmation():
    """An official Ahleya category is never silently reclassified as private."""
    from app.services.normalization import resolve_university
    institution = resolve_university("Helwan National University")
    payload = {"participants": [{"id": f"P{i}", "name": f"Fictional National Graduate {i}", "attributes": {
        "Gender": "Male", "University": "Helwan National University"}} for i in range(4)],
        "configuration": {"activities": [{"id": "main", "name": "Main Groups", "mode": "group_count", "value": 2}], "time_limit_seconds": 1}}
    client = TestClient(app)
    unresolved = client.post("/api/optimize", json=payload)
    assert unresolved.status_code == 422 and "University classification required" in unresolved.text
    payload["configuration"]["custom_universities"] = [{
        "id": institution["id"], "name": institution["official_english_name"], "aliases": [], "category": "public"}]
    confirmed = client.post("/api/optimize", json=payload)
    assert confirmed.status_code == 200, confirmed.text
    assert all(group["university_category_counts"] == {"public": 2}
               for group in confirmed.json()["metrics"]["activity_group_details"]["main"])
    payload["configuration"]["custom_universities"][0]["category"] = "national"
    unsupported = client.post("/api/optimize", json=payload)
    assert unsupported.status_code == 422


def test_prayer_selection_rejects_female_ids_in_generate_and_saved_allocations(generated):
    payload = copy.deepcopy(generated)
    payload["configuration"]["reflection_settings"]["selected_participant_ids"].append("P8")
    client = TestClient(app)
    response = client.post("/api/optimize", json=payload)
    assert response.status_code == 422 and "male" in response.text.casefold()
    validation = client.post("/api/allocations/validate", json=payload)
    assert validation.status_code == 200 and not validation.json()["valid"]
    assert "male" in str(validation.json()["errors"]).casefold()
    for path in ("/api/export/pdf", "/api/export/editable"):
        exported = client.post(path, json=payload)
        assert exported.status_code == 422


def minutes(value):
    time = datetime.strptime(value, "%I:%M %p")
    return time.hour * 60 + time.minute


def test_unselected_continue_during_break_and_faculty_can_idle_until_resume(generated):
    reflection = next(activity for activity in generated["allocation"]["activities"] if activity["activity_id"] == "reflection")
    selected = set(generated["configuration"]["reflection_settings"]["selected_participant_ids"])
    sessions = reflection["sessions"]
    assert all(minutes(session["end_time"]) <= 700 or minutes(session["start_time"]) >= 790
               for session in sessions if session["participant_id"] in selected)
    assert any(session["participant_id"] not in selected and minutes(session["start_time"]) < 790
               and minutes(session["end_time"]) > 700 for session in sessions)
    found_idle = False
    for faculty in generated["faculty_members"]:
        ordered = sorted((session for session in sessions if session["faculty_id"] == faculty["id"]), key=lambda session: minutes(session["start_time"]))
        assert len(ordered) == 4
        assert all(minutes(left["end_time"]) <= minutes(right["start_time"]) for left, right in zip(ordered, ordered[1:]))
        found_idle |= any(minutes(right["start_time"]) >= 790 and minutes(left["end_time"]) < 790
                          and minutes(right["start_time"]) > minutes(left["end_time"])
                          for left, right in zip(ordered, ordered[1:]))
    assert found_idle


def test_legacy_individual_faculty_availability_is_ignored(generated):
    payload = copy.deepcopy(generated)
    for member in payload["faculty_members"]:
        member.update({"available_from": "18:00", "available_until": "18:20", "prayer_unavailable": True,
                       "unavailable_intervals": [{"start_time": "00:00", "end_time": "17:59"}]})
    response = TestClient(app).post("/api/optimize", json=payload)
    assert response.status_code == 200, response.text
    reflection = next(activity for activity in response.json()["allocation"]["activities"] if activity["activity_id"] == "reflection")
    assert len(reflection["sessions"]) == 12
    assert max(minutes(session["end_time"]) for session in reflection["sessions"]) < 18 * 60
    assert all("available_from" not in member for member in generated["faculty_members"])


@pytest.mark.parametrize("cross_faculty", [False, True])
def test_manual_prayer_swaps_reject_protected_slots_and_valid_swaps_export(generated, cross_faculty):
    reflection = next(activity for activity in generated["allocation"]["activities"] if activity["activity_id"] == "reflection")
    selected = set(generated["configuration"]["reflection_settings"]["selected_participant_ids"])
    sessions = reflection["sessions"]
    protected = next(session for session in sessions if session["participant_id"] in selected and minutes(session["start_time"]) >= 790)
    restricted_slot = next(session for session in sessions if session["participant_id"] not in selected
                           and minutes(session["start_time"]) < 790 and minutes(session["end_time"]) > 700
                           and ((session["faculty_id"] != protected["faculty_id"]) if cross_faculty else (session["faculty_id"] == protected["faculty_id"])))
    response = TestClient(app).post("/api/allocations/edit", json={
        **generated, "activity_id": "reflection", "participant_id": protected["participant_id"],
        "target_group_id": restricted_slot["faculty_id"], "swap_with_id": restricted_slot["participant_id"], "allow_override": True})
    assert response.status_code == 422 and "protected" in response.text.casefold()
    compatible = next(session for session in sessions if session["participant_id"] != protected["participant_id"]
                      and (minutes(session["end_time"]) <= 700 or minutes(session["start_time"]) >= 790)
                      and ((session["faculty_id"] != protected["faculty_id"]) if cross_faculty else (session["faculty_id"] == protected["faculty_id"])))
    valid = TestClient(app).post("/api/allocations/edit", json={
        **generated, "activity_id": "reflection", "participant_id": protected["participant_id"],
        "target_group_id": compatible["faculty_id"], "swap_with_id": compatible["participant_id"]})
    assert valid.status_code == 200 and "requires_confirmation" not in valid.json(), valid.text
    allocation = valid.json()["allocation"]
    updated = next(activity for activity in allocation["activities"] if activity["activity_id"] == "reflection")
    exchanged = next(session for session in updated["sessions"] if session["participant_id"] == protected["participant_id"])
    assert exchanged["faculty_id"] == compatible["faculty_id"] and exchanged["start_time"] == compatible["start_time"]
    payload = {**generated, "allocation": allocation}
    pdf = TestClient(app).post("/api/export/pdf/reflection", json=payload)
    assert pdf.status_code == 200
    text = pdf_text(pdf.content)
    assert compatible["start_time"] in text and "Participant Offering" in text
    # Faculty offerings remain in exports; only the Results UI hides them.
    assert any(f"{member['name']} — {member['offering']}" in text for member in generated["faculty_members"])
    excel = TestClient(app).post("/api/export/editable", json=payload)
    assert excel.status_code == 200
    book = load_workbook(io.BytesIO(excel.content))
    rows = list(book["My Reflections"].iter_rows(values_only=True))
    assert any(compatible["start_time"] in row and f"Integration Hire {protected['participant_id'][1:]}" in row for row in rows)
