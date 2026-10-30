"""Productividad de procuradores.

Notificaciones, embargos, oficios e incautaciones salen del CRM judicial (JUDICIAL/*.sql, otro servidor).
Recupero castigo y gestion judicial se ingresan a mano. Metas, pesos y logros manuales: dbo.procuradores_metas.

Una meta con ejecutivo GRUPAL es de la cartera: su logro cuenta las gestiones de todos los usuarios de esa
cartera y se aplica a cada uno de sus ejecutivos.
Una meta de un ejecutivo sin usuario_crm tambien cuenta toda la cartera, pero solo para el: es el responsable
de esa variable, sin importar quien hizo la gestion (Tanner).
"""
from __future__ import annotations

from collections import Counter
from datetime import date

import cache
from cache import cached, cached_view
from database import get_connection, run_query, run_query_judicial


AUTOMATICAS = ("notificaciones", "embargos", "oficios", "incautaciones")
MANUALES = ("recupero", "gestion_judicial")
ETIQUETAS = {
    "notificaciones": "Notificaciones",
    "embargos": "Embargos",
    "oficios": "Oficios",
    "incautaciones": "Incautaciones",
    "recupero": "Recupero castigo",
    "gestion_judicial": "Gestión judicial",
}
GRUPAL = "GRUPAL"
TOPE_CUMPLIMIENTO = 1.3  # por variable
# Cartera en procuradores_metas -> titulo. Forum aun no esta en el CRM judicial.
CARTERAS = {"SANTANDER CONSUMER": "Santander Consumer", "TANNER": "Tanner", "FORUM": "Forum"}
CARTERAS_MAPEADAS = ("SANTANDER CONSUMER", "TANNER")

_GESTIONES_SQL = """
SET NOCOUNT ON;
DECLARE @desde DATE = ?, @hasta DATE = ?;

SELECT
    'notificaciones' AS variable, h.MANDANTE AS cartera, h.[NUMERO OPERACION] AS op, h.[NOMBRE USUARIO] AS usuario,
    MIN(h.TRIBUNAL) AS tribunal, MIN(h.[FECHA GESTIÓN]) AS fecha
FROM vw_histo_juicio_Reporte h
WHERE h.MANDANTE IN ('TANNER', 'SANTANDER CONSUMER')
  AND h.ESTADO = 'NOTIFICACION'
  AND h.SUBESTADO IN ('NOTIFICACION ART 44 DEL CPC', 'NOTIFICACION PERSONAL')
  AND h.[FECHA GESTIÓN] >= @desde
  AND h.[FECHA GESTIÓN] < @hasta
GROUP BY h.MANDANTE, h.[NUMERO OPERACION], h.[NOMBRE USUARIO]

UNION ALL

SELECT
    'embargos', h.MANDANTE, h.[NUMERO OPERACION], h.[NOMBRE USUARIO],
    MIN(h.TRIBUNAL), MIN(h.[FECHA GESTIÓN])
FROM vw_histo_juicio_Reporte h
WHERE h.MANDANTE IN ('TANNER', 'SANTANDER CONSUMER')
  AND h.ESTADO = 'EMBARGO'
  AND h.SUBESTADO = 'EMBARGO VEHICULO'
  AND h.[FECHA GESTIÓN] >= @desde
  AND h.[FECHA GESTIÓN] < @hasta
  AND NOT EXISTS (
        SELECT 1 FROM vw_histo_juicio_Reporte prev
        WHERE prev.[NUMERO OPERACION] = h.[NUMERO OPERACION]
          AND prev.MANDANTE = h.MANDANTE
          AND prev.SUBESTADO = 'EMBARGO VEHICULO'
          AND prev.[FECHA GESTIÓN] < @desde
  )
GROUP BY h.MANDANTE, h.[NUMERO OPERACION], h.[NOMBRE USUARIO]

UNION ALL

SELECT
    'oficios', d.MANDANTE, d.OP, h.[NOMBRE USUARIO],
    MIN(h.TRIBUNAL), MIN(h.[FECHA GESTIÓN])
FROM dbo.vw_consulta_informacion_deudores_Reporte d
INNER JOIN vw_histo_juicio_Reporte h ON h.[NUMERO OPERACION] = d.OP AND h.MANDANTE = d.MANDANTE
WHERE d.MANDANTE IN ('TANNER', 'SANTANDER CONSUMER')
  AND d.[FECHA EMBARGO] >= @desde
  AND d.[FECHA EMBARGO] < @hasta
  AND h.ESTADO = 'EMBARGO'
  AND h.SUBESTADO = 'ENCARGA INCAUTACION RECEPTOR'
  AND h.[FECHA GESTIÓN] >= @desde
  AND h.[FECHA GESTIÓN] < @hasta
GROUP BY d.MANDANTE, d.OP, h.[NOMBRE USUARIO]

UNION ALL

SELECT
    'incautaciones', h.MANDANTE, h.[NUMERO OPERACION], h.[NOMBRE USUARIO],
    MIN(h.TRIBUNAL), MIN(h.[FECHA GESTIÓN])
FROM vw_histo_juicio_Reporte h
WHERE h.MANDANTE IN ('TANNER', 'SANTANDER CONSUMER')
  AND h.ESTADO = 'INCAUTADO'
  AND h.SUBESTADO = 'INCAUTA VEHÍCULO'
  AND h.[FECHA GESTIÓN] >= @desde
  AND h.[FECHA GESTIÓN] < @hasta
  AND NOT EXISTS (
        SELECT 1 FROM vw_histo_juicio_Reporte prev
        WHERE prev.[NUMERO OPERACION] = h.[NUMERO OPERACION]
          AND prev.MANDANTE = h.MANDANTE
          AND prev.SUBESTADO = 'INCAUTA VEHÍCULO'
          AND prev.[FECHA GESTIÓN] < @desde
  )
GROUP BY h.MANDANTE, h.[NUMERO OPERACION], h.[NOMBRE USUARIO]
"""


