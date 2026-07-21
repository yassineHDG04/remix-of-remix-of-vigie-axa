-- ============================================================================
-- M2S / VIGIE - Schéma SQL v2 recommandé
-- Cible : PostgreSQL 14+ / Supabase PostgreSQL
-- Objectif : normaliser dossiers, constateurs, appels, handoffs et transcriptions
-- ============================================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Fonctions techniques
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION set_dossier_deadline()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.deadline_at := NEW.arrival_at + (NEW.sla_minutes * interval '1 minute');
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION set_call_duration()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.started_at IS NOT NULL AND NEW.ended_at IS NOT NULL THEN
        NEW.duration_sec := GREATEST(
            0,
            FLOOR(EXTRACT(EPOCH FROM (NEW.ended_at - NEW.started_at)))::integer
        );
    ELSE
        NEW.duration_sec := 0;
    END IF;

    RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- Référentiels
-- Les codes sont stables pour l'API ; les libellés peuvent évoluer côté UI.
-- ---------------------------------------------------------------------------

CREATE TABLE ref_dossier_statuses (
    code        varchar(30) PRIMARY KEY,
    libelle     varchar(100) NOT NULL,
    is_terminal boolean NOT NULL DEFAULT false,
    actif       boolean NOT NULL DEFAULT true
);

INSERT INTO ref_dossier_statuses (code, libelle, is_terminal) VALUES
    ('nouveau',     'Nouveau', false),
    ('en_cours',    'En cours', false),
    ('en_attente',  'En attente', false),
    ('handoff',     'Intervention humaine', false),
    ('valide',      'Validé', true),
    ('annule',      'Annulé', true),
    ('erreur',      'Erreur', true)
ON CONFLICT (code) DO NOTHING;

CREATE TABLE ref_call_statuses (
    code    varchar(30) PRIMARY KEY,
    libelle varchar(100) NOT NULL,
    actif   boolean NOT NULL DEFAULT true
);

INSERT INTO ref_call_statuses (code, libelle) VALUES
    ('planifie',    'Planifié'),
    ('en_cours',    'En cours'),
    ('pris',        'Appel pris'),
    ('repondeur',   'Répondeur'),
    ('non_repondu', 'Sans réponse'),
    ('echec',       'Échec technique'),
    ('annule',      'Annulé')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE ref_call_outcomes (
    code    varchar(40) PRIMARY KEY,
    libelle varchar(120) NOT NULL,
    actif   boolean NOT NULL DEFAULT true
);

