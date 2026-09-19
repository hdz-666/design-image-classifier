@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Installing requirements...
pip install -r requirements.txt --quiet

if not exist ".env" (
    echo No .env file found. Copy .env.example to .env and fill in API_KEY first.
    exit /b 1
)

echo Starting Design Matcher API on http://localhost:8000 ...
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

endlocal
