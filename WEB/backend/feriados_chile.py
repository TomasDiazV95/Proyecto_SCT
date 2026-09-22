"""Calendario de días hábiles de Chile.

Los feriados replican el catálogo de `ETL/etl_bench_control.py`
(`CHILE_HOLIDAYS_BY_YEAR`), que es donde se mantiene la lista oficial usada para
calcular `dia_habil` en `dbo.tmp_BENCH_CONTROL_DIARIO`. Al agregar un año nuevo
allá, hay que reflejarlo aquí.

Se calcula en el backend en vez de leer la tabla BENCH porque esa tabla sólo
contiene los días que el Excel de control alcanzó a cargar: por ejemplo, junio de
2026 no tiene el día 1, que es hábil. Calcularlo garantiza que no falten días.
"""

from datetime import date, timedelta


# FERIADOS CHILE 2026: https://www.feriadoschilenos.cl/feriados-2026/
CHILE_HOLIDAYS_BY_YEAR: dict[int, frozenset[date]] = {
    2026: frozenset(
        {
            date(2026, 1, 1),
            date(2026, 4, 3),
            date(2026, 4, 4),
            date(2026, 5, 1),
            date(2026, 5, 21),
            date(2026, 6, 21),
            date(2026, 6, 29),
            date(2026, 7, 16),
            date(2026, 8, 15),
            date(2026, 9, 18),
            date(2026, 9, 19),
            date(2026, 10, 12),
            date(2026, 10, 31),
            date(2026, 11, 1),
            date(2026, 12, 8),
            date(2026, 12, 25),
        }
    ),
}


def feriados(year: int) -> frozenset[date]:
    """Feriados del año. Vacío si el año no está en el catálogo, para no romper el cálculo."""
    return CHILE_HOLIDAYS_BY_YEAR.get(year, frozenset())


def es_habil(dia: date) -> bool:
    return dia.weekday() < 5 and dia not in feriados(dia.year)


def dias_habiles_al_cierre(start: date, end: date) -> dict[str, int]:
    """Fecha ISO -> días hábiles que faltan para el cierre, en negativo.

    0 es el último día hábil del período; -3 significa que después de esa fecha
    quedan 3 días hábiles. Mismo criterio que `business_days_remaining` del ETL
    BENCH, pero expresado como la cuenta regresiva que usa el eje del gráfico.
    """
    habiles: list[str] = []
    cursor = start
    while cursor < end:
        if es_habil(cursor):
            habiles.append(cursor.isoformat())
        cursor += timedelta(days=1)
    if not habiles:
        return {}
    ultimo = len(habiles) - 1
    return {fecha: -(ultimo - indice) for indice, fecha in enumerate(habiles)}
