import zipfile
import os
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
ROOT_ENV_PATH = BASE_DIR.parent / ".env"


def cargar_env(path: Path) -> None:
    if not path.exists():
        return

    for linea in path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue

        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip())


cargar_env(ROOT_ENV_PATH)
cargar_env(ENV_PATH)

USUARIO = os.getenv("USUARIO", "")
CLAVE = os.getenv("CLAVE", "")

CARPETA_BASE = Path(r"C:\Users\Analista de Datos\Desktop\SCT BENCH")
CARPETA_ZIP = CARPETA_BASE / "zip"
CARPETA_EXTRAIDA = CARPETA_BASE / "extraido"


def buscar_archivo_bench(carpeta: Path) -> Path:
    archivos = [p for p in carpeta.iterdir() if p.is_file()]

    for archivo in archivos:
        nombre = archivo.name.upper()
        if "BENCH MORA TARDIA - PHOENIX" in nombre:
            return archivo

    raise FileNotFoundError(
        f"No encontré un archivo con 'BENCH MORA TARDIA - PHOENIX' en {carpeta}"
    )


def run(playwright: Playwright) -> None:
    if not USUARIO or not CLAVE:
        raise ValueError("Faltan USUARIO o CLAVE en el archivo .env")

    CARPETA_ZIP.mkdir(parents=True, exist_ok=True)
    CARPETA_EXTRAIDA.mkdir(parents=True, exist_ok=True)

    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()

    page.goto("https://recuperaciones.santanderconsumer.cl/")

    page.get_by_role("textbox", name="Usuario").fill(USUARIO)
    page.get_by_role("textbox", name="Clave").fill(CLAVE)
    page.get_by_role("textbox", name="Clave").press("Enter")

    page.get_by_role("link", name=" explorador archivos").wait_for()
    page.get_by_role("link", name=" explorador archivos").click()

    frame = page.locator('iframe[name="myMainFrame"]').content_frame

    frame.get_by_role("link", name="📁 BENCH MORA TARDIA").wait_for()
    frame.get_by_role("link", name="📁 BENCH MORA TARDIA").click()

    frame.get_by_role("button", name="FECHA DE MODIFICACIÓN ↓↑").click()
    frame.locator("#rptEntriesWFM_chkSelectWFM_0").check()

    with page.expect_download() as download_info:
        frame.get_by_role("button", name="Descargar Archivos").click()

    download = download_info.value

    # Guardar ZIP con su nombre real
    nombre_zip = download.suggested_filename
    if not nombre_zip.lower().endswith(".zip"):
        nombre_zip += ".zip"

    ruta_zip = CARPETA_ZIP / nombre_zip
    download.save_as(str(ruta_zip))
    print(f"ZIP descargado en: {ruta_zip}")

    # Limpiar carpeta extraída anterior
    for archivo in CARPETA_EXTRAIDA.iterdir():
        if archivo.is_file():
            archivo.unlink()

    # Descomprimir ZIP
    with zipfile.ZipFile(ruta_zip, "r") as zip_ref:
        zip_ref.extractall(CARPETA_EXTRAIDA)

    print(f"ZIP extraído en: {CARPETA_EXTRAIDA}")

    # Buscar el archivo correcto dentro del ZIP
    archivo_bench = buscar_archivo_bench(CARPETA_EXTRAIDA)

    print(f"Archivo listo para ETL: {archivo_bench}")

    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
