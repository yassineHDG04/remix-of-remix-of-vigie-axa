
-- 1) has_role now also requires the profile to be active. Suspended users lose access.
CREATE OR REPLACE FUNCTION public.has_role(_user_id uuid, _role public.app_role)
RETURNS boolean
LANGUAGE sql
STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.user_roles ur
    LEFT JOIN public.profiles p ON p.id = ur.user_id
    WHERE ur.user_id = _user_id
      AND ur.role = _role
      AND COALESCE(p.status, 'actif') = 'actif'
  )
$$;

-- 2) Prevent users from self-editing sensitive profile columns.
-- A trigger blocks any attempt by a non-admin to change status or must_reset_password.
CREATE OR REPLACE FUNCTION public.profiles_guard_self_update()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF public.has_role(auth.uid(), 'admin') THEN
    RETURN NEW;
  END IF;

  IF NEW.status IS DISTINCT FROM OLD.status THEN
    RAISE EXCEPTION 'Seul un administrateur peut modifier le statut du compte.';
  END IF;
  IF NEW.must_reset_password IS DISTINCT FROM OLD.must_reset_password
     AND NEW.must_reset_password = true THEN
    -- Un utilisateur peut désactiver son propre must_reset_password (après avoir défini son mot de passe)
    -- mais ne peut pas le réactiver pour un autre effet de bord.
    RAISE EXCEPTION 'Seul un administrateur peut réactiver la demande de réinitialisation.';
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS profiles_guard_self_update ON public.profiles;
CREATE TRIGGER profiles_guard_self_update
BEFORE UPDATE ON public.profiles
FOR EACH ROW EXECUTE FUNCTION public.profiles_guard_self_update();

-- Le trigger utilise has_role() : conserver l'exécution restreinte
REVOKE ALL ON FUNCTION public.profiles_guard_self_update() FROM PUBLIC, anon, authenticated;
