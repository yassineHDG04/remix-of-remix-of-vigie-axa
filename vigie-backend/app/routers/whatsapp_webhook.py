"""Webhook entrant WhatsApp — reçoit les clics de bouton (ex. "Traité").

Deux méthodes exigées par Meta sur le MÊME endpoint :
  GET  : poignée de main de vérification, faite UNE FOIS quand tu enregistres
         l'URL du webhook dans le tableau de bord Meta.
  POST : notifications réelles (ici : clic sur le bouton Quick Reply).
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from ..config import config
from ..engine import apply_call_result
from ..providers.telephony import cleanup_whatsapp_call, connect_whatsapp_call
from ..repo import get_repo
from ..security import valid_whatsapp_signature

log = logging.getLogger("vigie.whatsapp_webhook")

router = APIRouter(prefix="/api/webhooks/whatsapp", tags=["whatsapp"])


@router.get("", summary="Vérification du webhook (poignée de main Meta)")
def verify_webhook(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
):
    """Meta appelle ceci UNE FOIS, au moment où tu enregistres l'URL du webhook
    dans le tableau de bord (WhatsApp > Configuration > Webhook). Si le token
    correspond, on renvoie le "challenge" tel quel -> Meta valide l'URL."""
    verify_token = config.whatsapp_webhook_verify_token
    if (
        verify_token
        and hub_mode == "subscribe"
        and secrets.compare_digest(hub_verify_token, verify_token)
    ):
        log.info("Webhook WhatsApp vérifié avec succès par Meta.")
        return PlainTextResponse(hub_challenge)
    log.warning("Échec de vérification du webhook WhatsApp (token incorrect ou mode invalide).")
    return JSONResponse({"error": "verification échouée"}, status_code=403)


@router.post("", summary="Réception des événements WhatsApp (clic sur bouton)")
async def receive_event(request: Request):
    """Reçoit les notifications Meta. On ne traite que les clics sur le bouton
    "Traité" envoyé avec le template de hand-off (payload = "ack:{dossier_id}").
    Toute autre notification est ignorée proprement (jamais d'erreur 500 —
    Meta désactiverait le webhook après trop d'échecs)."""
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not valid_whatsapp_signature(raw_body, signature):
        log.warning("Webhook WhatsApp rejeté : signature Meta invalide ou absente.")
        return JSONResponse({"error": "signature invalide"}, status_code=401)

    try:
        body = json.loads(raw_body)
    except Exception:
        return JSONResponse({"status": "ignored"}, status_code=200)

    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    _handle_message(msg)
                for call_event in value.get("calls", []):
                    await _handle_call_event(call_event)
    except Exception:
        log.exception("Erreur en traitant un événement webhook WhatsApp (ignorée).")

    # Toujours répondre 200 rapidement, sinon Meta considère le webhook en échec.
    return JSONResponse({"status": "ok"}, status_code=200)


def _handle_message(msg: dict) -> None:
    """Traite un message entrant. On s'intéresse uniquement au clic sur le
    bouton Quick Reply du template (type="button", payload="ack:{dossier_id}")."""
    if msg.get("type") != "button":
        return
    payload = (msg.get("button") or {}).get("payload", "")
    if not payload.startswith("ack:"):
        return
    dossier_id = payload.removeprefix("ack:")
    sender = msg.get("from", "inconnu")
    repo = get_repo()
    updated = repo.acknowledge_handoff(dossier_id, by=f"WhatsApp ({sender})")
    if updated:
        log.info("Hand-off acquitté via WhatsApp pour le dossier %s (par %s).", dossier_id, sender)
    else:
        log.warning("Bouton WhatsApp cliqué pour un dossier introuvable : %s", dossier_id)


async def _handle_call_event(event: dict) -> None:
    """Traite les événements audio Meta nécessaires au connecteur LiveKit.

    Le format Meta a évolué entre les versions de Cloud API ; on accepte donc
    ``event`` ou ``status`` et on ne fait confiance qu'à la signature HMAC déjà
    vérifiée sur le corps brut.
    """
    whatsapp_call_id = str(event.get("id") or event.get("call_id") or "")
    if not whatsapp_call_id:
        return
    event_name = str(event.get("event") or event.get("status") or "").lower()
    session = event.get("session") or {}
    sdp = str(session.get("sdp") or "")
    repo = get_repo()
    call = repo.get_call_by_provider_ref(whatsapp_call_id)
    if not call:
        opaque_id = str(event.get("biz_opaque_callback_data") or "")
        call = repo.get_call(opaque_id) if opaque_id else None

    if sdp and event_name in {"connect", "connected", "accept", "accepted"}:
        # Meta commence déjà à faire sonner le téléphone : la connexion doit
        # être réalisée immédiatement pour éviter silence puis déconnexion.
        await connect_whatsapp_call(whatsapp_call_id, sdp)
        if call:
            repo.update_call(call.id, {"provider_connected_at": datetime.utcnow()})
        log.info("Appel WhatsApp connecté à LiveKit : %s", whatsapp_call_id)
        return

    terminal_events = {
        "terminate",
        "terminated",
        "failed",
        "rejected",
        "declined",
        "busy",
        "no_answer",
        "not_answered",
    }
    if event_name not in terminal_events:
        return

    try:
        await cleanup_whatsapp_call(whatsapp_call_id)
    except Exception:
        log.debug("Nettoyage WhatsApp déjà effectué pour %s", whatsapp_call_id, exc_info=True)

    # Si personne n'a jamais décroché, aucun média ne rejoint la room et le
    # worker peut ne pas avoir le temps de poster. Le webhook clôt la tentative.
    # Pour un appel connecté, le shutdown callback du worker reste l'unique
    # source du résultat conversationnel et de la transcription.
    if call and call.status == "en_cours" and call.provider_connected_at is None:
        dossier = repo.get_dossier(call.dossier_id)
        if dossier:
            reason = f"whatsapp_{event_name}" if event_name == "failed" else None
            apply_call_result(
                call,
                dossier,
                status="non_joignable",
                call_channel_used="whatsapp",
                fallback_reason=reason,
            )
            log.info(
                "Tentative WhatsApp clôturée sans réponse : %s (%s)",
                whatsapp_call_id,
                event_name,
            )
