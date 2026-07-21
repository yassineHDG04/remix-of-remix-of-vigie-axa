-- Paramètres de l'agent vocal, stockés sur la ligne unique settings.id = 1.
-- Aucune policy RLS n'est modifiée : les règles existantes restent applicables.
ALTER TABLE public.settings
  ADD COLUMN IF NOT EXISTS livekit_url text DEFAULT '',
  ADD COLUMN IF NOT EXISTS livekit_api_key text DEFAULT '',
  ADD COLUMN IF NOT EXISTS livekit_api_secret text DEFAULT '',
  ADD COLUMN IF NOT EXISTS openai_api_key text DEFAULT '',
  ADD COLUMN IF NOT EXISTS vigie_api_base_url text DEFAULT '',
  ADD COLUMN IF NOT EXISTS agent_max_call_seconds integer DEFAULT 60,
  ADD COLUMN IF NOT EXISTS agent_max_response_tokens integer DEFAULT 200,
  ADD COLUMN IF NOT EXISTS agent_max_turns integer DEFAULT 6;

-- Champs M2S complémentaires. Aucune policy RLS n'est modifiée.
ALTER TABLE public.dossiers
  ADD COLUMN IF NOT EXISTS assure text DEFAULT '',
  ADD COLUMN IF NOT EXISTS vehicule text DEFAULT '',
  ADD COLUMN IF NOT EXISTS date_sinistre timestamptz NULL;
