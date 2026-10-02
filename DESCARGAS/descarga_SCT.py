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

USUARIO = os.getenv(
    "USUARIO",
    ""
)

CLAVE = os.getenv(
    "CLAVE",
    ""
)

GRAPH_TENANT_ID = os.getenv("GRAPH_TENANT_ID", "")
GRAPH_CLIENT_ID = os.getenv("GRAPH_CLIENT_ID", "")
GRAPH_CLIENT_SECRET = os.getenv("GRAPH_CLIENT_SECRET", "")
VISOR_MAILBOX = os.getenv("VISOR_MAILBOX", "")

# Credenciales del usuario judicial (mismo visor, otra cuenta y otro buzon OTP).
USUARIO_JUD = os.getenv("USUARIO_JUD", "").strip()
CLAVE_JUD = os.getenv("CLAVE_JUD", "").strip()
VISOR_MAILBOX_JUD = os.getenv("VISOR_MAILBOX_JUD", "").strip()

# Espera antes de comenzar a consultar Outlook/Graph.
OTP_WAIT_SECONDS = int(
    os.getenv("OTP_WAIT_SECONDS", "60")
)

# Tiempo adicional maximo esperando OTP.
OTP_TIMEOUT_SECONDS = int(
    os.getenv("OTP_TIMEOUT_SECONDS", "180")
)



# ============================================================
# CARPETAS LOCALES DESDE .ENV
# ============================================================

BENCH_TEMP_FOLDER = os.getenv("BENCH_TEMP_FOLDER", "").strip()
BENCH_STC_FOLDER = os.getenv("BENCH_STC_FOLDER", "").strip()
BENCH_SC_CASTIGO_FOLDER = os.getenv("BENCH_SC_CASTIGO_FOLDER", "").strip()


def resolver_carpeta_extraida() -> Path:
    rutas = {
        "BENCH_TEMP_FOLDER": BENCH_TEMP_FOLDER,
        "BENCH_STC_FOLDER": BENCH_STC_FOLDER,
        "BENCH_SC_CASTIGO_FOLDER": BENCH_SC_CASTIGO_FOLDER,
    }

    faltantes = [nombre for nombre, valor in rutas.items() if not valor]
    if faltantes:
        raise RuntimeError(
            "Faltan rutas BENCH en el .env: " + ", ".join(faltantes)
        )

    carpetas = {nombre: Path(valor) for nombre, valor in rutas.items()}
    referencia = carpetas["BENCH_TEMP_FOLDER"]

    if any(carpeta != referencia for carpeta in carpetas.values()):
        detalle = "\n".join(
            f"{nombre}={carpeta}" for nombre, carpeta in carpetas.items()
        )
        raise RuntimeError(
            "Las carpetas BENCH del .env no coinciden:\n" + detalle
        )

    return referencia


# Nombres de archivo en el visor: mismos patrones glob que usan los ETL.
BENCH_TEMP_PATTERN = os.getenv("BENCH_TEMP_PATTERN", "").strip()
BENCH_STC_PATTERN = os.getenv("BENCH_STC_PATTERN", "").strip()
BENCH_SC_CASTIGO_PATTERN = os.getenv("BENCH_SC_CASTIGO_PATTERN", "").strip()


def texto_desde_patron(nombre_variable: str, patron: str) -> str:
    # El patron del .env es un glob (ej. *NOMBRE*.xlsx); en el visor
    # se busca la fila por su fragmento fijo mas largo.
    fragmentos = [
        fragmento.strip()
        for fragmento in re.split(r"[*?]", patron)
        if fragmento.strip()
    ]

    if not fragmentos:
        raise RuntimeError(
            f"Falta el patron de archivo en el .env: {nombre_variable}"
        )

    return max(fragmentos, key=len)


CARPETA_EXTRAIDA = resolver_carpeta_extraida()
CARPETA_BASE = CARPETA_EXTRAIDA.parent
CARPETA_ZIP = CARPETA_BASE / "zip"
ARCHIVO_LOG = CARPETA_BASE / "descargas.log"


