from __future__ import annotations

from datetime import date

from cache import cached, cached_view
from database import run_query_sets


# Altas cuantias: la meta mide C1 y C2 juntos (contencion y normalizacion, como C3);
# por ciclo se reportan ademas C1 y C2 por separado, con la misma meta.
ALTAS_CUANTIAS_BLOCK = "C1 - C2"

BLOCK_ORDER = [
    "C1",
    "C2",
    ALTAS_CUANTIAS_BLOCK,
    "C3",
    "SUSCEPTIBLE CV",
    "C5",
    "C6",
    "PRE CASTIGO",
    "F1",
    "F2",
    "F3",
    "F4",
    "TOTAL F1 - F4",
]

# Bloques que entran al cumplimiento de mora tardia; castigo entra con su consolidado.
MORA_TARDIA_BLOCKS = ["C3", "SUSCEPTIBLE CV", "C5", "C6", "PRE CASTIGO"]
CASTIGO_TOTAL_BLOCK = "TOTAL F1 - F4"
# Bloques cuyo cumplimiento combina contencion y normalizacion con los ponderadores nivel 3.
BLOQUES_CON_NORMALIZACION = ("C1", "C2", ALTAS_CUANTIAS_BLOCK, "C3")
CUMPLIMIENTO_MAX = 130.0


METAS_ORDER = [
    "Contención C1_C2",
    "Normalización C1_C2",
    "Contención C3",
    "Normalización C3",
    "Cont Suscept CV",
    "Contención C5",
    "Contención C6",
    "Contención Pre Castigo",
]


def _zona_sql(column: str) -> str:
    """Unifica la zona: la carga CASTIGO trae 'CENTRO-NORTE', 'CENTRO-SUR', 'METROPOLITANA'
    y STC trae 'ZONA NORTE CENTRO', 'ZONA CENTRO SUR', 'ZONA METROPOLITANA'."""
    return f"""
        CASE UPPER(REPLACE(REPLACE(LTRIM(RTRIM({column})), '-', ' '), 'ZONA ', ''))
            WHEN 'CENTRO SUR' THEN 'ZONA CENTRO SUR'
            WHEN 'METROPOLITANA' THEN 'ZONA METROPOLITANA'
            WHEN 'CENTRO NORTE' THEN 'ZONA NORTE CENTRO'
            WHEN 'NORTE CENTRO' THEN 'ZONA NORTE CENTRO'
            ELSE NULLIF(LTRIM(RTRIM({column})), '')
        END"""


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _period_date(periodo: str | None) -> str:
    if periodo:
        text = str(periodo).strip()
        if len(text) >= 10:
            return text[:10]
        return text

    periodos = _filter_lists()["periodos"]
    return periodos[0][:10] if periodos else date.today().isoformat()


def _period_version(periodo: str | None) -> str:
    """El bench de fin de mes tiene dos cargas; el filtro de fecha las ofrece como
    'YYYY-MM-DD (Cierre)' y 'YYYY-MM-DD (Pre-cierre)'. Sin sufijo es la carga vigente."""
    text = _clean_text(periodo).upper().replace("-", "")
    return "PRECIERRE" if "PRECIERRE" in text else "CIERRE"


def _block_index(block: str) -> int:
    try:
        return BLOCK_ORDER.index(block)
    except ValueError:
        return 99


def _executive_key(value) -> str:
    """Clave normalizada para cruzar ejecutivos entre tablas.

    El JOIN en SQL cruza sin problemas porque el collation de la base es
    case-insensitive, pero los diccionarios de Python no: la sabana puede traer
    el nombre en mayusculas y stc_bloques_ejecutivos en Title Case.
    """
    return _clean_text(value).upper()


def _active_blocks_by_executive(rows: list[dict]) -> dict[str, list[str]]:
    active: dict[str, list[str]] = {}
    for row in rows:
        ejecutivo = row.get("ejecutivo") or ""
        bloque = row.get("bloque") or ""
        if ejecutivo and bloque:
            # La asignacion historica 'F1 - F2' habilita los bloques F1 y F2, que se reportan por separado.
            bloques = ["F1", "F2"] if bloque == "F1 - F2" else [bloque]
            actuales = active.setdefault(_executive_key(ejecutivo), [])
            actuales.extend(b for b in bloques if b not in actuales)
    return active


