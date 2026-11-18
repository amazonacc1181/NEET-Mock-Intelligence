# Start here — NEET Mock Intelligence

You do **not** need to buy an API, create a model-provider account, paste an API key or manually choose an AI model.

## One-time setup

1. Install Python 3.11 or newer.
2. On Windows, double-click `run_windows.bat`. On macOS/Linux, run `./run_mac_linux.sh` from a terminal.
3. The launcher installs the Python requirements, installs Ollama where supported, detects available RAM/disk/GPU, downloads the best local model tier that fits, configures the local endpoint and opens the app at `http://localhost:8501`.
4. The first run needs an internet connection and several GB to tens of GB of free disk space because model weights are downloaded once. They are not hosted in this GitHub repository.

If automatic Ollama installation fails, install it from https://ollama.com/download and run the launcher again. The app's **ONE-CLICK** page also has a local AI repair/setup control.

## Your only analysis workflow

Open the **ONE-CLICK: Full analysis** page:

1. Upload the 30 mock question-paper PDFs together.
2. Optionally upload answer keys / detailed mock solutions.
3. Upload the actual NEET 2026 question-paper PDF.
4. Click **START COMPLETE ANALYSIS — generate final PDF**.

The local AI team then imports the papers, analyses the extracted mock questions, analyses the NEET paper, retrieves candidate matches, classifies and independently verifies matches where a second model is available, and creates the reports. Completed analyses are checkpointed, so you can resume after an interruption by pressing the same button again.

## Files you receive

- `NEET_2026_Mock_Comparison_Detailed_Report.pdf` — the detailed report for every NEET question, with matched mock test/question numbers, relationship category, concepts, differences, solution comparison, evidence, confidence and unmatched/unprocessed status.
- `All_Mock_Questions_Analysis_Catalogue.pdf` — a question-by-question analysis catalogue for the entire mock bank.
- `NEET_2026_Mock_Comparison_Audit_Workbook.xlsx` — searchable tables containing the full mock analysis, NEET summary, every accepted match and extraction QA.

The files are downloadable from the app when the run finishes and are also saved locally under `data/`.

## What the local model setup chooses

The setup script checks available system RAM, NVIDIA VRAM when detectable, and free disk space. It selects one of these tiers:

- **High accuracy:** Qwen3.8 27B multimodal primary model + DeepSeek-R1 14B independent verifier + BGE-M3 embedding model + BGE reranker (requires a powerful computer and substantial storage).
- **Balanced:** Qwen3.5 9B multimodal primary model + DeepSeek-R1 8B verifier + BGE-M3 semantic retrieval.
- **Lightweight:** Qwen3.5 4B or 2B multimodal model and a smaller embedding model; no separate verifier. Analysis quality will be lower on this tier.

Model weights are downloaded locally from the public Ollama registry and Hugging Face model registry. No per-token API payment is used. Model licensing is governed by the model authors' licences; review those before commercial reuse.

## Important quality notes

- This is a local research assistant, not an official NEET answer key. AI-generated solutions are labelled and should be checked against trusted solutions.
- PDF extraction QA is essential. Review warnings for scanned pages, two-column layouts, formulae, chemical structures, diagrams and missing question numbers.
- The retriever ranks a candidate shortlist from the full bank, then the language model compares those candidates. A retrieval miss can still hide a true relationship.
- “No meaningful match” means no qualifying match was accepted from the candidates retrieved; it is not proof that no similar mock question exists.
- Model confidence is not a calibrated probability. Review low-confidence results and any result used for official teaching or assessment.
- The app does not upload your files to GitHub. PDFs, model caches, local database and reports stay on your computer. The local Ollama service receives prompts only from your own computer.

See `README.md` for technical details, limitations and troubleshooting.