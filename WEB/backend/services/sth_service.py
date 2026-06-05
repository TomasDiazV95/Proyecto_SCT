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
        "ciclos": [1, 2, 3, 4, 5, 6],
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
                CAST(b.fld_Contenido AS INT) AS contenido,
                CAST(b.[fld_MM$ Monto] AS FLOAT) AS monto
            FROM dbo.tmp_bench_STH b
            LEFT JOIN dbo.tmp_carterizado_STH c
                ON b.fld_Rut = c.rut
               AND c.mes_carterizado = ?
            WHERE b.fecha_carga = (
                SELECT MIN(t.fecha_carga)
                FROM dbo.tmp_bench_STH t
                WHERE t.fecha_carga BETWEEN ? AND EOMONTH(?)
            )
              AND b.[fld_Producto cliente] = ?
              AND b.fld_Empresa = ?
              AND CAST(b.fld_Ciclo AS INT) BETWEEN 1 AND 6
        )
        SELECT
            base.ejecutivo,
            CAST(0 AS INT) AS ciclo,
            SUM(base.monto) AS deuda_asignada,
            SUM(CASE WHEN base.contenido = 1 THEN base.monto ELSE 0 END) AS saldo_contenido,
            m.meta_contenido_pct,
            m.ponderador_nivel_1_pct
        FROM base
        LEFT JOIN dbo.sth_metas_mensuales m
          ON m.periodo = ?
         AND m.producto = ?
         AND m.tramo = 'Multiciclo'
         AND m.activo = 1
        GROUP BY base.ejecutivo, m.meta_contenido_pct, m.ponderador_nivel_1_pct
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
               AND c.mes_carterizado = ?
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

    return {
        "periodos": periodos,
        "ejecutivos": ejecutivos,
        "productos": PRODUCT_ORDER,
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
                row_exec["cumplimiento_final"] = float(ciclos_data[0].get("cumplimiento_meta") or 0)

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
