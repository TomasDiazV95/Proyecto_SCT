"""Excel de Banco Internacional Vigente con el formato del de procuradores.

Hoja CUMPLIMIENTOS: tabla principal con el cumplimiento final de cada ejecutivo y sus negocios (refinanciamiento
PC20, renegociacion PC07); debajo, el detalle de como se llega a ese cumplimiento: por tramo (30-90 y 90+)
MTO INICIAL, CONTENIDO, %CONT., META % (meta de contencion), %CUMPL y PONDERA. Los % son formulas que leen el detalle, asi que se puede
corregir un valor o una ponderacion a mano. Luego el detalle por operacion de la contencion
y de los negocios. La fila grupal Phoenix no va.
"""
from __future__ import annotations

from openpyxl import Workbook

from services.bit_service import TRAMOS, get_detalle, get_general, get_negocios, get_negocios_detalle
from services.excel_formato import (
    AZUL, BLANCA, CELESTE, ENTERO, MONEDA, NARANJO, PCT, PCT2, TITULO,
    anchos_cumplimiento, celda, columnas_grupos, formula, guardar, hoja_detalle, ratio, sin_phoenix,
    tabla_cumplimiento, valor,
)


TOPE_CUMPLIMIENTO = 1.3
NEGOCIOS = (("refinanciamiento", "REFINANC. (PC20)"), ("renegociacion", "RENEGOC. (PC07)"))


def _titulo_tramo(tramo: str) -> str:
    return f"TRAMO {tramo}"


def _cumplimiento_tramo(tramo: str):
    """%CUMPL = % contencion / meta % (con tope). Sin meta o sin cartera en el tramo: N/D."""
    titulo = _titulo_tramo(tramo)

    def fn(ref, r: int) -> str:
        ini, cont, meta = (f"{ref(titulo, sub)}{r}" for sub in ("MTO INICIAL", "CONTENIDO", "META %"))
        return f'=IF(OR(N({meta})=0,N({ini})=0),"N/D",MIN({cont}/{ini}/{meta},{TOPE_CUMPLIMIENTO}))'
    return fn


def _grupos_detalle(ponderaciones: dict[str, float], metas_pct: dict[str, float | None]) -> list[tuple[str, list[dict]]]:
    # La meta del tramo es un % de contencion sobre el monto inicial (la misma para todas sus operaciones).
    return [
        (_titulo_tramo(tramo), [
            valor("MTO INICIAL", f"{tramo}_inicial", MONEDA),
            valor("CONTENIDO", f"{tramo}_contenido", MONEDA, NARANJO),
            ratio("%CONT.", 1, 0, PCT2),
            valor("META %", f"{tramo}_meta_pct", PCT2, CELESTE, total=metas_pct[tramo] or 0),
            formula("%CUMPL", PCT, _cumplimiento_tramo(tramo)),
            valor("PONDERA", f"{tramo}_pondera", PCT, CELESTE, total=ponderaciones[tramo]),
        ])
        for tramo in TRAMOS
    ]


def _cumplimiento_final(ref_detalle, desfase: int):
    """%CUMPL de cada tramo por su PONDERA, leidos del cuadro de detalle (misma fila + desfase). Un tramo sin
    meta queda en N/D y su ponderacion se reparte en el otro, igual que en la pagina."""
    def fn(_ref, r: int) -> str:
        fila = r + desfase
        partes = [
            (f"{ref_detalle(_titulo_tramo(t), '%CUMPL')}{fila}", f"{ref_detalle(_titulo_tramo(t), 'PONDERA')}{fila}")
            for t in TRAMOS
        ]
        numerador = "+".join(f"IF(ISNUMBER({c}),{c}*{p},0)" for c, p in partes)
        pesos = "+".join(f"IF(ISNUMBER({c}),{p},0)" for c, p in partes)
        return f'=IFERROR(({numerador})/({pesos}),"N/D")'
    return fn


def _grupos_principal(ref_detalle, desfase: int) -> list[tuple[str, list[dict]]]:
    return [
        ("CUMPLIMIENTO", [formula("% FINAL", PCT, _cumplimiento_final(ref_detalle, desfase))]),
        ("NEGOCIOS", [
            *(valor(etiqueta, f"neg_{key}", ENTERO) for key, etiqueta in NEGOCIOS),
            valor("TOTAL", "neg_total", ENTERO),
        ]),
    ]


