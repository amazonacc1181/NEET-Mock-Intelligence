# Start here — NEET Mock Intelligence

## 1. Put your PDFs in the folder

Copy the 30 mock question PDFs into:

`input/mock_papers/`

Use names that include each test number, for example:

- `Allen_Test_01.pdf`
- `Allen_Test_02.pdf`
- …
- `Allen_Test_30.pdf`

If you have separate answer/solution PDFs, place them in `input/mock_solutions/` and keep the same test numbers in their filenames. The real NEET 2026 PDF is uploaded later inside the app.

## 2. Start the app on Windows

1. Install Python 3.11 (tick **Add Python to PATH** during installation).
2. Double-click `run_windows.bat`.
3. On first launch, Notepad opens `.env`. Add your model provider's API key and exact model ID, then save and close Notepad.
4. The app opens in your browser at `http://localhost:8501`.

For macOS/Linux, run `chmod +x run_mac_linux.sh` and then `./run_mac_linux.sh`. Edit `.env` before analysing questions.

## 3. Connect an AI model

The app does not contain an API key. In `.env`, configure:

- `LLM_BASE_URL` — your provider's OpenAI-compatible API base URL
- `LLM_API_KEY` — your own API key (or the local-server placeholder shown in `.env.example`)
- `LLM_MODEL` — exact model identifier from that provider

You can use a hosted API or a local OpenAI-compatible server such as Ollama/LM Studio. Free API plans have usage limits; the full 5,400-question analysis may need to be resumed over multiple quota windows. See `README.md` for verifier, vision model and provider examples.

For stronger local semantic question retrieval, install the optional BGE embedding model after the app's first launch. On Windows, in a new terminal from this project folder, run `.venv\Scripts\python -m pip install -r requirements-ai.txt`. The first embedding-model run downloads the model; lexical search remains available without it.

## 4. Run the four workflow steps

1. **Mock PDFs:** open the tab and click **Read / import mock PDFs from folder**.
2. **Analyse mock bank:** click **Analyse / resume all unanalysed mock questions**. It checkpoints completed questions.
3. **NEET 2026 paper:** upload the actual NEET PDF, parse it, then analyse it.
4. **Match & report:** run matching and download the Excel report.

## 5. Review extraction before trusting results

Open **Question review** and inspect the PDF extraction QA. Correct any merged/missing symbols, options or diagrams before running the analysis/matching stages. Scanned PDFs may need Tesseract OCR installed. For best visual matching of diagrams/graphs, configure a vision-capable model in `.env`.

## Important

- Do not put your question PDFs, `.env`, API keys or `data/` files in a public GitHub repository. They are excluded by `.gitignore`.
- The seven relationship categories are described in `README.md`.
- A no-match result means no qualifying match was found in the retrieved candidate shortlist; it is not proof that no related mock question exists.
- AI answers and confidence scores are not official or guaranteed. Verify low-confidence matches and solutions against trusted sources.