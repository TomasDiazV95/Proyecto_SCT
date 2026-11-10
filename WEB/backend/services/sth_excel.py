"""Excel de Santander Hipotecario con el formato del de procuradores.

Hoja CUMPLIMIENTOS: tabla principal con el cumplimiento de cada ejecutivo por producto, el producto trabajado y el
cumplimiento final. Debajo, un cuadro por producto con como se llega a ese cumplimiento: por ciclo DEUDA ASIG.,
SALDO CONT., %CONT., META %, %CUMPL. y PONDERA, y el % FINAL del producto. Los % son formulas que leen esos
cuadros, asi que se puede corregir un valor, una meta o una ponderacion a mano. Al final, los negocios del mes
por tipo. Luego el detalle por operacion y el de los negocios (por RUT).
La fila 'Grupal' (RUT sin ejecutivo, como Phoenix en las otras carteras) no va; si va el grupal que trabajan
ejecutivos con nombre (multiproducto desde octubre 2026).
"""
from __future__ import annotations

from openpyxl import Workbook

from services.excel_formato import (
    AZUL, BLANCA, CELESTE, ENTERO, MONEDA, NARANJO, PCT, PCT2, TITULO,
    anchos_cumplimiento, celda, columnas_grupos, formula, guardar, hoja_detalle, ratio, sin_phoenix, tabla_cumplimiento,
    valor,
)
from services.negocios_service import SIN_EJECUTIVO, get_conteo, get_detalle as get_negocios_detalle
from services.sth_service import (
    GENERAL_PRODUCT_ORDER, TRAMO_ORDER, _period_start, _reglas_multiproducto, get_detail_view, get_general_view,
    get_operaciones_excel,
)


TOPE_CUMPLIMIENTO = 1.3
NEGOCIO = "sth"
PRODUCTO_LABEL = {
    "hipotecario": "HIPOTECARIO",
    "consumo": "CONSUMO",
    "pyme": "PYME",
    "tarjeta": "TC",
    "multiproducto": "MULTIPRODUCTO",
}


def _es_grupal(nombre) -> bool:
    return str(nombre or "").strip().lower() == "grupal"


def _negocios_con_ejecutivo(filas: list[dict]) -> list[dict]:
    """Sin Phoenix, sin 'Grupal' y sin los negocios que el archivo no asigna a un ejecutivo."""
    return [f for f in sin_phoenix(filas) if f["ejecutivo"] != SIN_EJECUTIVO and not _es_grupal(f["ejecutivo"])]


def _cumplimiento_ciclo(titulo: str):
    """%CUMPL. = % contenido / meta %, con tope; sin meta o sin deuda en el ciclo: 0 (como en la pagina)."""
    def fn(ref, r: int) -> str:
        deuda, saldo, meta = (f"{ref(titulo, sub)}{r}" for sub in ("DEUDA ASIG.", "SALDO CONT.", "META %"))
        return f"=IF(OR(N({meta})=0,N({deuda})=0),0,MAX(0,MIN({saldo}/{deuda}/{meta},{TOPE_CUMPLIMIENTO})))"
    return fn


def _cumplimiento_final(titulos: list[str], datos: int, total: int, mayor_deuda: bool):
    """Por ejecutivo: suma de %CUMPL. x PONDERA de sus ciclos (con tope). Hipotecario hasta septiembre 2026: el
    %CUMPL. del ciclo con mas deuda. TOTAL: promedio de los ejecutivos ponderado por su deuda, como en la pagina."""
    def fn(ref, r: int) -> str:
        if r == total:
            rango = lambda c: f"{c}{datos}:{c}{total - 1}"
            deudas = [rango(ref(t, "DEUDA ASIG.")) for t in titulos]
            final = rango(ref("CUMPLIMIENTO", "% FINAL"))
            return f"=IFERROR(SUMPRODUCT({final},{'+'.join(deudas)})/SUM({','.join(deudas)}),0)"
        cumpl = [f"{ref(t, '%CUMPL.')}{r}" for t in titulos]
        if mayor_deuda and len(titulos) > 1:
            deudas = [f"{ref(t, 'DEUDA ASIG.')}{r}" for t in titulos]
            maximo = f"MAX({','.join(deudas)})"
            expr = cumpl[-1]
            for d, c in reversed(list(zip(deudas[:-1], cumpl[:-1]))):
                expr = f"IF({d}={maximo},{c},{expr})"
            return f"={expr}"
        suma = "+".join(f"{c}*{ref(t, 'PONDERA')}{r}" for c, t in zip(cumpl, titulos))
        return f"=MAX(0,MIN({suma},{TOPE_CUMPLIMIENTO}))"
    return fn


