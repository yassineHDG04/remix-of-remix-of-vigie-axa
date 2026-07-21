-- CHANTIER 2 — M2S est l'unique source de validation d'un dossier.
-- Migration idempotente : configuration live, journal webhook et garde RLS.

ALTER TABLE public.settings
  ADD COLUMN IF NOT EXISTS m2s_sync_mode text NOT NULL DEFAULT 'disabled',
  ADD COLUMN IF NOT EXISTS m2s_dossiers_api_url text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS m2s_poll_interval_seconds integer NOT NULL DEFAULT 300;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'settings_m2s_sync_mode_check'
      AND conrelid = 'public.settings'::regclass
  ) THEN
    ALTER TABLE public.settings
      ADD CONSTRAINT settings_m2s_sync_mode_check
      CHECK (m2s_sync_mode IN ('disabled', 'webhook', 'polling'));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'settings_m2s_poll_interval_check'
      AND conrelid = 'public.settings'::regclass
  ) THEN
    ALTER TABLE public.settings
      ADD CONSTRAINT settings_m2s_poll_interval_check
      CHECK (m2s_poll_interval_seconds BETWEEN 30 AND 86400);
  END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS public.m2s_webhook_events (
  event_id text PRIMARY KEY,
  payload_sha256 text NOT NULL CHECK (length(payload_sha256) = 64),
  processing_status text NOT NULL DEFAULT 'processing'
    CHECK (processing_status IN ('processing', 'processed', 'failed')),
  dossier_id uuid REFERENCES public.dossiers(id) ON DELETE SET NULL,
  error_message text,
  received_at timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz
);

GRANT SELECT, INSERT, UPDATE ON public.m2s_webhook_events TO authenticated;
GRANT ALL ON public.m2s_webhook_events TO service_role;
ALTER TABLE public.m2s_webhook_events ENABLE ROW LEVEL SECURITY;

-- Le compte moteur doit posséder role=admin ET l'adresse interne attendue.
-- La service_role native reste admise pour un déploiement Supabase autogéré.
CREATE OR REPLACE FUNCTION public.is_m2s_service_account()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT
    COALESCE(auth.role(), '') = 'service_role'
    OR (
      COALESCE(auth.jwt() ->> 'email', '') = 'moteur@vigie.internal'
      AND public.has_role(auth.uid(), 'admin')
    );
$$;

REVOKE ALL ON FUNCTION public.is_m2s_service_account() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_m2s_service_account() TO authenticated, service_role;

DROP POLICY IF EXISTS m2s_webhook_events_service_all ON public.m2s_webhook_events;
CREATE POLICY m2s_webhook_events_service_all
  ON public.m2s_webhook_events
  FOR ALL
  TO authenticated
  USING (public.is_m2s_service_account())
  WITH CHECK (public.is_m2s_service_account());

-- Claim atomique : un événement traité est ignoré ; un événement en échec peut
-- être rejoué uniquement avec exactement le même corps.
CREATE OR REPLACE FUNCTION public.claim_m2s_webhook_event(
  p_event_id text,
  p_payload_sha256 text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
  v_rows integer;
BEGIN
  INSERT INTO public.m2s_webhook_events(event_id, payload_sha256)
  VALUES (p_event_id, p_payload_sha256)
  ON CONFLICT (event_id) DO NOTHING;

  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows = 1 THEN
    RETURN true;
  END IF;

  UPDATE public.m2s_webhook_events
  SET processing_status = 'processing', error_message = NULL, processed_at = NULL,
      received_at = now()
  WHERE event_id = p_event_id
    AND payload_sha256 = p_payload_sha256
    AND (
      processing_status = 'failed'
      OR (processing_status = 'processing' AND received_at < now() - interval '5 minutes')
    );

  GET DIAGNOSTICS v_rows = ROW_COUNT;
  RETURN v_rows = 1;
END;
$$;

REVOKE ALL ON FUNCTION public.claim_m2s_webhook_event(text, text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.claim_m2s_webhook_event(text, text)
  TO authenticated, service_role;

-- Permet à un utilisateur autorisé de modifier les informations d'un dossier
-- déjà validé sans lui donner le droit de créer la transition vers "valide".
CREATE OR REPLACE FUNCTION public.dossier_was_already_validated(p_dossier_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT COALESCE((
    SELECT d.status = 'valide'::public.dossier_status
    FROM public.dossiers d
    WHERE d.id = p_dossier_id
  ), false);
$$;

REVOKE ALL ON FUNCTION public.dossier_was_already_validated(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.dossier_was_already_validated(uuid)
  TO authenticated, service_role;

DROP POLICY IF EXISTS dossiers_insert_roles ON public.dossiers;
DROP POLICY IF EXISTS dossiers_update_roles ON public.dossiers;
DROP POLICY IF EXISTS dossiers_write_auth ON public.dossiers;
DROP POLICY IF EXISTS dossiers_update_auth ON public.dossiers;

CREATE POLICY dossiers_insert_roles
  ON public.dossiers FOR INSERT TO authenticated
  WITH CHECK (
    (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'))
    AND (
      status <> 'valide'::public.dossier_status
      OR public.is_m2s_service_account()
    )
  );

CREATE POLICY dossiers_update_roles
  ON public.dossiers FOR UPDATE TO authenticated
  USING (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'))
  WITH CHECK (
    (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'))
    AND (
      status <> 'valide'::public.dossier_status
      OR public.dossier_was_already_validated(id)
      OR public.is_m2s_service_account()
    )
  );

-- Le trigger complète la policy RLS et bloque la transition même si une autre
-- policy permissive était ajoutée ultérieurement par erreur.
CREATE OR REPLACE FUNCTION public.guard_dossier_validation_from_m2s()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NEW.status = 'valide'::public.dossier_status
     AND OLD.status IS DISTINCT FROM NEW.status
     AND NOT public.is_m2s_service_account() THEN
    RAISE EXCEPTION
      'Validation interdite dans Vigie : le statut valide doit provenir de M2S.'
      USING ERRCODE = '42501';
  END IF;
  RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.guard_dossier_validation_from_m2s() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS trg_dossiers_validation_m2s_only ON public.dossiers;
CREATE TRIGGER trg_dossiers_validation_m2s_only
  BEFORE UPDATE OF status ON public.dossiers
  FOR EACH ROW
  EXECUTE FUNCTION public.guard_dossier_validation_from_m2s();

COMMENT ON TABLE public.m2s_webhook_events IS
  'Journal idempotent des événements de statut reçus de la plateforme M2S.';
COMMENT ON COLUMN public.settings.m2s_sync_mode IS
  'disabled, webhook ou polling ; pilotable depuis le dashboard Vigie.';
