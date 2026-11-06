"""Excel de Itau Castigo con el formato del de procuradores.

Hoja CUMPLIMIENTOS: una tabla por cobrador (Phoenix / Phoenix MCV) con META, AVANCE y %CUMPL del recupero y
la base de cada indicador (efectividad, cobertura, contencion cruce vigente). Los % son formulas, asi que se
puede corregir un valor a mano. Debajo, los nuevos convenios.
Luego una hoja por medible con su detalle por RUT u operacion. La fila grupal PHOENIX no va en el informe.
"""
from __future__ import annotations

from datetime import date, datetime

from openpyxl import Workbook

from services.excel_formato import (
    AZUL, BLANCA, CELESTE, ENTERO, FECHA, GRIS, MONEDA, NARANJO, NEGRITA, PCT, PCT2, TITULO,
    anchos_cumplimiento, celda, guardar, hoja_detalle, ratio, sin_phoenix, tabla_cumplimiento, valor,
)
from services.itau_castigo_service import (
    get_asignacion_detalle, get_cruce_detalle, get_general, get_nuevos_convenios,
    get_recupero_detalle,
)


TOPE_CUMPLIMIENTO = 1.3
COBRADORES = ("Phoenix", "Phoenix MCV")


def _grupos(cobrador: str, filas: list[dict]) -> list[tuple[str, list[dict]]]:
    # Igual que la pagina: Phoenix muestra el efectivo recuperado stock; Phoenix MCV, la contencion cruce vigente.
    # La meta es del cobrador: en el total va una sola vez, no la suma de las filas.
    meta_cobrador = next((f["meta_cobrador"] for f in filas if f.get("meta_cobrador")), 0)
    grupos = [
        ("RECUP. CASTIGO", [
            valor("META", "meta_recupero", MONEDA, CELESTE, total=meta_cobrador or "suma"),
            valor("AVANCE", "recupero_meta", MONEDA, NARANJO),
            ratio("%CUMPL", 1, 0, PCT, tope=TOPE_CUMPLIMIENTO, si_cero=0),
        ]),
    ]
    if cobrador != "Phoenix MCV":
        grupos.append(("EFECTIVO RECUP. STOCK", [valor("RECUPERO", "recupero_total", MONEDA)]))
    grupos += [
        ("EFECTIVIDAD", [
            valor("ASIGNADO", "monto_asignado", MONEDA),
            valor("RECUP. ASIG.", "recupero_asignado", MONEDA),
            ratio("%EFECT.", 1, 0, PCT2),
        ]),
        ("COBERTURA 4° DÍA HÁBIL", [
            valor("RUT ASIG.", "ruts_asignados", ENTERO),
            valor("RUT GEST.", "ruts_gestionados", ENTERO),
            ratio("%COBERT.", 1, 0, PCT),
        ]),
    ]
    if cobrador == "Phoenix MCV":
        grupos.append(("CONTENCIÓN CRUCE VIGENTE", [
            valor("SALDO INI.", "cruce_saldo_ini", MONEDA),
            valor("SALDO CONT.", "cruce_saldo_cont", MONEDA),
            ratio("%CONT.", 1, 0, PCT2),
        ]))
    return grupos


def _tabla_convenios(ws, top: int, convenios: dict) -> int:
    mes = _mes(convenios["periodo"])
    celda(ws, top, 2, f"NUEVOS CONVENIOS {mes}", font=BLANCA, fill=AZUL, hasta_col=5)
    if not convenios["asignacion_siguiente_cargada"]:
        ws.cell(row=top + 1, column=2, value=(
            f"Aún no se carga la asignación de castigo de {_mes(convenios['periodo_siguiente'])}: "
            f"los nuevos convenios de {mes} se ven cuando esté cargada."
        ))
        return top + 1
    celda(ws, top + 1, 2, "EJECUTIVO", font=BLANCA, fill=AZUL, hasta_col=3)
    celda(ws, top + 1, 4, "N° CONVENIOS", font=BLANCA, fill=AZUL)
    celda(ws, top + 1, 5, "ABONO INICIAL", font=BLANCA, fill=AZUL)
    r = top + 2
    for fila in sin_phoenix(convenios["rows"]):
        celda(ws, r, 2, fila["ejecutivo"], font=NEGRITA, hasta_col=3)
        celda(ws, r, 4, fila["nuevos_convenios"], fill=NARANJO, fmt=ENTERO)
        celda(ws, r, 5, fila["abono_inicial"], fill=NARANJO, fmt=MONEDA)
        r += 1
    celda(ws, r, 2, "TOTAL", font=NEGRITA, fill=GRIS, hasta_col=3)
    celda(ws, r, 4, f"=SUM(D{top + 2}:D{r - 1})" if r > top + 2 else 0, font=NEGRITA, fill=GRIS, fmt=ENTERO)
    celda(ws, r, 5, f"=SUM(E{top + 2}:E{r - 1})" if r > top + 2 else 0, font=NEGRITA, fill=GRIS, fmt=MONEDA)
    return r