def _level_1_weights(rows: list[dict]) -> dict[str, float]:
    weights = {"PCT": 0.0, "PTC": 0.0, "STOCK": 0.0}
    for row in rows:
        meta_tipo = row.get("meta_tipo") or ""
        if meta_tipo in weights:
            weights[meta_tipo] = float(row.get("ponderador_nivel_1_pct") or 0)
    weights["PTC"] = weights["PCT"]
    return weights


def _base_zona_sql(version: str) -> str:
    """Foto vigente de cada origen en #base_zona_original. Para el pre-cierre, el origen que
    tenga carga de pre-cierre en la fecha consultada sale de ahi; el resto, de la carga vigente."""
    columnas = f"""
        v.fecha,
        v.rut,
        v.operacion,
        {_zona_sql("v.zona")} AS zona,
        v.deuda,
        v.contenido,
        v.normalizado,
        LTRIM(RTRIM(v.ciclo)) AS ciclo,
        LTRIM(RTRIM(v.apertura)) AS apertura,
        LTRIM(RTRIM(v.ejecutivo)) AS ejecutivo,
        v.origen"""
    vigente = """
    FROM dbo.vw_stc_sabana_avance v
    INNER JOIN #ultimas_fechas uf
        ON v.origen = uf.origen
       AND v.fecha = uf.fecha_utilizada"""

    if version != "PRECIERRE":
        return f"""
    SELECT{columnas}
    INTO #base_zona_original{vigente};
"""
    return f"""
    SELECT{columnas}
    INTO #base_zona_original
    FROM dbo.vw_stc_sabana_avance_precierre v
    WHERE v.fecha = @fecha_consulta;

    INSERT INTO #base_zona_original
    SELECT{columnas}{vigente}
    WHERE v.origen NOT IN (SELECT origen FROM #base_zona_original);
"""


