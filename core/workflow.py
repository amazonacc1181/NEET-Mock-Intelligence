from __future__ import annotations

import json
import re
import hashlib
from pathlib import Path
from typing import Any, Callable

from core import config
from core.database import (
    get_papers, get_questions, get_state, save_document_text, replace_questions,
    save_matches, set_state, upsert_paper, delete_paper_by_filename, save_match_run, clear_matches,
)
from core.llm import (
    LLMError, analyze_question_batch, analyze_single_question, classify_matches,
    get_primary_client, get_verifier_client, get_vision_client, verify_match_batch,
)
from core.pdf_pipeline import folder_pdfs, infer_doc_kind, ingest_pdf
from core.retrieval import HybridRetriever

Progress = Callable[[int, int, str], None]


def _noop_progress(current: int, total: int, message: str) -> None:
    return None


def ingest_folder(folder: Path, forced_kind: str, progress: Progress | None = None) -> dict[str, Any]:
    progress = progress or _noop_progress
    files = folder_pdfs(folder)
    existing = {p["sha256"] for p in get_papers()}
    imported, skipped, warnings = [], [], []
    for i, path in enumerate(files, start=1):
        progress(i, len(files), f"Reading {path.name}")
        try:
            kind = infer_doc_kind(path.name, forced_kind)
            # Solution uploads in their dedicated folder are always treated as solution material.
            result = ingest_pdf(path, kind=kind, fallback_test_number=i)
            if result["paper"]["sha256"] in existing:
                skipped.append(path.name)
                continue
            # Re-importing a changed PDF with the same filename replaces the older indexed copy.
            delete_paper_by_filename(kind, path.name)
            upsert_paper(result["paper"])
            replace_questions(result["paper"]["id"], result["questions"])
            save_document_text(result["paper"]["id"], result["full_text"])
            imported.append({
                "filename": path.name,
                "kind": kind,
                "questions": len(result["questions"]),
                "pages": result["paper"]["page_count"],
                "warnings": result["warnings"],
                "paper_id": result["paper"]["id"],
            })
            warnings.extend(f"{path.name}: {w}" for w in result["warnings"])
            existing.add(result["paper"]["sha256"])
        except Exception as exc:
            warnings.append(f"{path.name}: import failed: {type(exc).__name__}: {exc}")
    return {"imported": imported, "skipped": skipped, "warnings": warnings}


def ingest_one_file(path: Path, kind: str, fallback_test_number: int = 1) -> dict[str, Any]:
    result = ingest_pdf(path, kind=kind, fallback_test_number=fallback_test_number)
    already = {p["sha256"] for p in get_papers()}
    if result["paper"]["sha256"] not in already:
        delete_paper_by_filename(kind, path.name)
        upsert_paper(result["paper"])
        replace_questions(result["paper"]["id"], result["questions"])
        save_document_text(result["paper"]["id"], result["full_text"])
    return result


def _solution_lookup() -> dict[tuple[int | None, int], str]:
    solution_questions = get_questions("solution")
    result: dict[tuple[int | None, int], str] = {}
    for q in solution_questions:
        key = (q.get("test_number"), int(q["question_number"]))
        # Prefer richer solution text if repeated.
        if len(q.get("question_text", "")) > len(result.get(key, "")):
            result[key] = q.get("question_text", "")
    return result


def analyze_bank(kind: str = "mock", progress: Progress | None = None, batch_size: int | None = None) -> dict[str, Any]:
    progress = progress or _noop_progress
    client = get_primary_client()
    vision_client = get_vision_client()
    questions = get_questions(kind, unanalysed_only=True)
    if not questions:
        return {"analyzed": 0, "remaining": 0, "errors": []}
    sol_index = {(q.get("test_number"), int(q.get("question_ordinal", q["question_number"]))): q.get("question_text", "") for q in get_questions("solution")}
    for q in questions:
        q["source_solution"] = sol_index.get((q.get("test_number"), int(q.get("question_ordinal", q["question_number"]))), "")
    batch_size = max(1, min(12, batch_size or config.LLM_BATCH_SIZE))
    errors: list[str] = []
    analyzed = 0
    for start in range(0, len(questions), batch_size):
        batch = questions[start:start + batch_size]
        progress(min(start + len(batch), len(questions)), len(questions), f"Analysing {kind} questions {start + 1}–{start + len(batch)}")
        try:
            results = analyze_question_batch(client, batch, vision_client)
            missing = [q for q in batch if q["id"] not in results]
            for q in batch:
                if q["id"] in results:
                    data = results[q["id"]]
                    data["solution_origin"] = "Provided in separate mock solution PDF (AI interpreted)" if q.get("source_solution") else ("AI-derived, unverified" if data.get("answer") not in (None, "", "Uncertain") else "Not solved")
                    data["_analysis_version"] = 1
                    from core.database import update_analysis
                    update_analysis(q["id"], data)
                    analyzed += 1
            # Retry omissions one by one; a batch response should not silently lose questions.
            for q in missing:
                try:
                    data = analyze_single_question(client, q, vision_client)
                    data["solution_origin"] = "Provided in separate mock solution PDF (AI interpreted)" if q.get("source_solution") else ("AI-derived, unverified" if data.get("answer") not in (None, "", "Uncertain") else "Not solved")
                    data["_analysis_version"] = 1
                    from core.database import update_analysis
                    update_analysis(q["id"], data)
                    analyzed += 1
                except Exception as exc:
                    errors.append(f"{q.get('label')} Q{q['question_number']}: {exc}")
        except Exception as batch_exc:
            # Fail safely and retry individually. Checkpoint each successful result.
            errors.append(f"Batch starting at {start + 1}: {type(batch_exc).__name__}: {batch_exc}")
            for q in batch:
                try:
                    data = analyze_single_question(client, q, vision_client)
                    data["solution_origin"] = "Provided in separate mock solution PDF (AI interpreted)" if q.get("source_solution") else ("AI-derived, unverified" if data.get("answer") not in (None, "", "Uncertain") else "Not solved")
                    data["_analysis_version"] = 1
                    from core.database import update_analysis
                    update_analysis(q["id"], data)
                    analyzed += 1
                except Exception as exc:
                    errors.append(f"{q.get('label')} Q{q['question_number']}: {exc}")
    remaining = len(get_questions(kind, unanalysed_only=True))
    return {"analyzed": analyzed, "remaining": remaining, "errors": errors}


