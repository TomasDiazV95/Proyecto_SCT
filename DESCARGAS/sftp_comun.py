"""Ayudas compartidas por las descargas SFTP (descarga_itau_vencida.py y descarga_bit_contencion.py)."""
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import paramiko
from dotenv import load_dotenv


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
