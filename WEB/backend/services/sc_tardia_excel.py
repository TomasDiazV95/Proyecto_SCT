"""Excel de Santander Consumer Tardia con el formato del de procuradores, una hoja por zona.

En cada hoja (NORTE, SUR, METROPOLITANA): tabla principal con el cumplimiento de cada ejecutivo en altas
cuantias (C1 - C2), mora tardia (C3, Susc. CV, C5, C6, Pre Castigo y su promedio), castigo (F1 - F3) y el
cumplimiento final. Debajo, un cuadro por bloque con como se llega a ese cumplimiento: DEUDA ASIG., CONTENIDO,
%CONT., META % y %CUMPL. (con normalizacion y PONDERA en C1 - C2 y C3; por fase en castigo). Luego los
negocios de la zona. Quien no tiene zona no va. Los % son formulas que leen esos cuadros, asi que se puede corregir un valor, una meta o
una ponderacion a mano. Al final el detalle por operacion y de los negocios.
"""
from __future__ import annotations

import unicodedata

from openpyxl import Workbook

from services.excel_formato import (
    AZUL, BLANCA, CELESTE, ENTERO, MONEDA, NARANJO, PCT, PCT2, TITULO,
    anchos_cumplimiento, celda, columnas_grupos, formula, guardar, hoja_detalle, ratio, sin_phoenix,
    tabla_cumplimiento, valor,
)
from services.negocios_service import SIN_EJECUTIVO, get_conteo, get_detalle as get_negocios_detalle
from services.sc_tardia_service import (
    ALTAS_CUANTIAS_BLOCK, CASTIGO_TOTAL_BLOCK, MORA_TARDIA_BLOCKS, _executive_key, _period_date, _period_version,
    get_cycle_view, get_metas, get_operaciones_excel, get_zonas_ejecutivos,
)


NEGOCIO = "sc-terreno"
TOPE_CUMPLIMIENTO = 1.3
ZONAS = (("ZONA NORTE CENTRO", "NORTE"), ("ZONA CENTRO SUR", "SUR"), ("ZONA METROPOLITANA", "METROPOLITANA"))
SIN_ZONA = "SIN ZONA"
ETIQUETA_MORA = {"C3": "C3", "SUSCEPTIBLE CV": "SUSC. CV", "C5": "C5", "C6": "C6", "PRE CASTIGO": "PRE CASTIGO"}
TITULO_BLOQUE = {
    ALTAS_CUANTIAS_BLOCK: "ALTAS CUANTÍAS (C1 - C2)",
    "C3": "C3",
    "SUSCEPTIBLE CV": "SUSCEPTIBLE CV",
    "C5": "C5",
    "C6": "C6",
    "PRE CASTIGO": "PRE CASTIGO",
    CASTIGO_TOTAL_BLOCK: "CASTIGO (F1 - F4)",
}
BLOQUES = [ALTAS_CUANTIAS_BLOCK, *MORA_TARDIA_BLOCKS, CASTIGO_TOTAL_BLOCK]
BLOQUES_CON_NORMALIZACION = (ALTAS_CUANTIAS_BLOCK, "C3")
# Variables de la tabla de metas (sin acentos) de contencion y normalizacion de cada bloque.
META_VARIABLE = {
    ALTAS_CUANTIAS_BLOCK: ("CONTENCION C1_C2", "NORMALIZACION C1_C2"),
    "C3": ("CONTENCION C3", "NORMALIZACION C3"),
    "SUSCEPTIBLE CV": ("CONT SUSCEPT CV", None),
    "C5": ("CONTENCION C5", None),
    "C6": ("CONTENCION C6", None),
    "PRE CASTIGO": ("CONTENCION PRE CASTIGO", None),
}
FASES = ("F1", "F2", "F3", "F4")
FASES_CON_META = ("F1", "F2", "F3")


def _clave(texto) -> str:
    sin_acentos = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return " ".join(sin_acentos.upper().split())


