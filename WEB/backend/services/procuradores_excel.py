"""Excel de procuradores con el formato de la planilla del concurso (CONCURSO PROCURADORES).

Hoja CUMPLIMIENTOS: resumen con el % final por procurador y, debajo, una tabla por cartera con META, AVANCE
y %CUMPL de cada variable. Los % son formulas, asi que se puede corregir un avance a mano en el Excel.
Luego una hoja por gestion del CRM con su detalle.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from openpyxl import Workbook

from services.excel_formato import AZUL, BLANCA, CELESTE, MONEDA, NARANJO, NEGRITA, PCT
from services.excel_formato import celda as _celda
from services.excel_formato import col as _col
from services.excel_formato import semaforo as _semaforo
from services.procuradores_service import AUTOMATICAS, ETIQUETAS, MANUALES, TOPE_CUMPLIMIENTO, get_detalle, get_general


ORDEN = AUTOMATICAS + MANUALES
TITULOS = {
    "notificaciones": "NOTIFICACION",
    "embargos": "EMBARGOS",
    "oficios": "OFICIOS",
    "incautaciones": "INCAUTACIONES",
    "recupero": "RECUP. CASTIGO",
    "gestion_judicial": "GESTION JUDICIAL",
}
# Recupero va en MM$ y gestion judicial en %, como en la planilla.
FORMATOS = {"recupero": MONEDA, "gestion_judicial": 'General"%"'}
HOJAS_DETALLE = ("embargos", "oficios", "notificaciones", "incautaciones")


def _bloques(cartera: dict) -> list[dict]:
    """Procuradores de la cartera agrupados por variables y pesos: cada grupo es una tabla.
    Solo entran las variables con meta (las demas no suman al cumplimiento)."""
    grupos: dict[tuple, list[dict]] = {}
    for fila in cartera["rows"]:
        firma = tuple(
            (v, fila["variables"][v]["peso"])
            for v in ORDEN
            if v in fila["variables"] and fila["variables"][v]["meta"] is not None
        )
        grupos.setdefault(firma, []).append(fila)
    return [{"pesos": dict(firma), "filas": filas} for firma, filas in grupos.items()]


def _tabla(ws, top: int, cartera: dict, bloque: dict, terminos: dict) -> int:
    """Escribe una tabla de cartera desde la fila top. Devuelve su ultima fila."""
    filas = bloque["filas"]
    n = len(filas)
    cab, sub, datos = top, top + 1, top + 2
    ultima = datos + n - 1

    _celda(ws, sub, 3, "PROCURADOR", font=BLANCA, fill=AZUL)
    _celda(ws, datos, 2, cartera["cartera"], hasta_fila=ultima)
    for k, fila in enumerate(filas):
        _celda(ws, datos + k, 3, fila["ejecutivo"], font=NEGRITA)

    for i, (variable, peso) in enumerate(bloque["pesos"].items()):
        c = 4 + 3 * i  # META, AVANCE, %CUMPL
        _celda(ws, cab, c, TITULOS[variable], font=BLANCA, fill=AZUL, hasta_col=c + 1)
        _celda(ws, cab, c + 2, peso, font=BLANCA, fill=AZUL, fmt=PCT)
        for j, titulo in enumerate(("META", "AVANCE", "%CUMPL")):
            _celda(ws, sub, c + j, titulo, font=BLANCA, fill=AZUL)

        # Meta grupal: una sola celda para todos los procuradores de la tabla.
        grupal = n > 1 and all(f["variables"][variable]["grupal"] for f in filas)
        peso_ref = f"${_col(c + 2)}${cab}"
        for k, fila in enumerate(filas):
            r = datos + k
            if not (grupal and k):
                dato = fila["variables"][variable]
                hasta = ultima if grupal else None
                fmt = FORMATOS.get(variable)
                _celda(ws, r, c, dato["meta"], fill=CELESTE, fmt=fmt, hasta_fila=hasta)
                _celda(ws, r, c + 1, dato["logro"], fill=NARANJO, fmt=fmt, hasta_fila=hasta)
                formula = f"=IFERROR(MIN({_col(c + 1)}{r}/{_col(c)}{r},{TOPE_CUMPLIMIENTO}),0)"
                _celda(ws, r, c + 2, formula, font=NEGRITA, fmt=PCT, hasta_fila=hasta)
            pct_ref = f"{_col(c + 2)}{datos if grupal else r}"
            terminos[(cartera["cartera"], fila["ejecutivo"])].append(f"{pct_ref}*{peso_ref}")
        ws.conditional_formatting.add(f"{_col(c + 2)}{datos}:{_col(c + 2)}{ultima}", _semaforo())
    return ultima


def _hoja_cumplimientos(ws, general: dict) -> None:
    ws.title = "CUMPLIMIENTOS"
    ws.sheet_view.showGridLines = False
    carteras = [c for c in general["carteras"] if c["rows"]]
    terminos = {(c["cartera"], f["ejecutivo"]): [] for c in carteras for f in c["rows"]}

    # Tablas por cartera, debajo del resumen.
    fila = 2 + len(terminos) + 4
    for cartera in carteras:
        for bloque in _bloques(cartera):
            if bloque["pesos"]:
                fila = _tabla(ws, fila, cartera, bloque, terminos) + 2
        fila += 1

    # Resumen: % final = suma de %CUMPL x peso de cada procurador.
    _celda(ws, 2, 3, "PROCURADOR", font=BLANCA, fill=AZUL, hasta_col=4)
    _celda(ws, 2, 5, "% CUMPLIMIENTO FINAL", font=BLANCA, fill=AZUL, hasta_col=6)
    r = 3
    for cartera in carteras:
        _celda(ws, r, 2, cartera["cartera"], hasta_fila=r + len(cartera["rows"]) - 1)
        for f in cartera["rows"]:
            formula = "=" + ("+".join(terminos[(cartera["cartera"], f["ejecutivo"])]) or "0")
            _celda(ws, r, 3, f["ejecutivo"], font=NEGRITA, hasta_col=4)
            _celda(ws, r, 5, formula, font=NEGRITA, fmt=PCT, hasta_col=6)
            r += 1
    if r > 3:
        ws.conditional_formatting.add(f"E3:E{r - 1}", _semaforo())

    ws.column_dimensions["A"].width = 4.5
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 30
    for c in range(4, 4 + 3 * len(ORDEN)):
        ws.column_dimensions[_col(c)].width = 12


def _operacion(op):
    texto = str(op or "").strip()
    return int(texto) if texto.isdigit() and len(texto) <= 15 else texto


def _hoja_detalle(wb, variable: str, filas: list[dict]) -> None:
    ws = wb.create_sheet(ETIQUETAS[variable].upper())
    ws.append(["GESTION", "MANDANTE", "OP", "USUARIO", "TRIBUNAL", "FECHA GESTIÓN"])
    for fila in filas:
        ws.append([
            fila["gestion"],
            fila["cartera"],
            _operacion(fila["op"]),
            fila["usuario"],
            fila["tribunal"],
            datetime.fromisoformat(fila["fecha"]) if fila["fecha"] else None,
        ])
        ws.cell(row=ws.max_row, column=3).number_format = "0"
        ws.cell(row=ws.max_row, column=6).number_format = "dd-mm-yyyy"
    for cell in ws[1]:
        cell.font = NEGRITA
    ws.freeze_panes = "A2"

    for col, width in zip("ABCDEF", (14, 22, 16, 38, 34, 14)):
        ws.column_dimensions[col].width = width


def build_excel(periodo: str | None) -> tuple[BytesIO, str]:
    general = get_general({"periodo": periodo})
    detalle = get_detalle({"periodo": general["periodo"]})

    wb = Workbook()
    _hoja_cumplimientos(wb.active, general)
    for variable in HOJAS_DETALLE:
        _hoja_detalle(wb, variable, [f for f in detalle if f["variable"] == variable])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output, f"Procuradores_{general['periodo']}.xlsx"
