"""Fictional manifest fixtures exercise export content and privacy boundaries."""
import io

import pandas as pd
import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

from app.models import ActivityAllocation, AllocationSnapshot, Configuration, FacultyMember, Group, Participant, SupportMember
from app.services.excel import (export_week2_workbook, export_workbook, hotel_room_summary,
                                parse_excel, parse_support_excel)
from app.services.pdf_export import export_pdf


def manifest_fixture():
    participants = [Participant(id=f"P{i}", name=f"Fictional Hire {i}", attributes={
        "Gender": "Male" if i < 3 else "Female", "University": "Cairo University",
        "University Category": "public", "L3 Offering": "Cyber"}) for i in range(6)]
    support = [SupportMember(id="S0", name="Fictional Lead One", gender="Male", category="Support Lead"),
               SupportMember(id="S1", name="Fictional Lead Two", gender="Female", category="Support Lead"),
               SupportMember(id="S2", name="Fictional Analyst One", gender="Male", category="Analyst Support"),
               SupportMember(id="S3", name="Fictional Analyst Two", gender="Female", category="Analyst Support")]
    faculty = [FacultyMember(id=f"F{i}", name=f"Fictional Faculty {i}", offering="Cyber") for i in range(3)]
    occupants = [["P0", "P1"], ["P2", "S2"], ["P3"], ["P4", "P5"], ["S0"], ["S1"], ["S3"], ["F0"], ["F1"], ["F2"]]
    hotel = ActivityAllocation(activity_id="hotel", activity_name="Hotel Rooms", groups=[
        Group(id=f"R{i}", name=f"Room {i+1}", participant_ids=ids) for i, ids in enumerate(occupants)])
    main = ActivityAllocation(activity_id="main", activity_name="Main Groups", groups=[
        Group(id="M0", name="Group A", participant_ids=["P0", "P2", "P4"]),
        Group(id="M1", name="Group B", participant_ids=["P1", "P3", "P5"])])
    bus = ActivityAllocation(activity_id="bus", activity_name="BUS Teams", groups=[
        Group(id="B0", name="BUS Team 1", participant_ids=["P0", "P1", "P2", "S0", "S2"]),
        Group(id="B1", name="BUS Team 2", participant_ids=["P3", "P4", "P5", "S1", "S3"])])
    reflection = ActivityAllocation(activity_id="reflection", activity_name="MyReflection", groups=[
        Group(id=f"F{i}", name=faculty[i].name, participant_ids=[f"P{i}", f"P{i+3}"]) for i in range(3)])
    return participants, support, faculty, AllocationSnapshot(activities=[main, bus, reflection, hotel])


def pdf_text(data):
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)


def test_private_hotel_pdf_has_every_person_roles_and_exact_room_summary():
    participants, support, faculty, allocation = manifest_fixture()
    hotel = allocation.activities[-1]
    summary = hotel_room_summary(hotel, participants, support, faculty)
    assert summary == {"total_rooms": 10, "new_hire_shared_rooms": 2,
                       "new_hire_analyst_shared_rooms": 1, "single_new_hire_rooms": 1,
                       "single_support_lead_rooms": 2, "single_analyst_support_rooms": 1,
                       "single_faculty_rooms": 3}
    assert sum(value for key, value in summary.items() if key != "total_rooms") == summary["total_rooms"]
    text = pdf_text(export_pdf(participants, allocation, support, {"hotel"}, faculty))
    assert "PRIVATE HOTEL ROOM MANIFEST" in text
    assert "Total rooms required: 10" in text
    for person in [*participants, *support, *faculty]:
        assert text.count(person.name) == 1
    assert all(f"Room {i}" in text for i in range(1, 11))
    assert "Support Lead" in text and "Analyst Support" in text and "Faculty" in text
    assert "Single new-hire rooms require accommodation review" in text
    assert "Male" not in text and "Female" not in text and "Cairo University" not in text


def test_participant_pdf_excludes_hotel_by_default_and_has_spaced_reflections_title():
    participants, support, faculty, allocation = manifest_fixture()
    text = pdf_text(export_pdf(participants, allocation, support, faculty_members=faculty))
    assert "My Reflections" in text and "MyReflection" not in text
    assert "HOTEL" not in text and "Room 1" not in text and "Total rooms" not in text
    assert all(person.name in text for person in participants)
    assert "Female" not in text and "Male" not in text
    assert "Cairo University" not in text and "public" not in text


