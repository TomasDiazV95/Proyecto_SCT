"""Excel de Itau Vigente con el formato del de procuradores.

Hoja CUMPLIMIENTOS: tabla principal con el cumplimiento de cada ejecutivo por variable (Consumo, Hipotecario y,
en los meses que lo llevan, Castigo), el % FINAL ponderado y, desde octubre 2026, el % aporte y la cobertura de
gestion. Debajo, el DETALLE CUMPLIMIENTO: una tabla por producto con los saldos de cada fase (META $ = saldo
inicial x meta de la fase) y el %CUMPL del producto (contenido / meta $, tope 130%), y la del castigo. La tabla
principal lee esos cuadros con formulas, asi que se puede corregir un valor o una ponderacion a mano.
En los meses con meta grupal todos los ejecutivos llevan el %CUMPL de la fila TOTAL.
Luego una hoja por medible con su detalle. La fila grupal PHOENIX no va en el informe.
"""
from __future__ import annotations

from openpyxl import Workbook

from services.excel_formato import (
    AZUL, BLANCA, CELESTE, ENTERO, FECHA, MONEDA, NARANJO, PCT, PCT2, TITULO,
    anchos_cumplimiento, celda, col, columnas_grupos, formula, guardar, hoja_detalle, ratio, sin_phoenix,
    tabla_cumplimiento, valor,
)
from services.itau_castigo_excel import _fecha
from services.itau_vigente_service import (
    CUMPLIMIENTO_MAX, PRODUCTOS, get_contencion_detalle, get_efectivo_detalle, get_general, get_negocios,
    get_recupero_castigo_detalle,
)


TOP = 3
CUMPL = "CUMPLIMIENTO"
CASTIGO = "CASTIGO"
NOMBRE_PRODUCTO = {"CONSUMO": "CONSUMO", "HIPOTECARIO": "HIPOTECARIO"}


def _total_producto(producto: str) -> str:
    return f"TOTAL {NOMBRE_PRODUCTO[producto]}"


def _metas_producto(metas: list[dict], producto: str) -> tuple[list[tuple[int, float]], float]:
    """([(fase, meta)], ponderacion) del producto en el mes."""
    propias = sorted((m for m in metas if m["producto"] == producto), key=lambda m: m["fase"])
    return [(m["fase"], m["meta_contencion"]) for m in propias], (propias[0]["ponderacion"] if propias else 0.0)


def _cumpl_grupal(total: int, num: str, den: str, si_cero="0"):
    """%CUMPL de la fila TOTAL en todas las filas (meta grupal): MIN(num/den, tope) de esa fila."""
    def fn(ref, _r: int) -> str:
        n, d = f"{ref(*num)}{total}", f"{ref(*den)}{total}"
        return f"=IF(N({d})=0,{si_cero},MIN({n}/{d},{CUMPLIMIENTO_MAX}))"
    return fn


def _grupos_producto(producto: str, fases: list[tuple[int, float]], pond: float, grupal: bool, total: int):
    key = producto.lower()
    grupos = [
        (f"FASE {fase} · META {round(meta * 100, 2):g}%", [
            valor("SALDO INI.", f"f{fase}_{key}_saldo_ini", MONEDA),
            valor("CONTENIDO", f"f{fase}_{key}_saldo_cont", MONEDA, NARANJO),
            valor("META $", f"f{fase}_{key}_meta_monto", MONEDA, CELESTE),
        ])
        for fase, meta in fases
    ]
    titulo = _total_producto(producto)
    cumplimiento = (
        formula("%CUMPL", PCT, _cumpl_grupal(total, (titulo, "CONTENIDO"), (titulo, "META $"), '"N/D"'))
        if grupal else ratio("%CUMPL", 1, 2, PCT, tope=CUMPLIMIENTO_MAX)
    )
    grupos.append((titulo, [
        valor("SALDO INI.", f"{key}_saldo_ini", MONEDA),
        valor("CONTENIDO", f"{key}_saldo_cont", MONEDA, NARANJO),
        valor("META $", f"{key}_meta_monto", MONEDA, CELESTE),
        cumplimiento,
        valor("POND.", "pond", PCT, CELESTE, total=pond),
    ]))
    return grupos