def _metas(periodo: str) -> dict[str, dict]:
    """Meta (fraccion) y ponderador nivel 3 (fraccion) por variable; castigo F1/F2 con la meta antigua 'F1 y F2'."""
    metas = {
        _clave(m["variable"]): {"meta": (m["meta_valor"] or 0) / 100, "pondera": (m["ponderador_nivel_3_pct"] or 0) / 100,
                                "nivel_1": m["ponderador_nivel_1_pct"], "tipo": m["meta_tipo"]}
        for m in get_metas({"periodo": periodo})
    }
    for fase in ("F1", "F2"):
        metas.setdefault(f"RECUPERO CASTIGO {fase}", metas.get("RECUPERO CASTIGO F1 Y F2", {"meta": 0}))
    return metas


def _cumplimiento(grupo_monto: str, sub_monto: str, grupo_deuda: str, grupo_meta: str):
    """%CUMPL. = monto / deuda / meta %, con tope; sin meta o sin deuda: 0 (como en la pagina)."""
    def fn(ref, r: int) -> str:
        monto = f"{ref(grupo_monto, sub_monto)}{r}"
        deuda = f"{ref(grupo_deuda, 'DEUDA ASIG.')}{r}"
        meta = f"{ref(grupo_meta, 'META %')}{r}"
        return f"=IF(OR(N({meta})=0,N({deuda})=0),0,MAX(0,MIN({monto}/{deuda}/{meta},{TOPE_CUMPLIMIENTO})))"
    return fn


def _pct_normalizado(ref, r: int) -> str:
    deuda, norm = f"{ref('CONTENCIÓN', 'DEUDA ASIG.')}{r}", f"{ref('NORMALIZACIÓN', 'NORMALIZADO')}{r}"
    return f"=IF(N({deuda})=0,0,{norm}/{deuda})"


def _final_normalizacion(ref, r: int) -> str:
    """Contencion y normalizacion ponderadas (nivel 3); sin meta de normalizacion, solo la contencion."""
    deuda = f"{ref('CONTENCIÓN', 'DEUDA ASIG.')}{r}"
    cc, pc = f"{ref('CONTENCIÓN', '%CUMPL.')}{r}", f"{ref('CONTENCIÓN', 'PONDERA')}{r}"
    cn, pn = f"{ref('NORMALIZACIÓN', '%CUMPL.')}{r}", f"{ref('NORMALIZACIÓN', 'PONDERA')}{r}"
    meta_norm = f"{ref('NORMALIZACIÓN', 'META %')}{r}"
    return (f"=IF(AND(N({meta_norm})>0,N({deuda})>0,N({pc})+N({pn})>0),"
            f"MAX(0,MIN(({cc}*{pc}+{cn}*{pn})/({pc}+{pn}),{TOPE_CUMPLIMIENTO})),{cc})")


def _grupos_bloque(bloque: str, metas: dict) -> tuple[list, tuple[str, str]]:
    """Columnas del cuadro de un bloque y (grupo, columna) de su cumplimiento."""
    var_cont, var_norm = META_VARIABLE[bloque]
    meta_cont = metas.get(var_cont, {"meta": 0, "pondera": 0})
    if bloque in BLOQUES_CON_NORMALIZACION:
        meta_norm = metas.get(var_norm, {"meta": 0, "pondera": 0})
        return [
            ("CONTENCIÓN", [
                valor("DEUDA ASIG.", "deuda", MONEDA),
                valor("CONTENIDO", "contenido", MONEDA, NARANJO),
                ratio("%CONT.", 1, 0, PCT2),
                valor("META %", "meta_cont", PCT2, CELESTE, total=meta_cont["meta"]),
                formula("%CUMPL.", PCT, _cumplimiento("CONTENCIÓN", "CONTENIDO", "CONTENCIÓN", "CONTENCIÓN")),
                valor("PONDERA", "pondera_cont", PCT, CELESTE, total=meta_cont["pondera"]),
            ]),
            ("NORMALIZACIÓN", [
                valor("NORMALIZADO", "normalizado", MONEDA, NARANJO),
                formula("%NORM.", PCT2, _pct_normalizado),
                valor("META %", "meta_norm", PCT2, CELESTE, total=meta_norm["meta"]),
                formula("%CUMPL.", PCT, _cumplimiento("NORMALIZACIÓN", "NORMALIZADO", "CONTENCIÓN", "NORMALIZACIÓN")),
                valor("PONDERA", "pondera_norm", PCT, CELESTE, total=meta_norm["pondera"]),
            ]),
            ("CUMPLIMIENTO", [formula("% FINAL", PCT, _final_normalizacion)]),
        ], ("CUMPLIMIENTO", "% FINAL")
    titulo = TITULO_BLOQUE[bloque]
    return [
        (titulo, [
            valor("DEUDA ASIG.", "deuda", MONEDA),
            valor("CONTENIDO", "contenido", MONEDA, NARANJO),
            ratio("%CONT.", 1, 0, PCT2),
            valor("META %", "meta_cont", PCT2, CELESTE, total=meta_cont["meta"]),
            formula("%CUMPL.", PCT, _cumplimiento(titulo, "CONTENIDO", titulo, titulo)),
        ]),
    ], (titulo, "%CUMPL.")


