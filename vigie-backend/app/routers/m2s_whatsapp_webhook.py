"""Webhook entrant provenant de M2S API WhatsApp."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ..repo import get_repo
from ..security import require_api_key

log = logging.getLogger("vigie.m2s_whatsapp_webhook")

router = APIRouter(
    prefix="/api/webhooks/m2s-whatsapp",
    tags=["webhooks M2S WhatsApp"],
    dependencies=[Depends(require_api_key)],
)

TRACKED_EVENTS = {
    "message.accepted": "accepted",
    "message.sent": "sent",
    "message.delivered": "delivered",
    "message.read": "read",
    "message.failed": "failed",
}


def _parse_event_time(value: object) -> datetime | None:
    """Convertit la date ISO du webhook en datetime UTC sans fuseau."""
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )

        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)

        return parsed
    except ValueError:
        return None


@router.post("", summary="Recevoir un événement de M2S API WhatsApp")
async def receive_m2s_whatsapp_event(request: Request) -> JSONResponse:
    """Reçoit un événement M2S et actualise le suivi de l'alerte."""

    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse(
            {
                "status": "rejected",
                "error": "Corps JSON invalide",
            },
            status_code=400,
        )

    event_id = str(body.get("id") or "")
    event_type = str(body.get("type") or "")
    instance_id = str(body.get("instance_id") or "")

    raw_data = body.get("data")
    data = raw_data if isinstance(raw_data, dict) else {}

    if not event_id or not event_type:
        return JSONResponse(
            {
                "status": "rejected",
                "error": "Les champs id et type sont obligatoires",
            },
            status_code=422,
        )

    message_id = str(data.get("message_id") or "")

    log.info(
        "Webhook M2S reçu : event_id=%s, type=%s, "
        "instance_id=%s, message_id=%s",
        event_id,
        event_type,
        instance_id,
        message_id,
    )

    tracked = False
    message_status = TRACKED_EVENTS.get(event_type)

    if message_status and message_id:
        failure_reason = (
            data.get("reason")
            or data.get("failure_reason")
        )

        tracked = get_repo().update_whatsapp_alert_status(
            m2s_message_id=message_id,
            status=message_status,
            event_id=event_id,
            event_at=_parse_event_time(body.get("occurred_at")),
            failure_reason=(
                str(failure_reason)
                if failure_reason is not None
                else None
            ),
        )

        if tracked:
            log.info(
                "Statut WhatsApp enregistré : message_id=%s, statut=%s",
                message_id,
                message_status,
            )
        else:
            log.warning(
                "Aucune alerte Vigie trouvée pour message_id=%s. "
                "Événement acquitté sans mise à jour.",
                message_id,
            )

    return JSONResponse(
        {
            "status": "received",
            "event_id": event_id,
            "event_type": event_type,
            "tracked": tracked,
        },
        status_code=200,
    )