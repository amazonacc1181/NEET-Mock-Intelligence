# NEET Mock Intelligence

A local-first question bank and cross-paper matching system for NEET preparation.

**Workflow:** put your mock PDFs in `input/mock_papers/`, import and analyse them, upload the actual NEET 2026 PDF, run matching, and export an Excel report.

Designed for 30 mock papers × 180 questions = 5,400 questions, compared with 180 NEET questions.

## Features

- PDF extraction using PyMuPDF, with optional Tesseract OCR for scanned pages.
- Question segmentation with test number, printed question number, PDF page and source-page preview.
- Local SQLite question bank and resumable analysis checkpoints.
- AI extraction of subject, NCERT chapter/topic, subtopic, concepts, question type, formulas/laws, reactions, NCERT source, answer, solution steps and common traps.
- Hybrid retrieval using optional BGE embeddings plus lexical similarity.
- Detailed relationship classification and explanations; optional independent second-model audit and vision-model support for diagrams.
- Excel report with NEET question summary, all matches, full mock analysis, unmatched questions, relationship counts and extraction QA.

## Relationship categories

1. **Exactly same**
2. **Substantially same — data/details changed**
3. **Same question pattern / solution method**
4. **Conceptually same — different application**
5. **Same NCERT source / knowledge**
6. **Same diagram / graph / experiment / data representation**
7. **Same multi-concept combination / reasoning chain**

Chapter-only overlap is not a match. Multiple matches per NEET question are supported. No meaningful match is a valid result.

## Quick start (Windows)

1. Install Python 3.11 (enable **Add Python to PATH**).
2. Clone/download this repository.
3. Put the 30 mock question PDFs in `input/mock_papers/` (e.g. `Allen_Test_01.pdf` … `Allen_Test_30.pdf`).
4. Optional: put solution PDFs in `input/mock_solutions/`, using corresponding test numbers.
5. Double-click `run_windows.bat`.
6. Copy `.env.example` to `.env` and configure an OpenAI-compatible provider:
   - `LLM_BASE_URL`
   - `LLM_API_KEY`
   - `LLM_MODEL`
7. Install optional semantic search: `pip install -r requirements-ai.txt`.
8. Open the local app at `http://localhost:8501`.
9. Import PDFs, analyse/resume the mock bank, upload NEET 2026, run matching and export the workbook.

## macOS / Linux

Run:

```bash
chmod +x run_mac_linux.sh
./run_mac_linux.sh
```

Then configure `.env` and follow the same app workflow.

## Model providers

The software accepts OpenAI-compatible chat-completions endpoints. It can connect to OpenRouter, Groq, Ollama or LM Studio. Example:

```dotenv
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=your_api_key
LLM_MODEL=exact-model-id-from-provider
```

For optional independent verification, set `VERIFY_BASE_URL`, `VERIFY_API_KEY`, and `VERIFY_MODEL` to a different model/provider. For image-heavy questions, configure a vision-capable endpoint with `VISION_BASE_URL`, `VISION_API_KEY`, and `VISION_MODEL`.

Free model quotas and availability change; there is no promise of unlimited free processing. The pipeline checkpoints progress so you can resume after rate limits. Local Ollama/LM Studio models are also supported, subject to your hardware.

## OCR and accuracy

Install Tesseract separately for scanned PDFs. On Ubuntu/Debian: `sudo apt-get install tesseract-ocr`; on macOS: `brew install tesseract`. Windows users should install Tesseract and add it to PATH.

Review extraction QA before analysis. The app does not claim that 180 questions were processed if fewer were found. AI-generated answers are marked unverified unless supplied/checked against trusted solutions. The retriever ranks candidate matches (30 by default, configurable up to 60); the LLM judges those candidates. A missed retrieval can therefore cause a missed match. Confidence is not a calibrated probability. Inspect low-confidence matches, diagrams, OCR and question numbering manually.

## Privacy

PDFs, database, page previews and reports remain local by default. When cloud models are configured, extracted question text (and images sent to a vision model) go to that provider. Review its privacy terms. **Never commit question PDFs, `.env`, API keys or generated `data/` files.** They are excluded by `.gitignore`.

## Development

```bash
pip install -r requirements.txt
pip install -r requirements-ai.txt
pip install -r requirements-dev.txt
pytest -q
streamlit run app.py
```
