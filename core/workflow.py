from __future__ import annotations

import json
import re
import hashlib
from pathlib import Path
from typing import Any, Callable

from core import config
from core.database import (
    get_papers, get_questions, get_state, save_document_text, replace_questions,
    save_matches, set_state, upsert_paper, delete_paper_by_filename, save_match_run, clear_matches, checkpoint_database,
)
from core.llm import (
    LLMError, analyze_question_batch, analyze_single_question, classify_matches,
    get_primary_client, get_verifier_client, get_vision_client, verify_match_batch, audit_question_analyses, manager_review,
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
            checkpoint_database()
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
        checkpoint_database()
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
    verifier = get_verifier_client()
    vision_client = get_vision_client()
    questions = get_questions(kind, unanalysed_only=True)
    if not questions:
        return {"analyzed": 0, "remaining": 0, "errors": [], "verified": 0}
    sol_index = {(q.get("test_number"), int(q.get("question_ordinal", q["question_number"]))): q.get("question_text", "") for q in get_questions("solution")}
    for q in questions:
        q["source_solution"] = sol_index.get((q.get("test_number"), int(q.get("question_ordinal", q["question_number"]))), "")
    batch_size = max(1, min(8, batch_size or config.LLM_BATCH_SIZE))
    errors: list[str] = []
    analyzed = 0
    verified = 0

    def save_results(batch: list[dict[str, Any]], results: dict[str, dict[str, Any]]) -> None:
        nonlocal analyzed, verified
        qa_reviews: dict[str, dict[str, Any]] = {}
        if verifier and results:
            try:
                qa_reviews = audit_question_analyses(verifier, batch, results)
                verified += len(qa_reviews)
            except Exception as exc:
                errors.append(f"Independent subject/solution audit unavailable for batch: {type(exc).__name__}: {exc}")
        from core.database import update_analysis
        for question in batch:
            data = results.get(question["id"])
            if not data:
                continue
            data["solution_origin"] = "Provided in separate mock solution PDF (AI interpreted)" if question.get("source_solution") else ("AI-derived, unverified" if data.get("answer") not in (None, "", "Uncertain") else "Not solved")
            data["_analysis_version"] = 2
            if question["id"] in qa_reviews:
                review = qa_reviews[question["id"]]
                data["_independent_review"] = review
                corrections = review.get("corrected_fields") or {}
                if review.get("status") == "CORRECTED" and isinstance(corrections, dict):
                    # Keep an audit trail before applying a verifier correction.
                    data["_pre_audit_values"] = {key: data.get(key) for key in corrections}
                    for key, value in corrections.items():
                        if key in {"subject", "chapter", "topic", "subtopic", "core_concept", "concept_tags", "question_type", "difficulty", "formulae_or_laws", "reactions_or_mechanisms", "ncert_anchor", "answer", "solution_steps", "common_traps"}:
                            data[key] = value
            else:
                data["_independent_review"] = {"status": "NOT_RUN", "issues": ["No independent verifier model was available for this run."], "answer_check": "UNCERTAIN", "concept_check": "UNCERTAIN"}
            update_analysis(question["id"], data)
            analyzed += 1
        checkpoint_database()

    for start in range(0, len(questions), batch_size):
        batch = questions[start:start + batch_size]
        progress(min(start + len(batch), len(questions)), len(questions), f"Subject Analyst: analysing {kind} questions {start + 1}–{start + len(batch)}")
        try:
            results = analyze_question_batch(client, batch, vision_client)
            missing = [q for q in batch if q["id"] not in results]
            save_results(batch, results)
            # Retry omissions individually; do not silently drop any question.
            for q in missing:
                try:
                    one = analyze_single_question(client, q, vision_client)
                    save_results([q], {q["id"]: one})
                except Exception as exc:
                    errors.append(f"{q.get('label')} Q{q['question_number']}: {exc}")
        except Exception as batch_exc:
            errors.append(f"Batch starting at {start + 1}: {type(batch_exc).__name__}: {batch_exc}")
            for q in batch:
                try:
                    data = analyze_single_question(client, q, vision_client)
                    save_results([q], {q["id"]: data})
                except Exception as exc:
                    errors.append(f"{q.get('label')} Q{q['question_number']}: {exc}")
    remaining = len(get_questions(kind, unanalysed_only=True))
    return {"analyzed": analyzed, "remaining": remaining, "errors": errors, "verified": verified}


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

    retriever = HybridRetriever(mock_questions, config.EMBEDDING_MODEL, config.ENABLE_EMBEDDINGS, config.ENABLE_RERANKER, config.RERANKER_MODEL)
    primary = get_primary_client()
    verifier = get_verifier_client() if use_verifier else None
    vision = get_vision_client()
    candidate_n = top_candidates or config.TOP_CANDIDATES
    processed = set(get_state("matched_neet_ids", []))
    newly_matched = 0
    errors: list[str] = []

    # A new mock bank invalidates the previous processed-ID marker; paper IDs are included in the run signature.
    # A new target NEET paper must invalidate the prior match checkpoint too.
    signature = ":".join(sorted([q["id"] for q in mock_questions] + ["NEET:" + q["id"] for q in neet_questions]))
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
            checkpoint_database()
            newly_matched += len(matches)
        except Exception as exc:
            errors.append(f"NEET Q{nq['question_number']}: {type(exc).__name__}: {exc}")
            # Do not mark a failed question complete. The next run resumes it.
    return {
        "questions_total": len(neet_questions),
        "questions_processed": len(processed),
        "matches_created": newly_matched,
        "embedding_status": retriever.embedding_status,
        "reranker_status": retriever.reranker_status,
        "verifier_enabled": bool(verifier),
        "vision_enabled": bool(vision),
        "errors": errors,
    }



def run_full_analysis(mock_dir: Path, solution_dir: Path, neet_pdf: Path, progress: Progress | None = None) -> dict[str, Any]:
    """Manager-controlled, resumable, end-to-end local analysis and report generation."""
    progress = progress or _noop_progress
    from core.reporting import export_pdf_report, export_workbook, export_mock_catalogue_pdf
    manager = get_primary_client()
    warnings: list[str] = []
    progress(1, 100, "Manager: checking the local AI team and source folders…")
    mock_ingest = ingest_folder(mock_dir, "mock", lambda i, n, m: progress(2 + int(8 * i / max(n, 1)), 100, "PDF Specialist: " + m))
    solution_ingest = ingest_folder(solution_dir, "solution", lambda i, n, m: progress(11 + int(3 * i / max(n, 1)), 100, "Solution PDF Specialist: " + m)) if folder_pdfs(solution_dir) else {"imported": [], "skipped": [], "warnings": []}
    neet_result = ingest_one_file(neet_pdf, "neet", 1)
    warnings.extend(mock_ingest["warnings"])
    warnings.extend(solution_ingest["warnings"])
    warnings.extend(neet_result.get("warnings", []))
    mock_questions = get_questions("mock")
    neet_questions = get_questions("neet")
    papers = get_papers()
    mock_papers = [p for p in papers if p["kind"] == "mock"]
    odd_papers = [p for p in mock_papers if p["question_count"] != config.EXPECTED_MOCK_QUESTIONS]
    if len(mock_papers) != 30:
        warnings.append(f"Expected 30 mock test PDFs; found {len(mock_papers)}. Check that every intended paper was uploaded.")
    if len(mock_questions) != config.EXPECTED_MOCK_QUESTIONS * 30:
        warnings.append(f"Expected about {config.EXPECTED_MOCK_QUESTIONS * 30} mock questions across 30 papers; extracted {len(mock_questions)}. Inspect PDF extraction QA.")
    if len(neet_questions) != config.EXPECTED_NEET_QUESTIONS:
        warnings.append(f"Expected {config.EXPECTED_NEET_QUESTIONS} NEET questions; extracted {len(neet_questions)}. Inspect the source PDF and extraction QA.")
    preflight = {
        "mock_papers": len(mock_papers),
        "mock_questions_extracted": len(mock_questions),
        "expected_mock_questions": config.EXPECTED_MOCK_QUESTIONS * 30,
        "papers_with_nonstandard_question_count": [{"file": p["filename"], "questions": p["question_count"]} for p in odd_papers],
        "neet_questions_extracted": len(neet_questions),
        "expected_neet_questions": config.EXPECTED_NEET_QUESTIONS,
        "source_warnings": warnings[:80],
    }
    try:
        preflight_review = manager_review(manager, "PAPER INGESTION QUALITY GATE", preflight, warnings)
    except Exception as exc:
        preflight_review = {"phase": "PAPER INGESTION QUALITY GATE", "status": "WARNING", "key_findings": [f"Manager review unavailable: {exc}"], "next_actions": []}
    set_state("manager_preflight_review", preflight_review)
    checkpoint_database()

    # Hard gate: never produce a report that silently omits questions because a PDF
    # was missing, scanned badly, or segmented incorrectly.
    if len(mock_papers) != 30 or odd_papers or len(mock_questions) != config.EXPECTED_MOCK_QUESTIONS * 30 or len(neet_questions) != config.EXPECTED_NEET_QUESTIONS:
        raise RuntimeError(
            "PDF extraction quality gate failed. Expected 30 mock papers with 180 questions each / 5,400 mock questions / "
            f"{config.EXPECTED_NEET_QUESTIONS} NEET questions, but found {len(mock_papers)} papers / "
            f"{len(mock_questions)} mock questions / {len(neet_questions)} NEET questions. "
            "No final report was released. The import and extraction records are saved; check the PDF quality, "
            "OCR and page layout, then resume or re-import the corrected PDFs."
        )

    progress(15, 100, f"Manager: {len(mock_questions):,} mock questions and {len(neet_questions)} NEET questions indexed. Starting specialist analysis…")
    mock_analysis = analyze_bank("mock", lambda i, n, m: progress(15 + int(46 * i / max(n, 1)), 100, m))
    neet_analysis = analyze_bank("neet", lambda i, n, m: progress(62 + int(8 * i / max(n, 1)), 100, m))
    warnings.extend(mock_analysis["errors"][:80])
    warnings.extend(neet_analysis["errors"][:40])
    remaining_mock = len(get_questions("mock", unanalysed_only=True))
    remaining_neet = len(get_questions("neet", unanalysed_only=True))
    if remaining_mock or remaining_neet:
        raise RuntimeError(f"Analysis is not complete: {remaining_mock} mock and {remaining_neet} NEET questions are pending. Fix model errors and resume; no final report was marked complete.")

    progress(71, 100, "Relationship Examiner: retrieving and comparing mock candidates for each NEET question…")
    match_result = run_matching(lambda i, n, m: progress(71 + int(21 * i / max(n, 1)), 100, "Relationship Examiner / Independent Verifier: " + m), top_candidates=config.TOP_CANDIDATES, use_verifier=True)
    warnings.extend(match_result["errors"][:40])
    if match_result["questions_processed"] < len(neet_questions):
        raise RuntimeError(
            f"Matching is incomplete: {match_result['questions_processed']} of {len(neet_questions)} "
            "NEET questions have been processed. No final PDF was released. Fix the listed errors and rerun; "
            "the saved checkpoints will resume the work."
        )

    final_metrics = {
        "mock_papers": len(mock_papers),
        "mock_questions": len(mock_questions),
        "mock_analysis_remaining": remaining_mock,
        "neet_questions": len(neet_questions),
        "neet_analysis_remaining": remaining_neet,
        "neet_questions_processed_for_matching": match_result["questions_processed"],
        "accepted_matches": match_result["matches_created"],
        "candidate_retrieval": match_result["embedding_status"],
        "cross_encoder_reranker": match_result.get("reranker_status", "Not run"),
        "independent_match_verifier_enabled": match_result["verifier_enabled"],
        "vision_model_enabled": match_result["vision_enabled"],
        "warnings": warnings[:80],
    }
    try:
        final_review = manager_review(manager, "FINAL REPORT RELEASE GATE", final_metrics, warnings)
    except Exception as exc:
        final_review = {"phase": "FINAL REPORT RELEASE GATE", "status": "WARNING", "key_findings": [f"Manager review unavailable: {exc}"], "next_actions": []}
    set_state("manager_final_review", final_review)

    progress(94, 100, "Report QA Editor: generating the detailed NEET relationship PDF and audit workbook…")
    pdf_path = config.DATA_DIR / "NEET_2026_Mock_Comparison_Detailed_Report.pdf"
    workbook_path = config.DATA_DIR / "NEET_2026_Mock_Comparison_Audit_Workbook.xlsx"
    catalogue_path = config.DATA_DIR / "All_Mock_Questions_Analysis_Catalogue.pdf"
    export_pdf_report(pdf_path)
    export_mock_catalogue_pdf(catalogue_path)
    export_workbook(workbook_path)
    progress(100, 100, "Complete. Report files generated locally.")
    return {
        "mock_ingest": mock_ingest,
        "solution_ingest": solution_ingest,
        "neet_ingest": neet_result,
        "mock_analysis": mock_analysis,
        "neet_analysis": neet_analysis,
        "matching": match_result,
        "preflight_review": preflight_review,
        "final_review": final_review,
        "warnings": warnings,
        "pdf_path": str(pdf_path),
        "catalogue_path": str(catalogue_path),
        "workbook_path": str(workbook_path),
    }