def _sc_tardia_sql(version: str = "CIERRE") -> str:
    """Lote unico: la vista se lee una sola vez a #base_zona_original (la foto vigente de cada
    origen) y de ahi salen los bloques activos, los ponderadores de nivel 1 y la tabla."""
    return f"""
    SET NOCOUNT ON;

    DECLARE @fecha_consulta DATE = CAST(? AS DATE);
    DECLARE @periodo DATE = DATEFROMPARTS(YEAR(@fecha_consulta), MONTH(@fecha_consulta), 1);

    SELECT
        v.origen,
        MAX(v.fecha) AS fecha_utilizada
    INTO #ultimas_fechas
    FROM dbo.vw_stc_sabana_avance v
    -- Solo cargas del mes consultado: un origen sin carga en el mes no arrastra el cierre anterior.
    WHERE v.fecha >= @periodo
      AND v.fecha <= @fecha_consulta
    GROUP BY v.origen;
{_base_zona_sql(version)}
    SELECT
        LTRIM(RTRIM(ejecutivo)) AS ejecutivo,
        LTRIM(RTRIM(bloque)) AS bloque
    FROM dbo.stc_bloques_ejecutivos
    WHERE periodo = @periodo
      AND activo = 1
    ORDER BY ejecutivo, bloque;

    SELECT
        meta_tipo,
        MAX(ponderador_nivel_1_pct) AS ponderador_nivel_1_pct
    FROM dbo.stc_metas_mensuales
    WHERE periodo = @periodo
      AND activo = 1
      AND meta_tipo IN ('PCT', 'STOCK')
    GROUP BY meta_tipo;

    WITH
    -- Cada ejecutivo queda en una sola zona: la que concentra mas operaciones.
    -- Asi una operacion suelta en otra zona no duplica al ejecutivo en la tabla.
    zona_principal_ejecutivo AS (
        SELECT ejecutivo, zona
        FROM (
            SELECT
                ejecutivo,
                zona,
                ROW_NUMBER() OVER (
                    PARTITION BY ejecutivo
                    ORDER BY COUNT_BIG(1) DESC, zona
                ) AS rn
            FROM #base_zona_original
            WHERE ISNULL(ejecutivo, '') <> ''
              AND zona IS NOT NULL
            GROUP BY ejecutivo, zona
        ) AS z
        WHERE rn = 1
    ),

    base AS (
        SELECT
            b.fecha,
            b.rut,
            b.operacion,
            ISNULL(zp.zona, b.zona) AS zona,
            b.deuda,
            b.contenido,
            b.normalizado,
            b.ciclo,
            b.apertura,
            b.ejecutivo,
            b.origen
        FROM #base_zona_original b
        LEFT JOIN zona_principal_ejecutivo zp
            ON zp.ejecutivo = b.ejecutivo
    ),

    stc_clasificado AS (
        SELECT
            fecha,
            rut,
            operacion,
            zona,
            deuda,
            contenido,
            normalizado,
            ciclo,
            apertura,
            ejecutivo,
            origen,
            CASE
                WHEN ciclo IN ('C6', 'C7', 'C8') AND apertura = 'SUSCEPTIBLE CASTIGO' THEN 'PRE CASTIGO'
                WHEN ciclo = 'C6' AND ISNULL(apertura, '') <> 'SUSCEPTIBLE CASTIGO' THEN 'C6'
                WHEN ciclo IN ('C1', 'C2') THEN ciclo
                WHEN ciclo = 'C3' THEN 'C3'
                WHEN apertura = 'SUSCEPTIBLE CV' THEN 'SUSCEPTIBLE CV'
                WHEN ciclo = 'C5' THEN 'C5'
                ELSE NULL
            END AS bloque
        FROM base
        WHERE origen = 'STC'
    ),

    -- C1 y C2 van por separado y ademas en el consolidado de altas cuantias, que es el que mide la meta.
    stc_bloques AS (
        SELECT ejecutivo, zona, operacion, deuda, contenido, normalizado, bloque
        FROM stc_clasificado
        UNION ALL
        SELECT ejecutivo, zona, operacion, deuda, contenido, normalizado, 'C1 - C2' AS bloque
        FROM stc_clasificado
        WHERE bloque IN ('C1', 'C2')
    ),

    castigo_clasificado AS (
        SELECT
            fecha,
            rut,
            operacion,
            zona,
            deuda,
            contenido,
            normalizado,
            ciclo,
            apertura,
            ejecutivo,
            origen,
            CASE
                WHEN ciclo = 'F1' THEN 'F1'
                WHEN ciclo = 'F2' THEN 'F2'
                WHEN ciclo = 'F3' THEN 'F3'
                WHEN ciclo = 'F4' THEN 'F4'
                ELSE NULL
            END AS bloque
        FROM base
        WHERE origen = 'CASTIGO'
    ),

    metas AS (
        SELECT
            m.periodo,
            LTRIM(RTRIM(m.variable)) AS variable,
            m.meta_valor,
            m.meta_tipo,
            m.ponderador_nivel_1_pct,
            m.ponderador_nivel_2_pct,
            m.ponderador_nivel_3_pct
        FROM dbo.stc_metas_mensuales m
        WHERE m.periodo = @periodo
          AND m.activo = 1
    ),

    resultado_stc_base AS (
        SELECT
            'STC' AS reporte,
            bloque,
            ejecutivo,
            zona,
            SUM(ISNULL(deuda, 0)) AS deuda_asignada,
            SUM(ISNULL(contenido, 0)) AS contenido,
            CASE WHEN bloque IN ('C1', 'C2', 'C1 - C2', 'C3') THEN SUM(ISNULL(normalizado, 0)) ELSE NULL END AS normalizado,
            COUNT(DISTINCT operacion) AS cantidad_casos,
            CASE
                WHEN bloque IN ('C1', 'C2', 'C1 - C2') THEN N'Contención C1_C2'
                WHEN bloque = 'C3' THEN 'Contención C3'
                WHEN bloque = 'SUSCEPTIBLE CV' THEN 'Cont Suscept CV'
                WHEN bloque = 'C5' THEN 'Contención C5'
                WHEN bloque = 'C6' THEN 'Contención C6'
                WHEN bloque = 'PRE CASTIGO' THEN 'Contención Pre Castigo'
                ELSE NULL
            END AS variable_meta_cont,
            CASE
                WHEN bloque IN ('C1', 'C2', 'C1 - C2') THEN N'Normalización C1_C2'
                WHEN bloque = 'C3' THEN 'Normalización C3'
                ELSE NULL
            END AS variable_meta_norm
        FROM stc_bloques
        WHERE bloque IS NOT NULL
        GROUP BY bloque, ejecutivo, zona
    ),

    resultado_stc AS (
        SELECT
            r.reporte,
            r.bloque,
            r.ejecutivo,
            r.zona,
            r.deuda_asignada,
            CASE WHEN meta_cont.meta_valor IS NULL THEN NULL ELSE ROUND(r.deuda_asignada * meta_cont.meta_valor / 100.0, 0) END AS monto_meta_cont,
            r.contenido,
            CASE WHEN meta_norm.meta_valor IS NULL THEN NULL ELSE ROUND(r.deuda_asignada * meta_norm.meta_valor / 100.0, 0) END AS monto_meta_norm,
            r.normalizado,
            r.cantidad_casos,
            -- Ponderadores de la tabla de metas: nivel 2 pesa cada bloque dentro de mora tardia,
            -- nivel 3 pesa contencion vs normalizacion dentro de C3.
            CAST(meta_cont.ponderador_nivel_2_pct AS float) AS pond_n2,
            CAST(meta_cont.ponderador_nivel_3_pct AS float) AS pond_n3_cont,
            CAST(meta_norm.ponderador_nivel_3_pct AS float) AS pond_n3_norm
        FROM resultado_stc_base r
        LEFT JOIN metas meta_cont
            ON meta_cont.variable = r.variable_meta_cont
        LEFT JOIN metas meta_norm
            ON meta_norm.variable = r.variable_meta_norm
    ),

    resultado_castigo_base AS (
        SELECT
            'CASTIGO' AS reporte,
            bloque,
            ejecutivo,
            zona,
            SUM(ISNULL(deuda, 0)) AS deuda_asignada,
            SUM(ISNULL(contenido, 0)) AS contenido,
            SUM(CASE WHEN ciclo = 'F1' THEN ISNULL(deuda, 0) ELSE 0 END) AS deuda_f1,
            SUM(CASE WHEN ciclo = 'F2' THEN ISNULL(deuda, 0) ELSE 0 END) AS deuda_f2,
            SUM(CASE WHEN ciclo = 'F3' THEN ISNULL(deuda, 0) ELSE 0 END) AS deuda_f3,
            COUNT(DISTINCT operacion) AS cantidad_casos
        FROM castigo_clasificado
        WHERE bloque IS NOT NULL
        GROUP BY bloque, ejecutivo, zona
    ),

    -- Meta de castigo por fase = asignacion de la fase x % de la fase.
    -- Desde 2026-08 las metas vienen separadas (F1, F2); antes era una sola 'F1 y F2'.
    metas_castigo AS (
        SELECT
            COALESCE(
                MAX(CASE WHEN variable = 'Recupero castigo F1' THEN meta_valor END),
                MAX(CASE WHEN variable = 'Recupero castigo F1 y F2' THEN meta_valor END)
            ) AS pct_f1,
            COALESCE(
                MAX(CASE WHEN variable = 'Recupero castigo F2' THEN meta_valor END),
                MAX(CASE WHEN variable = 'Recupero castigo F1 y F2' THEN meta_valor END)
            ) AS pct_f2,
            MAX(CASE WHEN variable = 'Recupero castigo F3' THEN meta_valor END) AS pct_f3
        FROM metas
    ),

    resultado_castigo AS (
        SELECT
            r.reporte,
            r.bloque,
            r.ejecutivo,
            r.zona,
            r.deuda_asignada,
            CASE
                WHEN r.bloque = 'F1' THEN ROUND(r.deuda_f1 * ISNULL(mc.pct_f1, 0) / 100.0, 0)
                WHEN r.bloque = 'F2' THEN ROUND(r.deuda_f2 * ISNULL(mc.pct_f2, 0) / 100.0, 0)
                WHEN r.bloque = 'F3' THEN ROUND(r.deuda_f3 * ISNULL(mc.pct_f3, 0) / 100.0, 0)
                ELSE NULL
            END AS monto_meta_cont,
            r.contenido,
            CAST(NULL AS NUMERIC(18, 2)) AS monto_meta_norm,
            CAST(NULL AS NUMERIC(18, 2)) AS normalizado,
            r.cantidad_casos,
            CAST(NULL AS float) AS pond_n2,
            CAST(NULL AS float) AS pond_n3_cont,
            CAST(NULL AS float) AS pond_n3_norm
        FROM resultado_castigo_base r
        CROSS JOIN metas_castigo mc
    ),

    -- Cumplimiento castigo = SUM(recupero F1..F3) / SUM(meta F1..F3): se suma primero y se divide despues.
    resultado_castigo_consolidado_base AS (
        SELECT
            'CASTIGO CONSOLIDADO' AS reporte,
            'TOTAL F1 - F4' AS bloque,
            ejecutivo,
            zona,
            SUM(CASE WHEN ciclo IN ('F1', 'F2', 'F3') THEN ISNULL(deuda, 0) ELSE 0 END) AS deuda_asignada,
            SUM(CASE WHEN ciclo = 'F1' THEN ISNULL(deuda, 0) ELSE 0 END) AS deuda_f1,
            SUM(CASE WHEN ciclo = 'F2' THEN ISNULL(deuda, 0) ELSE 0 END) AS deuda_f2,
            SUM(CASE WHEN ciclo = 'F3' THEN ISNULL(deuda, 0) ELSE 0 END) AS deuda_f3,
            SUM(CASE WHEN ciclo IN ('F1', 'F2', 'F3') THEN ISNULL(contenido, 0) ELSE 0 END) AS contenido,
            COUNT(DISTINCT operacion) AS cantidad_casos
        FROM base
        WHERE origen = 'CASTIGO'
          AND ciclo IN ('F1', 'F2', 'F3')
        GROUP BY ejecutivo, zona
    ),

    resultado_castigo_consolidado AS (
        SELECT
            r.reporte,
            r.bloque,
            r.ejecutivo,
            r.zona,
            r.deuda_asignada,
            ROUND(
                  (r.deuda_f1 * ISNULL(mc.pct_f1, 0) / 100.0)
                + (r.deuda_f2 * ISNULL(mc.pct_f2, 0) / 100.0)
                + (r.deuda_f3 * ISNULL(mc.pct_f3, 0) / 100.0),
                0
            ) AS monto_meta_cont,
            r.contenido,
            CAST(NULL AS NUMERIC(18, 2)) AS monto_meta_norm,
            CAST(NULL AS NUMERIC(18, 2)) AS normalizado,
            r.cantidad_casos,
            CAST(NULL AS float) AS pond_n2,
            CAST(NULL AS float) AS pond_n3_cont,
            CAST(NULL AS float) AS pond_n3_norm
        FROM resultado_castigo_consolidado_base r
        CROSS JOIN metas_castigo mc
    ),

    resultado_final AS (
        SELECT * FROM resultado_stc
        UNION ALL
        SELECT * FROM resultado_castigo
        UNION ALL
        SELECT * FROM resultado_castigo_consolidado
    ),

    resultado_filtrado AS (
        SELECT
            rf.reporte,
            rf.bloque,
            rf.ejecutivo,
            rf.zona,
            rf.deuda_asignada,
            rf.monto_meta_cont,
            rf.contenido,
            rf.monto_meta_norm,
            rf.normalizado,
            rf.cantidad_casos,
            rf.pond_n2,
            rf.pond_n3_cont,
            rf.pond_n3_norm
        FROM resultado_final rf
        WHERE EXISTS (
            SELECT 1
            FROM dbo.stc_bloques_ejecutivos be
            WHERE LTRIM(RTRIM(be.ejecutivo)) = rf.ejecutivo
              AND be.periodo = @periodo
              AND be.activo = 1
              AND (
                    LTRIM(RTRIM(be.bloque)) = rf.bloque
                    -- La asignacion historica 'F1 - F2' habilita F1 y F2 por separado.
                 OR (LTRIM(RTRIM(be.bloque)) = 'F1 - F2' AND rf.bloque IN ('F1', 'F2'))
                    -- Altas cuantias habilita tambien C1 y C2 por separado.
                 OR (LTRIM(RTRIM(be.bloque)) = 'C1 - C2' AND rf.bloque IN ('C1', 'C2'))
              )
        )
    )

    SELECT
        reporte,
        bloque,
        ejecutivo,
        zona,
        CAST(ROUND(deuda_asignada, 0) AS BIGINT) AS deuda_asignada,
        CAST(ROUND(monto_meta_cont, 0) AS BIGINT) AS monto_meta_cont,
        CAST(ROUND(contenido, 0) AS BIGINT) AS contenido,
        CAST(ROUND(monto_meta_norm, 0) AS BIGINT) AS monto_meta_norm,
        CAST(ROUND(normalizado, 0) AS BIGINT) AS normalizado,
        cantidad_casos,
        pond_n2,
        pond_n3_cont,
        pond_n3_norm
    FROM resultado_filtrado
    ORDER BY
        CASE reporte
            WHEN 'STC' THEN 1
            WHEN 'CASTIGO' THEN 2
            WHEN 'CASTIGO CONSOLIDADO' THEN 3
            ELSE 4
        END,
        ejecutivo,
        zona,
        CASE bloque
            WHEN 'C1' THEN -2
            WHEN 'C2' THEN -1
            WHEN 'C1 - C2' THEN 0
            WHEN 'C3' THEN 1
            WHEN 'SUSCEPTIBLE CV' THEN 2
            WHEN 'C5' THEN 3
            WHEN 'C6' THEN 4
            WHEN 'PRE CASTIGO' THEN 5
            WHEN 'F1' THEN 6
            WHEN 'F2' THEN 7
            WHEN 'F3' THEN 8
            WHEN 'F4' THEN 9
            WHEN 'TOTAL F1 - F4' THEN 10
            ELSE 11
        END
    """


