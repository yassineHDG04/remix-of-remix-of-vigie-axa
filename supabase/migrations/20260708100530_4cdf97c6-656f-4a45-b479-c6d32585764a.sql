ALTER TABLE public.dossiers ADD COLUMN IF NOT EXISTS stage_attempts integer NOT NULL DEFAULT 0;
ALTER TABLE public.dossiers ADD COLUMN IF NOT EXISTS stage_answered integer NOT NULL DEFAULT 0;
ALTER TABLE public.dossiers ADD COLUMN IF NOT EXISTS next_action_at timestamptz NULL;
ALTER TABLE public.calls ADD COLUMN IF NOT EXISTS provider_ref text NULL;
ALTER TYPE call_status ADD VALUE IF NOT EXISTS 'en_cours';