from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from core.database import get_match_rows, get_papers, get_questions, get_match_run_map
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