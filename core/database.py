from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import DB_PATH


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS papers (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            filename TEXT NOT NULL,
            label TEXT NOT NULL,
            test_number INTEGER,
            page_count INTEGER NOT NULL DEFAULT 0,
            question_count INTEGER NOT NULL DEFAULT 0,
            sha256 TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'extracted',
            warnings_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS questions (
            id TEXT PRIMARY KEY,
            paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            question_number INTEGER NOT NULL,
            question_ordinal INTEGER NOT NULL,
            subject TEXT,
            page_number INTEGER,
            question_text TEXT NOT NULL,
            options_json TEXT NOT NULL DEFAULT '{}',
            page_image TEXT,
            analysis_json TEXT,
            extraction_confidence REAL NOT NULL DEFAULT 0.0,
            created_at TEXT NOT NULL,
            UNIQUE(paper_id, kind, question_ordinal)
        );
        CREATE INDEX IF NOT EXISTS idx_questions_kind ON questions(kind);
        CREATE INDEX IF NOT EXISTS idx_questions_paper ON questions(paper_id);
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            neet_question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            mock_question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            relationship TEXT NOT NULL,
            confidence REAL NOT NULL,
            retrieval_score REAL NOT NULL DEFAULT 0.0,
            rationale TEXT,
            shared_concept TEXT,
            differences TEXT,
            solution_comparison TEXT,
            evidence_json TEXT NOT NULL DEFAULT '[]',
            verification_status TEXT NOT NULL DEFAULT 'Not independently verified',
            created_at TEXT NOT NULL,
            UNIQUE(neet_question_id, mock_question_id)
        );
        CREATE TABLE IF NOT EXISTS match_runs (
            neet_question_id TEXT PRIMARY KEY REFERENCES questions(id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            no_match_reason TEXT,
            candidate_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS run_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS document_text (
            paper_id TEXT PRIMARY KEY REFERENCES papers(id) ON DELETE CASCADE,
            full_text TEXT NOT NULL
        );
        """)


def upsert_paper(paper: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute("""INSERT INTO papers
        (id,kind,filename,label,test_number,page_count,question_count,sha256,status,warnings_json,created_at)
        VALUES (:id,:kind,:filename,:label,:test_number,:page_count,:question_count,:sha256,:status,:warnings_json,:created_at)
        ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, filename=excluded.filename,
        label=excluded.label, test_number=excluded.test_number, page_count=excluded.page_count,
        question_count=excluded.question_count, status=excluded.status,
        warnings_json=excluded.warnings_json""", paper)


def replace_questions(paper_id: str, questions: list[dict[str, Any]]) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM questions WHERE paper_id=?", (paper_id,))
        for q in questions:
            conn.execute("""INSERT INTO questions
            (id,paper_id,kind,question_number,question_ordinal,subject,page_number,question_text,options_json,page_image,analysis_json,extraction_confidence,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                q["id"], paper_id, q["kind"], q["question_number"], q.get("question_ordinal", q["question_number"]), q.get("subject"),
                q.get("page_number"), q["question_text"], json.dumps(q.get("options", {}), ensure_ascii=False),
                q.get("page_image"), json.dumps(q["analysis"], ensure_ascii=False) if q.get("analysis") else None,
                q.get("extraction_confidence", 0.7), q.get("created_at", utcnow())
            ))


def save_document_text(paper_id: str, full_text: str) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO document_text(paper_id,full_text) VALUES(?,?) ON CONFLICT(paper_id) DO UPDATE SET full_text=excluded.full_text", (paper_id, full_text))


def get_papers(kind: str | None = None) -> list[dict[str, Any]]:
    with connect() as conn:
        if kind:
            rows = conn.execute("SELECT * FROM papers WHERE kind=? ORDER BY COALESCE(test_number,999), filename", (kind,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM papers ORDER BY kind, COALESCE(test_number,999), filename").fetchall()
    result = []
    for r in rows:
        item = dict(r)
        item["warnings"] = json.loads(item.pop("warnings_json", "[]"))
        result.append(item)
    return result


def get_questions(kind: str | None = None, unanalysed_only: bool = False) -> list[dict[str, Any]]:
    query = """SELECT q.*, p.filename, p.label, p.test_number
               FROM questions q JOIN papers p ON p.id=q.paper_id"""
    clauses, params = [], []
    if kind:
        clauses.append("q.kind=?"); params.append(kind)
    if unanalysed_only:
        clauses.append("q.analysis_json IS NULL")
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY p.kind, COALESCE(p.test_number,999), p.filename, q.question_number"
    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        d["options"] = json.loads(d.pop("options_json", "{}"))
        raw = d.pop("analysis_json", None)
        d["analysis"] = json.loads(raw) if raw else None
        out.append(d)
    return out


def update_analysis(question_id: str, analysis: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute("UPDATE questions SET analysis_json=? WHERE id=?", (json.dumps(analysis, ensure_ascii=False), question_id))


def clear_matches(neet_question_ids: list[str] | None = None) -> None:
    with connect() as conn:
        if neet_question_ids:
            conn.executemany("DELETE FROM matches WHERE neet_question_id=?", [(x,) for x in neet_question_ids])
            conn.executemany("DELETE FROM match_runs WHERE neet_question_id=?", [(x,) for x in neet_question_ids])
        else:
            conn.execute("DELETE FROM matches")
            conn.execute("DELETE FROM match_runs")


def save_match_run(neet_id: str, status: str, no_match_reason: str = "", candidate_count: int = 0) -> None:
    with connect() as conn:
        conn.execute("""INSERT INTO match_runs(neet_question_id,status,no_match_reason,candidate_count,created_at)
        VALUES(?,?,?,?,?) ON CONFLICT(neet_question_id) DO UPDATE SET status=excluded.status,
        no_match_reason=excluded.no_match_reason,candidate_count=excluded.candidate_count,created_at=excluded.created_at""",
        (neet_id, status, no_match_reason, candidate_count, utcnow()))


def get_match_run_map() -> dict[str, dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM match_runs").fetchall()
    return {r["neet_question_id"]: dict(r) for r in rows}


def save_matches(neet_id: str, matches: list[dict[str, Any]]) -> None:
    with connect() as conn:
        for m in matches:
            conn.execute("""INSERT INTO matches
            (neet_question_id,mock_question_id,relationship,confidence,retrieval_score,rationale,shared_concept,differences,solution_comparison,evidence_json,verification_status,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(neet_question_id,mock_question_id) DO UPDATE SET
            relationship=excluded.relationship, confidence=excluded.confidence, retrieval_score=excluded.retrieval_score,
            rationale=excluded.rationale, shared_concept=excluded.shared_concept, differences=excluded.differences,
            solution_comparison=excluded.solution_comparison, evidence_json=excluded.evidence_json,
            verification_status=excluded.verification_status""", (
                neet_id, m["mock_question_id"], m["relationship"], float(m.get("confidence", 0)),
                float(m.get("retrieval_score", 0)), m.get("rationale", ""), m.get("shared_concept", ""),
                m.get("differences", ""), m.get("solution_comparison", ""),
                json.dumps(m.get("evidence", []), ensure_ascii=False), m.get("verification_status", "Not independently verified"), utcnow()
            ))


def get_match_rows() -> list[dict[str, Any]]:
    query = """SELECT m.*, nq.question_number AS neet_qno, np.label AS neet_label,
                     nq.question_text AS neet_text, nq.question_ordinal AS neet_ordinal, nq.subject AS subject, nq.analysis_json AS neet_analysis,
                     mq.question_number AS mock_qno, mq.question_ordinal AS mock_ordinal, mp.label AS mock_label, mp.test_number AS test_number,
                     mp.filename AS mock_filename, mq.question_text AS mock_text, mq.analysis_json AS mock_analysis
              FROM matches m
              JOIN questions nq ON nq.id=m.neet_question_id JOIN papers np ON np.id=nq.paper_id
              JOIN questions mq ON mq.id=m.mock_question_id JOIN papers mp ON mp.id=mq.paper_id
              ORDER BY nq.question_number, m.confidence DESC"""
    with connect() as conn:
        rows = conn.execute(query).fetchall()
    results = []
    for row in rows:
        d = dict(row)
        d["evidence"] = json.loads(d.pop("evidence_json", "[]"))
        d["neet_analysis"] = json.loads(d["neet_analysis"]) if d.get("neet_analysis") else {}
        d["mock_analysis"] = json.loads(d["mock_analysis"]) if d.get("mock_analysis") else {}
        results.append(d)
    return results


def set_state(key: str, value: Any) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO run_state(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (key, json.dumps(value, ensure_ascii=False), utcnow()))


def get_state(key: str, default: Any = None) -> Any:
    with connect() as conn:
        row = conn.execute("SELECT value FROM run_state WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def delete_papers_by_kind(kind: str) -> None:
    with connect() as conn:
        ids = [r[0] for r in conn.execute("SELECT id FROM papers WHERE kind=?", (kind,)).fetchall()]
        if ids:
            conn.executemany("DELETE FROM papers WHERE id=?", [(x,) for x in ids])
        if kind == "neet":
            conn.execute("DELETE FROM run_state WHERE key IN ('matched_neet_ids','matching_signature')")


def delete_paper_by_filename(kind: str, filename: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM papers WHERE kind=? AND filename=?", (kind, filename))


def update_question_content(question_id: str, question_text: str, options: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute("UPDATE questions SET question_text=?, options_json=?, analysis_json=NULL, extraction_confidence=1.0 WHERE id=?",
                     (question_text, json.dumps(options, ensure_ascii=False), question_id))
        conn.execute("DELETE FROM matches")
        conn.execute("DELETE FROM match_runs")
        conn.execute("DELETE FROM run_state WHERE key IN ('matched_neet_ids','matching_signature')")