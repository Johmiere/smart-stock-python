@echo off
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate.bat
if not exist .env (
  copy .env.example .env
  echo Created backend\.env. Edit it if your MySQL settings differ.
)
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
