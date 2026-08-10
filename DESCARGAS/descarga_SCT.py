import os
import re
import time
import html
import shutil
import zipfile

from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

import requests
from playwright.sync_api import Playwright, sync_playwright


# ============================================================
# CONFIGURACION GENERAL
# ============================================================

URL_VISOR = "https://recuperaciones.santanderconsumer.cl/"

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
ROOT_ENV_PATH = BASE_DIR.parent / ".env"


# ============================================================
# CARGAR .ENV
# ============================================================

def cargar_env(path: Path) -> None:
    if not path.exists():
        return

    for linea in path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()

        if not linea:
            continue

        if linea.startswith("#"):
            continue

        if "=" not in linea:
            continue

        clave, valor = linea.split("=", 1)

        os.environ.setdefault(
            clave.strip(),
            valor.strip()
        )


cargar_env(ROOT_ENV_PATH)
cargar_env(ENV_PATH)


# ============================================================
# VARIABLES .ENV
# ============================================================

USUARIO = os.getenv("USUARIO", "")
CLAVE = os.getenv("CLAVE", "")

GRAPH_TENANT_ID = os.getenv("GRAPH_TENANT_ID", "")
GRAPH_CLIENT_ID = os.getenv("GRAPH_CLIENT_ID", "")
GRAPH_CLIENT_SECRET = os.getenv("GRAPH_CLIENT_SECRET", "")
VISOR_MAILBOX = os.getenv("VISOR_MAILBOX", "")

# Espera antes de comenzar a consultar Outlook/Graph.
OTP_WAIT_SECONDS = int(
    os.getenv("OTP_WAIT_SECONDS", "60")
)

# Tiempo adicional máximo esperando OTP.
OTP_TIMEOUT_SECONDS = int(
    os.getenv("OTP_TIMEOUT_SECONDS", "180")
)


# ============================================================
# CARPETAS LOCALES
# ============================================================

CARPETA_BASE = Path(
    r"C:\Users\Analista de Datos\Desktop\SCT BENCH"
)

CARPETA_ZIP = CARPETA_BASE / "zip"
CARPETA_EXTRAIDA = CARPETA_BASE / "extraido"


# ============================================================
# DESCARGAS
# ============================================================

DESCARGAS = [
    {
        "nombre": "BENCH CASTIGO",
        "carpeta_visor": "📁 BENCH CASTIGO",
        "patron_archivo": "BENCH CASTIGO - PHOENIX",
    },
    {
        "nombre": "BENCH MORA TARDIA",
        "carpeta_visor": "📁 BENCH MORA TARDIA",
        "patron_archivo": "BENCH MORA TARDIA - PHOENIX",
    },
    {
        "nombre": "BENCH MORA TEMPRANA - TELEFONIA",
        "carpeta_visor": "📁 BENCH MORA TEMPRANA",
        "patron_archivo": (
            "BENCH MORA TEMPRANA - PHOENIX (TELEFONIA)"
        ),
    },
]


# ============================================================
# VALIDACION
# ============================================================

def validar_configuracion() -> None:
    variables = {
        "USUARIO": USUARIO,
        "CLAVE": CLAVE,
        "GRAPH_TENANT_ID": GRAPH_TENANT_ID,
        "GRAPH_CLIENT_ID": GRAPH_CLIENT_ID,
        "GRAPH_CLIENT_SECRET": GRAPH_CLIENT_SECRET,
        "VISOR_MAILBOX": VISOR_MAILBOX,
    }

    faltantes = [
        nombre
        for nombre, valor in variables.items()
        if not valor
    ]

    if faltantes:
        raise RuntimeError(
            "Faltan variables en .env: "
            + ", ".join(faltantes)
        )


# ============================================================
# MICROSOFT GRAPH
# ============================================================

def obtener_token_graph() -> str:
    url = (
        "https://login.microsoftonline.com/"
        f"{GRAPH_TENANT_ID}/oauth2/v2.0/token"
    )

    data = {
        "client_id": GRAPH_CLIENT_ID,
        "client_secret": GRAPH_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }

    response = requests.post(
        url,
        data=data,
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            "No fue posible obtener token de Graph. "
            f"HTTP {response.status_code}: "
            f"{response.text}"
        )

    return response.json()["access_token"]


