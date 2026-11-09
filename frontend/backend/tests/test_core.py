import io
import pandas as pd
import pytest
from openpyxl import load_workbook
from pypdf import PdfReader
from fastapi.testclient import TestClient
from app.main import app
from app.models import *
from app.services.optimizer import group_sizes, optimize
from app.services.scoring import score_allocation, validate_allocation
from app.services.normalization import display_gender, display_offering, normalize_university, resolve_university, university_directory
from app.services.excel import blank_template, match_chemistry, parse_chemistry

def people(n=30):
    return [Participant(id=f"P{i}", name=f"Person {i}", attributes={"Gender":"Female" if i%2 else "Male", "University":f"University {i%8}", "University Category":"other"}) for i in range(n)]

def config(n=30):
    return Configuration(activities=[Activity(id="main",name="Main Groups",mode="max_size",value=6), Activity(id="sports",name="Sports Day",mode="max_size",value=5), Activity(id="quiz",name="Quiz Night",mode="group_count",value=5)], factors=[Factor(id="gender",name="Gender",source_column="Gender"), Factor(id="dept",name="Department",source_column="Department")], time_limit_seconds=4)

def test_group_sizes():
    assert group_sizes(29,"max_size",6)==[6,6,6,6,5]

def test_standardized_offerings_and_faculty_validation():
    assert display_offering("Data & AI")=="AI & Data"
    assert display_offering("ai and data")=="AI & Data"
    assert display_offering("ETP")=="ET&P"
    assert FacultyMember(id="f1",name="Faculty",offering="data & ai").offering=="AI & Data"
    with pytest.raises(ValueError,match="Faculty offering must be one of"):
        FacultyMember(id="f1",name="Faculty",offering="Consulting")
    assert group_sizes(29,"group_count",4)==[8,7,7,7]

def test_cohorts_are_valid():
    for n in [20,25,27,29,30,40]:
        p=people(n); c=config(n); a=optimize(OptimizeRequest(participants=p,configuration=c))
        assert not validate_allocation(p,c,a)
        for activity in a.activities:
            assert len([x for g in activity.groups for x in g.participant_ids])==n

def test_scoring_counts_repeats():
    p=people(4); groups=[Group(id="g0",name="A",participant_ids=["P0","P1"]),Group(id="g1",name="B",participant_ids=["P2","P3"])]
    a=AllocationSnapshot(activities=[ActivityAllocation(activity_id=x,activity_name=x,groups=groups) for x in ["main","sports","quiz"]])
    c=Configuration(activities=[Activity(id=x,name=x,mode="group_count",value=2) for x in ["main","sports","quiz"]])
    score=score_allocation(p,c,a); assert score["total_unique_pairs"]==2; assert score["repeat_pairing_penalty"]==4

def test_locked_main_is_preserved():
    p=people(20); c=config(); first=optimize(OptimizeRequest(participants=p,configuration=c))
    c.activities[0].locked=True
    second=optimize(OptimizeRequest(participants=p,configuration=c,existing_allocation=first,regenerate_activity_ids=["sports","quiz"]))
    assert second.activities[0]==first.activities[0]

def test_api_health_and_sample():
    client=TestClient(app); assert client.get("/api/health").status_code==200
    response=client.get("/api/sample-template"); assert response.status_code==200
    assert len(response.content)>4000

def test_verified_university_aliases_without_fuzzy_merging():
    assert normalize_university("GUC") == normalize_university("German University in Cairo")
    assert normalize_university("Cairo  University") == normalize_university("Cairo University")
    assert normalize_university("Cairo Technical University") != normalize_university("Cairo University")

def test_every_directory_name_resolves_to_its_stable_id():
    directory=university_directory()
    assert len(directory)>=130
    assert len({item["id"] for item in directory})==len(directory)
    for item in directory:
        assert resolve_university(item["official_english_name"])["id"]==item["id"]

def test_arabic_partial_identity_and_similar_universities_stay_distinct():
    assert normalize_university("الجامعة الألمانية بالقاهرة")==normalize_university("GUC")
    assert normalize_university("المنصورة")=="custom:المنصوره"  # ambiguous partial input is not auto-selected
    assert normalize_university("Cairo University")!=normalize_university("Cairo National University")
    assert normalize_university("University of Oxford")=="custom:university of oxford"

