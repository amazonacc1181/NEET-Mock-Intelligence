# Start here — no PC required

## 1. Open the cloud notebook

[**Open NEET Mock Intelligence in Google Colab**](https://colab.research.google.com/github/amazonacc1181/NEET-Mock-Intelligence/blob/main/NEET_Mock_Intelligence_Colab.ipynb)

In Colab, choose **File → Save a copy in Drive** so you keep your own working notebook. The notebook embeds the project source and does not need to clone this GitHub repository when it runs. You can therefore make the GitHub repository private after saving your notebook copy.

## 2. Select free cloud hardware

In Colab choose **Runtime → Change runtime type → T4 GPU** when it is available. Free GPU access is not guaranteed. The notebook can fall back to smaller CPU models, but that will be much slower.

## 3. Run the notebook cells

The notebook will:

- Ask you to connect your Google Drive once.
- Install the PDF tools and local Ollama model runner in the Colab runtime.
- Download the selected open-weight models (no API key or paid model service).
- Ask you to upload all 30 mock PDFs together, then the NEET 2026 PDF. Optional solution PDFs can be included with filenames containing `solution`, `answer` or `key`.
- Analyse each extracted question and create the final report bundle.

Name your mock papers clearly, for example `Allen_Test_01.pdf` through `Allen_Test_30.pdf`. Name the real paper `NEET_2026.pdf` when uploading it.

## 4. Where the result is saved

The persistent folder is `Google Drive/MyDrive/NEET-Mock-Intelligence/`. It holds your uploaded PDFs, database checkpoint, page previews, embedding cache and final reports. At the end, the notebook offers the report bundle for download.

## 5. Resume after a runtime reset

Colab's free runtime is temporary and its GPU quota/availability changes. The notebook backs up its database to Drive after each paper, analysis batch and NEET match. Reopen your saved notebook, run the setup/model cell, then rerun the analysis cell. Completed work is skipped and the remaining work resumes. The model weights may need to download again in a new runtime.

## Accuracy and limitations

The process is designed to avoid silent omissions: it checks expected paper/question counts and does not release the final PDF if analysis or matching is incomplete. OCR, diagrams and model reasoning can still be wrong; inspect extraction QA and low-confidence relationships. AI-derived solutions are labelled unverified unless supported by supplied solution material. Confidence scores are model judgements, not calibrated probabilities.

## Optional local installation

For Windows, run `run_windows.bat`. For macOS/Linux, run `run_mac_linux.sh`. This requires a computer and local model storage; the Colab notebook is the recommended route when you do not have a PC.