def registrar_descarga(nombre_logico: str, nombre_archivo: str) -> None:
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    CARPETA_BASE.mkdir(parents=True, exist_ok=True)

    with ARCHIVO_LOG.open("a", encoding="utf-8") as log:
        log.write(f"{fecha} | {nombre_logico} | {nombre_archivo}\n")

    print(f"LOG: {nombre_logico} | {nombre_archivo}")


# ============================================================
# CONFIGURACION DESCARGAS
# ============================================================

DESCARGAS = [
    {
        "nombre":
            "BENCH CASTIGO",

        "carpeta_visor":
            "📁 BENCH CASTIGO",

        "patron_archivo":
            texto_desde_patron(
                "BENCH_SC_CASTIGO_PATTERN",
                BENCH_SC_CASTIGO_PATTERN,
            ),
    },

    {
        "nombre":
            "BENCH MORA TARDIA",

        "carpeta_visor":
            "📁 BENCH MORA TARDIA",

        "patron_archivo":
            texto_desde_patron(
                "BENCH_STC_PATTERN",
                BENCH_STC_PATTERN,
            ),
    },

    {
        "nombre":
            "BENCH MORA TEMPRANA - TELEFONIA",

        "carpeta_visor":
            "📁 BENCH MORA TEMPRANA",

        "patron_archivo":
            texto_desde_patron(
                "BENCH_TEMP_PATTERN",
                BENCH_TEMP_PATTERN,
            ),
    },

    # Asignacion de apertura mensual: YYYYMM - ASIGNACION_APERTURA - PHOENIX[ (TELEFONIA)].XLSX
    # El ".XLSX" evita que el patron de terreno tome el archivo de telefonia.
    {
        "nombre":
            "ASIGNACION APERTURA",

        "carpeta_visor":
            "📁 ASIGNACIÓN APERTURA",

        "patron_archivo":
            "ASIGNACION_APERTURA - PHOENIX.XLSX",
    },

    {
        "nombre":
            "ASIGNACION APERTURA - TELEFONIA",

        "carpeta_visor":
            "📁 ASIGNACIÓN APERTURA",

        "patron_archivo":
            "ASIGNACION_APERTURA - PHOENIX (TELEFONIA).XLSX",
    },
]