def test_zero_university_duplicates_when_feasible_and_gender_balanced():
    p = [Participant(id=f"P{i}", name=f"Person {i}", attributes={
        "Gender": "Female" if i % 2 else "Male", "University": f"University {i % 4}", "University Category":"other"
    }) for i in range(8)]
    c = Configuration(activities=[Activity(id="main", name="Main", mode="max_size", value=4)], time_limit_seconds=5)
    a = optimize(OptimizeRequest(participants=p, configuration=c))
    score = score_allocation(p, c, a)
    assert score["same_university_pairs"] == 0
    for detail in score["activity_group_details"]["main"]:
        assert detail["gender_counts"] == {"male": 2, "female": 2}

def test_unavoidable_university_duplicates_are_counted_exactly():
    p = [Participant(id=f"P{i}", name=f"Person {i}", attributes={
        "Gender": "Female" if i % 2 else "Male", "University": "Only University", "University Category":"other"
    }) for i in range(6)]
    c = Configuration(activities=[Activity(id="main", name="Main", mode="group_count", value=2)], time_limit_seconds=5)
    a = optimize(OptimizeRequest(participants=p, configuration=c))
    score = score_allocation(p, c, a)
    assert score["same_university_pairs"] == 6  # two groups, C(3, 2) each

def test_temporary_regeneration_preserves_main_exactly():
    p=people(25); c=config(); first=optimize(OptimizeRequest(participants=p,configuration=c))
    c.activities[0].locked=True
    second=optimize(OptimizeRequest(participants=p,configuration=c,existing_allocation=first,regenerate_activity_ids=["sports","quiz"]))
    assert second.activities[0].model_dump() == first.activities[0].model_dump()
    assert not validate_allocation(p,c,second)

def workbook(rows):
    output=io.BytesIO(); pd.DataFrame(rows).to_excel(output,index=False); return output.getvalue()

def test_excel_and_manual_use_same_normalization_pipeline():
    client=TestClient(app)
    rows=[{"Name":f"Person {i}","Gender":"M" if i%2==0 else "f",
           "University":"GUC" if i%2==0 else "German University in Cairo"} for i in range(8)]
    uploaded=client.post("/api/upload",files={"file":("people.xlsx",workbook(rows))})
    assert uploaded.status_code==200
    excel_people=uploaded.json()["participants"]
    manual=[{"id":person["id"],"name":row["Name"],"attributes":{"Gender":row["Gender"],"University":row["University"]}}
            for person,row in zip(excel_people,rows)]
    validated=client.post("/api/participants/validate",json=manual)
    assert validated.status_code==200
    assert validated.json()["participants"]==excel_people
    assert {p["attributes"]["University"] for p in excel_people}=={"German University in Cairo"}
    assert {p["attributes"]["Gender"] for p in excel_people}=={"Male","Female"}
    cfg=Configuration(activities=[Activity(id="main",name="Main",mode="max_size",value=4)],seed=42,time_limit_seconds=3)
    excel_result=optimize(OptimizeRequest(participants=[Participant(**p) for p in excel_people],configuration=cfg))
    manual_result=optimize(OptimizeRequest(participants=[Participant(**p) for p in validated.json()["participants"]],configuration=cfg))
    assert excel_result.activities==manual_result.activities

def test_gender_aliases_and_missing_field_errors():
    assert display_gender("MALE")=="Male"
    assert display_gender("F")=="Female"
    assert display_gender("nb") is None
    client=TestClient(app)
    response=client.post("/api/participants/validate",json=[{"id":"P1","name":"","attributes":{"Gender":"unknown value","University":""}}])
    assert response.status_code==422
    detail=" ".join(response.json()["detail"])
    assert "name is required" in detail and "valid gender" in detail and "university is required" in detail

def test_upload_rejects_missing_required_columns():
    response=TestClient(app).post("/api/upload",files={"file":("bad.xlsx",workbook([{"Name":"Person","Gender":"Male"}]))})
    assert response.status_code==422
    assert "University" in response.json()["detail"]

