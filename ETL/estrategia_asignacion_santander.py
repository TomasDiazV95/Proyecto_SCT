"""Reparto de la asignacion Santander (archivo bco_phoenix_ida) entre ejecutivos carterizados.

Grupos (numeracion global de ejecutivos):
  Hipotecario ciclo 1 -> 1, 2 | Hipotecario ciclos 2-3 -> 3, 4
  Consumo ciclos 1-2 -> 5, 6  | Consumo ciclos 3-6 -> 7
  Tarjeta alta cuantia multiciclo -> 8
Cada ejecutivo recibe a lo mas 350 RUT unicos, parejos en contacto directo 6m, pagos 6m, perfil y saldo.
El RUT va con el ciclo menor de sus operaciones (sin contar ciclo 0).
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from etl_asignacion_itau_castigo import connect

CRM_CARTERA = 530  # Santander en dbo.tmp_GEST_CRM
TOPE_RUT = 350
MAX_PASADAS_AJUSTE = 10
SIN_PERFIL = "SIN PERFIL"
NO_CARTERIZADO = "NO CARTERIZADO"

# Productos que valen para cada empresa asignada.
PRODUCTOS_EMPRESA = {
    "PHOENIX_CONSUMO": {"Credito de Consumo", "Tarjeta de Credito"},
    "PHOENIX_HIPOTECARIO": {"Credito Hipotecario"},
    "PHOENIX_TC": {"Tarjeta de Credito", "Credito de Consumo"},
}

# (grupo, empresa, ciclo minimo, ciclo maximo, ejecutivos)
GRUPOS = [
    ("HIPO_C1", "PHOENIX_HIPOTECARIO", 1, 1, [1, 2]),
    ("HIPO_C2_3", "PHOENIX_HIPOTECARIO", 2, 3, [3, 4]),
    ("CONS_C1_2", "PHOENIX_CONSUMO", 1, 2, [5, 6]),
    ("CONS_C3_6", "PHOENIX_CONSUMO", 3, 6, [7]),
    ("TC_ALTA", "PHOENIX_TC", 1, 99, [8]),
]
# Tarjeta alta cuantia: se eligen sus cupos entre los RUT de mayor saldo (este multiplo de los cupos).
TC_POOL_SALDO = 2

PERFIL_PUNTOS = {"BUENO": 0.05, "REGULAR": 0.0, SIN_PERFIL: 0.0, "MALO": -0.05}


def parse_args() -> argparse.Namespace:
    raiz = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", default=str(raiz / "20261105_bco_phoenix_ida.csv"), help="Archivo de asignacion (.csv o .xlsx)")
    parser.add_argument("--hoja", default=None, help="Hoja del Excel (por defecto, la que trae rut y nombre_empresa_asignada)")
    parser.add_argument("--desde", default="2026-05-01", help="Inicio de la ventana de 6 meses (contacto y pagos)")
    parser.add_argument("--relleno-csv", default=None, help="Archivo del que se toman casos para completar a un ejecutivo")
    parser.add_argument("--relleno-empresa", default="PHOENIX_PYME", help="Empresa de los casos de relleno")
    parser.add_argument("--relleno-ciclo", type=int, default=0, help="Ciclo de los casos de relleno")
    parser.add_argument("--relleno-producto", default=None, help="Producto de los casos de relleno (por defecto, todos)")
    parser.add_argument("--relleno-ejecutivo", type=int, default=None, help="Ejecutivo a completar hasta el tope")
    return parser.parse_args()


def query_df(cur, sql: str, params: tuple = ()) -> pd.DataFrame:
    cur.execute(sql, params)
    columns = [c[0] for c in cur.description]
    return pd.DataFrame.from_records([tuple(r) for r in cur.fetchall()], columns=columns)


def leer_excel(ruta: str, hoja: str | None) -> pd.DataFrame:
    if hoja is None:
        libro = pd.ExcelFile(ruta)
        hoja = next(
            (h for h in libro.sheet_names if {"rut", "nombre_empresa_asignada"} <= set(pd.read_excel(libro, sheet_name=h, nrows=0).columns)),
            None,
        )
        if hoja is None:
            raise RuntimeError(f"Ninguna hoja de {ruta} trae las columnas rut y nombre_empresa_asignada")
    print(f"Hoja: {hoja}")
    return pd.read_excel(ruta, sheet_name=hoja, dtype=str, keep_default_na=False)


def leer_archivo(ruta: str, hoja: str | None = None) -> pd.DataFrame:
    if Path(ruta).suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        df = leer_excel(ruta, hoja)
    else:
        df = pd.read_csv(ruta, sep=";", encoding="latin-1", dtype=str, keep_default_na=False)
    df["_rut"] = pd.to_numeric(df["rut"], errors="coerce").astype("Int64")
    df["_ciclo"] = pd.to_numeric(df["ciclo"], errors="coerce").fillna(0).astype(int)
    df["_saldo"] = pd.to_numeric(df["total_arrastre"], errors="coerce").fillna(0.0)
    df["_valido"] = [p in PRODUCTOS_EMPRESA.get(e, ()) for e, p in zip(df["nombre_empresa_asignada"], df["nombre_producto"])]
    # Ciclo del RUT: el menor de sus operaciones sin contar ciclo 0, mirando solo los productos validos de su
    # empresa (un RUT sin productos validos usa todos). Si todas estan en ciclo 0 queda en 0 = flujo, se excluye.
    base = df["_valido"] | ~df["nombre_empresa_asignada"].isin(PRODUCTOS_EMPRESA)
    usar = base | ~base.groupby(df["_rut"]).transform("any")
    ciclos = df["_ciclo"].where(usar & (df["_ciclo"] > 0))
    df["CICLO_RUT"] = ciclos.groupby(df["_rut"]).transform("min").fillna(0).astype(int)
    return df


def cargar_ruts(cur, ruts) -> None:
    cur.execute("IF OBJECT_ID('tempdb..#ruts') IS NOT NULL DROP TABLE #ruts")
    cur.execute("CREATE TABLE #ruts (rut bigint PRIMARY KEY)")
    cur.fast_executemany = True
    cur.executemany("INSERT INTO #ruts (rut) VALUES (?)", [(int(r),) for r in ruts])


def leer_contactos(cur, desde: str, hasta: str) -> pd.DataFrame:
    """Contactos directos (titular) del CRM Santander en la ventana, uno por fila de gestion."""
    g = query_df(
        cur,
        """
        SELECT TRY_CAST(g.rut AS bigint) AS rut, g.GestionFecha AS fecha, g.GestionHora AS hora,
               LTRIM(RTRIM(g.telefono)) AS telefono
        FROM dbo.tmp_GEST_CRM g
        INNER JOIN #ruts r ON r.rut = TRY_CAST(g.rut AS bigint)
        INNER JOIN dbo.kpi_tipo_contacto t
            ON t.valor = ISNULL(NULLIF(UPPER(LTRIM(RTRIM(g.ContactoGestion))), ''), '(VACIO)')
           AND t.tipo = 'DIRECTO'
        WHERE g.cartera = ? AND g.GestionFecha >= ? AND g.GestionFecha <= ?
        """,
        (CRM_CARTERA, desde, hasta),
    )
    if g.empty:
        return pd.DataFrame(columns=["rut", "MESES_CD", "N_CD", "TELEFONO_CD", "FECHA_ULTIMO_CD", "TELEFONOS_CD"])
    g["fecha"] = pd.to_datetime(g["fecha"])
    g["hora"] = g["hora"].astype(str)
    g["telefono"] = g["telefono"].fillna("").replace({"0": ""})
    g = g.sort_values(["rut", "fecha", "hora"], ascending=[True, False, False])

    def telefonos(s: pd.Series) -> str:
        # Telefonos distintos con contacto directo, del mas reciente al mas antiguo.
        return ", ".join(dict.fromkeys(t for t in s if t))

    con_fono = g[g["telefono"] != ""]
    ultimo_fono = con_fono.groupby("rut")["telefono"].first()
    res = g.groupby("rut").agg(
        MESES_CD=("fecha", lambda s: s.dt.to_period("M").nunique()),
        N_CD=("fecha", "size"),
        FECHA_ULTIMO_CD=("fecha", "first"),
        TELEFONOS_CD=("telefono", telefonos),
    )
    res["TELEFONO_CD"] = ultimo_fono.reindex(res.index).fillna("")
    res["FECHA_ULTIMO_CD"] = res["FECHA_ULTIMO_CD"].dt.date
    return res.reset_index()


def leer_bench(cur, desde: str) -> pd.DataFrame:
    """Ultima foto de cada mes del bench STH: contencion (pago) mensual y perfil de riesgo por RUT."""
    fotos = query_df(cur, "SELECT DISTINCT fecha_carga FROM dbo.tmp_bench_STH WHERE fecha_carga >= ?", (desde,))
    fotos["mes"] = pd.to_datetime(fotos["fecha_carga"]).dt.to_period("M")
    ultimas = fotos.groupby("mes")["fecha_carga"].max().tolist()
    marcas = ", ".join("?" for _ in ultimas)
    b = query_df(
        cur,
        f"""
        SELECT b.fecha_carga, TRY_CAST(b.fld_Rut AS bigint) AS rut,
               TRY_CAST(b.fld_Contenido AS int) AS contenido, LTRIM(RTRIM(b.fld_Perfil)) AS perfil
        FROM dbo.tmp_bench_STH b
        INNER JOIN #ruts r ON r.rut = TRY_CAST(b.fld_Rut AS bigint)
        WHERE b.fecha_carga IN ({marcas})
        """,
        tuple(ultimas),
    )
    if b.empty:
        return pd.DataFrame(columns=["rut", "MESES_BENCH", "MESES_PAGO", "MES_PAGO", "PERFIL_RIESGO"])
    # Un RUT cuenta como contenido en la foto si la mayoria de sus operaciones quedo contenida.
    por_foto = b.groupby(["rut", "fecha_carga"]).agg(contenido=("contenido", "mean")).reset_index()
    por_foto["contenido"] = por_foto["contenido"].ge(0.5).astype(int)
    hist = por_foto.groupby("rut").agg(MESES_BENCH=("fecha_carga", "nunique"), MESES_PAGO=("contenido", "sum"))
    # Meses en que el RUT quedo contenido (pago), ej: "2026-05, 2026-07".
    por_foto["mes"] = pd.to_datetime(por_foto["fecha_carga"]).dt.strftime("%Y-%m")
    pagados = por_foto[por_foto["contenido"] == 1].sort_values("mes")
    hist["MES_PAGO"] = pagados.groupby("rut")["mes"].agg(", ".join).reindex(hist.index).fillna("")

    perfiles = b[b["perfil"].notna() & (b["perfil"] != "")].copy()
    perfiles["perfil"] = perfiles["perfil"].str.upper().replace({"SIN_PERFIL": SIN_PERFIL})
    perfil = perfiles.sort_values("fecha_carga").groupby("rut")["perfil"].last().rename("PERFIL_RIESGO")
    return hist.join(perfil, how="outer").reset_index()


def armar_ruts(df: pd.DataFrame, contactos: pd.DataFrame, bench: pd.DataFrame) -> pd.DataFrame:
    """Una fila por RUT con sus datos de reparto (saldo solo de operaciones validas para su empresa)."""
    ruts = df.groupby("_rut").agg(
        EMPRESA=("nombre_empresa_asignada", "first"),
        CICLO_RUT=("CICLO_RUT", "first"),
    )
    validas = df[df["_valido"]].groupby("_rut").agg(SALDO=("_saldo", "sum"), OPERACIONES=("_saldo", "size"))
    ruts = ruts.join(validas).fillna({"SALDO": 0.0, "OPERACIONES": 0})
    ruts.index.name = "rut"
    ruts = ruts.reset_index()
    ruts = ruts.merge(contactos, on="rut", how="left").merge(bench, on="rut", how="left")

    for col in ("MESES_CD", "N_CD", "MESES_BENCH", "MESES_PAGO"):
        ruts[col] = ruts[col].fillna(0).astype(int)
    for col in ("TELEFONO_CD", "TELEFONOS_CD", "MES_PAGO"):
        ruts[col] = ruts[col].fillna("")
    ruts["PERFIL_RIESGO"] = ruts["PERFIL_RIESGO"].fillna(SIN_PERFIL)
    ruts["CD_6M"] = ruts["MESES_CD"].gt(0).map({True: "SI", False: "NO"})
    ruts["PAGO_6M"] = ruts["MESES_PAGO"].gt(0).map({True: "SI", False: "NO"})
    return ruts


def puntaje(g: pd.DataFrame) -> pd.Series:
    """Probabilidad estimada de contener: historial de contencion suavizado + contacto directo + perfil."""
    con_hist = g["MESES_BENCH"] > 0
    tasa_grupo = (g.loc[con_hist, "MESES_PAGO"].sum() / g.loc[con_hist, "MESES_BENCH"].sum()) if con_hist.any() else 0.5
    tasa = (g["MESES_PAGO"] + 2 * tasa_grupo) / (g["MESES_BENCH"] + 2)
    cd = g["MESES_CD"].clip(upper=3) * 0.05
    perfil = g["PERFIL_RIESGO"].map(PERFIL_PUNTOS).fillna(0.0)
    return tasa + cd + perfil


def seleccionar(g: pd.DataFrame, cupos: int, alta_cuantia: bool) -> pd.DataFrame:
    """Si hay mas RUT que cupos, se quedan los de mayor probabilidad de contener; dentro de cada tramo, mayor saldo."""
    if len(g) <= cupos:
        return g
    g = g.copy()
    if alta_cuantia:
        g = g.sort_values(["SALDO", "rut"], ascending=[False, True]).head(cupos * TC_POOL_SALDO)
    # Tramos de 0,05 de puntaje para que el saldo decida entre casos de probabilidad parecida.
    g["_tramo"] = (puntaje(g) / 0.05).round().astype(int)
    g = g.sort_values(["_tramo", "SALDO", "rut"], ascending=[False, False, True]).head(cupos)
    return g.drop(columns="_tramo")


def repartir(df: pd.DataFrame, n: int, estrato: list[str]) -> pd.Series:
    """Reparte por estrato compensando saldo; devuelve el indice de ejecutivo (0..n-1) por fila.
    Misma logica que ETL/estrategia_asignacion_itau_castigo.py."""
    saldo = [0.0] * n
    ops = [0] * n
    ruts = [0] * n
    marginal = [{} for _ in range(n)]
    asignado = {}

    def entregar(idx, row, k: int) -> None:
        asignado[idx] = k
        saldo[k] += row.SALDO
        ops[k] += row.OPERACIONES
        ruts[k] += 1

    ordenado = df.sort_values(["SALDO", "rut"], ascending=[False, True])
    estratos = []
    for _, grupo in ordenado.groupby(estrato, sort=True):
        filas = list(grupo.itertuples())
        estratos.append(filas)
        completos = len(filas) - len(filas) % n
        for i in range(0, completos, n):
            orden = sorted(range(n), key=lambda k: (saldo[k], ops[k], k))
            for row, k in zip(filas[i : i + n], orden):
                entregar(row.Index, row, k)
        usados = set()
        for row in filas[completos:]:
            claves = [(c, getattr(row, c)) for c in estrato]
            k = min(
                (k for k in range(n) if k not in usados),
                key=lambda k: (ruts[k], sum(marginal[k].get(c, 0) for c in claves), saldo[k], ops[k], k),
            )
            usados.add(k)
            for c in claves:
                marginal[k][c] = marginal[k].get(c, 0) + 1
            entregar(row.Index, row, k)

    # Ajuste fino: intercambia RUT del mismo estrato entre ejecutivos mientras mejore el equilibrio de saldo y operaciones.
    saldo_medio = sum(saldo) / n or 1.0
    ops_medio = sum(ops) / n or 1.0

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
                    d_saldo = y.SALDO - x.SALDO
                    d_ops = y.OPERACIONES - x.OPERACIONES
                    if costo(a, d_saldo, d_ops) + costo(b, -d_saldo, -d_ops) < costo(a) + costo(b) - 1e-12:
                        asignado[x.Index], asignado[y.Index] = b, a
                        saldo[a] += d_saldo
                        saldo[b] -= d_saldo
                        ops[a] += d_ops
                        ops[b] -= d_ops
                        mejoro = True
        if not mejoro:
            break
    return pd.Series(asignado)


def asignar_grupos(ruts: pd.DataFrame) -> pd.DataFrame:
    ruts = ruts.copy()
    ruts["GRUPO"] = ""
    ruts["EJECUTIVO"] = pd.NA
    for nombre, empresa, cmin, cmax, ejecutivos in GRUPOS:
        en_grupo = (ruts["EMPRESA"] == empresa) & ruts["CICLO_RUT"].between(cmin, cmax) & (ruts["OPERACIONES"] > 0)
        g = ruts[en_grupo]
        cupos = TOPE_RUT * len(ejecutivos)
        elegidos = seleccionar(g, cupos, alta_cuantia=nombre == "TC_ALTA")
        ruts.loc[g.index, "GRUPO"] = f"{nombre} {NO_CARTERIZADO}"
        ruts.loc[elegidos.index, "GRUPO"] = nombre
        if len(ejecutivos) == 1:
            ruts.loc[elegidos.index, "EJECUTIVO"] = ejecutivos[0]
            continue
        estrato = ["CD_6M", "PAGO_6M", "PERFIL_RIESGO"] + (["CICLO_RUT"] if cmax > cmin else [])
        indice = repartir(elegidos, len(ejecutivos), estrato)
        ruts.loc[indice.index, "EJECUTIVO"] = [ejecutivos[k] for k in indice.values]

    sin_grupo = ruts["GRUPO"] == ""
    ruts.loc[sin_grupo & ~ruts["EMPRESA"].isin(PRODUCTOS_EMPRESA), "GRUPO"] = "EMPRESA SIN REPARTO"
    ruts.loc[sin_grupo & ruts["EMPRESA"].isin(PRODUCTOS_EMPRESA) & (ruts["CICLO_RUT"] == 0), "GRUPO"] = "FLUJO CICLO 0"
    ruts.loc[ruts["GRUPO"] == "", "GRUPO"] = "FUERA DE PARAMETROS"
    return ruts


def resumen(ruts: pd.DataFrame) -> pd.DataFrame:
    c = ruts[ruts["EJECUTIVO"].notna()].copy()
    c["EJECUTIVO"] = c["EJECUTIVO"].astype(int)
    res = c.groupby(["GRUPO", "EJECUTIVO"]).agg(
        RUT=("rut", "count"),
        OPERACIONES=("OPERACIONES", "sum"),
        RUT_CON_ARRASTRE=("OPERACIONES", lambda s: int((s > 1).sum())),
        SALDO_ARRASTRE=("SALDO", "sum"),
        PCT_CD_6M=("CD_6M", lambda s: (s == "SI").mean()),
        PCT_PAGO_6M=("PAGO_6M", lambda s: (s == "SI").mean()),
    )
    perfiles = pd.crosstab([c["GRUPO"], c["EJECUTIVO"]], c["PERFIL_RIESGO"], normalize="index").add_prefix("PCT_PERFIL_")
    ciclos = pd.crosstab([c["GRUPO"], c["EJECUTIVO"]], c["CICLO_RUT"]).add_prefix("RUT_CICLO_")
    res = res.join(perfiles).join(ciclos).fillna(0).reset_index()
    for col in ("RUT", "SALDO_ARRASTRE"):
        res[f"DESV_{col}"] = res[col] / res.groupby("GRUPO")[col].transform("mean") - 1
    res = res.sort_values("EJECUTIVO")
    res["EJECUTIVO"] = etiqueta(res["EJECUTIVO"])
    return res.rename(columns={"RUT": "RUT_UNICOS"})


def etiqueta(ejecutivo: pd.Series) -> pd.Series:
    return ejecutivo.map(lambda n: f"Ejecutivo {int(n)}" if pd.notna(n) else None)


def armar_salida(df: pd.DataFrame, ruts: pd.DataFrame) -> pd.DataFrame:
    info = ruts.set_index("rut")
    salida = df.copy()
    r = salida["_rut"]
    salida["GRUPO"] = r.map(info["GRUPO"])
    # Solo las operaciones del producto que corresponde a la empresa llevan ejecutivo.
    salida["EJECUTIVO"] = etiqueta(r.map(info["EJECUTIVO"]).where(salida["_valido"]))
    fuera = ~salida["_valido"] & salida["nombre_empresa_asignada"].isin(PRODUCTOS_EMPRESA)
    salida.loc[fuera, "GRUPO"] = "PRODUCTO FUERA DE EMPRESA"
    for col in ("CD_6M", "MESES_CD", "TELEFONO_CD", "FECHA_ULTIMO_CD", "TELEFONOS_CD", "PAGO_6M", "MESES_PAGO", "MES_PAGO", "PERFIL_RIESGO"):
        salida[col] = r.map(info[col])
    salida["SALDO_RUT"] = r.map(info["SALDO"])
    return salida.drop(columns=[c for c in salida.columns if c.startswith("_")])


def rellenar(ruts: pd.DataFrame, rel: pd.DataFrame, contactos, bench, empresa: str, ciclo: int, ejecutivo: int,
             producto: str | None = None):
    """Completa al ejecutivo hasta TOPE_RUT con RUT de la empresa, ciclo y producto indicados que no sean arrastre:
    todas sus operaciones del archivo de relleno son de esa empresa, ciclo y producto, y no estan con otro ejecutivo."""
    cupo = TOPE_RUT - int((ruts["EJECUTIVO"] == ejecutivo).sum())
    if cupo <= 0:
        print(f"Ejecutivo {ejecutivo} ya tiene {TOPE_RUT} RUT, no se agrega relleno")
        return rel.iloc[0:0], ruts.iloc[0:0]
    es_caso = (rel["nombre_empresa_asignada"] == empresa) & (rel["_ciclo"] == ciclo)
    if producto:
        es_caso &= rel["nombre_producto"] == producto
    limpio = es_caso.groupby(rel["_rut"]).transform("all")
    asignados = set(ruts.loc[ruts["EJECUTIVO"].notna(), "rut"])
    candidatos = rel[limpio & ~rel["_rut"].isin(asignados) & rel["_rut"].notna()].copy()
    # Todas las operaciones del caso cuentan para el saldo y van con el ejecutivo.
    candidatos["_valido"] = True
    g = armar_ruts(candidatos, contactos, bench)
    elegidos = seleccionar(g, cupo, alta_cuantia=False)
    nombre = f"RELLENO {empresa} C{ciclo}" + (f" {producto.upper()}" if producto else "")
    elegidos = elegidos.assign(GRUPO=nombre, EJECUTIVO=ejecutivo)
    print(f"Relleno Ejecutivo {ejecutivo}: {len(g)} RUT candidatos, se agregan {len(elegidos)}")
    return candidatos[candidatos["_rut"].isin(elegidos["rut"])], elegidos


def escribir(destino: Path, salida: pd.DataFrame, res: pd.DataFrame) -> Path:
    try:
        with pd.ExcelWriter(destino, engine="openpyxl") as xw:
            salida.to_excel(xw, sheet_name="Asignacion", index=False)
            res.to_excel(xw, sheet_name="Resumen", index=False)
    except PermissionError:
        # El Excel anterior esta abierto: se guarda con la hora.
        destino = destino.with_name(f"{destino.stem}_{datetime.now():%H%M%S}{destino.suffix}")
        return escribir(destino, salida, res)
    return destino


def main() -> None:
    args = parse_args()
    df = leer_archivo(args.csv, args.hoja)
    df["ORIGEN"] = Path(args.csv).name
    hasta = pd.to_datetime(df["dia"].iloc[0], format="%Y%m%d").date().isoformat()
    rel = None
    if args.relleno_csv and args.relleno_ejecutivo:
        rel = leer_archivo(args.relleno_csv)
        rel["ORIGEN"] = Path(args.relleno_csv).name

    with connect() as cn:
        cur = cn.cursor()
        todos = pd.concat([df["_rut"], rel["_rut"]]) if rel is not None else df["_rut"]
        cargar_ruts(cur, todos.dropna().unique())
        contactos = leer_contactos(cur, args.desde, hasta)
        bench = leer_bench(cur, args.desde)

    ruts = asignar_grupos(armar_ruts(df, contactos, bench))
    salida = armar_salida(df, ruts)
    if rel is not None:
        filas_rel, ruts_rel = rellenar(
            ruts, rel, contactos, bench, args.relleno_empresa, args.relleno_ciclo, args.relleno_ejecutivo,
            args.relleno_producto,
        )
        # Un RUT de relleno que ya venia en la base se reemplaza por sus filas del archivo de relleno.
        ruts = pd.concat([ruts[~ruts["rut"].isin(ruts_rel["rut"])], ruts_rel], ignore_index=True)
        salida = pd.concat(
            [salida[~salida["rut"].isin(filas_rel["rut"])], armar_salida(filas_rel, ruts_rel)], ignore_index=True
        )
    res = resumen(ruts)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(f"Ventana contacto/pagos: {args.desde} a {hasta}")
    print(ruts["GRUPO"].value_counts().to_string())
    print(res.to_string(index=False, float_format=lambda v: f"{v:,.3f}"))

    destino = Path(args.csv).with_name(f"{Path(args.csv).stem}_ejecutivos.xlsx")
    print(f"OK: {escribir(destino, salida, res)}")


if __name__ == "__main__":
    sys.exit(main())
