"""Excel de Caja La Araucana con el formato del de procuradores.

Hoja CUMPLIMIENTOS: por ejecutivo el RECUPERO (todas las carteras sumadas) y el % aporte final (recupero de
la ejecutiva sobre el recupero total). Debajo, los negocios (reprogramaciones) por tramo de deuda (desde octubre
2026 solo el total). Los % son formulas, asi que se puede corregir un valor a mano. Luego el detalle de pagos
(con el codigo del tipo de pago y la gestion que se lo lleva) y de negocios. La deuda asignada no va, ni la fila
grupal Phoenix.
"""
from __future__ import annotations

from openpyxl import Workbook

from services.la_araucana_service import (
    APORTE_SOLO_EJECUTIVOS_DESDE, TRAMO_DEUDA_NEGOCIO, get_detalle_excel, get_negocios, get_resumen,
)
from services.excel_formato import (
    ENTERO, FECHA, MONEDA, NARANJO, PCT2, TITULO,
    anchos_cumplimiento, formula, guardar, hoja_detalle, sin_phoenix, tabla_cumplimiento, valor,
)


GRUPO = "LA ARAUCANA"
TRAMOS_NEGOCIO = (("MENOR", f"DEUDA ≤ ${TRAMO_DEUDA_NEGOCIO:,.0f}".replace(",", ".")),
                  ("MAYOR", f"DEUDA > ${TRAMO_DEUDA_NEGOCIO:,.0f}".replace(",", ".")))


def _aporte_final(fila_total: int):
    """Recupero de la ejecutiva (todas las carteras) sobre el recupero total (fila TOTAL)."""
    def fn(ref, r: int) -> str:
        rec = ref(GRUPO, "RECUPERO")
        return f"=IF(N({rec}${fila_total})=0,0,{rec}{r}/{rec}${fila_total})"
    return fn


def _grupos(fila_total: int, total_recupero: float | None) -> list[tuple[str, list[dict]]]:
    # Antes de APORTE_SOLO_EJECUTIVOS_DESDE el aporte se calculaba sobre el recupero incluyendo Phoenix: en ese
    # caso el TOTAL de recupero es el de toda la cartera y no la suma de las ejecutivas.
    return [
        (GRUPO, [
            valor("RECUPERO", "recupero", MONEDA, NARANJO, total="suma" if total_recupero is None else total_recupero),
            formula("% APORTE FINAL", PCT2, _aporte_final(fila_total)),
        ]),
    ]


def _grupos_negocios(con_tramos: bool) -> list[tuple[str, list[dict]]]:
    return [
        *(
            (titulo, [valor("N° REPROG.", f"{tramo}_q", ENTERO), valor("RECUPERO", f"{tramo}_recupero", MONEDA)])
            for tramo, titulo in (TRAMOS_NEGOCIO if con_tramos else ())
        ),
        ("TOTAL", [valor("N° REPROG.", "total_q", ENTERO), valor("RECUPERO", "total_recupero", MONEDA)]),
    ]


def _filas_resumen(rows: list[dict]) -> list[dict]:
    """Una fila por ejecutivo con el recupero sumado de todas las carteras."""
    filas: dict[str, dict] = {}
    for row in sin_phoenix(rows):
        fila = filas.setdefault(row["ejecutivo"], {"ejecutivo": row["ejecutivo"], "recupero": 0.0})
        fila["recupero"] += float(row["recupero"] or 0)
    return [filas[nombre] for nombre in sorted(filas)]


def _filas_negocios(rows: list[dict]) -> list[dict]:
    filas: dict[str, dict] = {}
    for row in sin_phoenix(rows):
        fila = filas.setdefault(row["ejecutivo"], {"ejecutivo": row["ejecutivo"], "total_q": 0, "total_recupero": 0})
        fila[f"{row['tramo_deuda']}_q"] = fila.get(f"{row['tramo_deuda']}_q", 0) + row["q_negocios"]
        fila[f"{row['tramo_deuda']}_recupero"] = fila.get(f"{row['tramo_deuda']}_recupero", 0) + row["recupero"]
        fila["total_q"] += row["q_negocios"]
        fila["total_recupero"] += row["recupero"]
    return [filas[nombre] for nombre in sorted(filas)]


