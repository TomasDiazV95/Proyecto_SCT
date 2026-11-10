"""Excel de Santander Consumer Temprana con el formato del de procuradores.

Hoja CUMPLIMIENTOS: por ejecutiva y tramo (C1, C2 y C3 cuando el tramo tiene mas de 350 casos) la DEUDA ASIG., el
MONTO CONT., el % contenido y el % cumplimiento (aporte de la ejecutiva al contenido del tramo). Debajo, los
negocios del mes por tipo. Los % son formulas, asi que se puede corregir un valor a mano. Luego el detalle por
operacion de la contencion y de los negocios. Sin Phoenix ni operaciones sin ejecutiva. En la contencion, la columna
FPD marca las operaciones de la base FPD del mes, que no suman al cumplimiento.
"""
from __future__ import annotations

from openpyxl import Workbook

from services.excel_formato import (
    ENTERO, FECHA, MONEDA, NARANJO, PCT2, TITULO,
    anchos_cumplimiento, formula, guardar, hoja_detalle, ratio, sin_phoenix, tabla_cumplimiento, valor,
)
from services.negocios_service import SIN_EJECUTIVO, get_conteo, get_detalle as get_negocios_detalle
from services.sc_temprana_service import _normalize_period, _period_version, get_cycle_view, get_detalle_excel


NEGOCIO = "sc-telefonia"
# Igual que la pagina: el tramo C3 solo se mide cuando tiene mas de 350 casos en el bench.
MIN_CASOS_C3 = 350


def _cumplimiento(tramo: str, fila_total: int):
    """Monto contenido de la ejecutiva sobre el contenido total del tramo (fila TOTAL)."""
    def fn(ref, r: int) -> str:
        cont = ref(f"TRAMO {tramo}", "MONTO CONT.")
        return f"=IF(N({cont}${fila_total})=0,0,{cont}{r}/{cont}${fila_total})"
    return fn


def _grupos(tramos: list[str], fila_total: int) -> list[tuple[str, list[dict]]]:
    return [
        (f"TRAMO {tramo}", [
            valor("DEUDA ASIG.", f"{tramo.lower()}_deuda_asignada", MONEDA),
            valor("MONTO CONT.", f"{tramo.lower()}_monto_cont", MONEDA, NARANJO),
            ratio("%CONT.", 1, 0, PCT2),
            formula("%CUMPL.", PCT2, _cumplimiento(tramo, fila_total)),
        ])
        for tramo in tramos
    ]


def _sin_ejecutivo(filas: list[dict]) -> list[dict]:
    return [f for f in sin_phoenix(filas) if f["ejecutivo"] != SIN_EJECUTIVO]


def build_excel(periodo: str | None) -> tuple:
    periodo = str(periodo or "").strip()
    if not periodo:
        raise RuntimeError("Falta el periodo")
    ciclo = get_cycle_view({"periodo": periodo})
    total = next((r for r in ciclo if r["ejecutivo"] == "Total"), {})
    tramos = ["C1", "C2"] + (["C3"] if int(total.get("c3_casos_base") or 0) > MIN_CASOS_C3 else [])
    claves = [f"{t.lower()}_{k}" for t in tramos for k in ("deuda_asignada", "monto_cont")]
    # Solo las ejecutivas con cartera en los tramos medidos.
    filas = sorted(
        (r for r in ciclo if r["ejecutivo"] != "Total" and any(r.get(k) for k in claves)),
        key=lambda r: r["ejecutivo"],
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "CUMPLIMIENTOS"
    ws.sheet_view.showGridLines = False
    ws.cell(row=1, column=2, value="SANTANDER CONSUMER TEMPRANA").font = TITULO

    fila = 3
    if filas:
        fila_total = fila + 2 + len(filas)
        fila = tabla_cumplimiento(ws, fila, "CARTERA", "TEMPRANA", filas, _grupos(tramos, fila_total)) + 3

    conteo = get_conteo(NEGOCIO, periodo)
    filas_neg = sorted(
        ({"ejecutivo": f["ejecutivo"], **f["conteos"], "total": f["total"]} for f in _sin_ejecutivo(conteo["filas"])),
        key=lambda f: f["ejecutivo"],
    )
    if filas_neg:
        tabla_cumplimiento(ws, fila, "NEGOCIOS", "TEMPRANA", filas_neg, [
            ("NEGOCIOS", [
                *(valor(p["nombre"].upper(), p["codigo"], ENTERO) for p in conteo["productos"]),
                valor("TOTAL", "total", ENTERO),
            ]),
        ])
    anchos_cumplimiento(ws, 3 + 4 * len(tramos) + 1)

    operaciones = sorted(
        get_detalle_excel(periodo),
        key=lambda r: (r["ejecutivo"], r["tramo"], -float(r["deuda"] or 0), str(r["operacion"])),
    )
    hoja_detalle(
        wb, "CONTENCION",
        [("EJECUTIVO", 24, None), ("OPERACIÓN", 16, None), ("RUT", 12, None), ("TRAMO", 8, None),
         ("DEUDA ASIG.", 15, MONEDA), ("MONTO CONT.", 15, MONEDA), ("CONTENIDO", 11, None), ("NORMALIZADO", 13, None),
         ("USUARIO GESTIÓN", 17, None), ("RESPUESTA GESTIÓN", 34, None), ("FECHA GESTIÓN", 14, FECHA),
         ("TELÉFONO", 13, None), ("FPD", 7, None)],
        [
            [r["ejecutivo"], r["operacion"], r["rut"], r["tramo"], r["deuda"], r["monto_contenido"],
             "SI" if r["contenido"] else "NO", "SI" if r["normalizado"] else "NO", r["usuario_gestion"],
             r["respuesta_gestion"], r["gestion_fecha"], r["telefono"], "SI" if r["fpd"] else "NO"]
            for r in operaciones if r["tramo"] in tramos
        ],
    )
    hoja_detalle(
        wb, "NEGOCIOS",
        [("EJECUTIVO", 24, None), ("OPERACIÓN", 18, None), ("TIPO", 18, None)],
        [[f["ejecutivo"], f["operacion"], f["producto_nombre"]] for f in _sin_ejecutivo(get_negocios_detalle(NEGOCIO, periodo)["filas"])],
    )

    foto = _normalize_period(periodo).replace("-", "")
    sufijo = "_precierre" if _period_version(periodo) == "PRECIERRE" else ""
    return guardar(wb), f"SC_Temprana_{foto}{sufijo}.xlsx"
