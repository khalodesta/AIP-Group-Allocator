from __future__ import annotations

import io
import math
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import AllocationSnapshot, FacultyMember, Participant, SupportMember
from app.services.excel import HOTEL_SUMMARY_LABELS, hotel_room_summary
from app.services.normalization import display_offering


ACTIVITY_TITLES = {"main": "MAIN TEAMS", "sports": "SPORTS DAY GROUPS", "quiz": "QUIZ NIGHT GROUPS",
                   "reflection": "My Reflections", "hotel": "PRIVATE HOTEL ROOM MANIFEST"}


def _team_label(index: int) -> str:
    label = ""
    number = index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        label = chr(65 + remainder) + label
    return f"TEAM {label}"


def _team_card(group, group_index: int, people: dict[str, str], width: float, compact: bool, dense: bool) -> Table:
    font_size = 6.3 if dense else (7.6 if compact else 9)
    leading = font_size + 2
    name_style = ParagraphStyle(f"Name-{group_index}", fontName="Helvetica", fontSize=font_size,
                                leading=leading, textColor=colors.HexColor("#17233C"))
    title_style = ParagraphStyle(f"Team-{group_index}", fontName="Helvetica-Bold", fontSize=font_size + 1,
                                 leading=leading + 1, textColor=colors.white)
    rows = [[Paragraph(escape(group.name or _team_label(group_index)), title_style), ""]]
    rows.extend([str(i), Paragraph(escape(people.get(pid, pid)), name_style)]
                for i, pid in enumerate(group.participant_ids, 1))
    number_width = 7 * mm
    card = Table(rows, colWidths=[number_width, width - number_width], repeatRows=1)
    card.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#163B64")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F8FB")]),
        ("TEXTCOLOR", (0, 1), (0, -1), colors.HexColor("#2F80A8")),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 1), (0, -1), font_size),
        ("ALIGN", (0, 1), (0, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD8E5")),
        ("INNERGRID", (0, 1), (-1, -1), 0.35, colors.HexColor("#DFE7EF")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, 0), 5 if compact else 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5 if compact else 6),
        ("TOPPADDING", (0, 1), (-1, -1), 2.5 if compact else 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 2.5 if compact else 4),
    ]))
    return card


