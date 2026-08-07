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
            valor.strip(),
        )


cargar_env(ROOT_ENV_PATH)
cargar_env(ENV_PATH)


# ============================================================
# VARIABLES .ENV
# ============================================================

USUARIO = os.getenv(
    "USUARIO",
    "",
)

CLAVE = os.getenv(
    "CLAVE",
    "",
)

GRAPH_TENANT_ID = os.getenv(
    "GRAPH_TENANT_ID",
    "",
)

GRAPH_CLIENT_ID = os.getenv(
    "GRAPH_CLIENT_ID",
    "",
)

GRAPH_CLIENT_SECRET = os.getenv(
    "GRAPH_CLIENT_SECRET",
    "",
)

VISOR_MAILBOX = os.getenv(
    "VISOR_MAILBOX",
    "",
)


# Espera fija antes de empezar a consultar Graph
OTP_WAIT_SECONDS = int(
    os.getenv(
        "OTP_WAIT_SECONDS",
        "60",
    )
)

# Después de la espera inicial, cuánto tiempo
# máximo seguirá consultando Graph
OTP_TIMEOUT_SECONDS = int(
    os.getenv(
        "OTP_TIMEOUT_SECONDS",
        "180",
    )
)


# ============================================================
# CARPETAS LOCALES
# ============================================================

CARPETA_BASE = Path(
    r"C:\Users\Analista de Datos\Desktop\SCT BENCH"
)

CARPETA_ZIP = (
    CARPETA_BASE
    / "zip"
)

CARPETA_EXTRAIDA = (
    CARPETA_BASE
    / "extraido"
)


# ============================================================
# CONFIGURACION DE DESCARGAS
# ============================================================

DESCARGAS = [
    {
        "nombre": "BENCH CASTIGO",

        "carpeta_visor":
            "📁 BENCH CASTIGO",

        "patron_archivo":
            "BENCH CASTIGO - PHOENIX",
    },

    {
        "nombre": "BENCH MORA TARDIA",

        "carpeta_visor":
            "📁 BENCH MORA TARDIA",

        "patron_archivo":
            "BENCH MORA TARDIA - PHOENIX",
    },

    {
        "nombre": "BENCH MORA TEMPRANA - TELEFONIA",

        "carpeta_visor":
            "📁 BENCH MORA TEMPRANA",

        "patron_archivo":
            (
                "BENCH MORA TEMPRANA - "
                "PHOENIX (TELEFONIA)"
            ),
    },
]


