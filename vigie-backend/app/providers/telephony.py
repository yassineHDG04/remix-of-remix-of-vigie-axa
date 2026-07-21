"""Fournisseurs de canaux d'appel LiveKit.

Trois implémentations derrière ``CallProvider`` :
- MockTelephony       : simulation locale ;
- TwilioSipProvider   : canal téléphonique SIP historique ;
- WhatsAppCallProvider: WhatsApp Business Calling via le connecteur LiveKit.

Le moteur ne connaît que l'interface place_call(). En mode réel, l'agent
(agent/worker.py) mène l'appel et poste le résultat de façon asynchrone via
POST /api/webhooks/calls/{call_id}/result — place_call() ne fait ici que
DÉCLENCHER l'appel (dispatch), il ne renvoie jamais de résultat immédiat.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Protocol

from ..config import config

log = logging.getLogger("vigie.telephony")


@dataclass
class PlacedCall:
    provider_ref: str
    call_channel_used: str = "sip"
    fallback_reason: Optional[str] = None
    estimated_transport_cost_usd: float = 0.0
    # En mock, le résultat est connu immédiatement :
    immediate_status: Optional[str] = None        # pris | non_joignable | repondeur
    immediate_duration_sec: int = 0
    immediate_reason: Optional[str] = None
    immediate_category: Optional[str] = None
    immediate_transcript: list = field(default_factory=list)


class CallProvider(Protocol):
    """Contrat unique vu par le moteur d'escalade."""

    channel: str

    def place_call(
        self,
        *,
        phone: str,
        ref_m2s: str,
        remaining_label: str,
        next_call_label: str,
        call_id: str | None = None,
        dossier_id: str | None = None,
        stage: int | None = None,
    ) -> PlacedCall: ...


MOCK_REASONS = [
    ("Had jouj ma bghawch itfahmo, kayn khilaf 3la l'mas2oulia.", "desaccord_parties"),
    ("L'blasa dyal l'accident machi f zone dyali, khassni wa9t bach nossel.", "zone_hors_km"),
    ("L'expert baqi ma ja, rapport dyalo ghadi ikoun ghedda.", "expertise_en_cours"),
    ("Baqi kansennaw chi pièces mn tarf l'client.", "pieces_manquantes"),
    ("Tiers l'akhor ma kayjaweb chi 3la telefone.", "injoignable_tiers"),
]


def _mock_transcript(ref_m2s: str, reason: str, remaining_label: str) -> list:
    return [
        {"speaker": "ia", "text": f"Salam, ana l'assistant AI dyal l'assurance. Kan3yyet lik 3la dossier {ref_m2s} li baqi machi validé ou t3ettel. Chnou sabab dyal te3ttal ?"},
        {"speaker": "constateur", "text": reason},
        {"speaker": "ia", "text": f"Wakha, sabab t9eyyed. Baqi lik {remaining_label} bach itvalida dossier. Chokran 3la l'mosahama dyalek."},
    ]


class MockTelephony:
    channel = "mock"

    def __init__(self, requested_channel: str = "sip") -> None:
        self.requested_channel = requested_channel

    def place_call(self, *, phone: str, ref_m2s: str, remaining_label: str, next_call_label: str,
                   call_id: str | None = None, dossier_id: str | None = None, stage: int | None = None) -> PlacedCall:
        answered = random.random() < config.mock_answer_rate
        if answered:
            reason, cat = random.choice(MOCK_REASONS)
            return PlacedCall(
                provider_ref=f"mock-{random.randint(10000, 99999)}",
                call_channel_used=self.requested_channel,
                immediate_status="pris",
                immediate_duration_sec=random.randint(35, 120),
                immediate_reason=reason,
                immediate_category=cat,
                immediate_transcript=_mock_transcript(ref_m2s, reason, remaining_label),
            )
        return PlacedCall(
            provider_ref=f"mock-{random.randint(10000, 99999)}",
            call_channel_used=self.requested_channel,
            immediate_status=random.choice(["non_joignable", "repondeur"]),
            immediate_duration_sec=random.randint(15, 40),
        )


