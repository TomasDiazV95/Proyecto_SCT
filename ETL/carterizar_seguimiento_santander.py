"""Carteriza casos del seguimiento Santander (hoja Export) entre ejecutivos, sin chocar con RUT ya carterizados.

1. PHOENIX PYME, producto Pyme, ciclos distintos de 0: nuevos ejecutivos (por defecto 9, 10, 11), 350 RUT cada uno.
2. PHOENIX HIPOTECARIO, Hipoteca+FFGG, contenido 0, sin carterizar: se agregan a los ejecutivos hipotecarios que ya
   estan en la columna Carterizado (ciclo 1: Lorena Fuentes y Maria Chavarria; ciclos 2-3: Ingrid Retamal y Claudia
   Aravena) hasta 350 RUT cada una. Los RUT que en la asignacion previa ya eran de una de ellas vuelven con ella.

Los repartos son parejos en contacto directo 6m, pagos 6m, perfil, ciclo y saldo. A todas las filas se les agregan
los meses de pago, el ultimo contacto directo y su telefono.
"""
import argparse
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd

from etl_asignacion_itau_castigo import connect
from estrategia_asignacion_santander import (
    SIN_PERFIL,
    TOPE_RUT,
    cargar_ruts,
    etiqueta,
    leer_bench,
    leer_contactos,
    repartir,
    resumen,
    seleccionar,
)

PYME = {"Empresa": "PHOENIX PYME", "Producto cliente": "Pyme"}
HIPO = {"Empresa": "PHOENIX HIPOTECARIO", "Producto cliente": "Hipoteca+FFGG", "Contenido": "0"}
# (grupo, ciclo minimo, ciclo maximo, ejecutivos que lo ven)
GRUPOS_HIPO = [
    ("HIPO_C1", 1, 1, ["Lorena Fuentes", "Maria Chavarria"]),
    ("HIPO_C2_3", 2, 3, ["Ingrid Retamal", "Claudia Aravena"]),
]
ESTRATO = ["CD_6M", "PAGO_6M", "PERFIL_RIESGO", "CICLO_RUT"]


def parse_args() -> argparse.Namespace:
    raiz = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archivo", default=str(raiz / "Copia de seguimiento al 05-11 Phoenix _ NOV.xlsx"))
    parser.add_argument("--hoja", default="Export")
    parser.add_argument("--salida", default=None, help="Excel de salida (por defecto, <archivo>_ejecutivos.xlsx)")
    parser.add_argument("--ejecutivos", type=int, nargs="+", default=[9, 10, 11], help="Numeros de ejecutivo PYME")
    parser.add_argument("--asignados", nargs="*", default=[], help="Excel con hoja Asignacion (rut, EJECUTIVO) ya repartidos")
    parser.add_argument("--desde", default="2026-05-01", help="Inicio de la ventana de 6 meses")
    parser.add_argument("--hasta", default="2026-11-05", help="Fecha del seguimiento (fin de la ventana de contactos)")
    return parser.parse_args()


def leer(ruta: str, **kw) -> pd.DataFrame:
    try:
        return pd.read_excel(ruta, dtype=str, **kw)
    except PermissionError:
        # Excel abierto: se lee una copia.
        copia = Path(tempfile.gettempdir()) / f"copia_{Path(ruta).name}"
        shutil.copyfile(ruta, copia)
        return pd.read_excel(copia, dtype=str, **kw)


def filtro(df: pd.DataFrame, condiciones: dict) -> pd.Series:
    m = pd.Series(True, index=df.index)
    for col, valor in condiciones.items():
        m &= df[col] == valor
    return m


def leer_previos(archivos: list[str]) -> pd.Series:
    """Ejecutivo (numero) de cada RUT en las asignaciones previas."""
    partes = []
    for ruta in archivos:
        a = leer(ruta, sheet_name="Asignacion", usecols=["rut", "EJECUTIVO"])
        a = a[a["EJECUTIVO"].fillna("") != ""]
        partes.append(pd.Series(a["EJECUTIVO"].values, index=pd.to_numeric(a["rut"], errors="coerce")))
    if not partes:
        return pd.Series(dtype=str)
    s = pd.concat(partes)
    s = s[s.index.notna()]
    s.index = s.index.astype("int64")
    return s[~s.index.duplicated()]


