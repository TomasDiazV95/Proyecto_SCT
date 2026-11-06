"""Estilos y helpers de los Excel de productividad (formato de la planilla del concurso de procuradores).

Hoja de cumplimientos con tablas de META / AVANCE / %CUMPL (los % son formulas) y hojas de detalle planas.
"""
from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


AZUL = PatternFill("solid", fgColor="0F4761")
CELESTE = PatternFill("solid", fgColor="CAEDFB")  # meta
NARANJO = PatternFill("solid", fgColor="F7C7AC")  # avance
GRIS = PatternFill("solid", fgColor="D9D9D9")  # fila total
BLANCA = Font(bold=True, color="FFFFFF")
NEGRITA = Font(bold=True)
TITULO = Font(bold=True, size=14, color="0F4761")
LINEA = Side(style="thin")
BORDE = Border(left=LINEA, right=LINEA, top=LINEA, bottom=LINEA)
CENTRO = Alignment(horizontal="center", vertical="center", wrap_text=True)

PCT = "0%"
PCT2 = "0.00%"
MONEDA = '_ "$"* #,##0_ ;_ "$"* \\-#,##0_ ;_ "$"* "-"_ ;_ @_ '
ENTERO = "#,##0"
FECHA = "dd-mm-yyyy"


def semaforo() -> ColorScaleRule:
    return ColorScaleRule(
        start_type="min", start_color="F8696B",
        mid_type="percentile", mid_value=50, mid_color="FFEB84",
        end_type="max", end_color="63BE7B",
    )


def col(n: int) -> str:
    return get_column_letter(n)


def celda(ws, fila: int, columna: int, valor=None, *, font=None, fill=None, fmt=None, hasta_fila=None, hasta_col=None):
    """Escribe una celda con borde; si se pide, la combina hasta (hasta_fila, hasta_col)."""
    hasta_fila, hasta_col = hasta_fila or fila, hasta_col or columna
    for r in range(fila, hasta_fila + 1):
        for c in range(columna, hasta_col + 1):
            cell = ws.cell(row=r, column=c)
            cell.border = BORDE
            cell.alignment = CENTRO
            if fill:
                cell.fill = fill
    cell = ws.cell(row=fila, column=columna, value=valor)
    if font:
        cell.font = font
    if fmt:
        cell.number_format = fmt
    if (hasta_fila, hasta_col) != (fila, columna):
        ws.merge_cells(start_row=fila, start_column=columna, end_row=hasta_fila, end_column=hasta_col)


def hoja_detalle(wb: Workbook, titulo: str, columnas: list[tuple[str, int, str | None]], filas: list[list]) -> None:
    """Hoja plana: columnas = [(encabezado, ancho, formato)], una lista de valores por fila."""
    ws = wb.create_sheet(titulo[:31])
    ws.append([nombre for nombre, _, _ in columnas])
    for fila in filas:
        ws.append(fila)
    for i, (_, ancho, fmt) in enumerate(columnas, start=1):
        ws.column_dimensions[col(i)].width = ancho
        if fmt:
            for (cell,) in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                cell.number_format = fmt
    for cell in ws[1]:
        cell.font = BLANCA
        cell.fill = AZUL
        cell.alignment = CENTRO
    ws.freeze_panes = "A2"
    if filas:
        ws.auto_filter.ref = f"A1:{col(len(columnas))}{len(filas) + 1}"


def guardar(wb: Workbook) -> BytesIO:
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output


# Tabla de cumplimientos: columnas agrupadas bajo un titulo (RECUP. CASTIGO, EFECTIVIDAD...). Cada columna es un
# valor (dato de la fila) o un ratio (formula entre dos columnas del mismo grupo).

def valor(sub: str, key: str, fmt: str, fill=None, *, total="suma") -> dict:
    """total: "suma" (SUM de las filas) o un valor fijo, p. ej. la meta que es una sola para todo el grupo."""
    return {"sub": sub, "tipo": "valor", "key": key, "fmt": fmt, "fill": fill, "total": total}


def ratio(sub: str, num: int, den: int, fmt: str, *, tope: float | None = None, si_cero="N/D", total="ratio", fijo=None) -> dict:
    """Formula num/den; num y den son la posicion de la columna dentro del grupo.
    total: "ratio" (misma formula sobre los totales) o "promedio" (promedio de las filas).
    fijo: texto en vez de formula, p. ej. "N/D" cuando el indicador no se puede medir."""
    return {"sub": sub, "tipo": "ratio", "num": num, "den": den, "fmt": fmt, "tope": tope, "si_cero": si_cero,
            "total": total, "fijo": fijo}


