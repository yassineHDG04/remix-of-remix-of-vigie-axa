
-- 1) WhatsApp contacts table (multiple supervisor contacts)
CREATE TABLE IF NOT EXISTS public.whatsapp_contacts (
  id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  label text NOT NULL DEFAULT '',
  number_whatsapp text NOT NULL,
  whatsapp_token text NOT NULL DEFAULT '',
  whatsapp_phone_number_id text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.whatsapp_contacts TO authenticated;
GRANT ALL ON public.whatsapp_contacts TO service_role;

ALTER TABLE public.whatsapp_contacts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "wa_contacts_read_roles" ON public.whatsapp_contacts
  FOR SELECT TO authenticated
  USING (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'));
CREATE POLICY "wa_contacts_insert_roles" ON public.whatsapp_contacts
  FOR INSERT TO authenticated
  WITH CHECK (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'));
CREATE POLICY "wa_contacts_update_roles" ON public.whatsapp_contacts
  FOR UPDATE TO authenticated
  USING (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'))
  WITH CHECK (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'));
CREATE POLICY "wa_contacts_delete_roles" ON public.whatsapp_contacts
  FOR DELETE TO authenticated
  USING (public.has_role(auth.uid(), 'admin') OR public.has_role(auth.uid(), 'superviseur'));

CREATE TRIGGER trg_wa_contacts_updated
  BEFORE UPDATE ON public.whatsapp_contacts
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- 2) Settings: add selected whatsapp contact + SIP telephony fields
ALTER TABLE public.settings
  ADD COLUMN IF NOT EXISTS selected_whatsapp_id uuid REFERENCES public.whatsapp_contacts(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS sip_trunk_id text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS sip_caller_id text NOT NULL DEFAULT '';

-- 3) Dossiers: add matricule, num_tel_client, nom_assurance, adresse, zone
ALTER TABLE public.dossiers
  ADD COLUMN IF NOT EXISTS matricule text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS num_tel_client text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS nom_assurance text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS adresse text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS zone text NOT NULL DEFAULT '';