def _load_rows(periodo: str, version: str) -> list[dict]:
    """Todas las filas de la fecha, sin filtros de zona / ejecutivo / bloque."""
    bloques, ponderadores, rows = run_query_sets(_sc_tardia_sql(version), (periodo,))[-3:]
    active_blocks = _active_blocks_by_executive(bloques)
    level_1_weights = _level_1_weights(ponderadores)

    response: list[dict] = []
    for row in rows:
        response.append(
            {
                "periodo": periodo,
                "reporte": row.get("reporte") or "",
                "bloque": row.get("bloque") or "",
                "ejecutivo": row.get("ejecutivo") or "SIN EJECUTIVO",
                "zona": row.get("zona") or "",
                "deuda_asignada": float(row.get("deuda_asignada") or 0),
                "monto_meta_cont": float(row.get("monto_meta_cont") or 0),
                "contenido": float(row.get("contenido") or 0),
                "monto_meta_norm": float(row.get("monto_meta_norm") or 0),
                "normalizado": float(row.get("normalizado") or 0),
                "cantidad_casos": int(row.get("cantidad_casos") or 0),
                "pond_n2": row.get("pond_n2"),
                "pond_n3_cont": row.get("pond_n3_cont"),
                "pond_n3_norm": row.get("pond_n3_norm"),
                "bloques_activos": active_blocks.get(_executive_key(row.get("ejecutivo")), []),
                "ponderadores_nivel_1": level_1_weights,
            }
        )

    response.sort(key=lambda x: (x["ejecutivo"], x["zona"], _block_index(x["bloque"])))
    return response


