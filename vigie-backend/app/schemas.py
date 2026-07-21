from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

DelayCategory = Literal[
    "desaccord_parties", "zone_hors_km", "expertise_en_cours",
    "pieces_manquantes", "injoignable_tiers", "autre",
]
CallStatus = Literal["en_cours", "pris", "non_joignable", "repondeur", "refus", "echec"]


# ---- Import (API m2s -> notre système) ----
class ConstateurIn(BaseModel):
    nom: str
    telephone: str
    zone: str = ""


class DossierImportIn(BaseModel):
    ref_m2s: str
    constateur: ConstateurIn
    arrival_at: Optional[datetime] = None  # défaut: maintenant (UTC)
    matricule: str = ""
    num_tel_client: str = ""
    nom_assurance: str = ""
    adresse: str = ""
    zone: str = ""
    assure: str = ""
    vehicule: str = ""
    date_sinistre: Optional[datetime] = None
    # Valeur déjà traduite dans le vocabulaire Vigie par map_m2s_payload().
    # None signifie que le contrat de statut M2S n'est pas encore connu.
    status: Optional[Literal["en_retard", "valide"]] = None


class ImportResult(BaseModel):
    imported: int
    skipped_existing: list[str]
    updated: int = 0
    status_changed: int = 0


# ---- Lecture ----
class ConstateurOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    nom: str
    telephone: str
    zone: str


class TranscriptTurnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    turn_no: int
    speaker: str
    text: str
    ts: datetime


class CallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    dossier_id: str
    stage: int
    attempt_no: int
    started_at: datetime
    ended_at: Optional[datetime]
    duration_sec: int
    status: str
    outcome: Optional[str]
    delay_reason: Optional[str]
    delay_category: Optional[str]
    voice_engine_used: Optional[str] = None
    models_used: dict[str, str] = Field(default_factory=dict)
    estimated_cost_usd: float = 0.0
    call_channel_used: Optional[Literal["sip", "whatsapp", "mock"]] = None
    fallback_reason: Optional[str] = None
    provider_connected_at: Optional[datetime] = None
    estimated_transport_cost_usd: float = 0.0


class CallDetailOut(CallOut):
    transcript: list[TranscriptTurnOut] = Field(default_factory=list)


class DossierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    ref_m2s: str
    constateur: ConstateurOut
    arrival_at: datetime
    sla_hours: float
    deadline_at: datetime
    status: str
    current_stage: int
    stage_attempts: int
    stage_answered: int
    next_action_at: Optional[datetime]
    handoff_reason: Optional[str]
    validated_at: Optional[datetime]
    handoff_acknowledged_at: Optional[datetime] = None
    handoff_acknowledged_by: Optional[str] = None
    matricule: str = ""
    num_tel_client: str = ""
    nom_assurance: str = ""
    adresse: str = ""
    zone: str = ""
    assure: str = ""
    vehicule: str = ""
    date_sinistre: Optional[datetime] = None
    remaining_minutes: Optional[int] = None  # calculé à la volée


class DossierCallEligibilityOut(BaseModel):
    dossier_id: str
    callable: bool
    reason: str


# ---- Settings ----
class SettingsIO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    nb_relances_ia: int = Field(ge=1, le=4)
    relance1_min: int = Field(ge=1)
    relance2_min: int = Field(ge=1)
    relance3_min: int = Field(ge=1)
    relance4_min: int = Field(ge=1)
    humain_min: int = Field(ge=1)
    retry_interval_min: int = Field(ge=1)
    max_attempts: int = Field(ge=1, le=10)
    call_window_start: str
    call_window_end: str
    sla_hours: float = Field(gt=0)
    zineb_whatsapp: str = ""
    selected_whatsapp_id: Optional[str] = None
    sip_trunk_id: str = ""
    sip_caller_id: str = ""
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    openai_api_key: str = ""
    vigie_api_base_url: str = ""
    agent_max_call_seconds: int = Field(default=60, ge=10)
    agent_max_response_tokens: int = Field(default=200, ge=20)
    agent_max_turns: int = Field(default=6, ge=1)
    voice_engine: Literal["realtime", "pipeline"] = "realtime"
    realtime_model: str = "gpt-realtime"
    stt_provider: Literal["openai"] = "openai"
    stt_model: str = "gpt-4o-mini-transcribe"
    stt_language: str = "ar"
    llm_model: str = "gpt-4o-mini"
    tts_provider: Literal["openai"] = "openai"
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice_id: str = "ash"
    m2s_sync_mode: Literal["disabled", "webhook", "polling"] = "disabled"
    m2s_dossiers_api_url: str = ""
    m2s_poll_interval_seconds: int = Field(default=300, ge=30, le=86400)
    call_channel: Literal["sip", "whatsapp", "whatsapp_then_sip"] = "sip"
    whatsapp_max_attempts: int = Field(default=2, ge=1, le=10)

    @model_validator(mode="after")
    def _check_thresholds(self):
        active = [self.relance1_min, self.relance2_min, self.relance3_min, self.relance4_min][: self.nb_relances_ia]
        # strictement décroissants
        for a, b in zip(active, active[1:]):
            if b >= a:
                raise ValueError("Les seuils de relance doivent être strictement décroissants (relance1 > relance2 > ...).")
        # le dernier seuil IA doit rester au-dessus du seuil humain
        if active[-1] <= self.humain_min:
            raise ValueError("Le dernier seuil de relance IA doit être supérieur au seuil d'intervention humaine.")
        # tout doit tenir dans la fenêtre SLA
        if active[0] > self.sla_hours * 60:
            raise ValueError("Le premier seuil de relance dépasse la durée SLA.")
        return self


# ---- Webhook résultat d'appel (provider réel) ----
class CallResultIn(BaseModel):
    status: CallStatus
    duration_sec: int = 0
    delay_reason: Optional[str] = None
    delay_category: Optional[DelayCategory] = None
    transcript: list[dict] = Field(default_factory=list)  # [{speaker, text}]
    voice_engine_used: Optional[Literal["realtime", "pipeline"]] = None
    models_used: dict[str, str] = Field(default_factory=dict)
    estimated_cost_usd: float = Field(default=0.0, ge=0)
    call_channel_used: Optional[Literal["sip", "whatsapp", "mock"]] = None
    fallback_reason: Optional[str] = None
    estimated_transport_cost_usd: float = Field(default=0.0, ge=0)


class KpiOut(BaseModel):
    en_retard: int
    critiques_1h: int
    en_handoff_humain: int
    valides_aujourdhui: int
    appels_aujourdhui: int
    taux_decroche_pct: int
