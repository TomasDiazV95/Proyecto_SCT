@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "BACKEND_DIR=%SCRIPT_DIR%.."

echo Invalidando sesiones de todos los usuarios...
python "%SCRIPT_DIR%logout_all_users.py"

if errorlevel 1 (
  echo [ERROR] No se pudieron invalidar las sesiones.
  exit /b 1
)

echo Sesiones invalidadas correctamente.
exit /b 0
