import io
import re
import uuid
from typing import List
import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl import Workbook
from openpyxl.worksheet.datavalidation import DataValidation
from app.models import AllocationSnapshot, FacultyMember, Participant, SupportMember
from app.services.normalization import display_gender, display_university, normalize_university


MASTER_COLUMNS = ["Adjective", "IT Name", "Deloitte Email", "Candidate Name", "Personal Email", "University",
                  "Years of Relevant Experience", "Gender", "L3 Offering", "Day 1", "Day 2", "Day 3", "Day 4", "Day 5"]
CHEMISTRY_TYPES = {"pioneer", "driver", "guardian", "integrator"}


def _value(value):
    if pd.isna(value): return None
    if hasattr(value, "item"):
        try: return value.item()
        except ValueError: pass
    if hasattr(value, "isoformat"): return value.isoformat()
    return value


def normalize_person_name(value: object) -> str:
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", str(value).casefold()).strip()


def parse_excel(data: bytes) -> tuple[List[Participant], List[str]]:
    frame = pd.read_excel(io.BytesIO(data), dtype=object)
    frame.columns = [str(c).strip() for c in frame.columns]
    canonical = {column: required for column in frame.columns
                 for required in ("Name", "Candidate Name", "Gender", "University", "L3 Offering")
                 if column.casefold() == required.casefold()}
    frame = frame.rename(columns=canonical)
    name_col = next((c for c in frame.columns if c.casefold() in {"name", "candidate name"}), None)
    if not name_col: raise ValueError("The workbook must contain a Candidate Name column")
    participants = []
    for index, row in frame.iterrows():
        name = row.get(name_col)
        if pd.isna(name) or not str(name).strip(): raise ValueError(f"Name is missing on spreadsheet row {index + 2}")
        raw_id = row.get("Participant ID") if "Participant ID" in frame.columns else None
        pid = str(raw_id).strip() if raw_id is not None and not pd.isna(raw_id) else f"P-{uuid.uuid4().hex[:10]}"
        gender = display_gender(row.get("Gender"))
        university = display_university(row.get("University"))
        if not gender: raise ValueError(f"Gender is missing or unsupported on spreadsheet row {index + 2}")
        if not university: raise ValueError(f"University is missing on spreadsheet row {index + 2}")
        attrs = {str(column): _value(row.get(column)) for column in frame.columns if column not in {name_col, "Participant ID"}}
        attrs.update({"Gender": gender, "University": university, "UniversityId": normalize_university(university)})
        if "L3 Offering" in frame.columns:
            attrs["L3 Offering"] = str(_value(row.get("L3 Offering")) or "").strip()
        participants.append(Participant(id=pid, name=str(name), attributes=attrs))
    return participants, list(frame.columns)


def parse_chemistry(data: bytes) -> list[dict]:
    frame = pd.read_excel(io.BytesIO(data), dtype=object)
    frame.columns = [str(c).strip() for c in frame.columns]
    lookup = {c.casefold(): c for c in frame.columns}
    missing = [c for c in ("Name", "Primary", "Secondary") if c.casefold() not in lookup]
    if missing: raise ValueError(f"Missing required columns: {', '.join(missing)}")
    records = []
    for index, row in frame.iterrows():
        name = str(_value(row[lookup["name"]]) or "").strip()
        primary = str(_value(row[lookup["primary"]]) or "").strip().title()
        secondary = str(_value(row[lookup["secondary"]]) or "").strip().title()
        if not name: raise ValueError(f"Name is missing on spreadsheet row {index + 2}")
        if primary.casefold() not in CHEMISTRY_TYPES or secondary.casefold() not in CHEMISTRY_TYPES:
            raise ValueError(f"Unsupported Business Chemistry value on spreadsheet row {index + 2}")
        records.append({"source_name": name, "primary": primary, "secondary": secondary,
                        "normalized_name": normalize_person_name(name)})
    return records


def match_chemistry(participants: list[Participant], records: list[dict]) -> dict:
    index = {}
    for person in participants: index.setdefault(normalize_person_name(person.name), []).append(person)
    matched, review = [], []
    for record in records:
        candidates = index.get(record["normalized_name"], [])
        if len(candidates) == 1:
            matched.append({**record, "participant_id": candidates[0].id})
        else:
            review.append({**record, "candidate_ids": [p.id for p in candidates]})
    return {"matched": matched, "requires_review": review}