def html_a_text(contenido: str) -> str:
    if not contenido:
        return ""

    contenido = html.unescape(contenido)

    contenido = re.sub(
        r"<script.*?</script>",
        " ",
        contenido,
        flags=re.DOTALL | re.IGNORECASE,
    )

    contenido = re.sub(
        r"<style.*?</style>",
        " ",
        contenido,
        flags=re.DOTALL | re.IGNORECASE,
    )

    contenido = re.sub(
        r"<[^>]+>",
        " ",
        contenido,
    )

    contenido = re.sub(
        r"\s+",
        " ",
        contenido,
    )

    return contenido.strip()


def extraer_codigo_visor(
    contenido: str
) -> str | None:

    texto = html_a_text(
        contenido
    ).upper()

    # 8 caracteres alfanumericos,
    # con al menos una letra y un numero.
    patron = (
        r"\b"
        r"(?=[A-Z0-9]{8}\b)"
        r"(?=[A-Z0-9]*[A-Z])"
        r"(?=[A-Z0-9]*[0-9])"
        r"[A-Z0-9]{8}"
        r"\b"
    )

    match = re.search(
        patron,
        texto,
    )

    if match:
        return match.group(0)

    return None


def normalizar_texto(
    texto: str
) -> str:

    return (
        texto
        .casefold()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )


def obtener_codigo_desde_graph(
    fecha_solicitud: datetime,
    timeout: int = 180,
) -> str:

    token = obtener_token_graph()

    mailbox = quote(
        VISOR_MAILBOX,
        safe="@.",
    )

    url = (
        "https://graph.microsoft.com/v1.0/"
        f"users/{mailbox}/messages"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    params = {
        "$top": 50,
        "$select": (
            "id,"
            "subject,"
            "receivedDateTime,"
            "body"
        ),
        "$orderby": "receivedDateTime desc",
    }

    fecha_minima = (
        fecha_solicitud
        - timedelta(minutes=2)
    )

    inicio = time.time()

    print()
    print("=" * 70)
    print("BUSCANDO CODIGO OTP")
    print("=" * 70)

    while time.time() - inicio < timeout:

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=30,
        )

        if not response.ok:
            raise RuntimeError(
                "Error consultando Graph. "
                f"HTTP {response.status_code}: "
                f"{response.text}"
            )

        mensajes = (
            response
            .json()
            .get("value", [])
        )

        for mensaje in mensajes:

            asunto = (
                mensaje
                .get("subject", "")
                .strip()
            )

            received_raw = mensaje.get(
                "receivedDateTime"
            )

            if not received_raw:
                continue

            try:
                received = datetime.fromisoformat(
                    received_raw.replace(
                        "Z",
                        "+00:00",
                    )
                )
            except ValueError:
                continue

            if received < fecha_minima:
                continue

            if (
                "codigo de autenticacion"
                not in normalizar_texto(asunto)
            ):
                continue

            body = (
                mensaje
                .get("body", {})
                .get("content", "")
            )

            codigo = extraer_codigo_visor(
                body
            )

            if codigo:
                print(
                    "OTP encontrado correctamente."
                )
                return codigo

        transcurrido = int(
            time.time() - inicio
        )

        print(
            f"OTP todavía no disponible "
            f"({transcurrido}/{timeout}s). "
            "Reintentando en 3 segundos..."
        )

        time.sleep(3)

    raise TimeoutError(
        "No se encontró el código de Visor "
        f"después de {timeout} segundos."
    )


# ============================================================
# LIMPIEZA LOCAL
# ============================================================

def limpiar_carpeta_extraida() -> None:

    CARPETA_EXTRAIDA.mkdir(
        parents=True,
        exist_ok=True,
    )

    for elemento in CARPETA_EXTRAIDA.iterdir():

        if elemento.is_file():
            elemento.unlink()

        elif elemento.is_dir():
            shutil.rmtree(
                elemento
            )

    print(
        f"Carpeta limpia: "
        f"{CARPETA_EXTRAIDA}"
    )


def limpiar_carpeta_zip() -> None:

    CARPETA_ZIP.mkdir(
        parents=True,
        exist_ok=True,
    )

    for archivo in CARPETA_ZIP.glob(
        "*.zip"
    ):

        try:
            archivo.unlink()

        except Exception as e:
            print(
                f"No se pudo eliminar "
                f"{archivo.name}: {e}"
            )

    print(
        f"Carpeta ZIP limpia: "
        f"{CARPETA_ZIP}"
    )


# ============================================================
# FECHAS
# ============================================================