def _meta_castigo(ref, r: int) -> str:
    return "=" + "+".join(f"{ref(f, 'DEUDA ASIG.')}{r}*{ref(f, 'META %')}{r}" for f in FASES_CON_META)


def _recupero_castigo(ref, r: int) -> str:
    return "=" + "+".join(f"{ref(f, 'RECUPERO')}{r}" for f in FASES)


def _cumplimiento_castigo(ref, r: int) -> str:
    """Recupero F1..F4 sobre la meta de F1..F3 (se suma primero y se divide despues), con tope."""
    meta, rec = (f"{ref('TOTAL F1 - F4', sub)}{r}" for sub in ("META RECUP.", "RECUPERO"))
    return f"=IF(N({meta})=0,0,MAX(0,MIN({rec}/{meta},{TOPE_CUMPLIMIENTO})))"


def _grupos_castigo(metas: dict) -> tuple[list, tuple[str, str]]:
    grupos = [
        (fase, [
            valor("DEUDA ASIG.", f"{fase}_deuda", MONEDA),
            valor("META %", f"{fase}_meta", PCT2, CELESTE, total=metas.get(f"RECUPERO CASTIGO {fase}", {"meta": 0})["meta"]),
            valor("RECUPERO", f"{fase}_recupero", MONEDA, NARANJO),
        ])
        for fase in FASES_CON_META
    ]
    grupos.append(("F4", [valor("RECUPERO", "F4_recupero", MONEDA, NARANJO)]))
    grupos.append(("TOTAL F1 - F4", [
        formula("META RECUP.", MONEDA, _meta_castigo),
        formula("RECUPERO", MONEDA, _recupero_castigo),
        formula("%CUMPL.", PCT, _cumplimiento_castigo),
    ]))
    return grupos, ("TOTAL F1 - F4", "%CUMPL.")


def _ejecutivos(rows: list[dict], operaciones: list[dict], metas: dict) -> dict[str, dict]:
    """Por ejecutivo: zona y los datos de cada bloque que entra a su cumplimiento."""
    ejecutivos: dict[str, dict] = {}
    for row in sin_phoenix(rows):
        ej = ejecutivos.setdefault(_executive_key(row["ejecutivo"]), {
            "ejecutivo": row["ejecutivo"], "zona": row["zona"] or SIN_ZONA, "bloques": {},
            "activos": set(row.get("bloques_activos") or []),
        })
        if row["bloque"] in BLOQUES:
            ej["bloques"][row["bloque"]] = row

    castigo: dict[str, dict] = {}
    for op in operaciones:
        if op["origen"] == "CASTIGO" and op["bloque"] in FASES:
            fases = castigo.setdefault(_executive_key(op["ejecutivo"]), {})
            fases[f"{op['bloque']}_deuda"] = fases.get(f"{op['bloque']}_deuda", 0) + op["deuda"]
            fases[f"{op['bloque']}_recupero"] = fases.get(f"{op['bloque']}_recupero", 0) + op["contenido"]

    for clave, ej in ejecutivos.items():
        detalle: dict[str, dict] = {}
        for bloque in BLOQUES:
            row = ej["bloques"].get(bloque)
            # Altas cuantias y castigo asignados sin cartera entran con 0, igual que en la pagina.
            if row is None and not (bloque in (ALTAS_CUANTIAS_BLOCK, CASTIGO_TOTAL_BLOCK) and bloque in ej["activos"]):
                continue
            fila = {"ejecutivo": ej["ejecutivo"]}
            if bloque == CASTIGO_TOTAL_BLOCK:
                for fase in FASES:
                    fila[f"{fase}_deuda"] = round(castigo.get(clave, {}).get(f"{fase}_deuda", 0))
                    fila[f"{fase}_recupero"] = round(castigo.get(clave, {}).get(f"{fase}_recupero", 0))
                    fila[f"{fase}_meta"] = metas.get(f"RECUPERO CASTIGO {fase}", {"meta": 0})["meta"]
            else:
                var_cont, var_norm = META_VARIABLE[bloque]
                fila.update({
                    "deuda": (row or {}).get("deuda_asignada") or 0,
                    "contenido": (row or {}).get("contenido") or 0,
                    "normalizado": (row or {}).get("normalizado") or 0,
                    "meta_cont": metas.get(var_cont, {"meta": 0})["meta"],
                    "pondera_cont": metas.get(var_cont, {"pondera": 0})["pondera"],
                    "meta_norm": metas.get(var_norm, {"meta": 0})["meta"] if var_norm else 0,
                    "pondera_norm": metas.get(var_norm, {"pondera": 0})["pondera"] if var_norm else 0,
                })
            detalle[bloque] = fila
        ej["detalle"] = detalle
    return ejecutivos


