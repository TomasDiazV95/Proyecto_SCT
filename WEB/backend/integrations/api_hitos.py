"""Cliente de la API BI de hitos judiciales (documentacion API.pdf).

Login con un usuario ADMINISTRADOR (API_BI_USER / API_BI_PASSWORD en el .env); el token dura una hora
y se renueva solo. Cada consulta devuelve los hitos del estudio del usuario, filtrables por cliente y mes.
"""
from __future__ import annotations

import os
import threading
import time

import requests

from database import load_env_files


URL_DEFECTO = "https://web-produccion-593970327833.southamerica-west1.run.app/api"
TIMEOUT = 120
_MARGEN_TOKEN = 120  # segundos antes de que venza se pide uno nuevo

_token: tuple[str, float] | None = None  # (access_token, vence_en monotonic)
_token_lock = threading.Lock()


def _url() -> str:
    return (os.getenv("API_BI_URL") or URL_DEFECTO).strip().rstrip("/")


def configurada() -> bool:
    load_env_files()  # el .env se carga recien al conectar a la base; aca puede no estar cargado aun
    return bool(os.getenv("API_BI_USER", "").strip() and os.getenv("API_BI_PASSWORD", "").strip())


def _login() -> str:
    global _token
    respuesta = requests.post(
        f"{_url()}/login",
        json={"username": os.getenv("API_BI_USER", "").strip(), "password": os.getenv("API_BI_PASSWORD", "")},
        timeout=TIMEOUT,
    )
    if respuesta.status_code != 200:
        raise RuntimeError(f"API de hitos: login rechazado ({respuesta.status_code} {_detalle(respuesta)})")
    cuerpo = respuesta.json()
    duracion = float(cuerpo.get("expires_in") or 3600)
    _token = (cuerpo["access_token"], time.monotonic() + duracion - _MARGEN_TOKEN)
    return _token[0]


def _access_token(renovar: bool = False) -> str:
    with _token_lock:
        if not renovar and _token and time.monotonic() < _token[1]:
            return _token[0]
        return _login()


def _detalle(respuesta: requests.Response) -> str:
    try:
        return str(respuesta.json().get("detail") or "")
    except ValueError:
        return respuesta.text[:200]


def hitos(endpoint: str, payload: dict) -> list[dict]:
    """POST /bi/<endpoint>. Si el token vencio (401) se vuelve a hacer login una vez."""
    if not configurada():
        raise RuntimeError("Faltan API_BI_USER / API_BI_PASSWORD en el .env")
    for intento in range(2):
        respuesta = requests.post(
            f"{_url()}/bi/{endpoint}",
            json=payload,
            headers={"Authorization": f"Bearer {_access_token(renovar=intento > 0)}"},
            timeout=TIMEOUT,
        )
        if respuesta.status_code == 401 and intento == 0:
            continue
        if respuesta.status_code != 200:
            raise RuntimeError(f"API de hitos /bi/{endpoint}: {respuesta.status_code} {_detalle(respuesta)}")
        return respuesta.json()
    raise RuntimeError(f"API de hitos /bi/{endpoint}: token rechazado")
