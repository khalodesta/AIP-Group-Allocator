import io
import re
import uuid
from datetime import datetime
from typing import List
import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from app.models import AllocationSnapshot, FacultyMember, Participant, SupportMember
from app.services.normalization import display_gender, display_offering, display_university, normalize_university


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
            attrs["L3 Offering"] = display_offering(_value(row.get("L3 Offering"))) or ""
        participants.append(Participant(id=pid, name=str(name), attributes=attrs))
    return participants, list(frame.columns)


def parse_support_excel(data: bytes) -> list[SupportMember]:
    """Read editable exports and legacy name-only staff sheets without guessing."""
    workbook = pd.ExcelFile(io.BytesIO(data))
    sheet = "Support Team" if "Support Team" in workbook.sheet_names else workbook.sheet_names[0]
    frame = pd.read_excel(workbook, sheet_name=sheet, dtype=object)
    columns = {str(column).strip().casefold(): column for column in frame.columns}
    name_column = columns.get("name", columns.get("support name"))
    if name_column is None:
        raise ValueError("The support workbook must contain a Name column")
    result = []
    used_ids = set()
    for index, row in frame.iterrows():
        name = _value(row.get(name_column))
        if name is None or not str(name).strip():
            raise ValueError(f"Support member name is missing on spreadsheet row {index + 2}")
        raw_id = _value(row.get(columns.get("support id", columns.get("id"))))
        identifier = str(raw_id).strip() if raw_id else f"S-{uuid.uuid4().hex[:10]}"
        if identifier in used_ids:
            raise ValueError(f"Duplicate support ID on spreadsheet row {index + 2}")
        used_ids.add(identifier)
        raw_gender = _value(row.get(columns.get("gender")))
        gender = display_gender(raw_gender)
        if raw_gender and not gender:
            raise ValueError(f"Support gender must be Male or Female on spreadsheet row {index + 2}")
        raw_category = _value(row.get(columns.get("support category", columns.get("category"))))
        category = str(raw_category).strip() if raw_category else None
        if category and category not in {"Support Lead", "Analyst Support"}:
            raise ValueError(f"Support category must be Support Lead or Analyst Support on spreadsheet row {index + 2}")
        result.append(SupportMember(id=identifier, name=str(name).strip(), gender=gender, category=category))
    return result


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


HOTEL_SUMMARY_LABELS = {
    "total_rooms": "Total rooms required",
    "new_hire_shared_rooms": "New-hire shared rooms",
    "new_hire_analyst_shared_rooms": "New-hire + Analyst Support shared rooms",
    "single_new_hire_rooms": "Single new-hire rooms",
    "single_support_lead_rooms": "Single Support Lead rooms",
    "single_analyst_support_rooms": "Single Analyst Support rooms",
    "single_faculty_rooms": "Single faculty rooms",
    "other_shared_rooms": "Approved manual room arrangements",
}


def hotel_room_summary(activity, participants, support_members, faculty_members):
    """Calculate counts from the current manifest, including manual changes."""
    hires = {person.id for person in participants}
    supports = {person.id: person for person in support_members}
    faculty = {person.id for person in faculty_members}
    summary = {key: 0 for key in HOTEL_SUMMARY_LABELS if key != "other_shared_rooms"}
    summary["total_rooms"] = len({group.id for group in activity.groups})
    for room in activity.groups:
        ids = room.participant_ids
        if len(ids) == 2 and all(pid in hires for pid in ids):
            summary["new_hire_shared_rooms"] += 1
        elif len(ids) == 2 and sum(pid in hires for pid in ids) == 1 and any(
                pid in supports and supports[pid].category == "Analyst Support" for pid in ids):
            summary["new_hire_analyst_shared_rooms"] += 1
        elif len(ids) == 1:
            pid = ids[0]
            if pid in hires:
                summary["single_new_hire_rooms"] += 1
            elif pid in faculty:
                summary["single_faculty_rooms"] += 1
            elif pid in supports and supports[pid].category == "Support Lead":
                summary["single_support_lead_rooms"] += 1
            elif pid in supports and supports[pid].category == "Analyst Support":
                summary["single_analyst_support_rooms"] += 1
    remaining = summary["total_rooms"] - sum(value for key, value in summary.items() if key != "total_rooms")
    if remaining > 0:
        summary["other_shared_rooms"] = remaining
    return summary


