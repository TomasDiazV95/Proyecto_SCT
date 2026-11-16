"""Simulador de convenios Veritus: datos del deudor por RUT desde la asignacion del mes.

Fuente: dbo.tmp_asignacion_veritus (ETL/etl_asignacion_veritus.py), una fila por operacion. Se usa el
ultimo PERIODO cargado. El calculo del convenio (PUT / plan de pago) corre en el navegador.
"""

from __future__ import annotations

import re

from database import run_query


class RutInvalido(ValueError):
    pass


def _dv(cuerpo: int) -> str:
    suma, factor = 0, 2
    for digito in reversed(str(cuerpo)):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    return "0" if resto == 11 else "K" if resto == 10 else str(resto)


def candidatos_rut(texto: str) -> list[tuple[int, str]]:
    """RUT escrito por el ejecutivo -> lecturas posibles [(cuerpo, dv)].

    Con guion ('3.390.953-5') lo que sigue es el DV y se valida. Sin guion ('33909535' o '3390953') es
    ambiguo: puede venir con o sin DV, asi que se prueban ambas lecturas (la con DV solo si el DV cuadra).
    """
    limpio = re.sub(r"[^0-9kK-]", "", str(texto or "")).upper()
    if "-" in limpio:
        cuerpo, _, dv = limpio.partition("-")
        dv = dv.replace("-", "")
        if not cuerpo.isdigit() or not 1 <= len(cuerpo) <= 8 or not re.fullmatch(r"[0-9K]", dv):
            raise RutInvalido("RUT inválido: revisa el número.")
        if _dv(int(cuerpo)) != dv:
            raise RutInvalido("RUT inválido: el dígito verificador no corresponde.")
        return [(int(cuerpo), dv)]

    lecturas: list[tuple[int, str]] = []
    cuerpo, dv = limpio[:-1], limpio[-1:]
    if cuerpo.isdigit() and 1 <= len(cuerpo) <= 8 and _dv(int(cuerpo)) == dv:
        lecturas.append((int(cuerpo), dv))
    if limpio.isdigit() and 1 <= len(limpio) <= 8:
        lecturas.append((int(limpio), _dv(int(limpio))))
    if not lecturas:
        raise RutInvalido("RUT inválido: revisa el número y el dígito verificador.")
    return lecturas


def _texto(valor) -> str | None:
    texto = str(valor).strip() if valor is not None else ""
    return texto or None


def _numero(valor) -> float:
    return float(valor) if valor is not None else 0.0


def get_deudor(rut_texto: str) -> dict | None:
    lecturas = candidatos_rut(rut_texto)
    sql = """
    SELECT
        a.PERIODO, a.FECHA_ASIGNACION, a.RAZON_SOCIAL, a.BANCO, a.SEGMENTO_JUDICIAL, a.CARTERA,
        CAST(a.DEUDA_TOTAL_RUT AS float) AS deuda_total_rut,
        a.ID_CONTRATO, a.TIPO_DE_PRODUCTO,
        CAST(a.SALDO_FINAL AS float) AS saldo_final,
        CAST(a.DEUDA_CASTIGADA AS float) AS deuda_castigada,
        a.FECHA_CASTIGO,
        a.EMAIL1, a.EMAIL2, a.FONO1, a.FONO2, a.FONO3, a.FONO4
    FROM dbo.tmp_asignacion_veritus a
    WHERE a.PERIODO = (SELECT MAX(PERIODO) FROM dbo.tmp_asignacion_veritus)
      AND a.RUT = ?
    ORDER BY a.SALDO_FINAL DESC
    """
    rows, rut, dv = [], None, None
    for rut, dv in lecturas:
        rows = run_query(sql, (rut,))
        if rows:
            break
    if not rows:
        return None

    primera = rows[0]
    deuda_archivo = max((r.get("deuda_total_rut") or 0) for r in rows)
    suma_saldos = sum(_numero(r.get("saldo_final")) for r in rows)

    def unicos(*campos: str) -> list[str]:
        vistos: list[str] = []
        for r in rows:
            for campo in campos:
                valor = _texto(r.get(campo))
                if valor and valor.lower() != "none" and valor not in vistos:
                    vistos.append(valor)
        return vistos

    return {
        "rut": rut,
        "dv": dv,
        "nombre": _texto(primera.get("RAZON_SOCIAL")) or "",
        "banco": _texto(primera.get("BANCO")),
        "entidad_legal": _texto(primera.get("SEGMENTO_JUDICIAL")),
        "portafolio": _texto(primera.get("CARTERA")),
        "periodo": _texto(primera.get("PERIODO")),
        "fecha_asignacion": primera.get("FECHA_ASIGNACION").isoformat() if primera.get("FECHA_ASIGNACION") else None,
        # DEUDA_TOTAL_RUT viene del banco y es la suma de SALDO_FINAL; si faltara, se suma aca.
        "deuda_total": round(deuda_archivo or suma_saldos),
        "emails": unicos("EMAIL1", "EMAIL2"),
        "fonos": unicos("FONO1", "FONO2", "FONO3", "FONO4"),
        "operaciones": [
            {
                "id_contrato": _texto(r.get("ID_CONTRATO")),
                "producto": _texto(r.get("TIPO_DE_PRODUCTO")),
                "saldo_final": round(_numero(r.get("saldo_final"))),
                "deuda_castigada": round(_numero(r.get("deuda_castigada"))),
                "fecha_castigo": r.get("FECHA_CASTIGO").isoformat() if r.get("FECHA_CASTIGO") else None,
            }
            for r in rows
        ],
    }
