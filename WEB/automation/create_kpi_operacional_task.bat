@echo off
setlocal

rem Crea la tarea de Windows que carga el KPI Operacional cada una hora.
rem Para cambiar la frecuencia: editar CADA_HORAS y volver a ejecutar este archivo.
set "TASK_NAME=KPI_Operacional_Carga"
set "CADA_HORAS=1"
set "SCRIPT_PATH=%~dp0run_kpi_operacional.bat"

echo Creando/actualizando tarea programada "%TASK_NAME%" (cada %CADA_HORAS% hora(s))...
schtasks /create /f /tn "%TASK_NAME%" /tr "\"%SCRIPT_PATH%\"" /sc hourly /mo %CADA_HORAS% /st 00:00 /rl LIMITED

if errorlevel 1 (
  echo [ERROR] No se pudo crear la tarea programada.
  exit /b 1
)

echo Tarea creada correctamente.
echo Puedes revisarla en el Programador de tareas de Windows.
exit /b 0