INSERT INTO ref_call_outcomes (code, libelle) VALUES
    ('cause_captee',     'Cause du retard captée'),
    ('non_joignable',    'Constateur non joignable'),
    ('rappel_demande',   'Rappel demandé'),
    ('aucune_cause',     'Aucune cause exploitable'),
    ('transfert_humain', 'Transfert vers un humain')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE ref_delay_categories (
    code        varchar(50) PRIMARY KEY,
    libelle     varchar(150) NOT NULL,
    description text,
    actif       boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

INSERT INTO ref_delay_categories (code, libelle) VALUES
    ('desaccord_parties', 'Désaccord entre les parties'),
    ('zone_hors_km',      'Zone hors kilométrage')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE ref_handoff_reasons (
    code    varchar(50) PRIMARY KEY,
    libelle varchar(150) NOT NULL,
    actif   boolean NOT NULL DEFAULT true
);

INSERT INTO ref_handoff_reasons (code, libelle) VALUES
    ('seuil_1h',             'Seuil d’une heure atteint'),
    ('tentatives_epuisees',  'Nombre de tentatives épuisé'),
    ('demande_constateur',   'Intervention humaine demandée par le constateur'),
    ('erreur_technique',     'Erreur technique'),
    ('autre',                'Autre motif')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE assurances (
    id         smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code       varchar(40) NOT NULL UNIQUE,
    nom        varchar(120) NOT NULL UNIQUE,
    actif      boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO assurances (code, nom) VALUES
    ('WAFA_ASSURANCE',  'Wafa Assurance'),
    ('RMA',             'RMA'),
    ('SANLAM_MAROC',    'Sanlam Maroc'),
    ('AXA_MAROC',       'AXA Maroc'),
    ('ATLANTASANAD',    'AtlantaSanad'),
    ('ALLIANZ_MAROC',   'Allianz Maroc'),
    ('MAROCAINE_VIE',   'La Marocaine Vie')
ON CONFLICT (code) DO NOTHING;

CREATE TRIGGER trg_assurances_updated_at
BEFORE UPDATE ON assurances
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE villes (
    id            smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nom           varchar(120) NOT NULL,
    nom_normalise varchar(120) NOT NULL,
    actif         boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_villes_nom_normalise UNIQUE (nom_normalise)
);

-- Valeurs déjà observées dans les données. Compléter avec le référentiel national.
INSERT INTO villes (nom, nom_normalise) VALUES
    ('Casablanca', 'casablanca'),
    ('Rabat',      'rabat'),
    ('Marrakech',  'marrakech'),
    ('Tanger',     'tanger'),
    ('Agadir',     'agadir'),
    ('Fès',        'fes')
ON CONFLICT (nom_normalise) DO NOTHING;

CREATE TABLE workflow_stages (
    id          smallint PRIMARY KEY,
    code        varchar(40) NOT NULL UNIQUE,
    libelle     varchar(120) NOT NULL,
    ordre       smallint NOT NULL UNIQUE,
    actif       boolean NOT NULL DEFAULT true,
    CONSTRAINT chk_workflow_stage_positive CHECK (id > 0 AND ordre > 0)
);

-- Libellés génériques à renommer selon le workflow métier exact.
INSERT INTO workflow_stages (id, code, libelle, ordre) VALUES
    (1, 'ETAPE_1', 'Étape 1', 1),
    (2, 'ETAPE_2', 'Étape 2', 2),
    (3, 'ETAPE_3', 'Étape 3', 3)
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Constateurs
-- Le téléphone est stocké une seule fois ici, jamais recopié dans dossiers.
-- ---------------------------------------------------------------------------

CREATE TABLE constateurs (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    nom                varchar(160) NOT NULL,
    telephone_e164     varchar(20) NOT NULL,
    zone_principale_id smallint REFERENCES villes(id) ON DELETE SET NULL,
    external_ref       varchar(100),
    actif              boolean NOT NULL DEFAULT true,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_constateurs_telephone UNIQUE (telephone_e164),
    CONSTRAINT chk_constateurs_telephone_e164
        CHECK (telephone_e164 ~ '^\+[1-9][0-9]{7,14}$')
);

CREATE INDEX idx_constateurs_nom ON constateurs (lower(nom));
CREATE INDEX idx_constateurs_zone ON constateurs (zone_principale_id);

CREATE TRIGGER trg_constateurs_updated_at
BEFORE UPDATE ON constateurs
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- Dossiers
-- arrival_at = date de réception par M2S
-- date_sinistre = date/heure réelle du sinistre fournie par l'API
-- ---------------------------------------------------------------------------

CREATE TABLE dossiers (
    id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Références
    ref_m2s                   varchar(80) NOT NULL,
    ref_sinistre              varchar(120) NOT NULL,

    -- Données reçues de l'API
    nom_assure                varchar(200) NOT NULL,
    vehicule                  varchar(255),
    matricule                 varchar(30),
    lieu_sinistre             text NOT NULL,
    ville_id                  smallint REFERENCES villes(id) ON DELETE SET NULL,
    date_sinistre             timestamptz NOT NULL,
    assurance_id              smallint NOT NULL REFERENCES assurances(id),
    constateur_id             uuid NOT NULL REFERENCES constateurs(id),
    telephone_assure          varchar(20),

    -- Pilotage SLA / workflow
    arrival_at                timestamptz NOT NULL DEFAULT now(),
    sla_minutes               integer NOT NULL DEFAULT 360,
    deadline_at               timestamptz NOT NULL,
    status_code               varchar(30) NOT NULL DEFAULT 'nouveau'
                              REFERENCES ref_dossier_statuses(code),
    current_stage_id          smallint REFERENCES workflow_stages(id),
    validated_at              timestamptz,
    final_delay_category_code varchar(50)
                              REFERENCES ref_delay_categories(code),

    -- Audit de la source API
    api_received_at           timestamptz NOT NULL DEFAULT now(),
    api_payload               jsonb,

    created_at                timestamptz NOT NULL DEFAULT now(),
    updated_at                timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_dossiers_ref_m2s UNIQUE (ref_m2s),
    -- Une référence sinistre peut théoriquement se répéter chez deux assureurs.
    CONSTRAINT uq_dossiers_assurance_ref_sinistre
        UNIQUE (assurance_id, ref_sinistre),
    CONSTRAINT chk_dossiers_sla_positive CHECK (sla_minutes > 0),
    CONSTRAINT chk_dossiers_deadline_order CHECK (deadline_at >= arrival_at),
    CONSTRAINT chk_dossiers_validation
        CHECK (validated_at IS NULL OR status_code = 'valide'),
    CONSTRAINT chk_dossiers_telephone_assure
        CHECK (telephone_assure IS NULL OR telephone_assure ~ '^\+[1-9][0-9]{7,14}$')
);

CREATE INDEX idx_dossiers_ref_sinistre ON dossiers (ref_sinistre);
CREATE INDEX idx_dossiers_status_deadline ON dossiers (status_code, deadline_at);
CREATE INDEX idx_dossiers_constateur ON dossiers (constateur_id);
CREATE INDEX idx_dossiers_assurance ON dossiers (assurance_id);
CREATE INDEX idx_dossiers_ville ON dossiers (ville_id);
CREATE INDEX idx_dossiers_validated_at ON dossiers (validated_at DESC)
    WHERE status_code = 'valide';
CREATE INDEX idx_dossiers_actifs_deadline ON dossiers (deadline_at)
    WHERE status_code IN ('nouveau', 'en_cours', 'en_attente', 'handoff');

CREATE TRIGGER trg_dossiers_set_deadline
BEFORE INSERT OR UPDATE OF arrival_at, sla_minutes ON dossiers
FOR EACH ROW EXECUTE FUNCTION set_dossier_deadline();

CREATE TRIGGER trg_dossiers_updated_at
BEFORE UPDATE ON dossiers
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- État par étape
-- Remplace stage_attempts, stage_answered et next_action_at dans dossiers.
-- ---------------------------------------------------------------------------

CREATE TABLE dossier_stage_states (
    dossier_id     uuid NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    stage_id       smallint NOT NULL REFERENCES workflow_stages(id),
    attempts_count smallint NOT NULL DEFAULT 0,
    answered       boolean NOT NULL DEFAULT false,
    next_action_at timestamptz,
    last_call_at   timestamptz,
    completed_at   timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (dossier_id, stage_id),
    CONSTRAINT chk_stage_state_attempts CHECK (attempts_count >= 0)
);

CREATE INDEX idx_stage_states_next_action
    ON dossier_stage_states (next_action_at)
    WHERE completed_at IS NULL AND next_action_at IS NOT NULL;

CREATE TRIGGER trg_stage_states_updated_at
BEFORE UPDATE ON dossier_stage_states
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- Appels
-- duration_sec est recalculé automatiquement à partir des timestamps.
-- ---------------------------------------------------------------------------

CREATE TABLE calls (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id          uuid NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    stage_id            smallint NOT NULL REFERENCES workflow_stages(id),
    attempt_no          smallint NOT NULL,
    started_at          timestamptz NOT NULL,
    ended_at            timestamptz,
    duration_sec        integer NOT NULL DEFAULT 0,
    status_code         varchar(30) NOT NULL REFERENCES ref_call_statuses(code),
    outcome_code        varchar(40) REFERENCES ref_call_outcomes(code),
    delay_reason        text,
    delay_category_code varchar(50) REFERENCES ref_delay_categories(code),
    provider_name       varchar(80),
    provider_ref        varchar(255),
    provider_payload    jsonb,
    recording_url       text,
    created_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_calls_attempt UNIQUE (dossier_id, stage_id, attempt_no),
    CONSTRAINT uq_calls_provider_ref UNIQUE (provider_ref),
    CONSTRAINT chk_calls_attempt_positive CHECK (attempt_no > 0),
    CONSTRAINT chk_calls_duration_positive CHECK (duration_sec >= 0),
    CONSTRAINT chk_calls_time_order
        CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE INDEX idx_calls_dossier_started
    ON calls (dossier_id, started_at DESC);
CREATE INDEX idx_calls_stage_status
    ON calls (stage_id, status_code);
CREATE INDEX idx_calls_delay_category
    ON calls (delay_category_code)
    WHERE delay_category_code IS NOT NULL;

CREATE TRIGGER trg_calls_set_duration
BEFORE INSERT OR UPDATE OF started_at, ended_at ON calls
FOR EACH ROW EXECUTE FUNCTION set_call_duration();

-- Synchronise l'état agrégé d'une étape depuis l'historique immutable des appels.
CREATE OR REPLACE FUNCTION upsert_dossier_stage_state_from_calls(
    p_dossier_id uuid,
    p_stage_id smallint
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO dossier_stage_states (
        dossier_id,
        stage_id,
        attempts_count,
        answered,
        last_call_at
    )
    SELECT
        p_dossier_id,
        p_stage_id,
        COALESCE(MAX(c.attempt_no), 0)::smallint,
        COALESCE(BOOL_OR(c.status_code = 'pris'), false),
        MAX(c.started_at)
    FROM calls c
    WHERE c.dossier_id = p_dossier_id
      AND c.stage_id = p_stage_id
    ON CONFLICT (dossier_id, stage_id)
    DO UPDATE SET
        attempts_count = EXCLUDED.attempts_count,
        answered       = EXCLUDED.answered,
        last_call_at   = EXCLUDED.last_call_at,
        updated_at     = now();
END;
$$;

CREATE OR REPLACE FUNCTION refresh_dossier_stage_state_from_calls()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM upsert_dossier_stage_state_from_calls(OLD.dossier_id, OLD.stage_id);
        RETURN OLD;
    END IF;

    IF TG_OP = 'UPDATE'
       AND (
           NEW.dossier_id IS DISTINCT FROM OLD.dossier_id
           OR NEW.stage_id IS DISTINCT FROM OLD.stage_id
       ) THEN
        -- Nettoie aussi l'ancien couple dossier/étape si un appel a été déplacé.
        PERFORM upsert_dossier_stage_state_from_calls(OLD.dossier_id, OLD.stage_id);
    END IF;

    PERFORM upsert_dossier_stage_state_from_calls(NEW.dossier_id, NEW.stage_id);
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_calls_refresh_stage_state
AFTER INSERT OR DELETE OR UPDATE OF dossier_id, stage_id, attempt_no, status_code ON calls
FOR EACH ROW EXECUTE FUNCTION refresh_dossier_stage_state_from_calls();

-- ---------------------------------------------------------------------------
-- Escalades / handoffs
-- Une table dédiée conserve l'historique au lieu d'écraser un seul motif.
-- acknowledged_by doit être relié à votre table users/auth.users selon l'auth.
-- ---------------------------------------------------------------------------

CREATE TABLE dossier_handoffs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id          uuid NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    stage_id            smallint REFERENCES workflow_stages(id),
    reason_code         varchar(50) NOT NULL REFERENCES ref_handoff_reasons(code),
    details             text,
    triggered_at        timestamptz NOT NULL DEFAULT now(),
    acknowledged_at     timestamptz,
    acknowledged_by     uuid,
    acknowledgment_note text,
    created_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_handoff_acknowledgment
        CHECK (
            (acknowledged_at IS NULL AND acknowledged_by IS NULL)
            OR acknowledged_at IS NOT NULL
        )
);

CREATE INDEX idx_handoffs_pending
    ON dossier_handoffs (triggered_at)
    WHERE acknowledged_at IS NULL;
CREATE INDEX idx_handoffs_dossier
    ON dossier_handoffs (dossier_id, triggered_at DESC);

-- ---------------------------------------------------------------------------
-- Transcriptions
-- ---------------------------------------------------------------------------

CREATE TABLE transcript_turns (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id     uuid NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
    turn_no     smallint NOT NULL,
    speaker     varchar(30) NOT NULL,
    text        text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    metadata    jsonb,

    CONSTRAINT uq_transcript_turn UNIQUE (call_id, turn_no),
    CONSTRAINT chk_transcript_turn_positive CHECK (turn_no > 0),
    CONSTRAINT chk_transcript_speaker
        CHECK (speaker IN ('ia', 'constateur', 'client', 'humain', 'systeme'))
);

CREATE INDEX idx_transcript_call_turn
    ON transcript_turns (call_id, turn_no);

-- ---------------------------------------------------------------------------
-- Vues prêtes pour le frontend
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_dossier_details AS
SELECT
    d.id,
    d.ref_m2s,
    d.ref_sinistre,
    d.nom_assure AS assure,
    d.vehicule,
    d.matricule,
    d.lieu_sinistre,
    v.nom AS zone,
    d.date_sinistre,
    a.nom AS assurance,
    c.id AS constateur_id,
    c.nom AS constateur,
    c.telephone_e164 AS num_tel_constateur,
    d.arrival_at,
    d.sla_minutes,
    d.deadline_at,
    d.status_code AS status,
    d.current_stage_id,
    d.validated_at,
    d.final_delay_category_code AS final_category,
    d.created_at,
    d.updated_at
FROM dossiers d
JOIN assurances a ON a.id = d.assurance_id
JOIN constateurs c ON c.id = d.constateur_id
LEFT JOIN villes v ON v.id = d.ville_id;

CREATE OR REPLACE VIEW v_dossiers_valides AS
SELECT
    d.id,
    d.ref_sinistre,
    d.nom_assure AS assure,
    a.nom AS assurance,
    d.matricule,
    d.lieu_sinistre,
    d.validated_at
FROM dossiers d
JOIN assurances a ON a.id = d.assurance_id
WHERE d.status_code = 'valide';

COMMENT ON VIEW v_dossier_details IS
'Vue pour /detail-dossier : données API + constateur joint par clé étrangère.';

COMMENT ON VIEW v_dossiers_valides IS
'Vue pour /dossiers-valides : Ref_sinistre, assuré, assurance, matricule, lieu_sinistre, validé le.';

COMMIT;