def _run_async(coro):
    """Exécute une coroutine dans un thread dédié, avec sa propre boucle asyncio.

    Nécessaire car place_call() doit rester APPELABLE DE FAÇON SYNCHRONE (le
    moteur — engine.py — est synchrone), y compris quand il est invoqué depuis
    engine_loop(), qui est déjà une coroutine en cours d'exécution dans la
    boucle asyncio principale (où un simple asyncio.run() échouerait).
    """
    box: dict = {}

    def runner():
        try:
            box["value"] = asyncio.run(coro)
        except Exception as e:  # noqa: BLE001
            box["error"] = e

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


class TwilioSipProvider:
    """Déclenche un VRAI appel : dispatch explicite de l'agent vocal
    (agent/worker.py, agent_name="vigie-agent") dans une nouvelle room, avec
    le contexte du dossier en métadonnées. C'est l'AGENT lui-même qui, en
    voyant un numéro de téléphone dans ses métadonnées, compose l'appel SIP
    sortant via create_sip_participant() puis mène la conversation.

    Fonctionne à l'identique avec Twilio (test) et un trunk SIP marocain
    (prod) — seuls sip_trunk_id / sip_caller_id changent, désormais réglables
    en direct depuis Paramètres -> Téléphonie IA (table settings), sans
    redéploiement.
    """

    channel = "sip"

    def place_call(self, *, phone: str, ref_m2s: str, remaining_label: str, next_call_label: str,
                   call_id: str | None = None, dossier_id: str | None = None, stage: int | None = None) -> PlacedCall:
        # LIVEKIT_URL / API_KEY / API_SECRET, OPENAI_API_KEY, VIGIE_API_BASE_URL et
        # les garde-fous de coût sont pilotés depuis Paramètres -> "Agent vocal &
        # LiveKit" (table settings), pas depuis .env — .env ne sert plus que de
        # repli si aucune valeur n'a jamais été enregistrée en base.
        # NOTE : livekit_url/api_key/api_secret ici n'affectent que CE dispatch
        # (le backend qui APPELLE LiveKit) — le worker agent, lui, s'enregistre
        # auprès de LiveKit à son propre démarrage avec SES variables d'env ;
        # les changer ici ne le reconnecte pas à un autre projet sans redémarrage
        # du worker (voir agent/README.md).
        from ..repo import get_repo
        s = get_repo().get_settings()
        livekit_url = s.livekit_url or config.livekit_url
        livekit_api_key = s.livekit_api_key or config.livekit_api_key
        livekit_api_secret = s.livekit_api_secret or config.livekit_api_secret
        if not (livekit_url and livekit_api_key and livekit_api_secret):
            raise RuntimeError(
                "Téléphonie réelle non configurée : renseigne LIVEKIT_URL, LIVEKIT_API_KEY, "
                "LIVEKIT_API_SECRET dans Paramètres -> Agent vocal & LiveKit (ou dans .env, ou laisse MOCK_MODE=true)."
            )
        sip_trunk_id = s.sip_trunk_id or config.sip_trunk_id
        sip_caller_id = s.sip_caller_id or config.sip_caller_id
        if not sip_trunk_id:
            raise RuntimeError(
                "Aucun SIP_TRUNK_ID configuré : renseigne-le dans Paramètres -> "
                "Téléphonie IA (ou SIP_TRUNK_ID dans .env en dernier recours)."
            )
        room_name = f"vigie-{ref_m2s}-{int(time.time())}"
        metadata = {
            "phone": phone, "ref_m2s": ref_m2s,
            "remaining_label": remaining_label, "next_call_label": next_call_label,
            "stage": stage, "call_id": call_id, "dossier_id": dossier_id,
            "sip_trunk_id": sip_trunk_id, "sip_caller_id": sip_caller_id,
            # Transmis à l'agent pour un pilotage PAR APPEL, sans redémarrage :
            "openai_api_key": s.openai_api_key or "",
            "vigie_api_base_url": s.vigie_api_base_url or "",
            "agent_max_call_seconds": s.agent_max_call_seconds,
            "agent_max_response_tokens": s.agent_max_response_tokens,
            "agent_max_turns": s.agent_max_turns,
            # Le worker construit le moteur au démarrage de CE job. Une
            # modification dans /parametres s'applique donc au prochain appel.
            "voice_engine": s.voice_engine,
            "realtime_model": s.realtime_model,
            "stt_provider": s.stt_provider,
            "stt_model": s.stt_model,
            "stt_language": s.stt_language,
            "llm_model": s.llm_model,
            "tts_provider": s.tts_provider,
            "tts_model": s.tts_model,
            "tts_voice_id": s.tts_voice_id,
            "call_channel": "sip",
            "transport_cost_per_minute_usd": config.sip_estimated_cost_per_minute_usd,
        }
        log.info("Dispatch agent réel -> room=%s phone=%s trunk=%s", room_name, phone, sip_trunk_id)
        _run_async(self._dispatch(room_name, metadata, livekit_url, livekit_api_key, livekit_api_secret))
        # Le résultat n'est PAS immédiat : l'agent postera sur le webhook
        # à la fin de l'appel (voir agent/worker.py -> post_result_to_backend).
        return PlacedCall(provider_ref=room_name, call_channel_used="sip")

    async def _dispatch(self, room_name: str, metadata: dict,
                        livekit_url: str, livekit_api_key: str, livekit_api_secret: str) -> None:
        from livekit import api
        lk = api.LiveKitAPI(livekit_url, livekit_api_key, livekit_api_secret)
        try:
            await lk.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name="vigie-agent",
                    room=room_name,
                    metadata=json.dumps(metadata),
                )
            )
        finally:
            await lk.aclose()


