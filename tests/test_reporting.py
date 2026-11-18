from core import database as db
from core.reporting import export_workbook


def test_report_exports_empty_workbook(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "report.sqlite3")
    db.init_db()
    path = export_workbook(tmp_path / "empty_report.xlsx")
    assert path.exists()
    assert path.stat().st_size > 1000


def _paper(paper_id, kind, filename, test_number, sha):
    from core.database import utcnow
    return {
        "id": paper_id, "kind": kind, "filename": filename, "label": filename.rsplit(".", 1)[0],
        "test_number": test_number, "page_count": 1, "question_count": 1, "sha256": sha * 64,
        "status": "extracted", "warnings_json": "[]", "created_at": utcnow(),
    }


def test_detailed_pdfs_export_neet_report_and_mock_catalogue(tmp_path, monkeypatch):
    from core import database as db
    from core.reporting import export_pdf_report, export_mock_catalogue_pdf
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "complete.sqlite3")
    db.init_db()
    db.upsert_paper(_paper("mock1", "mock", "Test_01.pdf", 1, "a"))
    db.upsert_paper(_paper("neet1", "neet", "NEET_2026.pdf", None, "b"))
    mock_q = {
        "id": "mock1:mock:1:q12", "kind": "mock", "question_number": 12, "question_ordinal": 12,
        "subject": "Physics", "page_number": 1, "question_text": "A 2 kg body moves at 5 m/s. Find momentum.",
        "options": {"A": "10 kg m/s"}, "analysis": None, "extraction_confidence": 0.95,
    }
    neet_q = {
        "id": "neet1:neet:1:q8", "kind": "neet", "question_number": 8, "question_ordinal": 8,
        "subject": "Physics", "page_number": 1, "question_text": "Find momentum of a 3 kg body moving at 4 m/s.",
        "options": {"A": "12 kg m/s"}, "analysis": None, "extraction_confidence": 0.95,
    }
    db.replace_questions("mock1", [mock_q])
    db.replace_questions("neet1", [neet_q])
    db.update_analysis(mock_q["id"], {
        "chapter": "Laws of Motion", "topic": "Momentum", "core_concept": "Momentum is mass multiplied by velocity.",
        "answer": "10 kg m/s", "solution_steps": ["Use p = mv", "Substitute 2 × 5 = 10 kg m/s"],
        "solution_origin": "AI-derived, unverified", "formulae_or_laws": ["p = mv"],
    })
    db.update_analysis(neet_q["id"], {
        "chapter": "Laws of Motion", "topic": "Momentum", "core_concept": "Momentum is mass multiplied by velocity.",
        "answer": "12 kg m/s", "solution_steps": ["Use p = mv", "Substitute 3 × 4 = 12 kg m/s"],
    })
    db.save_match_run(neet_q["id"], "no_meaningful_match", "Synthetic test fixture", 1)
    pdf = export_pdf_report(tmp_path / "neet_report.pdf")
    catalogue = export_mock_catalogue_pdf(tmp_path / "mock_catalogue.pdf")
    assert pdf.exists() and pdf.stat().st_size > 1000
    assert catalogue.exists() and catalogue.stat().st_size > 1000