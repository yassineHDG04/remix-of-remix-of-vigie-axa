from fastapi import APIRouter, Depends, HTTPException

from ..engine import apply_call_result
from ..repo import get_repo
from ..schemas import CallDetailOut, CallOut, CallResultIn, TranscriptTurnOut
from ..security import require_api_key

router = APIRouter(prefix="/api", tags=["appels"], dependencies=[Depends(require_api_key)])


def _call_out(c) -> CallOut:
    return CallOut(
        id=c.id, dossier_id=c.dossier_id, stage=c.stage, attempt_no=c.attempt_no,
        started_at=c.started_at, ended_at=c.ended_at, duration_sec=c.duration_sec,
        status=c.status, outcome=c.outcome, delay_reason=c.delay_reason,
        delay_category=c.delay_category, voice_engine_used=c.voice_engine_used,
        models_used=c.models_used or {}, estimated_cost_usd=c.estimated_cost_usd or 0.0,
        call_channel_used=c.call_channel_used, fallback_reason=c.fallback_reason,
        provider_connected_at=c.provider_connected_at,
        estimated_transport_cost_usd=c.estimated_transport_cost_usd or 0.0,
    )


@router.get("/dossiers/{dossier_id}/calls", response_model=list[CallOut],
            summary="Historique des appels d'un dossier")
def calls_of_dossier(dossier_id: str):
    repo = get_repo()
    if not repo.get_dossier(dossier_id):
        raise HTTPException(404, "Dossier introuvable")
    return [_call_out(c) for c in repo.list_calls(dossier_id)]


@router.get("/calls/{call_id}", response_model=CallDetailOut,
            summary="Détail d'un appel (cause + transcription)")
def call_detail(call_id: str):
    repo = get_repo()
    c = repo.get_call(call_id)
    if not c:
        raise HTTPException(404, "Appel introuvable")
    turns = [TranscriptTurnOut(turn_no=t.turn_no, speaker=t.speaker, text=t.text, ts=t.ts)
             for t in repo.get_transcript(call_id)]
    base = _call_out(c)
    return CallDetailOut(**base.model_dump(), transcript=turns)


@router.post("/webhooks/calls/{call_id}/result", response_model=CallDetailOut,
             summary="Webhook — résultat d'appel (provider réel)")
def call_result_webhook(call_id: str, body: CallResultIn):
    repo = get_repo()
    c = repo.get_call(call_id)
    if not c:
        raise HTTPException(404, "Appel introuvable")
    if c.status != "en_cours":
        raise HTTPException(409, f"Appel déjà clos (statut={c.status})")
    d = repo.get_dossier(c.dossier_id)
    apply_call_result(c, d, status=body.status, duration_sec=body.duration_sec,
                      delay_reason=body.delay_reason, delay_category=body.delay_category,
                      transcript=body.transcript,
                      voice_engine_used=body.voice_engine_used,
                      models_used=body.models_used,
                      estimated_cost_usd=body.estimated_cost_usd,
                      call_channel_used=body.call_channel_used,
                      fallback_reason=body.fallback_reason,
                      estimated_transport_cost_usd=body.estimated_transport_cost_usd)
    c2 = repo.get_call(call_id)
    turns = [TranscriptTurnOut(turn_no=t.turn_no, speaker=t.speaker, text=t.text, ts=t.ts)
             for t in repo.get_transcript(call_id)]
    return CallDetailOut(**_call_out(c2).model_dump(), transcript=turns)