def _grupos_principal(celdas: dict[str, dict], totales: dict[str, str], filas: list[dict], datos: int, total: int,
                      pesos: dict[str, float]):
    def bloque_ref(bloque: str):
        def fn(_ref, r: int) -> str:
            if r == total:
                return f"={totales[bloque]}" if bloque in totales else "-"
            celda_bloque = celdas.get(bloque, {}).get(filas[r - datos]["ejecutivo"])
            return f"={celda_bloque}" if celda_bloque else "-"
        return fn

    def promedio(ref, r: int) -> str:
        desde, hasta = ref("MORA TARDÍA", ETIQUETA_MORA[MORA_TARDIA_BLOCKS[0]]), ref("MORA TARDÍA", ETIQUETA_MORA[MORA_TARDIA_BLOCKS[-1]])
        return f'=IFERROR(AVERAGE({desde}{r}:{hasta}{r}),"-")'

    def final(ref, r: int) -> str:
        """Altas cuantias: solo su bloque. Si no, mora tardia (promedio simple de sus ciclos) y castigo
        ponderados (nivel 1); con uno solo de los dos, ese."""
        if r == total:
            columna = ref("CUMPLIMIENTO", "% FINAL")
            return f"=IFERROR(AVERAGE({columna}{datos}:{columna}{total - 1}),0)"
        altas = f"{ref('ALTAS CUANTÍAS', 'C1 - C2')}{r}"
        mora, pm = f"{ref('MORA TARDÍA', 'PROMEDIO')}{r}", f"{ref('MORA TARDÍA', 'PONDERA')}{r}"
        cast, pc = f"{ref('CASTIGO', 'TOTAL F1 - F3')}{r}", f"{ref('CASTIGO', 'PONDERA')}{r}"
        expr = (f"IF(ISNUMBER({altas}),{altas},IF(AND(ISNUMBER({mora}),ISNUMBER({cast})),{mora}*{pm}+{cast}*{pc},"
                f"IF(ISNUMBER({mora}),{mora},IF(ISNUMBER({cast}),{cast},0))))")
        return f"=MAX(0,MIN({expr},{TOPE_CUMPLIMIENTO}))"

    return [
        ("ALTAS CUANTÍAS", [formula("C1 - C2", PCT, bloque_ref(ALTAS_CUANTIAS_BLOCK))]),
        ("MORA TARDÍA", [
            *(formula(ETIQUETA_MORA[b], PCT, bloque_ref(b)) for b in MORA_TARDIA_BLOCKS),
            formula("PROMEDIO", PCT, promedio),
            valor("PONDERA", "pondera_mora", PCT, CELESTE, total=pesos["mora"]),
        ]),
        ("CASTIGO", [
            formula("TOTAL F1 - F3", PCT, bloque_ref(CASTIGO_TOTAL_BLOCK)),
            valor("PONDERA", "pondera_castigo", PCT, CELESTE, total=pesos["castigo"]),
        ]),
        ("CUMPLIMIENTO", [formula("% FINAL", PCT, final)]),
    ]


