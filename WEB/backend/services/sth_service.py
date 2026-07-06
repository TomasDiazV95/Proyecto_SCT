from __future__ import annotations

from datetime import date

from database import run_query


PRODUCT_CONFIG = {
    "hipotecario": {
        "nombre_meta": "Contención Hipotecario",
        "producto_cliente": "Hipoteca+FFGG",
        "empresa": "PHOENIX HIPOTECARIO",
        "ciclos": [1, 2, 3],
    },
    "consumo": {
        "nombre_meta": "Contención Consumo",
        "producto_cliente": "Consumo",
        "empresa": "PHOENIX CONSUMO",
        "ciclos": [1, 2],
    },
    "pyme": {
        "nombre_meta": "Pyme",
        "producto_cliente": "Pyme",
        "empresa": "PHOENIX Pyme",
        "ciclos": [1, 2, 3],
    },
    "tarjeta": {
        "nombre_meta": "Tarjeta",
        "producto_cliente": "Consumo",
        "empresa": "PHOENIX TC",
        "ciclos": [0, 99],
    },
}

PRODUCT_ORDER = ["hipotecario", "consumo", "pyme", "tarjeta"]
GENERAL_PRODUCT_ORDER = {
    "hipotecario": 1,
    "consumo": 2,
    "pyme": 3,
    "tarjeta": 4,
}
TRAMO_ORDER = {
    "Ciclo 1": 1,
    "Ciclo 2": 2,
    "Ciclo 3": 3,
    "Multiciclo": 4,
}



def _period_start(periodo: str | None) -> str:
    if periodo:
        text = str(periodo).strip()
        if len(text) >= 10:
            return text[:10]
        return text

    sql = """
    SELECT CONVERT(char(10), MAX(DATEFROMPARTS(YEAR(fecha_carga), MONTH(fecha_carga), 1)), 126) AS periodo
    FROM dbo.tmp_bench_STH
    """
    rows = run_query(sql)
    return (rows[0].get("periodo") if rows else None) or date.today().replace(day=1).isoformat()


def _safe_div(num: float, den: float) -> float:
    if den is None or den == 0:
        return 0.0
    return (num / den) * 100.0


def _cap(value: float, max_value: float = 130.0) -> float:
    return max(0.0, min(max_value, value))


def _cumplimiento_meta(pct_real: float, meta: float) -> float:
    if meta is None or meta <= 0:
        return 0.0
    return _cap(_safe_div(pct_real, meta))


def _tramo_meta(product_key: str, ciclo: int) -> str:
    if product_key == "tarjeta":
        if ciclo == 0:
            return "Ciclo 0"
        return "Multiciclo"
    return f"Ciclo {ciclo}"


