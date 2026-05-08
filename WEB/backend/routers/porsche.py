from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from fastapi import APIRouter, HTTPException

from database import run_query


router = APIRouter()

# Fuente unica de Porsche: vista consolidada, no tablas de staging.
DASHBOARD_VIEW = "dbo.dashboard_data"

TRAMO_ORDER = ["31-60", "61-90", "91-120", "121-150", "151-180", "181-210", "211-240"]
CONTACTO_META = {"31-60": 0.80, "61-90": 0.70, "91-120": 0.50, "121-150": 0.50, "151-180": 0.50, "181-210": 0.50, "211-240": 0.50}
RECUPERACION_META = {"31-60": 0.70, "61-90": 0.60, "91-120": 0.50, "121-150": 0.50, "151-180": 0.50, "181-210": 0.50, "211-240": 0.50}


def _coerce_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)

    text = str(value).strip()
    if not text:
        return None

    formats = (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%m-%Y",
        "%m/%Y",
    )
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt in ("%m-%Y", "%m/%Y"):
                return datetime(parsed.year, parsed.month, 1)
            return parsed
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(text.replace("Z", ""))
    except ValueError:
        return None


def _month_label(value) -> str:
    parsed = _coerce_datetime(value)
    if parsed is None:
        return ""
    return f"{parsed.month:02d}-{parsed.year:04d}"


def _month_sort_key(label: str) -> tuple[int, int]:
    try:
        month_str, year_str = label.split("-", 1)
        return int(year_str), int(month_str)
    except Exception:
        return 0, 0


def _selected_month_rows(rows: list[dict], mes: str | None) -> list[dict]:
    if not mes:
        return rows

    return [row for row in rows if _month_label(row.get("fecha_hora_carga")) == mes]


def _meta_for(tramo: str, kind: str) -> float:
    tramo_start = _parse_tramo_start(tramo)

    def tramo_high_default(meta_map: dict[str, float]) -> float:
        if tramo_start is not None and tramo_start >= 91:
            # Tramos altos (incluye extras como 241-270) usan meta del bloque alto.
            return meta_map.get("211-240", meta_map.get("181-210", 0.0))
        return 0.0

    if kind == "contactabilidad":
        return CONTACTO_META.get(tramo, tramo_high_default(CONTACTO_META))
    if kind == "recuperacion":
        return RECUPERACION_META.get(tramo, tramo_high_default(RECUPERACION_META))
    if kind == "promesas_pago":
        return 0.60
    if kind == "promesas_cumplidas":
        return 0.80
    if kind == "promesas_incumplidas":
        return 0.20
    if kind == "contenido":
        return 0.40
    if kind == "normalizado":
        return 0.50
    if kind == "renegociacion_solicitudes":
        return 0.20
    if kind == "renegociacion_efectivas":
        return 0.90
    if kind == "tpr":
        return 25.0
    if kind == "reiteracion_contacto":
        return 3.0
    return 0.0


def _to_float(v) -> float:
    try:
        if v is None:
            return 0.0
        return float(v)
    except Exception:
        return 0.0


def _to_int(v) -> int:
    try:
        if v is None:
            return 0
        return int(float(v))
    except Exception:
        return 0


def _parse_tramo_start(tramo: str) -> int | None:
    text = str(tramo or "").strip()
    m = text.split("-", 1)[0].strip()
    if not m.isdigit():
        return None
    return int(m)


def _cuadro_group_for_tramo(tramo: str) -> str | None:
    start = _parse_tramo_start(tramo)
    if start is None:
        return None
    if start == 31:
        return "31-60"
    if start == 61:
        return "61-90"
    if start >= 91:
        return "91+"
    return None


def _build_cuadro_contenido(rows: list[dict]) -> dict:
    metas = {"31-60": 0.70, "61-90": 0.60, "91+": 0.50}
    agg = {
        "31-60": {"contenido": 0.0, "no_contenido": 0.0, "total": 0.0},
        "61-90": {"contenido": 0.0, "no_contenido": 0.0, "total": 0.0},
        "91+": {"contenido": 0.0, "no_contenido": 0.0, "total": 0.0},
    }

    for row in rows:
        tramo = str(row.get("tramo", ""))
        group = _cuadro_group_for_tramo(tramo)
        if not group:
            continue
        deuda = _to_float(row.get("deuda"))
        total_pagado = _to_float(row.get("total_pagado"))
        if total_pagado > 0:
            agg[group]["contenido"] += deuda
            agg[group]["total"] += deuda
        else:
            agg[group]["no_contenido"] += deuda
            agg[group]["total"] += deuda

    total_porsche = sum(v["total"] for v in agg.values())

    calc = {}
    for group in ("31-60", "61-90", "91+"):
        total = agg[group]["total"]
        meta = metas[group]
        ponderador = (total / total_porsche) if total_porsche else 0.0
        real_total = (agg[group]["contenido"] / total) if total else 0.0
        cumplimiento = (real_total / meta) if meta else 0.0
        resultado = ponderador * cumplimiento
        calc[group] = {
            "ponderador": ponderador,
            "meta_total": meta,
            "real_total": real_total,
            "cumplimiento": cumplimiento,
            "resultado": resultado,
        }

    rows_visual = [
        {"negocio_pw": "31-60", **calc["31-60"]},
        {"negocio_pw": "61-90", **calc["61-90"]},
        {"negocio_pw": "91-120", "ponderador": None, "meta_total": None, "real_total": None, "cumplimiento": None, "resultado": None},
        {"negocio_pw": "121-150", **calc["91+"]},
        {"negocio_pw": "151-180", "ponderador": None, "meta_total": None, "real_total": None, "cumplimiento": None, "resultado": None},
        {"negocio_pw": "181-210", "ponderador": None, "meta_total": None, "real_total": None, "cumplimiento": None, "resultado": None},
    ]

    return {
        "rows": rows_visual,
        "resultado_total": calc["31-60"]["resultado"] + calc["61-90"]["resultado"] + calc["91+"]["resultado"],
    }


