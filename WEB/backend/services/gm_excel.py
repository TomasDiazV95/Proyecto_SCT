"""Excel de GM con el formato del de procuradores.

Hoja CUMPLIMIENTOS: tabla principal con el cumplimiento final de cada ejecutiva y sus negocios del mes; debajo, el
detalle de como se llega: una tabla por bucket con la contencion y la normalizacion (monto, %, META y POND.), el
%CUMPL del bucket y cuanto PONDERA ese bucket en el cumplimiento final de la ejecutiva. Los % son formulas, asi que
se puede corregir un valor, una meta o una ponderacion a mano. Luego los pagos por operacion y los negocios.
La fila grupal Phoenix no va.
"""
from __future__ import annotations

from openpyxl import Workbook

from services.excel_formato import (
    AZUL, BLANCA, CELESTE, ENTERO, MONEDA, NARANJO, PCT, PCT2, TITULO,
    anchos_cumplimiento, celda, columnas_grupos, formula, guardar, hoja_detalle, ratio, sin_phoenix,
    tabla_cumplimiento, valor,
)
from services.gm_service import BUCKET_ORDER, _period_start, get_cycle_view, get_monthly_export_rows
from services.negocios_service import SIN_EJECUTIVO, get_conteo, get_detalle as get_negocios_detalle


NEGOCIO = "gm"
TOPE_CUMPLIMIENTO = 1.3
CONT, NORM, CUMPL = "CONTENCIÓN", "NORMALIZACIÓN", "CUMPLIMIENTO"


def _pct_norm(ref, r: int) -> str:
    deuda, norm = f"{ref(CONT, 'DEUDA ASIG.')}{r}", f"{ref(NORM, 'NORMALIZADO')}{r}"
    return f"=IF(N({deuda})=0,0,{norm}/{deuda})"


def _cumplimiento_bucket(ref, r: int) -> str:
    """Igual que la pagina: cada variable es % real / meta (tope 130%) y se pondera; el total tambien topa en 130%."""
    def variable(grupo: str, pct: str) -> str:
        real, meta, pond = (f"{ref(grupo, sub)}{r}" for sub in (pct, "META", "POND."))
        return f"IF(N({meta})=0,0,MIN(N({real})/{meta},{TOPE_CUMPLIMIENTO}))*N({pond})"

    return f"=MIN({variable(CONT, '%CONT.')}+{variable(NORM, '%NORM.')},{TOPE_CUMPLIMIENTO})"


def _grupos_detalle(info: dict) -> list[tuple[str, list[dict]]]:
    """info: metas y ponderaciones del bucket (fracciones) y lo que pondera el bucket en el total."""
    return [
        (CONT, [
            valor("DEUDA ASIG.", "deuda", MONEDA),
            valor("CONTENIDO", "contenido", MONEDA, NARANJO),
            ratio("%CONT.", 1, 0, PCT2, si_cero=0),
            valor("META", "meta_c", PCT2, CELESTE, total=info["meta_c"]),
            valor("POND.", "pond_c", PCT, CELESTE, total=info["pond_c"]),
        ]),
        (NORM, [
            valor("NORMALIZADO", "normalizado", MONEDA, NARANJO),
            formula("%NORM.", PCT2, _pct_norm),
            valor("META", "meta_n", PCT2, CELESTE, total=info["meta_n"]),
            valor("POND.", "pond_n", PCT, CELESTE, total=info["pond_n"]),
        ]),
        (CUMPL, [
            formula("%CUMPL", PCT, _cumplimiento_bucket),
            valor("PONDERA", "pondera", PCT2, CELESTE, total=info["pondera"]),
        ]),
    ]


def _ponderas(rows: list[dict]) -> list[float]:
    """Peso de cada fila (bucket) en el cumplimiento final, igual que gm_service._cumpl_individual: los buckets se
    agrupan por su ponderador de tramo (sin ponderador cargado, todos pesan igual) y dentro del grupo pesa la deuda."""
    pesos = {r["bucket"]: r["ponderador_tramo_pct"] for r in rows if r.get("ponderador_tramo_pct") is not None} or None
    peso_de = [(pesos.get(r["bucket"], 0.0) if pesos else 100.0) for r in rows]
    deuda_grupo: dict[float, float] = {}
    for peso, r in zip(peso_de, rows):
        if peso and r["deuda_asignada"]:
            deuda_grupo[peso] = deuda_grupo.get(peso, 0.0) + float(r["deuda_asignada"])
    peso_total = sum(deuda_grupo)
    return [
        (peso / peso_total) * (float(r["deuda_asignada"]) / deuda_grupo[peso])
        if peso_total and peso in deuda_grupo and r["deuda_asignada"] else 0.0
        for peso, r in zip(peso_de, rows)
    ]


