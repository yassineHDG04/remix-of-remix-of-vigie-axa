import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# Schéma ALIGNÉ sur Supabase (Lovable) :
#  - clés primaires en UUID (text), générées côté application (portable SQLite + Postgres).
#  - colonnes "enum" typées via SAEnum(native_enum=True, create_type=False) :
#       -> Postgres/Supabase : réutilise les types ENUM déjà créés par Supabase
#          (ne tente jamais de les (re)créer) et les filtres WHERE fonctionnent.
#       -> SQLite (dev/mock) : dégradé automatiquement en VARCHAR + CHECK.
#
# dossier.current_stage : 0 (attente) 1..N (relances IA) N+1 (humain)
#   -> hand-off humain détecté via handoff_reason (non nul), pas via le numéro d'étape.


def _uuid() -> str:
    return str(uuid.uuid4())


# --- Types enum (doivent correspondre EXACTEMENT aux enums Supabase) ---
DossierStatus = SAEnum("en_retard", "valide", name="dossier_status",
                       native_enum=True, create_type=False)
CallStatus = SAEnum("en_cours", "pris", "non_joignable", "repondeur", "refus", "echec",
                    name="call_status", native_enum=True, create_type=False)
CallOutcome = SAEnum("cause_captee", "non_joignable", "hors_sujet", "refus",
                     name="call_outcome", native_enum=True, create_type=False)
DelayCategory = SAEnum("desaccord_parties", "zone_hors_km", "expertise_en_cours",
                       "pieces_manquantes", "injoignable_tiers", "autre",
                       name="delay_category", native_enum=True, create_type=False)
Speaker = SAEnum("ia", "constateur", name="speaker",
                 native_enum=True, create_type=False)


class Constateur(Base):
    __tablename__ = "constateurs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    nom: Mapped[str] = mapped_column(String(120))
    telephone: Mapped[str] = mapped_column(String(30), index=True)
    zone: Mapped[str] = mapped_column(String(60), default="")

    dossiers: Mapped[list["Dossier"]] = relationship(back_populates="constateur")


class Dossier(Base):
    __tablename__ = "dossiers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ref_m2s: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    constateur_id: Mapped[str] = mapped_column(String(36), ForeignKey("constateurs.id"))
    arrival_at: Mapped[datetime] = mapped_column(DateTime)
    sla_hours: Mapped[float] = mapped_column(Float, default=6.0)
    deadline_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(DossierStatus, default="en_retard", index=True)
    current_stage: Mapped[int] = mapped_column(Integer, default=0)

    # État de la boucle d'escalade
    stage_attempts: Mapped[int] = mapped_column(Integer, default=0)
    stage_answered: Mapped[int] = mapped_column(Integer, default=0)
    next_action_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    handoff_reason: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)  # texte libre côté Supabase
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    handoff_acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    handoff_acknowledged_by: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)

    # Champs métier additionnels (dossier sinistre M2S)
    matricule: Mapped[str] = mapped_column(String(60), default="")
    num_tel_client: Mapped[str] = mapped_column(String(30), default="")
    nom_assurance: Mapped[str] = mapped_column(String(120), default="")
    adresse: Mapped[str] = mapped_column(String(255), default="")
    zone: Mapped[str] = mapped_column(String(60), default="")
    assure: Mapped[str] = mapped_column(String(120), default="")
    vehicule: Mapped[str] = mapped_column(String(120), default="")
    date_sinistre: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    constateur: Mapped[Constateur] = relationship(back_populates="dossiers")
    calls: Mapped[list["Call"]] = relationship(back_populates="dossier", order_by="Call.started_at")


class Call(Base):
    __tablename__ = "calls"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    dossier_id: Mapped[str] = mapped_column(String(36), ForeignKey("dossiers.id"), index=True)
    stage: Mapped[int] = mapped_column(Integer)
    attempt_no: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_sec: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(CallStatus, default="en_cours")
    outcome: Mapped[Optional[str]] = mapped_column(CallOutcome, nullable=True)
    delay_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delay_category: Mapped[Optional[str]] = mapped_column(DelayCategory, nullable=True)
    provider_ref: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    voice_engine_used: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    models_used: Mapped[dict] = mapped_column(JSON, default=dict)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    call_channel_used: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    fallback_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider_connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    estimated_transport_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    dossier: Mapped[Dossier] = relationship(back_populates="calls")
    transcript: Mapped[list["TranscriptTurn"]] = relationship(back_populates="call", order_by="TranscriptTurn.turn_no")


class TranscriptTurn(Base):
    __tablename__ = "transcript_turns"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    call_id: Mapped[str] = mapped_column(String(36), ForeignKey("calls.id"), index=True)
    turn_no: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(Speaker)
    text: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    call: Mapped[Call] = relationship(back_populates="transcript")


