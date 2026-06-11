@echo off
setlocal

set "ROOT=%~dp0"
for %%I in ("%ROOT%..") do set "PROJECT_ROOT=%%~fI"
set "BACKEND_DIR=%ROOT%backend"
set "FRONTEND_DIR=%ROOT%frontend"
set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"

if not exist "%BACKEND_DIR%\main.py" (
  echo [ERROR] No se encontro el backend en "%BACKEND_DIR%".
  pause
  exit /b 1
)

if not exist "%FRONTEND_DIR%\package.json" (
  echo [ERROR] No se encontro el frontend en "%FRONTEND_DIR%".
  pause
  exit /b 1
)

if not exist "%PYTHON_EXE%" (
  echo [WARN] No se encontro la venv del proyecto en "%PYTHON_EXE%".
  echo [WARN] Se usara el python disponible en PATH.
  set "PYTHON_EXE=python"
)

echo Iniciando backend FastAPI en una nueva ventana...
start "Backend FastAPI" cmd /k "cd /d "%BACKEND_DIR%" && "%PYTHON_EXE%" -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"

echo Iniciando frontend React (Vite) en una nueva ventana...
start "Frontend React" cmd /k "cd /d "%FRONTEND_DIR%" && npm run dev -- --host 0.0.0.0 --port 5173"

set "LOCAL_IP="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 ^| Where-Object { $_.IPAddress -like '192.168.*' -or $_.IPAddress -like '10.*' -or $_.IPAddress -like '172.16.*' -or $_.IPAddress -like '172.17.*' -or $_.IPAddress -like '172.18.*' -or $_.IPAddress -like '172.19.*' -or $_.IPAddress -like '172.2?.*' -or $_.IPAddress -like '172.30.*' -or $_.IPAddress -like '172.31.*' } ^| Select-Object -First 1 -ExpandProperty IPAddress)"`) do set "LOCAL_IP=%%i"

echo.
echo Listo. Si es la primera vez, asegúrate de haber ejecutado antes:
echo   1) pip install -r WEB\backend\requirements.txt
echo   2) npm install (en WEB\frontend)
echo.
echo Frontend local: http://localhost:5173
echo Backend local:  http://localhost:8000
if defined LOCAL_IP (
  echo Frontend red:   http://%LOCAL_IP%:5173
  echo Backend red:    http://%LOCAL_IP%:8000
) else (
  echo No se pudo detectar IP local automaticamente.
)
echo.
pause