class WhatsAppCallProvider:
    """Initie un appel WhatsApp Business puis dispatche le même agent Vigie.

    Le média n'est pas géré par ``m2s-api`` : le connecteur officiel LiveKit
    négocie l'audio avec Meta. Le webhook ``/api/webhooks/whatsapp`` transmet
    ensuite la réponse SDP à ``ConnectWhatsAppCall``.
    """

    channel = "whatsapp"

    def place_call(self, *, phone: str, ref_m2s: str, remaining_label: str, next_call_label: str,
                   call_id: str | None = None, dossier_id: str | None = None,
                   stage: int | None = None) -> PlacedCall:
        if not config.whatsapp_calls_enabled:
            raise RuntimeError("whatsapp_calling_disabled")
        if not config.whatsapp_calls_access_token:
            raise RuntimeError("whatsapp_access_token_missing")
        if not config.whatsapp_calls_phone_number_id:
            raise RuntimeError("whatsapp_phone_number_id_missing")

        from ..repo import get_repo

        s = get_repo().get_settings()
        livekit_url = s.livekit_url or config.livekit_url
        livekit_api_key = s.livekit_api_key or config.livekit_api_key
        livekit_api_secret = s.livekit_api_secret or config.livekit_api_secret
        if not (livekit_url and livekit_api_key and livekit_api_secret):
            raise RuntimeError("livekit_credentials_missing")

        whatsapp_to = "".join(ch for ch in phone if ch.isdigit())
        if not whatsapp_to:
            raise RuntimeError("invalid_whatsapp_destination")

        room_name = f"vigie-wa-{ref_m2s}-{int(time.time())}"
        metadata = {
            "phone": phone,
            "ref_m2s": ref_m2s,
            "remaining_label": remaining_label,
            "next_call_label": next_call_label,
            "stage": stage,
            "call_id": call_id,
            "dossier_id": dossier_id,
            "call_channel": "whatsapp",
            "whatsapp_ringing_timeout_seconds": config.whatsapp_calls_ringing_timeout_seconds,
            "transport_cost_per_minute_usd": config.whatsapp_estimated_cost_per_minute_usd,
            "openai_api_key": s.openai_api_key or "",
            "vigie_api_base_url": s.vigie_api_base_url or "",
            "agent_max_call_seconds": s.agent_max_call_seconds,
            "agent_max_response_tokens": s.agent_max_response_tokens,
            "agent_max_turns": s.agent_max_turns,
            "voice_engine": s.voice_engine,
            "realtime_model": s.realtime_model,
            "stt_provider": s.stt_provider,
            "stt_model": s.stt_model,
            "stt_language": s.stt_language,
            "llm_model": s.llm_model,
            "tts_provider": s.tts_provider,
            "tts_model": s.tts_model,
            "tts_voice_id": s.tts_voice_id,
        }
        response = _run_async(
            self._dial_and_dispatch(
                room_name,
                whatsapp_to,
                metadata,
                livekit_url,
                livekit_api_key,
                livekit_api_secret,
            )
        )
        whatsapp_call_id = str(getattr(response, "whatsapp_call_id", "") or "")
        if not whatsapp_call_id:
            raise RuntimeError("livekit_whatsapp_call_id_missing")
        log.info(
            "Appel WhatsApp initié -> room=%s phone=%s call_id=%s",
            room_name,
            whatsapp_to,
            whatsapp_call_id,
        )
        return PlacedCall(
            provider_ref=whatsapp_call_id,
            call_channel_used="whatsapp",
        )

    async def _dial_and_dispatch(
        self,
        room_name: str,
        whatsapp_to: str,
        metadata: dict,
        livekit_url: str,
        livekit_api_key: str,
        livekit_api_secret: str,
    ):
        from livekit import api

        lk = api.LiveKitAPI(livekit_url, livekit_api_key, livekit_api_secret)
        try:
            response = await lk.connector.dial_whatsapp_call(
                api.DialWhatsAppCallRequest(
                    whatsapp_phone_number_id=config.whatsapp_calls_phone_number_id,
                    whatsapp_to_phone_number=whatsapp_to,
                    whatsapp_cloud_api_version=config.whatsapp_calls_cloud_api_version,
                    whatsapp_api_key=config.whatsapp_calls_access_token,
                    whatsapp_biz_opaque_callback_data=str(metadata.get("call_id") or ""),
                    room_name=room_name,
                    participant_identity=f"whatsapp_{whatsapp_to}",
                    participant_name="Constateur",
                    participant_metadata=json.dumps({
                        "call_id": metadata.get("call_id"),
                        "dossier_id": metadata.get("dossier_id"),
                        "call_channel": "whatsapp",
                    }),
                    destination_country=config.whatsapp_calls_destination_country,
                )
            )
            metadata["whatsapp_call_id"] = response.whatsapp_call_id
            await lk.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name="vigie-agent",
                    room=response.room_name or room_name,
                    metadata=json.dumps(metadata),
                )
            )
            return response
        finally:
            await lk.aclose()


