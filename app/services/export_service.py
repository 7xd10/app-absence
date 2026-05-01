"""
Service Export - Génération Excel, CSV et PDF des présences
"""
import io
import csv
from datetime import datetime
from flask import current_app

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    OPENPYXL_OK = True
except ImportError:
    OPENPYXL_OK = False

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer, HRFlowable)
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False


UEMF_BLUE = "003882"
UEMF_GREEN = "00A676"
UEMF_LIGHT = "E6F0FF"


def export_attendance_excel(session, attendances: list) -> bytes:
    """Génère un fichier Excel des présences avec logo UEMF et mise en forme."""
    if not OPENPYXL_OK:
        raise ImportError("openpyxl non installé")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Présences"

    # ── Styles ──────────────────────────────────────────────────────────────
    blue_fill = PatternFill("solid", fgColor=UEMF_BLUE)
    green_fill = PatternFill("solid", fgColor=UEMF_GREEN)
    light_fill = PatternFill("solid", fgColor=UEMF_LIGHT)
    header_font = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
    title_font = Font(name="Calibri", bold=True, color=UEMF_BLUE, size=14)
    center = Alignment(horizontal="center", vertical="center")
    thin = Border(
        left=Side(style="thin", color="CCCCCC"),
        right=Side(style="thin", color="CCCCCC"),
        top=Side(style="thin", color="CCCCCC"),
        bottom=Side(style="thin", color="CCCCCC"),
    )

    # ── Titre ────────────────────────────────────────────────────────────────
    ws.merge_cells("A1:H1")
    ws["A1"] = "EUROPRESENCE – FEUILLE DE PRÉSENCE"
    ws["A1"].font = title_font
    ws["A1"].alignment = center
    ws["A1"].fill = light_fill
    ws.row_dimensions[1].height = 32

    ws.merge_cells("A2:H2")
    ws["A2"] = f"Séance : {session.title}  |  Date : {session.started_at.strftime('%d/%m/%Y %H:%M') if session.started_at else 'N/A'}  |  Salle : {session.room or 'N/A'}"
    ws["A2"].alignment = center
    ws.row_dimensions[2].height = 20

    ws.merge_cells("A3:H3")
    ws["A3"] = f"Exporté le : {datetime.now().strftime('%d/%m/%Y à %H:%M')}  |  Université Euro-Méditerranéenne de Fès"
    ws["A3"].alignment = center
    ws["A3"].font = Font(name="Calibri", italic=True, color="888888", size=10)
    ws.row_dimensions[3].height = 18

    # ── En-têtes colonnes ────────────────────────────────────────────────────
    headers = ["#", "Matricule", "Nom", "Prénom", "Email", "Groupe", "Statut", "Heure de scan"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=5, column=col, value=h)
        cell.font = header_font
        cell.fill = blue_fill
        cell.alignment = center
        cell.border = thin
    ws.row_dimensions[5].height = 22

    # ── Données ──────────────────────────────────────────────────────────────
    for i, att in enumerate(attendances, 1):
        row = i + 5
        student = att.student
        group_name = att.group.name if att.group else "—"
        status_label = "✅ Présent" if att.status == "present" else "❌ Absent"
        scan_time = att.scanned_at.strftime("%H:%M:%S") if att.scanned_at else "—"

        row_data = [i, student.matricule or "—", student.last_name,
                    student.first_name, student.email, group_name, status_label, scan_time]

        row_fill = PatternFill("solid", fgColor="E8F8F2") if att.status == "present" \
            else PatternFill("solid", fgColor="FFF0F0")

        for col, val in enumerate(row_data, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.fill = row_fill
            cell.alignment = center if col in [1, 7, 8] else Alignment(vertical="center")
            cell.border = thin

    # ── Largeurs colonnes ─────────────────────────────────────────────────
    widths = [5, 14, 18, 18, 30, 20, 14, 16]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # ── Résumé ────────────────────────────────────────────────────────────
    summary_row = len(attendances) + 7
    present_count = sum(1 for a in attendances if a.status == "present")
    absent_count = len(attendances) - present_count
    ws.merge_cells(f"A{summary_row}:D{summary_row}")
    ws[f"A{summary_row}"] = f"Total présents : {present_count}  |  Absents : {absent_count}  |  Taux : {round(present_count/max(len(attendances),1)*100,1)}%"
    ws[f"A{summary_row}"].font = Font(name="Calibri", bold=True, color=UEMF_BLUE)
    ws[f"A{summary_row}"].fill = light_fill

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def export_attendance_csv(session, attendances: list) -> bytes:
    """Génère un CSV des présences."""
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    writer.writerow(["EuroPresence – Feuille de Présence"])
    writer.writerow([f"Séance: {session.title}"])
    writer.writerow([f"Date: {session.started_at.strftime('%d/%m/%Y %H:%M') if session.started_at else 'N/A'}"])
    writer.writerow([])
    writer.writerow(["#", "Matricule", "Nom", "Prénom", "Email", "Groupe", "Statut", "Heure"])

    for i, att in enumerate(attendances, 1):
        student = att.student
        writer.writerow([
            i,
            student.matricule or "",
            student.last_name,
            student.first_name,
            student.email,
            att.group.name if att.group else "",
            "Présent" if att.status == "present" else "Absent",
            att.scanned_at.strftime("%H:%M:%S") if att.scanned_at else "",
        ])

    return output.getvalue().encode("utf-8-sig")  # BOM pour Excel


def export_attendance_pdf(session, attendances: list) -> bytes:
    """Génère un PDF professionnel des présences."""
    if not REPORTLAB_OK:
        raise ImportError("reportlab non installé")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                             leftMargin=1.5*cm, rightMargin=1.5*cm,
                             topMargin=2*cm, bottomMargin=1.5*cm)

    styles = getSampleStyleSheet()
    blue = colors.HexColor("#003882")
    green = colors.HexColor("#00A676")
    light = colors.HexColor("#E6F0FF")

    story = []

    # Titre
    title_style = ParagraphStyle("Title", fontSize=18, textColor=blue,
                                  fontName="Helvetica-Bold", alignment=TA_CENTER,
                                  spaceAfter=6)
    sub_style = ParagraphStyle("Sub", fontSize=11, textColor=colors.HexColor("#555555"),
                                 alignment=TA_CENTER, spaceAfter=4)
    info_style = ParagraphStyle("Info", fontSize=9, textColor=colors.grey,
                                  alignment=TA_CENTER, spaceAfter=12)

    story.append(Paragraph("🎓 EuroPresence – Feuille de Présence", title_style))
    story.append(Paragraph("Université Euro-Méditerranéenne de Fès (UEMF)", sub_style))
    story.append(HRFlowable(width="100%", thickness=2, color=blue, spaceAfter=8))

    session_date = session.started_at.strftime("%d/%m/%Y à %H:%M") if session.started_at else "N/A"
    story.append(Paragraph(
        f"<b>Séance :</b> {session.title} &nbsp;|&nbsp; <b>Date :</b> {session_date} &nbsp;|&nbsp; <b>Salle :</b> {session.room or 'N/A'}",
        sub_style
    ))
    story.append(Paragraph(f"Exporté le {datetime.now().strftime('%d/%m/%Y à %H:%M')}", info_style))
    story.append(Spacer(1, 0.4*cm))

    # Table données
    headers = ["#", "Matricule", "Nom", "Prénom", "Email", "Groupe", "Statut", "Heure"]
    data = [headers]

    for i, att in enumerate(attendances, 1):
        s = att.student
        data.append([
            str(i),
            s.matricule or "—",
            s.last_name,
            s.first_name,
            s.email,
            att.group.name if att.group else "—",
            "✓ Présent" if att.status == "present" else "✗ Absent",
            att.scanned_at.strftime("%H:%M") if att.scanned_at else "—",
        ])

    col_widths = [1*cm, 2.5*cm, 3.5*cm, 3.5*cm, 5*cm, 3.5*cm, 2.5*cm, 2*cm]
    table = Table(data, colWidths=col_widths, repeatRows=1)

    present_indices = {i+1 for i, a in enumerate(attendances) if a.status == "present"}

    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), blue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9FA")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ROWHEIGHT", (0, 0), (-1, -1), 18),
    ])

    # Colorier les lignes présents en vert clair, absents en rouge clair
    for i in range(1, len(data)):
        if i in present_indices:
            style.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#E8F8F2"))
            style.add("TEXTCOLOR", (6, i), (6, i), colors.HexColor("#00A676"))
        else:
            style.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FFF0F0"))
            style.add("TEXTCOLOR", (6, i), (6, i), colors.HexColor("#E74C3C"))

    table.setStyle(style)
    story.append(table)

    # Résumé
    story.append(Spacer(1, 0.6*cm))
    present_count = sum(1 for a in attendances if a.status == "present")
    rate = round(present_count / max(len(attendances), 1) * 100, 1)
    story.append(HRFlowable(width="100%", thickness=1, color=light, spaceAfter=6))
    story.append(Paragraph(
        f"<b>Résumé :</b> {present_count} présents / {len(attendances)-present_count} absents / Taux de présence : <b>{rate}%</b>",
        ParagraphStyle("Summary", fontSize=10, textColor=blue, alignment=TA_CENTER)
    ))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