def test_editable_excel_roundtrips_support_roles_and_participant_categories():
    participants, support, faculty, allocation = manifest_fixture()
    participants[1].attributes.update({"University": "German University in Cairo", "University Category": "private"})
    data = export_week2_workbook(participants, allocation, faculty, support)
    workbook = load_workbook(io.BytesIO(data))
    assert "My Reflections" in workbook.sheetnames and "MyReflection" not in workbook.sheetnames
    imported = parse_support_excel(data)
    assert [person.model_dump() for person in imported] == [person.model_dump() for person in support]
    imported_participants, _ = parse_excel(data)
    assert [person.id for person in imported_participants] == [person.id for person in participants]
    assert [person.attributes["University Category"] for person in imported_participants] == ["public", "private", "public", "public", "public", "public"]
    rows = list(workbook["Hotel Rooms"].iter_rows(values_only=True))
    assert rows[0] == ("Room", "Occupant 1", "Occupant 1 Role", "Occupant 2", "Occupant 2 Role", "Occupancy")
    assert len(rows) - 1 == 10
    assert rows[2][2:5] == ("New Hire", "Fictional Analyst One", "Analyst Support")
    summary = dict(workbook["Hotel Summary"].iter_rows(min_row=2, values_only=True))
    assert summary["Total rooms required"] == 10
    assert summary["Single faculty rooms"] == 3
    staff_rows = list(workbook["BUS Teams"].iter_rows(values_only=True))
    assert sum(row[1] == "Support Lead" for row in staff_rows) == 2
    assert sum(row[1] == "Analyst Support" for row in staff_rows) == 2
    validations = list(workbook["Support Team"].data_validations.dataValidation)
    assert {validation.formula1 for validation in validations} == {'"Male,Female"', '"Support Lead,Analyst Support"'}


def test_legacy_staff_sheet_preserves_missing_details_and_rejects_invalid_categories():
    output = io.BytesIO()
    pd.DataFrame([{"Name": "Fictional Legacy Support"}]).to_excel(output, index=False)
    staff = parse_support_excel(output.getvalue())
    assert staff[0].gender is None and staff[0].category is None
    output = io.BytesIO()
    pd.DataFrame([{"Name": "Fictional Support", "Gender": "Female", "Support Category": "Unrecognized role"}]).to_excel(output, index=False)
    with pytest.raises(ValueError, match="Support Lead or Analyst Support"):
        parse_support_excel(output.getvalue())


def test_generic_workbook_handles_staff_hotel_and_editable_export_escapes_formulas():
    participants, support, faculty, allocation = manifest_fixture()
    data = export_workbook(participants, allocation, {}, Configuration(activities=[]), faculty, support)
    workbook = load_workbook(io.BytesIO(data))
    values = [cell.value for row in workbook["Hotel Rooms"] for cell in row]
    assert "Fictional Faculty 0" in values and "Fictional Lead One" in values
    assert "My Reflections" in workbook.sheetnames
    participants[0].name = '=HYPERLINK("https://invalid.example", "Fictional")'
    staff = export_week2_workbook(participants, allocation, faculty, support)
    workbook = load_workbook(io.BytesIO(staff))
    assert workbook["Participants"]["B2"].value.startswith("'=")
    assert all(cell.data_type != "f" for sheet in workbook for row in sheet for cell in row)


def test_master_excel_keeps_capital_helwan_aliases_distinct_from_national():
    output = io.BytesIO()
    pd.DataFrame([{"Candidate Name": f"Fictional Person {i}", "Gender": "M", "University": name}
                  for i, name in enumerate(("Helwan University", "Capital University", "جامعة العاصمة", "Helwan National University"))]).to_excel(output, index=False)
    participants, _ = parse_excel(output.getvalue())
    assert {person.attributes["University"] for person in participants[:3]} == {"Capital-Helwan University"}
    assert len({person.attributes["UniversityId"] for person in participants[:3]}) == 1
    assert participants[3].attributes["UniversityId"] != participants[0].attributes["UniversityId"]


def test_editable_excel_preserves_explicit_binary_grouping_for_custom_institutions():
    participants, support, faculty, allocation = manifest_fixture()
    participants[0].attributes.update({"University": "Fictional International Campus", "University Category": "private"})
    participants[1].attributes.update({"University": "Fictional Ahleya Campus", "University Category": "public"})
    data = export_week2_workbook(participants, allocation, faculty, support)
    imported, _ = parse_excel(data)
    assert imported[0].attributes["University Category"] == "private"
    assert imported[1].attributes["University Category"] == "public"
    assert imported[0].attributes["University"] == "Fictional International Campus"
    assert imported[1].attributes["University"] == "Fictional Ahleya Campus"
    text = pdf_text(export_pdf(participants, allocation, support, faculty_members=faculty))
    assert "private" not in text and "public" not in text
    assert "Fictional International Campus" not in text and "Fictional Ahleya Campus" not in text
    # Staff metadata receives no invented university grouping on export.
    book = load_workbook(io.BytesIO(data))
    assert [cell.value for cell in book["Support Team"][1]] == ["Support ID", "Name", "Gender", "Support Category"]
    assert [cell.value for cell in book["Faculty"][1]] == ["Faculty ID", "Name", "Offering"]
