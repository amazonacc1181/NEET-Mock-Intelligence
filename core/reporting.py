from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from core.database import get_match_rows, get_papers, get_questions, get_match_run_map, get_state
from core.llm import RELATIONSHIP_LABELS


def _analysis_fields(q: dict[str, Any]) -> dict[str, Any]:
    a = q.get("analysis") or {}
    return {
        "Subject": q.get("subject") or a.get("subject", ""),
        "Chapter": a.get("chapter", ""),
        "Topic": a.get("topic", ""),
        "Subtopic": a.get("subtopic", ""),
        "Core concept": a.get("core_concept", ""),
        "Concept tags": ", ".join(a.get("concept_tags", []) or []),
        "Question type": a.get("question_type", ""),
        "Difficulty": a.get("difficulty", ""),
        "Formulae / laws": "; ".join(a.get("formulae_or_laws", []) or []),
        "Reactions / mechanisms": "; ".join(a.get("reactions_or_mechanisms", []) or []),
        "NCERT anchor": a.get("ncert_anchor", ""),
        "AI answer": a.get("answer", ""),
        "Solution origin": a.get("solution_origin", ""),
        "Solution confidence": a.get("solution_confidence", ""),
        "Solution steps": "\n".join(a.get("solution_steps", []) or []),
        "Common traps": "; ".join(a.get("common_traps", []) or []),
        "Analysis warnings": "; ".join(a.get("extraction_warnings", []) or []),
    }


