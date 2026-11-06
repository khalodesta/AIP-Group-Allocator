import io
from collections import Counter
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from app.models import AllocationEditRequest, AllocationRequest, OptimizeRequest, Participant, ScenarioCompareRequest, SwapRequest
from app.services.excel import blank_template, export_week2_workbook, export_workbook, match_chemistry, parse_chemistry, parse_excel
from app.services.pdf_export import export_pdf
from app.services.optimizer import optimize, schedule_reflection
from app.services.scoring import score_allocation, validate_allocation
from app.services.normalization import display_gender, display_offering, display_university, normalize_university, university_directory

app = FastAPI(title="AIP Smart Group Allocator API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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
    missing = [name for name in ("Gender", "University")
               if not any(column.casefold() == name.casefold() for column in columns)]
    if not any(column.casefold() in {"name", "candidate name"} for column in columns): missing.insert(0, "Candidate Name")
    if missing: raise HTTPException(422, f"Missing required columns: {', '.join(missing)}")
    duplicates = [name for name, count in Counter(p.name.casefold() for p in participants).items() if count > 1]
    return {"participants": [p.model_dump() for p in participants], "columns": columns, "duplicate_names": duplicates}

@app.post("/api/upload/chemistry")
async def upload_chemistry(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".xlsx"): raise HTTPException(400, "Only .xlsx files are accepted")
    try: return {"records": parse_chemistry(await file.read())}
    except Exception as exc: raise HTTPException(422, str(exc))

@app.post("/api/chemistry/match")
def chemistry_match(payload: dict):
    try:
        participants = [Participant.model_validate(x) for x in payload.get("participants", [])]
        return match_chemistry(participants, payload.get("records", []))
    except Exception as exc: raise HTTPException(422, str(exc))

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

def structural_errors(request: AllocationRequest):
    """Validate identity/referential integrity without enforcing optimizer preferences."""
    people={p.id for p in request.participants}; support={p.id for p in request.support_members}
    if len(people)!=len(request.participants): return ["Participant IDs must be unique"]
    errors=[]; config={item.id:item for item in request.configuration.activities}
    for activity in request.allocation.activities:
        ids=[pid for group in activity.groups for pid in group.participant_ids]
        allowed=people|support if activity.activity_id=="bus" else people
        unknown=set(ids)-allowed
        if unknown: errors.append(f"{activity.activity_name}: invalid participant references")
        duplicates=[pid for pid,count in Counter(ids).items() if count>1]
        if duplicates: errors.append(f"{activity.activity_name}: a participant is assigned more than once")
        missing=people-set(ids)
        if missing: errors.append(f"{activity.activity_name}: one or more new hires are missing")
        if activity.activity_id=="bus" and support-set(ids): errors.append("BUS Teams: one or more support members are missing")
        cfg=config.get(activity.activity_id)
        if cfg and cfg.mode=="group_count" and len(activity.groups)!=cfg.value:
            errors.append(f"{activity.activity_name}: group count cannot be changed manually")
        if cfg and cfg.mode=="max_size" and activity.activity_id!="hotel" and any(len(group.participant_ids)>cfg.value for group in activity.groups):
            errors.append(f"{activity.activity_name}: destination is full; swap with a participant instead")
    return errors

def manual_conflicts(request: AllocationRequest):
    allocation=request.allocation; people={p.id:p for p in request.participants}; conflicts=[]
    edited_activity=getattr(request,"activity_id",None)
    def add(rule,message,policy=False,overridable=True,participants=None):
        conflicts.append({"rule":rule,"message":message,"policy_sensitive":policy,"overridable":overridable,
                          "participant_ids":participants or []})
    main=next((a for a in allocation.activities if a.activity_id=="main"),None)
    hotel=next((a for a in allocation.activities if a.activity_id=="hotel"),None)
    main_group={pid:(group.id,group.name) for group in main.groups for pid in group.participant_ids} if main else {}
    if hotel and edited_activity in (None,"main","hotel"):
        for room in hotel.groups:
            occupants=room.participant_ids
            if len(occupants)>2:
                permitted=request.configuration.allow_accommodation_policy_overrides
                add("hotel_capacity",f"{room.name} would exceed the approved capacity of two occupants. Accommodation-policy approval may be required.",True,permitted,occupants)
            if len(occupants)==2:
                left,right=occupants; names=[people[x].name for x in occupants if x in people]
                if left in people and right in people and people[left].attributes.get("Gender")!=people[right].attributes.get("Gender"):
                    permitted=request.configuration.allow_accommodation_policy_overrides
                    add("mixed_gender_room",f"{names[0]} and {names[1]} would share {room.name} despite having different recorded genders. Accommodation-policy approval may be required.",True,permitted,occupants)
    return conflicts

def edit_warning_conflicts(before, after, request: AllocationEditRequest):
    """Only the two administrator-approved optimization warnings, and only when worsened."""
    people={p.id:p for p in request.participants}; conflicts=[]
    def add(rule,message,ids): conflicts.append({"rule":rule,"message":message,"policy_sensitive":False,"overridable":True,"participant_ids":ids})
    def activity(snapshot,activity_id): return next((item for item in snapshot.activities if item.activity_id==activity_id),None)
    def roommate_conflicts(snapshot):
        main,hotel=activity(snapshot,"main"),activity(snapshot,"hotel"); found={}
        if not main or not hotel: return found
        locations={pid:(group.id,group.name) for group in main.groups for pid in group.participant_ids}
        for room in hotel.groups:
            if len(room.participant_ids)!=2: continue
            left,right=room.participant_ids; pair=tuple(sorted((left,right)))
            if locations.get(left) and locations[left][0]==locations.get(right,(None,None))[0]: found[pair]=(room.name,locations[left][1])
        return found
    if request.activity_id in {"main","hotel"}:
        old,new=roommate_conflicts(before),roommate_conflicts(after)
        for pair,(room,group) in new.items():
            if pair not in old:
                add("roommates_same_main",f"{people[pair[0]].name} and {people[pair[1]].name} share {room}. This change would also place them together in {group}.",list(pair))
    if request.activity_id in {"main","quiz","team"}:
        def pair_locations(snapshot):
            result={}
            for item in snapshot.activities:
                if item.activity_id not in {"main","quiz","team"}: continue
                for group in item.groups:
                    for index,left in enumerate(group.participant_ids):
                        for right in group.participant_ids[index+1:]: result.setdefault(tuple(sorted((left,right))),[]).append((item.activity_name,group.name))
            return result
        old,new=pair_locations(before),pair_locations(after)
        for pair,locations in new.items():
            if len(locations)>1 and len(locations)>len(old.get(pair,[])):
                where=" and ".join(f"{activity} {group}" for activity,group in locations)
                add("repeated_teammates",f"{people[pair[0]].name} and {people[pair[1]].name} would be teammates more than once: {where}.",list(pair))
    return conflicts

def reflection_session_errors(activity, people):
    if not activity.sessions: return []
    expected={pid for group in activity.groups for pid in group.participant_ids}; session_ids=[session.participant_id for session in activity.sessions]
    errors=[]
    if set(session_ids)!=expected or len(session_ids)!=len(set(session_ids)): errors.append("MyReflection appointments must assign every participant exactly once")
    group_for={pid:group.id for group in activity.groups for pid in group.participant_ids}
    slots=[]
    for session in activity.sessions:
        if session.participant_id not in people or group_for.get(session.participant_id)!=session.faculty_id: errors.append("MyReflection appointment faculty does not match the saved assignment")
        slots.append((session.faculty_id,session.start_time,session.end_time))
    if len(slots)!=len(set(slots)): errors.append("A faculty member cannot have two participants in the same appointment slot")
    return errors

@app.post("/api/allocations/validate")
def validate(request: AllocationRequest):
    errors = structural_errors(request)
    conflicts=manual_conflicts(request)
    errors.extend(item["message"] for item in conflicts if item["policy_sensitive"] and not item["overridable"])
    reflection=next((a for a in request.allocation.activities if a.activity_id=="reflection"),None)
    if reflection: errors.extend(reflection_session_errors(reflection,{p.id:p for p in request.participants}))
    return {"valid": not errors, "errors": errors, "conflicts": conflicts}

@app.post("/api/allocations/score")
def score(request: AllocationRequest): return score_allocation(request.participants, request.configuration, request.allocation)

@app.post("/api/allocations/swap")
def swap(request: SwapRequest):
    allocation = request.allocation.model_copy(deep=True)
    target = next((a for a in allocation.activities if a.activity_id == request.activity_id), None)
    if not target: raise HTTPException(404, "Activity not found")
    if target.locked: raise HTTPException(409, "This activity is locked")
    if request.activity_id == "bus":
        support_ids={member.id for member in request.support_members}
        if (request.participant_a in support_ids)!=(request.participant_b in support_ids):
            raise HTTPException(422,"Swap support members with support members, or new hires with new hires, so both BUS Teams remain balanced")
    ga = next((g for g in target.groups if request.participant_a in g.participant_ids), None)
    gb = next((g for g in target.groups if request.participant_b in g.participant_ids), None)
    if not ga or not gb: raise HTTPException(422, "Both participants must be assigned")
    ia, ib = ga.participant_ids.index(request.participant_a), gb.participant_ids.index(request.participant_b)
    ga.participant_ids[ia], gb.participant_ids[ib] = request.participant_b, request.participant_a
    if request.activity_id == "reflection":
        try:
            target.sessions = schedule_reflection(target, OptimizeRequest(
                participants=request.participants, configuration=request.configuration,
                faculty_members=request.faculty_members, support_members=request.support_members))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    main = next((a for a in allocation.activities if a.activity_id == "main"), None)
    hotel = next((a for a in allocation.activities if a.activity_id == "hotel"), None)
    if main and hotel:
        main_group={pid:g.id for g in main.groups for pid in g.participant_ids}
        pmap={p.id:p for p in request.participants}
        for room in hotel.groups:
            if len(room.participant_ids)==2:
                left,right=room.participant_ids
                if pmap[left].attributes.get("Gender")!=pmap[right].attributes.get("Gender"):
                    raise HTTPException(422,"Hotel roommates must have the same gender")
                if main_group[left]==main_group[right]:
                    raise HTTPException(422,"This change would place two hotel roommates in the same Main Group. Change the hotel pairing first or choose another swap.")
    errors = validate_allocation(request.participants, request.configuration, allocation)
    if errors: raise HTTPException(422, errors)
    return {"allocation": allocation, "metrics": score_allocation(request.participants, request.configuration, allocation)}

@app.post("/api/allocations/edit")
def edit_allocation(request: AllocationEditRequest):
    before=request.allocation.model_copy(deep=True); allocation=request.allocation.model_copy(deep=True)
    target_activity=next((a for a in allocation.activities if a.activity_id==request.activity_id),None)
    if not target_activity: raise HTTPException(404,"Activity not found")
    if target_activity.locked: raise HTTPException(409,"This activity is locked")
    source_group=next((g for g in target_activity.groups if request.participant_id in g.participant_ids),None)
    target_group=next((g for g in target_activity.groups if g.id==request.target_group_id),None)
    if not source_group or not target_group: raise HTTPException(422,"Participant or destination group was not found")
    if source_group.id==target_group.id and not request.swap_with_id: return {"allocation":allocation,"metrics":score_allocation(request.participants,request.configuration,allocation)}
    if request.activity_id=="reflection" and not request.swap_with_id:
        raise HTTPException(422,"Drop onto an existing MyReflection appointment to exchange available slots")
    if request.swap_with_id:
        swap_group=next((g for g in target_activity.groups if request.swap_with_id in g.participant_ids),None)
        if not swap_group or swap_group.id!=target_group.id: raise HTTPException(422,"Swap participant is not in the destination group")
        if request.swap_with_id==request.participant_id: raise HTTPException(422,"Choose two different people")
        left=source_group.participant_ids.index(request.participant_id);right=target_group.participant_ids.index(request.swap_with_id)
        source_group.participant_ids[left],target_group.participant_ids[right]=request.swap_with_id,request.participant_id
    else:
        source_group.participant_ids.remove(request.participant_id);target_group.participant_ids.append(request.participant_id)

    if request.activity_id=="reflection":
        first=next((session for session in target_activity.sessions if session.participant_id==request.participant_id),None)
        second=next((session for session in target_activity.sessions if session.participant_id==request.swap_with_id),None)
        if not first or not second: raise HTTPException(422,"Both participants must have valid MyReflection appointment slots")
        first.participant_id,second.participant_id=second.participant_id,first.participant_id
        people={p.id:p for p in request.participants}; faculty={f.id:f for f in request.faculty_members}
        for session in (first,second):
            participant_offering=(display_offering(people[session.participant_id].attributes.get("L3 Offering")) or "").casefold()
            faculty_offering=(display_offering(faculty[session.faculty_id].offering) or "").casefold() if session.faculty_id in faculty else ""
            session.offering_match=bool(participant_offering and participant_offering==faculty_offering)

    proposed=request.model_copy(update={"allocation":allocation})
    errors=structural_errors(proposed)
    if errors: raise HTTPException(422,errors)
    errors.extend(reflection_session_errors(target_activity,{p.id:p for p in request.participants}) if request.activity_id=="reflection" else [])
    if errors: raise HTTPException(422,errors)
    conflicts=manual_conflicts(proposed)+edit_warning_conflicts(before,allocation,request)
    if conflicts and not request.allow_override:
        return {"requires_confirmation":True,"conflicts":conflicts}
    prohibited=[item for item in conflicts if not item["overridable"]]
    if prohibited: raise HTTPException(422,[item["message"] for item in prohibited])
    return {"allocation":allocation,"metrics":score_allocation(request.participants,request.configuration,allocation),"conflicts":conflicts}

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
    errors=structural_errors(request)
    if errors: raise HTTPException(422,errors)
    data=export_pdf(request.participants,request.allocation,request.support_members,{"main","quiz","team","sports","bus","reflection"},request.faculty_members)
    return StreamingResponse(io.BytesIO(data),media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=AIP_Group_Allocations.pdf"})

@app.post("/api/export/pdf/{activity_id}")
def export_individual_pdf(activity_id: str, request: AllocationRequest):
    activity=next((item for item in request.allocation.activities if item.activity_id==activity_id),None)
    if not activity: raise HTTPException(404,"Allocation type not found in the current results")
    errors=structural_errors(request)
    if errors: raise HTTPException(422,errors)
    data=export_pdf(request.participants,request.allocation,request.support_members,{activity_id},request.faculty_members)
    return StreamingResponse(io.BytesIO(data),media_type="application/pdf",headers={"Content-Disposition":f"attachment; filename=AIP_{activity_id}.pdf"})

@app.post("/api/export/hotel-pdf")
def export_hotel_pdf(request: AllocationRequest):
    data=export_pdf(request.participants,request.allocation,request.support_members,{"hotel"})
    return StreamingResponse(io.BytesIO(data),media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=AIP_Hotel_Rooms_Private.pdf"})

@app.post("/api/export/editable")
def export_editable(request: AllocationRequest):
    data=export_week2_workbook(request.participants,request.allocation,request.faculty_members,request.support_members)
    return StreamingResponse(io.BytesIO(data),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":"attachment; filename=AIP_Week2_Allocations.xlsx"})

def sample_frame(blank=False):
    import pandas as pd
    universities = ["Cairo University", "Ain Shams University", "Alexandria University", "German University in Cairo", "American University in Cairo"]
    names = ["Ahmed Hassan", "Mariam Adel", "Omar Khaled", "Nour Ahmed", "Youssef Ali", "Salma Hossam", "Karim Tarek", "Dina Samir", "Mostafa Emad", "Farah Wael", "Hana Mahmoud", "Ali Nasser", "Laila Sherif", "Ziad Amr", "Reem Ashraf", "Tamer Salah", "Aya Magdy", "Hussein Fathy", "Rana Ayman", "Adel Sameh", "Mona Yasser", "Khaled Ehab", "Sara Hesham", "Amr Gamal", "Nada Osama", "Mahmoud Reda", "Yara Essam", "Hazem Rami", "Mai Alaa", "Fady Nabil"]
    rows=[] if blank else [{"Name": n, "Gender": "Female" if i % 2 else "Male", "University": universities[i%5]} for i,n in enumerate(names)]
    out=io.BytesIO(); pd.DataFrame(rows, columns=["Name","Gender","University"]).to_excel(out,index=False); out.seek(0); return out

@app.get("/api/sample-template")
def template(): return StreamingResponse(io.BytesIO(blank_template()), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition":"attachment; filename=AIP-participant-template.xlsx"})