def analyze_neet_paper(progress: Progress | None = None) -> dict[str, Any]:
    return analyze_bank(kind="neet", progress=progress)


def run_matching(progress: Progress | None = None, top_candidates: int | None = None, use_verifier: bool = True) -> dict[str, Any]:
    progress = progress or _noop_progress
    mock_questions = get_questions("mock")
    neet_questions = get_questions("neet")
    if not mock_questions:
        raise ValueError("No mock questions found. Put the 30 mock PDFs in input/mock_papers and ingest them first.")
    if not neet_questions:
        raise ValueError("No NEET paper found. Upload it in the NEET 2026 tab first.")
    unanalysed_mock = [q for q in mock_questions if not q.get("analysis")]
    unanalysed_neet = [q for q in neet_questions if not q.get("analysis")]
    if unanalysed_mock or unanalysed_neet:
        raise ValueError(f"Analysis is incomplete: {len(unanalysed_mock)} mock and {len(unanalysed_neet)} NEET questions still need AI analysis.")

    retriever = HybridRetriever(mock_questions, config.EMBEDDING_MODEL, config.ENABLE_EMBEDDINGS)
    primary = get_primary_client()
    verifier = get_verifier_client() if use_verifier else None
    vision = get_vision_client()
    candidate_n = top_candidates or config.TOP_CANDIDATES
    processed = set(get_state("matched_neet_ids", []))
    newly_matched = 0
    errors: list[str] = []

    # A new mock bank invalidates the previous processed-ID marker; paper IDs are included in the run signature.
    signature = ":".join(sorted(q["id"] for q in mock_questions))
    signature_key = hashlib.sha256(signature.encode("utf-8")).hexdigest()
    last_signature = get_state("matching_signature")
    if last_signature != signature_key:
        processed = set()
        clear_matches()
        set_state("matched_neet_ids", [])
        set_state("matching_signature", signature_key)

    for index, nq in enumerate(neet_questions, start=1):
        if nq["id"] in processed:
            progress(index, len(neet_questions), f"Already completed NEET Q{nq['question_number']}; resuming")
            continue
        progress(index, len(neet_questions), f"Finding and verifying matches for NEET Q{nq['question_number']}")
        try:
            subject = nq.get("subject") or (nq.get("analysis") or {}).get("subject")
            # Subject-constrained retrieval prevents semantically similar but irrelevant cross-subject results.
            ranked = retriever.rank(nq, candidate_n, subject_filter=subject)
            if len(ranked) < min(8, candidate_n):
                ranked = retriever.rank(nq, candidate_n)
            candidates = [(q, score) for q, score in ranked if q["id"] != nq["id"]]
            # Add exact text candidates at the top if the normalized question appears in the bank.
            matches, no_match_reason = classify_matches(primary, nq, candidates, vision)
            matches = matches[:config.MAX_MATCHES_PER_NEET_QUESTION]
            if verifier and matches:
                before_count = len(matches)
                try:
                    matches = verify_match_batch(verifier, nq, mock_questions, matches)
                except Exception as verifier_exc:
                    for match in matches:
                        match["verification_status"] = f"Verifier unavailable; primary result retained ({type(verifier_exc).__name__})"
                if before_count and not matches:
                    no_match_reason = "The independent verifier rejected every proposed candidate."
            save_matches(nq["id"], matches)
            save_match_run(nq["id"], "matched" if matches else "no_meaningful_match", no_match_reason, len(candidates))
            processed.add(nq["id"])
            set_state("matched_neet_ids", sorted(processed))
            newly_matched += len(matches)
        except Exception as exc:
            errors.append(f"NEET Q{nq['question_number']}: {type(exc).__name__}: {exc}")
            # Do not mark a failed question complete. The next run resumes it.
    return {
        "questions_total": len(neet_questions),
        "questions_processed": len(processed),
        "matches_created": newly_matched,
        "embedding_status": retriever.embedding_status,
        "verifier_enabled": bool(verifier),
        "vision_enabled": bool(vision),
        "errors": errors,
    }