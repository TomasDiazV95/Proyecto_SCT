from __future__ import annotations

from datetime import datetime

from database import run_query


TABLE = "dbo.tbl_gestiones_diarias_sct"


def _parse_date(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise RuntimeError(f"Formato de fecha no soportado: {value}")


def _parse_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        raw_values = value
    else:
        raw_values = str(value).split(",")
    return [str(item).strip() for item in raw_values if str(item).strip()]


def _add_optional_filters(where: list[str], params: list[object], filters: dict, exclude: str | None = None) -> None:
    fecha_desde = _parse_date(filters.get("fecha_desde"))
    fecha_hasta = _parse_date(filters.get("fecha_hasta"))
    values = {
        "ejecutivo": str(filters.get("ejecutivo") or "").strip(),
        "ejecutivos": _parse_list(filters.get("ejecutivos")),
        "contacto": str(filters.get("contacto") or "").strip(),
        "accion": str(filters.get("accion") or "").strip(),
        "canal": str(filters.get("canal") or "").strip(),
        "estado": str(filters.get("estado") or "").strip(),
        "tramo_mora": str(filters.get("tramo_mora") or "").strip(),
        "zona": str(filters.get("zona") or "").strip(),
    }

    if exclude != "fecha_desde" and fecha_desde:
        where.append("fecha_gestion_filtro >= CAST(? AS date)")
        params.append(fecha_desde)
    if exclude != "fecha_hasta" and fecha_hasta:
        where.append("fecha_gestion_filtro < DATEADD(day, 1, CAST(? AS date))")
        params.append(fecha_hasta)
    if exclude != "ejecutivo" and values["ejecutivos"]:
        placeholders = ",".join("?" for _ in values["ejecutivos"])
        where.append(f"cobrador_actual IN ({placeholders})")
        params.extend(values["ejecutivos"])
    elif exclude != "ejecutivo" and values["ejecutivo"]:
        where.append("cobrador_actual = ?")
        params.append(values["ejecutivo"])
    if exclude != "contacto" and values["contacto"]:
        where.append("contacto = ?")
        params.append(values["contacto"])
    if exclude != "accion" and values["accion"]:
        where.append("accion = ?")
        params.append(values["accion"])
    if exclude != "canal" and values["canal"]:
        where.append("canal = ?")
        params.append(values["canal"])
    if exclude != "estado" and values["estado"]:
        where.append("estado = ?")
        params.append(values["estado"])
    if exclude != "tramo_mora" and values["tramo_mora"]:
        where.append("tramo_mora = ?")
        params.append(values["tramo_mora"])
    if exclude != "zona" and values["zona"]:
        where.append("zona = ?")
        params.append(values["zona"])


def _distinct_filter_values(column: str, alias: str, filters: dict, exclude: str) -> list[str]:
    where = ["1 = 1"]
    params: list[object] = []
    _add_optional_filters(where, params, filters, exclude)
    where_sql = " AND ".join(where)
    rows = run_query(
        f"""
        SELECT DISTINCT {column} AS valor
        FROM {TABLE}
        WHERE {where_sql}
          AND {column} IS NOT NULL
          AND LTRIM(RTRIM({column})) <> ''
        ORDER BY valor
        """,
        tuple(params),
    )
    return [row["valor"] for row in rows if row.get("valor")]


def _sort_contact_columns(values: list[str]) -> list[str]:
    def priority(value: str) -> tuple[int, str]:
        text = value.upper().strip()
        if text == "TITULAR" or text.startswith("TITULAR "):
            return (0, text)
        if "SIN CONTACTO" in text and "TITULAR" in text:
            return (1, text)
        if "SIN CONTACTO" in text:
            return (2, text)
        if "AVAL" in text:
            return (3, text)
        return (4, text)

    return sorted(values, key=priority)


def get_filter_values(filters: dict | None = None) -> dict:
    filters = filters or {}
    date_rows = run_query(
        f"""
        SELECT
            CONVERT(char(10), MIN(fecha_gestion_filtro), 126) AS fecha_min,
            CONVERT(char(10), MAX(fecha_gestion_filtro), 126) AS fecha_max
        FROM {TABLE}
        """
    )
    return {
        "fecha_min": date_rows[0].get("fecha_min") if date_rows else None,
        "fecha_max": date_rows[0].get("fecha_max") if date_rows else None,
        "ejecutivos": _distinct_filter_values("cobrador_actual", "ejecutivo", filters, "ejecutivo"),
        "contactos": _distinct_filter_values("contacto", "contacto", filters, "contacto"),
        "acciones": _distinct_filter_values("accion", "accion", filters, "accion"),
        "canales": _distinct_filter_values("canal", "canal", filters, "canal"),
        "estados": _distinct_filter_values("estado", "estado", filters, "estado"),
        "tramos_mora": _distinct_filter_values("tramo_mora", "tramo_mora", filters, "tramo_mora"),
        "zonas": _distinct_filter_values("zona", "zona", filters, "zona"),
    }


def get_detail_view(filters: dict) -> dict:
    fecha_desde = _parse_date(filters.get("fecha_desde"))
    fecha_hasta = _parse_date(filters.get("fecha_hasta"))
    ejecutivo = str(filters.get("ejecutivo") or "").strip()
    contacto = str(filters.get("contacto") or "").strip()
    accion = str(filters.get("accion") or "").strip()
    canal = str(filters.get("canal") or "").strip()
    estado = str(filters.get("estado") or "").strip()
    tramo_mora = str(filters.get("tramo_mora") or "").strip()
    zona = str(filters.get("zona") or "").strip()
    page = max(int(filters.get("page") or 1), 1)
    page_size = min(max(int(filters.get("page_size") or 100), 1), 500)
    offset = (page - 1) * page_size

    where = ["1 = 1"]
    params: list[object] = []

    if fecha_desde:
        where.append("fecha_gestion_filtro >= CAST(? AS date)")
        params.append(fecha_desde)
    if fecha_hasta:
        where.append("fecha_gestion_filtro < DATEADD(day, 1, CAST(? AS date))")
        params.append(fecha_hasta)
    if ejecutivo:
        where.append("cobrador_actual = ?")
        params.append(ejecutivo)
    if contacto:
        where.append("contacto = ?")
        params.append(contacto)
    if accion:
        where.append("accion = ?")
        params.append(accion)
    if canal:
        where.append("canal = ?")
        params.append(canal)
    if estado:
        where.append("estado = ?")
        params.append(estado)
    if tramo_mora:
        where.append("tramo_mora = ?")
        params.append(tramo_mora)
    if zona:
        where.append("zona = ?")
        params.append(zona)

    where_sql = " AND ".join(where)

    count_sql = f"SELECT COUNT_BIG(1) AS total FROM {TABLE} WHERE {where_sql}"
    total_rows = run_query(count_sql, tuple(params))
    total = int(total_rows[0].get("total") or 0) if total_rows else 0

    data_sql = f"""
    SELECT
        id_gestion,
        CONVERT(varchar(36), id_ejecucion) AS id_ejecucion,
        nombre_archivo,
        numero_fila_origen,
        fecha_carga,
        periodo,
        ddas_fec_proc,
        ddas_nrt_ppal,
        ddas_drt_ppal,
        ddas_id_numero_operac,
        tramo_mora,
        cobrador_actual,
        empresa,
        fech_gest,
        fech_ingr,
        contacto,
        estado,
        fecha_comp,
        com_gest,
        tipo_gest,
        clasificacion_gestion,
        accion,
        canal,
        zona,
        fecha_gestion_filtro
    FROM {TABLE}
    WHERE {where_sql}
    ORDER BY fecha_gestion_filtro DESC, id_gestion DESC
    OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    """
    rows = run_query(data_sql, tuple(params + [offset, page_size]))
    return {
        "data": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_summary_view(filters: dict) -> dict:
    fecha_desde = _parse_date(filters.get("fecha_desde"))
    fecha_hasta = _parse_date(filters.get("fecha_hasta"))
    ejecutivo = str(filters.get("ejecutivo") or "").strip()
    ejecutivos = _parse_list(filters.get("ejecutivos"))
    contacto = str(filters.get("contacto") or "").strip()
    canal = str(filters.get("canal") or "").strip()
    tramo_mora = str(filters.get("tramo_mora") or "").strip()
    zona = str(filters.get("zona") or "").strip()
    page = max(int(filters.get("page") or 1), 1)
    page_size = min(max(int(filters.get("page_size") or 100), 1), 500)
    offset = (page - 1) * page_size

    where = ["1 = 1"]
    params: list[object] = []

    if fecha_desde:
        where.append("fecha_gestion_filtro >= CAST(? AS date)")
        params.append(fecha_desde)
    if fecha_hasta:
        where.append("fecha_gestion_filtro < DATEADD(day, 1, CAST(? AS date))")
        params.append(fecha_hasta)
    if ejecutivo:
        where.append("cobrador_actual = ?")
        params.append(ejecutivo)
    if ejecutivos:
        placeholders = ",".join("?" for _ in ejecutivos)
        where.append(f"cobrador_actual IN ({placeholders})")
        params.extend(ejecutivos)
    if contacto:
        where.append("contacto = ?")
        params.append(contacto)
    if canal:
        where.append("canal = ?")
        params.append(canal)
    if tramo_mora:
        where.append("tramo_mora = ?")
        params.append(tramo_mora)
    if zona:
        where.append("zona = ?")
        params.append(zona)

    where_sql = " AND ".join(where)
    group_cols = "cobrador_actual"
    group_select = "cobrador_actual"

    count_sql = f"""
    SELECT COUNT_BIG(1) AS total
    FROM (
        SELECT {group_select}
        FROM {TABLE}
        WHERE {where_sql}
        GROUP BY {group_cols}
    ) AS resumen
    """
    total_rows = run_query(count_sql, tuple(params))
    total = int(total_rows[0].get("total") or 0) if total_rows else 0

    column_rows = run_query(
        f"""
        SELECT DISTINCT ISNULL(NULLIF(LTRIM(RTRIM(contacto)), ''), 'Sin contacto') AS valor
        FROM {TABLE}
        WHERE {where_sql}
        ORDER BY valor
        """,
        tuple(params),
    )
    contacto_columns = _sort_contact_columns([row["valor"] for row in column_rows if row.get("valor")])

    data_sql = f"""
    ;WITH grupos AS (
        SELECT
            cobrador_actual,
            COUNT_BIG(1) AS total_gestiones,
            ROW_NUMBER() OVER (
                ORDER BY cobrador_actual
            ) AS rn
        FROM {TABLE}
        WHERE {where_sql}
        GROUP BY {group_cols}
    )
    SELECT
        cobrador_actual,
        total_gestiones
    FROM grupos
    WHERE rn > ? AND rn <= ?
    ORDER BY rn
    """
    group_rows = run_query(data_sql, tuple(params + [offset, offset + page_size]))

    cobrador_keys = [str(row.get("cobrador_actual") or "") for row in group_rows]
    contactos_by_cobrador: dict[str, dict[str, int]] = {key: {} for key in cobrador_keys}
    if cobrador_keys:
        placeholders = ",".join("?" for _ in cobrador_keys)
        contacto_rows = run_query(
            f"""
            SELECT
                ISNULL(cobrador_actual, '') AS cobrador_key,
                ISNULL(NULLIF(LTRIM(RTRIM(contacto)), ''), 'Sin contacto') AS valor,
                COUNT_BIG(1) AS total
            FROM {TABLE}
            WHERE {where_sql}
              AND ISNULL(cobrador_actual, '') IN ({placeholders})
            GROUP BY
                ISNULL(cobrador_actual, ''),
                ISNULL(NULLIF(LTRIM(RTRIM(contacto)), ''), 'Sin contacto')
            """,
            tuple(params + cobrador_keys),
        )
        for contacto_row in contacto_rows:
            cobrador_key = str(contacto_row.get("cobrador_key") or "")
            valor = contacto_row.get("valor")
            if valor:
                contactos_by_cobrador.setdefault(cobrador_key, {})[valor] = int(contacto_row.get("total") or 0)

    data = []
    for row in group_rows:
        cobrador_key = str(row.get("cobrador_actual") or "")
        data.append(
            {
                "cobrador_actual": row.get("cobrador_actual"),
                "total_gestiones": int(row.get("total_gestiones") or 0),
                "contactos": contactos_by_cobrador.get(cobrador_key, {}),
            }
        )

    return {
        "data": data,
        "contacto_columns": contacto_columns,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
