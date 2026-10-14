@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Install omphalOS first with: poetry install
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m omphalos --workspace .\workspace serve --open
