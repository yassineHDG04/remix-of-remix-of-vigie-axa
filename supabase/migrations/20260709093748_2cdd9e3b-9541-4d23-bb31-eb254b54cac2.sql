CREATE OR REPLACE FUNCTION public.handle_new_user()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  v_status text := 'actif';
  v_must_reset boolean := false;
  v_invited boolean := false;
  v_is_bootstrap_admin boolean := false;
BEGIN
  v_invited := COALESCE((NEW.raw_user_meta_data->>'invited')::boolean, false);
  v_is_bootstrap_admin := (NEW.email = 'elhodiguyyassine@gmail.com');

  IF v_invited THEN
    v_status := 'invite';
    v_must_reset := true;
  END IF;

  INSERT INTO public.profiles (id, email, full_name, status, must_reset_password)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(
      NEW.raw_user_meta_data->>'full_name',
      NEW.raw_user_meta_data->>'name',
      split_part(NEW.email, '@', 1)
    ),
    v_status,
    v_must_reset
  )
  ON CONFLICT (id) DO NOTHING;

  -- Attribution du rôle UNIQUEMENT si :
  --  - l'utilisateur a été créé via l'invitation admin (invite-supervisor), ou
  --  - c'est le compte admin bootstrap.
  -- Sinon : aucun rôle => aucun accès (les policies RLS bloquent tout).
  IF v_is_bootstrap_admin THEN
    INSERT INTO public.user_roles (user_id, role)
    VALUES (NEW.id, 'admin')
    ON CONFLICT (user_id, role) DO NOTHING;
  ELSIF v_invited THEN
    INSERT INTO public.user_roles (user_id, role)
    VALUES (NEW.id, 'superviseur')
    ON CONFLICT (user_id, role) DO NOTHING;
  END IF;

  RETURN NEW;
END;
$function$;