def blank_template() -> bytes:
    output = io.BytesIO(); workbook = Workbook(); sheet = workbook.active
    sheet.title = "Participants"; sheet.append(["Name", "Gender", "University"])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="246B9E")
    sheet.freeze_panes = "A2"; sheet.auto_filter.ref = "A1:C201"
    sheet.column_dimensions["A"].width = 30; sheet.column_dimensions["B"].width = 18; sheet.column_dimensions["C"].width = 38
    validation = DataValidation(type="list", formula1='"Male,Female"', allow_blank=False)
    validation.error = "Only Male or Female is accepted. Please use the dropdown."
    validation.errorTitle = "Invalid gender"; validation.prompt = "Select Male or Female."
    validation.promptTitle = "Gender"; validation.showErrorMessage = True; validation.showInputMessage = True
    sheet.add_data_validation(validation); validation.add("B2:B201")
    workbook.save(output); return output.getvalue()


def safe(value):
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def export_workbook(participants, allocation: AllocationSnapshot, metrics, configuration) -> bytes:
    output = io.BytesIO(); pmap = {p.id: p for p in participants}
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        assignment_rows = {p.id: {"Participant ID": safe(p.id), "Name": safe(p.name)} for p in participants}
        for activity in allocation.activities:
            rows=[]
            for group in activity.groups:
                for pid in group.participant_ids:
                    rows.append({"Group": group.name, "Participant ID": safe(pid), "Name": safe(pmap[pid].name)})
                    assignment_rows[pid][activity.activity_name] = group.name
            pd.DataFrame(rows).to_excel(writer, sheet_name=activity.activity_name[:31], index=False)
        for pid, value in metrics.get("participant_exposure", {}).items(): assignment_rows[pid]["Unique Teammates"] = value
        pd.DataFrame(assignment_rows.values()).to_excel(writer, sheet_name="Participant Assignments", index=False)
        pd.DataFrame([{"Metric": k, "Value": safe(v)} for k,v in metrics.items() if not isinstance(v, dict)]).to_excel(writer, sheet_name="Diversity Metrics", index=False)
        pd.DataFrame([{"Schema Version": configuration.schema_version, "Seed": configuration.seed,
                       "Solver Time Limit": configuration.time_limit_seconds}]).to_excel(writer, sheet_name="Configuration Summary", index=False)
        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
            for cell in ws[1]: cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="163B64")
            for column in ws.columns:
                ws.column_dimensions[column[0].column_letter].width = min(40, max(12, max(len(str(c.value or "")) for c in column) + 2))
    return output.getvalue()


def export_week2_workbook(participants: list[Participant], allocation: AllocationSnapshot,
                          faculty_members: list[FacultyMember], support_members: list[SupportMember]) -> bytes:
    output=io.BytesIO(); wb=Workbook(); wb.remove(wb.active)
    names={p.id:p.name for p in participants}; names.update({p.id:p.name for p in support_members})
    faculty={f.id:f for f in faculty_members}
    titles={"main":"Main Groups","quiz":"Quiz Night","team":"Team Building","bus":"BUS Teams","reflection":"MyReflection","hotel":"Hotel Rooms"}
    for activity in allocation.activities:
        if activity.activity_id not in titles: continue
        ws=wb.create_sheet(titles[activity.activity_id]); ws.sheet_view.showGridLines=False; ws.freeze_panes="A2"
        if activity.activity_id=="hotel":
            ws.append(["Room","Occupant 1","Occupant 2"])
            for g in activity.groups: ws.append([g.name,names.get(g.participant_ids[0],g.participant_ids[0]),names.get(g.participant_ids[1],"Single Occupancy") if len(g.participant_ids)>1 else "Single Occupancy"])
        elif activity.activity_id=="reflection":
            ws.append(["Faculty Member","Faculty Offering","Assigned New Hire"])
            for g in activity.groups:
                f=faculty.get(g.id)
                for pid in g.participant_ids: ws.append([g.name,f.offering if f else "",names.get(pid,pid)])
        elif activity.activity_id=="bus":
            ws.append(["BUS Team","Role","Name"])
            support_ids={x.id for x in support_members}
            for g in activity.groups:
                for pid in g.participant_ids: ws.append([g.name,"Support" if pid in support_ids else "New Hire",names.get(pid,pid)])
        else:
            ws.append(["Group","Participant Name"])
            for g in activity.groups:
                for pid in g.participant_ids: ws.append([g.name,names.get(pid,pid)])
        for cell in ws[1]: cell.font=Font(bold=True,color="FFFFFF");cell.fill=PatternFill("solid",fgColor="163B64")
        for row in range(2,ws.max_row+1):
            if row%2==0:
                for cell in ws[row]: cell.fill=PatternFill("solid",fgColor="F3F7FA")
        for col in ws.columns: ws.column_dimensions[col[0].column_letter].width=min(45,max(16,max(len(str(c.value or "")) for c in col)+2))
        ws.print_area=ws.dimensions;ws.sheet_properties.pageSetUpPr.fitToPage=True;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
    wb.save(output);return output.getvalue()
