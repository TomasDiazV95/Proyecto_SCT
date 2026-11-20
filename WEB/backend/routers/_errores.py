import logging

from fastapi import HTTPException


logger = logging.getLogger("uvicorn.error")


def error_500(exc: Exception) -> HTTPException:
    """El 500 de siempre (detail = mensaje de la excepcion), pero dejando la traza en el log del servidor.

    Llamar dentro del bloque except: `raise error_500(exc) from exc`."""
    logger.exception("Error no controlado: %s", exc)
    return HTTPException(status_code=500, detail=str(exc))