def _clean(value: object) -> str:
    return str(value or "").strip()


def _usuario_key(value: object) -> str:
    return _clean(value).upper()


def _rango(periodo: str) -> tuple[str, str]:
    desde = date.fromisoformat(f"{periodo[:7]}-01")
    hasta = date(desde.year + desde.month // 12, desde.month % 12 + 1, 1)
    return desde.isoformat(), hasta.isoformat()


def _gestiones(periodo: str) -> list[dict]:
    return cached(
        ("procuradores", "gestiones", periodo),
        lambda: run_query_judicial(_GESTIONES_SQL, _rango(periodo)),
    )


def _metas(periodo: str) -> list[dict]:
    return run_query(
        """
        SELECT cartera, ejecutivo, variable, usuario_crm, CAST(peso AS float) AS peso,
               CAST(meta AS float) AS meta, CAST(logro_manual AS float) AS logro_manual
        FROM dbo.procuradores_metas
        WHERE periodo = ?
        """,
        (periodo,),
    )


def _periodos() -> list[str]:
    rows = run_query("SELECT DISTINCT periodo FROM dbo.procuradores_metas ORDER BY periodo DESC")
    return [row["periodo"] for row in rows]


def _resolve_period(periodo: str | None) -> str:
    text = _clean(periodo)[:7]
    if text:
        return text
    periodos = _periodos()
    if not periodos:
        raise RuntimeError("No hay metas de procuradores cargadas")
    return periodos[0]


def _ejecutivos(metas: list[dict], cartera: str) -> list[str]:
    return sorted({m["ejecutivo"] for m in metas if m["cartera"] == cartera and m["ejecutivo"] != GRUPAL})


@cached_view
def get_filter_values(periodo: str | None = None) -> dict:
    periodos = _periodos()
    return {"periodos": periodos, "carteras": [{"value": k, "label": v} for k, v in CARTERAS.items()]}


def _logro(meta: dict, conteos: Counter) -> float | None:
    if meta["variable"] in MANUALES:
        return meta["logro_manual"]
    if meta["cartera"] not in CARTERAS_MAPEADAS:
        return None
    if meta["ejecutivo"] == GRUPAL or not meta["usuario_crm"]:
        return sum(n for (cartera, variable, _), n in conteos.items() if cartera == meta["cartera"] and variable == meta["variable"])
    return conteos[(meta["cartera"], meta["variable"], _usuario_key(meta["usuario_crm"]))]


def _variable(meta: dict, conteos: Counter) -> dict:
    logro = _logro(meta, conteos)
    return {
        "logro": logro,
        "meta": meta["meta"],
        "peso": meta["peso"],
        "cumplimiento": None if logro is None or not meta["meta"] else min(logro / meta["meta"], TOPE_CUMPLIMIENTO),
        "grupal": meta["ejecutivo"] == GRUPAL,
        "manual": meta["variable"] in MANUALES,
    }


def _fila(metas: list[dict], cartera: str, ejecutivo: str, conteos: Counter) -> dict:
    propias = [m for m in metas if m["cartera"] == cartera and m["ejecutivo"] in (ejecutivo, GRUPAL)]
    variables = {m["variable"]: _variable(m, conteos) for m in propias}

    # Gestiones de una variable sin meta para el ejecutivo: se muestran, pero no suman al cumplimiento.
    usuario = next((m["usuario_crm"] for m in propias if m["usuario_crm"]), None)
    for variable in AUTOMATICAS:
        hechas = conteos[(cartera, variable, _usuario_key(usuario))] if usuario else 0
        if variable not in variables and hechas:
            variables[variable] = {"logro": hechas, "meta": None, "peso": 0, "cumplimiento": None, "grupal": False, "manual": False}

    pendientes = [ETIQUETAS[k] for k, v in variables.items() if v["peso"] and v["logro"] is None]
    cumplimiento = sum(v["peso"] * (v["cumplimiento"] or 0) for v in variables.values())
    return {
        "ejecutivo": ejecutivo,
        "variables": variables,
        "cumplimiento": cumplimiento if cartera in CARTERAS_MAPEADAS else None,
        "pendientes": pendientes,
    }


@cached_view
def get_general(filters: dict) -> dict:
    periodo = _resolve_period(filters.get("periodo"))
    metas = _metas(periodo)
    conteos = Counter((r["cartera"], r["variable"], _usuario_key(r["usuario"])) for r in _gestiones(periodo))

    carteras = [
        {
            "cartera": cartera,
            "titulo": titulo,
            "mapeada": cartera in CARTERAS_MAPEADAS,
            "rows": [_fila(metas, cartera, ejecutivo, conteos) for ejecutivo in _ejecutivos(metas, cartera)],
        }
        for cartera, titulo in CARTERAS.items()
        if any(m["cartera"] == cartera for m in metas)
    ]
    return {
        "periodo": periodo,
        "tope_cumplimiento": TOPE_CUMPLIMIENTO,
        "carteras": carteras,
        "metas": [{**m, "cartera_titulo": CARTERAS.get(m["cartera"], m["cartera"])} for m in metas],
    }


@cached_view
def get_detalle(filters: dict) -> list[dict]:
    """Una fila por gestion contada: operacion, usuario, tribunal y fecha."""
    periodo = _resolve_period(filters.get("periodo"))
    filas = [
        {
            "variable": row["variable"],
            "gestion": ETIQUETAS[row["variable"]],
            "cartera": row["cartera"],
            "cartera_titulo": CARTERAS.get(row["cartera"], row["cartera"]),
            "op": row["op"],
            "usuario": _clean(row["usuario"]),
            "tribunal": _clean(row["tribunal"]),
            "fecha": row["fecha"].isoformat() if row["fecha"] else "",
        }
        for row in _gestiones(periodo)
    ]
    return sorted(filas, key=lambda f: (f["cartera"], f["gestion"], f["usuario"], f["fecha"]))


def guardar_logros(periodo: str, valores: list[dict], user_id: int) -> None:
    """Guarda recupero y gestion judicial. Valor vacio = sin ingresar. Todo o nada."""
    for item in valores:
        if item["variable"] not in MANUALES:
            raise ValueError(f"{item['variable']} no se ingresa a mano")
        if item.get("valor") is not None and item["valor"] < 0:
            raise ValueError("El logro no puede ser negativo")

    with get_connection() as cn:
        cur = cn.cursor()
        for item in valores:
            cur.execute(
                """
                UPDATE dbo.procuradores_metas
                SET logro_manual = ?, actualizado_por = ?, actualizado_en = SYSDATETIME()
                WHERE periodo = ? AND cartera = ? AND ejecutivo = ? AND variable = ?
                """,
                (item.get("valor"), user_id, periodo[:7], item["cartera"], item["ejecutivo"], item["variable"]),
            )
            if cur.rowcount == 0:
                cn.rollback()
                raise ValueError(f"No hay meta de {item['variable']} para {item['ejecutivo']} en {periodo}")
        cn.commit()
    cache.clear()
