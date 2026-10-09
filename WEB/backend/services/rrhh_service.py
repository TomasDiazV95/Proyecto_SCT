from __future__ import annotations

import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from database import run_query
from services import (
    bit_castigo_service,
    bit_service,
    gm_service,
    itau_castigo_service,
    itau_vencida_service,
    itau_vigente_service,
    la_araucana_service,
    sc_tardia_service,
    sc_temprana_service,
    sth_service,
)


# Planilla de cumplimientos de campañas para RRHH y Finanzas (formato "Cumplimientos Campañas <Mes> <AA>.xlsx").
# No calcula nada: cada adaptador toma el resultado del panel de productividad de su negocio en el ultimo
# corte del mes y lo deja en filas colaborador + variable. Solo salen las variables que la plataforma calcula.

HEADERS = [
    "MES",
    "CLIENTE",
    "CAMPAÑA",
    "VARIABLE A EVALUAR",
    "COLABORADOR",
    "RUT",
    "CUMPLIMIENTO TOTAL INDIVIDUAL",
    "APORTE INDIVIDUAL",
    "CUMPLIMIENTOS GRUPALES",
    "INSERTAR Q VARIABLES",
    "ANEXOS / RESPALDO",
    "ESTADO ANEXO / RESPALDO",
]
# Hoja NEGOCIOS: una fila por negocio cursado en el mes (respaldo de las variables de Q de negocios).
NEGOCIOS_HEADERS = [
    "MES",
    "CLIENTE",
    "CAMPAÑA",
    "TIPO NEGOCIO",
    "N° OPERACIÓN",
    "RUT CLIENTE",
    "EJECUTIVO",
    "MONTO DEUDA",
    "ABONO INICIAL",
    "TRAMO",
    "FECHA",
]
RESUMEN_HEADERS = ["CLIENTE", "CAMPAÑA", "CORTE", "N° COLABORADORES", "CUMPLIMIENTO PROMEDIO", "ESTADO"]

NA = "N/A"
VARIABLE_INDIVIDUAL = "Cumplimiento Individual"
# Filas de los paneles que no son colaboradores (cartera sin asignar, grupal o totales).
NO_COLABORADORES = {"PHOENIX", "GRUPAL", "TOTAL", "TOTAL GENERAL", "SIN EJECUTIVO", "SIN GESTION"}
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
PERIODOS_VISIBLES = 13
CORTES_TTL_SEGUNDOS = 300
CONSOLIDADO_WORKERS = 4

_cortes_cache: dict[str, tuple[float, list[str]]] = {}
_ruts_cache: tuple[float, dict[str, str]] | None = None


