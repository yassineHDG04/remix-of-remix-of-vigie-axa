-- Chantier 3 : routage configurable WhatsApp Calling -> SIP -> hand-off.
-- Migration idempotente. Les policies RLS existantes restent inchangées.

ALTER TABLE public.settings
  ADD COLUMN IF NOT EXISTS call_channel text NOT NULL DEFAULT 'sip',
  ADD COLUMN IF NOT EXISTS whatsapp_max_attempts integer NOT NULL DEFAULT 2;

ALTER TABLE public.calls
  ADD COLUMN IF NOT EXISTS call_channel_used text,
  ADD COLUMN IF NOT EXISTS fallback_reason text,
  ADD COLUMN IF NOT EXISTS provider_connected_at timestamptz,
  ADD COLUMN IF NOT EXISTS estimated_transport_cost_usd numeric(12,6) NOT NULL DEFAULT 0;

UPDATE public.settings
SET
  call_channel = CASE
    WHEN call_channel IN ('sip', 'whatsapp', 'whatsapp_then_sip') THEN call_channel
    ELSE 'sip'
  END,
  whatsapp_max_attempts = GREATEST(1, LEAST(10, COALESCE(whatsapp_max_attempts, 2)))
WHERE id = 1;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'settings_call_channel_check'
      AND conrelid = 'public.settings'::regclass
  ) THEN
    ALTER TABLE public.settings
      ADD CONSTRAINT settings_call_channel_check
      CHECK (call_channel IN ('sip', 'whatsapp', 'whatsapp_then_sip'));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'settings_whatsapp_max_attempts_check'
      AND conrelid = 'public.settings'::regclass
  ) THEN
    ALTER TABLE public.settings
      ADD CONSTRAINT settings_whatsapp_max_attempts_check
      CHECK (whatsapp_max_attempts BETWEEN 1 AND 10);
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'calls_call_channel_used_check'
      AND conrelid = 'public.calls'::regclass
  ) THEN
    ALTER TABLE public.calls
      ADD CONSTRAINT calls_call_channel_used_check
      CHECK (call_channel_used IS NULL OR call_channel_used IN ('sip', 'whatsapp', 'mock'));
  END IF;
END
$$;

COMMENT ON COLUMN public.settings.call_channel IS
  'sip = téléphone uniquement ; whatsapp_then_sip = WhatsApp puis téléphone ; whatsapp = réservé aux tests.';
COMMENT ON COLUMN public.calls.fallback_reason IS
  'Raison normalisée de la bascule du canal WhatsApp vers le canal SIP.';
COMMENT ON COLUMN public.calls.estimated_transport_cost_usd IS
  'Estimation du transport téléphonique/WhatsApp, distincte du coût IA estimated_cost_usd.';
