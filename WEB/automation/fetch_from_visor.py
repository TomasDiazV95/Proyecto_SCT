import os
import re
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._\- ]", "_", name)


def _fill_first(page, selectors: list[str], value: str) -> None:
    last_error = None
    for selector in selectors:
        try:
            page.locator(selector).first.wait_for(timeout=3000)
            page.locator(selector).first.fill(value)
            return
        except Exception as exc:
            last_error = exc
            continue
    raise RuntimeError(f"No se pudo completar input con selectores: {selectors}") from last_error


def _click_first(page, selectors: list[str]) -> None:
    last_error = None
    for selector in selectors:
        try:
            page.locator(selector).first.wait_for(timeout=3000)
            page.locator(selector).first.click()
            return
        except Exception as exc:
            last_error = exc
            continue
    raise RuntimeError(f"No se pudo hacer click con selectores: {selectors}") from last_error


def _open_explorer(page) -> None:
    explorer_url = _env("VISOR_EXPLORER_URL")
    if explorer_url:
        page.goto(explorer_url, wait_until="domcontentloaded")
        return

    for label in ["Explorador archivos", "Explorador de archivos", "Archivos", "File Explorer"]:
        try:
            page.get_by_role("link", name=re.compile(label, re.IGNORECASE)).first.click(timeout=3000)
            page.wait_for_load_state("networkidle", timeout=10000)
            return
        except Exception:
            continue


def _search_in_page(page, text: str) -> None:
    search_candidates = [
        "input[placeholder*='Buscar' i]",
        "input[name*='buscar' i]",
        "input[id*='buscar' i]",
        "input[type='search']",
        "input[placeholder*='Search' i]",
    ]

    for selector in search_candidates:
        try:
            inp = page.locator(selector).first
            inp.wait_for(timeout=2000)
            inp.fill(text)
            inp.press("Enter")
            page.wait_for_timeout(800)
            return
        except Exception:
            continue


def _pick_best_filename(names: list[str], expected_name: str) -> str | None:
    if expected_name in names:
        return expected_name

    suffix = _env("BENCH_FILE_SUFFIX", " - BENCH MORA TARDIA - PHOENIX.xlsx")
    candidates = [n for n in names if n.upper().endswith(suffix.upper())]
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0]


def download_latest_bench(expected_name: str, download_dir: Path, logger) -> Path | None:
    visor_url = _env("VISOR_URL", "https://recuperaciones.santanderconsumer.cl/Login.aspx")
    user = _env("VISOR_USER")
    password = _env("VISOR_PASSWORD")

    if not user or not password:
        raise RuntimeError("Faltan VISOR_USER o VISOR_PASSWORD en .env")

    download_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=_env("VISOR_HEADLESS", "true").lower() != "false")
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        logger.info("Abriendo visor web...")
        page.goto(visor_url, wait_until="domcontentloaded")

        logger.info("Iniciando sesion en visor...")
        _fill_first(
            page,
            [
                "input[name*='rut' i]",
                "input[id*='rut' i]",
                "input[name*='user' i]",
                "input[id*='user' i]",
                "input[type='text']",
            ],
            user,
        )
        _fill_first(
            page,
            [
                "input[type='password']",
                "input[name*='pass' i]",
                "input[id*='pass' i]",
            ],
            password,
        )
        _click_first(
            page,
            [
                "button:has-text('Ingresar')",
                "input[type='submit']",
                "button[type='submit']",
                "button:has-text('Login')",
            ],
        )
        page.wait_for_load_state("networkidle", timeout=20000)

        logger.info("Abriendo explorador de archivos...")
        _open_explorer(page)

        search_text = _env("BENCH_SEARCH_TEXT", "BENCH MORA TARDIA")
        _search_in_page(page, search_text)

        logger.info("Buscando archivo bench disponible...")
        links = page.locator("a")
        count = links.count()
        names: list[str] = []
        for i in range(count):
            text = (links.nth(i).inner_text() or "").strip()
            if text and "BENCH MORA TARDIA" in text.upper() and text.upper().endswith(".XLSX"):
                names.append(text)

        target_name = _pick_best_filename(names, expected_name)
        if not target_name:
            logger.info("No se encontro archivo bench nuevo en el visor.")
            browser.close()
            return None

        logger.info(f"Intentando descargar: {target_name}")
        target_link = page.locator(f"a:has-text('{target_name}')").first
        try:
            with page.expect_download(timeout=30000) as download_info:
                target_link.click()
            download = download_info.value
            save_path = download_dir / _safe_name(target_name)
            download.save_as(str(save_path))
            logger.info(f"Archivo descargado en: {save_path}")
            browser.close()
            return save_path
        except PlaywrightTimeoutError:
            # fallback: si no detecta descarga, intenta leer href y bajar con request autenticado
            href = target_link.get_attribute("href")
            if not href:
                browser.close()
                raise RuntimeError("No se pudo descargar el archivo: no hubo download ni href")

            logger.info("Descarga directa no detectada, usando fallback por request autenticado...")
            response = context.request.get(href)
            if not response.ok:
                browser.close()
                raise RuntimeError(f"Fallback de descarga fallo: HTTP {response.status}")

            save_path = download_dir / _safe_name(target_name)
            save_path.write_bytes(response.body())
            logger.info(f"Archivo descargado por fallback en: {save_path}")
            browser.close()
            return save_path
