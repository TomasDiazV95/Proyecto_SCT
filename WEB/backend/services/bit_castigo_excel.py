"""Excel de Banco Internacional Castigo con el formato del de procuradores.

Hoja CUMPLIMIENTOS: una tabla por ejecutivo con META, AVANCE y %CUMPL del recupero, la base del % efectividad,
los nuevos convenios con su abono inicial y la base del % cobertura. Los % son formulas, asi que se puede
corregir un valor a mano. Luego una hoja por medible con su detalle por RUT. La fila grupal Phoenix no va, salvo en la hoja RECUPERO,
que trae todo el recupero del mes (el de RUT sin ejecutiva como SIN EJECUTIVA).
"""
from __future__ import annotations

from openpyxl import Workbook

from services.bit_castigo_service import get_detalle, get_general, get_nuevos_convenios
from services.excel_formato import (
    CELESTE, ENTERO, MONEDA, NARANJO, PCT, PCT2, TITULO,
    anchos_cumplimiento, guardar, hoja_detalle, ratio, sin_phoenix, tabla_cumplimiento, valor,
)


TOPE_CUMPLIMIENTO = 1.3
SIN_EJECUTIVA = "SIN EJECUTIVA"


def _grupos(meta: float, hay_cobertura: bool) -> list[tuple[str, list[dict]]]:
    return [
        # La meta es del periodo, la misma para cada ejecutivo. El % total es el promedio de los ejecutivos,
        # igual que en la pagina.
        ("RECUP. CASTIGO", [
            valor("META", "meta", MONEDA, CELESTE, total=meta),
            valor("AVANCE", "monto_contenido", MONEDA, NARANJO),
            ratio("%CUMPL", 1, 0, PCT, tope=TOPE_CUMPLIMIENTO, si_cero=0, total="promedio"),
        ]),
        ("EFECTIVIDAD", [
            valor("ASIGNADO", "monto_asignado", MONEDA),
            valor("RECUP. ASIG.", "recupero_asignado", MONEDA),
            ratio("%EFECT.", 1, 0, PCT2),
        ]),
        ("NUEVOS CONVENIOS", [
            valor("N° CONVENIOS", "nuevos_convenios", ENTERO),
            valor("ABONO INICIAL", "abono_inicial", MONEDA),
        ]),
        # Base de la cobertura: RUT carterizados. Si el CRM no tiene gestiones desde el inicio del mes, no se mide.
        ("COBERTURA 4° DÍA HÁBIL", [
            valor("RUT CART.", "ruts_asignados", ENTERO),
            valor("RUT GEST.", "ruts_gestionados", ENTERO),
            ratio("%COBERT.", 1, 0, PCT, fijo=None if hay_cobertura else "N/D"),
        ]),
    ]


def _si_no(valor_bool: bool) -> str:
    return "SI" if valor_bool else "NO"


def _orden(fila: dict) -> tuple:
    return (fila["ejecutivo"], fila["rut"])


def _ejecutiva_recupero(fila: dict) -> str:
    """En la hoja RECUPERO va todo el recupero del mes: el de RUT sin ejecutiva (Phoenix) como SIN EJECUTIVA."""
    return SIN_EJECUTIVA if str(fila["ejecutivo"] or "").strip().upper() == "PHOENIX" else fila["ejecutivo"]


def build_excel(periodo: str | None) -> tuple:
    general = get_general({"periodo": periodo})
    filtros = {"periodo": general["periodo"]}
    meta = general["meta"] or 0
    hay_cobertura = general["total"]["pct_cobertura"] is not None

    wb = Workbook()
    ws = wb.active
    ws.title = "CUMPLIMIENTOS"
    ws.sheet_view.showGridLines = False
    ws.cell(row=1, column=2, value="BANCO INTERNACIONAL CASTIGO").font = TITULO
    filas = sorted(({**f, "meta": meta} for f in sin_phoenix(general["rows"])), key=lambda f: f["ejecutivo"])
    if filas:
        tabla_cumplimiento(ws, 3, "CARTERA", "CASTIGO", filas, _grupos(meta, hay_cobertura))
    anchos_cumplimiento(ws)

    detalle = get_detalle(filtros)
    hoja_detalle(
        wb, "RECUPERO",
        [("EJECUTIVO", 28, None), ("RUT", 13, None), ("DEUDA", 16, MONEDA), ("RECUPERO", 15, MONEDA),
         ("NUEVO CONVENIO", 15, None), ("ABONO INICIAL", 15, MONEDA)],
        [
            [_ejecutiva_recupero(f), f["rut"], f["deuda"], f["recupero"], _si_no(f["nuevos_convenios"]), f["abono_inicial"]]
            for f in sorted(
                detalle["recupero"],
                key=lambda f: (_ejecutiva_recupero(f) == SIN_EJECUTIVA, _ejecutiva_recupero(f), f["rut"]),
            )
        ],
    )
    hoja_detalle(
        wb, "ASIGNACION",
        [("EJECUTIVO", 28, None), ("RUT", 13, None), ("EN ASIGNACIÓN", 14, None), ("DEUDA ASIGNADA", 16, MONEDA),
         ("RECUPERO ASIG.", 15, MONEDA), ("CARTERIZADO", 13, None), ("GESTIONADO", 12, None)],
        [
            [f["ejecutivo"], f["rut"], _si_no(f["en_asignacion"]), f["monto_asignado"], f["recupero_asignado"],
             _si_no(f["carterizado"]), _si_no(f["gestionado"])]
            for f in sorted(sin_phoenix(detalle["asignacion"]), key=_orden)
        ],
    )
    hoja_detalle(
        wb, "NUEVOS CONVENIOS",
        [("EJECUTIVO", 28, None), ("RUT", 13, None), ("OPERACIONES", 30, None), ("DEUDA CASTIGADA", 16, MONEDA),
         ("ABONO INICIAL", 15, MONEDA)],
        [
            [f["ejecutivo"], f["rut"], ", ".join(f["operaciones"]), f["deuda"], f["abono_inicial"]]
            for f in sorted(sin_phoenix(get_nuevos_convenios(filtros)), key=_orden)
        ],
    )
    return guardar(wb), f"BIT_Castigo_{general['periodo']}.xlsx"
