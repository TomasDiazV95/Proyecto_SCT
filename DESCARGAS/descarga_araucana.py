import os
from ftplib import FTP, error_perm
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASSWORD = os.getenv("FTP_PASSWORD")

if not FTP_HOST or not FTP_USER or not FTP_PASSWORD:
    raise Exception("Faltan credenciales FTP en el .env")

MESES = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre",
}

fecha_referencia = datetime.now() - timedelta(days=1)
anio = fecha_referencia.year
mes_num = fecha_referencia.month
mes_texto = MESES[mes_num]
mes_num_str = str(mes_num).zfill(2)

carpeta_mes = f"{mes_texto} {anio}"

nombre_asignacion = f"Asignacion_PHOENIX_financiera_{mes_texto}{anio}.csv"
nombre_recuperacion = f"RECUPERACION_Phoenix_{anio}{mes_num_str}.csv"

ruta_remota_asignacion = f"/PHOENIX/{carpeta_mes}/{nombre_asignacion}"
ruta_remota_recuperacion = f"/PHOENIX/{carpeta_mes}/Pagos/{nombre_recuperacion}"

carpeta_local = Path(r"C:\Users\Analista de Datos\Desktop\ARAUCANA")
carpeta_local.mkdir(parents=True, exist_ok=True)

ruta_local_asignacion = carpeta_local / "ASIGNACION.csv"
ruta_local_recuperacion = carpeta_local / "RECUPERACION.csv"


def descargar_archivo(ftp: FTP, ruta_remota: str, ruta_local: Path) -> None:
    if ruta_local.exists():
        try:
            ruta_local.unlink()
        except PermissionError:
            pass
    with open(ruta_local, "wb") as archivo_local:
        ftp.retrbinary(f"RETR {ruta_remota}", archivo_local.write)


def existe_archivo(ftp: FTP, ruta_remota: str) -> bool:
    try:
        ftp.size(ruta_remota)
        return True
    except error_perm:
        return False


def main():
    print(f"Carpeta mes detectada: {carpeta_mes}")
    print(f"Asignacion esperada: {nombre_asignacion}")
    print(f"Recuperacion esperada: {nombre_recuperacion}")

    with FTP(FTP_HOST) as ftp:
        ftp.login(FTP_USER, FTP_PASSWORD)

        print("Conectado al FTP")

        # Regla principal: si no está ASIGNACION, no corre nada
        if not existe_archivo(ftp, ruta_remota_asignacion):
            raise FileNotFoundError("No existe ASIGNACION del mes actual")

        print("ASIGNACION encontrada, descargando...")
        descargar_archivo(ftp, ruta_remota_asignacion, ruta_local_asignacion)
        print(f"ASIGNACION descargada en: {ruta_local_asignacion}")

        print("Descargando RECUPERACION...")
        descargar_archivo(ftp, ruta_remota_recuperacion, ruta_local_recuperacion)
        print(f"RECUPERACION descargada en: {ruta_local_recuperacion}")

    print("Proceso FTP finalizado correctamente")


if __name__ == "__main__":
    main()
