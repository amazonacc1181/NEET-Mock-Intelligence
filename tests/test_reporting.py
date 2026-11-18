from core import database as db
from core.reporting import export_workbook


def test_report_exports_empty_workbook(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "report.sqlite3")
    db.init_db()
    path = export_workbook(tmp_path / "empty_report.xlsx")
    assert path.exists()
    assert path.stat().st_size > 1000