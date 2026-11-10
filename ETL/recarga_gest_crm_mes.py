"""Recarga un mes completo de dbo.tmp_GEST_CRM desde el CRM 3.0 para las carteras indicadas.

La carga diaria (traspaso_gestiones/etl_diario.py) solo lee el dia anterior. El CRM graba tarde, con la hora de la
llamada, las llamadas del discador que la ejecutiva tipifica despues, y esas gestiones nunca llegan. Este script
borra el mes de esas carteras en tmp_GEST_CRM y lo vuelve a cargar con la misma consulta, las mismas columnas y el
mismo hash_registro que la carga diaria, asi queda igual al CRM de hoy y la carga diaria no duplica nada.

Uso:
    python ETL/recarga_gest_crm_mes.py --mes 2026-10                    # cartera 531 (La Araucana)
    python ETL/recarga_gest_crm_mes.py --mes 2026-10 --carteras 531,532
"""
from __future__ import annotations

import argparse
import hashlib
import os
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pymysql
import pyodbc
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "ETL" / ".env")

TABLE = "dbo.tmp_GEST_CRM"
BATCH_SIZE = 5000

# Copia de SQL_GESTIONES_DB30 de traspaso_gestiones/etl_diario.py (no cambiarla sin cambiar alla).
SQL_GESTIONES_DB30 = """
SELECT
    g.idCartera AS cartera,
    c.rut,
    CONVERT(c.dv USING utf8mb4) COLLATE utf8mb4_unicode_ci AS dv,
    CONVERT(c.nombreCliente USING utf8mb4) COLLATE utf8mb4_unicode_ci AS nombreCliente,
    CONVERT(UPPER(g.username) USING utf8mb4) COLLATE utf8mb4_unicode_ci AS UsuarioGestion,
    CONVERT(tg.nombre USING utf8mb4) COLLATE utf8mb4_unicode_ci AS AccionGestion,
    CONVERT(td.nombre USING utf8mb4) COLLATE utf8mb4_unicode_ci AS ContactoGestion,
    CONVERT(r.nombre USING utf8mb4) COLLATE utf8mb4_unicode_ci AS RespuestaGestion,
    CONVERT(g.observaciones USING utf8mb4) COLLATE utf8mb4_unicode_ci AS observaciones,
    DATE(g.fechaInsert) AS GestionFecha,
    TIME(g.fechaInsert) AS GestionHora,
    CONVERT(g.nroDocumento USING utf8mb4) COLLATE utf8mb4_unicode_ci AS nroDocumento,
    CONVERT(IF(t.telefono IS NULL, g.fono, t.telefono) USING utf8mb4)
        COLLATE utf8mb4_unicode_ci AS telefono,
    'gestion' AS origen
FROM gestion g
LEFT JOIN cliente c ON g.rut = c.rut
LEFT JOIN tipogestion tg ON g.idTipoGestion = tg.idTipoGestion
LEFT JOIN tipodeudor td ON g.idTipoDeudor = td.idTipoDeudor
LEFT JOIN respuesta r ON g.idRespuesta = r.idRespuesta
LEFT JOIN telefono t ON g.idTelefono = t.idTelefono
WHERE g.idCartera = %s
  AND g.fechaInsert >= %s
  AND g.fechaInsert <= %s
  AND g.observaciones NOT IN ('__INTENTO_LLAMADA__')
GROUP BY c.rut, GestionFecha, GestionHora, telefono

UNION ALL

SELECT
    CAST(vl.postal_code AS UNSIGNED) AS cartera,
    c2.rut,
    CONVERT(c2.dv USING utf8mb4) COLLATE utf8mb4_unicode_ci AS dv,
    CONVERT(c2.nombreCliente USING utf8mb4) COLLATE utf8mb4_unicode_ci AS nombreCliente,
    CONVERT(v.user USING utf8mb4) COLLATE utf8mb4_unicode_ci AS UsuarioGestion,
    CONVERT('Gestion Discador' USING utf8mb4) COLLATE utf8mb4_unicode_ci AS AccionGestion,
    CONVERT('Gestion Discador' USING utf8mb4) COLLATE utf8mb4_unicode_ci AS ContactoGestion,
    CONVERT(v.status USING utf8mb4) COLLATE utf8mb4_unicode_ci AS RespuestaGestion,
    CONVERT('Llamada por Discador' USING utf8mb4) COLLATE utf8mb4_unicode_ci AS observaciones,
    DATE(v.call_date) AS GestionFecha,
    TIME(v.call_date) AS GestionHora,
    CONVERT('' USING utf8mb4) COLLATE utf8mb4_unicode_ci AS nroDocumento,
    CONVERT(v.phone_number USING utf8mb4) COLLATE utf8mb4_unicode_ci AS telefono,
    'vicidial_log' AS origen
FROM vicidial_log v
LEFT JOIN vicidial_list vl ON v.lead_id = vl.lead_id
LEFT JOIN cliente c2 ON vl.vendor_lead_code = c2.rut
WHERE v.user = 'VDAD'
  AND vl.postal_code = %s
  AND v.call_date >= %s
  AND v.call_date <= %s;
"""