def test_manual_validation_for_25_and_30_participants():
    client=TestClient(app)
    for count in (25,30):
        rows=[{"id":f"P{i}","name":f"Person {i}","attributes":{
            "Gender":"Male" if i%2==0 else "Female", "University":f"University {i%7}"
        }} for i in range(count)]
        response=client.post("/api/participants/validate",json=rows)
        assert response.status_code==200
        assert response.json()["count"]==count
        assert len({p["id"] for p in response.json()["participants"]})==count

def test_blank_template_has_exact_gender_dropdown_and_no_instructions_sheet():
    workbook=load_workbook(io.BytesIO(blank_template()))
    assert workbook.sheetnames==["Participants"]
    sheet=workbook["Participants"]
    assert [cell.value for cell in sheet[1]]==["Name","Gender","University"]
    validations=list(sheet.data_validations.dataValidation)
    assert len(validations)==1 and validations[0].formula1=='"Male,Female"'
    assert "B2:B201" in str(validations[0].sqref)
    assert "only male or female" in validations[0].error.lower()

def test_pdf_has_all_activities_all_names_and_no_private_attributes():
    p=people(6); c=Configuration(activities=[Activity(id=x,name=name,mode="group_count",value=2) for x,name in [("main","Main Groups"),("sports","Sports Day"),("quiz","Quiz Night")]])
    groups=[Group(id="g0",name="Group A",participant_ids=["P0","P1","P2"]),Group(id="g1",name="Group B",participant_ids=["P3","P4","P5"])]
    allocation=AllocationSnapshot(activities=[ActivityAllocation(activity_id=a.id,activity_name=a.name,groups=groups) for a in c.activities])
    response=TestClient(app).post("/api/export/pdf",json={"participants":[x.model_dump() for x in p],"configuration":c.model_dump(),"allocation":allocation.model_dump()})
    assert response.status_code==200 and response.headers["content-type"]=="application/pdf"
    reader=PdfReader(io.BytesIO(response.content)); text="\n".join(page.extract_text() for page in reader.pages)
    assert all(title in text for title in ["MAIN TEAMS","SPORTS DAY GROUPS","QUIZ NIGHT GROUPS"])
    assert all(text.count(person.name)==3 for person in p)
    assert "University 0" not in text and "Female" not in text and "same-university" not in text.lower()
    assert len(reader.pages)==3
    individual=TestClient(app).post("/api/export/pdf/quiz",json={"participants":[x.model_dump() for x in p],"configuration":c.model_dump(),"allocation":allocation.model_dump()})
    assert individual.status_code==200
    individual_text="\n".join(page.extract_text() for page in PdfReader(io.BytesIO(individual.content)).pages)
    assert "QUIZ NIGHT GROUPS" in individual_text
    assert "MAIN TEAMS" not in individual_text and "SPORTS DAY GROUPS" not in individual_text

def test_business_chemistry_parsing_and_safe_matching():
    data=workbook([{"Name":"  PERSON-0 ","Primary":"Pioneer","Secondary":"Driver"},
                   {"Name":"Unknown Person","Primary":"Guardian","Secondary":"Integrator"}])
    records=parse_chemistry(data); result=match_chemistry(people(3),records)
    assert result["matched"][0]["participant_id"]=="P0"
    assert len(result["requires_review"])==1

