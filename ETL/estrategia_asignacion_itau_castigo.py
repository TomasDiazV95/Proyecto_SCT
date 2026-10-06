import argparse
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from etl_asignacion_itau_castigo import ASIGNACION_FOLDER, TABLE, connect

# Cartera Itau Castigo en el CRM de gestiones (dbo.tmp_GEST_CRM).
CRM_CARTERA = 522
SIN_DATO = "SIN DATO"
MAX_PASADAS_AJUSTE = 10
COLUMNA_CONTACTO = "CONTACTO_TITULAR_6M"
# Columnas propias de la carga del ETL, no van al Excel.
COLUMNAS_CARGA = ("id_itau_castigo_asignacion", "fecha_carga", "ts_carga", "source_file")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reparto equilibrado de la asignacion Itau Castigo entre ejecutivos.")
    parser.add_argument("--periodo", default="202610", help="Periodo YYYYMM de la asignacion")
    parser.add_argument("--cobrador", default="PHOENIX", help="COBRADOR_VISTA a repartir")
    parser.add_argument("--ejecutivos", type=int, default=8, help="Cantidad de ejecutivos")
    parser.add_argument("--saldo-min", type=float, default=2_000_000, help="Se excluyen los RUT con saldo menor o igual")
    parser.add_argument("--meses", type=int, default=6, help="Meses hacia atras para la contactabilidad")
    parser.add_argument("--salida", default=ASIGNACION_FOLDER or str(Path(__file__).resolve().parent), help="Carpeta del Excel")
    return parser.parse_args()