def _grupos_castigo(castigo: dict, total: int):
    return [(CASTIGO, [
        valor("RECUPERO", "castigo_recupero", MONEDA, NARANJO),
        valor("META GRUPAL", "castigo_meta", MONEDA, CELESTE, total=castigo["meta"]),
        # El castigo es grupal: todos llevan el recupero de la suma de los ejecutivos sobre la meta.
        formula("%CUMPL GRUPAL", PCT, _cumpl_grupal(total, (CASTIGO, "RECUPERO"), (CASTIGO, "META GRUPAL"))),
        valor("POND.", "pond", PCT, CELESTE, total=castigo["ponderacion"]),
    ])]


def _filas_producto(rows: list[dict], producto: str, pond: float) -> list[dict]:
    key = producto.lower()
    filas = []
    for row in rows:
        fila = {
            "ejecutivo": row["ejecutivo"],
            "pond": pond,
            **{f"{key}_{campo}": row[f"{key}_{campo}"] for campo in ("saldo_ini", "saldo_cont", "meta_monto")},
        }
        for fase in row["fases"]:
            for campo in ("saldo_ini", "saldo_cont", "meta_monto"):
                fila[f"f{fase['fase']}_{key}_{campo}"] = fase[f"{key}_{campo}"]
        filas.append(fila)
    return filas


def _hoja_cumplimientos(ws, general: dict, negocios: dict) -> None:
    ws.title = "CUMPLIMIENTOS"
    ws.sheet_view.showGridLines = False
    ws.cell(row=1, column=2, value="ITAÚ VIGENTE").font = TITULO

    # Cantidad de negocios (renegociaciones) de cada ejecutivo: la misma consulta de la hoja NEGOCIOS.
    conteo = {r["ejecutivo"]: r["negocios"] for r in negocios["rows"]}
    rows = [{**r, "negocios": conteo.get(r["ejecutivo"], 0)} for r in sin_phoenix(general["rows"])]
    n = len(rows)
    grupal = bool(general.get("meta_grupal"))
    castigo = general.get("castigo")

    # Cuadros del detalle (debajo de la principal): su posicion se calcula antes para que la principal los lea.
    titulo_detalle = TOP + 2 + n + 3
    top = titulo_detalle + 1
    detalle = []  # (etiqueta, filas, grupos, top, nombre del grupo con %CUMPL y POND.)
    for producto in PRODUCTOS:
        fases, pond = _metas_producto(general["metas"], producto)
        if fases:
            grupos = _grupos_producto(producto, fases, pond, grupal, top + 2 + n)
            detalle.append((producto, _filas_producto(rows, producto, pond), grupos, top, _total_producto(producto)))
            top += 2 + n + 1 + 3
    if castigo:
        filas = [
            {"ejecutivo": r["ejecutivo"], "castigo_recupero": r.get("castigo_recupero") or 0,
             "castigo_meta": castigo["meta"], "pond": castigo["ponderacion"]}
            for r in rows
        ]
        detalle.append((CASTIGO, filas, _grupos_castigo(castigo, top + 2 + n), top, CASTIGO))

    # Celdas %CUMPL y POND. de cada cuadro en la fila equivalente a la r de la principal.
    def celdas(item, r: int) -> tuple[str, str]:
        _, _, grupos, t, grupo = item
        ref = columnas_grupos(grupos)
        cumpl_sub = "%CUMPL GRUPAL" if grupo == CASTIGO else "%CUMPL"
        fila = r - TOP + t
        return f"{ref(grupo, cumpl_sub)}{fila}", f"{ref(grupo, 'POND.')}{fila}"

    def variable(item):
        return lambda _ref, r: f"={celdas(item, r)[0]}"

    def final(_ref, r: int) -> str:
        pares = [celdas(item, r) for item in detalle]
        num = "+".join(f"IF(ISNUMBER({x}),{x}*{p},0)" for x, p in pares)
        den = "+".join(f"IF(ISNUMBER({x}),{p},0)" for x, p in pares)
        return f'=IF(({den})=0,"N/D",({num})/({den}))' if pares else '="N/D"'

    principal = [(f"{CUMPL} GRUPAL" if grupal else CUMPL, [
        *(formula(item[0], PCT, variable(item)) for item in detalle),
        formula("% FINAL", PCT, final),
    ])]
    if general.get("con_aporte_cobertura"):
        cont_total = TOP + 2 + n

        def aporte(ref, r: int) -> str:
            c = ref("% APORTE", "CONTENIDO")
            return f"=IF(N({c}{cont_total})=0,0,{c}{r}/{c}{cont_total})"

        cobertura = (general.get("cobertura_gestion") or {}).get("pct")
        principal += [
            ("% APORTE", [valor("CONTENIDO", "saldo_cont", MONEDA, NARANJO), formula("%APORTE", PCT2, aporte)]),
            ("COBERTURA GESTIÓN", [valor("%COBERT. GRUPAL", "cobertura_gestion", PCT2, total=cobertura or 0)]),
        ]
    if general.get("efectivo_recuperado"):
        principal.append(("EFECTIVO RECUP. NO MEDIBLE", [valor("EFECTIVO", "recupero_nm_efectivo", MONEDA)]))
    principal.append(("NEGOCIOS", [valor("RENEGOCIACIONES", "negocios", ENTERO)]))

    tabla_cumplimiento(ws, TOP, "CARTERA", "ITAÚ VIGENTE", rows, principal)

    ancho = max([3 + sum(len(specs) for _, specs in grupos) for _, _, grupos, _, _ in detalle], default=0)
    if detalle:
        celda(ws, titulo_detalle, 2, "DETALLE CUMPLIMIENTO", font=BLANCA, fill=AZUL, hasta_col=ancho)
        for etiqueta, filas, grupos, t, _ in detalle:
            tabla_cumplimiento(ws, t, "VARIABLE", etiqueta, filas, grupos)
    columnas = max(ancho + 2, 3 + sum(len(specs) for _, specs in principal) + 2)
    anchos_cumplimiento(ws, columnas)
    # Los saldos totales llegan a decenas de miles de millones: no caben en el ancho estandar.
    for c in range(4, columnas):
        ws.column_dimensions[col(c)].width = 19


