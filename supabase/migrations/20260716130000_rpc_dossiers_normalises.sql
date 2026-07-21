-- TP 5/6 — écritures transactionnelles après normalisation des dossiers.
-- Prérequis : tables clients, vehicules, assurances, sinistres,
-- dossiers.sinistre_id et vue v_dossiers_complets créées pendant les TP 1 à 4.

DO $$
BEGIN
  IF to_regclass('public.clients') IS NULL
     OR to_regclass('public.vehicules') IS NULL
     OR to_regclass('public.assurances') IS NULL
     OR to_regclass('public.sinistres') IS NULL
     OR to_regclass('public.v_dossiers_complets') IS NULL THEN
    RAISE EXCEPTION
      'TP 1 à 4 incomplets : clients, vehicules, assurances, sinistres et v_dossiers_complets sont requis.';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'dossiers'
      AND column_name = 'sinistre_id'
  ) THEN
    RAISE EXCEPTION 'TP 2 incomplet : public.dossiers.sinistre_id est requis.';
  END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Création atomique d'un sinistre + dossier.
-- Utilisée par le backend M2S et par l'import CSV du frontend.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.create_dossier_normalise(
  p_ref_m2s text,
  p_constateur_id uuid,
  p_dossier_id uuid DEFAULT NULL,
  p_arrival_at timestamptz DEFAULT now(),
  p_sla_hours double precision DEFAULT 24,
  p_deadline_at timestamptz DEFAULT NULL,
  p_status text DEFAULT 'en_retard',
  p_current_stage integer DEFAULT 0,
  p_validated_at timestamptz DEFAULT NULL,
  p_final_category text DEFAULT NULL,
  p_assure text DEFAULT '',
  p_num_tel_client text DEFAULT '',
  p_matricule text DEFAULT '',
  p_vehicule text DEFAULT '',
  p_nom_assurance text DEFAULT '',
  p_adresse text DEFAULT '',
  p_zone text DEFAULT '',
  p_date_sinistre timestamptz DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
  v_dossier_id uuid;
  v_sinistre_id uuid;
  v_client_id uuid;
  v_vehicule_id uuid;
  v_assurance_id uuid;
  v_phone_normalise text;
  v_matricule_normalisee text;
  v_arrival_at timestamptz := COALESCE(p_arrival_at, now());
  v_sla_hours integer := GREATEST(1, round(COALESCE(p_sla_hours, 24))::integer);