def _bloque(block: dict, top: int, multiproducto: bool) -> dict:
    """Filas y columnas del cuadro de un producto que empieza en la fila top."""
    pivot = [p for p in block["pivot_rows"] if not _es_grupal(p["ejecutivo"])]
    totales = {t["ciclo"]: t for t in block["totales_por_ciclo"]}
    ciclos = [c for c in block["ciclos"] if c in totales]
    titulos = [totales[c]["tramo"].upper() for c in ciclos]
    # Los integrantes de un grupal repiten la misma cartera: el total la cuenta una vez (la de la pagina).
    con_grupal = any(x.get("grupal") for p in pivot for x in p["ciclos"].values())

    filas = []
    for p in pivot:
        fila = {"ejecutivo": p["ejecutivo"]}
        for c in ciclos:
            dato = p["ciclos"].get(str(c)) or {}
            fila[f"c{c}_deuda"] = dato.get("deuda_asignada") or 0
            fila[f"c{c}_saldo"] = dato.get("saldo_contenido") or 0
            fila[f"c{c}_meta"] = (totales[c]["meta_contenido_pct"] or 0) / 100
            fila[f"c{c}_pondera"] = (totales[c]["ponderador_nivel_1_pct"] or 0) / 100
        filas.append(fila)

    datos = top + 2
    total = datos + len(filas)
    grupos = [
        (titulo, [
            valor("DEUDA ASIG.", f"c{c}_deuda", MONEDA, total=totales[c]["deuda_asignada"] if con_grupal else "suma"),
            valor("SALDO CONT.", f"c{c}_saldo", MONEDA, NARANJO,
                  total=totales[c]["saldo_contenido"] if con_grupal else "suma"),
            ratio("%CONT.", 1, 0, PCT2),
            valor("META %", f"c{c}_meta", PCT2, CELESTE, total=(totales[c]["meta_contenido_pct"] or 0) / 100),
            formula("%CUMPL.", PCT, _cumplimiento_ciclo(titulo)),
            valor("PONDERA", f"c{c}_pondera", PCT, CELESTE, total=(totales[c]["ponderador_nivel_1_pct"] or 0) / 100),
        ])
        for c, titulo in zip(ciclos, titulos)
    ]
    mayor_deuda = block["producto"] == "hipotecario" and not multiproducto
    grupos.append(("CUMPLIMIENTO", [formula("% FINAL", PCT, _cumplimiento_final(titulos, datos, total, mayor_deuda))]))
    columna_final = columnas_grupos(grupos)("CUMPLIMIENTO", "% FINAL")
    return {
        "producto": block["producto"],
        "top": top,
        "total": total,
        "filas": filas,
        "grupos": grupos,
        "con_grupal": con_grupal,
        "celda_final": {f["ejecutivo"]: f"{columna_final}{datos + i}" for i, f in enumerate(filas)},
        "celda_total": f"{columna_final}{total}",
    }


def _grupos_principal(productos: list[str], bloques: dict, filas: list[dict], datos: int, total: int, total_general: dict):
    def por_producto(producto: str):
        def fn(_ref, r: int) -> str:
            bloque = bloques.get(producto)
            if not bloque:
                return "-"
            if r == total:
                return f"={bloque['celda_total']}"
            celda_final = bloque["celda_final"].get(filas[r - datos]["ejecutivo"])
            return f"={celda_final}" if celda_final else "-"
        return fn

    def final(_ref, r: int):
        if r == total:
            return (total_general.get("cumplimiento_final") or 0) / 100
        fila = filas[r - datos]
        celda_final = bloques.get(fila["producto_trabajado"], {}).get("celda_final", {}).get(fila["ejecutivo"])
        return f"={celda_final}" if celda_final else 0

    return [
        ("CUMPLIMIENTO POR PRODUCTO", [formula(PRODUCTO_LABEL[p], PCT, por_producto(p)) for p in productos]),
        ("PRODUCTO TRABAJADO", [
            valor("PRODUCTO", "producto_label", None, total=""),
            valor("TRAMO", "tramo_trabajado", None, total=""),
            valor("DEUDA", "deuda_referencia", MONEDA, total=total_general.get("deuda_referencia") or 0),
        ]),
        ("CUMPLIMIENTO", [formula("% FINAL", PCT, final)]),
    ]