def test_week2_six_allocations_and_hotel_hard_constraints():
    cohort=[Participant(id=f"P{i}",name=f"Person {i}",attributes={"Gender":"Male" if i<14 else "Female",
        "University":f"University {i%8}", "University Category":"other","UniversityId":f"u{i%8}","L3 Offering":["Cyber","Customer","AI & Data"][i%3],
        "Primary Chemistry":["Pioneer","Driver","Guardian","Integrator"][i%4],
        "Secondary Chemistry":["Driver","Guardian","Integrator","Pioneer"][i%4]}) for i in range(27)]
    config=Configuration(activities=[Activity(id=x,name=x,mode="max_size",value=6) for x in ("main","quiz","team")],time_limit_seconds=3,include_business_chemistry=True)
    request=OptimizeRequest(participants=cohort,configuration=config,
        faculty_members=[FacultyMember(id=f"f{i}",name=f"Faculty {i}",offering=o) for i,o in enumerate(("Cyber","Customer","AI & Data"))],
        support_members=[SupportMember(id=f"s{i}",name=f"Support {i}",gender="Male" if i%2==0 else "Female",category="Support Lead" if i<2 else "Analyst Support") for i in range(5)])
    allocation=optimize(request); activities={a.activity_id:a for a in allocation.activities}
    assert set(activities)=={"main","quiz","team","bus","reflection","hotel"}
    main={pid:g.id for g in activities["main"].groups for pid in g.participant_ids}; pmap={p.id:p for p in cohort}
    assigned=[pid for room in activities["hotel"].groups for pid in room.participant_ids]
    assert len(assigned)==len(set(assigned))==35
    for room in activities["hotel"].groups:
        assert len(room.participant_ids)<=2
        if len(room.participant_ids)==2:
            left,right=room.participant_ids
            gender={p.id:p.attributes["Gender"] for p in cohort}
            gender.update({member.id:member.gender for member in request.support_members})
            assert gender[left]==gender[right]
            if left in pmap and right in pmap: assert main[left]!=main[right]
    assert sorted(len(g.participant_ids) for g in activities["reflection"].groups)==[9,9,9]

    # Chemistry-disabled mode must accept the same 27-person cohort without any
    # Chemistry attributes and still produce a complete, valid six-allocation set.
    without_chemistry=[p.model_copy(update={"attributes":{k:v for k,v in p.attributes.items() if "Chemistry" not in k}}) for p in cohort]
    disabled_config=config.model_copy(update={"include_business_chemistry":False})
    disabled=optimize(request.model_copy(update={"participants":without_chemistry,"configuration":disabled_config}))
    disabled_activities={a.activity_id:a for a in disabled.activities}
    assert set(disabled_activities)=={"main","quiz","team","bus","reflection","hotel"}
    for activity_id,activity in disabled_activities.items():
        assigned=[pid for group in activity.groups for pid in group.participant_ids if pid.startswith("P")]
        assert sorted(assigned)==sorted(p.id for p in without_chemistry), activity_id

    # Changing only gender must not alter My Reflections assignments. Gender still
    # remains available to the core/BUS allocations and as the hotel hard rule.
    alternate_gender=[p.model_copy(update={"attributes":{**p.attributes,"Gender":"Male" if i%2==0 else "Female"}}) for i,p in enumerate(without_chemistry)]
    alternate_gender_result=optimize(request.model_copy(update={"participants":alternate_gender,"configuration":disabled_config}))
    reflection_groups=lambda result: [group.participant_ids for group in next(a for a in result.activities if a.activity_id=="reflection").groups]
    assert reflection_groups(disabled)==reflection_groups(alternate_gender_result)


def test_enabled_business_chemistry_requires_complete_profiles():
    cohort=people(6)
    config=Configuration(activities=[Activity(id="main",name="Main",mode="max_size",value=3)],include_business_chemistry=True)
    with pytest.raises(ValueError,match="Primary and Secondary Business Chemistry"):
        optimize(OptimizeRequest(participants=cohort,configuration=config))