def build_excel(fecha_carga: str | None) -> tuple:
    general = get_general({"fecha_carga": fecha_carga})
    filtros = {"fecha_carga": general["fecha_carga"]}

    wb = Workbook()
    negocios = get_negocios(filtros)
    _hoja_cumplimientos(wb.active, general, negocios)

    hoja_detalle(
        wb, "CONTENCION",
        [("EJECUTIVO", 28, None), ("RUT", 12, None), ("NOMBRE", 36, None), ("OPERACIÓN", 26, None),
         ("PRODUCTO", 14, None), ("FASE", 7, None), ("CANAL", 34, None), ("MARCA", 22, None),
         ("SALDO INICIAL", 16, MONEDA), ("SALDO CONTENIDO", 16, MONEDA), ("META FASE", 11, PCT)],
        [
            [f["ejecutivo"], f["rut"], f["nombre"], f["operacion"], f["producto"], f["fase"], f["canal"], f["marca"],
             f["saldo_ini"], f["saldo_cont"], f["meta_pct"]]
            for f in sin_phoenix(get_contencion_detalle(filtros))
        ],
    )
    if general.get("castigo"):
        hoja_detalle(
            wb, "RECUPERO CASTIGO",
            [("EJECUTIVO", 28, None), ("RUT", 13, None), ("NOMBRE", 36, None), ("DEUDA", 15, MONEDA),
             ("RECUPERO", 15, MONEDA), ("FECHA RECUPERO", 15, FECHA)],
            [
                [f["ejecutivo"], f["rut"], f["nombre"], f["deuda"], f["recupero"], _fecha(f["fecha_recupero"])]
                for f in sin_phoenix(get_recupero_castigo_detalle(filtros)["filas"])
            ],
        )
    if general.get("efectivo_recuperado"):
        hoja_detalle(
            wb, "EFECTIVO RECUPERADO",
            [("EJECUTIVO", 28, None), ("OPERACIÓN", 26, None), ("RUT", 12, None), ("NOMBRE", 36, None),
             ("CUOTAS", 9, None), ("EFECTIVO", 15, MONEDA)],
            [
                [f["ejecutivo"], f["operacion"], f["rut"], f["nombre"], f["cuotas"], f["efectivo"]]
                for f in sin_phoenix(get_efectivo_detalle(filtros))
            ],
        )
    hoja_detalle(
        wb, "NEGOCIOS",
        # Los negocios de Itau son las renegociaciones del mes (desde octubre 2026, solo con saldo contenido).
        [("TIPO NEGOCIO", 16, None), ("EJECUTIVO", 28, None), ("RUT", 12, None), ("NOMBRE", 36, None),
         ("OPERACIÓN", 26, None), ("PRODUCTO", 14, None), ("FASE", 7, None)],
        [
            ["RENEGOCIACIÓN", f["ejecutivo"], f["rut"], f["nombre"], f["operacion"], f["producto"], f["fase"]]
            for f in sin_phoenix(negocios["detalle"])
        ],
    )
    return guardar(wb), f"Itau_Vigente_{general['fecha_carga']}.xlsx"
