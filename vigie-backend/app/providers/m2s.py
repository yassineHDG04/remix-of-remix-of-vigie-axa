"""Synchronisation des dossiers et statuts depuis la plateforme M2S.

M2S est la source de vérité de la validation. Vigie ne produit jamais ce
statut : il l'observe soit par webhook HMAC, soit par polling. Le contrat exact
du champ statut n'étant pas encore confirmé, ses valeurs sont volontairement
vides par défaut et configurables par variables d'environnement.
"""
from __future__ import annotations

import asyncio
import logging
import unicodedata
from dataclasses import dataclass

import httpx

from ..config import config
from ..repo import get_repo
from ..schemas import ConstateurIn, DossierImportIn, ImportResult

log = logging.getLogger("vigie.m2s")

# TODO(M2S-CONTRACT) : remplacer uniquement après confirmation écrite de M2S.
# Aucun nom ni aucune valeur métier ne sont devinés dans le code.
M2S_STATUS_FIELD_TODO = ""
M2S_VALIDATED_STATUS_VALUES_TODO: frozenset[str] = frozenset()
M2S_ACTIVE_STATUS_VALUES_TODO: frozenset[str] = frozenset()


@dataclass(frozen=True)
class M2SRuntimeConfig:
    mode: str
    api_url: str
    poll_interval_seconds: int


def get_m2s_runtime_config() -> M2SRuntimeConfig:
    """Résout la configuration live : table settings, puis repli sur .env."""
    try:
        settings = get_repo().get_settings()
    except Exception:
        log.exception("Impossible de lire les paramètres M2S en base ; repli sur .env")
        settings = None

    configured_mode = (getattr(settings, "m2s_sync_mode", "") or "").strip().lower()
    fallback_mode = "polling" if config.m2s_poll_enabled else "disabled"
    mode = configured_mode if configured_mode in {"disabled", "webhook", "polling"} else fallback_mode
    api_url = (
        (getattr(settings, "m2s_dossiers_api_url", "") or "").strip()
        or config.m2s_dossiers_api_url.strip()
    )
    interval = int(
        getattr(settings, "m2s_poll_interval_seconds", 0)
        or config.m2s_poll_interval_seconds
        or 300
    )
    return M2SRuntimeConfig(mode=mode, api_url=api_url, poll_interval_seconds=max(30, interval))


def _normalise_status(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).strip().casefold()


def _configured_values(raw: str, fallback: frozenset[str]) -> frozenset[str]:
    values = {_normalise_status(value) for value in raw.split(",") if value.strip()}
    return frozenset(values) if values else fallback


def status_contract() -> tuple[str, frozenset[str], frozenset[str]]:
    field = config.m2s_status_field.strip() or M2S_STATUS_FIELD_TODO
    validated = _configured_values(
        config.m2s_validated_status_values,
        M2S_VALIDATED_STATUS_VALUES_TODO,
    )
    active = _configured_values(
        config.m2s_active_status_values,
        M2S_ACTIVE_STATUS_VALUES_TODO,
    )
    return field, validated, active


def status_contract_configured() -> bool:
    field, validated, active = status_contract()
    return bool(field and (validated or active))


def _get_path(raw: dict, path: str):
    value: object = raw
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def extract_m2s_status(raw: dict) -> str | None:
    """Traduit le statut source en statut Vigie sans supposer le contrat M2S."""
    field, validated_values, active_values = status_contract()
    if not field:
        return None
    raw_status = _get_path(raw, field)
    if raw_status in (None, ""):
        return None
    normalised = _normalise_status(raw_status)
    if normalised in validated_values:
        return "valide"
    if normalised in active_values:
        return "en_retard"
    log.warning("Statut M2S inconnu ignoré (champ=%s, valeur=%r)", field, raw_status)
    return None