def build_excel(periodo: str | None) -> tuple:
    periodo = _period_start(periodo)
    filtros = {"periodo": periodo}
    multiproducto = _reglas_multiproducto(periodo)
    general = get_general_view(filtros)
    total_general = next((r for r in general if r["ejecutivo"] == "Total general"), {})
    filas = [
        {**r, "producto_label": PRODUCTO_LABEL.get(r["producto_trabajado"], r["producto_trabajado"])}
        for r in general
        if r["ejecutivo"] != "Total general" and not _es_grupal(r["ejecutivo"])
    ]
    detalle = get_detail_view(filtros)
    productos = [b["producto"] for b in detalle]

    wb = Workbook()
    ws = wb.active
    ws.title = "CUMPLIMIENTOS"
    ws.sheet_view.showGridLines = False
    ws.cell(row=1, column=2, value="SANTANDER HIPOTECARIO").font = TITULO

    # Primero se ubican los cuadros por producto (debajo de la tabla principal) para que las formulas de la
    # tabla principal apunten a sus celdas.
    principal = 3
    principal_total = principal + 2 + len(filas)
    fila = principal_total + 3
    bloques: dict[str, dict] = {}
    for block in detalle:
        bloque = _bloque(block, fila + 1, multiproducto)
        if not bloque["filas"]:
            continue
        bloque["titulo"] = fila
        bloques[block["producto"]] = bloque
        fila = bloque["total"] + 3

    if filas:
        tabla_cumplimiento(
            ws, principal, "CARTERA", "STH", filas,
            _grupos_principal(productos, bloques, filas, principal + 2, principal_total, total_general),
        )
    for producto, bloque in bloques.items():
        ancho = 3 + sum(len(specs) for _, specs in bloque["grupos"])
        celda(ws, bloque["titulo"], 2, f"DETALLE CUMPLIMIENTO {PRODUCTO_LABEL[producto]}", font=BLANCA, fill=AZUL, hasta_col=ancho)
        tabla_cumplimiento(ws, bloque["top"], "PRODUCTO", PRODUCTO_LABEL[producto], bloque["filas"], bloque["grupos"])

    # Negocios del mes por ejecutivo y tipo, debajo de los cuadros por producto.
    conteo = get_conteo(NEGOCIO, periodo)
    filas_neg = sorted(
        ({"ejecutivo": f["ejecutivo"], **f["conteos"], "total": f["total"]} for f in _negocios_con_ejecutivo(conteo["filas"])),
        key=lambda f: f["ejecutivo"],
    )
    if filas_neg:
        tabla_cumplimiento(ws, fila, "NEGOCIOS", "STH", filas_neg, [
            ("NEGOCIOS", [
                *(valor(p["nombre"].upper(), p["codigo"], ENTERO) for p in conteo["productos"]),
                valor("TOTAL", "total", ENTERO),
            ]),
        ])
    anchos_cumplimiento(ws, 24)

    # Operaciones de cada cuadro. Las del 'Grupal' solo donde lo trabajan ejecutivos con nombre.
    con_grupal = {p for p, b in bloques.items() if b["con_grupal"]}
    operaciones = [
        o for o in get_operaciones_excel(filtros)
        if o["producto"] in bloques and (not _es_grupal(o["ejecutivo"]) or o["producto"] in con_grupal)
    ]
    operaciones.sort(key=lambda o: (
        GENERAL_PRODUCT_ORDER.get(o["producto"], 99), TRAMO_ORDER.get(o["tramo"], 0), o["ejecutivo"], -o["deuda"],
        str(o["operacion"]),
    ))
    hoja_detalle(
        wb, "CONTENCION",
        [("PRODUCTO", 16, None), ("TRAMO", 14, None), ("EJECUTIVO", 24, None), ("RUT", 12, None), ("OPERACIÓN", 22, None),
         ("PRODUCTO CLIENTE", 16, None), ("CICLO", 8, None), ("DEUDA", 16, MONEDA), ("CONTENIDO", 11, None),
         ("SALDO CONT.", 16, MONEDA)],
        [
            [PRODUCTO_LABEL[o["producto"]], o["tramo"], "GRUPAL" if _es_grupal(o["ejecutivo"]) else o["ejecutivo"],
             o["rut"], o["operacion"], o["producto_cliente"], o["ciclo_bench"], o["deuda"],
             "SI" if o["contenido"] else "NO", o["saldo_contenido"]]
            for o in operaciones
        ],
    )
    hoja_detalle(
        wb, "NEGOCIOS",
        [("EJECUTIVO", 24, None), ("RUT", 14, None), ("TIPO", 18, None)],
        [[f["ejecutivo"], f["rut"], f["producto_nombre"]] for f in _negocios_con_ejecutivo(get_negocios_detalle(NEGOCIO, periodo)["filas"])],
    )
    return guardar(wb), f"STH_{periodo[:7]}.xlsx"
