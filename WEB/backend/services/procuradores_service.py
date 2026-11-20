"""Productividad de procuradores.

Notificaciones, embargos, oficios e incautaciones salen del CRM judicial (JUDICIAL/*.sql, otro servidor) para
Santander Consumer. Tanner y Forum salen de la API de hitos (integrations/api_hitos.py) cuando su cliente_id esta
en el .env; mientras no, Tanner sigue con el CRM y Forum queda sin mapear.
Recupero castigo y gestion judicial se ingresan a mano. Metas, pesos y logros manuales: dbo.procuradores_metas.

Una meta con ejecutivo GRUPAL es de la cartera: su logro cuenta las gestiones de todos los usuarios de esa
cartera y se aplica a cada uno de sus ejecutivos.
Una meta de un ejecutivo sin usuario_crm tambien cuenta toda la cartera, pero solo para el: es el responsable
de esa variable, sin importar quien hizo la gestion (Tanner).
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import date

import cache
from cache import cached, cached_view
from database import get_connection, run_query, run_query_judicial
from integrations import api_hitos
from services._comunes import clean as _clean


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
# Cartera en procuradores_metas -> titulo.
CARTERAS = {"SANTANDER CONSUMER": "Santander Consumer", "TANNER": "Tanner", "FORUM": "Forum"}
CARTERAS_CRM = ("SANTANDER CONSUMER", "TANNER")
# Carteras que se cuentan con la API de hitos: variable del .env con su cliente_id en la API.
CLIENTE_API_ENV = {"TANNER": "API_BI_CLIENTE_TANNER", "FORUM": "API_BI_CLIENTE_FORUM"}
# Variable -> endpoint de la API y filtros extra. Notificaciones: igual que en el CRM, sin las del art. 52.
ENDPOINTS_API = {
    "notificaciones": ("notificaciones", {"tipos": ["NOTIFICACION_PERSONAL", "NOTIFICACION_ART_44"]}),
    "embargos": ("embargos", {}),
    "oficios": ("oficios", {}),
    "incautaciones": ("incautaciones", {}),
}
# procurador_id de la API -> nombre, solo para mostrar en el detalle (el logro es de toda la cartera).
PROCURADORES_API = {25: "Nathaly Villanueva", 27: "Viviana Sanchez", 31: "Jimena Millar"}

_GESTIONES_SQL = """
SET NOCOUNT ON;
DECLARE @desde DATE = ?, @hasta DATE = ?;

-- Causas que volvieron de NOTIFICACION a DEMANDA PROVEIDA desde el inicio del mes (se calcula una vez: en
-- un NOT EXISTS directo sobre la vista la consulta pasa de ~40 s a ~11 min).
IF OBJECT_ID('tempdb..#revertidas') IS NOT NULL DROP TABLE #revertidas;
SELECT r.[NUMERO OPERACION] AS op, r.MANDANTE AS mandante, MAX(r.[FECHA GESTIÓN]) AS ultima
INTO #revertidas
FROM vw_histo_juicio_Reporte r
WHERE r.MANDANTE IN ('TANNER', 'SANTANDER CONSUMER')
  AND r.ESTADO = 'DEMANDA PROVEIDA'
  AND r.DETALLE LIKE 'ESTADO ANTERIOR NOTIFICACION%'
  AND r.[FECHA GESTIÓN] >= @desde
GROUP BY r.[NUMERO OPERACION], r.MANDANTE;

SELECT
    'notificaciones' AS variable, h.MANDANTE AS cartera, h.[NUMERO OPERACION] AS op, h.[NOMBRE USUARIO] AS usuario,
    MIN(h.TRIBUNAL) AS tribunal, MIN(h.[FECHA GESTIÓN]) AS fecha