def _build_detail_for_product(periodo: str, product_key: str) -> dict:
    config = PRODUCT_CONFIG[product_key]
    ciclos = config["ciclos"]

    if product_key == "tarjeta":
        sql = """
        WITH base AS (
            SELECT
                ISNULL(NULLIF(LTRIM(RTRIM(c.ejecutivo)), ''), 'Grupal') AS ejecutivo,
                CASE WHEN CAST(b.fld_Ciclo AS INT) = 0 THEN 0 ELSE 99 END AS ciclo,
                CASE WHEN CAST(b.fld_Ciclo AS INT) = 0 THEN 'Ciclo 0' ELSE 'Multiciclo' END AS tramo,
                CAST(b.fld_Contenido AS INT) AS contenido,
                CAST(b.[fld_MM$ Monto] AS FLOAT) AS monto
            FROM dbo.tmp_bench_STH b
            LEFT JOIN dbo.tmp_carterizado_STH c
                ON b.fld_Rut = c.rut
               AND CONVERT(date, c.mes_carterizado) = ?
            WHERE b.fecha_carga = (
                SELECT MIN(t.fecha_carga)
                FROM dbo.tmp_bench_STH t
                WHERE t.fecha_carga BETWEEN ? AND EOMONTH(?)
            )
              AND b.[fld_Producto cliente] = ?
              AND b.fld_Empresa = ?
              AND (CAST(b.fld_Ciclo AS INT) = 0 OR CAST(b.fld_Ciclo AS INT) BETWEEN 1 AND 6)
        )
        SELECT
            base.ejecutivo,
            base.ciclo,
            base.tramo,
            SUM(base.monto) AS deuda_asignada,
            SUM(CASE WHEN base.contenido = 1 THEN base.monto ELSE 0 END) AS saldo_contenido,
            m.meta_contenido_pct,
            m.ponderador_nivel_1_pct
        FROM base
        LEFT JOIN dbo.sth_metas_mensuales m
          ON m.periodo = ?
         AND m.producto = ?
         AND m.tramo = base.tramo
         AND m.activo = 1
        GROUP BY base.ejecutivo, base.ciclo, base.tramo, m.meta_contenido_pct, m.ponderador_nivel_1_pct
        """
        params = [periodo, periodo, periodo, config["producto_cliente"], config["empresa"], periodo, config["nombre_meta"]]
        rows = run_query(sql, tuple(params))
    else:
        ciclo_marks = ",".join("?" for _ in ciclos)
        extra_cycle_exec_filter = ""
        params_exec: list[str] = []

        if product_key == "hipotecario":
            extra_cycle_exec_filter = """
            AND EXISTS (
                SELECT 1
                FROM dbo.sth_hipotecario_ejecutivos_ciclo hc
                WHERE hc.periodo = ?
                    AND hc.ciclo = CAST(b.fld_Ciclo AS INT)
                    AND LTRIM(RTRIM(hc.ejecutivo)) =
                        ISNULL(NULLIF(LTRIM(RTRIM(c.ejecutivo)), ''), 'Grupal')
                    AND hc.activo = 1
            )
            """
            params_exec.append(periodo)

        sql = f"""
        WITH base AS (
            SELECT
                ISNULL(NULLIF(LTRIM(RTRIM(c.ejecutivo)), ''), 'Grupal') AS ejecutivo,
                CAST(b.fld_Ciclo AS INT) AS ciclo,
                CAST(b.fld_Contenido AS INT) AS contenido,
                CAST(b.[fld_MM$ Monto] AS FLOAT) AS monto
            FROM dbo.tmp_bench_STH b
            LEFT JOIN dbo.tmp_carterizado_STH c
                ON b.fld_Rut = c.rut
               AND CONVERT(date, c.mes_carterizado) = ?
            WHERE b.fecha_carga = (
                SELECT MIN(t.fecha_carga)
                FROM dbo.tmp_bench_STH t
                WHERE t.fecha_carga BETWEEN ? AND EOMONTH(?)
            )
              AND b.[fld_Producto cliente] = ?
              AND b.fld_Empresa = ?
              AND CAST(b.fld_Ciclo AS INT) IN ({ciclo_marks})
              {extra_cycle_exec_filter}
        ),
        agg AS (
            SELECT
                ejecutivo,
                ciclo,
                SUM(monto) AS deuda_asignada,
                SUM(CASE WHEN contenido = 1 THEN monto ELSE 0 END) AS saldo_contenido
            FROM base
            GROUP BY ejecutivo, ciclo
        )
        SELECT
            agg.ejecutivo,
            agg.ciclo,
            agg.deuda_asignada,
            agg.saldo_contenido,
            m.meta_contenido_pct,
            m.ponderador_nivel_1_pct
        FROM agg
        LEFT JOIN dbo.sth_metas_mensuales m
          ON m.periodo = ?
         AND m.producto = ?
         AND m.tramo = CONCAT('Ciclo ', agg.ciclo)
         AND m.activo = 1
        """

        params = [periodo, periodo, periodo, config["producto_cliente"], config["empresa"], *ciclos, *params_exec, periodo, config["nombre_meta"]]
        rows = run_query(sql, tuple(params))

    detail_rows: list[dict] = []
    for row in rows:
        deuda = float(row.get("deuda_asignada") or 0)
        saldo = float(row.get("saldo_contenido") or 0)
        pct = _safe_div(saldo, deuda)
        meta = float(row.get("meta_contenido_pct") or 0)
        ponderador = float(row.get("ponderador_nivel_1_pct") or 0)

        detail_rows.append(
            {
                "producto": product_key,
                "producto_meta": config["nombre_meta"],
                "ejecutivo": row.get("ejecutivo") or "Grupal",
                "ciclo": int(row.get("ciclo") or 0),
                "tramo": _tramo_meta(product_key, int(row.get("ciclo") or 0)),
                "deuda_asignada": deuda,
                "saldo_contenido": saldo,
                "porcentaje_contenido": pct,
                "meta_contenido_pct": meta,
                "ponderador_nivel_1_pct": ponderador,
                "cumplimiento_meta": _cumplimiento_meta(pct, meta),
                "cumplimiento_final": _cumplimiento_meta(pct, meta),
            }
        )

    detail_rows.sort(key=lambda x: (x["ciclo"], x["ejecutivo"]))

    return {
        "producto": product_key,
        "producto_meta": config["nombre_meta"],
        "rows": detail_rows,
    }