def obtener_fecha_de_fila(
    fila
) -> datetime | None:

    texto = fila.inner_text()

    match = re.search(
        r"(\d{2}-\d{2}-\d{4})"
        r"\s+"
        r"(\d{2}:\d{2})",
        texto,
    )

    if not match:
        return None

    try:
        return datetime.strptime(
            f"{match.group(1)} "
            f"{match.group(2)}",
            "%d-%m-%Y %H:%M",
        )

    except ValueError:
        return None


# ============================================================
# ORDENAR TABLA DESCENDENTE
# ============================================================

def ordenar_fecha_descendente(
    page,
    frame,
) -> None:

    print(
        "Ordenando por fecha de modificación..."
    )

    boton_fecha = frame.get_by_role(
        "button",
        name="FECHA DE MODIFICACIÓN ↓↑",
    )

    boton_fecha.wait_for(
        state="visible",
        timeout=10000,
    )

    # Primer clic para ordenar.
    boton_fecha.click()

    # Espera corta para actualización del DOM.
    page.wait_for_timeout(
        400
    )

    filas = frame.locator("tr")

    # Buscamos las dos primeras filas
    # que realmente tengan fecha.
    fechas = []

    limite = min(
        filas.count(),
        8,
    )

    for i in range(limite):

        fila = filas.nth(i)

        fecha = obtener_fecha_de_fila(
            fila
        )

        if fecha:
            fechas.append(fecha)

        if len(fechas) == 2:
            break

    # Si no conseguimos dos fechas,
    # no podemos verificar la dirección.
    if len(fechas) < 2:
        print(
            "No fue posible validar la dirección "
            "del orden; se continúa."
        )
        return

    fecha_1 = fechas[0]
    fecha_2 = fechas[1]

    # Si la primera es menor que la segunda,
    # estamos en ascendente.
    if fecha_1 < fecha_2:

        print(
            "Orden ascendente detectado. "
            "Cambiando a descendente..."
        )

        boton_fecha.click()

        page.wait_for_timeout(
            400
        )

    else:
        print(
            "Orden descendente confirmado."
        )


# ============================================================
# BUSCAR ULTIMO ARCHIVO
# ============================================================

def buscar_fila_mas_reciente(
    page,
    frame,
    patron_archivo: str,
):

    # Ordenamos la tabla primero.
    ordenar_fecha_descendente(
        page,
        frame,
    )

    print(
        f"Buscando: {patron_archivo}"
    )

    # Como ya está ordenada de nuevo a viejo,
    # solo necesitamos la primera coincidencia.
    filas = (
        frame
        .locator("tr")
        .filter(
            has_text=patron_archivo
        )
    )

    # Esperamos una coincidencia real.
    try:
        filas.first.wait_for(
            state="visible",
            timeout=10000,
        )
    except Exception:
        raise FileNotFoundError(
            f"No se encontró '{patron_archivo}'."
        )

    fila = filas.first

    texto = (
        fila
        .inner_text()
        .strip()
    )

    fecha = obtener_fecha_de_fila(
        fila
    )

    print(
        "Archivo seleccionado:"
    )

    print(texto)

    if fecha:
        print(
            f"Fecha modificación: "
            f"{fecha.strftime('%d-%m-%Y %H:%M')}"
        )

    return fila


# ============================================================
# GUARDAR DOWNLOAD
# ============================================================

def guardar_download(
    download,
    nombre_logico: str,
) -> Path:

    nombre_zip = (
        download
        .suggested_filename
    )

    if not nombre_zip.lower().endswith(
        ".zip"
    ):
        nombre_zip += ".zip"

    ruta_zip = (
        CARPETA_ZIP
        / nombre_zip
    )

    if ruta_zip.exists():
        ruta_zip.unlink()

    download.save_as(
        str(ruta_zip)
    )

    if not ruta_zip.exists():
        raise RuntimeError(
            f"No se guardó el ZIP de "
            f"{nombre_logico}."
        )

    if ruta_zip.stat().st_size == 0:
        raise RuntimeError(
            f"ZIP vacío para "
            f"{nombre_logico}."
        )

    print(
        f"ZIP guardado: {ruta_zip}"
    )

    print(
        f"Tamaño: "
        f"{ruta_zip.stat().st_size:,} bytes"
    )

    return ruta_zip


# ============================================================
# DESCARGAR DESDE CARPETA
# ============================================================