def export_workbook(participants, allocation: AllocationSnapshot, metrics, configuration,
                    faculty_members=None, support_members=None) -> bytes:
    output = io.BytesIO()
    people = {p.id: p.name for p in participants}
    people.update({p.id: p.name for p in (support_members or [])})
    people.update({p.id: p.name for p in (faculty_members or [])})
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        assignment_rows = {p.id: {"Participant ID": safe(p.id), "Name": safe(p.name)} for p in participants}
        for activity in allocation.activities:
            rows=[]
            for group in activity.groups:
                for pid in group.participant_ids:
                    rows.append({"Group": safe(group.name), "Participant ID": safe(pid), "Name": safe(people.get(pid, pid))})
                    if pid in assignment_rows:
                        assignment_rows[pid]["My Reflections" if activity.activity_id == "reflection" else activity.activity_name] = safe(group.name)
            title = "My Reflections" if activity.activity_id == "reflection" else activity.activity_name
            pd.DataFrame(rows).to_excel(writer, sheet_name=title[:31], index=False)
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
    participant_sheet=wb.create_sheet("Participants")
    attribute_columns=list(dict.fromkeys(["Gender","University",*(key for person in participants for key in person.attributes)]))
    participant_sheet.append(["Participant ID","Name",*attribute_columns])
    for person in participants:
        participant_sheet.append([person.id,person.name,*(person.attributes.get(key) for key in attribute_columns)])
    names={p.id:p.name for p in participants}; names.update({p.id:p.name for p in support_members})
    names.update({p.id:p.name for p in faculty_members})
    faculty={f.id:f for f in faculty_members}
    roles={p.id:"New Hire" for p in participants}
    roles.update({p.id:p.category or "Support category required" for p in support_members})
    roles.update({p.id:"Faculty" for p in faculty_members})
    titles={"main":"Main Groups","quiz":"Quiz Night","team":"Team Building","bus":"BUS Teams","reflection":"My Reflections","hotel":"Hotel Rooms","sports":"Sports Day"}
    for activity in allocation.activities:
        if activity.activity_id not in titles: continue
        ws=wb.create_sheet(titles[activity.activity_id]); ws.sheet_view.showGridLines=False; ws.freeze_panes="A2"
        section_title_rows=[];section_header_rows=[]
        if activity.activity_id=="hotel":
            ws.append(["Room","Occupant 1","Occupant 1 Role","Occupant 2","Occupant 2 Role","Occupancy"])
            for g in activity.groups:
                occupants=g.participant_ids
                ws.append([g.name,names.get(occupants[0],occupants[0]) if occupants else "",
                           roles.get(occupants[0],"Unknown") if occupants else "",
                           names.get(occupants[1],occupants[1]) if len(occupants)>1 else "",
                           roles.get(occupants[1],"Unknown") if len(occupants)>1 else "",
                           len(occupants)])
        elif activity.activity_id=="reflection":
            scheduled={session.participant_id:session for session in activity.sessions}
            people={p.id:p for p in participants}
            if scheduled:
                ws.freeze_panes="A3"
                for group_index,g in enumerate(activity.groups):
                    f=faculty.get(g.id);section_title_rows.append(ws.max_row+1)
                    ws.append([f"{g.name} — {display_offering(f.offering) if f else 'Offering not provided'}"]);ws.merge_cells(start_row=ws.max_row,start_column=1,end_row=ws.max_row,end_column=7)
                    section_header_rows.append(ws.max_row+1);ws.append(["#","Start Time","End Time","Assigned New Hire","Participant Offering","Offering Match","Prayer Status"])
                    sessions=sorted((s for s in activity.sessions if s.faculty_id==g.id),key=lambda s:datetime.strptime(s.start_time,"%I:%M %p"))
                    for index,session in enumerate(sessions,1):
                        pid=session.participant_id
                        ws.append([index,session.start_time,session.end_time,names.get(pid,pid),display_offering(people[pid].attributes.get("L3 Offering")) or "","Match" if session.offering_match else "Mismatch","Before Prayer" if session.before_prayer else "After Prayer"])
                    if group_index<len(activity.groups)-1: ws.append([])
            else:
                ws.append(["Faculty Member","Faculty Offering","Assigned New Hire"])
                for g in activity.groups:
                    f=faculty.get(g.id)
                    for pid in g.participant_ids: ws.append([g.name,display_offering(f.offering) if f else "",names.get(pid,pid)])
        elif activity.activity_id=="bus":
            ws.append(["BUS Team","Role","Name"])
            for g in activity.groups:
                for pid in g.participant_ids: ws.append([g.name,roles.get(pid,"Unknown"),names.get(pid,pid)])
        else:
            ws.append(["Group","Participant Name"])
            for g in activity.groups:
                for pid in g.participant_ids: ws.append([g.name,names.get(pid,pid)])
        for cell in ws[1]: cell.font=Font(bold=True,color="FFFFFF");cell.fill=PatternFill("solid",fgColor="163B64")
        for row in range(2,ws.max_row+1):
            if row%2==0:
                for cell in ws[row]: cell.fill=PatternFill("solid",fgColor="F3F7FA")
        for row in section_title_rows:
            for cell in ws[row]: cell.font=Font(bold=True,color="FFFFFF");cell.fill=PatternFill("solid",fgColor="163B64")
        for row in section_header_rows:
            for cell in ws[row]: cell.font=Font(bold=True,color="FFFFFF");cell.fill=PatternFill("solid",fgColor="2F80A8")
        for column_index,col in enumerate(ws.columns,1): ws.column_dimensions[get_column_letter(column_index)].width=min(45,max(16,max(len(str(c.value or "")) for c in col)+2))
        ws.print_area=ws.dimensions;ws.sheet_properties.pageSetUpPr.fitToPage=True;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
    support_sheet=wb.create_sheet("Support Team")
    support_sheet.append(["Support ID","Name","Gender","Support Category"])
    for member in support_members:
        support_sheet.append([member.id,member.name,member.gender,member.category])
    for column,choices in (("C", "Male,Female"),("D", "Support Lead,Analyst Support")):
        validation=DataValidation(type="list",formula1=f'"{choices}"',allow_blank=False)
        validation.showErrorMessage=True;validation.errorStyle="stop"
        support_sheet.add_data_validation(validation);validation.add(f"{column}2:{column}201")
    faculty_sheet=wb.create_sheet("Faculty")
    faculty_sheet.append(["Faculty ID","Name","Offering"])
    for member in faculty_members:
        faculty_sheet.append([member.id,member.name,display_offering(member.offering)])
    hotel=next((activity for activity in allocation.activities if activity.activity_id=="hotel"),None)
    if hotel:
        summary_sheet=wb.create_sheet("Hotel Summary")
        summary_sheet.append(["Occupancy summary","Rooms"])
        for key,value in hotel_room_summary(hotel,participants,support_members,faculty_members).items():
            summary_sheet.append([HOTEL_SUMMARY_LABELS[key],value])
    for sheet in wb.worksheets:
        # Every text cell is escaped, including imported names and faculty labels.
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value,str):cell.value=safe(cell.value)
        if sheet.title in {"Participants","Support Team","Faculty","Hotel Summary"}:
            sheet.freeze_panes="A2";sheet.sheet_view.showGridLines=False
            for cell in sheet[1]:cell.font=Font(bold=True,color="FFFFFF");cell.fill=PatternFill("solid",fgColor="163B64")
            for index,column in enumerate(sheet.columns,1):
                sheet.column_dimensions[get_column_letter(index)].width=min(55,max(16,max(len(str(cell.value or "")) for cell in column)+2))
    wb.save(output);return output.getvalue()
