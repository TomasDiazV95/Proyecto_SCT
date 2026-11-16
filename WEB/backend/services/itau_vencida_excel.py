"""Excel de Itau Vencida con el formato del de procuradores (mismo diseño que el de Itau Vigente).

Hoja CUMPLIMIENTOS: tabla principal con el cumplimiento de cada ejecutivo en Consumo e Hipotecario, el % FINAL
ponderado y la cobertura terreno (informativa, no pondera). Debajo, el DETALLE CUMPLIMIENTO: una tabla por producto
con los saldos de cada fase medible (META $ = saldo inicial x meta de la fase) y el %CUMPL del producto
(contenido / meta $, tope 130%). La tabla principal lee esos cuadros con formulas, asi que se puede corregir un valor
o una ponderacion a mano. El contenido es el valido: el RUT tuvo una gestion en el mes antes de pagar.
Luego una hoja por medible con su detalle. La fila PHOENIX (RUT sin carterizado) no va en el informe.
"""
from __future__ import annotations

from openpyxl import Workbook

from services.excel_formato import (
    AZUL, BLANCA, ENTERO, FECHA, MONEDA, PCT, TITULO,
    anchos_cumplimiento, celda, col, columnas_grupos, formula, guardar, hoja_detalle, ratio, sin_phoenix,
    tabla_cumplimiento, valor,
)
from services.itau_castigo_excel import _fecha
from services.itau_vencida_service import (
    PRODUCTOS, get_cobertura_detalle, get_contencion_detalle, get_general, get_negocios,
)
from services.itau_vigente_excel import CUMPL, TOP, _filas_producto, _grupos_producto, _metas_producto, _total_producto


def _hoja_cumplimientos(ws, general: dict, negocios: dict) -> None:
    ws.title = "CUMPLIMIENTOS"
    ws.sheet_view.showGridLines = False
    ws.cell(row=1, column=2, value="ITAÚ VENCIDA").font = TITULO

    # Cantidad de negocios (renegociaciones) de cada ejecutivo: la misma consulta de la hoja NEGOCIOS.
    conteo = {r["ejecutivo"]: r["negocios"] for r in negocios["rows"]}
    rows = [{**r, "negocios": conteo.get(r["ejecutivo"], 0)} for r in sin_phoenix(general["rows"])]
    n = len(rows)

    # Cuadros del detalle (debajo de la principal): su posicion se calcula antes para que la principal los lea.
    titulo_detalle = TOP + 2 + n + 3
    top = titulo_detalle + 1
    detalle = []  # (producto, filas, grupos, top)
    for producto in PRODUCTOS:
        fases, pond = _metas_producto(general["metas"], producto)
        if fases:
            grupos = _grupos_producto(producto, fases, pond, False, top + 2 + n)
            detalle.append((producto, _filas_producto(rows, producto, pond), grupos, top))
            top += 2 + n + 1 + 3

    def celdas(item, r: int) -> tuple[str, str]:
        """%CUMPL y POND. del cuadro del producto en la fila equivalente a la r de la principal."""
        producto, _, grupos, t = item
        ref = columnas_grupos(grupos)
        fila = r - TOP + t
        return f"{ref(_total_producto(producto), '%CUMPL')}{fila}", f"{ref(_total_producto(producto), 'POND.')}{fila}"

    def variable(item):
        return lambda _ref, r: f"={celdas(item, r)[0]}"

    def final(_ref, r: int) -> str:
        # Si el ejecutivo no tiene saldo con meta en un producto (N/D), su ponderacion se reparte en el otro.
        pares = [celdas(item, r) for item in detalle]
        num = "+".join(f"IF(ISNUMBER({x}),{x}*{p},0)" for x, p in pares)
        den = "+".join(f"IF(ISNUMBER({x}),{p},0)" for x, p in pares)
        return f'=IF(({den})=0,"N/D",({num})/({den}))' if pares else '="N/D"'

    meta_cobertura = general.get("meta_cobertura_terreno") or 0
    principal = [
        (CUMPL, [*(formula(item[0], PCT, variable(item)) for item in detalle), formula("% FINAL", PCT, final)]),
        (f"COBERTURA TERRENO · META {round(meta_cobertura * 100):g}%", [
            valor("RUT TERRENO", "cobertura_ruts", ENTERO),
            valor("RUT VISITADOS", "cobertura_cubiertos", ENTERO),
            ratio("%COBERT.", 1, 0, PCT),
        ]),
    ]
    principal.append(("NEGOCIOS", [valor("RENEGOCIACIONES", "negocios", ENTERO)]))
    tabla_cumplimiento(ws, TOP, "CARTERA", "ITAÚ VENCIDA", rows, principal)

    ancho = max([3 + sum(len(specs) for _, specs in grupos) for _, _, grupos, _ in detalle], default=0)
    if detalle:
        celda(ws, titulo_detalle, 2, "DETALLE CUMPLIMIENTO", font=BLANCA, fill=AZUL, hasta_col=ancho)
        for producto, filas, grupos, t in detalle:
            tabla_cumplimiento(ws, t, "VARIABLE", producto, filas, grupos)
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
         ("PRODUCTO", 14, None), ("FASE", 7, None), ("SALDO INICIAL", 16, MONEDA),
         ("SALDO CONT. BANCO", 17, MONEDA), ("SALDO CONT. VÁLIDO", 18, MONEDA), ("FECHA PAGO", 12, FECHA),
         ("PRIMERA GESTIÓN", 16, FECHA), ("META FASE", 11, PCT)],
        [
            [f["ejecutivo"], f["rut"], f["nombre"], f["operacion"], f["producto"], f["fase"], f["saldo_ini"],
             f["saldo_cont_banco"], f["saldo_cont"], _fecha(f["fecha_pago"]), _fecha(f["primera_gestion"]),
             f["meta_pct"]]
            for f in sin_phoenix(get_contencion_detalle(filtros))
        ],
    )
    hoja_detalle(
        wb, "COBERTURA TERRENO",
        [("EJECUTIVO", 28, None), ("RUT", 12, None), ("FECHA PAGO", 12, FECHA), ("PRIMERA VISITA", 15, FECHA),
         ("CUBIERTO", 10, None)],
        [
            [f["ejecutivo"], f["rut"], _fecha(f["fecha_pago"]), _fecha(f["primera_visita"]),
             "SI" if f["cubierto"] else "NO"]
            for f in sin_phoenix(get_cobertura_detalle(filtros))
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
    return guardar(wb), f"Itau_Vencida_{general['fecha_carga']}.xlsx"