def _read_dashboard_rows() -> list[dict]:
    return run_query(f"SELECT * FROM {DASHBOARD_VIEW}")


def _available_months(rows: list[dict]) -> list[str]:
    months = {
        _month_label(row.get("fecha_hora_carga"))
        for row in rows
        if row.get("fecha_hora_carga") is not None
    }
    return sorted((m for m in months if m), key=_month_sort_key)


def _tramo_rows(rows: list[dict]) -> list[str]:
    # Orden dinámico desde asignación del mes seleccionado, preservando estándar primero.
    seen = set()
    tramos_data: list[str] = []
    for row in rows:
        tramo = str(row.get("tramo", "")).strip()
        if tramo and tramo not in seen:
            seen.add(tramo)
            tramos_data.append(tramo)

    if not tramos_data:
        return TRAMO_ORDER.copy()

    def sort_key(tramo: str) -> tuple[int, int, str]:
        start = _parse_tramo_start(tramo)
        if start is None:
            return (1, 10_000, tramo)
        return (0, start, tramo)

    # Asegurar tramos estándar en su lugar si existen en datos.
    ordered_standard = [t for t in TRAMO_ORDER if t in seen]
    remaining = [t for t in tramos_data if t not in set(ordered_standard)]
    remaining.sort(key=sort_key)
    return ordered_standard + remaining


def _group_counts(rows: list[dict]) -> dict[str, int]:
    out = defaultdict(int)
    for row in rows:
        tramo = str(row.get("tramo", ""))
        out[tramo] += 1
    return out


def _section_ratio(rows: list[dict], value_col: str, meta_kind: str, result_name: str, pct_name: str, denominator_col: str | None = None, incumplida_rule: bool = False) -> list[dict]:
    tramos = _tramo_rows(rows)
    asignado = _group_counts(rows)
    result_sum = defaultdict(float)
    denom_sum = defaultdict(float)

    for row in rows:
        tramo = str(row.get("tramo", ""))
        result_sum[tramo] += _to_float(row.get(value_col))
        if denominator_col:
            denom_sum[tramo] += _to_float(row.get(denominator_col))

    out = []
    for tramo in tramos:
        den = denom_sum[tramo] if denominator_col else float(asignado[tramo])
        res = result_sum[tramo]
        pct = (res / den) if den else 0.0
        meta = _meta_for(tramo, meta_kind)
        if incumplida_rule:
            brecha = meta - pct
            cumplimiento = brecha + 1
        else:
            brecha = pct - meta
            cumplimiento = min(1.0, (pct / meta)) if meta else 0.0
        out.append(
            {
                "tramo": tramo,
                "meta": meta,
                "asignado": int(den if denominator_col else asignado[tramo]),
                result_name: res,
                pct_name: pct,
                "brecha": brecha,
                "cumplimiento": cumplimiento,
            }
        )
    return out


def _section_tpr(rows: list[dict]) -> list[dict]:
    tramos = _tramo_rows(rows)
    asignado = _group_counts(rows)
    sum_days = defaultdict(float)
    cnt_days = defaultdict(int)
    for row in rows:
        v = row.get("dias_habiles")
        if v is not None and _to_int(row.get("contactabilidad")) == 1:
            tramo = str(row.get("tramo", ""))
            sum_days[tramo] += _to_float(v)
            cnt_days[tramo] += 1

    out = []
    for tramo in tramos:
        tpr = (sum_days[tramo] / cnt_days[tramo]) if cnt_days[tramo] else 0.0
        meta = _meta_for(tramo, "tpr")
        pct_kpi = min(1.0, (meta / tpr)) if tpr else 0.0
        brecha = 0.0 if pct_kpi == 1 else -1 * (pct_kpi + 1)
        out.append(
            {
                "tramo": tramo,
                "meta": meta,
                "asignado": asignado[tramo],
                "TPR": tpr,
                "pct_kpi": pct_kpi,
                "brecha": brecha,
                "cumplimiento": pct_kpi,
            }
        )
    return out


