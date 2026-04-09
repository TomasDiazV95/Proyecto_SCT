# WEB - Productividad Ejecutivos

## Estructura

- `backend/`: API FastAPI que consulta SQL Server y calcula vistas general/por ciclo.
- `frontend/`: React + Bootstrap con filtros dinámicos y tablas de productividad.

## Backend (FastAPI)

1. Crear/activar entorno virtual.
2. Instalar dependencias:

```bash
python -m pip install -r WEB/backend/requirements.txt
```

3. Ejecutar API:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Ejecutar el comando en la carpeta `WEB/backend`.

Variables esperadas en `.env` o `ETL/.env`:

- `DB_SERVER`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_DRIVER` (opcional)
- `PRODUCTIVIDAD_TABLE` (opcional, por defecto `dbo.tmp_bench_STC`)

## Frontend (React + Bootstrap)

1. Instalar dependencias:

```bash
npm install
```

2. (Opcional) definir URL del backend:

```bash
set VITE_API_URL=http://localhost:8000
```

Si no defines `VITE_API_URL`, el frontend usa automaticamente `http://<host_actual>:8000`.

3. Ejecutar en desarrollo:

```bash
npm run dev
```

Ejecutar los comandos en `WEB/frontend`.

## Inicio rapido

Puedes iniciar backend y frontend con:

```bash
WEB\start_web.bat
```

El script muestra URLs locales y de red (`http://IP_DE_TU_PC:5173`) para abrir desde otro equipo en la misma red.
