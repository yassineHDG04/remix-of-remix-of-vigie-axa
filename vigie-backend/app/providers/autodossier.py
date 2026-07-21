"""Générateur automatique de dossiers sinistres.

Sert de REMPLAÇANT TEMPORAIRE à l'API M2S, tant qu'elle n'est pas disponible.
Crée périodiquement un dossier "frais" (arrivée = maintenant, donc SLA complet
devant lui) assigné à un unique constateur de test.

Le dossier suit ensuite le cycle NORMAL du moteur d'escalade :
  arrivée -> attente -> relance IA 1 -> 2 -> ... -> hand-off humain,
avec de VRAIS appels téléphoniques si MOCK_MODE=false.

Le jour où l'API M2S arrive : on désactive ce générateur
(AUTO_DOSSIER_ENABLED=false) et on active le poller (app/providers/m2s.py).
Aucun autre changement n'est nécessaire — le moteur ne voit aucune différence.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from ..config import config
from ..schemas import ConstateurIn, DossierImportIn, ImportResult

log = logging.getLogger("vigie.autodossier")


def _next_ref(now: datetime) -> str:
    """Référence unique et lisible, basée sur l'horodatage (évite les collisions)."""
    return f"{config.auto_dossier_ref_prefix}-{now.strftime('%Y%m%d-%H%M%S')}"


def create_one_dossier() -> ImportResult:
    """Crée UN dossier frais (arrival_at = maintenant) pour le constateur configuré.

    "Frais" = le SLA complet (sla_hours) démarre maintenant. Le premier appel
    n'interviendra donc qu'au franchissement du 1er seuil de relance
    (par défaut : quand il ne reste que 240 min, soit 2h après l'arrivée).
    """
    from ..importer import import_dossiers_list  # import local : évite un cycle

    now = datetime.utcnow()
    item = DossierImportIn(
        ref_m2s=_next_ref(now),
        constateur=ConstateurIn(
            nom=config.auto_dossier_constateur_nom,
            telephone=config.auto_dossier_constateur_tel,
            zone=config.auto_dossier_constateur_zone,
        ),
        arrival_at=now,  # dossier FRAIS : tout le SLA reste à courir
    )
    result = import_dossiers_list([item])
    if result.imported:
        log.info("Dossier auto-créé : %s (constateur %s)",
                 item.ref_m2s, config.auto_dossier_constateur_tel)
    else:
        log.warning("Dossier %s déjà présent — ignoré.", item.ref_m2s)
    return result


async def auto_dossier_loop() -> None:
    """Boucle de fond : crée un dossier frais toutes les N heures.

    Crée un premier dossier immédiatement au démarrage (sinon il faudrait
    attendre N heures avant de voir quoi que ce soit se passer).
    """
    interval_h = max(0.05, config.auto_dossier_interval_hours)  # garde-fou : min 3 min
    interval_s = int(interval_h * 3600)
    log.info("Générateur de dossiers démarré (toutes les %sh, constateur %s).",
             interval_h, config.auto_dossier_constateur_tel)

    while True:
        try:
            create_one_dossier()
        except Exception:
            log.exception("Erreur lors de la création automatique d'un dossier")
        await asyncio.sleep(interval_s)
