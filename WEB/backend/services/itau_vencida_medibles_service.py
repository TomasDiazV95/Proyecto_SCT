from __future__ import annotations

import re

from database import get_connection, run_query


TABLE = "dbo.itau_vencida_filtros_medibles"
# Lista blanca: el nombre de columna se interpola en SQL, los valores siempre van como parametros.
COLUMNAS = ("DETALLE_MARCA", "CANAL", "PRODUCTO", "SEGMENTO")
GESTOR_PHOENIX = "PHOENIX"
MAX_VALOR = 200


class FiltroInvalido(ValueError):
    pass


class FiltroDuplicado(ValueError):
    pass


def _periodo(value: str | None) -> str:
    text = str(value or "").strip()[:7]
    if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", text):
        raise FiltroInvalido(f"Periodo invalido: {value}. Se espera YYYY-MM")
    return text


def _filtro(periodo: str, columna: str, valor: str) -> tuple[str, str, str]:
    columna = str(columna or "").strip().upper()
    valor = str(valor or "").strip()
    if columna not in COLUMNAS:
        raise FiltroInvalido(f"Columna invalida: {columna}")
    if not valor:
        raise FiltroInvalido("El valor no puede estar vacio")
    if len(valor) > MAX_VALOR:
        raise FiltroInvalido(f"El valor supera {MAX_VALOR} caracteres")
    return _periodo(periodo), columna, valor


def _valores_contencion(periodo: str) -> dict[str, list[str]]:
    """Valores distintos de cada columna en la contencion Phoenix del mes (o la ultima carga si el mes no tiene)."""
    fechas = run_query(
        """
        SELECT MIN(fecha_carga) AS desde, MAX(fecha_carga) AS hasta
        FROM dbo.contencion_itau_vencida
        WHERE GESTOR = ?
          AND CONVERT(char(7), fecha_carga, 126) = ?
        """,
        (GESTOR_PHOENIX, periodo),
    )
    desde = fechas[0].get("desde") if fechas else None
    hasta = fechas[0].get("hasta") if fechas else None
    if not desde:
        ultima = run_query(
            "SELECT MAX(fecha_carga) AS fecha FROM dbo.contencion_itau_vencida WHERE GESTOR = ?",
            (GESTOR_PHOENIX,),
        )
        desde = hasta = ultima[0].get("fecha") if ultima else None
    if not desde:
        return {columna: [] for columna in COLUMNAS}

    valores: dict[str, list[str]] = {}
    for columna in COLUMNAS:
        valores[columna] = [
            r["valor"]
            for r in run_query(
                f"""
                SELECT DISTINCT LTRIM(RTRIM([{columna}])) AS valor
                FROM dbo.contencion_itau_vencida
                WHERE GESTOR = ?
                  AND fecha_carga BETWEEN ? AND ?
                  AND NULLIF(LTRIM(RTRIM([{columna}])), '') IS NOT NULL
                ORDER BY valor
                """,
                (GESTOR_PHOENIX, desde, hasta),
            )
            if r.get("valor")
        ]
    return valores


def get_medibles(periodo: str) -> dict:
    periodo = _periodo(periodo)
    filtros = [
        {"columna": str(r["columna"]).strip(), "valor": str(r["valor"]).strip()}
        for r in run_query(
            f"""
            SELECT columna, valor
            FROM {TABLE}
            WHERE periodo = ?
              AND activo = 1
            ORDER BY columna, valor
            """,
            (periodo,),
        )
    ]
    periodos = [
        r["periodo"]
        for r in run_query(f"SELECT DISTINCT periodo FROM {TABLE} WHERE activo = 1 ORDER BY periodo DESC")
    ]
    return {
        "periodo": periodo,
        "filtros": filtros,
        "periodos_configurados": periodos,
        "valores": _valores_contencion(periodo),
    }


def add_medible(periodo: str, columna: str, valor: str) -> dict:
    periodo, columna, valor = _filtro(periodo, columna, valor)
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(
            f"""
            SELECT activo
            FROM {TABLE}
            WHERE periodo = ? AND columna = ? AND UPPER(LTRIM(RTRIM(valor))) = UPPER(?)
            """,
            (periodo, columna, valor),
        )
        existing = cur.fetchone()
        if existing and existing[0]:
            raise FiltroDuplicado(f"{valor} ya esta configurado en {columna} para {periodo}")
        if existing:
            cur.execute(
                f"""
                UPDATE {TABLE} SET activo = 1
                WHERE periodo = ? AND columna = ? AND UPPER(LTRIM(RTRIM(valor))) = UPPER(?)
                """,
                (periodo, columna, valor),
            )
        else:
            cur.execute(
                f"INSERT INTO {TABLE} (periodo, columna, valor, activo) VALUES (?, ?, ?, 1)",
                (periodo, columna, valor),
            )
        cn.commit()
    return get_medibles(periodo)


def delete_medible(periodo: str, columna: str, valor: str) -> dict:
    periodo, columna, valor = _filtro(periodo, columna, valor)
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(
            f"DELETE FROM {TABLE} WHERE periodo = ? AND columna = ? AND valor = ?",
            (periodo, columna, valor),
        )
        cn.commit()
    return get_medibles(periodo)