def armar_ruts(df: pd.DataFrame, mask: pd.Series, contactos: pd.DataFrame, bench: pd.DataFrame) -> pd.DataFrame:
    """Una fila por RUT de las filas marcadas: ciclo menor (sin 0), saldo y operaciones."""
    p = df[mask]
    ruts = p.groupby("_rut").agg(
        SALDO=("_saldo", "sum"),
        OPERACIONES=("_saldo", "size"),
        CICLO_RUT=("_ciclo", lambda s: s[s > 0].min() if (s > 0).any() else 0),
        PERFIL_ARCHIVO=("Perfil", "first"),
    )
    ruts.index.name = "rut"
    ruts = ruts.reset_index().merge(contactos, on="rut", how="left").merge(bench, on="rut", how="left")
    for col in ("MESES_CD", "N_CD", "MESES_BENCH", "MESES_PAGO"):
        ruts[col] = ruts[col].fillna(0).astype(int)
    for col in ("TELEFONO_CD", "TELEFONOS_CD", "MES_PAGO"):
        ruts[col] = ruts[col].fillna("")
    # Perfil del seguimiento; si no trae, el ultimo del bench.
    perfil = ruts["PERFIL_ARCHIVO"].fillna("").str.strip().str.upper()
    ruts["PERFIL_RIESGO"] = perfil.where(perfil != "", ruts["PERFIL_RIESGO"]).fillna(SIN_PERFIL)
    ruts["CD_6M"] = ruts["MESES_CD"].gt(0).map({True: "SI", False: "NO"})
    ruts["PAGO_6M"] = ruts["MESES_PAGO"].gt(0).map({True: "SI", False: "NO"})
    ruts["GRUPO"] = ""
    ruts["EJECUTIVO"] = pd.NA
    return ruts.drop(columns="PERFIL_ARCHIVO")


def carterizar_pyme(df, contactos, bench, tomados: set, ejecutivos: list[int]) -> pd.DataFrame:
    ruts = armar_ruts(df, df["_pyme"], contactos, bench)
    ruts.loc[ruts["CICLO_RUT"] == 0, "GRUPO"] = "FLUJO CICLO 0"
    ruts.loc[ruts["rut"].isin(tomados), "GRUPO"] = "YA CARTERIZADO"
    g = ruts[ruts["GRUPO"] == ""]
    elegidos = seleccionar(g, TOPE_RUT * len(ejecutivos), alta_cuantia=False)
    ruts.loc[g.index, "GRUPO"] = "PYME_C1_3 NO CARTERIZADO"
    ruts.loc[elegidos.index, "GRUPO"] = "PYME_C1_3"
    indice = repartir(elegidos, len(ejecutivos), ESTRATO)
    ruts.loc[indice.index, "EJECUTIVO"] = etiqueta(pd.Series([ejecutivos[k] for k in indice.values], index=indice.index))
    print(f"PYME: {len(ruts)} RUT | ya carterizados {int((ruts['GRUPO'] == 'YA CARTERIZADO').sum())} | "
          f"candidatos {len(g)} | elegidos {len(elegidos)}")
    return ruts


def distribuir(elegidos: pd.DataFrame, cupo: dict) -> pd.Series:
    """Reparte en proporcion al cupo de cada ejecutivo, recorriendo estrato por estrato (mezcla pareja) y,
    dentro del estrato, de mayor a menor saldo hacia quien lleva menos saldo."""
    llenado = {e: 0 for e in cupo}
    saldo = {e: 0.0 for e in cupo}
    asignado = {}
    orden = elegidos.sort_values(ESTRATO + ["SALDO", "rut"], ascending=[True] * len(ESTRATO) + [False, True])
    for row in orden.itertuples():
        libres = [e for e in cupo if llenado[e] < cupo[e]]
        e = min(libres, key=lambda e: ((llenado[e] + 1) / cupo[e], saldo[e]))
        asignado[row.Index] = e
        llenado[e] += 1
        saldo[e] += row.SALDO
    return pd.Series(asignado, dtype=object)