def export_pdf(participants: list[Participant], allocation: AllocationSnapshot,
               support_members: list[SupportMember] | None = None,
               activity_ids: set[str] | None = None,
               faculty_members: list[FacultyMember] | None = None) -> bytes:
    output = io.BytesIO()
    people = {person.id: person.name for person in participants}
    people.update({person.id: person.name for person in (support_members or [])})
    people.update({person.id: person.name for person in (faculty_members or [])})
    participant_map = {person.id: person for person in participants}
    faculty_map = {person.id: person for person in (faculty_members or [])}
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=14 * mm, leftMargin=14 * mm,
                                 topMargin=12 * mm, bottomMargin=12 * mm,
                                 title="AIP Hotel Rooms Private" if activity_ids == {"hotel"} else "AIP Group Allocations",
                                 author="AIP Onboarding Program")
    styles = getSampleStyleSheet()
    story = []
    program = ParagraphStyle("Program", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10,
                             leading=12, textColor=colors.HexColor("#2F80A8"), alignment=TA_CENTER, spaceAfter=3)
    activity_style = ParagraphStyle("Activity", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=20,
                                    leading=23, textColor=colors.HexColor("#163B64"), alignment=TA_CENTER, spaceAfter=3)
    subtitle = ParagraphStyle("Subtitle", parent=styles["BodyText"], fontSize=8,
                              textColor=colors.HexColor("#64748B"), alignment=TA_CENTER, spaceAfter=8)
    usable_width = A4[0] - 28 * mm

    selected = [a for a in allocation.activities
                if (a.activity_id != "hotel" if activity_ids is None else a.activity_id in activity_ids)]
    for activity_index, activity in enumerate(selected):
        if activity_index:
            story.append(PageBreak())
        story.extend([Paragraph("AIP ONBOARDING PROGRAM", program),
                      Paragraph(ACTIVITY_TITLES.get(activity.activity_id, escape(activity.activity_name.upper())), activity_style),
                      Paragraph("Internal accommodation manifest" if activity.activity_id == "hotel" else "Group allocations", subtitle)])
        if activity.activity_id == "hotel":
            roles = {person.id: "New Hire" for person in participants}
            roles.update({person.id: person.category or "Support category required" for person in (support_members or [])})
            roles.update({person.id: "Faculty" for person in (faculty_members or [])})
            summary = hotel_room_summary(activity, participants, support_members or [], faculty_members or [])
            story.append(Paragraph(f"Total rooms required: {summary['total_rooms']}", styles["Heading2"]))
            summary_rows = [["Occupancy summary", "Rooms"]]
            summary_rows.extend([label, str(summary[key])] for key, label in HOTEL_SUMMARY_LABELS.items()
                                if key != "total_rooms" and key in summary)
            summary_table = Table(summary_rows, colWidths=[usable_width - 20*mm, 20*mm], repeatRows=1)
            manifest_style = TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#163B64")),
                ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE", (0,0), (-1,-1), 8),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F5F8FB")]),
                ("GRID", (0,0), (-1,-1), .35, colors.HexColor("#CBD8E5")),
                ("VALIGN", (0,0), (-1,-1), "TOP"),
                ("TOPPADDING", (0,0), (-1,-1), 5),
                ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ])
            summary_table.setStyle(manifest_style)
            story.extend([summary_table, Spacer(1,5*mm)])
            cell_style = ParagraphStyle("HotelCell", parent=styles["BodyText"], fontSize=8, leading=11)
            manifest_rows = [["Room", "Occupants", "Occupant roles", "Occupancy"]]
            for room in activity.groups:
                manifest_rows.append([
                    Paragraph(escape(room.name), cell_style),
                    Paragraph("<br/>".join(escape(people.get(pid,pid)) for pid in room.participant_ids), cell_style),
                    Paragraph("<br/>".join(escape(roles.get(pid,"Unknown")) for pid in room.participant_ids), cell_style),
                    "Single" if len(room.participant_ids) == 1 else str(len(room.participant_ids)),
                ])
            manifest = Table(manifest_rows, colWidths=[22*mm, 76*mm, 58*mm, usable_width-156*mm], repeatRows=1)
            manifest.setStyle(manifest_style)
            story.append(manifest)
            if summary["single_new_hire_rooms"]:
                story.extend([Spacer(1,3*mm), Paragraph(
                    "Single new-hire rooms require accommodation review. Add an available same-gender Analyst Support member or confirm the single-room booking.",
                    styles["BodyText"])])
            continue
        if activity.activity_id == "reflection" and activity.sessions:
            faculty_heading=ParagraphStyle("FacultyHeading",fontName="Helvetica-Bold",fontSize=11,leading=14,textColor=colors.HexColor("#163B64"),spaceBefore=5,spaceAfter=4)
            for group in activity.groups:
                faculty_member=faculty_map.get(group.id)
                heading=f"{group.name} — {display_offering(faculty_member.offering) if faculty_member else 'Offering not provided'}"
                rows=[["#","Time","Participant","Participant Offering","Match","Prayer Status"]]
                sessions=sorted((s for s in activity.sessions if s.faculty_id==group.id),key=lambda session:datetime.strptime(session.start_time,"%I:%M %p"))
                for index,session in enumerate(sessions,1):
                    participant=participant_map[session.participant_id]
                    rows.append([index,f"{session.start_time} - {session.end_time}",participant.name,
                                 display_offering(participant.attributes.get("L3 Offering")) or "",
                                 "Match" if session.offering_match else "Mismatch",
                                 "Before Prayer" if session.before_prayer else "After Prayer"])
                schedule=Table(rows,repeatRows=1,colWidths=[8*mm,32*mm,38*mm,38*mm,22*mm,30*mm])
                schedule.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#163B64")),
                    ("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
                    ("FONTSIZE",(0,0),(-1,-1),7),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F5F8FB")]),
                    ("GRID",(0,0),(-1,-1),.35,colors.HexColor("#CBD8E5")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                    ("LEFTPADDING",(0,0),(-1,-1),3),("RIGHTPADDING",(0,0),(-1,-1),3)]))
                story.extend([Paragraph(escape(heading),faculty_heading),schedule,Spacer(1,3*mm)])
            continue
        group_count = len(activity.groups)
        columns = 2 if group_count <= 12 else (3 if group_count <= 18 else 4)
        dense = columns == 4
        compact = columns == 3 or group_count > 8 or any(len(group.participant_ids) > 8 for group in activity.groups)
        compact = compact or dense
        gutter = 2 * mm if dense else 4 * mm
        card_width = (usable_width - gutter * (columns - 1)) / columns
        cards = [_team_card(group, index, people, card_width, compact, dense)
                 for index, group in enumerate(activity.groups)]
        rows = []
        for row_index in range(math.ceil(group_count / columns)):
            rows.append([cards[index] if index < group_count else ""
                         for index in range(row_index * columns, row_index * columns + columns)])
        grid = Table(rows, colWidths=[card_width] * columns, hAlign="CENTER")
        grid.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), gutter), ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm if compact else 3 * mm),
        ]))
        story.append(KeepTogether([grid, Spacer(1, mm)]))

    document.build(story)
    return output.getvalue()
