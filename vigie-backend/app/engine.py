"""Moteur d'escalade — le cœur métier (branché sur la couche repo).

Deux horloges :
  * SLA (mur) : deadline_at = arrival_at + sla_hours. Ne se met JAMAIS en pause.
  * Compteur d'étapes : on ne passe à l'étape suivante que si le constateur
    a répondu (stage_answered=1) à l'étape courante.

Boucle no-answer : rappel toutes les retry_interval_min, max_attempts fois,
puis hand-off humain — le premier atteint entre "N échecs" et "seuil humain" gagne.

Toutes les données passent par get_repo() (SqlRepo en dev/mock, SupabaseRepo en prod).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from .config import config
from .providers.call_routing import attempts_exhausted, next_channel
from .providers.telephony import PlacedCall, get_call_provider
from .providers.whatsapp import notify_handoff
from .repo import CallRow, DossierRow, SettingsRow, get_repo

log = logging.getLogger("vigie.engine")


# ---------- helpers ----------
def get_settings() -> SettingsRow:
    return get_repo().get_settings()


def remaining_minutes(d: DossierRow, now: datetime) -> float:
    return (d.deadline_at - now).total_seconds() / 60.0


def fmt_remaining(minutes: float) -> str:
    m = max(0, int(minutes))
    h, mm = divmod(m, 60)
    return f"{h}h {mm:02d}min" if h else f"{mm} min"


def in_call_window(s: SettingsRow, now: datetime) -> bool:
    hhmm = now.strftime("%H:%M")
    return s.call_window_start <= hhmm <= s.call_window_end


def nb_relances(s: SettingsRow) -> int:
    """Nombre de relances IA actives (borné 1..4)."""
    return max(1, min(4, s.nb_relances_ia))


def active_thresholds(s: SettingsRow) -> list[int]:
    """Les N premiers seuils (temps restant, en minutes) selon nb_relances_ia."""
    allt = [s.relance1_min, s.relance2_min, s.relance3_min, s.relance4_min]
    return allt[: nb_relances(s)]


def target_stage(s: SettingsRow, rem_min: float) -> int:
    """Étape IA exigée par le temps restant (0 = pas encore de relance ; max = N)."""
    stage = 0
    for i, t in enumerate(active_thresholds(s), start=1):
        if rem_min <= t:
            stage = i
    return stage


def _stage_calls(dossier_id: str, stage: int) -> list[CallRow]:
    return [c for c in get_repo().list_calls(dossier_id) if c.stage == stage]


# ---------- actions ----------
def _handoff(d: DossierRow, reason: str, rem_min: float) -> None:
    repo = get_repo()
    n = nb_relances(repo.get_settings())
    repo.update_dossier(d.id, {
        "current_stage": n + 1,          # une étape au-delà de la dernière relance IA
        "handoff_reason": reason,
        "next_action_at": None,
    })
    log.info("HAND-OFF humain %s (%s, restant=%s)", d.ref_m2s, reason, fmt_remaining(rem_min))
    notify_handoff(d.id, d.ref_m2s, d.constateur_nom, d.constateur_telephone,
                   fmt_remaining(rem_min), reason)


def _start_call(d: DossierRow, stage: int, rem_min: float, s: SettingsRow) -> str | None:
    repo = get_repo()
    fresh = repo.get_dossier(d.id)
    if not fresh or fresh.status != "en_retard":
        log.info("Appel annulé avant planification : %s est déjà validé dans M2S.", d.ref_m2s)
        return None
    now = datetime.utcnow()
    th = active_thresholds(s)
    next_threshold = th[stage] if stage < len(th) else s.humain_min  # prochain seuil (ou humain)
    next_label = fmt_remaining(max(0, rem_min - next_threshold))

    previous_calls = _stage_calls(d.id, stage)
    channel = next_channel(s.call_channel, previous_calls, s.whatsapp_max_attempts)
    attempt = len(previous_calls) + 1
    call_id = repo.insert_call({
        "dossier_id": d.id,
        "stage": stage,
        "attempt_no": attempt,
        "started_at": now,
        "status": "en_cours",
        "call_channel_used": channel,
    })
    repo.update_dossier(d.id, {
        "current_stage": stage, "stage_attempts": attempt,
        "stage_answered": 0, "next_action_at": None,
    })

    # Deuxième lecture pour fermer la petite fenêtre de course entre la
    # création de la ligne d'appel et le dispatch LiveKit.
    fresh = repo.get_dossier(d.id)
    if not fresh or fresh.status != "en_retard":
        repo.update_call(call_id, {
            "status": "echec",
            "ended_at": datetime.utcnow(),
            "delay_reason": "Appel annulé : dossier validé dans M2S avant dispatch.",
        })
        log.info("Dispatch annulé : validation M2S reçue pour %s.", d.ref_m2s)
        return None

    log.info(
        "APPEL %s — canal %s, étape %d tentative globale %d (restant=%s)",
        d.ref_m2s,
        channel,
        stage,
        attempt,
        fmt_remaining(rem_min),
    )
    try:
        placed = get_call_provider(channel).place_call(
            phone=d.constateur_telephone,
            ref_m2s=d.ref_m2s,
            remaining_label=fmt_remaining(rem_min),
            next_call_label=next_label,
            call_id=call_id,
            dossier_id=d.id,
            stage=stage,
        )
    except Exception as exc:  # échec fournisseur = résultat traçable, jamais tick cassé
        fallback_reason = f"{type(exc).__name__}:{str(exc)[:180]}"
        log.warning(
            "Placement %s impossible pour %s — bascule planifiée : %s",
            channel,
            d.ref_m2s,
            fallback_reason,
        )
        placed = PlacedCall(
            provider_ref=f"{channel}-placement-error-{call_id}",
            call_channel_used=channel,
            fallback_reason=fallback_reason,
            immediate_status="echec",
        )
    repo.update_call(call_id, {
        "provider_ref": placed.provider_ref,
        "call_channel_used": placed.call_channel_used,
        "fallback_reason": placed.fallback_reason,
        "estimated_transport_cost_usd": placed.estimated_transport_cost_usd,
    })

    # Mode MOCK : le résultat est immédiat -> on l'applique tout de suite.
    if placed.immediate_status is not None:
        call = repo.get_call(call_id)
        dossier = repo.get_dossier(d.id)  # relire l'état à jour (stage_attempts, etc.)
        apply_call_result(
            call, dossier,
            status=placed.immediate_status,
            duration_sec=placed.immediate_duration_sec,
            delay_reason=placed.immediate_reason,
            delay_category=placed.immediate_category,
            transcript=placed.immediate_transcript,
            call_channel_used=placed.call_channel_used,
            fallback_reason=placed.fallback_reason,
            estimated_transport_cost_usd=placed.estimated_transport_cost_usd,
        )
    return call_id


def apply_call_result(call: CallRow, dossier: DossierRow, *, status: str, duration_sec: int = 0,
                      delay_reason: str | None = None, delay_category: str | None = None,
                      transcript: list | None = None, voice_engine_used: str | None = None,
                      models_used: dict | None = None, estimated_cost_usd: float = 0.0,
                      call_channel_used: str | None = None,
                      fallback_reason: str | None = None,
                      estimated_transport_cost_usd: float = 0.0) -> None:
    """Applique un résultat d'appel (mock immédiat OU webhook du provider réel)."""
    repo = get_repo()
    now = datetime.utcnow()
    s = repo.get_settings()

    answered = status == "pris"
    outcome = "cause_captee" if (answered and delay_reason) else (
        "refus" if status == "refus" else "non_joignable" if status in ("non_joignable", "repondeur") else None
    )
    repo.update_call(call.id, {
        "status": status, "ended_at": now, "duration_sec": duration_sec,
        "outcome": outcome, "delay_reason": delay_reason, "delay_category": delay_category,
        "voice_engine_used": voice_engine_used,
        "models_used": models_used or {},
        "estimated_cost_usd": max(0.0, estimated_cost_usd),
        "call_channel_used": call_channel_used or getattr(call, "call_channel_used", None),
        "fallback_reason": fallback_reason or getattr(call, "fallback_reason", None),
        "estimated_transport_cost_usd": max(0.0, estimated_transport_cost_usd),
    })
    repo.insert_transcript(call.id, transcript or [])

    # Une validation reçue pendant l'appel est terminale. On conserve la trace
    # et la transcription de l'appel déjà décroché, mais aucun résultat tardif
    # ne doit reprogrammer une relance ou modifier le cycle du dossier.
    current_dossier = repo.get_dossier(dossier.id)
    if current_dossier and current_dossier.status == "valide":
        log.info(
            "Résultat d'appel archivé sans relance : %s validé par M2S pendant l'appel.",
            current_dossier.ref_m2s,
        )
        return

    if answered:
        repo.update_dossier(dossier.id, {"stage_answered": 1, "next_action_at": None})
    else:
        stage_calls = _stage_calls(dossier.id, call.stage)
        if attempts_exhausted(
            s.call_channel,
            stage_calls,
            sip_max_attempts=s.max_attempts,
            whatsapp_max_attempts=s.whatsapp_max_attempts,
        ):
            _handoff(dossier, "tentatives_epuisees", remaining_minutes(dossier, now))
            return
        # Une erreur immédiate du connecteur (permission, région, credential,
        # feature désactivée) passe au SIP dès le prochain tick. Une simple
        # non-réponse respecte l'intervalle de rappel configuré.
        immediate_fallback = bool(fallback_reason) and (
            (call_channel_used or getattr(call, "call_channel_used", None)) == "whatsapp"
            and s.call_channel == "whatsapp_then_sip"
        )
        repo.update_dossier(dossier.id, {
            "stage_answered": 0,
            "next_action_at": now if immediate_fallback else (
                now + timedelta(minutes=s.retry_interval_min)
            ),
        })


