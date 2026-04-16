# WEB - Productividad Ejecutivos

Este módulo contiene la aplicación web para la visualización y análisis de la productividad de ejecutivos.

---

## 📂 Estructura

- `backend/`: API FastAPI que consulta SQL Server y calcula vistas general/por ciclo.
- `frontend/`: React + Bootstrap con filtros dinámicos y tablas de productividad.
- `start_web.bat`: Script para iniciar el backend y frontend simultáneamente (solo Windows).

---

## ⚙️ Requisitos

*   Python 3.10+
*   Node.js (para el frontend)

---

## 🔐 Configuración (Backend)

Las siguientes variables de entorno son necesarias para la conexión a la base de datos y la tabla de productividad. Se deben definir en un archivo `.env` en la raíz del proyecto o en `WEB/backend/.env`:

```
DB_SERVER=tu_servidor
DB_NAME=tu_base_de_datos
DB_USER=tu_usuario
DB_PASSWORD=tu_password
DB_DRIVER=ODBC Driver 17 for SQL Server # Opcional, por defecto 'ODBC Driver 17 for SQL Server'
PRODUCTIVIDAD_TABLE=dbo.tmp_bench_STC # Opcional, por defecto 'dbo.tmp_bench_STC'
```

---

## Backend (FastAPI)

1. Crear/activar entorno virtual.
2. Instalar dependencias:

```bash
python -m pip install -r WEB/backend/requirements.txt
```

3. Ejecutar API (desde `WEB/backend`):

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Frontend (React + Bootstrap)

1. Instalar dependencias (desde `WEB/frontend`):

```bash
npm install
```

2. (Opcional) Definir la URL del backend:

```bash
set VITE_API_URL=http://localhost:8000
```

Si no se define `VITE_API_URL`, el frontend intentará conectarse automáticamente a `http://<host_actual>:8000`.

3. Ejecutar en desarrollo (desde `WEB/frontend`):

```bash
npm run dev
```

---

## ▶️ Inicio Rápido (Solo Windows)

Para iniciar el backend y el frontend simultáneamente, ejecuta el siguiente script desde la raíz del proyecto:

```bash
WEB\start_web.bat
```

Este script abrirá automáticamente el navegador con la aplicación y mostrará las URLs locales y de red (`http://IP_DE_TU_PC:5173`) para acceder desde otros equipos en la misma red.