def _fila_detalle(r: dict, pondera: float) -> dict:
    deuda = float(r["deuda_asignada"] or 0)
    normalizado = float(r["saldo_normalizado"] or 0)
    # Meses con % normalizado informado a mano: el monto se ajusta para que el % de la tabla sea ese.
    if deuda and abs(normalizado / deuda * 100.0 - float(r["porcentaje_normalizado"] or 0)) > 0.01:
        normalizado = deuda * float(r["porcentaje_normalizado"] or 0) / 100.0
    return {
        "ejecutivo": r["ejecutivo"],
        "deuda": deuda,
        "contenido": float(r["saldo_contenido"] or 0),
        "normalizado": normalizado,
        "meta_c": r["meta_contencion_pct"] / 100.0,
        "pond_c": r["ponderador_contencion_pct"] / 100.0,
        "meta_n": r["meta_normalizacion_pct"] / 100.0,
        "pond_n": r["ponderador_normalizacion_pct"] / 100.0,
        "pondera": pondera,
    }


def _detalle_por_bucket(ciclo: list[dict]) -> list[tuple[str, list[dict], dict]]:
    """[(bucket, filas por ejecutiva, info del bucket)] sin Phoenix, en el orden de los buckets."""
    filas = sin_phoenix(ciclo)
    pondera: dict[int, float] = {}
    for ejecutivo in {r["ejecutivo"] for r in filas}:
        propias = [r for r in filas if r["ejecutivo"] == ejecutivo]
        for r, peso in zip(propias, _ponderas(propias)):
            pondera[id(r)] = peso

    # Lo que pondera cada bucket en el TOTAL: misma regla sobre la deuda total de cada bucket.
    totales = []
    for bucket in BUCKET_ORDER:
        del_bucket = [r for r in filas if r["bucket"] == bucket]
        if del_bucket:
            totales.append({
                "bucket": bucket,
                "deuda_asignada": sum(float(r["deuda_asignada"] or 0) for r in del_bucket),
                "ponderador_tramo_pct": del_bucket[0].get("ponderador_tramo_pct"),
            })
    pondera_total = {t["bucket"]: peso for t, peso in zip(totales, _ponderas(totales))}

    salida = []
    for bucket in BUCKET_ORDER:
        del_bucket = sorted((r for r in filas if r["bucket"] == bucket), key=lambda r: r["ejecutivo"])
        if not del_bucket:
            continue
        primera = del_bucket[0]
        info = {
            "meta_c": primera["meta_contencion_pct"] / 100.0,
            "pond_c": primera["ponderador_contencion_pct"] / 100.0,
            "meta_n": primera["meta_normalizacion_pct"] / 100.0,
            "pond_n": primera["ponderador_normalizacion_pct"] / 100.0,
            "pondera": pondera_total.get(bucket, 0.0),
        }
        salida.append((bucket, [_fila_detalle(r, pondera[id(r)]) for r in del_bucket], info))
    return salida


def _cumplimiento_final(ref_detalle, desde: int, hasta: int):
    """Promedio de los %CUMPL de los buckets de la ejecutiva, ponderado por su PONDERA (lee el cuadro de detalle).
    En la fila TOTAL toma las filas TOTAL de cada bucket."""
    ejec = f"$C${desde}:$C${hasta}"
    cumpl = f"${ref_detalle(CUMPL, '%CUMPL')}${desde}:${ref_detalle(CUMPL, '%CUMPL')}${hasta}"
    pond = f"${ref_detalle(CUMPL, 'PONDERA')}${desde}:${ref_detalle(CUMPL, 'PONDERA')}${hasta}"

    def fn(_ref, r: int) -> str:
        return f"=IFERROR(SUMPRODUCT(--({ejec}=$C{r}),{cumpl},{pond})/SUMIF({ejec},$C{r},{pond}),0)"
    return fn


def _sin_ejecutivo(filas: list[dict]) -> list[dict]:
    return [f for f in sin_phoenix(filas) if f["ejecutivo"] != SIN_EJECUTIVO]


