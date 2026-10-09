from __future__ import annotations

import re

import numpy as np

import cache
from database import get_connection, run_query
from services.itau_vencida_service import FILTROS_FIJOS, PRODUCTOS, _load_filtros_medibles, _load_metas, filtros_fijos


TABLE = "dbo.itau_vencida_filtros_medibles"
# Lista blanca: el nombre de columna se interpola en SQL, los valores siempre van como parametros.
COLUMNAS = ("DETALLE_MARCA", "CANAL", "PRODUCTO", "SEGMENTO", "FASE_PROY_MAX")
GESTOR_PHOENIX = "PHOENIX"
MAX_VALOR = 200

# Busqueda de medibles por monto asignado: columnas que se prueban. Canal y fases son fijos.
COLUMNAS_BUSQUEDA = ("DETALLE_MARCA", "PRODUCTO", "SEGMENTO")
UNIDADES = {"pesos": 1.0, "millones": 1_000_000.0}
MAX_COMBINACIONES = 20_000_000
MAX_SUGERENCIAS = 5
# Mejores combinaciones que se guardan por cada opcion de la primera columna.
CANDIDATOS_POR_BLOQUE = 300


class FiltroInvalido(ValueError):
    pass


class FiltroDuplicado(ValueError):
    pass


def _periodo(value: str | None) -> str:
    text = str(value or "").strip()[:7]
    if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", text):
        raise FiltroInvalido(f"Periodo inválido: {value}. Se espera YYYY-MM")
    return text


def _filtro(periodo: str, columna: str, valor: str) -> tuple[str, str, str]:
    columna = str(columna or "").strip().upper()
    valor = str(valor or "").strip()
    if columna not in COLUMNAS:
        raise FiltroInvalido(f"Columna inválida: {columna}")
    if not valor:
        raise FiltroInvalido("El valor no puede estar vacío")
    if len(valor) > MAX_VALOR:
        raise FiltroInvalido(f"El valor supera {MAX_VALOR} caracteres")
    return _periodo(periodo), columna, valor


