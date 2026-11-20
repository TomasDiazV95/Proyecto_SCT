"""Helpers de texto y numeros que antes estaban copiados, iguales, en varios servicios.

Cada servicio los importa con su nombre local de siempre (por ejemplo `pct as _safe_div`), asi que los
calculos no cambian. Ojo: `pct` y `razon` NO son intercambiables (uno multiplica por 100, el otro no);
lo mismo `cap_pct` (tope 130, en porcentaje) y `cap_fraccion` (tope 1.3, en fraccion).
"""
from __future__ import annotations

from datetime import date


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def clean(value: object) -> str:
    return str(value or "").strip()


def pct(num: float, den: float) -> float:
    """num / den en porcentaje (x100); 0 si el denominador es 0 o None."""
    if den is None or den == 0:
        return 0.0
    return (num / den) * 100.0


def razon(num: float, den: float) -> float:
    """num / den como fraccion; 0 si el denominador es 0 o None."""
    if den is None or den == 0:
        return 0.0
    return num / den


def cap_pct(value: float, max_value: float = 130.0) -> float:
    """Porcentaje acotado a [0, max_value] (por defecto 130%)."""
    return max(0.0, min(max_value, value))


def cap_fraccion(value: float, max_value: float = 1.3) -> float:
    """Fraccion acotada a [0, max_value] (por defecto 1.3 = 130%)."""
    return max(0.0, min(value, max_value))


def cap_cumpl_meta(value: float) -> float:
    return min(float(value or 0), 1.3)


def cumplimiento_meta(pct_real: float, meta: float) -> float:
    """Cumplimiento de un porcentaje real contra su meta (ambos en %), acotado a 130."""
    if meta is None or meta <= 0:
        return 0.0
    return cap_pct(pct(pct_real, meta))


def periodo_from_fecha(fecha_carga: str) -> str:
    parsed = date.fromisoformat(fecha_carga)
    return parsed.replace(day=1).isoformat()


def in_list(values: tuple) -> str:
    return ", ".join("'{}'".format(str(value).replace("'", "''")) for value in values)
