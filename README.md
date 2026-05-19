# Proyecto Productividades


Proyecto de automatizacion, carga ETL y visualizacion web de productividades para distintas carteras. El repositorio integra scripts Python que descargan y cargan informacion operacional en SQL Server, una API FastAPI para consultar indicadores y un frontend React/Vite para analizar productividad por cartera.

## Modulos principales

- `ETL/`: procesos de lectura, limpieza y carga a SQL Server.
- `DESCARGAS/`: scripts de descarga desde visor, FTP o SFTP.
- `WEB/backend/`: API FastAPI que expone los indicadores para el frontend.
- `WEB/frontend/`: aplicacion React + Bootstrap.
- `WEB/automation/`: job diario para descargar BENCH mora tardia y ejecutar ETL.
- `sql/`: scripts de apoyo para tablas, vistas y metas.
- `archivos/`: archivos auxiliares usados por algunos procesos, como `orden_gest.txt`.

## Requisitos

- Windows recomendado para los `.bat` incluidos.
- Python 3.10+.
- SQL Server.
- ODBC Driver 17 o 18 for SQL Server.
- Node.js + npm.
- Acceso a las fuentes de datos correspondientes: visor SCT, FTP La Araucana, SFTP BIT o archivos locales.

## Instalacion

Desde la raiz del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r WEB\backend\requirements.txt
```

Instalar el frontend:

```powershell
cd WEB\frontend
npm install
cd ..\..
```

Dependencias opcionales segun proceso:

```powershell
python -m pip install -r WEB\automation\requirements.txt
python -m playwright install chromium
python -m pip install paramiko
```

`paramiko` se usa en `DESCARGAS\descarga_bit_contencion.py`.

## Configuracion

Crear un archivo `.env` en la raiz del proyecto. Varios scripts tambien leen `ETL\.env` o `DESCARGAS\.env` cuando corresponde.

Variables base de SQL Server:

```env
DB_SERVER=tu_servidor
DB_NAME=tu_base
DB_USER=tu_usuario
DB_PASSWORD=tu_password
DB_DRIVER=ODBC Driver 18 for SQL Server
```

## Ejecutar aplicacion web

Opcion rapida en Windows:

```powershell
WEB\start_web.bat
```

El script abre backend y frontend en ventanas separadas:

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`
- Healthcheck: `http://localhost:8000/api/health`

Ejecucion manual del backend:

```powershell
cd WEB\backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Ejecucion manual del frontend:

```powershell
cd WEB\frontend
$env:VITE_API_URL="http://localhost:8000"
npm run dev -- --host 0.0.0.0 --port 5173
```

Rutas principales del frontend:

- `/`: inicio.
- `/sc-tardia`: productividad Santander Consumer mora tardia.
- `/sc-temprana`: productividad Santander Consumer mora temprana.
- `/gm`: productividad GM.
- `/bit`: seguimiento BIT.
- `/la-araucana`: La Araucana.
- `/porsche`: dashboard Porsche.

## ETL principales

Ejecutar desde la raiz con el entorno virtual activo.

Santander Consumer mora tardia:

```powershell
python ETL\etl_bench_stc.py
```

Santander Consumer mora temprana:

```powershell
python ETL\etl_bench_temp_stc.py
python ETL\etl_asigna_gestion_temp_stc.py
```

GM:

```powershell
python ETL\etl_asigna_gm.py
```

BIT:

```powershell
python ETL\etl_bit.py --folder "C:\ruta\BIT" --periodo 2026-05
```

La Araucana:

```powershell
python ETL\etl_araucana.py
```

Santander/Home u otros seguimientos:

```powershell
python ETL\etl_bench_sth.py
```

Algunos scripts tienen rutas locales por defecto. Si se ejecutan en otro equipo, revisar las constantes de ruta o definir las variables de entorno soportadas antes de correrlos.

## Descargas

Descarga BENCH desde visor SCT:

```powershell
python DESCARGAS\descarga_SCT.py
```

Descarga La Araucana desde FTP:

```powershell
python DESCARGAS\descarga_araucana.py
```

Descarga BIT contencion desde SFTP:

```powershell
python DESCARGAS\descarga_bit_contencion.py
```

## Automatizacion diaria

Instalar dependencias:

```powershell
python -m pip install -r WEB\automation\requirements.txt
python -m playwright install chromium
```

Prueba manual:

```powershell
WEB\automation\run_daily_job.bat
```

Crear tarea programada de lunes a viernes a las 10:00:

```powershell
WEB\automation\create_scheduled_task.bat
```

Comportamiento del job diario:

- Omite sabados y domingos.
- Busca el archivo esperado segun fecha del dia.
- Si no hay archivo nuevo, termina sin cargar.
- Si el `source_file` ya existe en SQL Server, no reprocesa.
- Si hay archivo nuevo, descarga y ejecuta el ETL de BENCH mora tardia.

## Scripts SQL

- `sql\bit_setup.sql`: crea tablas base, indices y vista `dbo.vw_BIT_data` para BIT.
- `sql\bit_metas_template.sql`: plantilla mensual para cargar metas BIT por tramo.
- `sql\gm_metas_mensuales.sql`: crea/actualiza metas y ponderadores mensuales de GM.

Antes de usar el modulo BIT, ejecutar `sql\bit_setup.sql` en la base destino y luego cargar metas con `sql\bit_metas_template.sql`.

## Tablas y vistas relevantes

El proyecto crea o consulta, entre otras, las siguientes entidades:

- `dbo.tmp_bench_STC`
- `dbo.tmp_bench_temp_STC`
- `dbo.tmp_bench_temp_STC_asignado`
- `dbo.tmp_asig_GM`
- `dbo.gm_metas_mensuales`
- `dbo.tmp_BIT_contencion`
- `dbo.tmp_BIT_carterizado`
- `dbo.tmp_BIT_metas`
- `dbo.vw_BIT_data`
- `dbo.tmp_LA_asignacion`
- `dbo.tmp_LA_pagos`
- `dbo.tmp_LA_performance_cache`
- `dbo.dashboard_data`

La API tambien depende de tablas operacionales existentes, por ejemplo `dbo.tmp_GEST_CRM`, `dbo.tmp_ejecutivos`, `dbo.tmp_carterizado_GM` y `dbo.tmp_pagos_gm`.

## Validacion rapida

Backend:

```powershell
Invoke-WebRequest http://localhost:8000/api/health
```

Frontend:

```powershell
cd WEB\frontend
npm run build
```

Si el frontend no encuentra la API, definir `VITE_API_URL=http://localhost:8000` antes de ejecutar `npm run dev`.
