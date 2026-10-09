@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "ROOT=%~dp0"
for %%I in ("%ROOT%..") do set "PROJECT_ROOT=%%~fI"
set "BACKEND_DIR=%ROOT%backend"
set "FRONTEND_DIR=%ROOT%frontend"
set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "BUILD_ONLY=0"
rem Por defecto: recarga automatica al guardar (uvicorn --reload y Vite dev), sin compilar.
rem --prod: compila React y sirve la version compilada, sin recarga.
set "DEV_MODE=1"
set "IN_FRONTEND=0"
set "ARG_OK=0"
if "%~1"=="" set "ARG_OK=1"
if /i "%~1"=="--dev" set "ARG_OK=1"
if /i "%~1"=="--prod" (
  set "DEV_MODE=0"
  set "ARG_OK=1"
)
if /i "%~1"=="--build-only" (
  set "BUILD_ONLY=1"
  set "DEV_MODE=0"
  set "ARG_OK=1"
)
if "%ARG_OK%"=="0" (
  echo Uso: start_web.bat [--prod ^| --build-only]
  exit /b 1
)

if not exist "%BACKEND_DIR%\main.py" (
  echo [ERROR] No se encontro el backend en "%BACKEND_DIR%".
  goto :error
)
if not exist "%FRONTEND_DIR%\package.json" (
  echo [ERROR] No se encontro el frontend en "%FRONTEND_DIR%".
  goto :error
)

echo Preparando el entorno virtual del proyecto...
if exist "%PYTHON_EXE%" goto :activate_venv
rem Preferir versiones compatibles con las dependencias fijadas del backend.
for %%V in (3.14 3.13 3.12 3.11 3.10) do (
  py -%%V -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    py -%%V -m venv "%PROJECT_ROOT%\.venv"
    if errorlevel 1 goto :error
    goto :activate_venv
  )
)
python -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] < (3,15) else 1)" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Se necesita Python 3.10 a 3.14 para las dependencias actuales.
  echo Instala Python 3.14 con el lanzador py y vuelve a ejecutar este archivo.
  goto :error
)
python -m venv "%PROJECT_ROOT%\.venv"
if errorlevel 1 goto :error

:activate_venv
if not exist "%PROJECT_ROOT%\.venv\Scripts\activate.bat" (
  echo [ERROR] Falta activate.bat en .venv. Revisa el entorno virtual.
  goto :error
)
call "%PROJECT_ROOT%\.venv\Scripts\activate.bat"
if errorlevel 1 goto :error
rem Usar siempre el Python del proyecto, aunque se haya movido la carpeta.
set "VIRTUAL_ENV=%PROJECT_ROOT%\.venv"
set "PATH=%VIRTUAL_ENV%\Scripts;%PATH%"
"%PYTHON_EXE%" -c "import sys; sys.exit(0 if sys.prefix != sys.base_prefix else 1)"
if errorlevel 1 (
  echo [ERROR] El Python de .venv no es un entorno virtual valido.
  goto :error
)
echo [OK] Entorno activo: "%VIRTUAL_ENV%".

rem Buscar Node tambien en las ubicaciones habituales de Windows.
where node.exe >nul 2>&1
if errorlevel 1 (
  if exist "%ProgramFiles%\nodejs\node.exe" set "PATH=%ProgramFiles%\nodejs;%PATH%"
)
where node.exe >nul 2>&1
if errorlevel 1 (
  if exist "%LOCALAPPDATA%\Programs\nodejs\node.exe" set "PATH=%LOCALAPPDATA%\Programs\nodejs;%PATH%"
)
where node.exe >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Instala Node.js y vuelve a ejecutar este archivo.
  goto :error
)
where npm.cmd >nul 2>&1
if errorlevel 1 (
  echo [ERROR] No se encontro npm.cmd. Revisa la instalacion de Node.js.
  goto :error
)
node -e "const [a,b]=process.versions.node.split('.').map(Number);process.exit((a===20&&b>=19)||(a>=22&&(a!==22||b>=12))?0:1)"
if errorlevel 1 (
  echo [ERROR] Vite requiere Node 20.19+ o 22.12+ compatible.
  goto :error
)

pushd "%FRONTEND_DIR%"
if errorlevel 1 goto :error
set "IN_FRONTEND=1"
echo [1/3] Instalando dependencias del frontend...
if exist "package-lock.json" (
  call npm.cmd ci --include=dev --no-audit --no-fund
) else (
  call npm.cmd install --include=dev --no-audit --no-fund
)
if errorlevel 1 goto :error

if "%DEV_MODE%"=="1" goto :skip_build
echo [2/3] Compilando React...
call npm.cmd run build
if errorlevel 1 goto :error
echo [OK] Compilacion generada en "%FRONTEND_DIR%\dist".
:skip_build
popd
set "IN_FRONTEND=0"
if "%BUILD_ONLY%"=="1" exit /b 0

echo [3/3] Preparando backend...
"%PYTHON_EXE%" -m pip install -r "%BACKEND_DIR%\requirements.txt"
if errorlevel 1 goto :error

if "%DEV_MODE%"=="1" goto :start_dev
echo Iniciando backend FastAPI...
start "Backend FastAPI" /D "%BACKEND_DIR%" cmd /d /k ""%PYTHON_EXE%" -m uvicorn main:app --host 0.0.0.0 --port 8000"
echo Iniciando vista previa de la compilacion...
start "Frontend React compilado" /D "%FRONTEND_DIR%" cmd /d /k "npm.cmd run preview -- --host 0.0.0.0 --port 5173 --strictPort"
goto :started

:start_dev
echo Iniciando backend FastAPI con recarga automatica...
start "Backend FastAPI dev" /D "%BACKEND_DIR%" cmd /d /k ""%PYTHON_EXE%" -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"
echo Iniciando frontend React con recarga automatica...
start "Frontend React dev" /D "%FRONTEND_DIR%" cmd /d /k "npm.cmd run dev -- --host 0.0.0.0 --port 5173 --strictPort"

:started
echo.
echo Frontend local: http://localhost:5173
echo Backend local:  http://localhost:8000
echo En la misma red: http://IP_DE_ESTE_PC:5173
echo Conserva abiertas las dos ventanas de los servidores.
echo Si hay un error de conexion SQL, revisa el archivo .env y el driver ODBC.
echo.
pause
exit /b 0

:error
if "%IN_FRONTEND%"=="1" popd
echo.
echo [ERROR] No se pudo completar el inicio. Revisa el mensaje anterior.
if "%BUILD_ONLY%"=="0" pause
exit /b 1