def _rows_from_query(filters: dict) -> list[dict]:
    periodo = _period_date(filters.get("periodo"))
    version = _period_version(filters.get("periodo"))
    rows = cached(("sc_tardia", "rows", periodo, version), lambda: _load_rows(periodo, version))

    # Los filtros actuan sobre el resultado ya agregado, asi que se aplican en memoria
    # (sin distinguir mayusculas, igual que el collation de la base).
    for campo, valor in (
        ("zona", filters.get("zona")),
        ("ejecutivo", filters.get("ejecutivo")),
        ("bloque", filters.get("ciclo")),
    ):
        buscado = _clean_text(valor).upper()
        if buscado:
            rows = [row for row in rows if row[campo].strip().upper() == buscado]

    return [dict(row) for row in rows]


def _num(value) -> float:
    return float(value or 0)


def _cap_pct(value: float) -> float:
    return max(0.0, min(CUMPLIMIENTO_MAX, value))


def _capped_pct(numerador, denominador) -> float:
    den = _num(denominador)
    if not den:
        return 0.0
    return _cap_pct(_num(numerador) / den * 100.0)


def _row_compliance(row: dict) -> float:
    """Cumplimiento de un bloque. C1 - C2 y C3 combinan contencion y normalizacion con los
    ponderadores nivel 3 de la tabla de metas; el resto es solo contencion."""
    cont = _capped_pct(row.get("contenido"), row.get("monto_meta_cont"))
    norm = _capped_pct(row.get("normalizado"), row.get("monto_meta_norm"))
    peso_cont = _num(row.get("pond_n3_cont"))
    peso_norm = _num(row.get("pond_n3_norm"))
    if row.get("bloque") in BLOQUES_CON_NORMALIZACION and _num(row.get("monto_meta_norm")) > 0 and peso_cont + peso_norm > 0:
        return _cap_pct(((cont * peso_cont) + (norm * peso_norm)) / (peso_cont + peso_norm))
    return cont