def _filas(general: dict, negocios: dict, ponderaciones: dict[str, float], metas_pct: dict) -> list[dict]:
    """Una fila plana por ejecutivo con los montos de cada tramo y la cantidad de negocios."""
    filas: dict[str, dict] = {}
    for row in sin_phoenix(general["rows"]):
        fila = filas.setdefault(row["ejecutivo"], {"ejecutivo": row["ejecutivo"]})
        for tramo in TRAMOS:
            datos = row["tramos"][tramo]
            fila[f"{tramo}_inicial"] = datos["monto_inicial"]
            fila[f"{tramo}_contenido"] = datos["monto_contenido"]
            fila[f"{tramo}_meta_pct"] = metas_pct[tramo]
    for row in sin_phoenix(negocios["rows"]):
        fila = filas.setdefault(row["ejecutivo"], {"ejecutivo": row["ejecutivo"]})
        for key, _ in NEGOCIOS:
            fila[f"neg_{key}"] = row[key]["cantidad"]
        fila["neg_total"] = row["total"]["cantidad"]
    for fila in filas.values():
        for tramo in TRAMOS:
            fila.setdefault(f"{tramo}_pondera", ponderaciones[tramo])
            fila.setdefault(f"{tramo}_meta_pct", metas_pct[tramo])
    return [filas[nombre] for nombre in sorted(filas)]


def _rut(row: dict) -> str:
    rut = str(row.get("rut") or "").strip()
    dv = str(row.get("dv") or "").strip()
    return f"{rut}-{dv}" if rut and dv else rut


def build_excel(periodo: str | None) -> tuple:
    periodo = str(periodo or "").strip()
    if not periodo:
        raise RuntimeError("Falta el periodo")
    filtros = {"periodo": periodo}
    general = get_general(filtros)
    ponderaciones = {m["tramo"]: m["ponderacion"] for m in general["metas"]}
    metas_pct = {m["tramo"]: m["meta"] for m in general["metas"]}

    wb = Workbook()
    ws = wb.active
    ws.title = "CUMPLIMIENTOS"
    ws.sheet_view.showGridLines = False
    ws.cell(row=1, column=2, value="BANCO INTERNACIONAL VIGENTE").font = TITULO
    filas = _filas(general, get_negocios(filtros), ponderaciones, metas_pct)
    if filas:
        # Tabla principal arriba y cuadro de detalle debajo, con los ejecutivos en el mismo orden: la fila de
        # cada ejecutivo en el detalle es su fila en la principal + desfase.
        principal = 3
        titulo_detalle = principal + len(filas) + 5
        detalle_top = titulo_detalle + 1
        grupos_detalle = _grupos_detalle(ponderaciones, metas_pct)
        tabla_cumplimiento(
            ws, principal, "CARTERA", "VIGENTE", filas,
            _grupos_principal(columnas_grupos(grupos_detalle), detalle_top - principal),
        )
        ancho = 3 + sum(len(specs) for _, specs in grupos_detalle)
        celda(ws, titulo_detalle, 2, "DETALLE CUMPLIMIENTO FINAL", font=BLANCA, fill=AZUL, hasta_col=ancho)
        tabla_cumplimiento(ws, detalle_top, "CARTERA", "VIGENTE", filas, grupos_detalle)
    anchos_cumplimiento(ws, 20)

    # Solo las operaciones con tramo: son las que suman en la vista general.
    operaciones = [r for r in get_detalle(filtros)["rows"] if r.get("tramo") in TRAMOS]
    hoja_detalle(
        wb, "CONTENCION",
        [("EJECUTIVO", 28, None), ("RUT", 13, None), ("OPERACIÓN", 18, None), ("TRAMO", 9, None),
         ("MTO INICIAL", 15, MONEDA), ("CONTENIDO", 15, MONEDA), ("CONTIENE", 11, None), ("META %", 10, PCT2),
         ("TIPO CONT.", 12, None)],
        [
            [r["ejecutivo"], _rut(r), str(r.get("con_no") or "").strip(), r["tramo"], r["mto_inicial"],
             r["mto_contenido"], "SI" if r.get("contiene") else "NO", metas_pct.get(r["tramo"]),
             str(r.get("tipo_cont") or "").strip()]
            for r in sorted(sin_phoenix(operaciones), key=lambda r: (r["ejecutivo"], r["tramo"], str(r.get("con_no") or "")))
        ],
    )
    hoja_detalle(
        wb, "NEGOCIOS",
        [("EJECUTIVO", 28, None), ("OPERACIÓN", 18, None), ("PRODUCTO", 8, None), ("TIPO", 18, None)],
        [
            [f["ejecutivo"], f["operacion"], f["producto"], f["producto_nombre"]]
            for f in sin_phoenix(get_negocios_detalle(filtros)["filas"])
        ],
    )
    return guardar(wb), f"BIT_Vigente_{periodo}.xlsx"