# ============================================================
# VALIDAR CONFIGURACION
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
        f"{GRAPH_TENANT_ID}"
        "/oauth2/v2.0/token"
    )

    data = {
        "client_id":
            GRAPH_CLIENT_ID,

        "client_secret":
            GRAPH_CLIENT_SECRET,

        "scope":
            "https://graph.microsoft.com/.default",

        "grant_type":
            "client_credentials",
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


# ============================================================
# HTML -> TEXTO
# ============================================================

def html_a_text(
    contenido: str,
) -> str:

    if not contenido:
        return ""

    contenido = html.unescape(
        contenido
    )

    contenido = re.sub(
        r"<script.*?</script>",
        " ",
        contenido,
        flags=(
            re.DOTALL
            | re.IGNORECASE
        ),
    )

    contenido = re.sub(
        r"<style.*?</style>",
        " ",
        contenido,
        flags=(
            re.DOTALL
            | re.IGNORECASE
        ),
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


# ============================================================
# EXTRAER OTP
# ============================================================

def extraer_codigo_visor(
    contenido: str,
) -> str | None:

    texto = html_a_text(
        contenido
    ).upper()

    # OTP:
    # - 8 caracteres
    # - alfanumerico
    # - al menos una letra
    # - al menos un numero

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


# ============================================================
# NORMALIZAR TEXTO
# ============================================================

def normalizar_texto(
    texto: str,
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


# ============================================================
# OBTENER OTP DESDE GRAPH
# ============================================================

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
        "Authorization":
            f"Bearer {token}",

        "Accept":
            "application/json",
    }

    params = {
        "$top": 50,

        "$select": (
            "id,"
            "subject,"
            "receivedDateTime,"
            "body,"
            "from"
        ),

        "$orderby":
            "receivedDateTime desc",
    }

    # Margen por diferencia de reloj
    fecha_minima = (
        fecha_solicitud
        - timedelta(minutes=2)
    )

    inicio = time.time()

    print()
    print("=" * 70)
    print("BUSCANDO CODIGO OTP")
    print("=" * 70)

    intento = 0

    while (
        time.time() - inicio
        < timeout
    ):

        intento += 1

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
            .get(
                "value",
                [],
            )
        )

        print(
            f"Intento {intento}: "
            f"{len(mensajes)} correos revisados."
        )

        for mensaje in mensajes:

            asunto = (
                mensaje
                .get(
                    "subject",
                    "",
                )
                .strip()
            )

            received_raw = (
                mensaje
                .get(
                    "receivedDateTime"
                )
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

            # Ignorar correos antiguos
            if received < fecha_minima:
                continue

            asunto_normalizado = (
                normalizar_texto(
                    asunto
                )
            )

            # Asunto real:
            # Código de autenticación
            if (
                "codigo de autenticacion"
                not in asunto_normalizado
            ):
                continue

            print(
                "Correo de autenticacion encontrado: "
                f"{received_raw}"
            )

            body = (
                mensaje
                .get(
                    "body",
                    {},
                )
                .get(
                    "content",
                    "",
                )
            )

            codigo = (
                extraer_codigo_visor(
                    body
                )
            )

            if codigo:

                print(
                    "OTP encontrado correctamente."
                )

                # No imprimir el OTP
                return codigo

        transcurrido = int(
            time.time()
            - inicio
        )

        print(
            "OTP todavía no disponible "
            f"({transcurrido}/{timeout}s). "
            "Nuevo intento en 3 segundos..."
        )

        time.sleep(3)

    raise TimeoutError(
        "No se encontró el código "
        f"después de {timeout} segundos."
    )


# ============================================================
# LIMPIAR CARPETAS
# ============================================================

def limpiar_carpeta_extraida() -> None:

    CARPETA_EXTRAIDA.mkdir(
        parents=True,
        exist_ok=True,
    )

    for elemento in (
        CARPETA_EXTRAIDA.iterdir()
    ):

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

    for archivo in (
        CARPETA_ZIP.glob(
            "*.zip"
        )
    ):

        try:
            archivo.unlink()

        except Exception as e:

            print(
                "No se pudo eliminar "
                f"{archivo.name}: {e}"
            )

    print(
        f"Carpeta ZIP limpia: "
        f"{CARPETA_ZIP}"
    )


# ============================================================
# EXTRAER FECHA DE MODIFICACION
# ============================================================

def extraer_fecha_modificacion(
    texto: str,
) -> datetime | None:

    """
    Busca fechas como:

    07-08-2026 08:27

    y devuelve datetime.
    """

    match = re.search(
        r"\b"
        r"(\d{2}-\d{2}-\d{4})"
        r"\s+"
        r"(\d{2}:\d{2})"
        r"\b",
        texto,
    )

    if not match:
        return None

    fecha_texto = (
        f"{match.group(1)} "
        f"{match.group(2)}"
    )

    try:

        return datetime.strptime(
            fecha_texto,
            "%d-%m-%Y %H:%M",
        )

    except ValueError:

        return None


# ============================================================
# BUSCAR FILA MAS RECIENTE
# ============================================================

def buscar_fila_mas_reciente(
    frame,
    patron_archivo: str,
):

    print(
        f"Buscando archivo: "
        f"{patron_archivo}"
    )

    # Todas las filas que contengan
    # el nombre esperado
    filas = (
        frame
        .locator("tr")
        .filter(
            has_text=patron_archivo
        )
    )

    cantidad = filas.count()

    if cantidad == 0:

        raise FileNotFoundError(
            "No se encontró ningún archivo "
            f"que contenga '{patron_archivo}'."
        )

    candidatos = []

    for indice in range(
        cantidad
    ):

        fila = filas.nth(
            indice
        )

        texto = (
            fila
            .inner_text()
            .strip()
        )

        fecha = (
            extraer_fecha_modificacion(
                texto
            )
        )

        print()
        print(
            f"Candidato #{indice + 1}:"
        )

        print(texto)

        if fecha:

            print(
                "Fecha modificación: "
                f"{fecha.strftime('%d-%m-%Y %H:%M')}"
            )

            candidatos.append(
                (
                    fecha,
                    indice,
                    texto,
                )
            )

        else:

            print(
                "No se pudo detectar "
                "fecha de modificación."
            )

    if not candidatos:

        raise RuntimeError(
            "Se encontraron archivos, "
            "pero no fue posible detectar "
            "la FECHA DE MODIFICACIÓN."
        )

    # Mayor datetime = archivo más reciente
    candidatos.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    fecha_mas_reciente, indice, texto = (
        candidatos[0]
    )

    print()
    print("=" * 60)
    print("ARCHIVO MÁS RECIENTE")
    print("=" * 60)
    print(texto)

    print(
        "Fecha: "
        f"{fecha_mas_reciente.strftime('%d-%m-%Y %H:%M')}"
    )

    return (
        filas.nth(indice),
        fecha_mas_reciente,
    )


# ============================================================
# ABRIR EXPLORADOR
# ============================================================

def abrir_explorador_archivos(
    page,
):

    print()
    print(
        "Abriendo explorador de archivos..."
    )

    iframe = page.locator(
        'iframe[name="myMainFrame"]'
    )

    if iframe.count() > 0:

        frame = (
            iframe
            .content_frame
        )

        if frame is not None:

            page.wait_for_timeout(
                1000
            )

            print(
                "Explorador ya estaba abierto; "
                "se reutiliza la misma sesion."
            )

            return frame

    link_explorador = (
        page.get_by_role(
            "link",
            name=re.compile(r"explorador archivos", re.IGNORECASE),
        )
    )

    link_explorador.wait_for(
        state="visible",
        timeout=30000,
    )

    link_explorador.click()

    iframe.wait_for(
        state="attached",
        timeout=30000,
    )

    frame = (
        iframe
        .content_frame
    )

    if frame is None:

        raise RuntimeError(
            "No fue posible acceder al iframe "
            "del explorador de archivos."
        )

    page.wait_for_timeout(
        1500
    )

    print(
        "Explorador abierto correctamente."
    )

    return frame


# ============================================================
# DESCARGAR ARCHIVO DE UNA CARPETA
# ============================================================

def descargar_archivo_carpeta(
    page,
    configuracion: dict,
) -> Path:

    nombre = (
        configuracion[
            "nombre"
        ]
    )

    carpeta_visor = (
        configuracion[
            "carpeta_visor"
        ]
    )

    patron_archivo = (
        configuracion[
            "patron_archivo"
        ]
    )

    print()
    print("=" * 70)
    print(
        f"PROCESANDO: {nombre}"
    )
    print("=" * 70)

    frame = abrir_explorador_archivos(
        page
    )

    # ========================================================
    # ENTRAR A LA CARPETA
    # ========================================================

    carpeta = (
        frame
        .get_by_role(
            "link",
            name=carpeta_visor,
        )
    )

    carpeta.wait_for(
        state="visible",
        timeout=30000,
    )

    carpeta.click()

    # Dar tiempo a cargar la tabla
    page.wait_for_timeout(
        1500
    )

    print(
        f"Carpeta abierta: {nombre}"
    )

    # ========================================================
    # BUSCAR EL ARCHIVO MAS RECIENTE
    # ========================================================

    fila, fecha = (
        buscar_fila_mas_reciente(
            frame,
            patron_archivo,
        )
    )

    # ========================================================
    # CHECKBOX DE LA FILA ELEGIDA
    # ========================================================

    checkbox = (
        fila
        .locator(
            'input[type="checkbox"]'
        )
        .first
    )

    if checkbox.count() == 0:

        raise RuntimeError(
            "No se encontró checkbox "
            "para el archivo seleccionado."
        )

    # Desmarcar otros checkbox visibles
    checkboxes = (
        frame
        .locator(
            'input[type="checkbox"]'
        )
    )

    for i in range(
        checkboxes.count()
    ):

        cb = checkboxes.nth(i)

        try:

            if (
                cb.is_visible()
                and cb.is_checked()
            ):

                cb.uncheck()

        except Exception:
            pass

    # Marcar SOLO el archivo elegido
    checkbox.check()

    print(
        "Archivo seleccionado para descarga."
    )

    # ========================================================
    # DESCARGAR ZIP
    # ========================================================

    with page.expect_download(
        timeout=120000,
    ) as download_info:

        frame.get_by_role(
            "button",
            name="Descargar Archivos",
        ).click()

    download = (
        download_info.value
    )

    nombre_zip = (
        download
        .suggested_filename
    )

    if not (
        nombre_zip
        .lower()
        .endswith(".zip")
    ):

        nombre_zip += ".zip"

    ruta_zip = (
        CARPETA_ZIP
        / nombre_zip
    )

    # Evitar colisión con ZIP anterior
    if ruta_zip.exists():
        ruta_zip.unlink()

    download.save_as(
        str(ruta_zip)
    )

    print(
        f"ZIP descargado: "
        f"{ruta_zip}"
    )

    return ruta_zip


# ============================================================
# EXTRAER ZIP Y ELIMINARLO
# ============================================================

def extraer_y_eliminar_zip(
    ruta_zip: Path,
) -> list[Path]:

    print(
        f"Extrayendo: "
        f"{ruta_zip.name}"
    )

    try:

        with zipfile.ZipFile(
            ruta_zip,
            "r",
        ) as zip_ref:

            nombres = (
                zip_ref.namelist()
            )

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

        print(
            f"ZIP extraído correctamente: "
            f"{ruta_zip.name}"
        )

        # Eliminar ZIP solo si extractall terminó OK
        ruta_zip.unlink()

        print(
            f"ZIP eliminado: "
            f"{ruta_zip.name}"
        )

        return archivos_extraidos

    except Exception:

        print(
            "ERROR extrayendo ZIP."
        )

        print(
            "Se mantiene para revisión:"
        )

        print(
            ruta_zip
        )

        raise


# ============================================================
# LOGIN + OTP
# ============================================================

def autenticar_visor(
    page,
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

    # Usuario
    campo_usuario = (
        page.get_by_role(
            "textbox",
            name="Número de usuario",
        )
    )

    campo_usuario.wait_for(
        state="visible",
        timeout=30000,
    )

    campo_usuario.fill(
        USUARIO
    )

    # Clave
    campo_clave = (
        page.get_by_role(
            "textbox",
            name="Clave",
        )
    )

    campo_clave.fill(
        CLAVE
    )

    # Guardar hora ANTES de solicitar OTP
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
    # AVISO
    # ========================================================

    boton_cerrar = (
        page.get_by_text(
            "CERRAR"
        )
    )

    boton_cerrar.wait_for(
        state="visible",
        timeout=30000,
    )

    boton_cerrar.click()

    # ========================================================
    # CAMPO OTP
    # ========================================================

    campo_codigo = (
        page.get_by_role(
            "textbox",
            name="Código de 8 caracteres",
        )
    )

    campo_codigo.wait_for(
        state="visible",
        timeout=30000,
    )

    # ========================================================
    # ESPERAR CORREO
    # ========================================================

    print(
        f"Esperando {OTP_WAIT_SECONDS} "
        "segundos antes de consultar Graph..."
    )

    page.wait_for_timeout(
        OTP_WAIT_SECONDS
        * 1000
    )

    # ========================================================
    # OBTENER OTP
    # ========================================================

    codigo = (
        obtener_codigo_desde_graph(
            fecha_solicitud=(
                fecha_solicitud_otp
            ),
            timeout=(
                OTP_TIMEOUT_SECONDS
            ),
        )
    )

    # ========================================================
    # INGRESAR OTP
    # ========================================================

    campo_codigo.fill(
        codigo
    )

    page.get_by_role(
        "button",
        name="Validar código",
    ).click()

    print(
        "Código enviado."
    )

    # ========================================================
    # ESPERAR LOGIN EXITOSO
    # ========================================================

    link_explorador = (
        page.get_by_role(
            "link",
            name=" explorador archivos",
        )
    )

    link_explorador.wait_for(
        state="visible",
        timeout=30000,
    )

    print(
        "Login completado correctamente."
    )


# ============================================================
# MAIN
# ============================================================

def run(
    playwright: Playwright,
) -> None:

    validar_configuracion()

    # Crear carpetas
    CARPETA_ZIP.mkdir(
        parents=True,
        exist_ok=True,
    )

    CARPETA_EXTRAIDA.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Limpiar SOLO una vez
    limpiar_carpeta_extraida()
    limpiar_carpeta_zip()

    # ========================================================
    # NAVEGADOR
    # ========================================================

    browser = (
        playwright
        .chromium
        .launch(
            headless=False
        )
    )

    context = (
        browser
        .new_context(
            accept_downloads=True
        )
    )

    page = (
        context
        .new_page()
    )

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

        print()
        print(
            "Abriendo explorador de archivos..."
        )

        link_explorador = (
            page.get_by_role(
                "link",
                name=" explorador archivos",
            )
        )

        link_explorador.click()

        # ====================================================
        # OBTENER IFRAME UNA SOLA VEZ
        # ====================================================

        iframe = page.locator(
            'iframe[name="myMainFrame"]'
        )

        iframe.wait_for(
            state="attached",
            timeout=30000,
        )

        frame = (
            iframe
            .content_frame
        )

        print(
            "Explorador abierto correctamente."
        )

        # ====================================================
        # DESCARGAR LOS 3 ZIP
        # ====================================================

        zips_descargados = []

        for configuracion in (
            DESCARGAS
        ):

            ruta_zip = (
                descargar_archivo_carpeta(
                    page,
                    configuracion,
                )
            )

            zips_descargados.append(
                ruta_zip
            )

        # ====================================================
        # EXTRAER LOS 3 ZIP
        # ====================================================

        print()
        print("=" * 70)
        print("EXTRAYENDO ARCHIVOS")
        print("=" * 70)

        archivos_finales = []

        for ruta_zip in (
            zips_descargados
        ):

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

        for archivo in (
            archivos_finales
        ):

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
