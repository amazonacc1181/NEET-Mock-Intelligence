@echo off
setlocal
cd /d "%~dp0"
if not exist .venv (
  py -3.11 -m venv .venv
  if errorlevel 1 py -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-ai.txt
if errorlevel 1 (
  echo.
  echo Failed to install local AI retrieval dependencies. Check your internet connection and retry.
  pause
  exit /b 1
)
echo.
echo Preparing free local AI models. No API key or paid API is needed.
python setup_local_ai.py
if errorlevel 1 (
  echo.
  echo Local AI setup did not complete. Install Ollama from https://ollama.com/download and run this file again.
  pause
  exit /b 1
)
echo.
echo Starting NEET Mock Intelligence at http://localhost:8501
echo Upload the 30 mock PDFs and NEET 2026 PDF in the ONE-CLICK page.
streamlit run app.py
pause