def agregar_hipotecario(df, contactos, bench, previos: pd.Series, tomados: set) -> pd.DataFrame:
    sin_carterizar = df["Carterizado"].fillna("").str.strip() == ""
    ruts = armar_ruts(df, df["_hipo"] & sin_carterizar, contactos, bench)
    con = df[~sin_carterizar]
    actuales = con.groupby("Carterizado")["_rut"].nunique()
    # Nombre de cada "Ejecutivo N" previo segun la columna Carterizado del seguimiento.
    num = con["_rut"].map(previos)
    nombres = con[num.notna()].groupby(num[num.notna()])["Carterizado"].agg(lambda s: s.mode().iat[0])
    todos = [e for *_, ejs in GRUPOS_HIPO for e in ejs]

    previo = ruts["rut"].map(previos).map(nombres)
    vuelve = previo.isin(todos)
    ruts.loc[vuelve, "EJECUTIVO"] = previo[vuelve]
    ruts.loc[vuelve, "GRUPO"] = "HIPO VUELVE A SU EJECUTIVO"
    # Un RUT de la asignacion previa con otro ejecutivo (no hipotecario) no se toca.
    otro = ruts["GRUPO"].eq("") & ruts["rut"].isin(set(previos.index) | tomados)
    ruts.loc[otro, "GRUPO"] = "YA CARTERIZADO"
    ruts.loc[ruts["GRUPO"].eq("") & (ruts["CICLO_RUT"] == 0), "GRUPO"] = "FLUJO CICLO 0"

    for grupo, cmin, cmax, ejecutivos in GRUPOS_HIPO:
        g = ruts[ruts["GRUPO"].eq("") & ruts["CICLO_RUT"].between(cmin, cmax)]
        cupo = {e: TOPE_RUT - int(actuales.get(e, 0)) - int((ruts["EJECUTIVO"] == e).sum()) for e in ejecutivos}
        cupo = {e: c for e, c in cupo.items() if c > 0}
        elegidos = seleccionar(g, sum(cupo.values()), alta_cuantia=False) if cupo else g.iloc[0:0]
        ruts.loc[g.index, "GRUPO"] = f"{grupo} NO AGREGADO"
        ruts.loc[elegidos.index, "GRUPO"] = f"{grupo} AGREGADO"
        if len(elegidos):
            asignado = distribuir(elegidos, cupo)
            ruts.loc[asignado.index, "EJECUTIVO"] = asignado
        print(f"{grupo}: candidatos {len(g)} | cupos {cupo} | agregados {len(elegidos)}")
    ruts.loc[ruts["GRUPO"] == "", "GRUPO"] = "FUERA DE PARAMETROS"
    return ruts, actuales


def resumen_hipo(ruts: pd.DataFrame, actuales: pd.Series) -> pd.DataFrame:
    c = ruts[ruts["EJECUTIVO"].notna()]
    res = c.groupby("EJECUTIVO").agg(
        RUT_AGREGADOS=("rut", "count"),
        RUT_VUELVEN=("GRUPO", lambda s: int((s == "HIPO VUELVE A SU EJECUTIVO").sum())),
        OPERACIONES=("OPERACIONES", "sum"),
        SALDO_MM=("SALDO", "sum"),
        PCT_CD_6M=("CD_6M", lambda s: (s == "SI").mean()),
        PCT_PAGO_6M=("PAGO_6M", lambda s: (s == "SI").mean()),
    )
    perfiles = pd.crosstab(c["EJECUTIVO"], c["PERFIL_RIESGO"], normalize="index").add_prefix("PCT_PERFIL_")
    ciclos = pd.crosstab(c["EJECUTIVO"], c["CICLO_RUT"]).add_prefix("RUT_CICLO_")
    res = res.join(perfiles).join(ciclos).fillna(0)
    res.insert(0, "RUT_ANTES", actuales.reindex(res.index).fillna(0).astype(int))
    res.insert(3, "RUT_TOTAL", res["RUT_ANTES"] + res["RUT_AGREGADOS"])
    orden = [e for *_, ejs in GRUPOS_HIPO for e in ejs]
    return res.reindex([e for e in orden if e in res.index]).reset_index()


def escribir(destino: Path, hojas: dict) -> Path:
    try:
        with pd.ExcelWriter(destino, engine="openpyxl") as xw:
            for nombre, d in hojas.items():
                d.to_excel(xw, sheet_name=nombre, index=False)
    except PermissionError:
        # El Excel anterior esta abierto: se guarda con la hora.
        destino = destino.with_name(f"{destino.stem}_{datetime.now():%H%M%S}{destino.suffix}")
        return escribir(destino, hojas)
    return destino


