# NEET Mock Intelligence

A local-first, multi-agent-style NEET paper analysis system. Upload 30 mock question PDFs and the actual NEET 2026 PDF in one screen; the application analyses the question bank, finds and explains cross-paper relationships, and generates a detailed PDF report.

**No paid API or API key is required.** Open-weight models are downloaded once and run locally through Ollama. The software and orchestration code live in GitHub; model weights are large files and are downloaded on demand instead of being committed to the repository.

## One-click user workflow

1. Run `run_windows.bat` or `run_mac_linux.sh` once. The launcher installs Python dependencies, installs/starts Ollama where supported, detects the machine's resources and downloads the recommended local models.
2. Open the app at `http://localhost:8501`.
3. Open **ONE-CLICK: Full analysis**.
4. Upload the 30 mock test PDFs, optional mock solution/answer-key PDFs, and the NEET 2026 PDF.
5. Click **START COMPLETE ANALYSIS — generate final PDF**.
6. Download the detailed NEET comparison PDF, full mock-question catalogue PDF and audit workbook.

## AI team / division of labour

The workflow is coordinated by a manager and specialist passes, rather than one huge prompt that tries to do everything at once.

| Agent / specialist | Responsibility | Implementation |
|---|---|---|
| AI Operations Manager | Stage plan, completeness checks, preflight and final release review | Local Qwen manager prompts + deterministic workflow gates |
| PDF & Layout Specialist | Page extraction, question segmentation, page references, previews and OCR warnings | PyMuPDF + optional Tesseract OCR |
| NEET Subject Analyst | Subject, NCERT chapter/topic, precise concept, question type, formulas/reactions, difficulty and solutions | Local multimodal Qwen |
| Independent Solution Auditor | Independently checks proposed concepts, formulas, answers and solution steps; records corrections/issues | DeepSeek-R1 when the computer supports a second model |
| Semantic Retrieval Specialist | Searches all mock questions with dense embeddings and lexical features | BGE-M3 + TF-IDF word/character retrieval |
| Cross-Encoder Reranker | Re-scores the leading candidate shortlist for each NEET question | BGE-reranker-v2-m3 on the high-accuracy tier |
| Relationship Examiner | Compares NEET question with each candidate and explains relationship/evidence | Local multimodal Qwen |
| Independent Match Verifier | Challenges accepted matches, corrects overly strong labels and rejects chapter-only overlap | DeepSeek-R1 when available |
| Report QA Editor | Reports extracted/analysed/matched counts, no-match and unprocessed statuses; builds output files | Python + ReportLab + openpyxl |

On smaller computers the setup script reduces model sizes and may omit the independent verifier or cross-encoder. The app clearly displays which team roles are using a separate model and which are operating as a same-model review.

## Local model selection

The setup script checks system RAM, NVIDIA VRAM when available and free disk space. Its current automatic tiers are:

| Tier | Primary | Independent verifier | Retrieval |
|---|---|---|---|
| High accuracy | `qwen3.8:27b` (multimodal) | `deepseek-r1:14b` | `BAAI/bge-m3` + `BAAI/bge-reranker-v2-m3` |
| Balanced | `qwen3.5:9b` (multimodal) | `deepseek-r1:8b` | `BAAI/bge-m3` |
| Lightweight | `qwen3.5:4b` or `qwen3.5:2b` (multimodal) | No separate verifier | `BAAI/bge-small-en-v1.5` |