def ventana_contacto(periodo: str, meses: int) -> tuple[date, date]:
    fin = date(int(periodo[:4]), int(periodo[4:]), 1)
    total = fin.year * 12 + (fin.month - 1) - meses
    return date(total // 12, total % 12 + 1, 1), fin


def query_df(cur, sql: str, params: tuple) -> pd.DataFrame:
    cur.execute(sql, params)
    columns = [c[0] for c in cur.description]
    return pd.DataFrame.from_records([tuple(r) for r in cur.fetchall()], columns=columns)


def read_base(cur, periodo: str, cobrador: str) -> pd.DataFrame:
    cur.execute(f"SELECT COL_LENGTH('{TABLE}', 'OPERACIONES')")
    operaciones = "OPERACIONES" if cur.fetchone()[0] is not None else "CAST(1 AS int)"

    df = query_df(
        cur,
        f"""
        SELECT CAST(RUT AS bigint) AS RUT,
               CAST(SDO_CAST_ACTUAL AS float) AS SDO_CAST_ACTUAL,
               LTRIM(RTRIM(COBRADOR_VISTA)) AS COBRADOR_VISTA,
               LTRIM(RTRIM(CAST(BINS_MOB AS nvarchar(200)))) AS BINS_MOB,
               LTRIM(RTRIM(CAST(NT AS nvarchar(200)))) AS NT,
               CAST({operaciones} AS float) AS OPERACIONES
        FROM {TABLE}
        WHERE PERIODO = ?
          AND RUT IS NOT NULL
          AND UPPER(LTRIM(RTRIM(COBRADOR_VISTA))) = UPPER(LTRIM(RTRIM(?)))
        """,
        (periodo, cobrador),
    )
    if df.empty:
        raise RuntimeError(f"Sin filas en {TABLE} para periodo {periodo} y COBRADOR_VISTA {cobrador}")

    df["SDO_CAST_ACTUAL"] = df["SDO_CAST_ACTUAL"].fillna(0.0)
    df["OPERACIONES"] = df["OPERACIONES"].fillna(1).astype(int)
    for col in ("BINS_MOB", "NT"):
        df[col] = df[col].where(df[col].notna() & (df[col] != ""), SIN_DATO)

    repetidos = int(df["RUT"].duplicated().sum())
    if repetidos:
        # Un RUT repetido se consolida: suma saldo y operaciones, conserva el mayor MOB / NT.
        print(f"Aviso: {repetidos} filas con RUT repetido, se consolidan por RUT")
        df = df.groupby("RUT", as_index=False).agg(
            SDO_CAST_ACTUAL=("SDO_CAST_ACTUAL", "sum"),
            COBRADOR_VISTA=("COBRADOR_VISTA", "first"),
            BINS_MOB=("BINS_MOB", "max"),
            NT=("NT", "max"),
            OPERACIONES=("OPERACIONES", "sum"),
        )
    return df


def read_contactos(cur, desde: date, hasta: date) -> pd.DataFrame:
    # Contacto directo / titular segun el catalogo del KPI operacional (dbo.kpi_tipo_contacto).
    return query_df(
        cur,
        """
        SELECT TRY_CAST(g.rut AS bigint) AS RUT,
               COUNT(DISTINCT YEAR(g.GestionFecha) * 100 + MONTH(g.GestionFecha)) AS MESES_CON_CONTACTO
        FROM dbo.tmp_GEST_CRM g
        INNER JOIN dbo.kpi_tipo_contacto t
            ON t.valor = ISNULL(NULLIF(UPPER(LTRIM(RTRIM(g.ContactoGestion))), ''), '(VACIO)')
           AND t.tipo = 'DIRECTO'
        WHERE g.cartera = ?
          AND g.GestionFecha >= ?
          AND g.GestionFecha < ?
          AND TRY_CAST(g.rut AS bigint) IS NOT NULL
        GROUP BY TRY_CAST(g.rut AS bigint)
        """,
        (CRM_CARTERA, desde, hasta),
    )


def repartir(df: pd.DataFrame, n_ejecutivos: int) -> pd.Series:
    """Reparte por estrato (MOB x NT x contactado) compensando saldo; devuelve el indice de ejecutivo por fila."""
    saldo = [0.0] * n_ejecutivos
    ops = [0] * n_ejecutivos
    ruts = [0] * n_ejecutivos
    # Conteo por ejecutivo de cada categoria, solo de los sobrantes (los bloques completos suman igual a todos).
    marginal = [{} for _ in range(n_ejecutivos)]
    asignado = {}

    def entregar(idx, row, k: int) -> None:
        asignado[idx] = k
        saldo[k] += row.SDO_CAST_ACTUAL
        ops[k] += row.OPERACIONES
        ruts[k] += 1

    ordenado = df.sort_values(["SDO_CAST_ACTUAL", "RUT"], ascending=[False, True])
    estratos = []
    for _, grupo in ordenado.groupby(["BINS_MOB", "NT", "CONTACTADO_6M"], sort=True):
        filas = list(grupo.itertuples())
        estratos.append(filas)
        completos = len(filas) - len(filas) % n_ejecutivos

        # Bloques completos: el mayor saldo del bloque va al ejecutivo con menor saldo acumulado.
        for i in range(0, completos, n_ejecutivos):
            orden = sorted(range(n_ejecutivos), key=lambda k: (saldo[k], ops[k], k))
            for row, k in zip(filas[i : i + n_ejecutivos], orden):
                entregar(row.Index, row, k)

        # Sobrante del estrato: a quien tiene menos RUT y menos de esas categorias, luego menor saldo.
        usados = set()
        for row in filas[completos:]:
            claves = (("MOB", row.BINS_MOB), ("NT", row.NT), ("CONTACTO", row.CONTACTADO_6M))
            k = min(
                (k for k in range(n_ejecutivos) if k not in usados),
                key=lambda k: (ruts[k], sum(marginal[k].get(c, 0) for c in claves), saldo[k], ops[k], k),
            )
            usados.add(k)
            for c in claves:
                marginal[k][c] = marginal[k].get(c, 0) + 1
            entregar(row.Index, row, k)

    # Ajuste fino: intercambia RUT del mismo estrato entre dos ejecutivos mientras mejore el equilibrio de
    # saldo y operaciones. No cambia la cantidad de RUT ni la mezcla de MOB / NT / contactabilidad.
    saldo_medio = sum(saldo) / n_ejecutivos
    ops_medio = sum(ops) / n_ejecutivos

    def costo(k: int, d_saldo: float = 0.0, d_ops: int = 0) -> float:
        return ((saldo[k] + d_saldo) / saldo_medio - 1) ** 2 + ((ops[k] + d_ops) / ops_medio - 1) ** 2

    for _ in range(MAX_PASADAS_AJUSTE):
        mejoro = False
        for filas in estratos:
            for i, x in enumerate(filas):
                for y in filas[i + 1 :]:
                    a, b = asignado[x.Index], asignado[y.Index]
                    if a == b:
                        continue
                    d_saldo = y.SDO_CAST_ACTUAL - x.SDO_CAST_ACTUAL
                    d_ops = y.OPERACIONES - x.OPERACIONES
                    antes = costo(a) + costo(b)
                    despues = costo(a, d_saldo, d_ops) + costo(b, -d_saldo, -d_ops)
                    if despues < antes - 1e-12:
                        asignado[x.Index], asignado[y.Index] = b, a
                        saldo[a] += d_saldo
                        saldo[b] -= d_saldo
                        ops[a] += d_ops
                        ops[b] -= d_ops
                        mejoro = True
        if not mejoro:
            break

    return pd.Series(asignado)


def resumen_ejecutivo(df: pd.DataFrame) -> pd.DataFrame:
    res = df.groupby("EJECUTIVO", observed=False).agg(
        RUT=("RUT", "count"),
        OPERACIONES=("OPERACIONES", "sum"),
        SDO_CAST_ACTUAL=("SDO_CAST_ACTUAL", "sum"),
        SALDO_PROMEDIO=("SDO_CAST_ACTUAL", "mean"),
        CONTACTADOS_6M=("CONTACTADO_6M", lambda s: int((s == "SI").sum())),
    )
    res["PCT_CONTACTADOS"] = res["CONTACTADOS_6M"] / res["RUT"]
    for col in ("RUT", "OPERACIONES", "SDO_CAST_ACTUAL"):
        res[f"DESV_{col}"] = res[col] / res[col].mean() - 1
    return res.reset_index()


def read_asignacion_completa(cur, periodo: str, cobrador: str) -> pd.DataFrame:
    df = query_df(
        cur,
        f"""
        SELECT *
        FROM {TABLE}
        WHERE PERIODO = ?
          AND RUT IS NOT NULL
          AND UPPER(LTRIM(RTRIM(COBRADOR_VISTA))) = UPPER(LTRIM(RTRIM(?)))
        ORDER BY id_itau_castigo_asignacion
        """,
        (periodo, cobrador),
    )
    return df.drop(columns=[c for c in COLUMNAS_CARGA if c in df.columns])


def armar_salida(asignacion: pd.DataFrame, detalle: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    # Toda la asignacion con EJECUTIVO al lado de RUT; los RUT fuera del reparto quedan sin ejecutivo.
    ejecutivo_por_rut = dict(zip(detalle["RUT"], detalle["EJECUTIVO"].astype(str)))
    contacto_por_rut = dict(zip(base["RUT"], (base["CONTACTADO_6M"] == "SI").astype(int)))
    salida = asignacion.copy()
    ejecutivo = salida["RUT"].map(lambda rut: ejecutivo_por_rut.get(int(rut)))
    contacto = salida["RUT"].map(lambda rut: contacto_por_rut.get(int(rut), 0))
    posicion = salida.columns.get_loc("RUT") + 1
    salida.insert(posicion, "EJECUTIVO", ejecutivo)
    # 1 = tuvo contacto titular en los ultimos meses de la ventana, 0 = no tuvo.
    salida.insert(posicion + 1, COLUMNA_CONTACTO, contacto)
    return salida


def write_excel(destino, salida: pd.DataFrame) -> None:
    salida.to_excel(destino, sheet_name="Asignacion", index=False, engine="openpyxl")


def generar_estrategia(
    cur,
    periodo: str,
    n_ejecutivos: int,
    cobrador: str = "PHOENIX",
    saldo_min: float = 2_000_000,
    meses: int = 6,
) -> dict:
    """Arma el reparto con un cursor abierto. La usan este script y el modulo web Estrategia de Asignacion."""
    desde, hasta = ventana_contacto(periodo, meses)
    base = read_base(cur, periodo, cobrador)
    contactos = read_contactos(cur, desde, hasta)
    asignacion = read_asignacion_completa(cur, periodo, cobrador)

    base = base.merge(contactos, on="RUT", how="left")
    base["MESES_CON_CONTACTO"] = base["MESES_CON_CONTACTO"].fillna(0).astype(int)
    base["CONTACTADO_6M"] = base["MESES_CON_CONTACTO"].gt(0).map({True: "SI", False: "NO"})

    excluir = base["SDO_CAST_ACTUAL"] <= saldo_min
    no_asignado = base[excluir]
    detalle = base[~excluir].reset_index(drop=True)
    if detalle.empty:
        raise RuntimeError(f"No quedan RUT con saldo mayor a {saldo_min:,.0f}")

    nombres = [f"Ejecutivo {i + 1}" for i in range(n_ejecutivos)]
    indice = repartir(detalle, n_ejecutivos)
    detalle["EJECUTIVO"] = pd.Categorical(indice.reindex(detalle.index).map(lambda k: nombres[k]), categories=nombres, ordered=True)
    detalle = detalle.sort_values(["EJECUTIVO", "SDO_CAST_ACTUAL"], ascending=[True, False]).reset_index(drop=True)
    detalle = detalle[
        ["RUT", "SDO_CAST_ACTUAL", "COBRADOR_VISTA", "BINS_MOB", "NT", "OPERACIONES", "CONTACTADO_6M", "MESES_CON_CONTACTO", "EJECUTIVO"]
    ]

    return {
        "desde": desde,
        "hasta": hasta,
        "base": base,
        "detalle": detalle,
        "no_asignado": no_asignado,
        "resumen": resumen_ejecutivo(detalle),
        "salida": armar_salida(asignacion, detalle, base),
    }


def main() -> None:
    args = parse_args()

    with connect() as cn:
        estrategia = generar_estrategia(cn.cursor(), args.periodo, args.ejecutivos, args.cobrador, args.saldo_min, args.meses)

    desde, hasta = estrategia["desde"], estrategia["hasta"]
    base, detalle, no_asignado = estrategia["base"], estrategia["detalle"], estrategia["no_asignado"]
    resumen = estrategia["resumen"]

    print(f"Periodo {args.periodo} | {args.cobrador} | contactabilidad {desde} a {hasta} (excluye fin)")
    print(f"RUT base: {len(base)} | repartidos: {len(detalle)} | no asignados (saldo <= {args.saldo_min:,.0f}): {len(no_asignado)}")
    print(resumen.to_string(index=False, float_format=lambda v: f"{v:,.4f}"))
    print(
        "Desviacion maxima vs promedio -> "
        f"RUT: {resumen['DESV_RUT'].abs().max():.2%} | "
        f"operaciones: {resumen['DESV_OPERACIONES'].abs().max():.2%} | "
        f"saldo: {resumen['DESV_SDO_CAST_ACTUAL'].abs().max():.2%} | "
        f"% contactados: {resumen['PCT_CONTACTADOS'].min():.2%} a {resumen['PCT_CONTACTADOS'].max():.2%}"
    )
    for columna in ("BINS_MOB", "NT"):
        cruce = pd.crosstab(detalle["EJECUTIVO"], detalle[columna])
        print(f"Diferencia maxima de RUT entre ejecutivos por {columna}: {int((cruce.max() - cruce.min()).max())}")

    salida = Path(args.salida) / f"Estrategia_Asignacion_{args.cobrador.strip().upper().replace(' ', '_')}_{args.periodo}.xlsx"
    try:
        write_excel(salida, estrategia["salida"])
    except PermissionError:
        # El Excel anterior esta abierto: se guarda con la hora para no perder la corrida.
        salida = salida.with_name(f"{salida.stem}_{datetime.now():%H%M%S}{salida.suffix}")
        write_excel(salida, estrategia["salida"])
    print(f"OK: {salida}")


if __name__ == "__main__":
    main()