def export_workbook(path: Path) -> Path:
    all_questions = get_questions()
    mock_questions = [q for q in all_questions if q["kind"] == "mock"]
    neet_questions = [q for q in all_questions if q["kind"] == "neet"]
    matches = get_match_rows()
    match_runs = get_match_run_map()
    papers = get_papers()

    match_rows: list[dict[str, Any]] = []
    match_by_neet: dict[str, list[dict[str, Any]]] = {}
    for m in matches:
        rel_label = RELATIONSHIP_LABELS.get(m["relationship"], m["relationship"])
        row = {
            "NEET Q": m["neet_qno"],
            "NEET ordinal": m.get("neet_ordinal", ""),
            "NEET subject": m.get("subject", ""),
            "NEET question ID": m["neet_question_id"],
            "Mock test": m.get("mock_label", ""),
            "Mock test number": m.get("test_number", ""),
            "Mock Q": m["mock_qno"],
            "Mock ordinal": m.get("mock_ordinal", ""),
            "Relationship": rel_label,
            "Relationship code": m["relationship"],
            "AI confidence (%)": m["confidence"],
            "Retrieval score": m["retrieval_score"],
            "Why they match": m.get("rationale", ""),
            "Shared concept": m.get("shared_concept", ""),
            "Differences": m.get("differences", ""),
            "Solution comparison": m.get("solution_comparison", ""),
            "Evidence": "\n".join(m.get("evidence", []) or []),
            "Independent verification": m.get("verification_status", ""),
            "NEET question text": m.get("neet_text", ""),
            "Mock question text": m.get("mock_text", ""),
            "Mock chapter": (m.get("mock_analysis") or {}).get("chapter", ""),
            "Mock concept": (m.get("mock_analysis") or {}).get("core_concept", ""),
        }
        match_rows.append(row)
        match_by_neet.setdefault(m["neet_question_id"], []).append(row)

    neet_summary = []
    unmatched = []
    for q in neet_questions:
        rows = match_by_neet.get(q["id"], [])
        rows = sorted(rows, key=lambda x: (x["AI confidence (%)"], x["Retrieval score"]), reverse=True)
        best = rows[0] if rows else None
        a = q.get("analysis") or {}
        run = match_runs.get(q["id"], {})
        row = {
            "NEET Q": q["question_number"],
            "NEET ordinal": q.get("question_ordinal", ""),
            "Subject": q.get("subject") or a.get("subject", ""),
            "Chapter": a.get("chapter", ""),
            "Topic": a.get("topic", ""),
            "Core concept": a.get("core_concept", ""),
            "Total credible matches": len(rows),
            "No-match explanation": run.get("no_match_reason", "") if not rows else "",
            "Candidates examined": run.get("candidate_count", ""),
            "Best mock test": best["Mock test"] if best else ("No meaningful match found" if run.get("status") == "no_meaningful_match" else "Not processed"),
            "Best mock Q": best["Mock Q"] if best else "",
            "Best relationship": best["Relationship"] if best else ("No meaningful match" if run.get("status") == "no_meaningful_match" else "Not processed"),
            "Best confidence (%)": best["AI confidence (%)"] if best else "",
            "All matches (test/Q/type)": " | ".join(f"{r['Mock test']} Q{r['Mock Q']} — {r['Relationship']} ({r['AI confidence (%)']}%)" for r in rows),
            "Question text": q.get("question_text", "")[:30000],
            "AI answer": a.get("answer", ""),
            "Solution steps": "\n".join(a.get("solution_steps", []) or []),
            "Analysis warnings": "; ".join(a.get("extraction_warnings", []) or []),
        }
        neet_summary.append(row)
        if not rows and run.get("status") == "no_meaningful_match":
            unmatched.append(row)

    mock_rows = []
    for q in mock_questions:
        a = q.get("analysis") or {}
        row = {
            "Mock test": q.get("label", ""),
            "Test number": q.get("test_number", ""),
            "Question number": q["question_number"],
            "Question ordinal": q.get("question_ordinal", ""),
            "Source PDF": q.get("filename", ""),
            "PDF page": q.get("page_number", ""),
            "Extraction confidence": q.get("extraction_confidence", ""),
            "Question text": q.get("question_text", "")[:30000],
            "Options": json.dumps(q.get("options", {}), ensure_ascii=False),
        }
        row.update(_analysis_fields(q))
        mock_rows.append(row)

    paper_rows = []
    for p in papers:
        paper_rows.append({
            "Type": p["kind"], "PDF": p["filename"], "Label": p["label"],
            "Test number": p.get("test_number", ""), "Pages": p["page_count"],
            "Extracted questions": p["question_count"], "Status": p["status"],
            "Warnings": "\n".join(p.get("warnings", [])),
        })

    relationship_rows = []
    counts: dict[str, int] = {}
    for row in match_rows:
        counts[row["Relationship"]] = counts.get(row["Relationship"], 0) + 1
    for label, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        relationship_rows.append({"Relationship": label, "Matched pairs": count})
    relationship_rows.append({"Relationship": "NEET questions with no matches", "Matched pairs": len(unmatched)})

    sheets = {
        "NEET question summary": pd.DataFrame(neet_summary),
        "All matches": pd.DataFrame(match_rows),
        "All mock questions": pd.DataFrame(mock_rows),
        "No meaningful match": pd.DataFrame(unmatched),
        "Relationship counts": pd.DataFrame(relationship_rows),
        "PDF extraction QA": pd.DataFrame(paper_rows),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="17365D")
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            for col_idx, cells in enumerate(ws.columns, start=1):
                header = str(cells[0].value or "")
                max_len = min(max([len(str(c.value or "").split("\n")[0]) for c in cells[: min(len(cells), 120)] ] + [len(header)]) + 2, 52)
                ws.column_dimensions[get_column_letter(col_idx)].width = max(12, max_len)
            for row in ws.iter_rows(min_row=2):
                for cell in row:
                    if isinstance(cell.value, str) and ("\n" in cell.value or len(cell.value) > 100):
                        cell.alignment = Alignment(wrap_text=True, vertical="top")
    return path


def _pdf_safe(value: Any) -> str:
    from xml.sax.saxutils import escape
    text = "" if value is None else str(value)
    return escape(text).replace("\n", "<br/>")


