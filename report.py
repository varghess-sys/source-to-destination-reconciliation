"""
report.py
---------
Builds the PDF reconciliation report:
  Page 1   - Summary: counts by status, counts by field
  Page 2+  - Detail table, one row per (record, field) that is NOT a clean
             MATCH, grouped by status severity (worst first), color coded.
  Appendix - Full detail table (every field, every record) for audit trail.
"""

from datetime import datetime
from collections import defaultdict

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)

STATUS_COLOR = {
    "MATCH": colors.HexColor("#d9ead3"),
    "MATCH_AFTER_TRANSFORM": colors.HexColor("#fff2cc"),
    "MISMATCH": colors.HexColor("#f4cccc"),
    "MISSING_IN_DESTINATION": colors.HexColor("#f9cb9c"),
    "FIELD_NOT_IN_SOURCE": colors.HexColor("#d9d2e9"),
    "KEY_NOT_FOUND_IN_SOURCE": colors.HexColor("#ea9999"),
}

STATUS_LABEL = {
    "MATCH": "Match",
    "MATCH_AFTER_TRANSFORM": "Match (after expected transform)",
    "MISMATCH": "Mismatch",
    "MISSING_IN_DESTINATION": "Missing in destination",
    "FIELD_NOT_IN_SOURCE": "Field not present in any source",
    "KEY_NOT_FOUND_IN_SOURCE": "Key not found in any source",
}

# order of severity, worst first, for the "issues" section
SEVERITY_ORDER = [
    "KEY_NOT_FOUND_IN_SOURCE",
    "MISMATCH",
    "MISSING_IN_DESTINATION",
    "FIELD_NOT_IN_SOURCE",
]


def _fmt_source_values(source_values: dict) -> str:
    if not source_values:
        return "-"
    parts = []
    for sname, vals in source_values.items():
        uniq = sorted(set(str(v) for v in vals))
        parts.append(f"{sname}: {', '.join(uniq)}")
    return "\n".join(parts)