# Se descarga con el usuario judicial (USUARIO_JUD / CLAVE_JUD).
# Archivo: YYYYMMDD - BENCH BENCH JUDICIAL - P&S.xlsx; se toma el de carga mas reciente.
DESCARGAS_JUDICIAL = [
    {
        "nombre":
            "BENCH JUDICIAL",

        "carpeta_visor":
            "📁 BENCH JUDICIAL",

        "patron_archivo":
            "BENCH BENCH JUDICIAL - P&S",
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


def faltantes_judicial() -> list[str]:

    variables = {
        "USUARIO_JUD": USUARIO_JUD,
        "CLAVE_JUD": CLAVE_JUD,
        "VISOR_MAILBOX_JUD": VISOR_MAILBOX_JUD,
    }

    return [
        nombre
        for nombre, valor in variables.items()
        if not valor
    ]


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
    buzon: str | None = None,
    codigos_excluidos: set[str] | None = None,
) -> str:

    token = obtener_token_graph()

    codigos_excluidos = codigos_excluidos or set()

    mailbox = quote(
        buzon or VISOR_MAILBOX,
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

            if codigo and codigo not in codigos_excluidos:
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
# LIMPIAR EXTRAIDO
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


# ============================================================
# LIMPIAR ZIP
# ============================================================

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
                f"No se pudo eliminar "
                f"{archivo.name}: {e}"
            )

    print(
        f"Carpeta ZIP limpia: "
        f"{CARPETA_ZIP}"
    )


# ============================================================
# BUSCAR PRIMERA FILA COINCIDENTE
# ============================================================

def buscar_primera_fila(
    frame,
    patron_archivo: str,
):

    filas = (
        frame
        .locator("tr")
        .filter(
            has_text=patron_archivo
        )
    )

    fila = (
        filas.first
    )

    try:

        fila.wait_for(
            state="visible",
            timeout=10000,
        )

    except Exception as e:

        raise FileNotFoundError(
            f"No se encontró "
            f"'{patron_archivo}'."
        ) from e

    return fila


# ============================================================
# BUSCAR FILA CON LA CARGA MAS RECIENTE
# ============================================================

# Columna FECHA DE MODIFICACIÓN del visor: dd-mm-yyyy hh:mm
REGEX_FECHA_CARGA = re.compile(
    r"\b(\d{2})-(\d{2})-(\d{4})\s+(\d{1,2}):(\d{2})\b"
)

# Fecha YYYYMMDD al inicio del nombre del archivo.
REGEX_FECHA_NOMBRE = re.compile(
    r"(?<!\d)(\d{8})(?!\d)"
)


def fecha_carga_fila(
    texto_fila: str
) -> datetime | None:

    fechas = REGEX_FECHA_CARGA.findall(
        texto_fila
    )

    # Una fila de archivo tiene exactamente una fecha de carga.
    if len(fechas) != 1:
        return None

    dia, mes, anio, hora, minuto = map(int, fechas[0])

    try:
        return datetime(anio, mes, dia, hora, minuto)
    except ValueError:
        return None


def buscar_fila_ultima_carga(
    page,
    frame,
    patron_archivo: str,
):

    # Espera a que exista al menos una fila coincidente.
    buscar_primera_fila(
        frame,
        patron_archivo,
    )

    filas = (
        frame
        .locator("tr")
        .filter(
            has_text=patron_archivo
        )
    )

    # La carpeta puede seguir cargando filas: se espera
    # a que el listado deje de cambiar antes de comparar.
    textos = filas.all_inner_texts()

    for _ in range(20):

        page.wait_for_timeout(500)

        textos_nuevos = filas.all_inner_texts()

        if textos_nuevos == textos:
            break

        textos = textos_nuevos

    # Si suben el mismo periodo mas de una vez, manda la ultima carga;
    # a igual fecha de carga, la fecha mas alta en el nombre.
    mejor_indice = None
    mejor_clave = None

    for indice, texto in enumerate(textos):

        fecha_carga = fecha_carga_fila(texto)

        if fecha_carga is None:
            continue

        match_nombre = REGEX_FECHA_NOMBRE.search(texto)

        clave = (
            fecha_carga,
            match_nombre.group(1) if match_nombre else "",
            indice,
        )

        if mejor_clave is None or clave > mejor_clave:
            mejor_clave = clave
            mejor_indice = indice

    if mejor_indice is None:
        raise FileNotFoundError(
            f"No se encontró '{patron_archivo}' "
            "con fecha de modificación en el visor."
        )

    print(
        f"Coincidencias: {len(textos)} | "
        f"Última carga: {mejor_clave[0]:%d-%m-%Y %H:%M}"
    )

    return filas.nth(mejor_indice)


# ============================================================
# GUARDAR DESCARGA
# ============================================================

def guardar_download(
    download,
    nombre_logico: str,
) -> Path:

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

    if (
        ruta_zip.stat().st_size
        == 0
    ):

        raise RuntimeError(
            f"ZIP vacío para "
            f"{nombre_logico}."
        )

    print(
        f"ZIP guardado: "
        f"{ruta_zip}"
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
    abrir_carpeta: bool = True,
) -> tuple[Path, datetime]:

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

    # ========================================================
    # ABRIR CARPETA
    # ========================================================

    # Si la descarga anterior fue de esta misma carpeta ya esta
    # abierta: reabrirla recarga la tabla mientras se elige la fila.
    if abrir_carpeta:

        carpeta = (
            frame
            .get_by_role(
                "link",
                name=carpeta_visor,
            )
        )

        carpeta.wait_for(
            state="visible",
            timeout=10000,
        )

        carpeta.click()

    # ========================================================
    # ESPERAR TABLA
    # ========================================================

    frame.locator(
        "tr"
    ).first.wait_for(
        state="visible",
        timeout=10000,
    )

    print(
        f"Carpeta abierta: "
        f"{nombre}"
    )

    # ========================================================
    # TOMAR EL ARCHIVO CON LA CARGA MAS RECIENTE
    # ========================================================

    # No depende del orden de la tabla: compara la
    # FECHA DE MODIFICACIÓN de todas las coincidencias.
    fila = buscar_fila_ultima_carga(
        page,
        frame,
        patron_archivo,
    )

    texto_archivo = (
        fila
        .inner_text()
        .strip()
    )

    print()
    print(
        "SE DESCARGARA:"
    )

    print(
        texto_archivo
    )

    # Fecha en que el archivo fue cargado al visor.
    fecha_visor = fecha_carga_fila(
        texto_archivo
    )

    # ========================================================
    # DESMARCAR CUALQUIER CHECKBOX ANTERIOR
    # ========================================================

    marcados = (
        frame
        .locator(
            'input[type="checkbox"]:checked'
        )
    )

    while (
        marcados.count()
        > 0
    ):

        try:

            marcados.first.uncheck()

        except Exception:

            break

    # ========================================================
    # MARCAR CHECKBOX DE LA FILA
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
        "Checkbox seleccionado."
    )

    print(
        "Fila seleccionada:"
    )

    print(
        fila
        .inner_text()
        .strip()
    )

    # ========================================================
    # BOTON DESCARGA
    # ========================================================

    boton_descarga = (
        frame
        .get_by_role(
            "button",
            name="Descargar Archivos",
        )
    )

    boton_descarga.wait_for(
        state="visible",
        timeout=10000,
    )

    print(
        f"Descargando "
        f"{nombre}..."
    )

    # ========================================================
    # DESCARGAR
    # ========================================================

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

    ruta_zip = guardar_download(
        download,
        nombre,
    )

    return ruta_zip, fecha_visor


