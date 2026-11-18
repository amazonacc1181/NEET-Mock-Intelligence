from core import database as db


def test_database_question_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.sqlite3")
    db.init_db()
    paper = {
        "id":"paper123", "kind":"mock", "filename":"Test_01.pdf", "label":"Test_01",
        "test_number":1, "page_count":1, "question_count":1, "sha256":"a"*64,
        "status":"extracted", "warnings_json":"[]", "created_at":"2026-01-01T00:00:00+00:00"
    }
    db.upsert_paper(paper)
    db.replace_questions("paper123", [{
        "id":"paper123:mock:1:q1", "kind":"mock", "question_number":1, "question_ordinal":1,
        "subject":"Physics", "page_number":1, "question_text":"A sample physics question with sufficient text.",
        "options":{"A":"1","B":"2"}, "page_image":None, "analysis":None, "extraction_confidence":0.9
    }])
    qs = db.get_questions("mock")
    assert len(qs) == 1
    assert qs[0]["question_ordinal"] == 1
    assert qs[0]["options"]["A"] == "1"