def get_cycle_view(filters: dict) -> list[dict]:
    rows = _rows_from_query(filters)
    for row in rows:
        row["pct_contencion"] = _capped_pct(row["contenido"], row["monto_meta_cont"])
        row["pct_normalizacion"] = _capped_pct(row["normalizado"], row["monto_meta_norm"])
        row["cumplimiento_operativo"] = _row_compliance(row)
    return rows


def get_general_view(filters: dict) -> list[dict]:
    """Una fila por ejecutivo con el cumplimiento de cada bloque y el cumplimiento final."""
    rows = _rows_from_query(filters)

    # Ponderador nivel 2 de cada bloque de mora tardia (es el mismo para todos los ejecutivos del mes).
    peso_nivel_2: dict[str, float] = {}
    for row in rows:
        if row.get("pond_n2") is not None:
            peso_nivel_2[row["bloque"]] = _num(row["pond_n2"])

    grouped: dict[str, dict] = {}
    for row in rows:
        current = grouped.setdefault(
            row["ejecutivo"],
            {
                "ejecutivo": row["ejecutivo"],
                "casos_asignados": 0,
                "sumas": {},
                "bloques_activos": set(),
                "ponderadores_nivel_1": {"PTC": 0.0, "STOCK": 0.0},
            },
        )
        # C1 y C2 ya vienen sumados en el consolidado de altas cuantias.
        if row["bloque"] not in ("C1", "C2"):
            current["casos_asignados"] += int(row.get("cantidad_casos") or 0)
        # Se suma primero y se divide despues: el ejecutivo puede tener el bloque en mas de una fila.
        suma = current["sumas"].setdefault(
            row["bloque"],
            {
                "bloque": row["bloque"],
                "contenido": 0.0,
                "monto_meta_cont": 0.0,
                "normalizado": 0.0,
                "monto_meta_norm": 0.0,
                "pond_n3_cont": row.get("pond_n3_cont"),
                "pond_n3_norm": row.get("pond_n3_norm"),
            },
        )
        for campo in ("contenido", "monto_meta_cont", "normalizado", "monto_meta_norm"):
            suma[campo] += _num(row.get(campo))
        current["bloques_activos"].update(row.get("bloques_activos") or [])
        current["ponderadores_nivel_1"] = row.get("ponderadores_nivel_1") or current["ponderadores_nivel_1"]

    response: list[dict] = []
    for item in grouped.values():
        bloques = {suma["bloque"]: _row_compliance(suma) for suma in item["sumas"].values()}
        activos = item["bloques_activos"]
        mora_blocks = [b for b in MORA_TARDIA_BLOCKS if b in activos or b in bloques]
        tiene_castigo = CASTIGO_TOTAL_BLOCK in activos or CASTIGO_TOTAL_BLOCK in bloques

        # Mora tardia = promedio de los bloques activos ponderado por nivel 2 (se re-normaliza sobre los activos).
        peso_total = sum(peso_nivel_2.get(b, 0.0) for b in mora_blocks)
        if not mora_blocks:
            mora = 0.0
        elif peso_total > 0:
            mora = sum(bloques.get(b, 0.0) * peso_nivel_2.get(b, 0.0) for b in mora_blocks) / peso_total
        else:
            mora = sum(bloques.get(b, 0.0) for b in mora_blocks) / len(mora_blocks)
        castigo = bloques.get(CASTIGO_TOTAL_BLOCK, 0.0)

        pesos = item["ponderadores_nivel_1"]
        if ALTAS_CUANTIAS_BLOCK in activos or ALTAS_CUANTIAS_BLOCK in bloques:
            # Altas cuantias se mide solo por su bloque (contencion + normalizacion C1_C2).
            cumplimiento = bloques.get(ALTAS_CUANTIAS_BLOCK, 0.0)
        elif mora_blocks and tiene_castigo:
            cumplimiento = (mora * _num(pesos.get("PTC")) / 100.0) + (castigo * _num(pesos.get("STOCK")) / 100.0)
        elif mora_blocks:
            cumplimiento = mora
        elif tiene_castigo:
            cumplimiento = castigo
        else:
            cumplimiento = 0.0

        response.append(
            {
                "ejecutivo": item["ejecutivo"],
                "casos_asignados": item["casos_asignados"],
                "bloques": bloques,
                "ponderadores_nivel_1": pesos,
                "cumplimiento_operativo": _cap_pct(cumplimiento),
            }
        )

    response.sort(key=lambda x: x["cumplimiento_operativo"], reverse=True)
    return response