def build_excel(periodo: str | None) -> tuple:
    periodo = str(periodo or "").strip()
    if not periodo:
        raise RuntimeError("Falta el periodo")
    resumen = get_resumen({"periodo": periodo})
    negocios = get_negocios({"periodo": periodo})
    detalle = get_detalle_excel(periodo)
    mes = detalle["period_month"]

    wb = Workbook()
    ws = wb.active
    ws.title = "CUMPLIMIENTOS"
    ws.sheet_view.showGridLines = False
    ws.cell(row=1, column=2, value="CAJA LA ARAUCANA").font = TITULO

    fila = 3
    filas = _filas_resumen(resumen["rows"])
    if filas:
        total_recupero = None
        if mes < APORTE_SOLO_EJECUTIVOS_DESDE:
            total_recupero = sum(float(row["recupero"] or 0) for row in resumen["rows"])
        fila_total = fila + 2 + len(filas)
        fila = tabla_cumplimiento(ws, fila, "CARTERA", "LA ARAUCANA", filas, _grupos(fila_total, total_recupero)) + 3
    con_tramos = negocios.get("con_tramos", True)
    filas_neg = _filas_negocios(negocios["rows"])
    if filas_neg:
        tabla_cumplimiento(ws, fila, "NEGOCIOS", "REPROGRAMACIÓN", filas_neg, _grupos_negocios(con_tramos))
    anchos_cumplimiento(ws, 15)

    hoja_detalle(
        wb, "RECUPERO",
        [("EJECUTIVO", 28, None), ("FOLIO", 16, None), ("RUT", 13, None), ("CARTERA", 10, None),
         ("FECHA PAGO", 12, FECHA), ("CÓDIGO TIPO PAGO", 17, None), ("RECUPERO", 15, MONEDA), ("CRITERIO", 27, None),
         ("USUARIO GESTIÓN", 22, None), ("FECHA GESTIÓN", 14, FECHA), ("HORA GESTIÓN", 12, None),
         ("ACCIÓN", 16, None), ("CONTACTO", 20, None), ("RESPUESTA", 34, None), ("OBSERVACIÓN", 60, None)],
        [
            [p["ejecutivo"], p["contrato"], p["rut"], p["tipo_cartera"], p["fecha_pago"], p["tipo_pago"], p["recupero"],
             p["criterio"], p["usuario"], p["fecha_gestion"], p["hora_gestion"], p["accion"], p["contacto"],
             p["respuesta"], p["observacion"]]
            for p in sin_phoenix(detalle["pagos"])
        ],
    )
    tramos = dict(TRAMOS_NEGOCIO)
    # La deuda del folio solo se muestra en los meses con tramos, donde define el tramo del negocio.
    columnas_neg = [("EJECUTIVO", 28, None), ("FOLIO", 16, None), ("RUT", 13, None), ("CARTERA", 10, None),
                    ("FECHA NEGOCIO", 14, FECHA)]
    if con_tramos:
        columnas_neg.append(("DEUDA", 15, MONEDA))
    columnas_neg.append(("RECUPERO", 15, MONEDA))
    if con_tramos:
        columnas_neg.append(("TRAMO DEUDA", 22, None))
    hoja_detalle(
        wb, "NEGOCIOS",
        columnas_neg,
        [
            [n["ejecutivo"], n["contrato"], n["rut"], n["tipo_cartera"], n["fecha_pago"]]
            + ([n["deuda"]] if con_tramos else [])
            + [n["recupero"]]
            + ([tramos.get(n["tramo_deuda"], n["tramo_deuda"])] if con_tramos else [])
            for n in sorted(sin_phoenix(negocios["detalle"]), key=lambda n: (n["ejecutivo"], str(n["fecha_pago"]), n["contrato"]))
        ],
    )
    periodo_archivo = f"{mes[5:7]}-{mes[:4]}"
    return guardar(wb), f"La_Araucana_{periodo_archivo}.xlsx"