BEGIN
  IF btrim(COALESCE(p_ref_m2s, '')) = '' THEN
    RAISE EXCEPTION 'La référence M2S est obligatoire.';
  END IF;

  -- Idempotence : une référence déjà importée renvoie son dossier existant.
  SELECT d.id
  INTO v_dossier_id
  FROM public.sinistres s
  JOIN public.dossiers d ON d.sinistre_id = s.id
  WHERE s.ref_m2s = btrim(p_ref_m2s)
  LIMIT 1;

  IF v_dossier_id IS NOT NULL THEN
    RETURN v_dossier_id;
  END IF;

  -- Client : réutilisation par numéro normalisé quand il est disponible.
  v_phone_normalise := regexp_replace(COALESCE(p_num_tel_client, ''), '[^0-9+]', '', 'g');
  IF v_phone_normalise <> '' THEN
    SELECT id INTO v_client_id
    FROM public.clients
    WHERE regexp_replace(telephone, '[^0-9+]', '', 'g') = v_phone_normalise
    LIMIT 1;
  END IF;

  IF v_client_id IS NULL
     AND (btrim(COALESCE(p_assure, '')) <> '' OR v_phone_normalise <> '') THEN
    BEGIN
      INSERT INTO public.clients(nom, telephone)
      VALUES (COALESCE(p_assure, ''), COALESCE(p_num_tel_client, ''))
      RETURNING id INTO v_client_id;
    EXCEPTION WHEN unique_violation THEN
      SELECT id INTO v_client_id
      FROM public.clients
      WHERE regexp_replace(telephone, '[^0-9+]', '', 'g') = v_phone_normalise
      LIMIT 1;
    END;
  ELSIF v_client_id IS NOT NULL THEN
    UPDATE public.clients
    SET
      nom = CASE
        WHEN btrim(COALESCE(p_assure, '')) <> '' THEN p_assure
        ELSE nom
      END,
      telephone = CASE
        WHEN v_phone_normalise <> '' THEN p_num_tel_client
        ELSE telephone
      END
    WHERE id = v_client_id;
  END IF;

  -- Véhicule : réutilisation par matricule normalisée.
  v_matricule_normalisee := upper(
    regexp_replace(COALESCE(p_matricule, ''), '[[:space:]-]', '', 'g')
  );
  IF v_matricule_normalisee <> '' THEN
    SELECT id INTO v_vehicule_id
    FROM public.vehicules
    WHERE upper(regexp_replace(matricule, '[[:space:]-]', '', 'g')) = v_matricule_normalisee
    LIMIT 1;
  END IF;

  IF v_vehicule_id IS NULL
     AND (btrim(COALESCE(p_vehicule, '')) <> '' OR v_matricule_normalisee <> '') THEN
    BEGIN
      INSERT INTO public.vehicules(matricule, description)
      VALUES (COALESCE(p_matricule, ''), COALESCE(p_vehicule, ''))
      RETURNING id INTO v_vehicule_id;
    EXCEPTION WHEN unique_violation THEN
      SELECT id INTO v_vehicule_id
      FROM public.vehicules
      WHERE upper(regexp_replace(matricule, '[[:space:]-]', '', 'g')) = v_matricule_normalisee
      LIMIT 1;
    END;
  ELSIF v_vehicule_id IS NOT NULL THEN
    UPDATE public.vehicules
    SET
      matricule = CASE
        WHEN v_matricule_normalisee <> '' THEN p_matricule
        ELSE matricule
      END,
      description = CASE
        WHEN btrim(COALESCE(p_vehicule, '')) <> '' THEN p_vehicule
        ELSE description
      END
    WHERE id = v_vehicule_id;
  END IF;

  -- Assurance : référentiel insensible à la casse et aux espaces externes.
  IF btrim(COALESCE(p_nom_assurance, '')) <> '' THEN
    SELECT id INTO v_assurance_id
    FROM public.assurances
    WHERE lower(btrim(nom)) = lower(btrim(p_nom_assurance))
    LIMIT 1;

    IF v_assurance_id IS NULL THEN
      BEGIN
        INSERT INTO public.assurances(nom)
        VALUES (btrim(p_nom_assurance))
        RETURNING id INTO v_assurance_id;
      EXCEPTION WHEN unique_violation THEN
        SELECT id INTO v_assurance_id
        FROM public.assurances
        WHERE lower(btrim(nom)) = lower(btrim(p_nom_assurance))
        LIMIT 1;
      END;
    END IF;
  END IF;

  v_sinistre_id := gen_random_uuid();
  v_dossier_id := COALESCE(p_dossier_id, gen_random_uuid());

  INSERT INTO public.sinistres(
    id, ref_m2s, client_id, vehicule_id, assurance_id, constateur_id,
    lieu_sinistre, zone, date_sinistre
  )
  VALUES (
    v_sinistre_id, btrim(p_ref_m2s), v_client_id, v_vehicule_id,
    v_assurance_id, p_constateur_id, COALESCE(p_adresse, ''),
    COALESCE(p_zone, ''), p_date_sinistre
  );

  -- Pendant les TP 5 à 7, les anciennes colonnes obligatoires existent encore :
  -- on les alimente aussi. Après le TP 8, la branche normalisée suffit.
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'dossiers'
      AND column_name = 'ref_m2s'
  ) THEN
    INSERT INTO public.dossiers(
      id, sinistre_id, ref_m2s, constateur_id,
      arrival_at, sla_hours, deadline_at, status,
      current_stage, validated_at, final_category,
      assure, num_tel_client, matricule, vehicule, nom_assurance,
      adresse, zone, date_sinistre
    )
    VALUES (
      v_dossier_id, v_sinistre_id, btrim(p_ref_m2s), p_constateur_id,
      v_arrival_at, v_sla_hours,
      COALESCE(p_deadline_at, v_arrival_at + make_interval(hours => v_sla_hours)),
      COALESCE(NULLIF(p_status, ''), 'en_retard')::public.dossier_status,
      GREATEST(0, COALESCE(p_current_stage, 0)), p_validated_at,
      CASE
        WHEN btrim(COALESCE(p_final_category, '')) = '' THEN NULL
        ELSE p_final_category::public.delay_category
      END,
      COALESCE(p_assure, ''), COALESCE(p_num_tel_client, ''),
      COALESCE(p_matricule, ''), COALESCE(p_vehicule, ''),
      COALESCE(p_nom_assurance, ''), COALESCE(p_adresse, ''),
      COALESCE(p_zone, ''), p_date_sinistre
    );
  ELSE
    INSERT INTO public.dossiers(
      id, sinistre_id, arrival_at, sla_hours, deadline_at, status,
      current_stage, validated_at, final_category
    )
    VALUES (
      v_dossier_id,
      v_sinistre_id,
      v_arrival_at,
      v_sla_hours,
      COALESCE(p_deadline_at, v_arrival_at + make_interval(hours => v_sla_hours)),
      COALESCE(NULLIF(p_status, ''), 'en_retard')::public.dossier_status,
      GREATEST(0, COALESCE(p_current_stage, 0)),
      p_validated_at,
      CASE
        WHEN btrim(COALESCE(p_final_category, '')) = '' THEN NULL
        ELSE p_final_category::public.delay_category
      END
    );
  END IF;

  RETURN v_dossier_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- Mise à jour atomique de la carte « Informations complémentaires ».
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.update_dossier_m2s(
  p_dossier_id uuid,
  p_assure text DEFAULT '',
  p_num_tel_client text DEFAULT '',
  p_matricule text DEFAULT '',
  p_vehicule text DEFAULT '',
  p_nom_assurance text DEFAULT '',
  p_adresse text DEFAULT '',
  p_zone text DEFAULT '',
  p_date_sinistre timestamptz DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
  v_sinistre_id uuid;
  v_current_client_id uuid;
  v_current_vehicule_id uuid;
  v_client_id uuid;
  v_vehicule_id uuid;
  v_assurance_id uuid;
  v_phone_normalise text;
  v_matricule_normalisee text;
BEGIN
  SELECT s.id, s.client_id, s.vehicule_id
  INTO v_sinistre_id, v_current_client_id, v_current_vehicule_id
  FROM public.dossiers d
  JOIN public.sinistres s ON s.id = d.sinistre_id
  WHERE d.id = p_dossier_id;

  IF v_sinistre_id IS NULL THEN
    RAISE EXCEPTION 'Dossier introuvable ou non relié à un sinistre.';
  END IF;

  -- Client/assuré.
  v_phone_normalise := regexp_replace(COALESCE(p_num_tel_client, ''), '[^0-9+]', '', 'g');
  IF btrim(COALESCE(p_assure, '')) = '' AND v_phone_normalise = '' THEN
    v_client_id := NULL;
  ELSE
    IF v_phone_normalise <> '' THEN
      SELECT id INTO v_client_id
      FROM public.clients
      WHERE regexp_replace(telephone, '[^0-9+]', '', 'g') = v_phone_normalise
      LIMIT 1;
    END IF;

    v_client_id := COALESCE(v_client_id, v_current_client_id);
    IF v_client_id IS NULL THEN
      BEGIN
        INSERT INTO public.clients(nom, telephone)
        VALUES (COALESCE(p_assure, ''), COALESCE(p_num_tel_client, ''))
        RETURNING id INTO v_client_id;
      EXCEPTION WHEN unique_violation THEN
        SELECT id INTO v_client_id
        FROM public.clients
        WHERE regexp_replace(telephone, '[^0-9+]', '', 'g') = v_phone_normalise
        LIMIT 1;
      END;
    ELSE
      UPDATE public.clients
      SET nom = COALESCE(p_assure, ''), telephone = COALESCE(p_num_tel_client, '')
      WHERE id = v_client_id;
    END IF;
  END IF;

  -- Véhicule.
  v_matricule_normalisee := upper(
    regexp_replace(COALESCE(p_matricule, ''), '[[:space:]-]', '', 'g')
  );
  IF btrim(COALESCE(p_vehicule, '')) = '' AND v_matricule_normalisee = '' THEN
    v_vehicule_id := NULL;
  ELSE
    IF v_matricule_normalisee <> '' THEN
      SELECT id INTO v_vehicule_id
      FROM public.vehicules
      WHERE upper(regexp_replace(matricule, '[[:space:]-]', '', 'g')) = v_matricule_normalisee
      LIMIT 1;
    END IF;

    v_vehicule_id := COALESCE(v_vehicule_id, v_current_vehicule_id);
    IF v_vehicule_id IS NULL THEN
      BEGIN
        INSERT INTO public.vehicules(matricule, description)
        VALUES (COALESCE(p_matricule, ''), COALESCE(p_vehicule, ''))
        RETURNING id INTO v_vehicule_id;
      EXCEPTION WHEN unique_violation THEN
        SELECT id INTO v_vehicule_id
        FROM public.vehicules
        WHERE upper(regexp_replace(matricule, '[[:space:]-]', '', 'g')) = v_matricule_normalisee
        LIMIT 1;
      END;
    ELSE
      UPDATE public.vehicules
      SET matricule = COALESCE(p_matricule, ''), description = COALESCE(p_vehicule, '')
      WHERE id = v_vehicule_id;
    END IF;
  END IF;

  -- Assurance.
  IF btrim(COALESCE(p_nom_assurance, '')) <> '' THEN
    SELECT id INTO v_assurance_id
    FROM public.assurances
    WHERE lower(btrim(nom)) = lower(btrim(p_nom_assurance))
    LIMIT 1;

    IF v_assurance_id IS NULL THEN
      BEGIN
        INSERT INTO public.assurances(nom)
        VALUES (btrim(p_nom_assurance))
        RETURNING id INTO v_assurance_id;
      EXCEPTION WHEN unique_violation THEN
        SELECT id INTO v_assurance_id
        FROM public.assurances
        WHERE lower(btrim(nom)) = lower(btrim(p_nom_assurance))
        LIMIT 1;
      END;
    END IF;
  END IF;

  UPDATE public.sinistres
  SET
    client_id = v_client_id,
    vehicule_id = v_vehicule_id,
    assurance_id = v_assurance_id,
    lieu_sinistre = COALESCE(p_adresse, ''),
    zone = COALESCE(p_zone, ''),
    date_sinistre = p_date_sinistre
  WHERE id = v_sinistre_id;

  -- Double écriture temporaire : garde les colonnes historiques synchronisées
  -- jusqu'à leur suppression contrôlée au TP 8. La branche est ignorée ensuite.
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'dossiers'
      AND column_name = 'ref_m2s'
  ) THEN
    UPDATE public.dossiers
    SET
      assure = COALESCE(p_assure, ''),
      num_tel_client = COALESCE(p_num_tel_client, ''),
      matricule = COALESCE(p_matricule, ''),
      vehicule = COALESCE(p_vehicule, ''),
      nom_assurance = COALESCE(p_nom_assurance, ''),
      adresse = COALESCE(p_adresse, ''),
      zone = COALESCE(p_zone, ''),
      date_sinistre = p_date_sinistre
    WHERE id = p_dossier_id;
  END IF;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.create_dossier_normalise(
  text, uuid, uuid, timestamptz, double precision, timestamptz, text, integer,
  timestamptz, text, text, text, text, text, text, text, text, timestamptz
) FROM PUBLIC, anon;

REVOKE EXECUTE ON FUNCTION public.update_dossier_m2s(
  uuid, text, text, text, text, text, text, text, timestamptz
) FROM PUBLIC, anon;

GRANT EXECUTE ON FUNCTION public.create_dossier_normalise(
  text, uuid, uuid, timestamptz, double precision, timestamptz, text, integer,
  timestamptz, text, text, text, text, text, text, text, text, timestamptz
) TO authenticated, service_role;

GRANT EXECUTE ON FUNCTION public.update_dossier_m2s(
  uuid, text, text, text, text, text, text, text, timestamptz
) TO authenticated, service_role;

-- Force PostgREST/Supabase à voir immédiatement les deux nouvelles RPC.
NOTIFY pgrst, 'reload schema';