def _hoja_zona(wb: Workbook, zona: str, nombre: str, ejecutivos: list[dict], negocios: list[dict], productos: list[dict],
               metas: dict, pesos: dict[str, float]) -> None:
    ws = wb.create_sheet(nombre)
    ws.sheet_view.showGridLines = False
    ws.cell(row=1, column=2, value=f"SANTANDER CONSUMER TARDÍA · {zona}").font = TITULO

    filas = []
    for ej in sorted(ejecutivos, key=lambda e: e["ejecutivo"]):
        detalle = ej["detalle"]
        mora = any(b in detalle for b in MORA_TARDIA_BLOCKS)
        # La ponderacion mora tardia / castigo solo aplica a quien tiene los dos (y no es altas cuantias).
        pondera = mora and CASTIGO_TOTAL_BLOCK in detalle and ALTAS_CUANTIAS_BLOCK not in detalle
        filas.append({
            "ejecutivo": ej["ejecutivo"],
            "pondera_mora": pesos["mora"] if pondera else "-",
            "pondera_castigo": pesos["castigo"] if pondera else "-",
        })

    # Primero se ubican los cuadros por bloque (debajo de la tabla principal) para que las formulas de la
    # tabla principal apunten a sus celdas.
    principal = 3
    principal_total = principal + 2 + len(filas)
    fila = principal_total + 3
    cuadros = []
    celdas: dict[str, dict] = {}
    totales: dict[str, str] = {}
    for bloque in BLOQUES:
        filas_bloque = [ej["detalle"][bloque] for ej in sorted(ejecutivos, key=lambda e: e["ejecutivo"]) if bloque in ej["detalle"]]
        if not filas_bloque:
            continue
        grupos, (grupo_final, sub_final) = _grupos_castigo(metas) if bloque == CASTIGO_TOTAL_BLOCK else _grupos_bloque(bloque, metas)
        top = fila + 1
        datos = top + 2
        columna = columnas_grupos(grupos)(grupo_final, sub_final)
        celdas[bloque] = {f["ejecutivo"]: f"{columna}{datos + i}" for i, f in enumerate(filas_bloque)}
        totales[bloque] = f"{columna}{datos + len(filas_bloque)}"
        cuadros.append((bloque, fila, top, filas_bloque, grupos))
        fila = datos + len(filas_bloque) + 3

    if filas:
        tabla_cumplimiento(
            ws, principal, "ZONA", nombre, filas,
            _grupos_principal(celdas, totales, filas, principal + 2, principal_total, pesos),
        )
    for bloque, titulo, top, filas_bloque, grupos in cuadros:
        ancho = 3 + sum(len(specs) for _, specs in grupos)
        celda(ws, titulo, 2, f"DETALLE CUMPLIMIENTO {TITULO_BLOQUE[bloque]}", font=BLANCA, fill=AZUL, hasta_col=ancho)
        tabla_cumplimiento(ws, top, "BLOQUE", TITULO_BLOQUE[bloque], filas_bloque, grupos)

    if negocios:
        tabla_cumplimiento(ws, fila, "NEGOCIOS", nombre, sorted(negocios, key=lambda n: n["ejecutivo"]), [
            ("NEGOCIOS", [
                *(valor(p["nombre"].upper(), p["codigo"], ENTERO) for p in productos),
                valor("TOTAL", "total", ENTERO),
            ]),
        ])
    anchos_cumplimiento(ws, 20)


def _sin_ejecutivo(filas: list[dict]) -> list[dict]:
    return [f for f in sin_phoenix(filas) if f["ejecutivo"] != SIN_EJECUTIVO]


