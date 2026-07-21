"""Décision pure du canal d'appel pour le chantier 3.

Cette couche ne contacte aucun fournisseur. Elle rend la boucle déterministe et
testable : WhatsApp consomme son propre quota, puis SIP consomme le quota
historique ``max_attempts`` avant le hand-off humain.
"""
from __future__ import annotations

from typing import Iterable, Protocol


class AttemptLike(Protocol):
    call_channel_used: str | None
    fallback_reason: str | None


VALID_CALL_CHANNELS = {"sip", "whatsapp", "whatsapp_then_sip"}


def normalize_strategy(value: str | None) -> str:
    return value if value in VALID_CALL_CHANNELS else "sip"


def channel_attempts(attempts: Iterable[AttemptLike], channel: str) -> int:
    return sum(1 for item in attempts if item.call_channel_used == channel)


def next_channel(
    strategy: str,
    attempts: Iterable[AttemptLike],
    whatsapp_max_attempts: int,
) -> str:
    """Retourne le canal de la prochaine tentative de l'étape courante.

    Une erreur de placement permanente/immédiate est matérialisée par
    ``fallback_reason``. Dans ce cas, on n'insiste pas sur WhatsApp : la
    prochaine tentative passe directement au SIP.
    """
    normalized = normalize_strategy(strategy)
    if normalized == "sip":
        return "sip"
    if normalized == "whatsapp":
        return "whatsapp"

    rows = list(attempts)
    whatsapp_rows = [row for row in rows if row.call_channel_used == "whatsapp"]
    if any((row.fallback_reason or "").strip() for row in whatsapp_rows):
        return "sip"
    limit = max(1, min(10, int(whatsapp_max_attempts or 1)))
    return "whatsapp" if len(whatsapp_rows) < limit else "sip"


def attempts_exhausted(
    strategy: str,
    attempts: Iterable[AttemptLike],
    *,
    sip_max_attempts: int,
    whatsapp_max_attempts: int,
) -> bool:
    """Indique si le dernier canal autorisé a épuisé son quota."""
    normalized = normalize_strategy(strategy)
    rows = list(attempts)
    if normalized == "whatsapp":
        return channel_attempts(rows, "whatsapp") >= max(1, whatsapp_max_attempts)
    # En mode mixte comme en mode historique, seul l'épuisement du SIP est
    # terminal. Les échecs WhatsApp provoquent une bascule, jamais un hand-off.
    return channel_attempts(rows, "sip") >= max(1, sip_max_attempts)

