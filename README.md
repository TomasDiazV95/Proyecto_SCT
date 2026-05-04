# Proyecto SCT - ETL & Web App para Productividad de Ejecutivos

Este proyecto integra un proceso **ETL (Extract, Transform, Load)** para la carga y limpieza de datos desde archivos Excel hacia **SQL Server**, con una **aplicación web** que permite visualizar y analizar la productividad de ejecutivos.

---

## 📂 Estructura del proyecto

```
Proyecto_SCT/
│
├── ETL/
│   ├── etl_bench_stc.py
│   ├── data_cleaners.py
│
├── WEB/
│   ├── backend/
│   │   ├── main.py
│   │   ├── requirements.txt
│   │   └── ...
│   ├── frontend/
│   │   ├── src/
│   │   ├── public/
│   │   ├── index.html
│   │   ├── package.json
│   │   └── ...
│   └── start_web.bat
│
├── .env                    # Variables de entorno (no incluido)
├── .gitignore
├── requirements.txt
└── README.md
```

---

## ⚙️ Requisitos

* Python 3.10+
* SQL Server
* ODBC Driver (17 o 18)

---

## 📦 Instalación

1. Clonar repositorio:

```bash
git clone https://github.com/TomasDiazV95/Proyecto_SCT.git
cd Proyecto_SCT
```

2. Crear entorno virtual:

```bash
python -m venv .venv
.venv\Scripts\activate
```

3. Instalar dependencias:

```bash
python -m pip install -r requirements.txt
```

---

## 🔐 Configuración

Crear archivo `.env` en la raíz:

```
DB_SERVER=tu_servidor
DB_NAME=tu_base_de_datos
DB_USER=tu_usuario
DB_PASSWORD=tu_password
DB_DRIVER=ODBC Driver 17 for SQL Server
```

---

## ▶️ Ejecución

```bash
python ETL/etl_bench_stc.py
```

Para mora temprana:

```bash
python ETL/etl_bench_temp_stc.py
```

Para asignar mejor gestión (cartera 526) usando `archivos/orden_gest.txt`:

```bash
python ETL/etl_asigna_gestion_temp_stc.py
```

---

## 📊 Tecnologías utilizadas

* `pandas`
* `pyodbc`
* `python-dotenv`
* `thefuzz` + `python-Levenshtein`
* `openpyxl`
* `FastAPI`
* `uvicorn`
* `React`
* `Bootstrap`
* `Node.js`
* `npm`