def _clave_nombre(nombre) -> str:
    """Nombre sin tildes, en mayusculas y con espacios simples, para cruzar con la nomina."""
    text = unicodedata.normalize("NFD", str(nombre or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().upper()


def _ruts_colaboradores() -> dict[str, str]:
    """RUT por nombre de panel (dbo.rrhh_colaboradores). nombre_panel admite varias formas separadas por ';'."""
    global _ruts_cache
    if _ruts_cache and time.monotonic() - _ruts_cache[0] < CORTES_TTL_SEGUNDOS:
        return _ruts_cache[1]
    sql = """
    SELECT rut, nombre_panel
    FROM dbo.rrhh_colaboradores
    WHERE activo = 1
      AND nombre_panel IS NOT NULL
    """
    ruts: dict[str, str] = {}
    for row in run_query(sql):
        for nombre in str(row["nombre_panel"]).split(";"):
            clave = _clave_nombre(nombre)
            if clave:
                ruts[clave] = str(row["rut"]).strip()
    _ruts_cache = (time.monotonic(), ruts)
    return ruts


def _parse_periodo(periodo: str | None) -> date:
    """Mes de la planilla: acepta 'YYYY-MM' o 'YYYY-MM-DD'. Sin valor, el mes en curso."""
    text = str(periodo or "").strip()
    if not text:
        return date.today().replace(day=1)
    match = re.match(r"^(\d{4})-(\d{2})", text)
    if not match:
        raise ValueError(f"Periodo inválido: {periodo}")
    return date(int(match[1]), int(match[2]), 1)


def _mes_de(valor) -> str:
    """'YYYY-MM' de una fecha de corte, en cualquiera de los formatos que usan los paneles
    ('YYYY-MM-DD', 'YYYY-MM-DD (Cierre)', 'YYYYMM', 'MM-YYYY')."""
    text = str(valor or "").strip()
    match = re.match(r"^(\d{4})-?(\d{2})", text)
    if match:
        return f"{match[1]}-{match[2]}"
    match = re.match(r"^(\d{2})-(\d{4})$", text)
    if match:
        return f"{match[2]}-{match[1]}"
    return ""


def _es_colaborador(nombre) -> bool:
    text = str(nombre or "").strip()
    return bool(text) and text.upper() not in NO_COLABORADORES


def _pct(value) -> float | None:
    """Los paneles que trabajan en escala 0-100 se llevan a fraccion (1 = 100%), como el resto."""
    return None if value is None else float(value) / 100.0


def _pct_texto(value: float) -> str:
    return f"{value * 100:.2f}%".replace(".", ",")


class _Planilla:
    """Arma las filas de una campaña con los datos comunes (mes, cliente, corte)."""

    def __init__(self, mes: date, cliente: str, campana: str, corte: str):
        self.mes = mes
        self.cliente = cliente
        self.campana = f"{campana} {MESES[mes.month - 1]} {mes:%y}"
        self.corte = corte
        self.rows: list[dict] = []
        self.negocios: list[dict] = []

    def zona(self, zona: str) -> "_Planilla":
        otra = _Planilla(self.mes, self.cliente, "", self.corte)
        otra.campana = f"{self.campana} - {zona}"
        otra.rows = self.rows
        return otra

    def con_campana(self, campana: str) -> "_Planilla":
        otra = _Planilla(self.mes, self.cliente, campana, self.corte)
        otra.rows = self.rows
        otra.negocios = self.negocios
        return otra

    def add_negocio(self, tipo: str, operacion, ejecutivo: str, *, rut=None, deuda=None, abono=None, tramo=None, fecha=None) -> None:
        self.negocios.append(
            {
                "MES": self.mes,
                "CLIENTE": self.cliente,
                "CAMPAÑA": self.campana,
                "TIPO NEGOCIO": tipo,
                "N° OPERACIÓN": str(operacion or "").strip(),
                "RUT CLIENTE": str(rut or "").strip(),
                "EJECUTIVO": str(ejecutivo).strip(),
                "MONTO DEUDA": NA if deuda is None else deuda,
                "ABONO INICIAL": NA if abono is None else abono,
                "TRAMO": tramo or NA,
                "FECHA": fecha or "",
            }
        )

    def add(self, variable: str, colaborador: str, *, individual=None, aporte=None, grupal=None, q=None) -> None:
        # Una variable sin ningun valor calculado no se informa.
        if individual is None and aporte is None and grupal is None and q is None:
            return
        self.rows.append(
            {
                "MES": self.mes,
                "CLIENTE": self.cliente,
                "CAMPAÑA": self.campana,
                "VARIABLE A EVALUAR": variable,
                "COLABORADOR": str(colaborador).strip(),
                "RUT": "",
                "CUMPLIMIENTO TOTAL INDIVIDUAL": NA if individual is None else individual,
                "APORTE INDIVIDUAL": NA if aporte is None else aporte,
                "CUMPLIMIENTOS GRUPALES": NA if grupal is None else grupal,
                "INSERTAR Q VARIABLES": NA if q is None else q,
                "ANEXOS / RESPALDO": f"Plataforma · corte {self.corte}",
                "ESTADO ANEXO / RESPALDO": "COMPLETO",
            }
        )


# ---------------------------------------------------------------------------
# Adaptadores: un negocio -> filas de la planilla
# ---------------------------------------------------------------------------

SC_TARDIA_BLOQUES = [
    ("C5", "Cumplimiento C5"),
    ("C6", "Cumplimiento C6"),
    ("SUSCEPTIBLE CV", "Cumplimiento SCV al cierre de mes"),
    ("PRE CASTIGO", "Cumplimiento Precastigo al cierre"),
    (sc_tardia_service.CASTIGO_TOTAL_BLOCK, "Cumplimiento Castigo"),
]


def _sc_tardia(p: _Planilla) -> None:
    # Una campaña por zona, igual que la planilla de RRHH (RM, Zona Norte, Zona Sur).
    for zona in sc_tardia_service.get_filter_values()["zonas"]:
        filtros = {"periodo": p.corte, "zona": zona, "tramo": None, "apertura": None, "ejecutivo": None}
        campana = p.zona(zona)
        # Normalizacion C3: se suma primero y se divide despues, como en el panel.
        norm: dict[str, list[float]] = {}
        for row in sc_tardia_service.get_cycle_view(dict(filtros)):
            if row.get("bloque") == "C3":
                acc = norm.setdefault(row["ejecutivo"], [0.0, 0.0])
                acc[0] += float(row.get("normalizado") or 0)
                acc[1] += float(row.get("monto_meta_norm") or 0)

        for row in sc_tardia_service.get_general_view(dict(filtros)):
            nombre = row["ejecutivo"]
            if not _es_colaborador(nombre):
                continue
            campana.add(VARIABLE_INDIVIDUAL, nombre, individual=_pct(row["cumplimiento_operativo"]))
            normalizado, meta_norm = norm.get(nombre, [0.0, 0.0])
            if meta_norm:
                tope = sc_tardia_service.CUMPLIMIENTO_MAX / 100.0
                campana.add("Normalización C3", nombre, individual=min(normalizado / meta_norm, tope))
            for bloque, variable in SC_TARDIA_BLOQUES:
                if bloque in row["bloques"]:
                    campana.add(variable, nombre, individual=_pct(row["bloques"][bloque]))


def _sc_temprana(p: _Planilla) -> None:
    for row in sc_temprana_service.get_cycle_view({"periodo": p.corte}):
        if not _es_colaborador(row["ejecutivo"]):
            continue
        for tramo in ("c1", "c2", "c3"):
            p.add(f"Aporte Individual {tramo.upper()}", row["ejecutivo"], aporte=_pct(row[f"{tramo}_porc_aporte"]))


# Bucket del panel -> variable de la planilla (el ultimo tramo se informa como 91-120).
GM_BUCKETS = {"6 a 30": "Contención 6-30", "31 a 60": "Contención 31-60", "61 a 90": "Contención 61-90", "91 a 150": "Contención 91-120"}


def _gm(p: _Planilla) -> None:
    buckets = [b for b in gm_service.get_bucket_view({"periodo": p.corte}) if b["bucket"] in gm_service.BUCKET_ORDER]
    for row in gm_service.get_general_view({"periodo": p.corte, "ejecutivo": None}):
        if not _es_colaborador(row["ejecutivo"]):
            continue
        p.add(VARIABLE_INDIVIDUAL, row["ejecutivo"], individual=_pct(row["cumplimiento_final"]))
        # La contencion por bucket es de toda la campaña: el mismo valor para cada colaborador.
        for bucket in buckets:
            p.add(GM_BUCKETS.get(bucket["bucket"], f"Contención {bucket['bucket']}"), row["ejecutivo"], grupal=_pct(bucket["porcentaje_contencion"]))


def _ejecutivos_itau_vigente() -> set[str]:
    """Ejecutivos de Itau Vigente con el nombre que llevan en el carterizado de castigo (cambia entre meses)."""
    rows = run_query(
        """
        SELECT a.nombre_carterizado
        FROM dbo.itau_vigente_ejecutivos_castigo a
        INNER JOIN dbo.itau_vigente_ejecutivos e
            ON e.usuario = a.usuario
           AND e.activo = 1
        """
    )
    return {str(row["nombre_carterizado"] or "").strip().upper() for row in rows}


def _itau_castigo(p: _Planilla) -> None:
    # Terreno y MCV son campañas distintas: se separan por el cobrador del ejecutivo.
    campanas = {"Phoenix MCV": p.con_campana("Banco Itau MCV")}
    # Los ejecutivos de Itau Vigente se pagan por esa campaña: no van en castigo.
    vigente = _ejecutivos_itau_vigente()
    for row in itau_castigo_service.get_general({"fecha_carga": p.corte})["rows"]:
        if not _es_colaborador(row["ejecutivo"]) or str(row["ejecutivo"]).strip().upper() in vigente:
            continue
        mcv = row.get("cobrador_vista") in campanas
        campana = campanas[row["cobrador_vista"]] if mcv else p
        campana.add(VARIABLE_INDIVIDUAL, row["ejecutivo"], individual=row["cumplimiento"])
        campana.add("Efectividad Sobre Saldo Asignado", row["ejecutivo"], individual=row["pct_efectividad"])
        if mcv:
            # Contencion cruce vigente del panel; sin saldo en el cruce no se informa.
            if row["cruce_saldo_ini"]:
                campana.add("Contención Vigente", row["ejecutivo"], individual=row["pct_contencion_cruce"])
            campana.add("Cobertura Gestión al 4to día hábil", row["ejecutivo"], individual=row["pct_cobertura"])
        else:
            campana.add("Cobertura Gestión", row["ejecutivo"], individual=row["pct_cobertura"])


def _itau_contencion(p: _Planilla, data: dict) -> None:
    """Cumplimiento individual de Itau Vencida e Itau Vigente."""
    for row in data["rows"]:
        if not _es_colaborador(row["ejecutivo"]):
            continue
        p.add(VARIABLE_INDIVIDUAL, row["ejecutivo"], individual=row.get("cumplimiento"))


def _itau_vencida(p: _Planilla) -> None:
    data = itau_vencida_service.get_general({"fecha_carga": p.corte})
    _itau_contencion(p, data)
    # Contencion de consumo de la campaña por fase medible, en una sola celda como en la planilla.
    fases = [
        f"F{fase['fase']} {_pct_texto(fase['consumo_saldo_cont'] / fase['consumo_saldo_ini'])}"
        for fase in data["total"]["fases"]
        if fase.get("consumo_meta_pct") is not None and fase.get("consumo_saldo_ini")
    ]
    if fases:
        variable = "Cumplimientos Consumo Medibles " + ", ".join(texto.split(" ")[0] for texto in fases)
        for nombre in dict.fromkeys(row["COLABORADOR"] for row in p.rows if row["CAMPAÑA"] == p.campana):
            p.add(variable, nombre, q=" / ".join(fases))


def _itau_vigente(p: _Planilla) -> None:
    data = itau_vigente_service.get_general({"fecha_carga": p.corte})
    _itau_contencion(p, data)
    castigo = data.get("castigo")
    if not castigo:
        return
    for row in data["rows"]:
        if _es_colaborador(row["ejecutivo"]):
            p.add(
                "Recupero Efectivo Castigo Itau Telefonia",
                row["ejecutivo"],
                grupal=castigo["cumplimiento"],
                q=row.get("castigo_recupero"),
            )


BIT_TIPOS_NEGOCIO = {"PC20": "Refinanciamiento", "PC07": "Renegociación"}


def _bit(p: _Planilla) -> None:
    # Negocios cursados en el mes (refinanciamientos + renegociaciones), como en la vista Negocios del panel.
    negocios = {row["ejecutivo"]: row["total"]["cantidad"] for row in bit_service.get_negocios({"periodo": p.corte})["rows"]}
    for row in bit_service.get_general({"periodo": p.corte})["rows"]:
        if not _es_colaborador(row["ejecutivo"]):
            continue
        p.add(VARIABLE_INDIVIDUAL, row["ejecutivo"], individual=row["cumplimiento"])
        p.add("Refinanciamientos, Renegociaciones, Extensiones (GMF)", row["ejecutivo"], q=negocios.get(row["ejecutivo"], 0))
    # Detalle: las operaciones contenidas via producto que cuenta la variable anterior.
    for row in bit_service.get_detalle({"periodo": p.corte})["rows"]:
        tipo = BIT_TIPOS_NEGOCIO.get(str(row["tipo_cont"] or "").strip().upper())
        if tipo and _es_colaborador(row["ejecutivo"]):
            rut = f"{row['rut']}-{row['dv']}" if row.get("dv") else row["rut"]
            p.add_negocio(tipo, row["con_no"], row["ejecutivo"], rut=rut, deuda=row["mto_contenido"], tramo=row["tramo"])


def _bit_castigo(p: _Planilla) -> None:
    for row in bit_castigo_service.get_general({"periodo": p.corte})["rows"]:
        if not _es_colaborador(row["ejecutivo"]):
            continue
        p.add(VARIABLE_INDIVIDUAL, row["ejecutivo"], individual=row["pct_cumpl_meta"])
        p.add("Nuevos Convenios", row["ejecutivo"], q=row["nuevos_convenios"])
        p.add("Efectividad Sobre Saldo Asignado", row["ejecutivo"], individual=row["pct_efectividad"])
        p.add("Cobertura Gestión", row["ejecutivo"], individual=row["pct_cobertura"])
    # El recupero de castigo viene por RUT: se informan las operaciones castigo asignadas de ese RUT.
    for row in bit_castigo_service.get_nuevos_convenios({"periodo": p.corte}):
        if _es_colaborador(row["ejecutivo"]):
            p.add_negocio(
                "Nuevo Convenio",
                " / ".join(row["operaciones"]),
                row["ejecutivo"],
                rut=row["rut"],
                deuda=row["deuda"],
                abono=row["abono_inicial"],
            )


def _sth(p: _Planilla) -> None:
    for row in sth_service.get_general_view({"periodo": p.corte}):
        if not _es_colaborador(row["ejecutivo"]):
            continue
        p.add(VARIABLE_INDIVIDUAL, row["ejecutivo"], individual=_pct(row["cumplimiento_final"]))


LA_ARAUCANA_NEGOCIOS = "Reprogramaciones (Vigente) / Nuevos Convenios (Castigo) Deuda"
LA_ARAUCANA_TRAMOS = [("MENOR", "<= $1.000.000"), ("MAYOR", "> $1.000.000")]


def _la_araucana(p: _Planilla) -> None:
    # El aporte final viene repetido en cada cartera del ejecutivo: se informa una vez.
    aportes: dict[str, float] = {}
    for row in la_araucana_service.get_resumen({"periodo": p.corte})["rows"]:
        if _es_colaborador(row["ejecutivo"]):
            aportes.setdefault(row["ejecutivo"], float(row["pct_aporte_final"] or 0))
    # Negocios del mes (pagos NE-REPRO) por tramo de deuda del folio, como en la vista Negocios del panel.
    negocios: dict[tuple[str, str], int] = {}
    data = la_araucana_service.get_negocios({"periodo": p.corte})
    for row in data["rows"]:
        if _es_colaborador(row["ejecutivo"]):
            negocios[(row["ejecutivo"], row["tramo_deuda"])] = int(row["q_negocios"] or 0)
    tramos = dict(LA_ARAUCANA_TRAMOS)
    for row in data["detalle"]:
        if not _es_colaborador(row["ejecutivo"]):
            continue
        # Vigente = reprogramacion (va con la deuda); castigo y +365 = nuevo convenio (va ademas con el abono).
        vigente = str(row["tipo_cartera"] or "").strip().upper() == "VIGENTE"
        p.add_negocio(
            "Reprogramación" if vigente else f"Nuevo Convenio ({str(row['tipo_cartera']).strip()})",
            row["contrato"],
            row["ejecutivo"],
            rut=row["rut"],
            deuda=float(row["deuda"] or 0),
            abono=None if vigente else float(row["recupero"] or 0),
            tramo=tramos.get(row["tramo_deuda"]),
            fecha=row["fecha_pago"],
        )

    for nombre in dict.fromkeys([*aportes, *(ejecutivo for ejecutivo, _tramo in negocios)]):
        p.add("Aporte Individual", nombre, aporte=aportes.get(nombre))
        for tramo, etiqueta in LA_ARAUCANA_TRAMOS:
            p.add(f"{LA_ARAUCANA_NEGOCIOS} {etiqueta}", nombre, q=negocios.get((nombre, tramo), 0))


def _fechas_itau_contencion() -> list[str]:
    # Itau Vencida e Itau Vigente salen de la misma contencion: comparten fechas de carga.
    return itau_vigente_service.get_filter_values()["fechas_carga"]


# cortes: fechas disponibles del panel (mas reciente primero). build: adaptador del negocio.
NEGOCIOS: dict[str, dict] = {
    "sc-tardia": {
        "cliente": "SANTANDER CONSUMER",
        "campana": "Santander Consumer Terreno",
        "cortes": lambda: sc_tardia_service.get_filter_values()["periodos"],
        "build": _sc_tardia,
    },
    "sc-temprana": {
        "cliente": "SANTANDER CONSUMER",
        "campana": "Santander Consumer Telefonía",
        "cortes": lambda: sc_temprana_service.get_filter_values()["periodos"],
        "build": _sc_temprana,
    },
    "gm": {
        "cliente": "GENERAL MOTORS",
        "campana": "General Motors",
        "cortes": lambda: gm_service.get_filter_values()["periodos"],
        "build": _gm,
    },
    "itau-castigo": {
        "cliente": "BANCO ITAÚ",
        "campana": "Banco Itau Castigo Terreno",
        "cortes": lambda: itau_castigo_service.get_filter_values()["fechas_carga"],
        "build": _itau_castigo,
    },
    "itau-vencida": {
        "cliente": "BANCO ITAÚ",
        "campana": "Banco Itau Vencida",
        "cortes": _fechas_itau_contencion,
        "build": _itau_vencida,
    },
    "itau-vigente": {
        "cliente": "BANCO ITAÚ",
        "campana": "Banco Itau Vigente",
        "cortes": _fechas_itau_contencion,
        "build": _itau_vigente,
    },
    "bit": {
        "cliente": "BANCO INTERNACIONAL",
        "campana": "Banco Internacional Vigente",
        "cortes": lambda: bit_service.get_filter_values()["periodos"],
        "build": _bit,
    },
    "bit-castigo": {
        "cliente": "BANCO INTERNACIONAL",
        "campana": "Banco Internacional Castigo",
        "cortes": lambda: bit_castigo_service.get_filter_values()["periodos"],
        "build": _bit_castigo,
    },
    "sth": {
        "cliente": "BANCO SANTANDER",
        "campana": "Banco Santander Hipoteca",
        "cortes": lambda: sth_service.get_filter_values()["periodos"],
        "build": _sth,
    },
    "la-araucana": {
        "cliente": "LA ARAUCANA",
        "campana": "Caja La Araucana",
        "cortes": lambda: la_araucana_service.get_filtros()["periodos"],
        "build": _la_araucana,
    },
}


def _cortes(codigo: str) -> list[str]:
    cached = _cortes_cache.get(codigo)
    if cached and time.monotonic() - cached[0] < CORTES_TTL_SEGUNDOS:
        return cached[1]
    valores = [str(v).strip() for v in NEGOCIOS[codigo]["cortes"]() if v]
    _cortes_cache[codigo] = (time.monotonic(), valores)
    return valores


def _corte_del_mes(codigo: str, mes: date) -> str | None:
    """Ultimo corte del negocio dentro del mes. Con pre-cierre, la lista ya trae primero la carga de cierre."""
    clave = f"{mes:%Y-%m}"
    return next((valor for valor in _cortes(codigo) if _mes_de(valor) == clave), None)


def _negocio(codigo: str) -> dict:
    negocio = NEGOCIOS.get(str(codigo or "").strip())
    if not negocio:
        raise ValueError(f"Negocio no reconocido: {codigo}")
    return negocio


def _permitidos(codigos: set[str] | None) -> list[str]:
    return [codigo for codigo in NEGOCIOS if codigos is None or codigo in codigos]


def get_periodos() -> list[str]:
    hoy = date.today()
    periodos = []
    for atras in range(PERIODOS_VISIBLES):
        indice = hoy.year * 12 + hoy.month - 1 - atras
        periodos.append(f"{indice // 12:04d}-{indice % 12 + 1:02d}")
    return periodos


def get_negocios(periodo: str | None, codigos: set[str] | None = None) -> list[dict]:
    """codigos: negocios que puede ver el usuario; None = todos."""
    mes = _parse_periodo(periodo)

    def resolver(codigo: str) -> dict:
        negocio = NEGOCIOS[codigo]
        item = {"codigo": codigo, "cliente": negocio["cliente"], "campana": negocio["campana"], "corte": None, "error": None}
        try:
            item["corte"] = _corte_del_mes(codigo, mes)
        except Exception as exc:
            item["error"] = str(exc)
        item["disponible"] = bool(item["corte"])
        return item

    with ThreadPoolExecutor(max_workers=CONSOLIDADO_WORKERS) as pool:
        return list(pool.map(resolver, _permitidos(codigos)))


def get_planilla(periodo: str | None, codigo: str) -> dict:
    negocio = _negocio(codigo)
    mes = _parse_periodo(periodo)
    corte = _corte_del_mes(codigo, mes)
    planilla = _Planilla(mes, negocio["cliente"], negocio["campana"], corte or "")
    if corte:
        negocio["build"](planilla)
        ruts = _ruts_colaboradores()
        for row in planilla.rows:
            row["RUT"] = ruts.get(_clave_nombre(row["COLABORADOR"]), "")
    return {
        "codigo": codigo,
        "cliente": negocio["cliente"],
        "campana": planilla.campana,
        "periodo": f"{mes:%Y-%m}",
        "corte": corte,
        "rows": planilla.rows,
        "negocios": planilla.negocios,
    }


def _resumen(rows: list[dict], corte: str) -> list[dict]:
    """Una linea por campaña: colaboradores y promedio del cumplimiento individual."""
    campanas: dict[tuple[str, str], dict] = {}
    for row in rows:
        item = campanas.setdefault((row["CLIENTE"], row["CAMPAÑA"]), {"colaboradores": set(), "cumplimientos": []})
        item["colaboradores"].add(row["COLABORADOR"])
        valor = row["CUMPLIMIENTO TOTAL INDIVIDUAL"]
        if row["VARIABLE A EVALUAR"] == VARIABLE_INDIVIDUAL and isinstance(valor, (int, float)):
            item["cumplimientos"].append(float(valor))
    return [
        {
            "CLIENTE": cliente,
            "CAMPAÑA": campana,
            "CORTE": corte,
            "N° COLABORADORES": len(item["colaboradores"]),
            "CUMPLIMIENTO PROMEDIO": sum(item["cumplimientos"]) / len(item["cumplimientos"]) if item["cumplimientos"] else NA,
            "ESTADO": "COMPLETO",
        }
        for (cliente, campana), item in campanas.items()
    ]


def get_consolidado(periodo: str | None, codigos: set[str] | None = None) -> dict:
    """Todas las campañas del mes. Un negocio sin datos o con error no bota el consolidado: queda en el resumen."""
    mes = _parse_periodo(periodo)

    def cargar(codigo: str) -> tuple[list[dict], list[dict], list[dict]]:
        negocio = NEGOCIOS[codigo]
        try:
            data = get_planilla(periodo, codigo)
            estado = None if data["rows"] else "SIN DATOS"
        except Exception as exc:
            data = {"rows": [], "negocios": [], "campana": negocio["campana"], "corte": None}
            estado = f"ERROR: {exc}"
        if estado:
            sin_datos = {
                "CLIENTE": negocio["cliente"],
                "CAMPAÑA": data["campana"],
                "CORTE": data.get("corte") or "",
                "N° COLABORADORES": 0,
                "CUMPLIMIENTO PROMEDIO": NA,
                "ESTADO": estado,
            }
            return [], [sin_datos], []
        return data["rows"], _resumen(data["rows"], data["corte"]), data["negocios"]

    rows: list[dict] = []
    resumen: list[dict] = []
    negocios: list[dict] = []
    with ThreadPoolExecutor(max_workers=CONSOLIDADO_WORKERS) as pool:
        for filas, lineas, detalle in pool.map(cargar, _permitidos(codigos)):
            rows += filas
            resumen += lineas
            negocios += detalle
    return {"periodo": f"{mes:%Y-%m}", "rows": rows, "resumen": resumen, "negocios": negocios}