def _section_reiteracion(rows: list[dict]) -> list[dict]:
    tramos = _tramo_rows(rows)
    asignado = _group_counts(rows)
    contactados = defaultdict(float)
    sum_int = defaultdict(float)
    cnt_int = defaultdict(int)
    for row in rows:
        tramo = str(row.get("tramo", ""))
        c = _to_float(row.get("contactabilidad"))
        contactados[tramo] += c
        if c == 0:
            sum_int[tramo] += _to_float(row.get("intensidad"))
            cnt_int[tramo] += 1

    out = []
    for tramo in tramos:
        rc = (sum_int[tramo] / cnt_int[tramo]) if cnt_int[tramo] else 0.0
        meta = _meta_for(tramo, "reiteracion_contacto")
        pct_kpi = (rc / meta) if meta else 0.0
        brecha = pct_kpi - 1
        cumplimiento = 1.0 if pct_kpi > 1 else pct_kpi
        out.append(
            {
                "tramo": tramo,
                "meta": meta,
                "asignado": asignado[tramo],
                "casos_sin_contacto": int(asignado[tramo] - contactados[tramo]),
                "RC": rc,
                "pct_kpi": pct_kpi,
                "brecha": brecha,
                "cumplimiento": cumplimiento,
            }
        )
    return out


def _section_campana_renegociacion(rows: list[dict]) -> list[dict]:
    casos_campana = int(sum(_to_float(r.get("marca_rene")) for r in rows))
    solicitudes = float(sum(_to_float(r.get("rene_ofrecida")) for r in rows))
    efectivas = float(sum(_to_float(r.get("rene_cursada")) for r in rows))

    def row(nombre: str, meta: float, valor: float) -> dict:
        pct = (valor / casos_campana) if casos_campana else 0.0
        return {
            "tramo": nombre,
            "meta": meta,
            "asignado": casos_campana,
            "kpi": valor,
            "pct_kpi": pct,
            "brecha": pct - meta,
            "cumplimiento": pct,
        }

    return [row("Solicitudes", 0.20, solicitudes), row("Efectivas", 0.90, efectivas)]


@router.get("/filtros")
def filtros() -> dict:
    try:
        rows = _read_dashboard_rows()
        meses = _available_months(rows)
        return {"filters": {"meses": meses, "default_mes": meses[-1] if meses else ""}}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/dashboard")
def dashboard(mes: str | None = None) -> dict:
    try:
        rows = _read_dashboard_rows()
        available_months = _available_months(rows)
        selected_month = mes or (available_months[-1] if available_months else "")
        rows = _selected_month_rows(rows, selected_month)
        for r in rows:
            r["contenido_bin"] = 1 if str(r.get("contenido", "")).upper() == "SI" else 0
            r["normalizado_bin"] = 1 if str(r.get("normaliza", "")).upper() == "SI" else 0
            r["pago_bin"] = 1 if _to_float(r.get("total_pagado")) > 0 else 0

        sections = {
            "contactabilidad": _section_ratio(rows, "contactabilidad", "contactabilidad", "casos_contactados", "pct_contacto"),
            "promesas_pago": _section_ratio(rows, "filtro_compromiso", "promesas_pago", "casos_con_promesa", "pct_promesa_pago", denominator_col="contactabilidad"),
            "promesas_cumplidas": _section_ratio(rows, "pago_con_compromiso", "promesas_cumplidas", "promesas_cumplidas", "pct_cumplimiento_promesa", denominator_col="filtro_compromiso"),
            "promesas_incumplidas": _section_ratio(rows, "incumplido", "promesas_incumplidas", "promesas_incumplidas", "pct_incumplido", denominator_col="filtro_compromiso", incumplida_rule=True),
            "recuperacion": _section_ratio(rows, "pago_bin", "recuperacion", "casos_pagados", "pct_recupero"),
            "contenido": _section_ratio(rows, "contenido_bin", "contenido", "casos_contenidos", "pct_contenido"),
            "normalizado": _section_ratio(rows, "normalizado_bin", "normalizado", "casos_normalizados", "pct_normalizado"),
            "campana_renegociacion": _section_campana_renegociacion(rows),
            "tpr": _section_tpr(rows),
            "reiteracion_contacto": _section_reiteracion(rows),
        }

        summary = {
            "asignados": len(rows),
            "contactados": int(sum(_to_float(r.get("contactabilidad")) for r in rows)),
            "con_promesa": int(sum(_to_float(r.get("filtro_compromiso")) for r in rows)),
            "recuperado": float(sum(_to_float(r.get("total_pagado")) for r in rows)),
        }

        return {
            "filters": {"meses": available_months, "default_mes": available_months[-1] if available_months else "", "mes": selected_month},
            "summary": summary,
            "sections": sections,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/cuadro-contenido")
def cuadro_contenido(mes: str | None = None) -> dict:
    try:
        rows = _read_dashboard_rows()
        available_months = _available_months(rows)
        selected_month = mes or (available_months[-1] if available_months else "")
        month_rows = _selected_month_rows(rows, selected_month)
        cuadro = _build_cuadro_contenido(month_rows)
        return {
            "filters": {"meses": available_months, "default_mes": available_months[-1] if available_months else "", "mes": selected_month},
            "cuadro": cuadro,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
