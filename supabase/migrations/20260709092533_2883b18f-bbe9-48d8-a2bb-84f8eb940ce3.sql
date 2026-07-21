DROP POLICY IF EXISTS settings_update_admin ON public.settings;
CREATE POLICY settings_update_admin_or_superviseur ON public.settings
  FOR UPDATE TO authenticated
  USING (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'))
  WITH CHECK (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'));