import io
import math
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import AllocationSnapshot, Participant


ACTIVITY_TITLES = {"main": "MAIN TEAMS", "sports": "SPORTS DAY GROUPS", "quiz": "QUIZ NIGHT GROUPS"}


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
    rows = [[Paragraph(_team_label(group_index), title_style), ""]]
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


def export_pdf(participants: list[Participant], allocation: AllocationSnapshot) -> bytes:
    output = io.BytesIO()
    people = {person.id: person.name for person in participants}
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=14 * mm, leftMargin=14 * mm,
                                 topMargin=12 * mm, bottomMargin=12 * mm,
                                 title="AIP Group Allocations", author="AIP Onboarding Program")
    styles = getSampleStyleSheet()
    story = []
    program = ParagraphStyle("Program", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10,
                             leading=12, textColor=colors.HexColor("#2F80A8"), alignment=TA_CENTER, spaceAfter=3)
    activity_style = ParagraphStyle("Activity", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=20,
                                    leading=23, textColor=colors.HexColor("#163B64"), alignment=TA_CENTER, spaceAfter=3)
    subtitle = ParagraphStyle("Subtitle", parent=styles["BodyText"], fontSize=8,
                              textColor=colors.HexColor("#64748B"), alignment=TA_CENTER, spaceAfter=8)
    usable_width = A4[0] - 28 * mm

    for activity_index, activity in enumerate(allocation.activities):
        if activity_index:
            story.append(PageBreak())
        story.extend([Paragraph("AIP ONBOARDING PROGRAM", program),
                      Paragraph(ACTIVITY_TITLES.get(activity.activity_id, escape(activity.activity_name.upper())), activity_style),
                      Paragraph("Group allocations", subtitle)])
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
