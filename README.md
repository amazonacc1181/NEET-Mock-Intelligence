# NEET Mock Intelligence

**Cloud-first NEET question analysis — no personal computer, no API key, and no paid AI subscription required.**

## Open the cloud notebook

[![Open in Google Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/amazonacc1181/NEET-Mock-Intelligence/blob/main/NEET_Mock_Intelligence_Colab.ipynb)

The Colab notebook contains a self-contained copy of the application code. Open it, choose **File → Save a copy in Drive**, connect to a GPU runtime when one is available, and upload your mock PDFs and NEET 2026 PDF. The models run inside the temporary Colab runtime; the database, uploaded PDFs, checkpoints, page previews and reports are saved to your Google Drive. No model API keys are required.

The notebook performs PDF extraction, question analysis, solution auditing, semantic/lexical candidate retrieval, relationship adjudication, match verification and PDF/Excel report generation. It is designed for 30 mock papers × 180 questions = 5,400 questions, plus 180 NEET questions.

## What you receive

- **NEET 2026 detailed comparison PDF:** every NEET question, accepted mock matches, test number and question number, relationship type, shared concept, differences, solution comparison, evidence and unmatched-question reasons.
- **Complete mock question catalogue PDF:** extracted question text, chapter/topic, concept analysis, answer/solution notes, formulas/reactions and source page.
- **Audit workbook:** searchable question catalogue, match pairs, verification, extraction QA and relationship counts.

## Seven relationship categories

1. Exactly same.
2. Substantially same — data/details changed.
3. Same question pattern / solution method.
4. Conceptually same — different application.
5. Same NCERT source / knowledge.
6. Same diagram / graph / experiment / data representation.
7. Same multi-concept combination / reasoning chain.

Chapter-only overlap is not a match. Multiple mock questions can match one NEET question. No meaningful match is a valid result.

## Free cloud runtime — important limitations

The notebook uses Google Colab's free hosted CPU/GPU resources and runs open-weight models locally in that runtime. Google says free GPU availability and resource limits are dynamic and not guaranteed; free sessions can run for at most 12 hours, depending on availability and usage. The notebook checkpoints the database to Google Drive after each paper, analysis batch and NEET match so an interrupted run can be resumed. Model weights may need to be downloaded again after a fresh runtime.

A continuous, always-on upload website with guaranteed GPU compute and permanent storage cannot be promised at $0. The Colab notebook is the free option: it runs online, but you must open the notebook and start/resume the job yourself. Do not use a Colab notebook as a hidden web server; this project uses the normal notebook interface and upload controls.

A Google account and enough Google Drive storage are required. For best performance, select **Runtime → Change runtime type → T4 GPU** when available. If no GPU is available, the notebook falls back to smaller CPU models, which will be substantially slower and may take multiple sessions.

## Privacy

The AI models run locally inside your Colab runtime; the app does not send the question text to a third-party model API. Your PDFs, SQLite checkpoint, page previews, cache and reports are saved to the Google Drive folder `MyDrive/NEET-Mock-Intelligence`. Google Colab and Google Drive are still cloud services, so your files are processed/stored on Google's infrastructure. Keep the GitHub repository private if it contains any material you do not want public. Never upload API keys (none are required by the Colab notebook).

## Local computer option (optional)

The Streamlit app can also run locally on Windows, macOS or Linux using `run_windows.bat` or `run_mac_linux.sh`, with Ollama-hosted open-weight models. See [START_HERE.md](START_HERE.md).

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```