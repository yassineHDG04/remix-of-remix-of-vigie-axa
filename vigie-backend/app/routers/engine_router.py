from fastapi import APIRouter, Depends, Header, HTTPException

from ..config import config
from ..engine import tick
from ..security import require_api_key

router = APIRouter(
    prefix="/api/engine",
    tags=["moteur"],
    dependencies=[Depends(require_api_key)],
)


@router.post("/tick", summary="Forcer une évaluation immédiate (ou tick par cron externe)")
def force_tick(x_tick_token: str | None = Header(default=None)):
    """Évalue tous les dossiers et déclenche les actions dues.

    - En hébergement classique (Render/VPS) : le moteur tourne déjà en tâche de fond,
      cet endpoint sert surtout aux tests.
    - En serverless (Vercel) : ENGINE_AUTOSTART=false et un CRON EXTERNE appelle
      cet endpoint périodiquement -> c'est lui qui fait vivre le moteur.

    Si ENGINE_TICK_TOKEN est défini, l'en-tête X-Tick-Token doit correspondre.
    """
    if config.engine_tick_token and x_tick_token != config.engine_tick_token:
        raise HTTPException(401, "Jeton de tick invalide ou manquant (en-tête X-Tick-Token).")
    return tick()