def descargar_desde_carpeta(
    page,
    frame,
    configuracion: dict,
) -> Path:

    nombre = configuracion["nombre"]
    carpeta_visor = configuracion[
        "carpeta_visor"
    ]
    patron_archivo = configuracion[
        "patron_archivo"
    ]

    print()
    print("=" * 70)
    print(
        f"PROCESANDO: {nombre}"
    )
    print("=" * 70)

    # ========================================================
    # ABRIR CARPETA
    # ========================================================

    carpeta = frame.get_by_role(
        "link",
        name=carpeta_visor,
    )

    carpeta.wait_for(
        state="visible",
        timeout=10000,
    )

    carpeta.click()

    # En vez de sleep(1500), esperamos
    # directamente a que aparezca una fila.
    frame.locator("tr").first.wait_for(
        state="visible",
        timeout=10000,
    )

    # ========================================================
    # ENCONTRAR ULTIMO ARCHIVO
    # ========================================================

    fila = buscar_fila_mas_reciente(
        page,
        frame,
        patron_archivo,
    )

    # ========================================================
    # DESMARCAR CHECKBOX ANTERIORES
    # ========================================================

    checkboxes_marcados = frame.locator(
        'input[type="checkbox"]:checked'
    )

    cantidad_marcados = (
        checkboxes_marcados.count()
    )

    for i in range(
        cantidad_marcados
    ):

        try:
            checkboxes_marcados.nth(
                0
            ).uncheck()
        except Exception:
            break

    # ========================================================
    # MARCAR CHECKBOX CORRECTO
    # ========================================================

    checkbox = (
        fila
        .locator(
            'input[type="checkbox"]'
        )
        .first
    )

    checkbox.wait_for(
        state="visible",
        timeout=10000,
    )

    checkbox.check()

    if not checkbox.is_checked():
        raise RuntimeError(
            f"No fue posible seleccionar "
            f"{nombre}."
        )

    print(
        "Archivo seleccionado."
    )

    # ========================================================
    # DESCARGAR
    # ========================================================

    boton_descarga = frame.get_by_role(
        "button",
        name="Descargar Archivos",
    )

    boton_descarga.wait_for(
        state="visible",
        timeout=10000,
    )

    print(
        f"Descargando {nombre}..."
    )

    with page.expect_download(
        timeout=120000
    ) as download_info:

        boton_descarga.click()

    download = (
        download_info.value
    )

    print(
        "Descarga recibida."
    )

    return guardar_download(
        download,
        nombre,
    )


# ============================================================
# EXTRAER ZIP
# ============================================================

def extraer_y_eliminar_zip(
    ruta_zip: Path,
) -> list[Path]:

    print(
        f"Extrayendo: {ruta_zip.name}"
    )

    try:

        with zipfile.ZipFile(
            ruta_zip,
            "r",
        ) as zip_ref:

            nombres = zip_ref.namelist()

            zip_ref.extractall(
                CARPETA_EXTRAIDA
            )

        archivos_extraidos = []

        for nombre in nombres:

            archivo = (
                CARPETA_EXTRAIDA
                / nombre
            )

            if archivo.is_file():

                archivos_extraidos.append(
                    archivo
                )

        ruta_zip.unlink()

        print(
            f"ZIP eliminado: "
            f"{ruta_zip.name}"
        )

        return archivos_extraidos

    except Exception:

        print(
            f"Error extrayendo "
            f"{ruta_zip}"
        )

        raise


# ============================================================
# LOGIN + OTP
# ============================================================