# ============================================================
# EXTRAER Y BORRAR ZIP
# ============================================================

def extraer_y_eliminar_zip(
    ruta_zip: Path,
    nombre_logico: str,
    fecha_visor: datetime,
) -> list[Path]:

    print()
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

                # Los ETL leen esta fecha para detectar archivos
                # resubidos al visor con el mismo nombre.
                marca = fecha_visor.timestamp()

                os.utime(
                    archivo,
                    (marca, marca),
                )

                archivos_extraidos.append(
                    archivo
                )

                registrar_descarga(
                    nombre_logico,
                    archivo.name,
                )

        # Borrar ZIP solo después
        # de extracción exitosa
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

        print(
            "El ZIP se conserva "
            "para revisión."
        )

        raise


# ============================================================
# LOGIN + OTP
# ============================================================

def autenticar_visor(
    page,
    usuario: str | None = None,
    clave: str | None = None,
    buzon: str | None = None,
    codigos_excluidos: set[str] | None = None,
) -> str:

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
        usuario or USUARIO
    )

    # ========================================================
    # CLAVE
    # ========================================================

    campo_clave = page.get_by_role(
        "textbox",
        name="Clave",
    )

    campo_clave.fill(
        clave or CLAVE
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
        buzon=buzon,
        codigos_excluidos=codigos_excluidos,
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

    return codigo


# ============================================================
# EXPLORADOR
# ============================================================

def abrir_explorador(
    page
):

    print()
    print(
        "Abriendo explorador..."
    )

    link_explorador = (
        page
        .get_by_role(
            "link",
            name=" explorador archivos",
        )
    )

    link_explorador.click()

    iframe = (
        page
        .locator(
            'iframe[name="myMainFrame"]'
        )
    )

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
            "No fue posible acceder "
            "al iframe myMainFrame."
        )

    frame.locator(
        "body"
    ).wait_for(
        state="visible",
        timeout=10000,
    )

    print(
        "Explorador abierto."
    )

    return frame


# ============================================================
# SESION: LOGIN + DESCARGAS
# ============================================================