FROM vw_histo_juicio_Reporte h
WHERE h.MANDANTE IN ('TANNER', 'SANTANDER CONSUMER')
  AND h.ESTADO = 'NOTIFICACION'
  AND h.SUBESTADO IN ('NOTIFICACION ART 44 DEL CPC', 'NOTIFICACION PERSONAL')
  AND h.[FECHA GESTIÓN] >= @desde
  AND h.[FECHA GESTIÓN] < @hasta
  -- Ya notificada antes del mes: no cuenta, salvo que despues se haya presentado una demanda nueva.
  -- Si la causa se reactivo despues de esa notificacion, tampoco cuenta.
  AND NOT EXISTS (
        SELECT 1 FROM vw_histo_juicio_Reporte prev
        WHERE prev.[NUMERO OPERACION] = h.[NUMERO OPERACION]
          AND prev.MANDANTE = h.MANDANTE
          AND prev.SUBESTADO IN ('NOTIFICACION ART 44 DEL CPC', 'NOTIFICACION PERSONAL')
          AND prev.[FECHA GESTIÓN] < @desde
          AND (
                EXISTS (
                    SELECT 1 FROM vw_histo_juicio_Reporte reac
                    WHERE reac.[NUMERO OPERACION] = prev.[NUMERO OPERACION]
                      AND reac.MANDANTE = prev.MANDANTE
                      AND reac.ESTADO = 'REACTIVADO'
                      AND reac.[FECHA GESTIÓN] >= prev.[FECHA GESTIÓN]
                      AND reac.[FECHA GESTIÓN] <= h.[FECHA GESTIÓN]
                )
                OR NOT EXISTS (
                    SELECT 1 FROM vw_histo_juicio_Reporte dem
                    WHERE dem.[NUMERO OPERACION] = prev.[NUMERO OPERACION]
                      AND dem.MANDANTE = prev.MANDANTE
                      AND dem.ESTADO = 'DEMANDA PRESENTADA'
                      AND dem.[FECHA GESTIÓN] > prev.[FECHA GESTIÓN]
                      AND dem.[FECHA GESTIÓN] <= h.[FECHA GESTIÓN]
                )
          )
  )
  -- Notificacion revertida: si despues la causa vuelve de NOTIFICACION a DEMANDA PROVEIDA, no cuenta.
  AND NOT EXISTS (
        SELECT 1 FROM #revertidas rev
        WHERE rev.op = h.[NUMERO OPERACION]
          AND rev.mandante = h.MANDANTE
          AND rev.ultima >= h.[FECHA GESTIÓN]
  )
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
  -- Causa reactivada: no cuenta si el encargo ya estaba registrado antes de la reactivacion.
  AND NOT EXISTS (
        SELECT 1 FROM vw_histo_juicio_Reporte prev
        INNER JOIN vw_histo_juicio_Reporte reac
            ON reac.[NUMERO OPERACION] = prev.[NUMERO OPERACION]
           AND reac.MANDANTE = prev.MANDANTE
           AND reac.ESTADO = 'REACTIVADO'
           AND reac.[FECHA GESTIÓN] >= prev.[FECHA GESTIÓN]
           AND reac.[FECHA GESTIÓN] <= h.[FECHA GESTIÓN]
        WHERE prev.[NUMERO OPERACION] = d.OP
          AND prev.MANDANTE = d.MANDANTE
          AND prev.SUBESTADO = 'ENCARGA INCAUTACION RECEPTOR'
          AND prev.[FECHA GESTIÓN] < @desde
  )
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


def _usuario_key(value: object) -> str:
    return _clean(value).upper()