async def connect_whatsapp_call(whatsapp_call_id: str, sdp_answer: str) -> None:
    """Relie immédiatement la réponse SDP Meta au connecteur LiveKit."""
    from livekit import api
    from livekit.protocol.rtc import SessionDescription

    from ..repo import get_repo

    s = get_repo().get_settings()
    lk = api.LiveKitAPI(
        s.livekit_url or config.livekit_url,
        s.livekit_api_key or config.livekit_api_key,
        s.livekit_api_secret or config.livekit_api_secret,
    )
    try:
        await lk.connector.connect_whatsapp_call(
            api.ConnectWhatsAppCallRequest(
                whatsapp_call_id=whatsapp_call_id,
                sdp=SessionDescription(type="answer", sdp=sdp_answer),
            )
        )
    finally:
        await lk.aclose()


async def cleanup_whatsapp_call(whatsapp_call_id: str) -> None:
    """Nettoie une session terminée par l'utilisateur (appel idempotent best effort)."""
    from livekit import api

    from ..repo import get_repo

    s = get_repo().get_settings()
    lk = api.LiveKitAPI(
        s.livekit_url or config.livekit_url,
        s.livekit_api_key or config.livekit_api_key,
        s.livekit_api_secret or config.livekit_api_secret,
    )
    try:
        await lk.connector.disconnect_whatsapp_call(
            api.DisconnectWhatsAppCallRequest(
                whatsapp_call_id=whatsapp_call_id,
                whatsapp_api_key=config.whatsapp_calls_access_token,
                disconnect_reason=api.DisconnectWhatsAppCallRequest.BUSINESS_INITIATED,
            )
        )
    finally:
        await lk.aclose()


def get_call_provider(channel: str) -> CallProvider:
    if config.mock_mode:
        return MockTelephony(requested_channel=channel)
    if channel == "whatsapp":
        return WhatsAppCallProvider()
    return TwilioSipProvider()


def get_telephony():
    """Compatibilité avec l'ancien code : retourne le fournisseur SIP."""
    return get_call_provider("sip")


# Alias de compatibilité pour les imports externes historiques.
LiveKitSipTelephony = TwilioSipProvider