def descargar_con_sesion(
    browser,
    descargas: list[dict],
    usuario: str | None = None,
    clave: str | None = None,
    buzon: str | None = None,
    codigos_excluidos: set[str] | None = None,
) -> tuple[list[tuple[Path, str, datetime]], str]:

    context = (
        browser
        .new_context(
            accept_downloads=True
        )
    )

    try:

        page = (
            context
            .new_page()
        )

        codigo = autenticar_visor(
            page,
            usuario=usuario,
            clave=clave,
            buzon=buzon,
            codigos_excluidos=codigos_excluidos,
        )

        frame = abrir_explorador(
            page
        )

        zips_descargados = []
        carpeta_abierta = None

        for (
            indice,
            configuracion
        ) in enumerate(
            descargas,
            start=1,
        ):

            print()
            print(
                f"DESCARGA "
                f"{indice}/"
                f"{len(descargas)}"
            )

            ruta_zip, fecha_visor = (
                descargar_desde_carpeta(
                    page,
                    frame,
                    configuracion,
                    abrir_carpeta=(
                        configuracion["carpeta_visor"]
                        != carpeta_abierta
                    ),
                )
            )

            carpeta_abierta = configuracion["carpeta_visor"]

            zips_descargados.append(
                (ruta_zip, configuracion["nombre"], fecha_visor)
            )

        return zips_descargados, codigo

    finally:

        try:

            context.close()

        except Exception:

            pass


# ============================================================
# MAIN
# ============================================================

def run(
    playwright: Playwright,
    solo_judicial: bool = False,
) -> None:

    if not solo_judicial:
        validar_configuracion()

    variables_judicial_faltantes = faltantes_judicial()

    if solo_judicial and variables_judicial_faltantes:
        raise RuntimeError(
            "Faltan variables en .env: "
            + ", ".join(variables_judicial_faltantes)
        )

    # ========================================================
    # CARPETAS
    # ========================================================

    CARPETA_ZIP.mkdir(
        parents=True,
        exist_ok=True,
    )

    CARPETA_EXTRAIDA.mkdir(
        parents=True,
        exist_ok=True,
    )

    if solo_judicial:

        # Solo se reemplaza el bench judicial; los demas archivos se conservan.
        for archivo in CARPETA_EXTRAIDA.glob(
            "*BENCH JUDICIAL*"
        ):
            archivo.unlink()

    else:

        # Limpiar una sola vez al inicio
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

    try:

        zips_descargados = []
        codigos_usados: set[str] = set()

        # ====================================================
        # USUARIO PRINCIPAL
        # ====================================================

        if not solo_judicial:

            zips, codigo = descargar_con_sesion(
                browser,
                DESCARGAS,
            )

            zips_descargados.extend(zips)
            codigos_usados.add(codigo)

        # ====================================================
        # USUARIO JUDICIAL
        # ====================================================

        if variables_judicial_faltantes:

            print()
            print(
                "ADVERTENCIA: se omite BENCH JUDICIAL. "
                "Faltan variables en .env: "
                + ", ".join(variables_judicial_faltantes)
            )

        else:

            print()
            print("=" * 70)
            print("SESION JUDICIAL")
            print("=" * 70)

            zips, codigo = descargar_con_sesion(
                browser,
                DESCARGAS_JUDICIAL,
                usuario=USUARIO_JUD,
                clave=CLAVE_JUD,
                buzon=VISOR_MAILBOX_JUD,
                codigos_excluidos=codigos_usados,
            )

            zips_descargados.extend(zips)
            codigos_usados.add(codigo)

        # ====================================================
        # EXTRAER
        # ====================================================

        print()
        print("=" * 70)
        print("EXTRAYENDO ARCHIVOS")
        print("=" * 70)

        archivos_finales = []

        for ruta_zip, nombre_logico, fecha_visor in (
            zips_descargados
        ):

            extraidos = (
                extraer_y_eliminar_zip(
                    ruta_zip,
                    nombre_logico,
                    fecha_visor,
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
                f"OK: "
                f"{archivo.name}"
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

            browser.close()

        except Exception:

            pass


# ============================================================
# EJECUCION
# ============================================================

if __name__ == "__main__":

    import sys

    with sync_playwright() as playwright:

        run(
            playwright,
            solo_judicial="--solo-judicial" in sys.argv,
        )