def test_enhanced_reflection_schedules_selected_people_before_and_after_prayer():
    cohort=[Participant(id=f"P{i}",name=f"Person {i}",attributes={"Gender":"Male" if i<12 else "Female",
        "University":f"University {i%6}", "University Category":"other","UniversityId":f"u{i%6}","L3 Offering":["Cyber","Customer","AI & Data"][i%3]}) for i in range(27)]
    selected=[f"P{i}" for i in range(9)]
    settings=ReflectionSettings(enabled=True,selected_participant_ids=selected,start_time="11:00",
        session_duration_minutes=20,prayer_deadline="12:00",resume_time="13:00")
    config=Configuration(activities=[Activity(id=x,name=x,mode="max_size",value=6) for x in ("main","quiz","team")],
        reflection_settings=settings,time_limit_seconds=3)
    faculty=[FacultyMember(id=f"f{i}",name=f"Faculty {i}",offering=o) for i,o in enumerate(("Cyber","Customer","AI & Data"))]
    request=OptimizeRequest(participants=cohort,configuration=config,faculty_members=faculty,
        support_members=[SupportMember(id=f"s{i}",name=f"Support {i}",gender="Male",category="Support Lead") for i in range(2)])
    allocation=optimize(request); reflection=next(a for a in allocation.activities if a.activity_id=="reflection")
    assert len(reflection.sessions)==27
    session_map={s.participant_id:s for s in reflection.sessions}
    from app.services.optimizer import validate_reflection_sessions
    assert not validate_reflection_sessions(reflection,request)
    for faculty_id in (f.id for f in faculty):
        intervals=[(s.start_time,s.end_time) for s in reflection.sessions if s.faculty_id==faculty_id]
        assert len(intervals)==len(set(intervals))

    continuation=config.model_copy(update={"reflection_settings":settings.model_copy(update={"selected_participant_ids":[f"P{i}" for i in range(27)]})})
    continued=optimize(request.model_copy(update={"configuration":continuation}))
    appointments=next(a for a in continued.activities if a.activity_id=="reflection").sessions
    assert len(appointments)==27 and any(not session.before_prayer for session in appointments)

    source,target=reflection.groups[:2]
    response=TestClient(app).post("/api/allocations/swap",json={"participants":[p.model_dump() for p in cohort],
        "faculty_members":[f.model_dump() for f in faculty],"support_members":[s.model_dump() for s in request.support_members],"configuration":config.model_dump(),
        "allocation":allocation.model_dump(),"activity_id":"reflection","participant_a":source.participant_ids[0],"participant_b":target.participant_ids[0]})
    assert response.status_code==200 and "requires_confirmation" not in response.json()


def test_enhanced_reflection_exports_include_schedule_fields():
    cohort=[Participant(id=f"P{i}",name=f"Person {i}",attributes={"Gender":"Male","University":"Cairo University","L3 Offering":offering})
            for i,offering in enumerate(("Cyber","Customer","AI & Data"))]
    faculty=[FacultyMember(id=f"f{i}",name=f"Faculty {i}",offering=offering) for i,offering in enumerate(("Cyber","Customer","AI & Data"))]
    reflection=ActivityAllocation(activity_id="reflection",activity_name="My Reflections",
        groups=[Group(id="f0",name="Faculty 0",participant_ids=["P1"]),Group(id="f1",name="Faculty 1",participant_ids=["P0"]),Group(id="f2",name="Faculty 2",participant_ids=["P2"])],
        sessions=[ReflectionSession(participant_id="P0",faculty_id="f1",start_time="11:00 AM",end_time="11:20 AM",offering_match=True,before_prayer=True),
                  ReflectionSession(participant_id="P1",faculty_id="f0",start_time="11:00 AM",end_time="11:20 AM",offering_match=True,before_prayer=True),
                  ReflectionSession(participant_id="P2",faculty_id="f2",start_time="11:20 AM",end_time="11:40 AM",offering_match=True,before_prayer=True)])
    allocation=AllocationSnapshot(activities=[reflection])
    config=Configuration(activities=[],reflection_settings=ReflectionSettings(enabled=True,selected_participant_ids=["P0"]))
    payload={"participants":[p.model_dump() for p in cohort],"faculty_members":[f.model_dump() for f in faculty],
        "configuration":config.model_dump(),"allocation":allocation.model_dump()}
    client=TestClient(app)
    pdf=client.post("/api/export/pdf",json=payload);assert pdf.status_code==200
    text="\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
    assert all(value in text for value in ("Participant Offering","Faculty 0 — Cyber","11:00 AM - 11:20 AM","Match"))
    assert text.index("Person 1") < text.index("Person 0") < text.index("Person 2")
    excel=client.post("/api/export/editable",json=payload);assert excel.status_code==200
    sheet=load_workbook(io.BytesIO(excel.content))["My Reflections"]
    assert sheet["A1"].value=="Faculty 0 — Cyber"
    assert [cell.value for cell in sheet[2]]==["#","Start Time","End Time","Assigned New Hire","Participant Offering","Offering Match","Prayer Status"]
    assert [sheet.cell(row,4).value for row in (3,7,11)]==["Person 1","Person 0","Person 2"]


