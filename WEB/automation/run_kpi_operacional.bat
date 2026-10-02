@echo off
setlocal

rem Carga diaria del KPI Operacional (dbo.sp_kpi_operacional_cargar): mes actual y 3 anteriores.
set "ROOT=%~dp0..\.."
set "LOG=%ROOT%\Logs\etl_kpi_operacional.log"

cd /d "%ROOT%"
if not exist "%ROOT%\Logs" mkdir "%ROOT%\Logs"

set "PYTHON=python"
if exist "%ROOT%\.venv\Scripts\python.exe" set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
set "PYTHONIOENCODING=utf-8"

echo ===== %date% %time% Inicio carga KPI Operacional >> "%LOG%"
"%PYTHON%" "%ROOT%\ETL\etl_kpi_operacional.py" >> "%LOG%" 2>&1

if errorlevel 1 (
  echo ===== %date% %time% [ERROR] La carga fallo >> "%LOG%"
  echo [ERROR] Carga KPI Operacional fallo. Revisar %LOG%
  exit /b 1
)

echo ===== %date% %time% Carga finalizada >> "%LOG%"
echo Carga KPI Operacional finalizada.
exit /b 0