def autenticar_visor(
    page
) -> None:

    print()
    print("=" * 70)
    print("LOGIN VISOR")
    print("=" * 70)

    page.goto(
        URL_VISOR,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    # ========================================================
    # USUARIO
    # ========================================================

    campo_usuario = page.get_by_role(
        "textbox",
        name="Número de usuario",
    )

    campo_usuario.wait_for(
        state="visible",
        timeout=30000,
    )

    campo_usuario.fill(
        USUARIO
    )

    # ========================================================
    # CLAVE
    # ========================================================

    campo_clave = page.get_by_role(
        "textbox",
        name="Clave",
    )

    campo_clave.fill(
        CLAVE
    )

    fecha_solicitud_otp = (
        datetime.now(
            timezone.utc
        )
    )

    print(
        "Solicitando código..."
    )

    page.get_by_role(
        "button",
        name="Ingresar",
    ).click()

    # ========================================================
    # CERRAR AVISO
    # ========================================================

    boton_cerrar = page.get_by_text(
        "CERRAR"
    )

    boton_cerrar.wait_for(
        state="visible",
        timeout=30000,
    )

    boton_cerrar.click()

    # ========================================================
    # CAMPO OTP
    # ========================================================

    campo_codigo = page.get_by_role(
        "textbox",
        name="Código de 8 caracteres",
    )

    campo_codigo.wait_for(
        state="visible",
        timeout=30000,
    )

    # ========================================================
    # ESPERA INICIAL OTP
    # ========================================================

    print(
        f"Esperando {OTP_WAIT_SECONDS} "
        "segundos para recibir el correo..."
    )

    page.wait_for_timeout(
        OTP_WAIT_SECONDS * 1000
    )

    # ========================================================
    # GRAPH
    # ========================================================

    codigo = obtener_codigo_desde_graph(
        fecha_solicitud=(
            fecha_solicitud_otp
        ),
        timeout=(
            OTP_TIMEOUT_SECONDS
        ),
    )

    # ========================================================
    # VALIDAR CODIGO
    # ========================================================

    campo_codigo.fill(
        codigo
    )

    page.get_by_role(
        "button",
        name="Validar código",
    ).click()

    # ========================================================
    # ESPERAR HOME
    # ========================================================

    link_explorador = page.get_by_role(
        "link",
        name=" explorador archivos",
    )

    link_explorador.wait_for(
        state="visible",
        timeout=30000,
    )

    print(
        "Login completado."
    )


# ============================================================
# MAIN
# ============================================================

def run(
    playwright: Playwright
) -> None:

    validar_configuracion()

    CARPETA_ZIP.mkdir(
        parents=True,
        exist_ok=True,
    )

    CARPETA_EXTRAIDA.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Limpiar una sola vez.
    limpiar_carpeta_extraida()
    limpiar_carpeta_zip()

    browser = playwright.chromium.launch(
        headless=False
    )

    context = browser.new_context(
        accept_downloads=True
    )

    page = context.new_page()

    try:

        # ====================================================
        # LOGIN
        # ====================================================

        autenticar_visor(
            page
        )

        # ====================================================
        # ABRIR EXPLORADOR UNA SOLA VEZ
        # ====================================================

        print(
            "Abriendo explorador..."
        )

        link_explorador = page.get_by_role(
            "link",
            name=" explorador archivos",
        )

        link_explorador.click()

        iframe = page.locator(
            'iframe[name="myMainFrame"]'
        )

        iframe.wait_for(
            state="attached",
            timeout=30000,
        )

        frame = iframe.content_frame

        if frame is None:
            raise RuntimeError(
                "No fue posible acceder "
                "al iframe myMainFrame."
            )

        # Esperar contenido real.
        frame.locator("body").wait_for(
            state="visible",
            timeout=10000,
        )

        print(
            "Explorador abierto."
        )

        # ====================================================
        # DESCARGAR
        # ====================================================

        zips_descargados = []

        for configuracion in DESCARGAS:

            ruta_zip = descargar_desde_carpeta(
                page,
                frame,
                configuracion,
            )

            zips_descargados.append(
                ruta_zip
            )

        # ====================================================
        # EXTRAER
        # ====================================================

        print()
        print("=" * 70)
        print("EXTRAYENDO ARCHIVOS")
        print("=" * 70)

        archivos_finales = []

        for ruta_zip in zips_descargados:

            extraidos = (
                extraer_y_eliminar_zip(
                    ruta_zip
                )
            )

            archivos_finales.extend(
                extraidos
            )

        # ====================================================
        # RESUMEN
        # ====================================================

        print()
        print("=" * 70)
        print("PROCESO COMPLETADO")
        print("=" * 70)

        for archivo in archivos_finales:

            print(
                f"OK: {archivo.name}"
            )

        print("-" * 70)

        print(
            f"Destino: "
            f"{CARPETA_EXTRAIDA}"
        )

        print(
            f"Archivos extraídos: "
            f"{len(archivos_finales)}"
        )

        print("=" * 70)

    finally:

        try:
            context.close()
        except Exception:
            pass

        try:
            browser.close()
        except Exception:
            pass


# ============================================================
# EJECUCION
# ============================================================

if __name__ == "__main__":

    with sync_playwright() as playwright:
        run(playwright)