def build_excel(periodo: str | None) -> tuple:
    periodo = str(periodo or "").strip()
    if not periodo:
        raise RuntimeError("Falta el periodo")
    filtros = {"periodo": periodo}
    rows = get_cycle_view(filtros)
    operaciones = get_operaciones_excel(periodo)
    metas = _metas(periodo)
    nivel_1 = (rows[0]["ponderadores_nivel_1"] if rows else {}) or {}
    pesos = {"mora": (nivel_1.get("PTC") or 0) / 100, "castigo": (nivel_1.get("STOCK") or 0) / 100}
    ejecutivos = _ejecutivos(rows, operaciones, metas)

    # Zona de cada ejecutivo: la de la productividad; para los que solo tienen negocios, la de la foto consultada
    # o, si no tienen cartera en ella, la de su ultima foto en la sabana.
    zona_de = dict(get_zonas_ejecutivos())
    zona_de.update({_executive_key(op["ejecutivo"]): op["zona"] or SIN_ZONA for op in operaciones})
    zona_de.update({clave: ej["zona"] for clave, ej in ejecutivos.items()})

    conteo = get_conteo(NEGOCIO, periodo)
    negocios_por_zona: dict[str, list[dict]] = {}
    for f in _sin_ejecutivo(conteo["filas"]):
        zona = zona_de.get(_executive_key(f["ejecutivo"]), SIN_ZONA)
        negocios_por_zona.setdefault(zona, []).append({"ejecutivo": f["ejecutivo"], **f["conteos"], "total": f["total"]})

    wb = Workbook()
    wb.remove(wb.active)
    for zona, nombre in ZONAS:
        _hoja_zona(
            wb, zona, nombre, [ej for ej in ejecutivos.values() if ej["zona"] == zona],
            negocios_por_zona.get(zona, []), conteo["productos"], metas, pesos,
        )

    # Operaciones de los bloques que entran al cumplimiento de cada ejecutivo.
    # Quien no tiene zona (Norte, Sur o Metropolitana) no va en el Excel.
    orden_zona = {zona: i for i, (zona, _) in enumerate(ZONAS)}
    orden_bloque = {b: i for i, b in enumerate(BLOQUES)}
    detalle = []
    for op in operaciones:
        ej = ejecutivos.get(_executive_key(op["ejecutivo"]))
        if not ej or ej["zona"] not in orden_zona or not op["bloque"]:
            continue
        if op["origen"] == "CASTIGO":
            bloque = CASTIGO_TOTAL_BLOCK
        else:
            bloque = ALTAS_CUANTIAS_BLOCK if op["bloque"] in ("C1", "C2") else op["bloque"]
        if bloque not in ej["detalle"]:
            continue
        detalle.append((ej, bloque, op))
    detalle.sort(key=lambda d: (
        orden_zona[d[0]["zona"]], d[0]["ejecutivo"], orden_bloque[d[1]], d[2]["ciclo"], -d[2]["deuda"],
        d[2]["operacion"],
    ))
    hoja_detalle(
        wb, "CONTENCION",
        [("ZONA", 20, None), ("EJECUTIVO", 24, None), ("BLOQUE", 24, None), ("CICLO", 8, None), ("APERTURA", 22, None),
         ("RUT", 12, None), ("OPERACIÓN", 20, None), ("DEUDA", 16, MONEDA), ("CONTENIDO / RECUPERO", 16, MONEDA),
         ("NORMALIZADO", 16, MONEDA)],
        [
            [ej["zona"], ej["ejecutivo"], TITULO_BLOQUE[bloque], op["ciclo"], op["apertura"], op["rut"], op["operacion"],
             op["deuda"], op["contenido"], op["normalizado"] if bloque in BLOQUES_CON_NORMALIZACION else None]
            for ej, bloque, op in detalle
        ],
    )
    negocios = sorted(
        (
            (zona, f) for zona, f in (
                (zona_de.get(_executive_key(f["ejecutivo"]), SIN_ZONA), f)
                for f in _sin_ejecutivo(get_negocios_detalle(NEGOCIO, periodo)["filas"])
            )
            if zona in orden_zona
        ),
        key=lambda x: (orden_zona[x[0]], x[1]["ejecutivo"], x[1]["producto_nombre"], x[1]["operacion"]),
    )
    hoja_detalle(
        wb, "NEGOCIOS",
        [("ZONA", 20, None), ("EJECUTIVO", 24, None), ("OPERACIÓN", 18, None), ("TIPO", 18, None)],
        [[zona, f["ejecutivo"], f["operacion"], f["producto_nombre"]] for zona, f in negocios],
    )

    foto = _period_date(periodo).replace("-", "")
    sufijo = "_precierre" if _period_version(periodo) == "PRECIERRE" else ""
    return guardar(wb), f"SC_Tardia_{foto}{sufijo}.xlsx"