def extract_m2s_ref(raw: dict) -> str:
    for key in ("ref_sinistre", "reference", "ref_m2s"):
        value = raw.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def map_m2s_payload(raw: dict) -> DossierImportIn | None:
    """Convertit un dossier M2S vers le contrat interne Vigie.

    Structure métier déjà connue : ``assuré``, ``vehicule``, ``matricule``,
    ``lieu_sinistre``, ``ref_sinistre``, ``date_sinistre``, ``constateur``,
    ``num_tel_constateur`` et ``nom_assurance``. Le statut passe exclusivement
    par :func:`extract_m2s_status` afin de rester isolé tant que M2S n'a pas
    confirmé son nom et ses valeurs.
    """

    def _get(data: dict, *keys, default=""):
        for key in keys:
            if key in data and data[key] not in (None, ""):
                return data[key]
        return default

    try:
        ref = extract_m2s_ref(raw)
        if not ref:
            raise KeyError("ref_sinistre")
        constateur_nom = _get(raw, "constateur", "nom_constateur", default="Constateur")
        constateur_tel = _get(raw, "num_tel_constateur", "telephone_constateur", "tel_constateur")
        if not constateur_tel:
            raise KeyError("num_tel_constateur")
    except (KeyError, TypeError):
        log.warning("Ligne M2S ignorée (référence ou téléphone constateur manquant) : %s", raw)
        return None

    lieu = str(_get(raw, "lieu_sinistre", "adresse", "lieu"))
    date_sinistre_raw = _get(raw, "date_sisnistre", "date_sinistre", "date_du_sinistre")

    return DossierImportIn(
        ref_m2s=ref,
        constateur=ConstateurIn(
            nom=str(constateur_nom),
            telephone=str(constateur_tel),
            zone="",
        ),
        arrival_at=None,
        matricule=str(_get(raw, "matricule")),
        num_tel_client=str(_get(raw, "num_tel_client", "telephone_client", "tel_client")),
        nom_assurance=str(_get(raw, "nom_assurance", "assurance")),
        adresse=lieu,
        zone=_extract_zone(lieu),
        assure=str(_get(raw, "assuré", "assure", "nom_assure")),
        vehicule=str(_get(raw, "vehicule", "véhicule")),
        date_sinistre=_parse_date(date_sinistre_raw),
        status=extract_m2s_status(raw),
    )


_MOROCCAN_CITIES = [
    "Casablanca", "Rabat", "Fès", "Fes", "Marrakech", "Tanger", "Agadir",
    "Meknès", "Meknes", "Oujda", "Kénitra", "Kenitra", "Tétouan", "Tetouan",
    "Safi", "El Jadida", "Béni Mellal", "Beni Mellal", "Nador", "Khouribga",
    "Settat", "Larache", "Mohammédia", "Mohammedia", "Khemisset", "Taza",
]


def _extract_zone(lieu: str) -> str:
    if not lieu:
        return ""
    lieu_low = lieu.lower()
    for city in _MOROCCAN_CITIES:
        if city.lower() in lieu_low:
            return city
    return ""


def _parse_date(raw_value):
    if not raw_value:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(str(raw_value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def fetch_dossiers(runtime: M2SRuntimeConfig | None = None) -> list[dict]:
    """Appelle l'API M2S et renvoie sa liste de dossiers, sans lever."""
    runtime = runtime or get_m2s_runtime_config()
    if not runtime.api_url:
        log.info("URL API dossiers M2S non configurée — aucune synchronisation.")
        return []
    headers = {"Accept": "application/json"}
    if config.m2s_api_token:
        # TODO(M2S-CONTRACT) : confirmer le nom d'en-tête et le schéma d'auth.
        headers["Authorization"] = f"Bearer {config.m2s_api_token}"
    try:
        response = httpx.get(runtime.api_url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            data = data.get("data") or data.get("dossiers") or []
        return data if isinstance(data, list) else []
    except Exception:
        log.exception("Échec de l'appel à l'API M2S (%s)", runtime.api_url)
        return []


# Alias rétrocompatible pour les appels/tests existants.
fetch_overdue_dossiers = fetch_dossiers


def sync_from_m2s(runtime: M2SRuntimeConfig | None = None) -> ImportResult:
    """Synchronise créations, données et changements de statut depuis M2S."""
    from ..importer import import_dossiers_list

    raw_list = fetch_dossiers(runtime)
    items = [mapped for raw in raw_list if (mapped := map_m2s_payload(raw)) is not None]
    result = import_dossiers_list(items, sync_existing=True, allow_status_updates=True)
    log.info(
        "Sync M2S : %d créés, %d actualisés, %d statuts modifiés, %d ignorés.",
        result.imported,
        result.updated,
        result.status_changed,
        len(result.skipped_existing),
    )
    return result


async def m2s_poll_loop() -> None:
    """Poller toujours vivant, activable à chaud depuis ``/parametres``."""
    log.info("Superviseur de synchronisation M2S démarré.")
    last_idle_reason = ""
    while True:
        runtime = get_m2s_runtime_config()
        if runtime.mode != "polling" or not runtime.api_url:
            reason = "mode non polling" if runtime.mode != "polling" else "URL absente"
            if reason != last_idle_reason:
                log.info("Poller M2S en attente (%s).", reason)
                last_idle_reason = reason
            await asyncio.sleep(10)
            continue

        last_idle_reason = ""
        try:
            sync_from_m2s(runtime)
        except Exception:
            log.exception("Erreur dans le poller M2S")
        await asyncio.sleep(runtime.poll_interval_seconds)