def build_excel(periodo: str | None) -> tuple:
    periodo = _period_start(periodo)
    buckets = _detalle_por_bucket(get_cycle_view({"periodo": periodo, "ejecutivo": ""}))
    conteo = get_conteo(NEGOCIO, periodo)
    productos = conteo["productos"]

    # Tabla principal: una fila por ejecutiva con cartera o negocios en el mes.
    principal: dict[str, dict] = {}
    for _, filas, _ in buckets:
        for f in filas:
            principal.setdefault(f["ejecutivo"], {"ejecutivo": f["ejecutivo"]})
    for f in _sin_ejecutivo(conteo["filas"]):
        fila = principal.setdefault(f["ejecutivo"], {"ejecutivo": f["ejecutivo"]})
        fila.update(f["conteos"])
        fila["neg_total"] = f["total"]
    filas_principal = [principal[nombre] for nombre in sorted(principal)]

    wb = Workbook()
    ws = wb.active
    ws.title = "CUMPLIMIENTOS"
    ws.sheet_view.showGridLines = False
    ws.cell(row=1, column=2, value="GENERAL MOTORS").font = TITULO

    ancho = 3 + sum(len(specs) for _, specs in _grupos_detalle({"meta_c": 0, "pond_c": 0, "meta_n": 0, "pond_n": 0, "pondera": 0}))
    if filas_principal:
        # Posiciones del cuadro de detalle (debajo de la principal) para que la formula del % FINAL lo pueda leer.
        top = 3
        titulo_detalle = top + 2 + len(filas_principal) + 1 + 3
        inicio = titulo_detalle + 1
        posiciones = []
        fila = inicio
        for _, filas, _ in buckets:
            posiciones.append(fila)
            fila += 2 + len(filas) + 1 + 2
        fin = fila - 3

        ref_detalle = columnas_grupos(_grupos_detalle(buckets[0][2])) if buckets else None
        grupos_principal = []
        if ref_detalle:
            grupos_principal.append((CUMPL, [formula("% FINAL", PCT, _cumplimiento_final(ref_detalle, inicio, fin))]))
        if productos:
            grupos_principal.append(("NEGOCIOS", [
                *(valor(p["nombre"].upper(), p["codigo"], ENTERO) for p in productos),
                valor("TOTAL", "neg_total", ENTERO),
            ]))
        if grupos_principal:
            tabla_cumplimiento(ws, top, "CARTERA", "GM", filas_principal, grupos_principal)

        if buckets:
            celda(ws, titulo_detalle, 2, "DETALLE CUMPLIMIENTO FINAL", font=BLANCA, fill=AZUL, hasta_col=ancho)
            for (bucket, filas, info), fila_top in zip(buckets, posiciones):
                tabla_cumplimiento(ws, fila_top, "BUCKET", bucket, filas, _grupos_detalle(info))
    anchos_cumplimiento(ws, ancho + 2)

    _, operaciones = get_monthly_export_rows(periodo)
    operaciones = [
        r for r in sin_phoenix(operaciones) if str(r.get("bucket") or "").strip() in BUCKET_ORDER
    ]
    operaciones.sort(key=lambda r: (r["ejecutivo"], BUCKET_ORDER.index(str(r["bucket"]).strip()), str(r["op"])))
    hoja_detalle(
        wb, "PAGOS",
        [("EJECUTIVO", 24, None), ("OPERACIÓN", 18, None), ("RUT", 13, None), ("NOMBRE", 36, None),
         ("BUCKET", 10, None), ("DÍAS MORA", 10, ENTERO), ("DEUDA", 15, MONEDA), ("CUOTA", 14, MONEDA),
         ("CONTENIDO", 11, None), ("NORMALIZADO", 13, None)],
        [
            [r["ejecutivo"], str(r["op"] or "").strip(), r["rut"], r["nombre"], str(r["bucket"]).strip(),
             r["dias_de_mora"], r["deuda"], r["cuota"], "SI" if r["contenido"] else "NO",
             "SI" if r["normalizado"] else "NO"]
            for r in operaciones
        ],
    )
    hoja_detalle(
        wb, "NEGOCIOS",
        [("EJECUTIVO", 24, None), ("OPERACIÓN", 18, None), ("TIPO", 18, None)],
        [[f["ejecutivo"], f["operacion"], f["producto_nombre"]] for f in _sin_ejecutivo(get_negocios_detalle(NEGOCIO, periodo)["filas"])],
    )
    return guardar(wb), f"GM_{periodo[:7]}.xlsx"