def test_drag_edit_endpoint_validates_swaps_cross_dependencies_and_bus_balance():
    cohort=[Participant(id=f"P{i}",name=f"Person {i}",attributes={"Gender":"Male" if i<2 else "Female","University":f"U{i}","L3 Offering":"Cyber"}) for i in range(4)]
    config=Configuration(activities=[Activity(id="main",name="Main",mode="group_count",value=2),Activity(id="quiz",name="Quiz",mode="group_count",value=2)])
    main=ActivityAllocation(activity_id="main",activity_name="Main",groups=[Group(id="main-0",name="A",participant_ids=["P0","P2"]),Group(id="main-1",name="B",participant_ids=["P1","P3"])])
    quiz=ActivityAllocation(activity_id="quiz",activity_name="Quiz",groups=[Group(id="quiz-0",name="A",participant_ids=["P0","P1"]),Group(id="quiz-1",name="B",participant_ids=["P2","P3"])])
    hotel=ActivityAllocation(activity_id="hotel",activity_name="Hotel",groups=[Group(id="room-1",name="Room 1",participant_ids=["P0","P1"]),Group(id="room-2",name="Room 2",participant_ids=["P2","P3"])])
    allocation=AllocationSnapshot(activities=[main,quiz,hotel])
    base={"participants":[p.model_dump() for p in cohort],"configuration":config.model_dump(),"allocation":allocation.model_dump()}
    client=TestClient(app)

    valid=client.post("/api/allocations/edit",json={**base,"activity_id":"quiz","participant_id":"P0","target_group_id":"quiz-1","swap_with_id":"P2"})
    assert valid.status_code==200
    edited=valid.json()["allocation"]
    edited_quiz=next(a for a in edited["activities"] if a["activity_id"]=="quiz")
    assert edited_quiz["groups"][0]["participant_ids"]==["P2","P1"]

    main_conflict=client.post("/api/allocations/edit",json={**base,"activity_id":"main","participant_id":"P0","target_group_id":"main-1","swap_with_id":"P3"})
    assert main_conflict.status_code==200 and main_conflict.json()["requires_confirmation"] is True
    assert any(item["rule"]=="roommates_same_main" for item in main_conflict.json()["conflicts"])
    main_override=client.post("/api/allocations/edit",json={**base,"activity_id":"main","participant_id":"P0","target_group_id":"main-1","swap_with_id":"P3","allow_override":True})
    assert main_override.status_code==200 and main_override.json()["allocation"]

    hotel_conflict=client.post("/api/allocations/edit",json={**base,"activity_id":"hotel","participant_id":"P0","target_group_id":"room-2","swap_with_id":"P2"})
    assert hotel_conflict.status_code==200 and hotel_conflict.json()["requires_confirmation"] is True
    mixed=next(item for item in hotel_conflict.json()["conflicts"] if item["rule"]=="mixed_gender_room")
    assert mixed["policy_sensitive"] is True and mixed["overridable"] is False
    prohibited=client.post("/api/allocations/edit",json={**base,"activity_id":"hotel","participant_id":"P0","target_group_id":"room-2","swap_with_id":"P2","allow_override":True})
    assert prohibited.status_code==422

    supports=[SupportMember(id="S0",name="Support 0",gender="Male",category="Support Lead"),SupportMember(id="S1",name="Support 1",gender="Female",category="Support Lead")]
    bus=ActivityAllocation(activity_id="bus",activity_name="BUS",groups=[Group(id="bus-0",name="BUS 1",participant_ids=["P0","P1","S0"]),Group(id="bus-1",name="BUS 2",participant_ids=["P2","P3","S1"])])
    bus_allocation=AllocationSnapshot(activities=[bus])
    bus_move=client.post("/api/allocations/edit",json={"participants":[p.model_dump() for p in cohort],"support_members":[s.model_dump() for s in supports],
        "configuration":Configuration(activities=[]).model_dump(),"allocation":bus_allocation.model_dump(),"activity_id":"bus","participant_id":"P0","target_group_id":"bus-1"})
    assert bus_move.status_code==200 and "requires_confirmation" not in bus_move.json()


