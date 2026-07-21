import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect as _sa_inspect

from .config import config
from .database import Base, engine
from .engine import engine_loop
from .providers.autodossier import auto_dossier_loop
from .providers.m2s import m2s_poll_loop
from .routers import (
    calls,
    dossiers,
    engine_router,
    kpi,
    m2s_webhook,
    m2s_whatsapp_webhook,
    settings,
    whatsapp_webhook,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("vigie.main")

IS_SQLITE = config.database_url.startswith("sqlite")
USE_LOCAL_SQL = IS_SQLITE and not config.use_supabase  # SqlRepo local

app = FastAPI(
    title="Vigie — Backend métier",
    description="Relance vocale IA & escalade des dossiers en retard (m2s Maroc). "
                "Mode MOCK par défaut : les appels sont simulés. "
                "Swagger interactif ci-dessous pour tester chaque endpoint.",
    version="0.3.0",
)

# CORS : "*" en prototype ; en prod, mettre le domaine du frontend dans CORS_ORIGINS.
_origins = [o.strip() for o in config.cors_origins.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"])

app.include_router(dossiers.router)
app.include_router(calls.router)
app.include_router(settings.router)
app.include_router(engine_router.router)
app.include_router(kpi.router)
app.include_router(whatsapp_webhook.router)
app.include_router(m2s_whatsapp_webhook.router)
app.include_router(m2s_webhook.router)

@app.get("/", tags=["santé"])
def health():
    return {
        "service": "vigie-backend",
        "mock_mode": config.mock_mode,
        "data_layer": "supabase" if config.use_supabase else ("sqlite" if IS_SQLITE else "sql"),
        "m2s_poll_enabled": config.m2s_poll_enabled,
        "m2s_webhook_signature_configured": bool(config.m2s_webhook_secret),
        "auto_dossier_enabled": config.auto_dossier_enabled,
        "api_auth_configured": bool(config.vigie_api_key),
        "whatsapp_signature_configured": bool(config.whatsapp_app_secret),
        "whatsapp_calling_enabled": config.whatsapp_calls_enabled,
        "whatsapp_calling_configured": bool(
            config.whatsapp_calls_access_token and config.whatsapp_calls_phone_number_id
        ),
        "docs": "/docs",
    }


def ensure_settings_schema():
    """SQLite uniquement : ajoute les colonnes manquantes sur une base existante
    (create_all ne modifie pas une table déjà créée, ni ne crée les toutes
    nouvelles tables comme whatsapp_contacts si la base existe déjà)."""
    insp = _sa_inspect(engine)
    tables = insp.get_table_names()

    if "settings" in tables:
        cols = {c["name"] for c in insp.get_columns("settings")}
        with engine.begin() as conn:
            if "nb_relances_ia" not in cols:
                conn.exec_driver_sql("ALTER TABLE settings ADD COLUMN nb_relances_ia INTEGER DEFAULT 3")
            if "relance4_min" not in cols:
                conn.exec_driver_sql("ALTER TABLE settings ADD COLUMN relance4_min INTEGER DEFAULT 45")
            if "selected_whatsapp_id" not in cols:
                conn.exec_driver_sql("ALTER TABLE settings ADD COLUMN selected_whatsapp_id VARCHAR(36)")
            if "sip_trunk_id" not in cols:
                conn.exec_driver_sql("ALTER TABLE settings ADD COLUMN sip_trunk_id VARCHAR(60) DEFAULT ''")
            if "sip_caller_id" not in cols:
                conn.exec_driver_sql("ALTER TABLE settings ADD COLUMN sip_caller_id VARCHAR(30) DEFAULT ''")
            for col, ddl in [
                ("livekit_url", "VARCHAR(255)"), ("livekit_api_key", "VARCHAR(120)"),
                ("livekit_api_secret", "VARCHAR(255)"), ("openai_api_key", "VARCHAR(255)"),
                ("vigie_api_base_url", "VARCHAR(255)"),
            ]:
                if col not in cols:
                    conn.exec_driver_sql(f"ALTER TABLE settings ADD COLUMN {col} {ddl} DEFAULT ''")
            for col, default in [
                ("agent_max_call_seconds", 60), ("agent_max_response_tokens", 200), ("agent_max_turns", 6),
                ("m2s_poll_interval_seconds", 300),
                ("whatsapp_max_attempts", 2),
            ]:
                if col not in cols:
                    conn.exec_driver_sql(f"ALTER TABLE settings ADD COLUMN {col} INTEGER DEFAULT {default}")
            if "m2s_sync_mode" not in cols:
                conn.exec_driver_sql("ALTER TABLE settings ADD COLUMN m2s_sync_mode VARCHAR(20) DEFAULT 'disabled'")
            if "m2s_dossiers_api_url" not in cols:
                conn.exec_driver_sql("ALTER TABLE settings ADD COLUMN m2s_dossiers_api_url VARCHAR(500) DEFAULT ''")
            if "call_channel" not in cols:
                conn.exec_driver_sql(
                    "ALTER TABLE settings ADD COLUMN call_channel VARCHAR(30) DEFAULT 'sip'"
                )
            for col, ddl, default in [
                ("voice_engine", "VARCHAR(20)", "realtime"),
                ("realtime_model", "VARCHAR(120)", "gpt-realtime"),
                ("stt_provider", "VARCHAR(40)", "openai"),
                ("stt_model", "VARCHAR(120)", "gpt-4o-mini-transcribe"),
                ("stt_language", "VARCHAR(20)", "ar"),
                ("llm_model", "VARCHAR(120)", "gpt-4o-mini"),
                ("tts_provider", "VARCHAR(40)", "openai"),
                ("tts_model", "VARCHAR(120)", "gpt-4o-mini-tts"),
                ("tts_voice_id", "VARCHAR(120)", "ash"),
            ]:
                if col not in cols:
                    conn.exec_driver_sql(
                        f"ALTER TABLE settings ADD COLUMN {col} {ddl} DEFAULT '{default}'"
                    )

    if "dossiers" in tables:
        cols = {c["name"] for c in insp.get_columns("dossiers")}
        with engine.begin() as conn:
            for col, ddl in [
                ("matricule", "VARCHAR(60)"), ("num_tel_client", "VARCHAR(30)"),
                ("nom_assurance", "VARCHAR(120)"), ("adresse", "VARCHAR(255)"),
                ("zone", "VARCHAR(60)"), ("assure", "VARCHAR(120)"), ("vehicule", "VARCHAR(120)"),
            ]:
                if col not in cols:
                    conn.exec_driver_sql(f"ALTER TABLE dossiers ADD COLUMN {col} {ddl} DEFAULT ''")
            if "date_sinistre" not in cols:
                conn.exec_driver_sql("ALTER TABLE dossiers ADD COLUMN date_sinistre DATETIME")

    if "calls" in tables:
        cols = {c["name"] for c in insp.get_columns("calls")}
        with engine.begin() as conn:
            if "voice_engine_used" not in cols:
                conn.exec_driver_sql("ALTER TABLE calls ADD COLUMN voice_engine_used VARCHAR(20)")
            if "models_used" not in cols:
                conn.exec_driver_sql("ALTER TABLE calls ADD COLUMN models_used JSON DEFAULT '{}'")
            if "estimated_cost_usd" not in cols:
                conn.exec_driver_sql("ALTER TABLE calls ADD COLUMN estimated_cost_usd FLOAT DEFAULT 0")
            if "call_channel_used" not in cols:
                conn.exec_driver_sql("ALTER TABLE calls ADD COLUMN call_channel_used VARCHAR(20)")
            if "fallback_reason" not in cols:
                conn.exec_driver_sql("ALTER TABLE calls ADD COLUMN fallback_reason TEXT")
            if "provider_connected_at" not in cols:
                conn.exec_driver_sql("ALTER TABLE calls ADD COLUMN provider_connected_at DATETIME")
            if "estimated_transport_cost_usd" not in cols:
                conn.exec_driver_sql(
                    "ALTER TABLE calls ADD COLUMN estimated_transport_cost_usd FLOAT DEFAULT 0"
                )

    if "whatsapp_contacts" not in tables:
        # Table toute nouvelle : create_all() (appelé juste avant) l'a déjà créée
        # si le modèle WhatsappContact est importé -- rien à faire ici.
        pass


@app.on_event("startup")
async def on_startup():
    if not config.vigie_api_key:
        log.error(
            "VIGIE_API_KEY absente : les routes dossiers, appels, paramètres, "
            "KPI et moteur resteront verrouillées."
        )
    if not config.whatsapp_app_secret:
        log.warning("WHATSAPP_APP_SECRET absent : les webhooks WhatsApp POST seront rejetés.")

    if config.use_supabase:
        log.info("Couche données : Supabase (API service role). Schéma géré par Supabase.")
    elif USE_LOCAL_SQL:
        # Dev/mock : on possède le schéma localement (SQLite).
        from . import models  # noqa: F401  (enregistre les tables sur Base.metadata)
        Base.metadata.create_all(bind=engine)
        ensure_settings_schema()
        log.info("Couche données : SQLite locale (dev/mock).")
    else:
        log.info("Couche données : SQL (%s), schéma non géré ici.", config.database_url.split(":")[0])

    if config.engine_autostart:
        asyncio.create_task(engine_loop())
    # Toujours lancé : la page /parametres peut activer/désactiver le polling
    # à chaud sans redémarrer le backend.
    asyncio.create_task(m2s_poll_loop())
    if config.auto_dossier_enabled:
        asyncio.create_task(auto_dossier_loop())