# ---------- tick ----------
def tick(db=None) -> dict:
    """Évalue tous les dossiers en retard et déclenche les actions dues.
    Le paramètre db est ignoré (compat rétro) ; tout passe par get_repo()."""
    repo = get_repo()
    s = repo.get_settings()
    now = datetime.utcnow()
    summary = {"evaluated": 0, "calls_started": 0, "handoffs": 0, "skipped_window": 0}

    for d in repo.list_dossiers("en_retard"):
        summary["evaluated"] += 1
        if d.handoff_reason:  # déjà passé à l'humain
            continue
        rem = remaining_minutes(d, now)

        # SLA échu -> hand-off (le mur ne pardonne pas)
        if rem <= 0:
            _handoff(d, "sla_echu", rem)
            summary["handoffs"] += 1
            continue
        # Seuil humain
        if rem <= s.humain_min:
            _handoff(d, "seuil_1h", rem)
            summary["handoffs"] += 1
            continue

        tgt = target_stage(s, rem)
        if tgt == 0:
            continue
        if not in_call_window(s, datetime.now()):
            summary["skipped_window"] += 1
            continue
        if repo.has_call_in_progress(d.id):
            continue

        if d.current_stage < tgt and (d.current_stage == 0 or d.stage_answered):
            # Progression d'étape (1er contact, ou répondu à l'étape précédente,
            # y compris démarrage direct à l'étape correspondant au temps restant).
            if _start_call(d, stage=tgt, rem_min=rem, s=s):
                summary["calls_started"] += 1
        elif not d.stage_answered and d.stage_attempts > 0:
            # Boucle no-answer : rappel programmé atteint ?
            if d.next_action_at and now >= d.next_action_at:
                if _start_call(d, stage=d.current_stage, rem_min=rem, s=s):
                    summary["calls_started"] += 1
    return summary


async def engine_loop():
    log.info("Moteur d'escalade démarré (tick=%ss, mock=%s, supabase=%s)",
             config.engine_tick_seconds, config.mock_mode, config.use_supabase)
    while True:
        try:
            tick()
        except Exception:
            log.exception("Erreur dans le tick moteur")
        await asyncio.sleep(config.engine_tick_seconds)
