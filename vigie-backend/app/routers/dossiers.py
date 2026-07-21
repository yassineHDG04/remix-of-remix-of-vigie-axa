from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from ..engine import remaining_minutes
from ..importer import import_dossiers_list
from ..providers.autodossier import create_one_dossier
from ..providers.m2s import sync_from_m2s
from ..repo import DossierRow, get_repo
from ..schemas import (
    ConstateurOut,
    DossierCallEligibilityOut,
    DossierImportIn,
    DossierOut,
    ImportResult,
)
from ..security import require_api_key

router = APIRouter(
    prefix="/api/dossiers",
    tags=["dossiers"],
    dependencies=[Depends(require_api_key)],
)


def _serialize(d: DossierRow, now: datetime) -> DossierOut:
    return DossierOut(
        id=d.id, ref_m2s=d.ref_m2s,
        constateur=ConstateurOut(id=d.constateur_id, nom=d.constateur_nom,
                                 telephone=d.constateur_telephone, zone=d.constateur_zone),
        arrival_at=d.arrival_at, sla_hours=d.sla_hours, deadline_at=d.deadline_at,
        status=d.status, current_stage=d.current_stage, stage_attempts=d.stage_attempts,
        stage_answered=d.stage_answered, next_action_at=d.next_action_at,
        handoff_reason=d.handoff_reason, validated_at=d.validated_at,
        handoff_acknowledged_at=d.handoff_acknowledged_at,
        handoff_acknowledged_by=d.handoff_acknowledged_by,
        matricule=d.matricule, num_tel_client=d.num_tel_client,
        nom_assurance=d.nom_assurance, adresse=d.adresse, zone=d.zone,
        assure=d.assure, vehicule=d.vehicule, date_sinistre=d.date_sinistre,
        remaining_minutes=int(remaining_minutes(d, now)) if d.status == "en_retard" else None,
    )


@router.post("/import", response_model=ImportResult, summary="Import des dossiers en retard (push depuis m2s)")
def import_dossiers(items: list[DossierImportIn]):
    """Point d'entrée si m2s *pousse* les dossiers vers nous. Idempotent."""
    return import_dossiers_list(items)


@router.post("/sync-m2s", response_model=ImportResult, summary="Tirer les dossiers depuis l'API m2s (pull)")
def sync_m2s():
    """Déclenche une récupération depuis l'API m2s configurée (m2s_DOSSIERS_API_URL)."""
    return sync_from_m2s()


@router.post("/auto-create", response_model=ImportResult,
             summary="Créer un dossier frais maintenant (générateur, en attendant l'API M2S)")
def auto_create():
    """Crée immédiatement un dossier frais pour le constateur configuré
    (AUTO_DOSSIER_CONSTATEUR_TEL). Le générateur automatique fait la même chose
    toutes les AUTO_DOSSIER_INTERVAL_HOURS heures s'il est activé."""
    return create_one_dossier()


@router.get("", response_model=list[DossierOut], summary="Lister les dossiers")
def list_dossiers(status: str | None = None):
    now = datetime.utcnow()
    return [_serialize(d, now) for d in get_repo().list_dossiers(status)]


@router.get("/{dossier_id}", response_model=DossierOut)
def get_dossier(dossier_id: str):
    d = get_repo().get_dossier(dossier_id)
    if not d:
        raise HTTPException(404, "Dossier introuvable")
    return _serialize(d, datetime.utcnow())


@router.get("/{dossier_id}/call-eligibility", response_model=DossierCallEligibilityOut)
def call_eligibility(dossier_id: str):
    """Pré-vol du worker : empêche un dispatch ancien d'appeler après validation M2S."""
    dossier = get_repo().get_dossier(dossier_id)
    if not dossier:
        raise HTTPException(404, "Dossier introuvable")
    callable_now = dossier.status == "en_retard" and not dossier.handoff_reason
    reason = "eligible" if callable_now else (
        "validated_by_m2s" if dossier.status == "valide" else "handoff_humain"
    )
    return DossierCallEligibilityOut(
        dossier_id=dossier.id,
        callable=callable_now,
        reason=reason,
    )


@router.post("/{dossier_id}/validate", response_model=DossierOut,
             summary="Route historique verrouillée — validation réservée à M2S")
def validate_dossier(dossier_id: str):
    if not get_repo().get_dossier(dossier_id):
        raise HTTPException(404, "Dossier introuvable")
    raise HTTPException(
        403,
        "Validation interdite dans Vigie : le constateur valide le dossier dans M2S.",
    )
