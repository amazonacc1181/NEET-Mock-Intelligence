from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import config
from core.database import init_db, get_papers, get_questions, get_match_rows, get_match_run_map, delete_papers_by_kind, update_question_content
from core.llm import RELATIONSHIP_LABELS, get_primary_client, get_verifier_client, get_vision_client, LLMError
from core.pdf_pipeline import save_uploaded_file, folder_pdfs
from core.reporting import export_workbook, export_pdf_report
from core.workflow import ingest_folder, ingest_one_file, analyze_bank, run_matching, run_full_analysis
from core.local_ai import connection_status, configure_local_ai, hardware_profile, model_plan
from core.agent_team import team_status

st.set_page_config(page_title="NEET Mock Intelligence", page_icon="🧠", layout="wide")
init_db()

st.markdown("""
<style>
.block-container {padding-top: 1.5rem; padding-bottom: 2.5rem; max-width: 1500px;}
[data-testid="stMetric"] {background: rgba(120,130,145,.08); border: 1px solid rgba(120,130,145,.18); padding: 12px 14px; border-radius: 12px;}
.small-muted {color: #87909d; font-size: .88rem;}
.step-card {padding: 12px 14px; border: 1px solid rgba(130,140,150,.24); border-radius: 12px;}
</style>
""", unsafe_allow_html=True)

st.title("🧠 NEET Mock Intelligence")
st.caption("Analyse your mock papers once. Then compare every NEET question against the indexed mock-question bank.")


def progress_callback(bar, status):
    def update(current: int, total: int, message: str):
        if total <= 0:
            bar.progress(0)
        else:
            bar.progress(min(1.0, current / total))
        status.info(message)
    return update


def show_warnings(items: list[str]):
    if items:
        with st.expander(f"Review {len(items)} warning(s)", expanded=True):
            for w in items:
                st.warning(w)


def paper_metrics():
    papers = get_papers()
    qs = get_questions()
    mocks = [q for q in qs if q["kind"] == "mock"]
    neet = [q for q in qs if q["kind"] == "neet"]
    analyzed_mock = sum(bool(q.get("analysis")) for q in mocks)
    analyzed_neet = sum(bool(q.get("analysis")) for q in neet)
    return papers, mocks, neet, analyzed_mock, analyzed_neet

papers, mocks, neet, analyzed_mock, analyzed_neet = paper_metrics()

# Sidebar: provider setup and workflow navigation.
with st.sidebar:
    st.header("Workflow")
    page = st.radio("Go to", ["ONE-CLICK: Full analysis", "Overview", "1 · Mock PDFs", "2 · Analyse mock bank", "3 · NEET 2026 paper", "4 · Match & report", "Question review"], label_visibility="collapsed")
    st.divider()
    st.subheader("Local AI team")
    local_status = connection_status()
    primary_ready = bool(local_status["running"] and config.LLM_MODEL and config.LLM_MODEL in local_status["models"])
    st.write("Ollama local engine:", "🟢 running" if local_status["running"] else "🔴 not running")
    st.caption(f"Main model: {config.LLM_MODEL or 'not configured'}")
    st.write("Independent verifier:", "🟢 configured" if config.VERIFY_MODEL else "⚪ same-model review")
    st.write("Vision model:", "🟢 configured" if config.VISION_MODEL else "⚪ not configured")
    st.caption("No cloud API key is required. Models run on this computer after their one-time download.")