@cached_view
def get_metas(filters: dict) -> list[dict]:
    """Metas activas del mes de la fecha consultada (dbo.stc_metas_mensuales), para el panel de metas."""
    periodo = _period_date(filters.get("periodo"))
    sql = """
    SELECT
        LTRIM(RTRIM(variable)) AS variable,
        CAST(meta_valor AS float) AS meta_valor,
        LTRIM(RTRIM(meta_tipo)) AS meta_tipo,
        CAST(ponderador_nivel_1_pct AS float) AS ponderador_nivel_1_pct,
        CAST(ponderador_nivel_2_pct AS float) AS ponderador_nivel_2_pct,
        CAST(ponderador_nivel_3_pct AS float) AS ponderador_nivel_3_pct
    FROM dbo.stc_metas_mensuales
    WHERE periodo = DATEFROMPARTS(YEAR(CAST(? AS DATE)), MONTH(CAST(? AS DATE)), 1)
      AND activo = 1
    """
    rows = [
        {
            "periodo": periodo,
            "variable": row.get("variable") or "",
            "meta_valor": row.get("meta_valor"),
            "meta_tipo": row.get("meta_tipo") or "",
            "ponderador_nivel_1_pct": row.get("ponderador_nivel_1_pct"),
            "ponderador_nivel_2_pct": row.get("ponderador_nivel_2_pct"),
            "ponderador_nivel_3_pct": row.get("ponderador_nivel_3_pct"),
        }
        for row in run_query_sets(sql, (periodo, periodo))[-1]
    ]
    # Mismo orden que la tabla de metas del negocio; las variables no listadas (castigo) van al final.
    orden = {variable: idx for idx, variable in enumerate(METAS_ORDER)}
    rows.sort(key=lambda r: (orden.get(r["variable"], len(orden)), r["variable"]))
    return rows


