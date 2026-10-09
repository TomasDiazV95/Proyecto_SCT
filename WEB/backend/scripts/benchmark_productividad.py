"""Mide cuanto demora cada productividad (filtros y vistas) contra la base, solo lectura.

Uso (desde WEB/backend):
    python scripts/benchmark_productividad.py                  # todas, dos pasadas por vista
    python scripts/benchmark_productividad.py gm sth           # solo algunas
    python scripts/benchmark_productividad.py --pasadas 1 --dump salida/   # guarda el JSON de cada vista

Con --dump se puede comparar el resultado de dos versiones del codigo (diff de las carpetas).
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import database  # noqa: E402
from precalentar import MODULOS  # noqa: E402


_conexiones = 0
_get_connection = database.get_connection


def _contar_conexion():
    global _conexiones
    _conexiones += 1
    return _get_connection()


database.get_connection = _contar_conexion


def medir(etiqueta: str, fn):
    global _conexiones
    _conexiones = 0
    inicio = time.perf_counter()
    try:
        resultado, error = fn(), ""
    except Exception as exc:  # la medicion sigue con la vista siguiente
        resultado, error = None, f"  ERROR {type(exc).__name__}: {str(exc)[:160]}"
    segundos = time.perf_counter() - inicio
    print(f"  {etiqueta:44} {segundos:8.2f}s  consultas={_conexiones:2}{error}", flush=True)
    return resultado, segundos


def guardar(carpeta: Path | None, nombre: str, resultado) -> None:
    if carpeta is None or resultado is None:
        return
    carpeta.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(resultado, default=str, sort_keys=True, ensure_ascii=False, indent=1)
    (carpeta / f"{nombre}.json").write_text(texto, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("modulos", nargs="*", help="servicios a medir (por defecto todos)")
    parser.add_argument("--pasadas", type=int, default=2, help="veces que se pide cada vista")
    parser.add_argument("--dump", type=Path, default=None, help="carpeta donde guardar el JSON de cada vista")
    args = parser.parse_args()

    totales: dict[str, float] = {}
    for nombre, fn_filtros, clave_fecha, vistas in MODULOS:
        if args.modulos and nombre not in args.modulos:
            continue
        print(f"\n[{nombre}]", flush=True)
        servicio = importlib.import_module(f"services.{nombre}_service")
        filtros_fn = getattr(servicio, fn_filtros)

        filtros, total = medir("filtros()", lambda: filtros_fn(None))
        fechas = (filtros or {}).get("periodos") or (filtros or {}).get("fechas_carga") or []
        if not fechas:
            print("  sin fechas disponibles")
            continue
        fecha = fechas[0]
        print(f"  -> {clave_fecha} = {fecha!r}")
        guardar(args.dump, f"{nombre}__filtros", filtros)

        con_fecha, segundos = medir("filtros(fecha)", lambda: filtros_fn(fecha))
        total += segundos
        guardar(args.dump, f"{nombre}__filtros_fecha", con_fecha)
        ejecutivos = (con_fecha or {}).get("ejecutivos") or []

        for vista in vistas:
            vista_fn = getattr(servicio, vista)
            for pasada in range(1, args.pasadas + 1):
                resultado, segundos = medir(f"{vista} ({pasada}a)", lambda: vista_fn({clave_fecha: fecha}))
                if pasada == 1:
                    total += segundos
                    guardar(args.dump, f"{nombre}__{vista}", resultado)
            if ejecutivos and vista != "get_metas":
                filtro = {clave_fecha: fecha, "ejecutivo": ejecutivos[0]}
                resultado, _ = medir(f"{vista} (un ejecutivo)", lambda: vista_fn(filtro))
                guardar(args.dump, f"{nombre}__{vista}__ejecutivo", resultado)
        totales[nombre] = total

    print("\n=== Suma de la primera carga (filtros + filtros(fecha) + vistas) ===")
    for nombre, total in totales.items():
        print(f"  {nombre:14} {total:8.2f}s")


if __name__ == "__main__":
    main()