def export_pdf_report(path: Path) -> Path:
    """Create the detailed question-by-question NEET-to-mock comparison PDF."""
    from collections import Counter
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether

    all_questions = get_questions()
    mock_questions = [q for q in all_questions if q["kind"] == "mock"]
    neet_questions = sorted([q for q in all_questions if q["kind"] == "neet"], key=lambda q: (q.get("question_ordinal", 9999), q.get("question_number", 9999)))
    matches = get_match_rows()
    match_runs = get_match_run_map()
    papers = get_papers()
    if not neet_questions:
        raise ValueError("No NEET questions are available. Import and analyse the NEET paper first.")

    by_neet: dict[str, list[dict[str, Any]]] = {}
    for match in matches:
        by_neet.setdefault(match["neet_question_id"], []).append(match)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CoverTitleCustom", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=23, leading=28, textColor=colors.HexColor("#17365D"), alignment=TA_CENTER, spaceAfter=12))
    styles.add(ParagraphStyle(name="SectionCustom", parent=styles["Heading1"], fontSize=15, leading=19, textColor=colors.HexColor("#17365D"), spaceBefore=10, spaceAfter=8))
    styles.add(ParagraphStyle(name="QHeadingCustom", parent=styles["Heading2"], fontSize=12, leading=15, textColor=colors.HexColor("#1F4E79"), spaceBefore=9, spaceAfter=5))
    styles.add(ParagraphStyle(name="SubHeadingCustom", parent=styles["Heading3"], fontSize=9.5, leading=12, textColor=colors.HexColor("#365F91"), spaceBefore=5, spaceAfter=3))
    styles.add(ParagraphStyle(name="BodyCustom", parent=styles["BodyText"], fontSize=8.5, leading=11.2, spaceAfter=4, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name="SmallCustom", parent=styles["BodyText"], fontSize=7.3, leading=9.2, textColor=colors.HexColor("#404040"), spaceAfter=3))
    styles.add(ParagraphStyle(name="MutedCustom", parent=styles["BodyText"], fontSize=7.5, leading=10, textColor=colors.HexColor("#666666"), spaceAfter=4))
    styles.add(ParagraphStyle(name="CalloutCustom", parent=styles["BodyText"], fontSize=8.5, leading=11, textColor=colors.HexColor("#7F6000"), backColor=colors.HexColor("#FFF2CC"), borderPadding=6, spaceBefore=4, spaceAfter=7))

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=17*mm, leftMargin=17*mm, topMargin=17*mm, bottomMargin=17*mm, title="NEET 2026 — Mock Test Relationship Analysis", author="NEET Mock Intelligence")
    story: list[Any] = []
    match_counts = Counter(RELATIONSHIP_LABELS.get(m["relationship"], m["relationship"]) for m in matches)
    matched_neet = sum(bool(by_neet.get(q["id"])) for q in neet_questions)
    no_match = sum(1 for q in neet_questions if not by_neet.get(q["id"]) and match_runs.get(q["id"], {}).get("status") == "no_meaningful_match")
    unprocessed = len(neet_questions) - matched_neet - no_match
    analyzed_mock = sum(bool(q.get("analysis")) for q in mock_questions)
    analyzed_neet = sum(bool(q.get("analysis")) for q in neet_questions)

    story += [Spacer(1, 24*mm), Paragraph("NEET 2026", styles["CoverTitleCustom"]), Paragraph("Mock Test Relationship Analysis", styles["CoverTitleCustom"]), Spacer(1, 7*mm)]
    story.append(Paragraph("A question-by-question evidence report comparing the NEET 2026 paper with the indexed mock-test bank.", styles["BodyCustom"]))
    story.append(Spacer(1, 8*mm))
    summary_label = ParagraphStyle(
        name="SummaryLabel", parent=styles["SmallCustom"], fontName="Helvetica-Bold",
        fontSize=7.2, leading=8.5, textColor=colors.HexColor("#17365D"), spaceAfter=0,
    )
    summary_value = ParagraphStyle(
        name="SummaryValue", parent=styles["SmallCustom"], fontName="Helvetica",
        fontSize=8, leading=9.2, textColor=colors.black, spaceAfter=0,
    )
    summary_data = [
        [Paragraph("Mock papers", summary_label), Paragraph(str(sum(p["kind"] == "mock" for p in papers)), summary_value), Paragraph("Mock questions", summary_label), Paragraph(f"{len(mock_questions):,}", summary_value)],
        [Paragraph("Mock questions analysed", summary_label), Paragraph(f"{analyzed_mock:,}/{len(mock_questions):,}", summary_value), Paragraph("NEET questions analysed", summary_label), Paragraph(f"{analyzed_neet:,}/{len(neet_questions):,}", summary_value)],
        [Paragraph("NEET questions with matches", summary_label), Paragraph(str(matched_neet), summary_value), Paragraph("No meaningful match", summary_label), Paragraph(str(no_match), summary_value)],
        [Paragraph("Unprocessed / failed", summary_label), Paragraph(str(unprocessed), summary_value), Paragraph("Accepted mock-to-NEET pairs", summary_label), Paragraph(str(len(matches)), summary_value)],
    ]
    table = Table(summary_data, colWidths=[46*mm, 32*mm, 46*mm, 32*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#D9EAF7")),
        ("BACKGROUND", (2,0), (2,-1), colors.HexColor("#D9EAF7")),
        ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#B4C7E7")),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ]))
    story.append(table)
    story += [Spacer(1, 8*mm), Paragraph("Relationship categories", styles["SectionCustom"])]
    for key, label in RELATIONSHIP_LABELS.items():
        story.append(Paragraph(f"<b>{_pdf_safe(label)}</b> — {_pdf_safe(_relationship_definition(key))}", styles["BodyCustom"]))
    story += [Spacer(1, 3*mm), Paragraph("How to read this report", styles["SectionCustom"])]
    story.append(Paragraph("Each NEET question is listed with every accepted mock-paper match. Mock references include test number, printed question number and source PDF page where available. Relationship labels are not interchangeable: an identical question is distinguished from a shared method, broad concept or NCERT source.", styles["BodyCustom"]))
    story.append(Paragraph("A no-match result means that no qualifying relationship was accepted from the candidate set retrieved by this version of the system. It is not proof that no related question exists in the entire bank. OCR quality, diagrams and candidate retrieval may affect recall. Model confidence is an estimate, not a calibrated probability.", styles["CalloutCustom"]))
    story.append(PageBreak())

    story.append(Paragraph("Executive relationship summary", styles["SectionCustom"]))
    count_rows = [["Relationship", "Accepted pairs"]]
    for label, count in match_counts.most_common():
        count_rows.append([_pdf_safe(label), str(count)])
    if len(count_rows) == 1:
        count_rows.append(["No accepted matches yet", "0"])
    count_table = Table(count_rows, colWidths=[130*mm, 30*mm], repeatRows=1)
    count_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#17365D")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("GRID", (0,0), (-1,-1), .3, colors.HexColor("#B4C7E7")),
        ("FONTSIZE", (0,0), (-1,-1), 8), ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(count_table)
    manager_review_data = get_state("manager_final_review", {}) or {}
    if manager_review_data:
        story.append(Spacer(1, 5*mm))
        story.append(Paragraph("AI Operations Manager — final release review", styles["SectionCustom"]))
        story.append(Paragraph("<b>Status:</b> " + _pdf_safe(manager_review_data.get("status", "Not recorded")), styles["BodyCustom"]))
        for title, key in [("Key findings", "key_findings"), ("Quality gates", "quality_gates"), ("Recommended next actions", "next_actions")]:
            values = manager_review_data.get(key) or []
            if values:
                story.append(Paragraph("<b>" + title + "</b><br/>" + "<br/>".join(f"• {_pdf_safe(x)}" for x in values), styles["SmallCustom"]))
    story.append(Spacer(1, 5*mm))

    for q in neet_questions:
        a = q.get("analysis") or {}
        q_matches = sorted(by_neet.get(q["id"], []), key=lambda m: (m.get("confidence", 0), m.get("retrieval_score", 0)), reverse=True)
        run = match_runs.get(q["id"], {})
        title = f"NEET Q{q.get('question_number')}  |  {_pdf_safe(q.get('subject') or a.get('subject') or 'Subject uncertain')}  |  {_pdf_safe(a.get('chapter', 'Chapter uncertain'))}"
        block: list[Any] = [Paragraph(title, styles["QHeadingCustom"])]
        meta = f"Paper: {_pdf_safe(q.get('label', 'NEET 2026'))} · Source PDF page: {_pdf_safe(q.get('page_number', 'Not recorded'))} · Topic: {_pdf_safe(a.get('topic', 'Not classified'))} · Difficulty: {_pdf_safe(a.get('difficulty', 'Uncertain'))}"
        block.append(Paragraph(meta, styles["MutedCustom"]))
        block.append(Paragraph("<b>Question</b><br/>" + _pdf_safe(q.get("question_text", "")), styles["BodyCustom"]))
        if q.get("options"):
            opts = "<br/>".join(f"<b>{_pdf_safe(k)}.</b> {_pdf_safe(v)}" for k, v in q["options"].items())
            block.append(Paragraph("<b>Options</b><br/>" + opts, styles["SmallCustom"]))
        if a.get("core_concept"):
            block.append(Paragraph("<b>Concept</b>: " + _pdf_safe(a.get("core_concept")), styles["BodyCustom"]))
        if a.get("concept_tags"):
            block.append(Paragraph("<b>Concept tags</b>: " + _pdf_safe(", ".join(a.get("concept_tags", []))), styles["SmallCustom"]))
        if a.get("formulae_or_laws"):
            block.append(Paragraph("<b>Formulae / laws</b>: " + _pdf_safe("; ".join(a.get("formulae_or_laws", []))), styles["SmallCustom"]))
        if a.get("reactions_or_mechanisms"):
            block.append(Paragraph("<b>Reactions / mechanisms</b>: " + _pdf_safe("; ".join(a.get("reactions_or_mechanisms", []))), styles["SmallCustom"]))
        if a.get("ncert_anchor"):
            block.append(Paragraph("<b>NCERT source</b>: " + _pdf_safe(a.get("ncert_anchor")), styles["SmallCustom"]))
        if a.get("answer"):
            block.append(Paragraph("<b>AI answer</b>: " + _pdf_safe(a.get("answer")) + " · " + _pdf_safe(a.get("solution_origin", "Origin not recorded")), styles["SmallCustom"]))
        if a.get("solution_steps"):
            block.append(Paragraph("<b>Solution outline</b><br/>" + "<br/>".join(f"{i+1}. {_pdf_safe(s)}" for i, s in enumerate(a.get("solution_steps", []))), styles["SmallCustom"]))
        if a.get("extraction_warnings"):
            block.append(Paragraph("<b>Analysis warnings</b>: " + _pdf_safe("; ".join(a.get("extraction_warnings", []))), styles["CalloutCustom"]))
        block.append(Paragraph(f"<b>Mock matches accepted: {len(q_matches)}</b>", styles["SubHeadingCustom"]))
        story.append(KeepTogether(block))

        if q_matches:
            for rank, m in enumerate(q_matches, start=1):
                label = RELATIONSHIP_LABELS.get(m["relationship"], m["relationship"])
                mock_ref = f"Mock Test {m.get('test_number') or m.get('mock_label') or '—'} · Q{m.get('mock_qno')} · PDF page {m.get('mock_page_number') or 'not recorded'}"
                match_block = [Paragraph(f"{rank}. {_pdf_safe(mock_ref)}", styles["SubHeadingCustom"])]
                match_block.append(Paragraph(f"<b>Relationship:</b> {_pdf_safe(label)} · <b>Confidence:</b> {float(m.get('confidence', 0)):.0f}% · <b>Verification:</b> {_pdf_safe(m.get('verification_status', 'Not independently verified'))}", styles["SmallCustom"]))
                match_block.append(Paragraph("<b>Mock question</b><br/>" + _pdf_safe(m.get("mock_text", "")), styles["SmallCustom"]))
                ma = m.get("mock_analysis") or {}
                if ma.get("core_concept"):
                    match_block.append(Paragraph("<b>Mock concept</b>: " + _pdf_safe(ma.get("core_concept")), styles["SmallCustom"]))
                if ma.get("solution_steps"):
                    match_block.append(Paragraph("<b>Mock solution outline</b><br/>" + "<br/>".join(f"{i+1}. {_pdf_safe(s)}" for i, s in enumerate(ma.get("solution_steps", []))), styles["SmallCustom"]))
                match_block.append(Paragraph("<b>Why they match</b>: " + _pdf_safe(m.get("rationale", "")), styles["SmallCustom"]))
                match_block.append(Paragraph("<b>Shared concept / source</b>: " + _pdf_safe(m.get("shared_concept", "")), styles["SmallCustom"]))
                match_block.append(Paragraph("<b>Differences</b>: " + _pdf_safe(m.get("differences", "")), styles["SmallCustom"]))
                match_block.append(Paragraph("<b>Solution comparison</b>: " + _pdf_safe(m.get("solution_comparison", "")), styles["SmallCustom"]))
                if m.get("evidence"):
                    match_block.append(Paragraph("<b>Evidence</b><br/>" + "<br/>".join(f"• {_pdf_safe(e)}" for e in m.get("evidence", [])), styles["SmallCustom"]))
                story.append(KeepTogether(match_block))
                story.append(Spacer(1, 2*mm))
        else:
            status = run.get("status", "not_processed")
            reason = run.get("no_match_reason", "")
            if status == "no_meaningful_match":
                story.append(Paragraph("No meaningful mock match accepted.", styles["CalloutCustom"]))
                if reason:
                    story.append(Paragraph("<b>Search explanation</b>: " + _pdf_safe(reason), styles["SmallCustom"]))
            else:
                story.append(Paragraph("Not processed or matching did not complete. This is not a confirmed no-match.", styles["CalloutCustom"]))
        story.append(Spacer(1, 4*mm))

    story.append(PageBreak())
    story.append(Paragraph("Extraction and quality-control notes", styles["SectionCustom"]))
    for paper in papers:
        warns = paper.get("warnings", [])
        line = f"<b>{_pdf_safe(paper.get('kind'))}: {_pdf_safe(paper.get('filename'))}</b> — {_pdf_safe(paper.get('question_count'))} extracted questions, {_pdf_safe(paper.get('page_count'))} pages, status: {_pdf_safe(paper.get('status'))}."
        if warns:
            line += " Warnings: " + _pdf_safe("; ".join(warns))
        story.append(Paragraph(line, styles["SmallCustom"]))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("Interpretation and limitations", styles["SectionCustom"]))
    limitations = [
        "The PDF parser retains original page references but OCR, multi-column layouts, diagrams and chemical structures can be imperfect. Check low extraction-confidence questions against the source PDFs.",
        "The local language model analyses and compares questions; its explanations and answers are not an official NEET answer key. A separate verifier, when available, is an independent model opinion rather than a guarantee.",
        "Candidate retrieval uses semantic and lexical ranking before detailed AI adjudication. A related mock question not included in the candidate shortlist can be missed. A no-match status is therefore not proof of absolute absence.",
        "Confidence values are model-reported indicators, not calibrated statistical probabilities. Human review is recommended for low-confidence matches, diagrams, numerical problems and any answer used for official teaching material.",
    ]
    for item in limitations:
        story.append(Paragraph("• " + _pdf_safe(item), styles["BodyCustom"]))

    def footer(canvas, doc_obj):
        canvas.saveState()
        width, _height = A4
        canvas.setStrokeColor(colors.HexColor("#B4C7E7"))
        canvas.line(17*mm, 13*mm, width-17*mm, 13*mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(17*mm, 8.5*mm, "NEET Mock Intelligence · Local AI analysis · Verify against original papers")
        canvas.drawRightString(width-17*mm, 8.5*mm, f"Page {doc_obj.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path


def _relationship_definition(code: str) -> str:
    definitions = {
        "EXACTLY_SAME": "The same question and required reasoning; only harmless formatting or option-order changes.",
        "SUBSTANTIALLY_SAME_DATA_DIFFERENCE": "The same structure and solution path, with values, names or minor data changed.",
        "SAME_PATTERN_OR_SOLUTION_METHOD": "The same question pattern and reasoning method, but a different quantity or structural variation.",
        "CONCEPTUALLY_SAME_DIFFERENT_APPLICATION": "The same underlying concept applied in a different context or setup.",
        "SAME_NCERT_SOURCE_OR_KNOWLEDGE": "The same specific NCERT statement, fact, reaction, example, figure, table or passage.",
        "SAME_DIAGRAM_OR_EXPERIMENTAL_SETUP": "The same distinctive diagram, graph, apparatus, experiment or data representation.",
        "SAME_MULTI_CONCEPT_COMBINATION": "The same combination and sequence of concepts with a similar reasoning chain.",
    }
    return definitions.get(code, "Relationship explanation not available.")



def export_mock_catalogue_pdf(path: Path) -> Path:
    """Create a full mock-question analysis catalogue for every successfully extracted mock question."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepTogether

    mock_questions = get_questions("mock")
    if not mock_questions:
        raise ValueError("No mock questions are available for the catalogue.")
    mock_questions.sort(key=lambda q: (q.get("test_number") or 999, q.get("question_ordinal") or 9999, q.get("question_number") or 9999))
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CatalogTitle", parent=styles["Title"], fontSize=21, leading=25, textColor=colors.HexColor("#17365D"), alignment=1, spaceAfter=12))
    styles.add(ParagraphStyle(name="CatalogQ", parent=styles["Heading2"], fontSize=10.5, leading=13, textColor=colors.HexColor("#1F4E79"), spaceBefore=8, spaceAfter=4))
    styles.add(ParagraphStyle(name="CatalogBody", parent=styles["BodyText"], fontSize=7.8, leading=10, spaceAfter=3))
    styles.add(ParagraphStyle(name="CatalogSmall", parent=styles["BodyText"], fontSize=7, leading=8.5, textColor=colors.HexColor("#444444"), spaceAfter=2))
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=15*mm, bottomMargin=16*mm, title="NEET Mock Question Bank Analysis Catalogue")
    story = [Spacer(1, 22*mm), Paragraph("NEET MOCK QUESTION BANK", styles["CatalogTitle"]), Paragraph("Complete question-by-question analysis catalogue", styles["CatalogTitle"]), Spacer(1, 8*mm), Paragraph(f"Indexed mock questions: {len(mock_questions):,}. This catalogue records the extracted question, its source test/page, chapter/topic/concept analysis, formulas/reactions, answer provenance and solution outline.", styles["CatalogBody"]), PageBreak()]
    for q in mock_questions:
        a = q.get("analysis") or {}
        heading = f"Test {q.get('test_number') or q.get('label') or '—'} · Q{q.get('question_number')} · {_pdf_safe(q.get('subject') or a.get('subject') or 'Subject uncertain')} · PDF page {_pdf_safe(q.get('page_number', '—'))}"
        block = [Paragraph(heading, styles["CatalogQ"])]
        block.append(Paragraph("<b>Question</b><br/>" + _pdf_safe(q.get("question_text", "")), styles["CatalogBody"]))
        if q.get("options"):
            block.append(Paragraph("<b>Options</b><br/>" + "<br/>".join(f"<b>{_pdf_safe(k)}.</b> {_pdf_safe(v)}" for k, v in q["options"].items()), styles["CatalogSmall"]))
        if not a:
            block.append(Paragraph("<b>Analysis status:</b> Not analysed", styles["CatalogSmall"]))
        else:
            for label, value in [
                ("Chapter", a.get("chapter")), ("Topic", a.get("topic")), ("Subtopic", a.get("subtopic")),
                ("Core concept", a.get("core_concept")), ("Question type", a.get("question_type")),
                ("Difficulty", a.get("difficulty")), ("NCERT anchor", a.get("ncert_anchor")),
            ]:
                if value:
                    block.append(Paragraph(f"<b>{label}:</b> {_pdf_safe(value)}", styles["CatalogSmall"]))
            if a.get("concept_tags"):
                block.append(Paragraph("<b>Concept tags:</b> " + _pdf_safe(", ".join(a.get("concept_tags", []))), styles["CatalogSmall"]))
            if a.get("formulae_or_laws"):
                block.append(Paragraph("<b>Formulae / laws:</b> " + _pdf_safe("; ".join(a.get("formulae_or_laws", []))), styles["CatalogSmall"]))
            if a.get("reactions_or_mechanisms"):
                block.append(Paragraph("<b>Reactions / mechanisms:</b> " + _pdf_safe("; ".join(a.get("reactions_or_mechanisms", []))), styles["CatalogSmall"]))
            if a.get("answer"):
                block.append(Paragraph("<b>Answer:</b> " + _pdf_safe(a.get("answer")) + " · <b>Origin:</b> " + _pdf_safe(a.get("solution_origin", "Not recorded")) + " · <b>Answer confidence:</b> " + _pdf_safe(a.get("solution_confidence", "Unspecified")), styles["CatalogSmall"]))
            if a.get("solution_steps"):
                block.append(Paragraph("<b>Solution steps</b><br/>" + "<br/>".join(f"{i+1}. {_pdf_safe(step)}" for i, step in enumerate(a.get("solution_steps", []))), styles["CatalogSmall"]))
            if a.get("common_traps"):
                block.append(Paragraph("<b>Common traps:</b> " + _pdf_safe("; ".join(a.get("common_traps", []))), styles["CatalogSmall"]))
            review = a.get("_independent_review") or {}
            if review:
                block.append(Paragraph("<b>Independent review:</b> " + _pdf_safe(review.get("status", "Not run")) + " · " + _pdf_safe("; ".join(review.get("issues", []) or [])), styles["CatalogSmall"]))
            if a.get("extraction_warnings"):
                block.append(Paragraph("<b>Warnings:</b> " + _pdf_safe("; ".join(a.get("extraction_warnings", []))), styles["CatalogSmall"]))
        story.append(KeepTogether(block))
        story.append(Spacer(1, 3*mm))
    def footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#B4C7E7"))
        canvas.line(16*mm, 12*mm, A4[0]-16*mm, 12*mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(16*mm, 7.5*mm, "NEET Mock Intelligence · Mock question bank catalogue")
        canvas.drawRightString(A4[0]-16*mm, 7.5*mm, f"Page {doc_obj.page}")
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path