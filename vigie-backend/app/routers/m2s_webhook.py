"""Webhook signé par lequel M2S notifie un changement de statut dossier."""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status

from ..config import config
from ..importer import import_dossiers_list
from ..providers.m2s import (
    extract_m2s_ref,
    extract_m2s_status,
    get_m2s_runtime_config,
    map_m2s_payload,
    status_contract_configured,
)
from ..repo import get_repo
from ..security import valid_m2s_signature

router = APIRouter(prefix="/api/webhooks/m2s", tags=["webhooks M2S"])
log = logging.getLogger("vigie.webhook.m2s")


def _event_payload(body: dict) -> dict:
    payload = body.get("data", body.get("dossier", body))
    if isinstance(payload, dict) and isinstance(payload.get("dossier"), dict):
        payload = payload["dossier"]
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Payload dossier M2S invalide.")
    return payload


@router.post("/dossier-status", summary="Statut dossier reçu de M2S (HMAC + idempotence)")
async def dossier_status_webhook(
    request: Request,
    x_m2s_signature: Annotated[str | None, Header(alias="X-M2S-Signature-256")] = None,
    x_hub_signature: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
    x_m2s_event_id: Annotated[str | None, Header(alias="X-M2S-Event-ID")] = None,
):
    runtime = get_m2s_runtime_config()
    if runtime.mode != "webhook":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Le mode webhook M2S n'est pas activé dans Paramètres.",
        )
    if not config.m2s_webhook_secret.strip():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "M2S_WEBHOOK_SECRET n'est pas configuré sur le backend.",
        )
    if not status_contract_configured():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Le contrat de statut M2S doit être confirmé et configuré côté backend.",
        )

    raw_body = await request.body()
    signature = x_m2s_signature or x_hub_signature
    if not valid_m2s_signature(raw_body, signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Signature HMAC M2S invalide.")

    try:
        body = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Corps JSON M2S invalide.") from None
    if not isinstance(body, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Le webhook M2S doit être un objet JSON.")

    event_id = str(x_m2s_event_id or body.get("event_id") or body.get("id") or "").strip()
    if not event_id or len(event_id) > 160:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "event_id M2S obligatoire (160 caractères maximum).",
        )
    payload = _event_payload(body)
    dossier_ref = extract_m2s_ref(payload)
    mapped_status = extract_m2s_status(payload)
    if not dossier_ref:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Référence sinistre M2S absente.")
    if mapped_status is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Statut M2S absent ou inconnu ; événement refusé sans modifier le dossier.",
        )

    repo = get_repo()
    payload_sha256 = hashlib.sha256(raw_body).hexdigest()
    existing_event = repo.get_m2s_webhook_event(event_id)
    if existing_event and existing_event.get("payload_sha256") != payload_sha256:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "event_id M2S déjà utilisé avec un payload différent.",
        )
    if not repo.claim_m2s_webhook_event(event_id, payload_sha256):
        # Relire après le claim pour couvrir deux requêtes concurrentes qui
        # arrivent avec le même event_id mais des corps différents.
        claimed_event = repo.get_m2s_webhook_event(event_id)
        if claimed_event and claimed_event.get("payload_sha256") != payload_sha256:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "event_id M2S déjà utilisé avec un payload différent.",
            )
        log.info("Événement M2S rejoué et ignoré : %s", event_id)
        return {
            "accepted": True,
            "duplicate": True,
            "event_id": event_id,
            "dossier_ref": dossier_ref,
            "status_changed": False,
        }

    dossier_id: str | None = None
    try:
        mapped = map_m2s_payload(payload)
        if mapped is not None:
            result = import_dossiers_list(
                [mapped],
                sync_existing=True,
                allow_status_updates=True,
            )
            dossier = repo.get_dossier_by_ref(dossier_ref)
            dossier_id = dossier.id if dossier else None
            changed = bool(result.status_changed)
        else:
            # Un webhook de statut peut ne contenir que référence + statut.
            # Les créations restent réservées aux payloads complets/polling.
            dossier = repo.get_dossier_by_ref(dossier_ref)
            if not dossier:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "Dossier inconnu et payload M2S incomplet pour le créer.",
                )
            dossier_id = dossier.id
            changed = repo.apply_m2s_status(dossier.id, mapped_status)

        repo.complete_m2s_webhook_event(
            event_id,
            processing_status="processed",
            dossier_id=dossier_id,
        )
        log.info(
            "Événement M2S traité : event=%s dossier=%s statut=%s changement=%s",
            event_id,
            dossier_ref,
            mapped_status,
            changed,
        )
        return {
            "accepted": True,
            "duplicate": False,
            "event_id": event_id,
            "dossier_ref": dossier_ref,
            "status": mapped_status,
            "status_changed": changed,
        }
    except HTTPException as exc:
        repo.complete_m2s_webhook_event(
            event_id,
            processing_status="failed",
            dossier_id=dossier_id,
            error_message=str(exc.detail)[:500],
        )
        raise
    except Exception as exc:
        repo.complete_m2s_webhook_event(
            event_id,
            processing_status="failed",
            dossier_id=dossier_id,
            error_message=str(exc)[:500],
        )
        log.exception("Échec du traitement de l'événement M2S %s", event_id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Échec interne du traitement M2S ; l'événement peut être rejoué.",
        ) from exc
