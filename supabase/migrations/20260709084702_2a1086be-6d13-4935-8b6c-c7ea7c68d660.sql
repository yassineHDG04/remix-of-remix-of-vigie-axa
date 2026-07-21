
-- Tighten RLS policies: restrict app data access to users with an actual role (admin or superviseur)
-- and restrict settings writes to admins only.

-- CALLS
DROP POLICY IF EXISTS calls_read_all_auth ON public.calls;
DROP POLICY IF EXISTS calls_write_auth ON public.calls;
DROP POLICY IF EXISTS calls_update_auth ON public.calls;

CREATE POLICY calls_read_roles ON public.calls FOR SELECT TO authenticated
  USING (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'));
CREATE POLICY calls_insert_roles ON public.calls FOR INSERT TO authenticated
  WITH CHECK (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'));
CREATE POLICY calls_update_roles ON public.calls FOR UPDATE TO authenticated
  USING (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'))
  WITH CHECK (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'));

-- CONSTATEURS
DROP POLICY IF EXISTS constateurs_read_all_auth ON public.constateurs;
DROP POLICY IF EXISTS constateurs_write_auth ON public.constateurs;
DROP POLICY IF EXISTS constateurs_update_auth ON public.constateurs;

CREATE POLICY constateurs_read_roles ON public.constateurs FOR SELECT TO authenticated
  USING (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'));
CREATE POLICY constateurs_insert_roles ON public.constateurs FOR INSERT TO authenticated
  WITH CHECK (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'));
CREATE POLICY constateurs_update_roles ON public.constateurs FOR UPDATE TO authenticated
  USING (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'))
  WITH CHECK (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'));

-- DOSSIERS
DROP POLICY IF EXISTS dossiers_read_all_auth ON public.dossiers;
DROP POLICY IF EXISTS dossiers_write_auth ON public.dossiers;
DROP POLICY IF EXISTS dossiers_update_auth ON public.dossiers;

CREATE POLICY dossiers_read_roles ON public.dossiers FOR SELECT TO authenticated
  USING (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'));
CREATE POLICY dossiers_insert_roles ON public.dossiers FOR INSERT TO authenticated
  WITH CHECK (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'));
CREATE POLICY dossiers_update_roles ON public.dossiers FOR UPDATE TO authenticated
  USING (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'))
  WITH CHECK (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'));

-- TRANSCRIPT TURNS
DROP POLICY IF EXISTS transcript_read_all_auth ON public.transcript_turns;
DROP POLICY IF EXISTS transcript_write_auth ON public.transcript_turns;

CREATE POLICY transcript_read_roles ON public.transcript_turns FOR SELECT TO authenticated
  USING (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'));
CREATE POLICY transcript_insert_roles ON public.transcript_turns FOR INSERT TO authenticated
  WITH CHECK (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'));

-- SETTINGS: reads for roles, writes admin-only
DROP POLICY IF EXISTS settings_read_all_auth ON public.settings;
DROP POLICY IF EXISTS settings_update_auth ON public.settings;

CREATE POLICY settings_read_roles ON public.settings FOR SELECT TO authenticated
  USING (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'));
CREATE POLICY settings_update_admin ON public.settings FOR UPDATE TO authenticated
  USING (public.has_role(auth.uid(), 'admin'))
  WITH CHECK (public.has_role(auth.uid(), 'admin'));

-- PROFILES: remove overly permissive select-all policy; keep own + admin policies
DROP POLICY IF EXISTS profiles_select_all_authenticated ON public.profiles;

-- SECURITY DEFINER functions: restrict EXECUTE
-- handle_new_user and set_updated_at are trigger functions — no client should call them.
REVOKE ALL ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.set_updated_at() FROM PUBLIC, anon, authenticated;

-- has_role is used inside RLS policies; revoke from anon (not needed) but keep authenticated (policies invoke it).
REVOKE ALL ON FUNCTION public.has_role(uuid, public.app_role) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO authenticated, service_role;
