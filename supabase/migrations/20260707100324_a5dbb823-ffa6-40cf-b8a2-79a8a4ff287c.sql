
-- =========================================================
-- ENUMS
-- =========================================================
CREATE TYPE public.app_role AS ENUM ('admin', 'superviseur');
CREATE TYPE public.dossier_status AS ENUM ('en_retard', 'valide');
CREATE TYPE public.call_status AS ENUM ('pris', 'non_joignable', 'repondeur', 'refus', 'echec');
CREATE TYPE public.call_outcome AS ENUM ('cause_captee', 'non_joignable', 'hors_sujet', 'refus');
CREATE TYPE public.delay_category AS ENUM ('desaccord_parties', 'zone_hors_km', 'expertise_en_cours', 'pieces_manquantes', 'injoignable_tiers', 'autre');
CREATE TYPE public.speaker AS ENUM ('ia', 'constateur');

-- =========================================================
-- PROFILES
-- =========================================================
CREATE TABLE public.profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  full_name TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE ON public.profiles TO authenticated;
GRANT ALL ON public.profiles TO service_role;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "profiles_select_all_authenticated"
  ON public.profiles FOR SELECT TO authenticated USING (true);
CREATE POLICY "profiles_update_own"
  ON public.profiles FOR UPDATE TO authenticated
  USING (auth.uid() = id) WITH CHECK (auth.uid() = id);

-- =========================================================
-- USER ROLES (never on profiles)
-- =========================================================
CREATE TABLE public.user_roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role public.app_role NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, role)
);
GRANT SELECT ON public.user_roles TO authenticated;
GRANT ALL ON public.user_roles TO service_role;
ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.has_role(_user_id UUID, _role public.app_role)
RETURNS BOOLEAN
LANGUAGE SQL
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.user_roles WHERE user_id = _user_id AND role = _role
  )
$$;

CREATE POLICY "user_roles_select_own_or_admin"
  ON public.user_roles FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.has_role(auth.uid(), 'admin'));
CREATE POLICY "user_roles_admin_manage"
  ON public.user_roles FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'admin'))
  WITH CHECK (public.has_role(auth.uid(), 'admin'));

-- =========================================================
-- Trigger: create profile + default role on signup
-- =========================================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.profiles (id, email, full_name)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(
      NEW.raw_user_meta_data->>'full_name',
      NEW.raw_user_meta_data->>'name',
      split_part(NEW.email, '@', 1)
    )
  )
  ON CONFLICT (id) DO NOTHING;

  INSERT INTO public.user_roles (user_id, role)
  VALUES (NEW.id, 'superviseur')
  ON CONFLICT (user_id, role) DO NOTHING;

  RETURN NEW;
END;
$$;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- =========================================================
-- CONSTATEURS
-- =========================================================
CREATE TABLE public.constateurs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nom TEXT NOT NULL,
  telephone TEXT NOT NULL,
  zone TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.constateurs TO authenticated;
GRANT ALL ON public.constateurs TO service_role;
ALTER TABLE public.constateurs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "constateurs_read_all_auth" ON public.constateurs
  FOR SELECT TO authenticated USING (true);
CREATE POLICY "constateurs_write_auth" ON public.constateurs
  FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "constateurs_update_auth" ON public.constateurs
  FOR UPDATE TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "constateurs_delete_admin" ON public.constateurs
  FOR DELETE TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- =========================================================
-- DOSSIERS
-- =========================================================
CREATE TABLE public.dossiers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ref_axa TEXT NOT NULL UNIQUE,
  constateur_id UUID NOT NULL REFERENCES public.constateurs(id) ON DELETE RESTRICT,
  arrival_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sla_hours INTEGER NOT NULL DEFAULT 24,
  deadline_at TIMESTAMPTZ NOT NULL,
  status public.dossier_status NOT NULL DEFAULT 'en_retard',
  current_stage INTEGER NOT NULL DEFAULT 0,
  validated_at TIMESTAMPTZ,
  handoff_reason TEXT,
  final_category public.delay_category,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_dossiers_status ON public.dossiers(status);
