@echo off
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -m omphalos --workspace .\workspace serve --open
  exit /b
)
where poetry >nul 2>&1
if not errorlevel 1 (
  poetry run python -m omphalos --workspace .\workspace serve --open
  exit /b
)
echo Install omphalOS first with: poetry install
pause
exit /b 1
