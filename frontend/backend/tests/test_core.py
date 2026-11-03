import io
import pandas as pd
from openpyxl import load_workbook
from pypdf import PdfReader
from fastapi.testclient import TestClient
from app.main import app
from app.models import *
from app.services.optimizer import group_sizes, optimize
from app.services.scoring import score_allocation, validate_allocation
from app.services.normalization import display_gender, normalize_university, resolve_university, university_directory
from app.services.excel import blank_template

def people(n=30):
    return [Participant(id=f"P{i}", name=f"Person {i}", attributes={"Gender":"Female" if i%2 else "Male", "University":f"University {i%8}"}) for i in range(n)]

def config(n=30):
    return Configuration(activities=[Activity(id="main",name="Main Groups",mode="max_size",value=6), Activity(id="sports",name="Sports Day",mode="max_size",value=5), Activity(id="quiz",name="Quiz Night",mode="group_count",value=5)], factors=[Factor(id="gender",name="Gender",source_column="Gender"), Factor(id="dept",name="Department",source_column="Department")], time_limit_seconds=4)

def test_group_sizes():
    assert group_sizes(29,"max_size",6)==[6,6,6,6,5]
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
        "Gender": "Female" if i % 2 else "Male", "University": f"University {i % 4}"
    }) for i in range(8)]
    c = Configuration(activities=[Activity(id="main", name="Main", mode="max_size", value=4)], time_limit_seconds=5)
    a = optimize(OptimizeRequest(participants=p, configuration=c))
    score = score_allocation(p, c, a)
    assert score["same_university_pairs"] == 0
    for detail in score["activity_group_details"]["main"]:
        assert detail["gender_counts"] == {"male": 2, "female": 2}

def test_unavoidable_university_duplicates_are_counted_exactly():
    p = [Participant(id=f"P{i}", name=f"Person {i}", attributes={
        "Gender": "Female" if i % 2 else "Male", "University": "Only University"
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