def get_filter_values() -> dict:
    sql_periodos = """
    SELECT DISTINCT CONVERT(char(10), DATEFROMPARTS(YEAR(fecha_carga), MONTH(fecha_carga), 1), 126) AS periodo
    FROM dbo.tmp_bench_STH
    WHERE fecha_carga IS NOT NULL
    ORDER BY periodo DESC
    """
    periodos = [r["periodo"] for r in run_query(sql_periodos) if r.get("periodo")]

    sql_ejecutivos = """
    SELECT DISTINCT ISNULL(NULLIF(LTRIM(RTRIM(ejecutivo)), ''), 'Grupal') AS ejecutivo
    FROM dbo.tmp_carterizado_STH
    ORDER BY ejecutivo
    """
    ejecutivos = [r["ejecutivo"] for r in run_query(sql_ejecutivos) if r.get("ejecutivo")]

    productos_detalle = sorted({config["producto_cliente"] for config in PRODUCT_CONFIG.values()})

    return {
        "periodos": periodos,
        "ejecutivos": ejecutivos,
        "productos": PRODUCT_ORDER,
        "productos_detalle": productos_detalle,
        "ciclos": list(range(0, 7)),
    }


def get_detail_view(filters: dict) -> list[dict]:
    periodo = _period_start(filters.get("periodo"))
    ejecutivo_filter = (filters.get("ejecutivo") or "").strip().lower()

    result: list[dict] = []
    for product in PRODUCT_ORDER:
        data = _build_detail_for_product(periodo, product)
        rows = data["rows"]

        if product in ("hipotecario", "consumo"):
            rows = [r for r in rows if (r.get("ejecutivo") or "").strip().lower() != "grupal"]

        if ejecutivo_filter:
            rows = [r for r in rows if (r.get("ejecutivo") or "").strip().lower() == ejecutivo_filter]

        cycle_totals: list[dict] = []
        grouped: dict[int, dict] = {}
        for row in rows:
            ciclo = int(row["ciclo"])
            item = grouped.setdefault(
                ciclo,
                {
                    "ciclo": ciclo,
                    "tramo": _tramo_meta(product, ciclo),
                    "deuda_asignada": 0.0,
                    "saldo_contenido": 0.0,
                    "meta_contenido_pct": float(row.get("meta_contenido_pct") or 0),
                    "ponderador_nivel_1_pct": float(row.get("ponderador_nivel_1_pct") or 0),
                },
            )
            item["deuda_asignada"] += float(row.get("deuda_asignada") or 0)
            item["saldo_contenido"] += float(row.get("saldo_contenido") or 0)

        for ciclo in sorted(grouped.keys()):
            item = grouped[ciclo]
            pct = _safe_div(item["saldo_contenido"], item["deuda_asignada"])
            cumplimiento_meta = _cumplimiento_meta(pct, item["meta_contenido_pct"])
            cycle_totals.append(
                {
                    "ciclo": ciclo,
                    "tramo": item["tramo"],
                    "deuda_asignada": item["deuda_asignada"],
                    "saldo_contenido": item["saldo_contenido"],
                    "porcentaje_contenido": pct,
                    "meta_contenido_pct": item["meta_contenido_pct"],
                    "ponderador_nivel_1_pct": item["ponderador_nivel_1_pct"],
                    "cumplimiento_meta": cumplimiento_meta,
                    "cumplimiento_final": cumplimiento_meta,
                }
            )

        by_ejecutivo: dict[str, dict] = {}
        for row in rows:
            ejecutivo = row["ejecutivo"]
            row_exec = by_ejecutivo.setdefault(
                ejecutivo,
                {
                    "ejecutivo": ejecutivo,
                    "ciclos": {},
                },
            )
            row_exec["ciclos"][str(row["ciclo"])] = row

        for row_exec in by_ejecutivo.values():
            ciclos_data = list(row_exec["ciclos"].values())
            if not ciclos_data:
                row_exec["cumplimiento_final"] = 0.0
                continue

            if product == "consumo":
                row_exec["cumplimiento_final"] = _cap(
                    sum(float(x.get("cumplimiento_meta") or 0) * (float(x.get("ponderador_nivel_1_pct") or 0) / 100.0) for x in ciclos_data)
                )
            elif product == "pyme":
                row_exec["cumplimiento_final"] = _cap(
                    sum(float(x.get("cumplimiento_meta") or 0) * (float(x.get("ponderador_nivel_1_pct") or 0) / 100.0) for x in ciclos_data)
                )
            elif product == "hipotecario":
                elegido = max(ciclos_data, key=lambda x: float(x.get("deuda_asignada") or 0))
                row_exec["cumplimiento_final"] = float(elegido.get("cumplimiento_meta") or 0)
            else:
                row_exec["cumplimiento_final"] = _cap(
                    sum(float(x.get("cumplimiento_meta") or 0) * (float(x.get("ponderador_nivel_1_pct") or 0) / 100.0) for x in ciclos_data)
                )

            for data in ciclos_data:
                data["cumplimiento_final"] = row_exec["cumplimiento_final"]

        pivot_rows = list(by_ejecutivo.values())
        def _min_ciclo(row):
            ciclos = [int(c) for c in row["ciclos"].keys()]
            return min(ciclos) if ciclos else 99

        if product == "hipotecario":
            pivot_rows.sort(
                key=lambda x: (
                    _min_ciclo(x),
                    str(x["ejecutivo"] or "")
                )
            )
        else:
            pivot_rows.sort(
                key=lambda x: (
                    0 if str(x["ejecutivo"]).strip().lower() == "grupal" else 1,
                    str(x["ejecutivo"] or "")
                )
            )

        deuda_total_final = 0.0
        suma_final_ponderada = 0.0
        for row_exec in pivot_rows:
            deuda_ref = sum(float(x.get("deuda_asignada") or 0) for x in row_exec["ciclos"].values())
            deuda_total_final += deuda_ref
            suma_final_ponderada += float(row_exec.get("cumplimiento_final") or 0) * deuda_ref

        total_cumplimiento_final = (suma_final_ponderada / deuda_total_final) if deuda_total_final else 0.0

        for item in cycle_totals:
            item["cumplimiento_final"] = total_cumplimiento_final

        result.append(
            {
                "producto": product,
                "producto_meta": data["producto_meta"],
                "periodo": periodo,
                "rows": rows,
                "pivot_rows": pivot_rows,
                "ciclos": sorted(grouped.keys()),
                "totales_por_ciclo": cycle_totals,
                "cumplimiento_final_bloque": total_cumplimiento_final,
            }
        )

    return result


