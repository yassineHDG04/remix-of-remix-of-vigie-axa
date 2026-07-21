"""Import des dossiers (endpoint HTTP + poller m2s), via la couche repo."""
from datetime import datetime, timedelta

from .repo import get_repo, new_uuid
from .schemas import DossierImportIn, ImportResult


def _m2s_values(item: DossierImportIn, constateur_id: str) -> dict:
    return {
        "constateur_id": constateur_id,
        "matricule": item.matricule,
        "num_tel_client": item.num_tel_client,
        "nom_assurance": item.nom_assurance,
        "adresse": item.adresse,
        "zone": item.zone,
        "assure": item.assure,
        "vehicule": item.vehicule,
        "date_sinistre": item.date_sinistre,
    }


def import_dossiers_list(
    items: list[DossierImportIn], *, sync_existing: bool = False,
    allow_status_updates: bool = False,
) -> ImportResult:
    """Importe ou synchronise des dossiers M2S.

    Le chemin historique ``/api/dossiers/import`` conserve son comportement
    d'insertion idempotente. Seuls le poller et le webhook M2S passent
    ``sync_existing=True`` et ``allow_status_updates=True`` : une validation ne
    peut donc jamais être produite par un import client générique.
    """
    repo = get_repo()
    s = repo.get_settings()
    imported, updated, status_changed, skipped = 0, 0, 0, []
    for it in items:
        constateur_id = repo.get_or_create_constateur(
            it.constateur.nom, it.constateur.telephone, it.constateur.zone)
        existing = repo.get_dossier_by_ref(it.ref_m2s)
        if existing:
            if not sync_existing:
                skipped.append(it.ref_m2s)
                continue
            repo.update_m2s_fields(existing.id, _m2s_values(it, constateur_id))
            updated += 1
            if allow_status_updates and it.status:
                status_changed += int(repo.apply_m2s_status(existing.id, it.status))
            continue

        arrival = it.arrival_at or datetime.utcnow()
        initial_status = it.status if allow_status_updates and it.status else "en_retard"
        repo.insert_dossier({
            "id": new_uuid(),
            "ref_m2s": it.ref_m2s,
            "constateur_id": constateur_id,
            "arrival_at": arrival,
            "sla_hours": s.sla_hours,
            "deadline_at": arrival + timedelta(hours=s.sla_hours),
            "status": initial_status,
            "current_stage": 0,
            "validated_at": datetime.utcnow() if initial_status == "valide" else None,
            **_m2s_values(it, constateur_id),
        })
        imported += 1
        status_changed += int(initial_status == "valide")
    return ImportResult(
        imported=imported,
        skipped_existing=skipped,
        updated=updated,
        status_changed=status_changed,
    )