def _valores_contencion(periodo: str) -> dict[str, list[str]]:
    """Valores distintos de cada columna en la ultima contencion Phoenix cargada en el mes (o la ultima carga si el mes no tiene)."""
    fechas = run_query(
        """
        SELECT MAX(fecha_carga) AS fecha
        FROM dbo.contencion_itau_vencida
        WHERE GESTOR = ?
          AND CONVERT(char(7), fecha_carga, 126) = ?
        """,
        (GESTOR_PHOENIX, periodo),
    )
    fecha = fechas[0].get("fecha") if fechas else None
    if not fecha:
        ultima = run_query(
            "SELECT MAX(fecha_carga) AS fecha FROM dbo.contencion_itau_vencida WHERE GESTOR = ?",
            (GESTOR_PHOENIX,),
        )
        fecha = ultima[0].get("fecha") if ultima else None
    if not fecha:
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
                  AND CAST(fecha_carga AS date) = CAST(? AS date)
                  AND NULLIF(LTRIM(RTRIM([{columna}])), '') IS NOT NULL
                ORDER BY valor
                """,
                (GESTOR_PHOENIX, fecha),
            )
            if r.get("valor")
        ]
    return valores


def get_medibles(periodo: str) -> dict:
    periodo = _periodo(periodo)
    # Los mismos filtros con que se calcula la productividad; los fijos se marcan para no poder quitarlos.
    filtros = [{**f, "fijo": f["columna"] in FILTROS_FIJOS} for f in _load_filtros_medibles(periodo)]
    periodos = [
        r["periodo"]
        for r in run_query(f"SELECT DISTINCT periodo FROM {TABLE} WHERE activo = 1 ORDER BY periodo DESC")
    ]
    return {
        "periodo": periodo,
        "filtros": filtros,
        "fijos": filtros_fijos(),
        "periodos_configurados": periodos,
        "valores": _valores_contencion(periodo),
        "cargas": _cargas_periodo(periodo),
        "fases_meta": _fases_meta(periodo),
    }


def add_medibles(periodo: str, columna: str, valores: list[str]) -> dict:
    """Agrega varios valores de una columna en una sola transaccion. Los que ya estaban se informan y no se duplican."""
    limpios: list[str] = []
    for valor in valores or []:
        periodo_ok, columna_ok, valor_ok = _filtro(periodo, columna, valor)
        if valor_ok.upper() not in {v.upper() for v in limpios}:
            limpios.append(valor_ok)
    if not limpios:
        raise FiltroInvalido("Selecciona al menos un valor")
    periodo, columna = _periodo(periodo), str(columna).strip().upper()
    _rechazar_fijo(columna)

    agregados: list[str] = []
    ya_existian: list[str] = []
    with get_connection() as cn:
        cur = cn.cursor()
        _guardar_fijos(cur, periodo)
        for valor in limpios:
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
                ya_existian.append(valor)
                continue
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
            agregados.append(valor)
        cn.commit()
    cache.clear()

    if not agregados:
        raise FiltroDuplicado(f"Los valores seleccionados ya estaban configurados para {periodo}")
    return {**get_medibles(periodo), "agregados": agregados, "ya_existian": ya_existian}


def delete_medible(periodo: str, columna: str, valor: str) -> dict:
    periodo, columna, valor = _filtro(periodo, columna, valor)
    _rechazar_fijo(columna)
    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(
            f"DELETE FROM {TABLE} WHERE periodo = ? AND columna = ? AND valor = ?",
            (periodo, columna, valor),
        )
        cn.commit()
    cache.clear()
    return get_medibles(periodo)


def _rechazar_fijo(columna: str) -> None:
    if columna in FILTROS_FIJOS:
        raise FiltroInvalido("El canal y las fases medibles son fijos y no se pueden cambiar")


def _guardar_fijos(cur, periodo: str) -> None:
    """Deja en la tabla el canal y las fases fijos del mes, sin otros valores en esas columnas."""
    marcas = ", ".join("?" for _ in FILTROS_FIJOS)
    cur.execute(f"DELETE FROM {TABLE} WHERE periodo = ? AND columna IN ({marcas})", (periodo, *FILTROS_FIJOS))
    for fijo in filtros_fijos():
        cur.execute(
            f"INSERT INTO {TABLE} (periodo, columna, valor, activo) VALUES (?, ?, ?, 1)",
            (periodo, fijo["columna"], fijo["valor"]),
        )


def replace_medibles(periodo: str, filtros: list[dict]) -> dict:
    """Deja como medibles del mes los filtros recibidos mas el canal y las fases fijos, en una sola
    transaccion. Sin filtros, el mes queda medido solo por lo fijo."""
    limpios: list[tuple[str, str]] = []
    for filtro in filtros or []:
        periodo_ok, columna, valor = _filtro(periodo, filtro.get("columna"), filtro.get("valor"))
        if columna in FILTROS_FIJOS:
            continue
        if (columna, valor.upper()) not in {(c, v.upper()) for c, v in limpios}:
            limpios.append((columna, valor))
    periodo = _periodo(periodo)

    with get_connection() as cn:
        cur = cn.cursor()
        cur.execute(f"DELETE FROM {TABLE} WHERE periodo = ?", (periodo,))
        _guardar_fijos(cur, periodo)
        for columna, valor in limpios:
            cur.execute(
                f"INSERT INTO {TABLE} (periodo, columna, valor, activo) VALUES (?, ?, ?, 1)",
                (periodo, columna, valor),
            )
        cn.commit()
    cache.clear()
    return get_medibles(periodo)


def _cargas_periodo(periodo: str) -> list[str]:
    return [
        r["fecha"]
        for r in run_query(
            """
            SELECT DISTINCT CONVERT(char(10), fecha_carga, 126) AS fecha
            FROM dbo.contencion_itau_vencida
            WHERE GESTOR = ?
              AND CONVERT(char(7), fecha_carga, 126) = ?
            ORDER BY fecha DESC
            """,
            (GESTOR_PHOENIX, periodo),
        )
        if r.get("fecha")
    ]


def _fases_meta(periodo: str) -> dict[str, list[int]]:
    """Fases con meta de cada producto: son las que mide el banco y las unicas que entran al cumplimiento."""
    metas = _load_metas(f"{periodo}-01")
    return {producto: sorted(metas[producto]["fases"]) for producto in PRODUCTOS if producto in metas}


def _opciones_eje(valores: list[str]) -> list[tuple[list[str] | None, list[bool]]]:
    """Formas de filtrar una columna: sin restriccion (None) o un subconjunto de sus valores.
    El valor vacio no se puede agregar como medible, asi que solo entra cuando la columna no restringe."""
    con_valor = [i for i, valor in enumerate(valores) if valor]
    opciones: list[tuple[list[str] | None, list[bool]]] = [(None, [True] * len(valores))]
    for mask in range(1, 2 ** len(con_valor)):
        elegidos = [con_valor[i] for i in range(len(con_valor)) if mask >> i & 1]
        if len(elegidos) == len(valores):
            continue  # Todos los valores: es lo mismo que no restringir.
        opciones.append(([valores[i] for i in elegidos], [i in elegidos for i in range(len(valores))]))
    return opciones


def sugerir_medibles(periodo: str, fecha_carga: str, montos: list[dict], unidad: str = "pesos") -> dict:
    """Busca que valores de Detalle marca, Producto y Segmento dejan el saldo inicial de cada producto
    igual al monto asignado que informa el banco, dentro del canal y las fases fijos. Prueba todas las
    combinaciones. Los montos pueden ser el total del producto o el detalle por fase."""
    periodo = _periodo(periodo)
    fecha_carga = str(fecha_carga or "").strip()[:10]
    if fecha_carga not in _cargas_periodo(periodo):
        raise FiltroInvalido(f"No hay carga de contención Phoenix el {fecha_carga or '(sin fecha)'} en {periodo}")
    if unidad not in UNIDADES:
        raise FiltroInvalido(f"Unidad inválida: {unidad}")
    factor = UNIDADES[unidad]

    fases_meta = _fases_meta(periodo)
    celdas = [(producto, fase) for producto in PRODUCTOS for fase in fases_meta.get(producto, [])]
    if not celdas:
        raise FiltroInvalido(f"{periodo} no tiene metas cargadas; sin metas no se sabe qué fases se miden")
    # Cada monto es de una fase o, sin fase, el total del producto (suma de sus fases con meta).
    ingresado: dict[tuple[str, int | None], float] = {}
    for item in montos or []:
        producto = str(item.get("producto") or "").strip().upper()
        clave = (producto, int(item["fase"]) if item.get("fase") else None)
        if item.get("monto") is not None and (clave in celdas or (clave[1] is None and producto in fases_meta)):
            ingresado[clave] = float(item["monto"]) * factor
    if not ingresado:
        raise FiltroInvalido("Ingresa el monto asignado de al menos un producto")

    # Cubo de la carga: saldo inicial del canal fijo por cada combinacion de las columnas, producto y fase.
    columnas_sql = ", ".join(f"LTRIM(RTRIM(ISNULL([{c}], ''))) AS [{c}]" for c in COLUMNAS_BUSQUEDA)
    grupo_sql = ", ".join(f"LTRIM(RTRIM(ISNULL([{c}], '')))" for c in COLUMNAS_BUSQUEDA)
    cubo = run_query(
        f"""
        SELECT {columnas_sql},
               CASE UPPER(LTRIM(RTRIM(GLOSA_TIPO_CARTERA)))
                   WHEN 'CONSUMO' THEN 'CONSUMO'
                   WHEN 'VIVIENDA' THEN 'HIPOTECARIO'
                   ELSE 'OTRO'
               END AS producto,
               CAST(FASE_PROY_MAX AS int) AS fase,
               SUM(COALESCE(CAST(SALDO_INI AS float), 0)) AS saldo
        FROM dbo.contencion_itau_vencida
        WHERE GESTOR = ?
          AND CAST(fecha_carga AS date) = CAST(? AS date)
          AND UPPER(LTRIM(RTRIM(ISNULL(CANAL, '')))) IN ({", ".join("?" for _ in FILTROS_FIJOS["CANAL"])})
        GROUP BY {grupo_sql}, UPPER(LTRIM(RTRIM(GLOSA_TIPO_CARTERA))), CAST(FASE_PROY_MAX AS int)
        """,
        (GESTOR_PHOENIX, fecha_carga, *FILTROS_FIJOS["CANAL"]),
    )
    cubo = [row for row in cubo if (row["producto"], row["fase"]) in celdas]

    # El filtro compara sin distinguir mayusculas: se agrupa igual y se muestra el texto original.
    # Un valor sin saldo en las celdas que se miden no cambia ningun resultado: no se prueba.
    etiquetas: list[dict[str, str]] = [{} for _ in COLUMNAS_BUSQUEDA]
    for row in cubo:
        if float(row["saldo"] or 0):
            for eje, columna in enumerate(COLUMNAS_BUSQUEDA):
                etiquetas[eje].setdefault(str(row[columna]).upper(), str(row[columna]))
    ejes = [sorted(e) for e in etiquetas]
    opciones = [_opciones_eje(valores) for valores in ejes]
    combinaciones = 1
    for opcion in opciones:
        combinaciones *= len(opcion)
    if combinaciones > MAX_COMBINACIONES:
        raise FiltroInvalido(
            f"La carga del {fecha_carga} tiene demasiados valores distintos para probar todas las combinaciones "
            f"({combinaciones:,} posibles). Configura los medibles a mano."
        )

    tensor = np.zeros([len(e) for e in ejes] + [len(celdas)])
    for row in cubo:
        if float(row["saldo"] or 0):
            pos = tuple(ejes[eje].index(str(row[c]).upper()) for eje, c in enumerate(COLUMNAS_BUSQUEDA))
            tensor[pos + (celdas.index((row["producto"], row["fase"])),)] += float(row["saldo"])

    # A igual diferencia, primero la combinacion mas simple: menos columnas restringidas y menos valores.
    costos = [np.array([0 if valores is None else 100 + len(valores) for valores, _ in opcion], dtype=float) for opcion in opciones]
    mascaras = [np.array([m for _, m in opcion], dtype=float) for opcion in opciones]

    # La columna con mas opciones se recorre de a una (acota la memoria); las demas se
    # resuelven juntas: saldo de cada celda para todas sus combinaciones a la vez.
    primero = max(range(len(opciones)), key=lambda eje: len(opciones[eje]))
    otros = [eje for eje in range(len(opciones)) if eje != primero]
    resto = np.moveaxis(tensor, primero, 0)
    for lugar, eje in enumerate(otros, start=1):
        resto = np.moveaxis(np.tensordot(mascaras[eje], resto, axes=(1, lugar)), 0, lugar)
    simpleza_resto = np.zeros([len(opciones[eje]) for eje in otros])
    for lugar, eje in enumerate(otros):
        forma = [1] * len(otros)
        forma[lugar] = len(opciones[eje])
        simpleza_resto = simpleza_resto + costos[eje].reshape(forma)

    # Una fila por monto ingresado: que celdas suma (una fase, o todas las del producto si es el total).
    suma = np.array(
        [[1.0 if p == producto and fase in (None, f) else 0.0 for p, f in celdas] for producto, fase in ingresado]
    )
    objetivo = np.array(list(ingresado.values()))
    candidatos: list[tuple[float, float, tuple, np.ndarray]] = []
    for a, mascara in enumerate(mascaras[primero]):
        saldos = np.tensordot(mascara, resto, axes=(0, 0))
        error = np.abs(saldos @ suma.T - objetivo).sum(axis=-1).round(0)
        mejores = np.lexsort((simpleza_resto.ravel(), error.ravel()))[:CANDIDATOS_POR_BLOQUE]
        for plano in mejores:
            pos = np.unravel_index(plano, error.shape)
            candidatos.append((float(error[pos]), float(costos[primero][a] + simpleza_resto[pos]), (a, *pos), saldos[pos].copy()))
    candidatos.sort(key=lambda c: (c[0], c[1]))

    tolerancia = max(1.0, factor / 2)
    sugerencias: list[dict] = []
    vistos: set[tuple] = set()
    for diferencia_total, _, pos, calculado in candidatos:
        # Dos combinaciones con el mismo saldo en todas las celdas miden lo mismo: se muestra una.
        firma = tuple(np.round(calculado, 0))
        if firma in vistos:
            continue
        vistos.add(firma)
        # Por producto: sus fases y al final el total (fase None).
        detalle = []
        for producto in PRODUCTOS:
            fases = fases_meta.get(producto, [])
            saldo_fases = [float(calculado[celdas.index((producto, fase))]) for fase in fases]
            for fase, saldo in [*zip(fases, saldo_fases), (None, sum(saldo_fases))] if fases else []:
                monto = ingresado.get((producto, fase))
                detalle.append(
                    {
                        "producto": producto,
                        "fase": fase,
                        "ingresado": monto,
                        "calculado": saldo,
                        "diferencia": None if monto is None else saldo - monto,
                    }
                )
        filtros = {}
        for eje, lugar in zip([primero, *otros], pos):
            valores = opciones[eje][lugar][0]
            filtros[COLUMNAS_BUSQUEDA[eje]] = None if valores is None else [etiquetas[eje][v] for v in valores]
        sugerencias.append(
            {
                "filtros": {columna: filtros[columna] for columna in COLUMNAS_BUSQUEDA},
                "celdas": detalle,
                "diferencia_total": diferencia_total,
                "coincide": all(abs(c["diferencia"]) <= tolerancia for c in detalle if c["diferencia"] is not None),
            }
        )
        if len(sugerencias) == MAX_SUGERENCIAS:
            break

    return {
        "periodo": periodo,
        "fecha_carga": fecha_carga,
        "unidad": unidad,
        "fijos": filtros_fijos(),
        "combinaciones_probadas": combinaciones,
        "sugerencias": sugerencias,
    }
