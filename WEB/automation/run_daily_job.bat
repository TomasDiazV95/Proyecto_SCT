@echo off
setlocal

set "ROOT=%~dp0..\.."
set "AUTOMATION_DIR=%~dp0"

cd /d "%ROOT%"
python "%AUTOMATION_DIR%run_daily_job.py"

if errorlevel 1 (
  echo [ERROR] Proceso diario fallo.
  exit /b 1
)

echo Proceso diario finalizado.
exit /b 0
