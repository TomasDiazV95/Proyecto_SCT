import json
import os
import re
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

import paramiko
from dotenv import load_dotenv


DEFAULT_REMOTE_DIR = "/Home/Out"
LOCAL_DIR = Path(r"C:\Users\Analista de Datos\Desktop\AUTOMATIZACION\ITAU")
CUOTAS_METADATA_NAME = "CUOTAS.meta.json"
ASIGNACION_METADATA_NAME = "ASIGNACION.meta.json"
CUOTAS_LOCAL_GLOB = "Cuotas_PHOENIX_*.csv"
ASIGNACION_LOCAL_GLOB = "Asignacion_PHOENIX_*.csv"


def load_env_files() -> None:
    base_dir = Path(__file__).resolve().parent
    load_dotenv(base_dir.parent / ".env")
    load_dotenv(base_dir / ".env")


def _download_with_replace(sftp: paramiko.SFTPClient, remote_file: str, local_path: Path) -> None:
    with NamedTemporaryFile(delete=False, suffix=local_path.suffix) as tmp_file:
        tmp_path = Path(tmp_file.name)

    try:
        sftp.get(remote_file, str(tmp_path))
        os.replace(tmp_path, local_path)
    except PermissionError as exc:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise PermissionError(
            f"No se pudo sobrescribir {local_path}. Cierra el archivo si esta abierto y vuelve a intentar."
        ) from exc
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def _write_metadata(metadata_path: Path, payload: dict) -> None:
    metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _remove_previous_files(local_dir: Path, pattern: str, keep_name: str) -> list[Path]:
    keep_name_upper = keep_name.upper()
    skipped_files: list[Path] = []
    for path in local_dir.glob(pattern):
        if path.name.upper() == keep_name_upper:
            continue
        if path.is_file():
            try:
                path.unlink(missing_ok=True)
            except PermissionError:
                skipped_files.append(path)
    return skipped_files


def _download_original_name(
    sftp: paramiko.SFTPClient,
    remote_dir: str,
    file_name: str,
    local_dir: Path,
    cleanup_pattern: str,
) -> tuple[Path, list[Path]]:
    local_path = local_dir / file_name
    remote_file = f"{remote_dir}/{file_name}"
    _download_with_replace(sftp, remote_file, local_path)
    skipped_files = _remove_previous_files(local_dir, cleanup_pattern, file_name)
    return local_path, skipped_files


def pick_latest_file(sftp: paramiko.SFTPClient, remote_dir: str, prefix: str) -> tuple[str, datetime]:
    # Solo el .csv del dia: quedan fuera los historicos comprimidos (.csv.gz) y los error_*.
    pattern = re.compile(rf"^{re.escape(prefix)}_PHOENIX_(\d{{8}})\.csv$", re.IGNORECASE)
    candidates: list[tuple[str, datetime]] = []

    for entry in sftp.listdir_attr(remote_dir):
        name = entry.filename
        match = pattern.match(name)
        if not match:
            continue
        dt = datetime.strptime(match.group(1), "%Y%m%d")
        candidates.append((name, dt))

    if not candidates:
        raise FileNotFoundError(
            f"No se encontraron archivos con formato {prefix}_PHOENIX_YYYYMMDD.csv en {remote_dir}"
        )

    return max(candidates, key=lambda item: item[1])


def download_cuotas(sftp: paramiko.SFTPClient, remote_dir: str, local_dir: Path) -> None:
    latest_name, latest_date = pick_latest_file(sftp, remote_dir, "Cuotas")
    metadata_path = local_dir / CUOTAS_METADATA_NAME
    local_path, skipped_files = _download_original_name(sftp, remote_dir, latest_name, local_dir, CUOTAS_LOCAL_GLOB)

    period = latest_date.strftime("%Y-%m")
    _write_metadata(
        metadata_path,
        {
            "original_filename": latest_name,
            "fecha_detectada": latest_date.strftime("%Y-%m-%d"),
            "periodo_detectado": period,
        },
    )

    print(f"Archivo cuotas seleccionado: {latest_name}")
    print(f"Fecha cuotas detectada: {latest_date.strftime('%Y-%m-%d')}")
    print(f"Periodo cuotas detectado: {period}")
    print(f"Guardado en: {local_path}")
    print(f"Metadata guardada en: {metadata_path}")
    for skipped_file in skipped_files:
        print(f"Advertencia: no se pudo eliminar archivo anterior en uso: {skipped_file}")


def download_asignacion(sftp: paramiko.SFTPClient, remote_dir: str, local_dir: Path) -> None:
    latest_name, latest_date = pick_latest_file(sftp, remote_dir, "Asignacion")
    metadata_path = local_dir / ASIGNACION_METADATA_NAME
    local_path, skipped_files = _download_original_name(sftp, remote_dir, latest_name, local_dir, ASIGNACION_LOCAL_GLOB)

    period = latest_date.strftime("%Y-%m")
    _write_metadata(
        metadata_path,
        {
            "original_filename": latest_name,
            "fecha_detectada": latest_date.strftime("%Y-%m-%d"),
            "periodo_detectado": period,
        },
    )

    print(f"Archivo asignacion seleccionado: {latest_name}")
    print(f"Fecha asignacion detectada: {latest_date.strftime('%Y-%m-%d')}")
    print(f"Periodo asignacion detectado: {period}")
    print(f"Guardado en: {local_path}")
    print(f"Metadata guardada en: {metadata_path}")
    for skipped_file in skipped_files:
        print(f"Advertencia: no se pudo eliminar archivo anterior en uso: {skipped_file}")


def main() -> None:
    load_env_files()

    host = (os.getenv("ITAU_SFTP_HOST") or "").strip()
    port = int((os.getenv("ITAU_SFTP_PORT") or "22").strip() or "22")
    user = (os.getenv("ITAU_SFTP_USER") or "").strip()
    password = (os.getenv("ITAU_SFTP_PASSWORD") or "").strip()
    remote_dir = (os.getenv("ITAU_SFTP_REMOTE_DIR") or DEFAULT_REMOTE_DIR).strip().rstrip("/")

    if not host or not user or not password:
        raise RuntimeError("Faltan variables ITAU_SFTP_HOST, ITAU_SFTP_USER o ITAU_SFTP_PASSWORD en .env")

    local_dir = LOCAL_DIR
    local_dir.mkdir(parents=True, exist_ok=True)

    transport = paramiko.Transport((host, port))
    try:
        transport.connect(username=user, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        try:
            download_cuotas(sftp, remote_dir, local_dir)
            download_asignacion(sftp, remote_dir, local_dir)
        finally:
            sftp.close()
    finally:
        transport.close()


if __name__ == "__main__":
    main()