Ollama currently lists Qwen3.8 27B as a multimodal 18 GB model with a 256K context window; Qwen3.5 9B is listed as a 6.6 GB text-and-image model. These are approximate model package sizes, not total runtime memory requirements. See the [Qwen3.8 Ollama model](https://ollama.com/library/qwen3.8), [Qwen3.5 Ollama model](https://ollama.com/library/qwen3.5), [DeepSeek-R1 Ollama model](https://ollama.com/library/deepseek-r1), and [Ollama model library](https://ollama.com/library).

Hardware selection is an estimate. Quantisation, context length, CPU/GPU offload, operating system and concurrent apps affect real performance. A high-accuracy tier needs a capable PC and substantial free disk. If it cannot fit, the script chooses a smaller tier rather than pretending the flagship model will run smoothly.

## What the final files contain

### `NEET_2026_Mock_Comparison_Detailed_Report.pdf`

For each NEET question: original question and options; subject/chapter/topic/concept; AI answer and solution outline; all accepted mock matches; test number, printed mock question number and mock PDF page; relationship category; confidence and verification status; why they match; differences; solution-method comparison; evidence; and an explicit no-match/unprocessed status where applicable. The report also contains match counts and paper extraction quality notes.

### `All_Mock_Questions_Analysis_Catalogue.pdf`

A question-by-question catalogue of every successfully extracted mock question, including its test, question number, page, question text, options, topic/concept, formulas/reactions, solution and independent review status.

### `NEET_2026_Mock_Comparison_Audit_Workbook.xlsx`

Structured sheets for NEET summary, every accepted match, all mock-question analyses, unmatched NEET questions, relationship counts and PDF extraction QA.

All three files are also saved in the local `data/` folder.

## Seven relationship categories

1. **Exactly same** — essentially the same question and required reasoning; harmless formatting or option-order differences are allowed.
2. **Substantially same — data/details changed** — same question structure and solution path, with changed values, names or minor details.
3. **Same question pattern / solution method** — same problem template/reasoning method, but a different requested quantity or meaningful structural variation.
4. **Conceptually same — different application** — same underlying concept applied in a different setting or application.
5. **Same NCERT source / knowledge** — same specific NCERT statement, fact, reaction, example, figure, table or passage, even if the question asked differs.
6. **Same diagram / graph / experiment / data representation** — same distinctive diagram, graph, apparatus, experiment or data representation is reused/adapted.
7. **Same multi-concept combination / reasoning chain** — substantially the same sequence/combination of concepts and a similar reasoning chain.

Chapter-only overlap is not a match. Multiple mock matches may be returned for one NEET question. No meaningful match is a valid result.

## Technical architecture

- **UI:** Streamlit, with a one-click all-in-one analysis page and question-review tools.
- **PDF extraction:** PyMuPDF, page rendering, question segmentation, optional Tesseract OCR.
- **Storage:** SQLite, resumable question-analysis and matching checkpoints.
- **Model runtime:** local Ollama OpenAI-compatible endpoint at `http://127.0.0.1:11434/v1`.
- **Dense retrieval:** BGE-M3 / BGE-small sentence embeddings, cached locally.
- **Lexical retrieval:** word and character TF-IDF, exact-string/fuzzy comparison.
- **Candidate reranking:** BGE cross-encoder when enabled by the hardware plan.
- **Relationship classification:** structured LLM output with strict candidate-ID validation and evidence requirements.
- **Reporting:** ReportLab PDF and openpyxl workbook.

## Requirements and setup

- Python 3.11+.
- Internet connection for initial installation and one-time model downloads.
- Adequate local RAM/GPU and free disk space for the selected model tier.
- Windows: run `run_windows.bat`.
- macOS/Linux: run `chmod +x run_mac_linux.sh && ./run_mac_linux.sh`.

Ollama is installed automatically where supported (Windows Package Manager, Homebrew, Linux installer). If auto-install is unavailable, install it from https://ollama.com/download and run the launcher again. The script downloads selected model weights from the Ollama registry; BGE embeddings and reranker weights are downloaded to the Hugging Face cache when the matching stage first runs.

## PDF naming and numbering

Name mock PDFs with test numbers such as `Allen_Test_01.pdf` … `Allen_Test_30.pdf`. Optional solution PDFs should carry the corresponding test number. The parser preserves the printed question number and its ordinal position. It initially infers NEET subject from ordinal position (1–45 Physics, 46–90 Chemistry, 91–180 Biology); review this if your PDF uses another order or numbering convention.

## Accuracy, QA and limitations

This is a careful local analysis workflow, **not a guarantee of perfect output or an official answer-key generator**.

- PDF extraction can miss symbols or confuse two-column layouts, OCR, equations, chemical structures, diagrams and restarted question numbers. Review extraction warnings and source-page images.
- AI-generated answers are not official. A separately configured local verifier is a second model's independent opinion, not a mathematical proof.
- The semantic/lexical retriever ranks a candidate shortlist (default 60). The LLM judges those candidates in detail. A related mock question outside that shortlist can be missed.
- “No meaningful match” means no qualifying match was accepted from the retrieved shortlist; it does not prove that no related question exists in the full bank.
- Confidence is a model-reported indicator, not a calibrated probability. Manually review low-confidence matches and any answer used in official educational material.
- The app refuses to silently mark missing or failed questions as completed. A partially processed question is labelled as such in the reports.

## Privacy and GitHub

Question PDFs, `.env`, downloaded models, local database, page previews and generated reports are not uploaded to GitHub by the app. They remain on your computer. The `.gitignore` excludes user PDFs, local `.env`, and `data/` files. Model weights are large; the repository includes setup code and model identifiers, and downloads weights from their public model registries at first launch. The local Ollama service receives prompts only from this computer.

## Troubleshooting

- **Ollama missing:** install from https://ollama.com/download and rerun the launcher.
- **Model download fails:** check internet, free disk and firewall, then press **Set up / repair local AI models** again.
- **Scanned PDF yields few questions:** install Tesseract OCR and retry; inspect the extraction warnings and source pages.
- **Question count is not 180:** the system does not invent missing questions. Check the source PDF parser QA before continuing.
- **Out of memory:** close other applications, restart Ollama, use the smaller tier or increase available RAM/VRAM.
- **Matching is slow:** local model reasoning and BGE reranking can take time; the local database checkpoints finished questions so the run can resume.

## Development

```bash
pip install -r requirements.txt
pip install -r requirements-ai.txt
pip install -r requirements-dev.txt
python -m pytest -q
streamlit run app.py
```