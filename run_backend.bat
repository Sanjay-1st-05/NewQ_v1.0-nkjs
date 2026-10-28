@echo off
REM NewQ backend for mobile app use.
REM --host 0.0.0.0 makes the API reachable from your phone over Wi-Fi
REM (the default 127.0.0.1 bind only accepts local connections).
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt >nul
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