def _get_operations_detail_view_legacy(filters: dict) -> dict:
    periodo = _period_start(filters.get("periodo"))
    operacion = str(filters.get("operacion") or "").strip()
    ejecutivo = str(filters.get("ejecutivo") or "").strip()
    producto = str(filters.get("producto") or "").strip()
    ciclo = str(filters.get("ciclo") or "").strip()
    contenido = str(filters.get("contenido") or "").strip()
    page = max(1, int(filters.get("page") or 1))
    page_size = min(500, max(1, int(filters.get("page_size") or 100)))
    offset = (page - 1) * page_size

    where_clauses = []
    params: list = [periodo] * 7

    if operacion:
        where_clauses.append("CAST(base.operacion AS VARCHAR(100)) LIKE ?")
        params.append(f"%{operacion}%")
    if ejecutivo:
        where_clauses.append("base.ejecutivo = ?")
        params.append(ejecutivo)
    if producto:
        where_clauses.append("base.producto = ?")
        params.append(producto)
    if ciclo:
        where_clauses.append("CAST(base.ciclo AS VARCHAR(20)) = ?")
        params.append(ciclo)
    if contenido in {"0", "1"}:
        where_clauses.append("base.contenido = ?")
        params.append(int(contenido))
    extra_where = ""
    if where_clauses:
        extra_where = "WHERE " + " AND ".join(where_clauses)

    sql = f"""
    WITH asignacion AS (
        SELECT
            bench.fld_Rut AS rut,
            bench.fld_Operaciones AS operacion,
            bench.fld_Contenido AS contenido,
            bench.fld_Ciclo AS ciclo,
            bench.[fld_MM$ Monto] AS deuda,
            bench.[fld_Producto cliente] AS producto
        FROM dbo.tmp_bench_STH bench
        WHERE bench.fecha_carga = (
            SELECT MIN(t.fecha_carga)
            FROM dbo.tmp_bench_STH t
            WHERE t.fecha_carga >= ?
              AND t.fecha_carga < DATEADD(MONTH, 1, CAST(? AS date))
        )
    ),
    gestiones AS (
        SELECT
            g.rut,
            g.UsuarioGestion,
            g.RespuestaGestion,
            g.GestionFecha,
            g.GestionHora,
            g.telefono,
            CASE g.RespuestaGestion
                WHEN 'COMPROMISO DE PAGO TELEFONICO' THEN 1
                WHEN 'COMPROMISO HTML' THEN 2
                WHEN 'OFERTA HIPOTECARIA' THEN 3
                WHEN 'OFERTA DERIVACIÓN EN LINEA' THEN 4
                WHEN 'OFERTA CAMPAÑA' THEN 5
                WHEN 'APOYO EN LINEA CAMPAÑA HB' THEN 6
                WHEN 'OFERTA CAMPAÑA WHATSAPP' THEN 7
                WHEN 'POSTERGA FECHA DE PAGO' THEN 8
                WHEN 'SOLICITA RENEGOCIAR' THEN 9
                WHEN 'TRAMITANDO CAMPAÑA RENEGOCIACION' THEN 10
                WHEN 'CLIENTE PAGO O REGULARIZO' THEN 11
                WHEN 'CLIENTE TITULAR CORTA LLAMADO' THEN 12
                WHEN 'RECHAZA PAGAR' THEN 13
                WHEN 'POSTERGAR LLAMADO' THEN 14
                WHEN 'CESANTE' THEN 15
                WHEN 'CIERRE DE PRODUCTO' THEN 16
                WHEN 'DESCONOCE DEUDA' THEN 17
                WHEN 'TÉRMINO DE CONTRATO' THEN 18
                WHEN 'FRAUDE' THEN 19
                WHEN 'ENFERMEDAD GRAVE - PROPIA' THEN 20
                WHEN 'SOBRECARGA FINANCIERA POR IMPREVISTOS MAYORES' THEN 21
                WHEN 'ENFERMEDAD PROPIA O TERCERO' THEN 22
                WHEN 'ENFERMEDAD GRAVE - DE UN FAMILIAR DIRECTO' THEN 23
                WHEN 'EMERGENCIA FAMILIAR RELEVANTE - FALLECIMIENTO' THEN 24
                WHEN 'EMERGENCIA FAMILIAR RELEVANTE - ACCIDENTES' THEN 25
                WHEN 'GASTOS MÉDICOS O URGENCIAS NO CUBIERTAS POR S' THEN 26
                WHEN 'REDUCCIÓN DE JORNADA' THEN 27
                WHEN 'TRAMITANDO SEGURO' THEN 28
                WHEN 'CAÍDA DE COMISIONES' THEN 29
                WHEN 'INUBICABLE' THEN 30
                ELSE 999
            END AS peso_gestion
        FROM dbo.tmp_GEST_CRM g
        WHERE g.cartera = 530
          AND g.GestionFecha >= ?
          AND g.GestionFecha < DATEADD(MONTH, 1, CAST(? AS date))
          AND g.AccionGestion = 'CONTACTO TITULAR'
    ),
    mejor_gestion AS (
        SELECT rut, UsuarioGestion, RespuestaGestion, GestionFecha, telefono
        FROM (
            SELECT
                gestiones.*,
                ROW_NUMBER() OVER (
                    PARTITION BY rut
                    ORDER BY peso_gestion ASC, GestionFecha DESC, GestionHora DESC
                ) AS rn
            FROM gestiones
        ) ranking
        WHERE rn = 1
    ),
    compromisos AS (
        SELECT RutCliente, FechaCompromiso
        FROM (
            SELECT
                fc.RutCliente,
                fc.FechaCompromiso,
                ROW_NUMBER() OVER (
                    PARTITION BY fc.RutCliente
                    ORDER BY fc.FechaGestion DESC, fc.FechaCompromiso DESC
                ) AS rn
            FROM dbo.tmp_FECHA_COMPROMISO_CRM fc
            WHERE fc.FechaGestion >= ?
              AND fc.FechaGestion < DATEADD(MONTH, 1, CAST(? AS date))
        ) ranking
        WHERE rn = 1
    ),
    carterizado AS (
        SELECT
            car.rut,
            MAX(NULLIF(LTRIM(RTRIM(car.ejecutivo)), '')) AS ejecutivo
        FROM dbo.tmp_carterizado_STH car
        WHERE CONVERT(date, car.mes_carterizado) = ?
        GROUP BY car.rut
    ),
    base AS (
        SELECT
            bench.rut,
            ISNULL(NULLIF(LTRIM(RTRIM(car.ejecutivo)), ''), 'Grupal') AS ejecutivo,
            bench.operacion,
            CASE WHEN TRY_CAST(bench.contenido AS INT) <> 0 THEN 1 ELSE 0 END AS contenido,
            TRY_CAST(bench.ciclo AS INT) AS ciclo,
            CAST(ISNULL(bench.deuda, 0) AS FLOAT) AS deuda,
            bench.producto
        FROM asignacion bench
        LEFT JOIN carterizado car
            ON bench.rut = car.rut
    ),
    filtered AS (
        SELECT *
        FROM base
        {extra_where}
    ),
    paged AS (
        SELECT
            filtered.*,
            COUNT_BIG(1) OVER () AS total_count
        FROM filtered
        ORDER BY ciclo, deuda DESC, operacion
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    )
    SELECT
        paged.*,
        mg.UsuarioGestion AS usuario_gestion,
        mg.RespuestaGestion AS mejor_gestion,
        mg.GestionFecha AS gestion_fecha,
        mg.telefono AS telefono_gestion,
        comp.FechaCompromiso AS fecha_compromiso
    FROM paged
    LEFT JOIN mejor_gestion mg
        ON paged.rut = mg.rut
    LEFT JOIN compromisos comp
        ON paged.rut = comp.RutCliente
    ORDER BY paged.ciclo, paged.deuda DESC, paged.operacion
    """

    query_params = [*params, offset, page_size]
    rows = []
    total = 0
    for row in run_query(sql, tuple(query_params)):
        total = int(row.get("total_count") or 0)
        rows.append(
            {
                "periodo": periodo,
                "ejecutivo": row.get("ejecutivo") or "Grupal",
                "operacion": row.get("operacion"),
                "contenido": int(row.get("contenido") or 0),
                "ciclo": row.get("ciclo"),
                "deuda": float(row.get("deuda") or 0),
                "producto": row.get("producto") or "",
                "usuario_gestion": row.get("usuario_gestion") or "",
                "mejor_gestion": row.get("mejor_gestion") or "",
                "gestion_fecha": str(row.get("gestion_fecha") or ""),
                "telefono_gestion": row.get("telefono_gestion") or "",
                "fecha_compromiso": str(row.get("fecha_compromiso") or ""),
            }
        )

    return {
        "data": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_operations_detail_view(filters: dict) -> dict:
    periodo = _period_start(filters.get("periodo"))
    operacion = str(filters.get("operacion") or "").strip()
    ejecutivo = str(filters.get("ejecutivo") or "").strip()
    producto = str(filters.get("producto") or "").strip()
    ciclo = str(filters.get("ciclo") or "").strip()
    contenido = str(filters.get("contenido") or "").strip()
    page = max(1, int(filters.get("page") or 1))
    page_size = min(500, max(1, int(filters.get("page_size") or 100)))
    offset = (page - 1) * page_size

    carterizado_filter = ""
    join_type = "LEFT JOIN"
    params: list = [periodo, periodo]
    where_clauses = []

    if ejecutivo and ejecutivo.lower() != "grupal":
        carterizado_filter = "AND LTRIM(RTRIM(car.ejecutivo)) = ?"
        params.append(ejecutivo)
        join_type = "INNER JOIN"

    params.extend([periodo, periodo])

    if ejecutivo.lower() == "grupal":
        where_clauses.append("base.ejecutivo = 'Grupal'")
    if operacion:
        where_clauses.append("CAST(base.operacion AS VARCHAR(100)) LIKE ?")
        params.append(f"%{operacion}%")
    if producto:
        where_clauses.append("base.producto = ?")
        params.append(producto)
    if ciclo:
        where_clauses.append("CAST(base.ciclo AS VARCHAR(20)) = ?")
        params.append(ciclo)
    if contenido in {"0", "1"}:
        where_clauses.append("base.contenido = ?")
        params.append(int(contenido))

    extra_where = ""
    if where_clauses:
        extra_where = "WHERE " + " AND ".join(where_clauses)

    page_sql = f"""
    WITH carterizado AS (
        SELECT
            car.rut,
            MAX(NULLIF(LTRIM(RTRIM(car.ejecutivo)), '')) AS ejecutivo
        FROM dbo.tmp_carterizado_STH car
        WHERE car.mes_carterizado >= ?
          AND car.mes_carterizado < DATEADD(DAY, 1, CAST(? AS date))
          {carterizado_filter}
        GROUP BY car.rut
    ),
    base AS (
        SELECT
            bench.fld_Rut AS rut,
            ISNULL(car.ejecutivo, 'Grupal') AS ejecutivo,
            bench.fld_Operaciones AS operacion,
            CASE WHEN TRY_CAST(bench.fld_Contenido AS INT) <> 0 THEN 1 ELSE 0 END AS contenido,
            TRY_CAST(bench.fld_Ciclo AS INT) AS ciclo,
            CAST(ISNULL(bench.[fld_MM$ Monto], 0) AS FLOAT) AS deuda,
            bench.[fld_Producto cliente] AS producto
        FROM dbo.tmp_bench_STH bench
        {join_type} carterizado car
            ON bench.fld_Rut = car.rut
        WHERE bench.fecha_carga = (
            SELECT MIN(t.fecha_carga)
            FROM dbo.tmp_bench_STH t
            WHERE t.fecha_carga >= ?
              AND t.fecha_carga < DATEADD(MONTH, 1, CAST(? AS date))
        )
    )
    SELECT
        base.*,
        COUNT_BIG(1) OVER () AS total_count
    FROM base
    {extra_where}
    ORDER BY base.ciclo, base.deuda DESC, base.operacion
    OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    OPTION (RECOMPILE)
    """

    page_rows = run_query(page_sql, tuple([*params, offset, page_size]))
    total = int(page_rows[0].get("total_count") or 0) if page_rows else 0

    unique_ruts: list = []
    seen_ruts: set[str] = set()
    for row in page_rows:
        rut = row.get("rut")
        key = str(rut or "").strip()
        if key and key not in seen_ruts:
            seen_ruts.add(key)
            unique_ruts.append(rut)

    management_by_rut: dict[str, dict] = {}
    commitment_by_rut: dict[str, dict] = {}

    if unique_ruts:
        rut_marks = ",".join("?" for _ in unique_ruts)
        response_priority = [
            "COMPROMISO DE PAGO TELEFONICO",
            "COMPROMISO HTML",
            "OFERTA HIPOTECARIA",
            "OFERTA DERIVACIÓN EN LINEA",
            "OFERTA CAMPAÑA",
            "APOYO EN LINEA CAMPAÑA HB",
            "OFERTA CAMPAÑA WHATSAPP",
            "POSTERGA FECHA DE PAGO",
            "SOLICITA RENEGOCIAR",
            "TRAMITANDO CAMPAÑA RENEGOCIACION",
            "CLIENTE PAGO O REGULARIZO",
            "CLIENTE TITULAR CORTA LLAMADO",
            "RECHAZA PAGAR",
            "POSTERGAR LLAMADO",
            "CESANTE",
            "CIERRE DE PRODUCTO",
            "DESCONOCE DEUDA",
            "TÉRMINO DE CONTRATO",
            "FRAUDE",
            "ENFERMEDAD GRAVE - PROPIA",
            "SOBRECARGA FINANCIERA POR IMPREVISTOS MAYORES",
            "ENFERMEDAD PROPIA O TERCERO",
            "ENFERMEDAD GRAVE - DE UN FAMILIAR DIRECTO",
            "EMERGENCIA FAMILIAR RELEVANTE - FALLECIMIENTO",
            "EMERGENCIA FAMILIAR RELEVANTE - ACCIDENTES",
            "GASTOS MÉDICOS O URGENCIAS NO CUBIERTAS POR S",
            "REDUCCIÓN DE JORNADA",
            "TRAMITANDO SEGURO",
            "CAÍDA DE COMISIONES",
            "INUBICABLE",
        ]
        priority_cases = "\n".join(
            f"WHEN N'{response.replace("'", "''")}' THEN {position}"
            for position, response in enumerate(response_priority, start=1)
        )

        management_sql = f"""
        WITH ranked AS (
            SELECT
                g.rut,
                g.UsuarioGestion,
                g.RespuestaGestion,
                g.GestionFecha,
                g.telefono,
                ROW_NUMBER() OVER (
                    PARTITION BY g.rut
                    ORDER BY
                        CASE g.RespuestaGestion
                            {priority_cases}
                            ELSE 999
                        END,
                        g.GestionFecha DESC,
                        g.GestionHora DESC
                ) AS rn
            FROM dbo.tmp_GEST_CRM g
            WHERE g.cartera = 530
              AND g.GestionFecha >= ?
              AND g.GestionFecha < DATEADD(MONTH, 1, CAST(? AS date))
              AND g.AccionGestion = 'CONTACTO TITULAR'
              AND g.rut IN ({rut_marks})
        )
        SELECT rut, UsuarioGestion, RespuestaGestion, GestionFecha, telefono
        FROM ranked
        WHERE rn = 1
        """
        for row in run_query(management_sql, tuple([periodo, periodo, *unique_ruts])):
            management_by_rut[str(row.get("rut") or "").strip()] = row

        commitment_sql = f"""
        WITH ranked AS (
            SELECT
                fc.RutCliente,
                fc.FechaCompromiso,
                ROW_NUMBER() OVER (
                    PARTITION BY fc.RutCliente
                    ORDER BY fc.FechaGestion DESC, fc.FechaCompromiso DESC
                ) AS rn
            FROM dbo.tmp_FECHA_COMPROMISO_CRM fc
            WHERE fc.cartera = 530
              AND fc.FechaGestion >= ?
              AND fc.FechaGestion < DATEADD(MONTH, 1, CAST(? AS date))
              AND fc.RutCliente IN ({rut_marks})
        )
        SELECT RutCliente, FechaCompromiso
        FROM ranked
        WHERE rn = 1
        """
        for row in run_query(commitment_sql, tuple([periodo, periodo, *unique_ruts])):
            commitment_by_rut[str(row.get("RutCliente") or "").strip()] = row

    rows = []
    for row in page_rows:
        rut_key = str(row.get("rut") or "").strip()
        management = management_by_rut.get(rut_key, {})
        commitment = commitment_by_rut.get(rut_key, {})
        rows.append(
            {
                "periodo": periodo,
                "ejecutivo": row.get("ejecutivo") or "Grupal",
                "operacion": row.get("operacion"),
                "contenido": int(row.get("contenido") or 0),
                "ciclo": row.get("ciclo"),
                "deuda": float(row.get("deuda") or 0),
                "producto": row.get("producto") or "",
                "usuario_gestion": management.get("UsuarioGestion") or "",
                "mejor_gestion": management.get("RespuestaGestion") or "",
                "gestion_fecha": str(management.get("GestionFecha") or ""),
                "telefono_gestion": management.get("telefono") or "",
                "fecha_compromiso": str(commitment.get("FechaCompromiso") or ""),
            }
        )

    return {
        "data": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_general_view(filters: dict) -> list[dict]:
    detail = get_detail_view(filters)
    by_exec: dict[str, dict] = {}

    for block in detail:
        product = block["producto"]
        for row in block["rows"]:
            ejecutivo = row["ejecutivo"]
            if str(ejecutivo).strip().lower() == "grupal":
                continue
            current = by_exec.setdefault(
                ejecutivo,
                {
                    "ejecutivo": ejecutivo,
                    "hipotecario": None,
                    "consumo": None,
                    "pyme": None,
                    "tarjeta": None,
                    "cumplimiento_final": 0.0,
                    "producto_trabajado": "",
                    "tramo_trabajado": "",
                    "deuda_referencia": 0.0,
                },
            )

            current[product] = float(row["cumplimiento_final"])
            deuda = float(row["deuda_asignada"] or 0)
            if deuda >= float(current["deuda_referencia"]):
                current["deuda_referencia"] = deuda
                current["cumplimiento_final"] = float(row["cumplimiento_final"])
                current["producto_trabajado"] = product
                current["tramo_trabajado"] = row["tramo"]

    rows = list(by_exec.values())
    rows.sort(
        key=lambda x: (
            GENERAL_PRODUCT_ORDER.get(str(x.get("producto_trabajado") or "").strip().lower(), 99),
            TRAMO_ORDER.get(str(x.get("tramo_trabajado") or "").strip(), 99),
            -float(x.get("cumplimiento_final") or 0),
            str(x.get("ejecutivo") or ""),
        )
    )

    total_deuda = sum(float(r.get("deuda_referencia") or 0) for r in rows)
    total_cumpl = sum(float(r.get("cumplimiento_final") or 0) * float(r.get("deuda_referencia") or 0) for r in rows)
    rows.append(
        {
            "ejecutivo": "Total general",
            "hipotecario": None,
            "consumo": None,
            "pyme": None,
            "tarjeta": None,
            "cumplimiento_final": (total_cumpl / total_deuda) if total_deuda else 0.0,
            "producto_trabajado": "",
            "tramo_trabajado": "",
            "deuda_referencia": total_deuda,
        }
    )
    return rows