# Mismo hash que la carga diaria.
HASH_FIELDS = [
    "cartera", "rut", "dv", "nombreCliente", "UsuarioGestion", "AccionGestion",
    "ContactoGestion", "RespuestaGestion", "observaciones", "GestionFecha",
    "GestionHora", "nroDocumento", "telefono", "origen",
]


def to_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def hash_registro(row: dict) -> str:
    payload = "|".join(to_str(row.get(f)).strip() for f in HASH_FIELDS)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hora(value):
    if isinstance(value, timedelta):
        total = int(value.total_seconds())
        return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"
    return value


def sqlserver() -> pyodbc.Connection:
    faltan = [n for n in ("DB_SERVER", "DB_NAME", "DB_USER", "DB_PASSWORD") if not os.getenv(n)]
    if faltan:
        raise RuntimeError("Faltan variables en .env: " + ", ".join(faltan))
    disponibles = pyodbc.drivers()
    driver = next(
        (d for d in (os.getenv("DB_DRIVER"), "ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server")
         if d and d in disponibles),
        None,
    )
    if not driver:
        raise RuntimeError(f"No hay driver ODBC para SQL Server. Drivers encontrados: {disponibles}")
    return pyodbc.connect(
        f"Driver={{{driver}}};Server={os.getenv('DB_SERVER')};Database={os.getenv('DB_NAME')};"
        f"UID={os.getenv('DB_USER')};PWD={os.getenv('DB_PASSWORD')};TrustServerCertificate=yes;",
        autocommit=False,
    )


def crm() -> pymysql.connections.Connection:
    faltan = [n for n in ("DB3_HOST", "DB3_USER", "DB3_PASSWORD", "DB3_NAME") if not os.getenv(n)]
    if faltan:
        raise RuntimeError("Faltan variables del CRM 3.0 en .env: " + ", ".join(faltan))
    return pymysql.connect(
        host=os.getenv("DB3_HOST"),
        port=int(os.getenv("DB3_PORT") or 3306),
        user=os.getenv("DB3_USER"),
        password=os.getenv("DB3_PASSWORD"),
        database=os.getenv("DB3_NAME"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=30,
        read_timeout=600,
    )


def filas_cartera(cn_crm, cartera: int, mes: date, fin: date) -> list[tuple]:
    """Gestiones del mes dia por dia, como la carga diaria (el GROUP BY de la consulta es por dia)."""
    filas: dict[str, tuple] = {}
    dia = mes
    with cn_crm.cursor() as cur:
        while dia < fin:
            desde, hasta = f"{dia.isoformat()} 00:00:00", f"{dia.isoformat()} 23:59:59"
            cur.execute(SQL_GESTIONES_DB30, (cartera, desde, hasta, cartera, desde, hasta))
            for r in cur.fetchall():
                h = hash_registro(r)
                filas[h] = (
                    int(r["cartera"]) if r["cartera"] is not None else None, r["rut"], r["dv"], r["nombreCliente"],
                    r["UsuarioGestion"], r["AccionGestion"], r["ContactoGestion"], r["RespuestaGestion"],
                    r["observaciones"], r["GestionFecha"], hora(r["GestionHora"]), r["nroDocumento"], r["telefono"],
                    r["origen"], h,
                )
            dia += timedelta(days=1)
    return list(filas.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mes", required=True, help="Mes a recargar, AAAA-MM")
    parser.add_argument("--carteras", default="531", help="Carteras del CRM 3.0 separadas por coma (por defecto 531)")
    args = parser.parse_args()

    mes = datetime.strptime(args.mes, "%Y-%m").date()
    fin = (mes + timedelta(days=32)).replace(day=1)
    carteras = [int(c) for c in args.carteras.split(",") if c.strip()]

    cn_crm, cn_sql = crm(), sqlserver()
    try:
        for cartera in carteras:
            t0 = time.time()
            filas = filas_cartera(cn_crm, cartera, mes, fin)
            cur = cn_sql.cursor()
            cur.fast_executemany = True
            cur.execute(f"DELETE FROM {TABLE} WHERE cartera = ? AND GestionFecha >= ? AND GestionFecha < ?",
                        (cartera, mes, fin))
            borradas = cur.rowcount
            sql = f"""INSERT INTO {TABLE} (cartera, rut, dv, nombreCliente, UsuarioGestion, AccionGestion,
                ContactoGestion, RespuestaGestion, observaciones, GestionFecha, GestionHora, nroDocumento, telefono,
                origen, hash_registro) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            for i in range(0, len(filas), BATCH_SIZE):
                cur.executemany(sql, filas[i:i + BATCH_SIZE])
            cn_sql.commit()
            print(f"cartera {cartera} {mes:%Y-%m}: {borradas} filas reemplazadas por {len(filas)} en {time.time() - t0:.0f} s")
    except Exception:
        cn_sql.rollback()
        raise
    finally:
        cn_crm.close()
        cn_sql.close()


if __name__ == "__main__":
    main()