CREATE INDEX idx_dossiers_deadline ON public.dossiers(deadline_at);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.dossiers TO authenticated;
GRANT ALL ON public.dossiers TO service_role;
ALTER TABLE public.dossiers ENABLE ROW LEVEL SECURITY;

CREATE POLICY "dossiers_read_all_auth" ON public.dossiers
  FOR SELECT TO authenticated USING (true);
CREATE POLICY "dossiers_write_auth" ON public.dossiers
  FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "dossiers_update_auth" ON public.dossiers
  FOR UPDATE TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "dossiers_delete_admin" ON public.dossiers
  FOR DELETE TO authenticated USING (public.has_role(auth.uid(), 'admin'));

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = public AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

CREATE TRIGGER trg_dossiers_updated
  BEFORE UPDATE ON public.dossiers
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- =========================================================
-- CALLS
-- =========================================================
CREATE TABLE public.calls (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dossier_id UUID NOT NULL REFERENCES public.dossiers(id) ON DELETE CASCADE,
  stage INTEGER NOT NULL,
  attempt_no INTEGER NOT NULL DEFAULT 1,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ended_at TIMESTAMPTZ,
  duration_sec INTEGER NOT NULL DEFAULT 0,
  status public.call_status NOT NULL DEFAULT 'echec',
  outcome public.call_outcome,
  delay_reason TEXT,
  delay_category public.delay_category,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_calls_dossier ON public.calls(dossier_id);
CREATE INDEX idx_calls_started_at ON public.calls(started_at);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.calls TO authenticated;
GRANT ALL ON public.calls TO service_role;
ALTER TABLE public.calls ENABLE ROW LEVEL SECURITY;

CREATE POLICY "calls_read_all_auth" ON public.calls
  FOR SELECT TO authenticated USING (true);
CREATE POLICY "calls_write_auth" ON public.calls
  FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "calls_update_auth" ON public.calls
  FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

-- =========================================================
-- TRANSCRIPT TURNS
-- =========================================================
CREATE TABLE public.transcript_turns (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id UUID NOT NULL REFERENCES public.calls(id) ON DELETE CASCADE,
  turn_no INTEGER NOT NULL,
  speaker public.speaker NOT NULL,
  text TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (call_id, turn_no)
);
CREATE INDEX idx_transcript_call ON public.transcript_turns(call_id);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.transcript_turns TO authenticated;
GRANT ALL ON public.transcript_turns TO service_role;
ALTER TABLE public.transcript_turns ENABLE ROW LEVEL SECURITY;

CREATE POLICY "transcript_read_all_auth" ON public.transcript_turns
  FOR SELECT TO authenticated USING (true);
CREATE POLICY "transcript_write_auth" ON public.transcript_turns
  FOR INSERT TO authenticated WITH CHECK (true);

-- =========================================================
-- SETTINGS (singleton)
-- =========================================================
CREATE TABLE public.settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  nb_relances_ia INTEGER NOT NULL DEFAULT 3,
  relance1_min INTEGER NOT NULL DEFAULT 60,
  relance2_min INTEGER NOT NULL DEFAULT 30,
  relance3_min INTEGER NOT NULL DEFAULT 15,
  relance4_min INTEGER NOT NULL DEFAULT 10,
  humain_min INTEGER NOT NULL DEFAULT 5,
  retry_interval_min INTEGER NOT NULL DEFAULT 20,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  call_window_start TEXT NOT NULL DEFAULT '09:00',
  call_window_end TEXT NOT NULL DEFAULT '18:00',
  sla_hours INTEGER NOT NULL DEFAULT 24,
  zineb_whatsapp TEXT NOT NULL DEFAULT '+212600000000',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE ON public.settings TO authenticated;
GRANT ALL ON public.settings TO service_role;
ALTER TABLE public.settings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "settings_read_all_auth" ON public.settings
  FOR SELECT TO authenticated USING (true);
CREATE POLICY "settings_update_auth" ON public.settings
  FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

CREATE TRIGGER trg_settings_updated
  BEFORE UPDATE ON public.settings
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

INSERT INTO public.settings (id) VALUES (1);
