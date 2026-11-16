"""Excel de Santander Consumer Tardia con el formato del de procuradores, una hoja por zona.

En cada hoja (NORTE, SUR, METROPOLITANA): tabla principal con el cumplimiento de cada ejecutivo en altas
cuantias (C1 - C2), mora tardia (C3, Susc. CV, C5, C6, Pre Castigo y su promedio), castigo (F1 - F3) y el
cumplimiento final. Debajo, un cuadro por bloque con como se llega a ese cumplimiento: DEUDA ASIG., CONTENIDO,
%CONT., META % y %CUMPL. (con normalizacion y PONDERA en C1 - C2 y C3; por fase en castigo). Luego los
negocios de la zona. Quien no tiene zona no va. Los % son formulas que leen esos cuadros, asi que se puede corregir un valor, una meta o
una ponderacion a mano. Al final el detalle por operacion y de los negocios.

SC Piloto (fuente 'piloto', ejecutivos de telefonia) usa el mismo formato en una sola hoja PILOTO, sin altas
cuantias ni C3; sus negocios son los del archivo de SC Terreno de los ejecutivos de su carterizado.
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
    ALTAS_CUANTIAS_BLOCK, CASTIGO_TOTAL_BLOCK, MORA_TARDIA_BLOCKS, _executive_key, _period_date, _period_version, con_tope,
    get_ciclos_mes, get_cycle_view, get_ejecutivos_piloto, get_metas, get_operaciones_excel, get_zonas_ejecutivos,
    operacion_key,
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
# Negocios que corresponden a otro ejecutivo (columna CORRESPONDE A de la hoja NEGOCIOS). Solo informativo:
# el negocio sigue contando para el ejecutivo que lo trae el archivo.
CORRESPONDE_A = {
    op: "GUILLERMO MORALES"
    for op in ("650081937979", "650071064470", "650061587122", "650077916878", "650080313459")
}
FASES = ("F1", "F2", "F3", "F4")
FASES_CON_META = ("F1", "F2", "F3")
# Por fuente: titulo de las hojas, nombre del archivo, si lleva altas cuantias y negocios, y las hojas
# (zona de la productividad, nombre). Piloto va en una sola hoja: sus ejecutivos son de telefonia.
PILOTO = "PILOTO"
EXCEL_FUENTES = {
    "terreno": {"titulo": "SANTANDER CONSUMER TARDÍA", "archivo": "SC_Tardia", "altas": True, "negocios": True,
                "hojas": ZONAS, "mora": MORA_TARDIA_BLOCKS},
    # El piloto no tiene C3 (es SC Telefonia). Sus negocios vienen en el archivo de SC Terreno.
    "piloto": {"titulo": "SC PILOTO", "archivo": "SC_Piloto", "altas": False, "negocios": True,
               "hojas": ((PILOTO, PILOTO),), "mora": [b for b in MORA_TARDIA_BLOCKS if b != "C3"]},
}


def _clave(texto) -> str:
    sin_acentos = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return " ".join(sin_acentos.upper().split())


def _metas(periodo: str, fuente: str = "terreno") -> dict[str, dict]:
    """Meta (fraccion) y ponderador nivel 3 (fraccion) por variable; castigo F1/F2 con la meta antigua 'F1 y F2'."""
    metas = {
        _clave(m["variable"]): {"meta": (m["meta_valor"] or 0) / 100, "pondera": (m["ponderador_nivel_3_pct"] or 0) / 100,
                                "nivel_1": m["ponderador_nivel_1_pct"], "tipo": m["meta_tipo"]}
        for m in get_metas({"periodo": periodo}, fuente)
    }
    for fase in ("F1", "F2"):
        metas.setdefault(f"RECUPERO CASTIGO {fase}", metas.get("RECUPERO CASTIGO F1 Y F2", {"meta": 0}))
    return metas


def _limite(expr: str, tope: bool) -> str:
    return f"MAX(0,MIN({expr},{TOPE_CUMPLIMIENTO}))" if tope else f"MAX(0,{expr})"


def _cumplimiento(grupo_monto: str, sub_monto: str, grupo_deuda: str, grupo_meta: str, tope: bool = True):
    """%CUMPL. = monto / deuda / meta %, con tope (salvo C3 desde oct-2026); sin meta o sin deuda: 0 (como en la pagina)."""
    def fn(ref, r: int) -> str:
        monto = f"{ref(grupo_monto, sub_monto)}{r}"
        deuda = f"{ref(grupo_deuda, 'DEUDA ASIG.')}{r}"
        meta = f"{ref(grupo_meta, 'META %')}{r}"
        return f"=IF(OR(N({meta})=0,N({deuda})=0),0,{_limite(f'{monto}/{deuda}/{meta}', tope)})"
    return fn


def _pct_normalizado(ref, r: int) -> str:
    deuda, norm = f"{ref('CONTENCIÓN', 'DEUDA ASIG.')}{r}", f"{ref('NORMALIZACIÓN', 'NORMALIZADO')}{r}"
    return f"=IF(N({deuda})=0,0,{norm}/{deuda})"


def _final_normalizacion(tope: bool = True):
    def fn(ref, r: int) -> str:
        """Contencion y normalizacion ponderadas (nivel 3); sin meta de normalizacion, solo la contencion."""
        deuda = f"{ref('CONTENCIÓN', 'DEUDA ASIG.')}{r}"
        cc, pc = f"{ref('CONTENCIÓN', '%CUMPL.')}{r}", f"{ref('CONTENCIÓN', 'PONDERA')}{r}"
        cn, pn = f"{ref('NORMALIZACIÓN', '%CUMPL.')}{r}", f"{ref('NORMALIZACIÓN', 'PONDERA')}{r}"
        meta_norm = f"{ref('NORMALIZACIÓN', 'META %')}{r}"
        return (f"=IF(AND(N({meta_norm})>0,N({deuda})>0,N({pc})+N({pn})>0),"
                f"{_limite(f'({cc}*{pc}+{cn}*{pn})/({pc}+{pn})', tope)},{cc})")
    return fn


def _grupos_bloque(bloque: str, metas: dict, periodo: str) -> tuple[list, tuple[str, str]]:
    """Columnas del cuadro de un bloque y (grupo, columna) de su cumplimiento."""
    var_cont, var_norm = META_VARIABLE[bloque]
    meta_cont = metas.get(var_cont, {"meta": 0, "pondera": 0})
    tope = con_tope(bloque, periodo)
    if bloque in BLOQUES_CON_NORMALIZACION:
        meta_norm = metas.get(var_norm, {"meta": 0, "pondera": 0})
        return [
            ("CONTENCIÓN", [
                valor("DEUDA ASIG.", "deuda", MONEDA),
                valor("CONTENIDO", "contenido", MONEDA, NARANJO),
                ratio("%CONT.", 1, 0, PCT2),
                valor("META %", "meta_cont", PCT2, CELESTE, total=meta_cont["meta"]),
                formula("%CUMPL.", PCT, _cumplimiento("CONTENCIÓN", "CONTENIDO", "CONTENCIÓN", "CONTENCIÓN", tope)),
                valor("PONDERA", "pondera_cont", PCT, CELESTE, total=meta_cont["pondera"]),
            ]),
            ("NORMALIZACIÓN", [
                valor("NORMALIZADO", "normalizado", MONEDA, NARANJO),
                formula("%NORM.", PCT2, _pct_normalizado),
                valor("META %", "meta_norm", PCT2, CELESTE, total=meta_norm["meta"]),
                formula("%CUMPL.", PCT, _cumplimiento("NORMALIZACIÓN", "NORMALIZADO", "CONTENCIÓN", "NORMALIZACIÓN", tope)),
                valor("PONDERA", "pondera_norm", PCT, CELESTE, total=meta_norm["pondera"]),
            ]),
            ("CUMPLIMIENTO", [formula("% FINAL", PCT, _final_normalizacion(tope))]),
        ], ("CUMPLIMIENTO", "% FINAL")
    titulo = TITULO_BLOQUE[bloque]
    return [
        (titulo, [
            valor("DEUDA ASIG.", "deuda", MONEDA),
            valor("CONTENIDO", "contenido", MONEDA, NARANJO),
            ratio("%CONT.", 1, 0, PCT2),
            valor("META %", "meta_cont", PCT2, CELESTE, total=meta_cont["meta"]),
            formula("%CUMPL.", PCT, _cumplimiento(titulo, "CONTENIDO", titulo, titulo, tope)),
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
                      pesos: dict[str, float], con_altas: bool = True, mora_blocks: list[str] = MORA_TARDIA_BLOCKS):
    def bloque_ref(bloque: str):
        def fn(_ref, r: int) -> str:
            if r == total:
                return f"={totales[bloque]}" if bloque in totales else "-"
            celda_bloque = celdas.get(bloque, {}).get(filas[r - datos]["ejecutivo"])
            return f"={celda_bloque}" if celda_bloque else "-"
        return fn

    def promedio(ref, r: int) -> str:
        desde, hasta = ref("MORA TARDÍA", ETIQUETA_MORA[mora_blocks[0]]), ref("MORA TARDÍA", ETIQUETA_MORA[mora_blocks[-1]])
        return f'=IFERROR(AVERAGE({desde}{r}:{hasta}{r}),"-")'

    def final(ref, r: int) -> str:
        """Altas cuantias: solo su bloque. Si no, mora tardia (promedio simple de sus ciclos) y castigo
        ponderados (nivel 1); con uno solo de los dos, ese."""
        if r == total:
            columna = ref("CUMPLIMIENTO", "% FINAL")
            return f"=IFERROR(AVERAGE({columna}{datos}:{columna}{total - 1}),0)"
        mora, pm = f"{ref('MORA TARDÍA', 'PROMEDIO')}{r}", f"{ref('MORA TARDÍA', 'PONDERA')}{r}"
        cast, pc = f"{ref('CASTIGO', 'TOTAL F1 - F3')}{r}", f"{ref('CASTIGO', 'PONDERA')}{r}"
        expr = (f"IF(AND(ISNUMBER({mora}),ISNUMBER({cast})),{mora}*{pm}+{cast}*{pc},"
                f"IF(ISNUMBER({mora}),{mora},IF(ISNUMBER({cast}),{cast},0)))")
        if con_altas:
            altas = f"{ref('ALTAS CUANTÍAS', 'C1 - C2')}{r}"
            expr = f"IF(ISNUMBER({altas}),{altas},{expr})"
        return f"=MAX(0,MIN({expr},{TOPE_CUMPLIMIENTO}))"

    altas_grupo = [("ALTAS CUANTÍAS", [formula("C1 - C2", PCT, bloque_ref(ALTAS_CUANTIAS_BLOCK))])] if con_altas else []
    return [
        *altas_grupo,
        ("MORA TARDÍA", [
            *(formula(ETIQUETA_MORA[b], PCT, bloque_ref(b)) for b in mora_blocks),
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
               metas: dict, pesos: dict[str, float], config: dict = EXCEL_FUENTES["terreno"], periodo: str = "") -> None:
    ws = wb.create_sheet(nombre)
    ws.sheet_view.showGridLines = False
    titulo = config["titulo"] if zona == PILOTO else f"{config['titulo']} · {zona}"
    ws.cell(row=1, column=2, value=titulo).font = TITULO

    filas = []
    for ej in sorted(ejecutivos, key=lambda e: e["ejecutivo"]):
        detalle = ej["detalle"]
        mora = any(b in detalle for b in MORA_TARDIA_BLOCKS)
        # La ponderacion mora tardia / castigo solo aplica a quien tiene los dos (y no es altas cuantias).
        pondera = mora and CASTIGO_TOTAL_BLOCK in detalle and ALTAS_CUANTIAS_BLOCK not in detalle
        filas.append({
            "ejecutivo": ej["ejecutivo"],
            "ciclos": _ciclos_cumplimiento(detalle),
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
        grupos, (grupo_final, sub_final) = (
            _grupos_castigo(metas) if bloque == CASTIGO_TOTAL_BLOCK else _grupos_bloque(bloque, metas, periodo)
        )
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
            _grupos_principal(celdas, totales, filas, principal + 2, principal_total, pesos, config["altas"], config["mora"]),
            previa=("CICLOS CUMPLIMIENTO", "ciclos"),
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
    # D es EJECUTIVO en la tabla principal (C lleva los ciclos).
    ws.column_dimensions["D"].width = 26


def _ciclos_cumplimiento(detalle: dict) -> str:
    """Ciclos que entran al % FINAL, con la misma regla de la formula: altas cuantias va sola; si no,
    los ciclos de mora tardia que tiene y castigo."""
    if ALTAS_CUANTIAS_BLOCK in detalle:
        return "C1 - C2"
    ciclos = [ETIQUETA_MORA[b] for b in MORA_TARDIA_BLOCKS if b in detalle]
    if CASTIGO_TOTAL_BLOCK in detalle:
        ciclos.append("CASTIGO F1 - F4")
    return ", ".join(ciclos)


def _sin_ejecutivo(filas: list[dict]) -> list[dict]:
    return [f for f in sin_phoenix(filas) if f["ejecutivo"] != SIN_EJECUTIVO]


def build_excel(periodo: str | None, fuente: str = "terreno") -> tuple:
    periodo = str(periodo or "").strip()
    if not periodo:
        raise RuntimeError("Falta el periodo")
    config = EXCEL_FUENTES[fuente]
    filtros = {"periodo": periodo}
    rows = get_cycle_view(filtros, fuente)
    operaciones = get_operaciones_excel(periodo, fuente)
    metas = _metas(periodo, fuente)
    nivel_1 = (rows[0]["ponderadores_nivel_1"] if rows else {}) or {}
    pesos = {"mora": (nivel_1.get("PTC") or 0) / 100, "castigo": (nivel_1.get("STOCK") or 0) / 100}
    ejecutivos = _ejecutivos(rows, operaciones, metas)
    if not config["altas"]:
        # Sin altas cuantias no hay bloque C1 - C2 (ni sus operaciones en el detalle).
        for ej in ejecutivos.values():
            ej["detalle"].pop(ALTAS_CUANTIAS_BLOCK, None)
    if fuente == "piloto":
        # Una sola hoja: los ejecutivos de telefonia no se reparten por zona.
        for ej in ejecutivos.values():
            ej["zona"] = PILOTO

    # Zona de cada ejecutivo: la de la productividad; para los que solo tienen negocios, la de la foto consultada
    # o, si no tienen cartera en ella, la de su ultima foto en la sabana.
    zona_de = dict(get_zonas_ejecutivos(fuente))
    zona_de.update({_executive_key(op["ejecutivo"]): op["zona"] or SIN_ZONA for op in operaciones})
    zona_de.update({clave: ej["zona"] for clave, ej in ejecutivos.items()})

    # Piloto: negocios del archivo de SC Terreno solo de los ejecutivos de su carterizado, todos en la hoja PILOTO.
    solo_ejecutivos = get_ejecutivos_piloto(periodo) if fuente == "piloto" else None
    if solo_ejecutivos is not None:
        zona_de = {_executive_key(e): PILOTO for e in solo_ejecutivos}
    conteo = get_conteo(NEGOCIO, periodo, ejecutivos=solo_ejecutivos) if config["negocios"] else {"filas": [], "productos": []}
    negocios_por_zona: dict[str, list[dict]] = {}
    for f in _sin_ejecutivo(conteo["filas"]):
        zona = zona_de.get(_executive_key(f["ejecutivo"]), SIN_ZONA)
        negocios_por_zona.setdefault(zona, []).append({"ejecutivo": f["ejecutivo"], **f["conteos"], "total": f["total"]})

    wb = Workbook()
    wb.remove(wb.active)
    for zona, nombre in config["hojas"]:
        _hoja_zona(
            wb, zona, nombre, [ej for ej in ejecutivos.values() if ej["zona"] == zona],
            negocios_por_zona.get(zona, []), conteo["productos"], metas, pesos, config, periodo,
        )

    # Operaciones de los bloques que entran al cumplimiento de cada ejecutivo.
    # Quien no tiene zona (Norte, Sur o Metropolitana) no va en el Excel.
    orden_zona = {zona: i for i, (zona, _) in enumerate(config["hojas"])}
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
    if config["negocios"]:
        negocios = sorted(
            (
                (zona, f) for zona, f in (
                    (zona_de.get(_executive_key(f["ejecutivo"]), SIN_ZONA), f)
                    for f in _sin_ejecutivo(get_negocios_detalle(NEGOCIO, periodo, ejecutivos=solo_ejecutivos)["filas"])
                )
                if zona in orden_zona
            ),
            key=lambda x: (orden_zona[x[0]], x[1]["ejecutivo"], x[1]["producto_nombre"], x[1]["operacion"]),
        )
        # Ciclo (C1..C8) o tramo de castigo (F1..F4) de cada negocio: el de la foto consultada; si la operacion
        # no esta en ella, el de su ultima foto del mes.
        ciclo_de = {operacion_key(op["operacion"]): op["ciclo"] for op in operaciones if op["ciclo"]}
        faltan = [f["operacion"] for _, f in negocios if operacion_key(f["operacion"]) not in ciclo_de]
        ciclo_de.update(get_ciclos_mes(periodo, faltan, fuente))
        hoja_detalle(
            wb, "NEGOCIOS",
            [("ZONA", 20, None), ("EJECUTIVO", 24, None), ("OPERACIÓN", 18, None), ("CICLO / TRAMO", 14, None),
             ("TIPO", 18, None), ("CORRESPONDE A", 22, None)],
            [[zona, f["ejecutivo"], f["operacion"], ciclo_de.get(operacion_key(f["operacion"]), "-"), f["producto_nombre"],
              CORRESPONDE_A.get(operacion_key(f["operacion"]))]
             for zona, f in negocios],
        )

    foto = _period_date(periodo, fuente).replace("-", "")
    sufijo = "_precierre" if _period_version(periodo) == "PRECIERRE" else ""
    return guardar(wb), f"{config['archivo']}_{foto}{sufijo}.xlsx"