def formula(sub: str, fmt: str, fn) -> dict:
    """Formula libre entre columnas de cualquier grupo: fn(ref, fila) devuelve la formula, con
    ref(titulo_grupo, sub) = letra de esa columna. En la fila TOTAL se aplica la misma formula."""
    return {"sub": sub, "tipo": "formula", "fn": fn, "fmt": fmt}


def _formula_ratio(spec: dict, inicio: int, r: int) -> str:
    num, den = f"{col(inicio + spec['num'])}{r}", f"{col(inicio + spec['den'])}{r}"
    division = f"{num}/{den}"
    if spec["tope"] is not None:
        division = f"MIN({division},{spec['tope']})"
    si_cero = f'"{spec["si_cero"]}"' if isinstance(spec["si_cero"], str) else spec["si_cero"]
    return f"=IF(N({den})=0,{si_cero},{division})"


def columnas_grupos(grupos: list[tuple[str, list[dict]]]):
    """ref(titulo_grupo, sub) = letra de esa columna en la tabla (los grupos parten en la columna D)."""
    posiciones: dict[tuple[str, str], int] = {}
    c = 4
    for titulo_grupo, specs in grupos:
        for j, spec in enumerate(specs):
            posiciones[(titulo_grupo, spec["sub"])] = c + j
        c += len(specs)
    return lambda titulo_grupo, sub_col: col(posiciones[(titulo_grupo, sub_col)])


def tabla_cumplimiento(ws, top: int, titulo: str, etiqueta: str, filas: list[dict], grupos: list[tuple[str, list[dict]]]) -> int:
    """Tabla desde la fila top: columna B = titulo (p. ej. COBRADOR) con la etiqueta combinada, C = EJECUTIVO,
    luego los grupos y una fila TOTAL. Devuelve la fila del total."""
    cab, sub, datos = top, top + 1, top + 2
    ultima = datos + len(filas) - 1
    total = ultima + 1

    celda(ws, cab, 2, titulo, font=BLANCA, fill=AZUL, hasta_fila=sub)
    celda(ws, cab, 3, "EJECUTIVO", font=BLANCA, fill=AZUL, hasta_fila=sub)
    celda(ws, datos, 2, etiqueta, font=NEGRITA, hasta_fila=total)
    for k, fila in enumerate(filas):
        celda(ws, datos + k, 3, fila["ejecutivo"], font=NEGRITA)
    celda(ws, total, 3, "TOTAL", font=NEGRITA, fill=GRIS)

    rango = lambda c: f"{col(c)}{datos}:{col(c)}{ultima}"
    ref = columnas_grupos(grupos)

    c = 4
    for titulo_grupo, specs in grupos:
        celda(ws, cab, c, titulo_grupo, font=BLANCA, fill=AZUL, hasta_col=c + len(specs) - 1)
        for j, spec in enumerate(specs):
            columna = c + j
            celda(ws, sub, columna, spec["sub"], font=BLANCA, fill=AZUL)
            for k, fila in enumerate(filas):
                r = datos + k
                if spec["tipo"] == "valor":
                    celda(ws, r, columna, fila.get(spec["key"]) or 0, fill=spec["fill"], fmt=spec["fmt"])
                elif spec["tipo"] == "formula":
                    celda(ws, r, columna, spec["fn"](ref, r), font=NEGRITA, fmt=spec["fmt"])
                else:
                    celda(ws, r, columna, spec["fijo"] or _formula_ratio(spec, c, r), font=NEGRITA, fmt=spec["fmt"])
            if spec["tipo"] == "valor":
                valor_total = f"=SUM({rango(columna)})" if spec["total"] == "suma" else spec["total"]
            elif spec["tipo"] == "formula":
                valor_total = spec["fn"](ref, total)
            elif spec["fijo"]:
                valor_total = spec["fijo"]
            elif spec["total"] == "promedio":
                valor_total = f"=IFERROR(AVERAGE({rango(columna)}),0)"
            else:
                valor_total = _formula_ratio(spec, c, total)
            celda(ws, total, columna, valor_total, font=NEGRITA, fill=GRIS, fmt=spec["fmt"])
            if (spec["tipo"] == "formula" or spec.get("tope") is not None) and filas:
                ws.conditional_formatting.add(rango(columna), semaforo())
        c += len(specs)
    return total


def anchos_cumplimiento(ws, columnas: int = 18) -> None:
    ws.column_dimensions["A"].width = 3
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 30
    for c in range(4, columnas):
        ws.column_dimensions[col(c)].width = 15


def sin_phoenix(filas) -> list[dict]:
    """La fila grupal PHOENIX (RUT sin ejecutivo) no va en los informes."""
    return [f for f in filas if str(f.get("ejecutivo") or "").strip().upper() != "PHOENIX"]
