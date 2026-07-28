@echo off
setlocal

set "TASK_NAME=Intranet_Logout_All_23H"
set "SCRIPT_PATH=%~dp0logout_all_users.bat"

echo Creando/actualizando tarea programada "%TASK_NAME%"...
schtasks /create /f /tn "%TASK_NAME%" /tr "\"%SCRIPT_PATH%\"" /sc daily /st 23:00 /rl LIMITED

if errorlevel 1 (
  echo [ERROR] No se pudo crear la tarea programada.
  exit /b 1
)

echo Tarea creada correctamente.
echo Puedes revisarla en el Programador de tareas de Windows.
exit /b 0
