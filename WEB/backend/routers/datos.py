from fastapi import APIRouter, Depends

import datos_version
from auth.dependencies import current_user


router = APIRouter(dependencies=[Depends(current_user)])


@router.get("/version")
def version() -> dict:
    """Version de los datos: sube cuando cambia la base. Las paginas la consultan para recargarse."""
    return {"version": datos_version.VERSION}
