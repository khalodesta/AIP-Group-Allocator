import io
import uuid
from typing import List
import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl import Workbook
from openpyxl.worksheet.datavalidation import DataValidation
from app.models import AllocationSnapshot, Participant
from app.services.normalization import display_gender, display_university, normalize_university


def parse_excel(data: bytes) -> tuple[List[Participant], List[str]]:
    frame = pd.read_excel(io.BytesIO(data), dtype=object)
    frame.columns = [str(c).strip() for c in frame.columns]
    canonical = {column: required for column in frame.columns
                 for required in ("Name", "Gender", "University")
                 if column.casefold() == required.casefold()}
    frame = frame.rename(columns=canonical)
    name_col = next((c for c in frame.columns if c.lower() == "name"), None)
    if not name_col: raise ValueError("The workbook must contain a Name column")
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
        attrs = {"Gender": gender, "University": university, "UniversityId": normalize_university(university)}
        participants.append(Participant(id=pid, name=str(name), attributes=attrs))
    return participants, list(frame.columns)


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
