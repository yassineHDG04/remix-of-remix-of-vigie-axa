-- Chantier 1 : moteur vocal configurable et traçabilité des appels.
-- Migration idempotente. Les policies RLS existantes restent inchangées.

ALTER TABLE public.settings
  ADD COLUMN IF NOT EXISTS voice_engine text NOT NULL DEFAULT 'realtime',
  ADD COLUMN IF NOT EXISTS realtime_model text NOT NULL DEFAULT 'gpt-realtime',
  ADD COLUMN IF NOT EXISTS stt_provider text NOT NULL DEFAULT 'openai',
  ADD COLUMN IF NOT EXISTS stt_model text NOT NULL DEFAULT 'gpt-4o-mini-transcribe',
  ADD COLUMN IF NOT EXISTS stt_language text NOT NULL DEFAULT 'ar',
  ADD COLUMN IF NOT EXISTS llm_model text NOT NULL DEFAULT 'gpt-4o-mini',
  ADD COLUMN IF NOT EXISTS tts_provider text NOT NULL DEFAULT 'openai',
  ADD COLUMN IF NOT EXISTS tts_model text NOT NULL DEFAULT 'gpt-4o-mini-tts',
  ADD COLUMN IF NOT EXISTS tts_voice_id text NOT NULL DEFAULT 'ash';

ALTER TABLE public.calls
  ADD COLUMN IF NOT EXISTS voice_engine_used text,
  ADD COLUMN IF NOT EXISTS models_used jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS estimated_cost_usd numeric(12, 6) NOT NULL DEFAULT 0;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'settings_voice_engine_check'
      AND conrelid = 'public.settings'::regclass
  ) THEN
    ALTER TABLE public.settings
      ADD CONSTRAINT settings_voice_engine_check
      CHECK (voice_engine IN ('realtime', 'pipeline'));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'calls_voice_engine_used_check'
      AND conrelid = 'public.calls'::regclass
  ) THEN
    ALTER TABLE public.calls
      ADD CONSTRAINT calls_voice_engine_used_check
      CHECK (voice_engine_used IS NULL OR voice_engine_used IN ('realtime', 'pipeline', 'mock'));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'calls_estimated_cost_usd_check'
      AND conrelid = 'public.calls'::regclass
  ) THEN
    ALTER TABLE public.calls
      ADD CONSTRAINT calls_estimated_cost_usd_check
      CHECK (estimated_cost_usd >= 0);
  END IF;
END
$$;

