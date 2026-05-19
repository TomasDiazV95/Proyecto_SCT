import os
import re
import json
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

import paramiko
from dotenv import load_dotenv


def load_env_files() -> None:
    base_dir = Path(__file__).resolve().parent
    load_dotenv(base_dir.parent / ".env")
    load_dotenv(base_dir / ".env")


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


def main() -> None:
    load_env_files()

    host = (os.getenv("BIT_SFTP_HOST") or os.getenv("SFTP_HOST") or "").strip()
    port = int((os.getenv("BIT_SFTP_PORT") or os.getenv("SFTP_PORT") or "22").strip() or "22")
    user = (os.getenv("BIT_SFTP_USER") or os.getenv("SFTP_USER") or "").strip()
    password = (os.getenv("BIT_SFTP_PASSWORD") or os.getenv("SFTP_PASSWORD") or "").strip()

    if not host or not user or not password:
        raise RuntimeError("Faltan variables BIT_SFTP_HOST, BIT_SFTP_USER o BIT_SFTP_PASSWORD en .env")

    remote_dir = "/Entrada/Seguimientos"
    local_path = Path(r"C:\Users\Analista de Datos\Desktop\AUTOMATIZACION\BIT\CONTENCION.xlsx")
    local_path.parent.mkdir(parents=True, exist_ok=True)

    transport = paramiko.Transport((host, port))
    try:
        transport.connect(username=user, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        try:
            latest_name, latest_date = pick_latest_bit_file(sftp, remote_dir)
            remote_file = f"{remote_dir}/{latest_name}"

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

            period = latest_date.strftime("%Y-%m")
            metadata_path = local_path.parent / "CONTENCION.meta.json"
            metadata_path.write_text(
                json.dumps(
                    {
                        "original_filename": latest_name,
                        "fecha_detectada": latest_date.strftime("%Y-%m-%d"),
                        "periodo_detectado": period,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            print(f"Archivo seleccionado: {latest_name}")
            print(f"Fecha detectada: {latest_date.strftime('%Y-%m-%d')}")
            print(f"Periodo detectado: {period}")
            print(f"Guardado en: {local_path}")
            print(f"Metadata guardada en: {metadata_path}")
        finally:
            sftp.close()
    finally:
        transport.close()


if __name__ == "__main__":
    main()
