@echo off
setlocal

set "TASK_NAME=Santander_Bench_Diario_10AM"
set "SCRIPT_PATH=%~dp0run_daily_job.bat"

echo Creando/actualizando tarea programada "%TASK_NAME%"...
schtasks /create /f /tn "%TASK_NAME%" /tr "\"%SCRIPT_PATH%\"" /sc weekly /d MON,TUE,WED,THU,FRI /st 10:00 /rl LIMITED

if errorlevel 1 (
  echo [ERROR] No se pudo crear la tarea programada.
  exit /b 1
)

echo Tarea creada correctamente.
echo Puedes revisarla en el Programador de tareas de Windows.
exit /b 0