def main() -> None:
    args = parse_args()
    df = leer(args.archivo, sheet_name=args.hoja)
    df["_rut"] = pd.to_numeric(df["Rut"], errors="coerce").astype("Int64")
    df["_ciclo"] = pd.to_numeric(df["Ciclo"], errors="coerce").fillna(0).astype(int)
    df["_saldo"] = pd.to_numeric(df["MM$ Monto"], errors="coerce").fillna(0.0)
    df["_pyme"] = filtro(df, PYME)
    df["_hipo"] = filtro(df, HIPO)

    with connect() as cn:
        cur = cn.cursor()
        cargar_ruts(cur, df["_rut"].dropna().unique())
        contactos = leer_contactos(cur, args.desde, args.hasta)
        bench = leer_bench(cur, args.desde)

    previos = leer_previos(args.asignados)
    tomados = set(df.loc[df["Carterizado"].fillna("").str.strip() != "", "_rut"].dropna()) | set(previos.index)
    pyme = carterizar_pyme(df, contactos, bench, tomados, args.ejecutivos)
    tomados |= set(pyme.loc[pyme["EJECUTIVO"].notna(), "rut"])
    hipo, actuales = agregar_hipotecario(df, contactos, bench, previos, tomados - set(previos.index))

    # Salida: el archivo original con las columnas nuevas (datos de contacto y pago para todas las filas).
    sin_carterizar = df["Carterizado"].fillna("").str.strip() == ""
    r = df["_rut"]
    p, h = pyme.set_index("rut"), hipo.set_index("rut")
    datos = pd.concat([
        contactos.set_index("rut")[["FECHA_ULTIMO_CD", "TELEFONO_CD"]],
        bench.set_index("rut")[["MESES_PAGO", "MES_PAGO"]],
    ], axis=1)
    salida = df.drop(columns=[c for c in df.columns if c.startswith("_")]).copy()
    es_hipo = df["_hipo"] & sin_carterizar
    salida["EJECUTIVO"] = r.map(p["EJECUTIVO"]).where(df["_pyme"])
    salida.loc[es_hipo, "EJECUTIVO"] = r[es_hipo].map(h["EJECUTIVO"])
    salida["GRUPO"] = r.map(p["GRUPO"]).where(df["_pyme"])
    salida.loc[es_hipo, "GRUPO"] = r[es_hipo].map(h["GRUPO"])
    # Carterizado del archivo y, si no trae, el ejecutivo asignado aqui (para tablas dinamicas).
    salida["CARTERIZADO_FINAL"] = salida["Carterizado"].where(~sin_carterizar, salida["EJECUTIVO"])
    salida["CD_6M"] = r.map(datos["FECHA_ULTIMO_CD"]).notna().map({True: "SI", False: "NO"})
    salida["FECHA_ULTIMO_CD"] = r.map(datos["FECHA_ULTIMO_CD"])
    salida["TELEFONO_CD"] = r.map(datos["TELEFONO_CD"]).fillna("")
    salida["MESES_PAGO"] = r.map(datos["MESES_PAGO"]).fillna(0).astype(int)
    salida["MES_PAGO"] = r.map(datos["MES_PAGO"]).fillna("")
    # Las columnas numericas del original vuelven a ser numero (se leyeron como texto), si no se pierde ningun dato.
    for col in ("Rut", "Operaciones", "Contenido", "Ciclo", "MM$ Monto", "Campaña", "Compromiso", "Marco mora"):
        num = pd.to_numeric(salida[col], errors="coerce")
        if num.notna().sum() == salida[col].notna().sum():
            salida[col] = num

    res_pyme = resumen(pyme.assign(EJECUTIVO=pyme["EJECUTIVO"].str.replace("Ejecutivo ", "").astype("Int64")))
    res_hipo = resumen_hipo(hipo, actuales)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(res_pyme.to_string(index=False, float_format=lambda v: f"{v:,.3f}"))
    print(res_hipo.to_string(index=False, float_format=lambda v: f"{v:,.3f}"))

    destino = Path(args.salida) if args.salida else Path(args.archivo).with_name(f"{Path(args.archivo).stem}_ejecutivos.xlsx")
    destino = escribir(destino, {"Asignacion": salida, "Resumen PYME": res_pyme, "Resumen Hipotecario": res_hipo})
    print(f"OK: {destino}")


if __name__ == "__main__":
    sys.exit(main())
