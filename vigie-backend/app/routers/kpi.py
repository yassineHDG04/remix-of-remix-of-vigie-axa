from datetime import datetime

from fastapi import APIRouter, Depends

from ..repo import get_repo
from ..schemas import KpiOut
from ..security import require_api_key

router = APIRouter(prefix="/api/kpi", tags=["kpi"], dependencies=[Depends(require_api_key)])


@router.get("", response_model=KpiOut, summary="Indicateurs pour le dashboard")
def kpi():
    repo = get_repo()
    now = datetime.utcnow()
    today = now.date()
    today_start = datetime(now.year, now.month, now.day)

    en_retard = repo.list_dossiers("en_retard")
    critiques = sum(1 for d in en_retard if (d.deadline_at - now).total_seconds() < 3600)
    handoff = sum(1 for d in en_retard if d.handoff_reason)

    valides = repo.list_dossiers("valide")
    valides_today = sum(1 for d in valides if d.validated_at and d.validated_at.date() == today)

    appels_today = repo.count_calls_since(today_start)
    pris_today = repo.count_calls_since(today_start, status="pris")
    # taux de décroché = pris / (appels terminés). Approché ici par pris/appels du jour.
    taux = round(100 * pris_today / appels_today) if appels_today else 0

    return KpiOut(en_retard=len(en_retard), critiques_1h=critiques, en_handoff_humain=handoff,
                  valides_aujourdhui=valides_today, appels_aujourdhui=appels_today,
                  taux_decroche_pct=taux)
