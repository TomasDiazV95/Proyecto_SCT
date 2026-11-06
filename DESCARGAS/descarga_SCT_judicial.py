"""Descarga del visor SCT con el usuario judicial (USUARIO_JUD / CLAVE_JUD).

Mismo visor que descarga_SCT.py, pero otra cuenta y otro buzon OTP
(VISOR_MAILBOX_JUD). Reutiliza la logica de descarga_SCT.py y deja el archivo
en la misma carpeta de los bench, donde lo lee ETL/etl_bench_sc_judicial.py.

Solo reemplaza los archivos del bench judicial; los del usuario principal se
conservan. Puede correr antes, despues o en paralelo con descarga_SCT.py.
"""

import os

from playwright.sync_api import Playwright, sync_playwright

from descarga_SCT import (
    CARPETA_EXTRAIDA,
    CARPETA_ZIP,
    PATRON_ARCHIVOS_JUDICIAL,
    ejecutar_descargas,
    validar_variables,
)


# ============================================================
# VARIABLES .ENV (ya cargadas por descarga_SCT)
# ============================================================

USUARIO_JUD = os.getenv("USUARIO_JUD", "").strip()
CLAVE_JUD = os.getenv("CLAVE_JUD", "").strip()
VISOR_MAILBOX_JUD = os.getenv("VISOR_MAILBOX_JUD", "").strip()

# ZIP propios: la descarga principal limpia CARPETA_ZIP al iniciar.
CARPETA_ZIP_JUDICIAL = CARPETA_ZIP / "judicial"


# ============================================================
# CONFIGURACION DESCARGAS
# ============================================================

# Archivo: YYYYMMDD - BENCH BENCH JUDICIAL - P&S.xlsx; se toma el de carga mas reciente.
DESCARGAS_JUDICIAL = [
    {
        "nombre":
            "BENCH JUDICIAL",

        "carpeta_visor":
            "📁 BENCH JUDICIAL",

        "patron_archivo":
            "BENCH BENCH JUDICIAL - P&S",

        "fin_de_mes":
            True,
    },
]


# ============================================================
# MAIN
# ============================================================

def run(
    playwright: Playwright,
) -> None:

    validar_variables(
        {
            "USUARIO_JUD": USUARIO_JUD,
            "CLAVE_JUD": CLAVE_JUD,
            "VISOR_MAILBOX_JUD": VISOR_MAILBOX_JUD,
        }
    )

    # Solo se reemplaza el bench judicial; los demas archivos se conservan.
    CARPETA_EXTRAIDA.mkdir(
        parents=True,
        exist_ok=True,
    )

    for archivo in CARPETA_EXTRAIDA.glob(
        PATRON_ARCHIVOS_JUDICIAL
    ):

        try:
            archivo.unlink()
        except PermissionError as exc:
            # No se salta: si queda un archivo viejo, el ETL podria cargarlo.
            raise PermissionError(
                f"No se pudo borrar '{archivo.name}' porque otro programa lo tiene abierto "
                "(normalmente Excel). Cierralo y vuelve a ejecutar la descarga."
            ) from exc

    ejecutar_descargas(
        playwright,
        DESCARGAS_JUDICIAL,
        usuario=USUARIO_JUD,
        clave=CLAVE_JUD,
        buzon=VISOR_MAILBOX_JUD,
        carpeta_zip=CARPETA_ZIP_JUDICIAL,
    )


# ============================================================
# EJECUCION
# ============================================================

if __name__ == "__main__":

    with sync_playwright() as playwright:

        run(playwright)