def build_report(results: list, summary: dict, config: dict, output_path: str,
                  title: str = "Source-to-Destination Reconciliation Report",
                  salary_analysis: list | None = None):
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, leading=10)
    small_bold = ParagraphStyle("small_bold", parent=small, fontName="Helvetica-Bold")

    doc = SimpleDocTemplate(
        output_path, pagesize=landscape(letter),
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
    )
    story = []

    # ---------- Summary page ----------
    story.append(Paragraph(title, styles["Title"]))
    story.append(Paragraph(
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
        f"Key field: {config['key_field']} | "
        f"Sources: {', '.join(s['name'] for s in config['sources'])}",
        styles["Normal"]
    ))
    story.append(Spacer(1, 16))

    story.append(Paragraph("Overall Summary", styles["Heading2"]))
    summary_rows = [["Status", "Count"]]
    for status in ["MATCH", "MATCH_AFTER_TRANSFORM", "MISMATCH",
                    "MISSING_IN_DESTINATION", "FIELD_NOT_IN_SOURCE",
                    "KEY_NOT_FOUND_IN_SOURCE"]:
        if status in summary:
            summary_rows.append([STATUS_LABEL[status], str(summary[status])])
    summary_rows.append(["TOTAL FIELD CHECKS", str(summary.get("TOTAL_CHECKS", 0))])

    t = Table(summary_rows, colWidths=[4 * inch, 1.5 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#434343")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eeeeee")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    for i, row in enumerate(summary_rows[1:-1], start=1):
        label = row[0]
        status_key = [k for k, v in STATUS_LABEL.items() if v == label]
        if status_key:
            t.setStyle(TableStyle([("BACKGROUND", (0, i), (-1, i), STATUS_COLOR[status_key[0]])]))
    story.append(t)
    story.append(Spacer(1, 16))

    # by-field breakdown
    by_field = defaultdict(lambda: defaultdict(int))
    for r in results:
        by_field[r["field"]][r["status"]] += 1

    story.append(Paragraph("Breakdown by Field", styles["Heading2"]))
    field_rows = [["Field", "Match", "Match (transform)", "Mismatch",
                   "Missing in Dest", "Not in Source", "Key Not Found"]]
    all_fields = list(config["fields_to_validate"]) + [
        spec["output_field"] for spec in config.get("computed_fields", [])
    ]
    field_order = {field: position for position, field in enumerate(all_fields)}
    for field in all_fields:
        counts = by_field[field]
        field_rows.append([
            field,
            str(counts.get("MATCH", 0)),
            str(counts.get("MATCH_AFTER_TRANSFORM", 0)),
            str(counts.get("MISMATCH", 0)),
            str(counts.get("MISSING_IN_DESTINATION", 0)),
            str(counts.get("FIELD_NOT_IN_SOURCE", 0)),
            str(counts.get("KEY_NOT_FOUND_IN_SOURCE", 0)),
        ])
    t2 = Table(field_rows, colWidths=[1.6 * inch] + [1.35 * inch] * 6)
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#434343")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]))
    story.append(t2)
    if salary_analysis:
        story.append(PageBreak())
        story.append(Paragraph("Salary Analysis: Loss of Pay", styles["Heading2"]))
        story.append(Paragraph(
            "Net salary is gross eligible salary less the loss-of-pay deduction. "
            "Daily rates use the actual calendar days in each month.",
            styles["Normal"],
        ))
        story.append(Spacer(1, 8))
        salary_rows = [[
            "Employee ID", "Month", "Days", "Eligible", "LOP Days",
            "Gross Salary", "LOP Deduction", "Net Salary",
        ]]
        for item in salary_analysis:
            salary_rows.append([
                str(item.get("EmployeeID") or ""),
                str(item.get("Month") or ""),
                str(item.get("DaysInMonth") or ""),
                str(item.get("EligibleDays") or ""),
                str(item.get("LossOfPayDays") or 0),
                str(item.get("GrossSalary") or ""),
                str(item.get("LossOfPayDeduction") or 0),
                str(item.get("NetSalary") or ""),
            ])
        ts = Table(
            salary_rows,
            colWidths=[1.15*inch, 0.7*inch, 0.55*inch, 0.65*inch,
                       0.7*inch, 1.15*inch, 1.15*inch, 1.15*inch],
            repeatRows=1,
        )
        ts.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#434343")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ]))
        story.append(ts)

    story.append(PageBreak())

    # ---------- Issues detail (everything that isn't a clean MATCH) ----------
    story.append(Paragraph("Detail: Records Requiring Attention", styles["Heading2"]))
    story.append(Paragraph(
        "Every row below is a field that did NOT come back as a clean, "
        "unmodified match between source and destination.", styles["Normal"]
    ))
    story.append(Spacer(1, 10))

    issues = [r for r in results if r["status"] in SEVERITY_ORDER]
    issues.sort(key=lambda r: (
        SEVERITY_ORDER.index(r["status"]), r["key"] or "",
        field_order.get(r["field"], len(field_order)),
    ))

    if not issues:
        story.append(Paragraph("No issues found — all fields matched cleanly.", styles["Normal"]))
    else:
        header = ["Key", "Field", "Status", "Destination Value", "Source Value(s)"]
        rows = [header]
        row_statuses = [None]
        for r in issues:
            rows.append([
                Paragraph(str(r["key"]), small),
                Paragraph(str(r["field"]), small),
                Paragraph(STATUS_LABEL[r["status"]], small_bold),
                Paragraph(str(r["destination_value"]) if r["destination_value"] not in (None, "") else "(empty)", small),
                Paragraph(_fmt_source_values(r["source_values"]).replace("\n", "<br/>"), small),
            ])
            row_statuses.append(r["status"])

        t3 = Table(rows, colWidths=[1.1*inch, 1.1*inch, 1.8*inch, 2.2*inch, 3*inch], repeatRows=1)
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#434343")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
        ]
        for i, status in enumerate(row_statuses):
            if status:
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), STATUS_COLOR[status]))
        t3.setStyle(TableStyle(style_cmds))
        story.append(t3)

    story.append(PageBreak())

    # ---------- Full appendix ----------
    story.append(Paragraph("Appendix: Full Field-by-Field Detail", styles["Heading2"]))
    story.append(Spacer(1, 8))
    header = ["Key", "Field", "Status", "Destination Value", "Source Value(s)"]
    rows = [header]
    row_statuses = [None]
    all_sorted = sorted(results, key=lambda r: (
        r["key"] or "", field_order.get(r["field"], len(field_order))
    ))
    for r in all_sorted:
        rows.append([
            Paragraph(str(r["key"]), small),
            Paragraph(str(r["field"]), small),
            Paragraph(STATUS_LABEL[r["status"]], small),
            Paragraph(str(r["destination_value"]) if r["destination_value"] not in (None, "") else "(empty)", small),
            Paragraph(_fmt_source_values(r["source_values"]).replace("\n", "<br/>"), small),
        ])
        row_statuses.append(r["status"])
    t4 = Table(rows, colWidths=[1.1*inch, 1.1*inch, 1.8*inch, 2.2*inch, 3*inch], repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#434343")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
    ]
    for i, status in enumerate(row_statuses):
        if status:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), STATUS_COLOR[status]))
    t4.setStyle(TableStyle(style_cmds))
    story.append(t4)

    doc.build(story)