def _rango(periodo: str) -> tuple[str, str]:
    desde = date.fromisoformat(f"{periodo[:7]}-01")
    hasta = date(desde.year + desde.month // 12, desde.month % 12 + 1, 1)
    return desde.isoformat(), hasta.isoformat()


def _gestiones_crm(periodo: str) -> list[dict]:
    return cached(
        ("procuradores", "gestiones", periodo),
        lambda: run_query_judicial(_GESTIONES_SQL, _rango(periodo)),
    )


def _clientes_api() -> dict[str, int]:
    """Cartera -> cliente_id de las carteras que se cuentan con la API (requiere usuario de la API en el .env)."""
    if not api_hitos.configurada():
        return {}
    clientes = {}
    for cartera, variable_env in CLIENTE_API_ENV.items():
        valor = os.getenv(variable_env, "").strip()
        if valor:
            clientes[cartera] = int(valor)
    return clientes


def _procurador_api(procurador_id: int | None) -> str:
    if not procurador_id:
        return ""
    return PROCURADORES_API.get(procurador_id, f"Procurador {procurador_id}")


def _hitos_api(cartera: str, cliente_id: int) -> list[dict]:
    """Primer hito de cada pagare en toda la historia del cliente (distinct sin fecha), por variable.
    Asi un pagare cuenta solo en el mes de su primer hito, como en el CRM (ya hecha antes del mes no cuenta)."""

    def cargar() -> list[dict]:
        filas = []
        for variable, (endpoint, extra) in ENDPOINTS_API.items():
            for hito in api_hitos.hitos(endpoint, {"cliente_id": cliente_id, "distinct": True, **extra}):
                fecha = hito.get("fecha_tramite_1")
                filas.append({
                    "variable": variable,
                    "cartera": cartera,
                    "op": hito.get("numero_pagare") or hito.get("rol") or "",
                    "usuario": _procurador_api(hito.get("procurador_id")),
                    "tribunal": hito.get("tribunal_nombre") or "",
                    "fecha": date.fromisoformat(fecha) if fecha else None,
                })
        return filas

    return cached(("procuradores", "api", cartera, cliente_id), cargar)


def _gestiones(periodo: str) -> tuple[list[dict], set[str], dict[str, str]]:
    """Gestiones contadas en el mes, carteras con fuente de gestiones y aviso de las que no se pudieron leer."""
    clientes = _clientes_api()
    filas = [r for r in _gestiones_crm(periodo) if r["cartera"] not in clientes]
    mapeadas = {c for c in CARTERAS_CRM if c not in clientes}
    avisos = {}
    desde, hasta = (date.fromisoformat(d) for d in _rango(periodo))
    for cartera, cliente_id in clientes.items():
        try:
            hitos = _hitos_api(cartera, cliente_id)
        except Exception as exc:  # la API caida no debe botar las demas carteras
            avisos[cartera] = f"No se pudo consultar la API de hitos: {exc}"
            continue
        filas += [h for h in hitos if h["fecha"] and desde <= h["fecha"] < hasta]
        mapeadas.add(cartera)
    return filas, mapeadas, avisos


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


def _logro(meta: dict, conteos: Counter, mapeadas: set[str]) -> float | None:
    if meta["variable"] in MANUALES:
        return meta["logro_manual"]
    if meta["cartera"] not in mapeadas:
        return None
    if meta["ejecutivo"] == GRUPAL or not meta["usuario_crm"]:
        return sum(n for (cartera, variable, _), n in conteos.items() if cartera == meta["cartera"] and variable == meta["variable"])
    return conteos[(meta["cartera"], meta["variable"], _usuario_key(meta["usuario_crm"]))]


def _variable(meta: dict, conteos: Counter, mapeadas: set[str]) -> dict:
    logro = _logro(meta, conteos, mapeadas)
    return {
        "logro": logro,
        "meta": meta["meta"],
        "peso": meta["peso"],
        "cumplimiento": None if logro is None or not meta["meta"] else min(logro / meta["meta"], TOPE_CUMPLIMIENTO),
        "grupal": meta["ejecutivo"] == GRUPAL,
        "manual": meta["variable"] in MANUALES,
    }


def _fila(metas: list[dict], cartera: str, ejecutivo: str, conteos: Counter, mapeadas: set[str]) -> dict:
    propias = [m for m in metas if m["cartera"] == cartera and m["ejecutivo"] in (ejecutivo, GRUPAL)]
    variables = {m["variable"]: _variable(m, conteos, mapeadas) for m in propias}

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
        "cumplimiento": cumplimiento if cartera in mapeadas else None,
        "pendientes": pendientes,
    }


@cached_view
def get_general(filters: dict) -> dict:
    periodo = _resolve_period(filters.get("periodo"))
    metas = _metas(periodo)
    gestiones, mapeadas, avisos = _gestiones(periodo)
    conteos = Counter((r["cartera"], r["variable"], _usuario_key(r["usuario"])) for r in gestiones)
    clientes = _clientes_api()

    carteras = [
        {
            "cartera": cartera,
            "titulo": titulo,
            "mapeada": cartera in mapeadas,
            "fuente": "api" if cartera in clientes else "crm",
            "aviso": avisos.get(cartera, ""),
            "rows": [_fila(metas, cartera, ejecutivo, conteos, mapeadas) for ejecutivo in _ejecutivos(metas, cartera)],
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
        for row in _gestiones(periodo)[0]
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