def _load_filter_lists() -> dict:
    """Fechas, zonas y ejecutivos de toda la sabana, en un solo viaje a la base."""
    sql = f"""
    SET NOCOUNT ON;

    SELECT DISTINCT CONVERT(char(10), fecha, 126) AS valor
    FROM dbo.vw_stc_sabana_avance
    WHERE fecha IS NOT NULL
    ORDER BY valor DESC;

    SELECT DISTINCT {_zona_sql("zona")} AS valor
    FROM dbo.vw_stc_sabana_avance
    WHERE zona IS NOT NULL AND LTRIM(RTRIM(zona)) <> ''
    ORDER BY valor;

    SELECT DISTINCT LTRIM(RTRIM(ejecutivo)) AS valor
    FROM dbo.vw_stc_sabana_avance
    WHERE ejecutivo IS NOT NULL AND LTRIM(RTRIM(ejecutivo)) <> ''
    ORDER BY valor;

    -- Fechas con carga de pre-cierre (la vista existe desde SQL/sct_precierre.sql).
    IF OBJECT_ID('dbo.vw_stc_sabana_avance_precierre', 'V') IS NOT NULL
        SELECT DISTINCT CONVERT(char(10), fecha, 126) AS valor
        FROM dbo.vw_stc_sabana_avance_precierre
        WHERE fecha IS NOT NULL;
    ELSE
        SELECT CAST(NULL AS char(10)) AS valor WHERE 1 = 0;
    """
    periodos, zonas, ejecutivos, precierres = run_query_sets(sql)[-4:]
    con_precierre = {r["valor"] for r in precierres if r.get("valor")}
    fechas: list[str] = []
    for fecha in (r["valor"] for r in periodos if r.get("valor")):
        if fecha in con_precierre:
            fechas += [f"{fecha} (Cierre)", f"{fecha} (Pre-cierre)"]
        else:
            fechas.append(fecha)
    return {
        "periodos": fechas,
        "zonas": [r["valor"] for r in zonas if r.get("valor")],
        "ejecutivos": [r["valor"] for r in ejecutivos if r.get("valor")],
    }


def _filter_lists() -> dict:
    return cached(("sc_tardia", "filtros"), _load_filter_lists)


def get_filter_values(periodo: str | None = None, zona: str | None = None) -> dict:
    listas = _filter_lists()
    if periodo:
        # Con fecha de consulta: exactamente los ejecutivos que aparecen en la tabla (misma fecha y zona).
        rows = _rows_from_query({"periodo": periodo, "zona": zona})
        ejecutivos = sorted({row["ejecutivo"] for row in rows if row.get("ejecutivo")})
    else:
        ejecutivos = list(listas["ejecutivos"])

    return {
        "periodos": list(listas["periodos"]),
        "tramos": BLOCK_ORDER,
        "aperturas": [],
        "ejecutivos": ejecutivos,
        "zonas": list(listas["zonas"]),
    }
