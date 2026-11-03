import io
from collections import Counter
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from app.models import AllocationRequest, OptimizeRequest, ScenarioCompareRequest, SwapRequest
from app.services.excel import blank_template, export_workbook, parse_excel
from app.services.pdf_export import export_pdf
from app.services.optimizer import optimize
from app.services.scoring import score_allocation, validate_allocation
from app.services.normalization import display_gender, display_university, normalize_university, university_directory

app = FastAPI(title="AIP Smart Group Allocator API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/health")
def health(): return {"status": "healthy", "service": "allocator-api"}

@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".xlsx"): raise HTTPException(400, "Only .xlsx files are accepted")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024: raise HTTPException(413, "File exceeds the 10 MB limit")
    try:
        participants, columns = parse_excel(data)
    except Exception as exc: raise HTTPException(422, str(exc))
    missing = [name for name in ("Name", "Gender", "University")
               if not any(column.casefold() == name.casefold() for column in columns)]
    if missing: raise HTTPException(422, f"Missing required columns: {', '.join(missing)}")
    duplicates = [name for name, count in Counter(p.name.casefold() for p in participants).items() if count > 1]
    return {"participants": [p.model_dump() for p in participants], "columns": columns, "duplicate_names": duplicates}

@app.post("/api/participants/validate")
def validate_participants(items: list[dict]):
    errors=[]; normalized=[]; ids=[]
    for index, item in enumerate(items, start=1):
        pid=str(item.get("id", "")).strip(); name=str(item.get("name", "")).strip()
        attributes=item.get("attributes") or {}; gender=display_gender(attributes.get("Gender")); university=display_university(attributes.get("University"))
        if not pid: errors.append(f"Participant {index}: internal ID is missing")
        if not name: errors.append(f"Participant {index}: name is required")
        if not gender: errors.append(f"Participant {index}: choose a valid gender option")
        if not university: errors.append(f"Participant {index}: university is required")
        ids.append(pid); normalized.append({"id":pid,"name":name,"attributes":{"Gender":gender,"University":university,"UniversityId":normalize_university(university)}})
    duplicates=[pid for pid,count in Counter(ids).items() if pid and count>1]
    if duplicates: errors.append("Duplicate participant IDs were detected")
    if errors: raise HTTPException(422, errors)
    return {"valid":True,"count":len(items),"participants":normalized}

@app.get("/api/universities")
def universities(): return {"universities":university_directory(),"count":len(university_directory())}

@app.post("/api/optimize")
def run_optimizer(request: OptimizeRequest):
    try:
        result = optimize(request); metrics = score_allocation(request.participants, request.configuration, result)
        return {"allocation": result, "metrics": metrics}
    except ValueError as exc: raise HTTPException(422, str(exc))

@app.post("/api/allocations/validate")
def validate(request: AllocationRequest):
    errors = validate_allocation(request.participants, request.configuration, request.allocation)
    return {"valid": not errors, "errors": errors}

@app.post("/api/allocations/score")
def score(request: AllocationRequest): return score_allocation(request.participants, request.configuration, request.allocation)

@app.post("/api/allocations/swap")
def swap(request: SwapRequest):
    allocation = request.allocation.model_copy(deep=True)
    target = next((a for a in allocation.activities if a.activity_id == request.activity_id), None)
    if not target: raise HTTPException(404, "Activity not found")
    if target.locked: raise HTTPException(409, "This activity is locked")
    ga = next((g for g in target.groups if request.participant_a in g.participant_ids), None)
    gb = next((g for g in target.groups if request.participant_b in g.participant_ids), None)
    if not ga or not gb: raise HTTPException(422, "Both participants must be assigned")
    ia, ib = ga.participant_ids.index(request.participant_a), gb.participant_ids.index(request.participant_b)
    ga.participant_ids[ia], gb.participant_ids[ib] = request.participant_b, request.participant_a
    errors = validate_allocation(request.participants, request.configuration, allocation)
    if errors: raise HTTPException(422, errors)
    return {"allocation": allocation, "metrics": score_allocation(request.participants, request.configuration, allocation)}

@app.post("/api/scenarios/compare")
def compare(request: ScenarioCompareRequest):
    results=[]
    for scenario in request.scenarios:
        result = optimize(OptimizeRequest(participants=request.participants, configuration=scenario.configuration))
        results.append({"name": scenario.name, "allocation": result, "metrics": score_allocation(request.participants, scenario.configuration, result)})
    return {"scenarios": results}

@app.post("/api/export")
def export(request: AllocationRequest):
    metrics = score_allocation(request.participants, request.configuration, request.allocation)
    data = export_workbook(request.participants, request.allocation, metrics, request.configuration)
    return StreamingResponse(io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=AIP-allocations.xlsx"})

@app.post("/api/export/pdf")
def export_results_pdf(request: AllocationRequest):
    errors=validate_allocation(request.participants,request.configuration,request.allocation)
    if errors: raise HTTPException(422,errors)
    data=export_pdf(request.participants,request.allocation)
    return StreamingResponse(io.BytesIO(data),media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=AIP_Group_Allocations.pdf"})

def sample_frame(blank=False):
    import pandas as pd
    universities = ["Cairo University", "Ain Shams University", "Alexandria University", "German University in Cairo", "American University in Cairo"]
    names = ["Ahmed Hassan", "Mariam Adel", "Omar Khaled", "Nour Ahmed", "Youssef Ali", "Salma Hossam", "Karim Tarek", "Dina Samir", "Mostafa Emad", "Farah Wael", "Hana Mahmoud", "Ali Nasser", "Laila Sherif", "Ziad Amr", "Reem Ashraf", "Tamer Salah", "Aya Magdy", "Hussein Fathy", "Rana Ayman", "Adel Sameh", "Mona Yasser", "Khaled Ehab", "Sara Hesham", "Amr Gamal", "Nada Osama", "Mahmoud Reda", "Yara Essam", "Hazem Rami", "Mai Alaa", "Fady Nabil"]
    rows=[] if blank else [{"Name": n, "Gender": "Female" if i % 2 else "Male", "University": universities[i%5]} for i,n in enumerate(names)]
    out=io.BytesIO(); pd.DataFrame(rows, columns=["Name","Gender","University"]).to_excel(out,index=False); out.seek(0); return out

@app.get("/api/sample-template")
def template(): return StreamingResponse(io.BytesIO(blank_template()), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition":"attachment; filename=AIP-participant-template.xlsx"})
