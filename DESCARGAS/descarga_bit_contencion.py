import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

import paramiko
from dotenv import load_dotenv


REMOTE_DIR = "/Entrada/Seguimientos"
LOCAL_DIR = Path(r"C:\Users\Analista de Datos\Desktop\AUTOMATIZACION\BIT")
CONT_METADATA_NAME = "CONTENCION.meta.json"
CASTIGO_METADATA_NAME = "CASTIGO.meta.json"
CONT_LOCAL_GLOB = "Seguimiento_Metas_PHOENIX_*.xlsx"
CASTIGO_LOCAL_GLOB = "Detalle_Recuperos_Castigo_*.xlsx"


@dataclass(frozen=True)
class RemoteFileMatch:
    filename: str
    periodo: str
    variant: str
    detected_at: datetime
    mtime: datetime


def load_env_files() -> None:
    base_dir = Path(__file__).resolve().parent
    load_dotenv(base_dir.parent / ".env")
    load_dotenv(base_dir / ".env")


def _download_with_replace(sftp: paramiko.SFTPClient, remote_file: str, local_path: Path) -> None:
    with NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_file:
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


def _remove_previous_files(local_dir: Path, pattern: str, keep_name: str) -> None:
    keep_name_upper = keep_name.upper()
    for path in local_dir.glob(pattern):
        if path.name.upper() == keep_name_upper:
            continue
        if path.is_file():
            path.unlink(missing_ok=True)


def _download_original_name(
    sftp: paramiko.SFTPClient,
    remote_dir: str,
    file_name: str,
    local_dir: Path,
    cleanup_pattern: str,
) -> Path:
    local_path = local_dir / file_name
    remote_file = f"{remote_dir}/{file_name}"
    _download_with_replace(sftp, remote_file, local_path)
    _remove_previous_files(local_dir, cleanup_pattern, file_name)
    return local_path


def pick_latest_bit_file(sftp: paramiko.SFTPClient, remote_dir: str) -> tuple[str, datetime]:
    pattern = re.compile(r"^Seguimiento_Metas_PHOENIX_(\d{8})\.xlsx$")
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
            f"No se encontraron archivos con formato Seguimiento_Metas_PHOENIX_YYYYMMDD.xlsx en {remote_dir}"
        )

    return max(candidates, key=lambda item: item[1])


def pick_latest_castigo_file(sftp: paramiko.SFTPClient, remote_dir: str) -> RemoteFileMatch:
    pattern = re.compile(r"^Detalle_Recuperos_Castigo_(\d{6})(?:_(PRECIERRE|CIERRE))?\.xlsx$")
    candidates: list[RemoteFileMatch] = []

    for entry in sftp.listdir_attr(remote_dir):
        name = entry.filename
        match = pattern.match(name)
        if not match:
            continue

        raw_period = match.group(1)
        variant = match.group(2) or "base"
        periodo = f"{raw_period[:4]}-{raw_period[4:6]}"
        mtime = datetime.fromtimestamp(entry.st_mtime)
        candidates.append(
            RemoteFileMatch(
                filename=name,
                periodo=periodo,
                variant=variant,
                detected_at=datetime.strptime(raw_period, "%Y%m"),
                mtime=mtime,
            )
        )

    if not candidates:
        raise FileNotFoundError(
            f"No se encontraron archivos con formato Detalle_Recuperos_Castigo_YYYYMM[_PRECIERRE|_CIERRE].xlsx en {remote_dir}"
        )

    return max(candidates, key=lambda item: item.mtime)


def download_contencion(sftp: paramiko.SFTPClient, remote_dir: str, local_dir: Path) -> None:
    latest_name, latest_date = pick_latest_bit_file(sftp, remote_dir)
    metadata_path = local_dir / CONT_METADATA_NAME
    local_path = _download_original_name(sftp, remote_dir, latest_name, local_dir, CONT_LOCAL_GLOB)

    period = latest_date.strftime("%Y-%m")
    _write_metadata(
        metadata_path,
        {
            "original_filename": latest_name,
            "fecha_detectada": latest_date.strftime("%Y-%m-%d"),
            "periodo_detectado": period,
        },
    )

    print(f"Archivo contencion seleccionado: {latest_name}")
    print(f"Fecha contencion detectada: {latest_date.strftime('%Y-%m-%d')}")
    print(f"Periodo contencion detectado: {period}")
    print(f"Guardado en: {local_path}")
    print(f"Metadata guardada en: {metadata_path}")


def download_castigo(sftp: paramiko.SFTPClient, remote_dir: str, local_dir: Path) -> None:
    latest = pick_latest_castigo_file(sftp, remote_dir)
    metadata_path = local_dir / CASTIGO_METADATA_NAME
    local_path = _download_original_name(sftp, remote_dir, latest.filename, local_dir, CASTIGO_LOCAL_GLOB)
    _write_metadata(
        metadata_path,
        {
            "original_filename": latest.filename,
            "periodo_detectado": latest.periodo,
            "sftp_mtime": latest.mtime.isoformat(timespec="seconds"),
            "variant": latest.variant,
        },
    )

    print(f"Archivo castigo seleccionado: {latest.filename}")
    print(f"Periodo castigo detectado: {latest.periodo}")
    print(f"SFTP mtime castigo: {latest.mtime.isoformat(timespec='seconds')}")
    print(f"Variante castigo: {latest.variant}")
    print(f"Guardado en: {local_path}")
    print(f"Metadata guardada en: {metadata_path}")


def main() -> None:
    load_env_files()

    host = (os.getenv("BIT_SFTP_HOST") or os.getenv("SFTP_HOST") or "").strip()
    port = int((os.getenv("BIT_SFTP_PORT") or os.getenv("SFTP_PORT") or "22").strip() or "22")
    user = (os.getenv("BIT_SFTP_USER") or os.getenv("SFTP_USER") or "").strip()
    password = (os.getenv("BIT_SFTP_PASSWORD") or os.getenv("SFTP_PASSWORD") or "").strip()

    if not host or not user or not password:
        raise RuntimeError("Faltan variables BIT_SFTP_HOST, BIT_SFTP_USER o BIT_SFTP_PASSWORD en .env")

    local_dir = LOCAL_DIR
    local_dir.mkdir(parents=True, exist_ok=True)

    transport = paramiko.Transport((host, port))
    try:
        transport.connect(username=user, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        try:
            download_contencion(sftp, REMOTE_DIR, local_dir)
            download_castigo(sftp, REMOTE_DIR, local_dir)
        finally:
            sftp.close()
    finally:
        transport.close()


if __name__ == "__main__":
    main()