def test_reflection_manual_swaps_exchange_existing_slots_without_warnings_and_export_new_times():
    cohort=[Participant(id=f"P{i}",name=f"Person {i}",attributes={"Gender":"Male","University":f"U{i}","L3 Offering":"Cyber"}) for i in range(4)]
    faculty=[FacultyMember(id="f0",name="Layla",offering="Cyber"),FacultyMember(id="f1",name="Aisha",offering="Engineering"),FacultyMember(id="f2",name="Faculty 2",offering="Customer")]
    reflection=ActivityAllocation(activity_id="reflection",activity_name="My Reflections",
        groups=[Group(id="f0",name="Layla",participant_ids=["P0","P1","P2"]),Group(id="f1",name="Aisha",participant_ids=["P3"]),Group(id="f2",name="Faculty 2",participant_ids=[])],
        sessions=[ReflectionSession(participant_id="P0",faculty_id="f0",start_time="10:00 AM",end_time="10:20 AM",offering_match=True,before_prayer=True),
                  ReflectionSession(participant_id="P1",faculty_id="f0",start_time="10:20 AM",end_time="10:40 AM",offering_match=True,before_prayer=True),
                  ReflectionSession(participant_id="P2",faculty_id="f0",start_time="10:40 AM",end_time="11:00 AM",offering_match=True,before_prayer=True),
                  ReflectionSession(participant_id="P3",faculty_id="f1",start_time="10:00 AM",end_time="10:20 AM",offering_match=False,before_prayer=True)])
    configuration=Configuration(activities=[],reflection_settings=ReflectionSettings(start_time="10:00"))
    base={"participants":[p.model_dump() for p in cohort],"faculty_members":[f.model_dump() for f in faculty],
          "configuration":configuration.model_dump(),"allocation":AllocationSnapshot(activities=[reflection]).model_dump(),"activity_id":"reflection"}
    client=TestClient(app)

    same=client.post("/api/allocations/edit",json={**base,"participant_id":"P0","target_group_id":"f0","swap_with_id":"P2"})
    assert same.status_code==200 and "requires_confirmation" not in same.json()
    edited=AllocationSnapshot.model_validate(same.json()["allocation"])
    sessions={session.participant_id:session for session in edited.activities[0].sessions}
    assert sessions["P2"].start_time=="10:00 AM" and sessions["P0"].start_time=="10:40 AM"
    assert sessions["P2"].faculty_id==sessions["P0"].faculty_id=="f0"

    cross_base={**base,"allocation":edited.model_dump()}
    cross=client.post("/api/allocations/edit",json={**cross_base,"participant_id":"P0","target_group_id":"f1","swap_with_id":"P3"})
    assert cross.status_code==200 and "requires_confirmation" not in cross.json()
    cross_allocation=AllocationSnapshot.model_validate(cross.json()["allocation"])
    cross_sessions={session.participant_id:session for session in cross_allocation.activities[0].sessions}
    assert cross_sessions["P0"].faculty_id=="f1" and cross_sessions["P3"].faculty_id=="f0"
    assert len({(session.faculty_id,session.start_time) for session in cross_sessions.values()})==4

    export_payload={"participants":[p.model_dump() for p in cohort],"faculty_members":[f.model_dump() for f in faculty],
                    "configuration":configuration.model_dump(),"allocation":cross_allocation.model_dump()}
    excel=client.post("/api/export/editable",json=export_payload)
    assert excel.status_code==200
    values=[cell.value for row in load_workbook(io.BytesIO(excel.content))["My Reflections"].iter_rows() for cell in row]
    assert "10:40 AM" in values and "Person 3" in values
    pdf=client.post("/api/export/pdf/reflection",json=export_payload)
    assert pdf.status_code==200
    pdf_text="\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "10:40 AM" in pdf_text and "Person 3" in pdf_text
