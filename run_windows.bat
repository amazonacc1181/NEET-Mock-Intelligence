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
if exist .env (echo Using existing .env file.) else (copy .env.example .env >nul & echo Created .env. Add your model provider details in Notepad, then close Notepad to continue. & notepad .env)
echo.
echo Starting NEET Mock Intelligence at http://localhost:8501
streamlit run app.py