if page == "ONE-CLICK: Full analysis":
    st.header("Run the complete NEET mock comparison")
    st.write("Upload your mock question papers and the actual NEET 2026 paper here. The local AI team will extract, analyse, compare, verify and prepare the final detailed PDF and audit workbook.")
    profile = hardware_profile()
    plan = model_plan(profile)
    c1, c2, c3 = st.columns(3)
    c1.metric("System RAM", f"{profile['ram_gb']} GB")
    c2.metric("GPU VRAM", f"{profile['vram_gb']} GB")
    c3.metric("Free disk", f"{profile['free_disk_gb']} GB")
    st.info(f"Recommended local setup: **{plan['tier']}** · Main model: `{plan['primary_model'] or 'not supported'}` · Independent verifier: `{plan['verifier_model'] or 'not available on this hardware'}`. {plan['note']}")
    if not local_status["running"] or not primary_ready:
        st.warning("The local AI engine/model is not ready yet. On first use, the launcher installs Ollama (where supported) and downloads the selected open-weight model. You can also repair the setup below.")
        if st.button("Set up / repair local AI models", type="primary"):
            with st.status("Preparing local AI models…", expanded=True) as status_box:
                try:
                    def model_progress(message):
                        status_box.write(message)
                    setup_result = configure_local_ai(model_progress)
                    status_box.update(label="Local AI is ready", state="complete")
                    st.success(f"Main model: {setup_result['plan']['primary_model']}. No API key used.")
                    st.rerun()
                except Exception as exc:
                    status_box.update(label="Local AI setup needs attention", state="error")
                    st.error(str(exc))
        st.markdown("Install Ollama manually if needed: [ollama.com/download](https://ollama.com/download). Then restart this app.")

    st.divider()
    mock_uploads = st.file_uploader("1. Upload all 30 mock question-paper PDFs", type=["pdf"], accept_multiple_files=True, key="full_mock_uploads")
    solution_uploads = st.file_uploader("2. Optional: upload mock answer keys / detailed solutions", type=["pdf"], accept_multiple_files=True, key="full_solution_uploads")
    neet_upload = st.file_uploader("3. Upload the actual NEET 2026 question-paper PDF", type=["pdf"], accept_multiple_files=False, key="full_neet_upload")
    mock_existing = folder_pdfs(config.MOCK_DIR)
    neet_existing = folder_pdfs(config.NEET_DIR)
    st.caption(f"Already in local folders: {len(mock_existing)} mock PDFs · {len(folder_pdfs(config.SOLUTION_DIR))} solution PDFs · {len(neet_existing)} NEET PDF(s). Uploads are stored locally; nothing is pushed back to GitHub.")
    ready_to_run = bool((mock_uploads or mock_existing) and (neet_upload or neet_existing) and primary_ready)
    if st.button("START COMPLETE ANALYSIS — generate final PDF", type="primary", use_container_width=True, disabled=not ready_to_run):
        with st.status("The AI team is working through your papers…", expanded=True) as work_status:
            bar = st.progress(0.0)
            message = st.empty()
            try:
                for f in mock_uploads or []:
                    save_uploaded_file(f, config.MOCK_DIR)
                for f in solution_uploads or []:
                    save_uploaded_file(f, config.SOLUTION_DIR)
                if neet_upload is not None:
                    target = config.NEET_DIR / "NEET_2026.pdf"
                    target.write_bytes(neet_upload.getbuffer())
                    neet_path = target
                else:
                    neet_path = neet_existing[0]
                result = run_full_analysis(config.MOCK_DIR, config.SOLUTION_DIR, neet_path, progress_callback(bar, message))
                st.session_state["full_analysis_result"] = result
                work_status.update(label="Analysis and report generation finished", state="complete")
            except Exception as exc:
                work_status.update(label="Analysis stopped — resume after fixing the issue", state="error")
                st.error(f"{type(exc).__name__}: {exc}")
                st.info("Completed question analyses and matching results are checkpointed in the local database. Fix the issue and press the button again to resume.")

    result = st.session_state.get("full_analysis_result")
    if result:
        st.success("The report files have been generated locally.")
        col1, col2 = st.columns(2)
        pdf_file = Path(result["pdf_path"])
        catalogue_file = Path(result["catalogue_path"])
        workbook_file = Path(result["workbook_path"])
        if pdf_file.exists():
            col1.download_button("Download detailed NEET comparison PDF", data=pdf_file.read_bytes(), file_name=pdf_file.name, mime="application/pdf", type="primary", use_container_width=True)
        if workbook_file.exists():
            col2.download_button("Download complete audit workbook", data=workbook_file.read_bytes(), file_name=workbook_file.name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        if catalogue_file.exists():
            st.download_button("Download all-mock-question analysis catalogue PDF", data=catalogue_file.read_bytes(), file_name=catalogue_file.name, mime="application/pdf", use_container_width=True)
        st.subheader("Manager's final quality review")
        st.json(result.get("final_review", {}))
        st.subheader("Run summary")
        st.write({"Mock questions analysed": result["mock_analysis"]["analyzed"], "NEET questions analysed": result["neet_analysis"]["analyzed"], "Accepted mock matches": result["matching"]["matches_created"], "Verifier enabled": result["matching"]["verifier_enabled"], "Vision model enabled": result["matching"]["vision_enabled"]})
        show_warnings(result.get("warnings", []))

    st.divider()
    st.subheader("AI company-style division of labour")
    for agent in team_status(config.LLM_MODEL, config.VERIFY_MODEL, config.VISION_MODEL, config.EMBEDDING_MODEL):
        st.markdown(f"**{agent['name']}** · `{agent['model']}`  " + "\n" + agent["mode"])

elif page == "Overview":
    a, b, c, d = st.columns(4)
    a.metric("Mock PDFs", sum(p["kind"] == "mock" for p in papers))
    b.metric("Mock questions", f"{len(mocks):,}")
    c.metric("Mock questions analysed", f"{analyzed_mock:,} / {len(mocks):,}")
    d.metric("NEET questions", f"{len(neet):,}")

    st.subheader("Your four-step workflow")
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown("**1. Add mock papers**\n\nPut 30 PDFs in `input/mock_papers/` or upload them in the Mock PDFs tab.")
    c2.markdown("**2. Analyse the bank**\n\nExtract every question, concept, chapter, formulas and solution steps.")
    c3.markdown("**3. Add NEET 2026**\n\nUpload the actual NEET paper and extract its questions.")
    c4.markdown("**4. Match & export**\n\nFind and explain exact, data-changed, pattern, conceptual and NCERT relationships.")

    st.subheader("Project folders")
    st.code("input/mock_papers/     ← place your 30 mock PDFs here\ninput/mock_solutions/  ← optional separate solution PDFs / keys\ninput/neet_2026/       ← actual NEET paper is uploaded here\ndata/                  ← local database, previews and reports", language="text")
    st.info("Your PDF files and question database stay on this computer by default. Do not commit PDFs, API keys or the data folder to a public GitHub repository.")

    if not primary_ready:
        st.warning("Run the one-time local AI setup from the ONE-CLICK page or launch script. No cloud API key is required.")

    if papers:
        st.subheader("Imported PDFs")
        df = pd.DataFrame([{"Type":p["kind"],"PDF":p["filename"],"Test":p.get("test_number"),"Pages":p["page_count"],"Questions":p["question_count"],"Status":p["status"]} for p in papers])
        st.dataframe(df, use_container_width=True, hide_index=True)

elif page == "1 · Mock PDFs":
    st.header("1. Add your 30 mock papers")
    st.write("You can either copy files directly into the folder or upload them here. Each PDF should ideally contain one complete 180-question test.")
    with st.expander("Folder location", expanded=True):
        st.code(str(config.MOCK_DIR), language="text")
        st.caption("For reliable test references, use filenames such as Allen_Test_01.pdf, Allen_Test_02.pdf … Allen_Test_30.pdf.")

    uploaded = st.file_uploader("Upload mock question PDFs", type=["pdf"], accept_multiple_files=True, key="mock_uploads")
    if uploaded and st.button("Save uploaded mock PDFs", type="primary"):
        saved = []
        for f in uploaded:
            p = save_uploaded_file(f, config.MOCK_DIR)
            saved.append(p.name)
        st.success(f"Saved {len(saved)} PDF(s) to input/mock_papers/.")
        st.write(saved)

    files = folder_pdfs(config.MOCK_DIR)
    st.metric("PDFs currently in mock_papers folder", len(files))
    if files:
        st.dataframe(pd.DataFrame([{"Filename":p.name,"Size (MB)":round(p.stat().st_size/1024/1024,2)} for p in files]), use_container_width=True, hide_index=True)
    else:
        st.warning("No PDFs found yet. Add your 30 files to the folder above.")

    if st.button("Read / import mock PDFs from folder", type="primary", disabled=not files):
        bar = st.progress(0.0); status = st.empty()
        result = ingest_folder(config.MOCK_DIR, "mock", progress_callback(bar, status))
        st.success(f"Imported {len(result['imported'])} PDF(s); skipped {len(result['skipped'])} already-imported file(s).")
        if result["imported"]:
            st.dataframe(pd.DataFrame([{k:v for k,v in x.items() if k not in ("warnings","paper_id")} for x in result["imported"]]), use_container_width=True, hide_index=True)
        show_warnings(result["warnings"])
        st.rerun()

    st.divider()
    st.subheader("Optional: separate mock solution PDFs / answer explanations")
    st.caption("Place solution files in input/mock_solutions/. Name them with the same test number, e.g. Test_01_Solutions.pdf. If question-numbered solutions are detected, the AI will use them when analysing the matching mock questions.")
    st.code(str(config.SOLUTION_DIR), language="text")
    sol_uploaded = st.file_uploader("Upload solution / answer-key PDFs", type=["pdf"], accept_multiple_files=True, key="solution_uploads")
    if sol_uploaded and st.button("Save solution PDFs"):
        for f in sol_uploaded:
            save_uploaded_file(f, config.SOLUTION_DIR)
        st.success(f"Saved {len(sol_uploaded)} solution PDF(s).")
    sol_files = folder_pdfs(config.SOLUTION_DIR)
    st.write(f"Solution PDFs in folder: **{len(sol_files)}**")
    if st.button("Import solution PDFs", disabled=not sol_files):
        bar = st.progress(0.0); status = st.empty()
        result = ingest_folder(config.SOLUTION_DIR, "solution", progress_callback(bar, status))
        st.success(f"Imported {len(result['imported'])} solution PDF(s).")
        show_warnings(result["warnings"])
        st.rerun()

elif page == "2 · Analyse mock bank":
    st.header("2. Analyse all mock questions")
    if not mocks:
        st.warning("Import your mock PDFs first.")
    else:
        st.metric("Mock questions in database", f"{len(mocks):,}")
        st.metric("Questions already analysed", f"{analyzed_mock:,}")
        st.caption("Analysis includes subject, NCERT chapter, topic, concept, question style, formulas/reactions, answer and solution steps, traps and source confidence. Existing completed questions are retained; failed questions can be resumed.")
        batch_size = st.slider("Questions per AI request", min_value=1, max_value=12, value=config.LLM_BATCH_SIZE, help="Use smaller batches if the provider has a smaller context window. Failed batches are retried question-by-question.")
        if st.button("Analyse / resume all unanalysed mock questions", type="primary", disabled=not primary_ready):
            bar = st.progress(0.0); status = st.empty()
            try:
                result = analyze_bank("mock", progress_callback(bar, status), batch_size=batch_size)
                st.success(f"Analysed {result['analyzed']} question(s). Remaining: {result['remaining']}.")
                if result["errors"]:
                    show_warnings(result["errors"][:100])
            except Exception as exc:
                st.error(f"Analysis could not start: {exc}")
            st.rerun()
        if len(mocks) and analyzed_mock == len(mocks):
            st.success("All extracted mock questions have an AI analysis record.")
        if analyzed_mock < len(mocks):
            st.info("The analysis is checkpointed. It is safe to stop and resume later; already analysed questions are not reprocessed.")

elif page == "3 · NEET 2026 paper":
    st.header("3. Upload the actual NEET 2026 paper")
    st.caption("This replaces the currently indexed NEET comparison paper, but does not delete your mock question bank.")
    uploaded_neet = st.file_uploader("NEET 2026 question paper PDF", type=["pdf"], accept_multiple_files=False, key="neet_pdf")
    if uploaded_neet and st.button("Save NEET 2026 PDF", type="primary"):
        target = config.NEET_DIR / "NEET_2026.pdf"
        target.write_bytes(uploaded_neet.getbuffer())
        st.success("Saved NEET_2026.pdf.")

    neet_files = folder_pdfs(config.NEET_DIR)
    st.write(f"NEET PDF(s) found: **{len(neet_files)}**")
    if neet_files:
        st.dataframe(pd.DataFrame([{"Filename":p.name,"Size (MB)":round(p.stat().st_size/1024/1024,2)} for p in neet_files]), use_container_width=True, hide_index=True)
    if st.button("Parse / replace NEET comparison paper", type="primary", disabled=not neet_files):
        # The app intentionally supports one active NEET target paper at a time.
        target_path = neet_files[0]
        delete_papers_by_kind("neet")
        result = ingest_one_file(target_path, "neet", 1)
        st.success(f"Extracted {len(result['questions'])} NEET questions from {target_path.name}.")
        show_warnings(result["warnings"])
        st.rerun()

    neet_now = get_questions("neet")
    if neet_now:
        st.metric("NEET questions extracted", len(neet_now))
        st.metric("NEET questions analysed", sum(bool(q.get("analysis")) for q in neet_now))
        if not primary_ready:
            st.warning("Configure the primary model in .env before running AI analysis.")
        if st.button("Analyse / resume NEET 2026 questions", type="primary", disabled=not primary_ready):
            bar = st.progress(0.0); status = st.empty()
            result = analyze_bank("neet", progress_callback(bar, status))
            st.success(f"Analysed {result['analyzed']} NEET question(s); remaining {result['remaining']}.")
            show_warnings(result["errors"][:100])
            st.rerun()

elif page == "4 · Match & report":
    st.header("4. Match NEET questions against all mock tests")
    if not mocks or not neet:
        st.warning("You need an imported mock bank and an imported NEET 2026 paper.")
    else:
        st.write(f"Mock bank: **{len(mocks):,} questions** · NEET paper: **{len(neet)} questions**")
        pending_mock = sum(not q.get("analysis") for q in mocks)
        pending_neet = sum(not q.get("analysis") for q in neet)
        if pending_mock or pending_neet:
            st.error(f"Complete AI analysis first: {pending_mock} mock and {pending_neet} NEET questions remain.")
        else:
            st.success("Question analysis is complete. Ready to find candidate matches.")
        top_n = st.slider("Candidates examined per NEET question", 10, 60, config.TOP_CANDIDATES, 5, help="Larger candidate pools can improve recall but use more context and API tokens.")
        use_verifier = st.checkbox("Use independent second-model verification (recommended when configured)", value=bool(config.VERIFY_BASE_URL and config.VERIFY_MODEL), disabled=not bool(config.VERIFY_BASE_URL and config.VERIFY_MODEL))
        if vision_ready := bool(config.VISION_BASE_URL and config.VISION_MODEL):
            st.info("Vision model is configured. Page previews may be supplied for diagrams, graphs, apparatus and tables.")
        else:
            st.caption("No separate vision model configured. Text and OCR are used; diagrams still need manual page-preview review if they affect a match.")
        if st.button("Run / resume NEET-to-mock matching", type="primary", disabled=bool(pending_mock or pending_neet or not primary_ready)):
            bar = st.progress(0.0); status = st.empty()
            try:
                result = run_matching(progress_callback(bar, status), top_candidates=top_n, use_verifier=use_verifier)
                st.success(f"Processed {result['questions_processed']} of {result['questions_total']} NEET questions; new matches saved: {result['matches_created']}.")
                st.caption(f"Retrieval: {result['embedding_status']} · Verifier: {result['verifier_enabled']} · Vision: {result['vision_enabled']}")
                show_warnings(result["errors"][:100])
            except Exception as exc:
                st.error(str(exc))

        rows = get_match_rows()
        if rows:
            st.subheader("Current match results")
            summary = pd.DataFrame(rows)
            st.metric("Credible mock-to-NEET pairs", len(rows))
            st.dataframe(summary[["neet_qno","neet_ordinal","subject","mock_label","test_number","mock_qno","mock_ordinal","relationship","confidence","retrieval_score","verification_status"]].rename(columns={"neet_qno":"NEET Q","neet_ordinal":"NEET ordinal","subject":"Subject","mock_label":"Mock test","test_number":"Test no.","mock_qno":"Mock Q","mock_ordinal":"Mock ordinal","relationship":"Relationship code","confidence":"Confidence","retrieval_score":"Search score","verification_status":"Verification"}), use_container_width=True, hide_index=True)
            qnos = sorted({int(x["neet_qno"]) for x in rows})
            selected_q = st.selectbox("Inspect one NEET question", qnos)
            current = [x for x in rows if int(x["neet_qno"]) == selected_q]
            for i, m in enumerate(sorted(current, key=lambda x:x["confidence"], reverse=True), start=1):
                label = RELATIONSHIP_LABELS.get(m["relationship"], m["relationship"])
                with st.expander(f"{i}. {m['mock_label']} — Q{m['mock_qno']} (ordinal {m.get('mock_ordinal')}) · {label} · {m['confidence']:.0f}%", expanded=(i == 1)):
                    st.markdown("**Why they match**")
                    st.write(m.get("rationale", ""))
                    st.markdown("**Shared concept**")
                    st.write(m.get("shared_concept", ""))
                    st.markdown("**Differences**")
                    st.write(m.get("differences", ""))
                    st.markdown("**Solution comparison**")
                    st.write(m.get("solution_comparison", ""))
                    if m.get("evidence"):
                        st.markdown("**Evidence**")
                        for e in m["evidence"]:
                            st.write("• " + e)
                    st.caption(m.get("verification_status", ""))
        else:
            st.info("No accepted matches have been saved yet. Run matching above, or review the no-match list below if all questions have been processed.")

        run_notes = get_match_run_map()
        matched_ids = {x["neet_question_id"] for x in rows}
        no_match_qs = [q for q in neet if q["id"] not in matched_ids and q["id"] in run_notes]
        if no_match_qs:
            with st.expander(f"{len(no_match_qs)} NEET question(s) with no meaningful mock match"):
                st.dataframe(pd.DataFrame([{"NEET Q":q["question_number"],"Subject":q.get("subject"),"Reason":run_notes[q["id"]].get("no_match_reason"),"Candidates examined":run_notes[q["id"]].get("candidate_count")} for q in no_match_qs]), use_container_width=True, hide_index=True)

        st.divider()
        if st.button("Build Excel report", type="primary"):
            out = config.DATA_DIR / "NEET_2026_Mock_Question_Matching_Report.xlsx"
            try:
                export_workbook(out)
                st.success(f"Report created: {out.name}")
                st.download_button("Download Excel report", data=out.read_bytes(), file_name=out.name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            except Exception as exc:
                st.error(f"Could not generate report: {exc}")

elif page == "Question review":
    st.header("Question extraction & analysis review")
    kind = st.selectbox("Question bank", ["mock", "neet", "solution"])
    questions = get_questions(kind)
    if not questions:
        st.info("No questions found for this category yet.")
    else:
        rows = []
        for q in questions:
            a = q.get("analysis") or {}
            rows.append({
                "Paper": q.get("label"), "Test": q.get("test_number"), "Q no": q.get("question_number"),
                "Ordinal": q.get("question_ordinal"), "Subject": q.get("subject"), "PDF page": q.get("page_number"),
                "Extracted text length": len(q.get("question_text", "")), "Extraction confidence": q.get("extraction_confidence"),
                "Analysed": bool(a), "Chapter": a.get("chapter", ""), "Topic": a.get("topic", ""),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        choices = {f"{q.get('label')} · Q{q['question_number']} · page {q.get('page_number')}": q for q in questions}
        selected = st.selectbox("Open a question", list(choices.keys()))
        q = choices[selected]
        left, right = st.columns([1, 1])
        with left:
            st.markdown("**Extracted question**")
            st.text(q.get("question_text", ""))
            if q.get("page_image") and Path(q["page_image"]).exists():
                st.image(q["page_image"], caption=f"Original PDF page {q.get('page_number')}", use_container_width=True)
        with right:
            st.markdown("**AI analysis**")
            st.json(q.get("analysis") or {"status":"Not analysed yet"})
        st.divider()
        st.markdown("**Correct extraction (optional)**")
        st.caption("Use this if PDF extraction has merged columns, missed a symbol, or misread an option. Saving clears this question's AI analysis and all previous matching results so they can be recomputed.")
        edited_text = st.text_area("Question and options text", value=q.get("question_text", ""), height=220, key=f"edit_text_{q['id']}")
        edited_options = st.text_area("Options JSON", value=json.dumps(q.get("options", {}), ensure_ascii=False, indent=2), height=120, key=f"edit_options_{q['id']}")
        if st.button("Save corrected extraction", type="primary"):
            try:
                options_data = json.loads(edited_options or "{}")
                if not isinstance(options_data, dict):
                    raise ValueError("Options JSON must be an object, for example {\"A\": \"option text\"}.")
                if not edited_text.strip():
                    raise ValueError("Question text cannot be empty.")
                update_question_content(q["id"], edited_text, options_data)
                st.success("Corrected question saved. Re-run AI analysis and matching for updated results.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not save correction: {exc}")