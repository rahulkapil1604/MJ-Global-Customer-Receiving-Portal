@echo off
cd /d %~dp0
if not exist .venv (
  py -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist config.json copy config.example.json config.json >nul
start "" http://127.0.0.1:8787/create
python -m uvicorn app:app --host 0.0.0.0 --port 8787
pause
