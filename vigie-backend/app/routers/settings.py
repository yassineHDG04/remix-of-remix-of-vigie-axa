from fastapi import APIRouter, Depends

from ..repo import get_repo
from ..schemas import SettingsIO
from ..security import require_api_key

router = APIRouter(
    prefix="/api/settings",
    tags=["paramètres"],
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=SettingsIO, summary="Lire les paramètres")
def read_settings():
    return get_repo().get_settings()


@router.put("", response_model=SettingsIO, summary="Mettre à jour les paramètres (dashboard)")
def update_settings(body: SettingsIO):
    return get_repo().update_settings(body.model_dump())