class Settings(Base):
    """Une seule ligne (id=1) — paramètres éditables depuis le dashboard.
    id reste un entier (comme Supabase settings.id)."""
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    nb_relances_ia: Mapped[int] = mapped_column(Integer, default=3)
    relance1_min: Mapped[int] = mapped_column(Integer, default=240)
    relance2_min: Mapped[int] = mapped_column(Integer, default=150)
    relance3_min: Mapped[int] = mapped_column(Integer, default=90)
    relance4_min: Mapped[int] = mapped_column(Integer, default=45)
    humain_min: Mapped[int] = mapped_column(Integer, default=60)
    retry_interval_min: Mapped[int] = mapped_column(Integer, default=10)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    call_window_start: Mapped[str] = mapped_column(String(5), default="08:00")
    call_window_end: Mapped[str] = mapped_column(String(5), default="20:00")
    sla_hours: Mapped[float] = mapped_column(Float, default=6.0)
    zineb_whatsapp: Mapped[str] = mapped_column(String(30), default="")
    selected_whatsapp_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    sip_trunk_id: Mapped[str] = mapped_column(String(60), default="")
    sip_caller_id: Mapped[str] = mapped_column(String(30), default="")
    livekit_url: Mapped[str] = mapped_column(String(255), default="")
    livekit_api_key: Mapped[str] = mapped_column(String(120), default="")
    livekit_api_secret: Mapped[str] = mapped_column(String(255), default="")
    openai_api_key: Mapped[str] = mapped_column(String(255), default="")
    vigie_api_base_url: Mapped[str] = mapped_column(String(255), default="")
    agent_max_call_seconds: Mapped[int] = mapped_column(Integer, default=60)
    agent_max_response_tokens: Mapped[int] = mapped_column(Integer, default=200)
    agent_max_turns: Mapped[int] = mapped_column(Integer, default=6)
    voice_engine: Mapped[str] = mapped_column(String(20), default="realtime")
    realtime_model: Mapped[str] = mapped_column(String(120), default="gpt-realtime")
    stt_provider: Mapped[str] = mapped_column(String(40), default="openai")
    stt_model: Mapped[str] = mapped_column(String(120), default="gpt-4o-mini-transcribe")
    stt_language: Mapped[str] = mapped_column(String(20), default="ar")
    llm_model: Mapped[str] = mapped_column(String(120), default="gpt-4o-mini")
    tts_provider: Mapped[str] = mapped_column(String(40), default="openai")
    tts_model: Mapped[str] = mapped_column(String(120), default="gpt-4o-mini-tts")
    tts_voice_id: Mapped[str] = mapped_column(String(120), default="ash")
    m2s_sync_mode: Mapped[str] = mapped_column(String(20), default="disabled")
    m2s_dossiers_api_url: Mapped[str] = mapped_column(String(500), default="")
    m2s_poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    call_channel: Mapped[str] = mapped_column(String(30), default="sip")
    whatsapp_max_attempts: Mapped[int] = mapped_column(Integer, default=2)


class WhatsappContact(Base):
    """Carnet de contacts WhatsApp (superviseurs à notifier au hand-off).
    settings.selected_whatsapp_id pointe vers l'un d'entre eux."""
    __tablename__ = "whatsapp_contacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    label: Mapped[str] = mapped_column(String(60), default="")
    numero: Mapped[str] = mapped_column(String(30), default="")
    whatsapp_token: Mapped[str] = mapped_column(String(255), default="")
    whatsapp_phone_number_id: Mapped[str] = mapped_column(String(60), default="")

class WhatsappAlert(Base):
    """Suivi d'une alerte WhatsApp envoyée lors d'un hand-off humain."""

    __tablename__ = "whatsapp_alerts"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_uuid,
    )

    dossier_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("dossiers.id"),
        unique=True,
        index=True,
    )

    whatsapp_contact_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("whatsapp_contacts.id"),
        nullable=True,
    )

    m2s_message_id: Mapped[str] = mapped_column(
        String(60),
        unique=True,
        index=True,
    )

    instance_id: Mapped[str] = mapped_column(
        String(60),
        default="",
    )

    recipient: Mapped[str] = mapped_column(
        String(30),
        default="",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="accepted",
        index=True,
    )

    failure_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    accepted_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    failed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    last_event_id: Mapped[Optional[str]] = mapped_column(
        String(60),
        nullable=True,
    )

    last_event_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class M2SWebhookEvent(Base):
    """Journal d'idempotence des événements de statut envoyés par M2S."""

    __tablename__ = "m2s_webhook_events"

    event_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(20), default="processing")
    dossier_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