def _mes(periodo: str | None) -> str:
    return datetime.fromisoformat(periodo).strftime("%m-%Y") if periodo else "N/D"


def _fecha(valor) -> date | None:
    """Fechas del banco ('20260805'), ISO ('2026-08-05') o datetime."""
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()[:10]
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            pass
    return None


def _hoja_cumplimientos(ws, general: dict, convenios: dict) -> None:
    ws.title = "CUMPLIMIENTOS"
    ws.sheet_view.showGridLines = False
    ws.cell(row=1, column=2, value="ITAÚ CASTIGO").font = TITULO

    fila = 3
    for cobrador in COBRADORES:
        filas = sorted(
            (r for r in sin_phoenix(general["rows"]) if r["cobrador_vista"].upper() == cobrador.upper()),
            key=lambda r: r["ejecutivo"],
        )
        if filas:
            fila = tabla_cumplimiento(ws, fila, "COBRADOR", cobrador, filas, _grupos(cobrador, filas)) + 3
    _tabla_convenios(ws, fila, convenios)
    anchos_cumplimiento(ws)


def _orden_detalle(fila: dict) -> tuple:
    return (fila.get("cobrador_vista", ""), fila["ejecutivo"], fila["rut"], fila.get("operacion", ""))


def build_excel(fecha_carga: str | None) -> tuple:
    filtros = {"fecha_carga": fecha_carga}
    general = get_general(filtros)
    filtros = {"fecha_carga": general["fecha_carga"]}
    convenios = get_nuevos_convenios(filtros)

    wb = Workbook()
    _hoja_cumplimientos(wb.active, general, convenios)

    hoja_detalle(
        wb, "RECUPERO",
        [("EJECUTIVO", 28, None), ("COBRADOR_VISTA", 16, None), ("EJECUTIVO META", 28, None), ("COBRADOR META", 16, None),
         ("RUT", 13, None), ("NOMBRE", 36, None), ("DEUDA", 15, MONEDA), ("RECUPERO", 15, MONEDA), ("FECHA RECUPERO", 15, FECHA)],
        [
            [f["ejecutivo"], f["cobrador_vista"], f["ejecutivo_meta"], f["cobrador_meta"], f["rut"], f["nombre"],
             f["deuda"], f["recupero"], _fecha(f["fecha_recupero"])]
            for f in sorted(sin_phoenix(get_recupero_detalle(filtros)), key=_orden_detalle)
        ],
    )
    hoja_detalle(
        wb, "ASIGNACION",
        [("EJECUTIVO", 28, None), ("COBRADOR_VISTA", 16, None), ("RUT", 13, None), ("NOMBRE", 36, None),
         ("MONTO ASIGNADO", 16, MONEDA), ("RECUPERO", 15, MONEDA), ("GESTIONADO", 12, None), ("PRIMERA GESTIÓN", 16, FECHA)],
        [
            [f["ejecutivo"], f["cobrador_vista"], f["rut"], f["nombre"], f["monto_asignado"], f["recupero"],
             "SI" if f["gestionado"] else "NO", _fecha(f["primera_gestion"])]
            for f in sorted(sin_phoenix(get_asignacion_detalle(filtros)), key=_orden_detalle)
        ],
    )
    hoja_detalle(
        wb, "CRUCE VIGENTE",
        [("EJECUTIVO", 28, None), ("COBRADOR_VISTA", 16, None), ("RUT", 13, None), ("OPERACIÓN", 20, None),
         ("SALDO INICIAL", 16, MONEDA), ("SALDO CONTENIDO", 16, MONEDA)],
        [
            [f["ejecutivo"], f["cobrador_vista"], f["rut"], f["operacion"], f["saldo_ini"], f["saldo_cont"]]
            for f in sorted(sin_phoenix(get_cruce_detalle(filtros)), key=_orden_detalle)
        ],
    )
    hoja_detalle(
        wb, "NUEVOS CONVENIOS",
        [("EJECUTIVO", 28, None), ("RUT", 13, None), ("NOMBRE", 36, None), ("COBRADOR_VISTA", 16, None),
         ("SALDO CASTIGADO", 16, MONEDA), ("ABONO INICIAL", 15, MONEDA)],
        [
            [f["ejecutivo"], f["rut"], f["nombre"], f["cobrador_vista"], f["saldo_castigado"], f["abono_inicial"]]
            for f in sin_phoenix(convenios["detalle"])
        ],
    )
    return guardar(wb), f"Itau_Castigo_{general['fecha_carga']}.xlsx"
