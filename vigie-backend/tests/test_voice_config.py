import os
import unittest
from unittest.mock import patch

from agent.voice_config import VoiceConfig, estimate_ai_cost_usd


class VoiceConfigTests(unittest.TestCase):
    def test_database_metadata_wins_over_environment(self):
        with patch.dict(
            os.environ,
            {"VOICE_ENGINE": "realtime", "OPENAI_LLM_MODEL": "env-model"},
            clear=False,
        ):
            config = VoiceConfig.from_metadata(
                {
                    "voice_engine": "pipeline",
                    "stt_provider": "openai",
                    "stt_model": "gpt-4o-mini-transcribe",
                    "stt_language": "ar",
                    "llm_model": "gpt-4o-mini",
                    "tts_provider": "openai",
                    "tts_model": "gpt-4o-mini-tts",
                    "tts_voice_id": "ash",
                }
            )

        self.assertEqual(config.voice_engine, "pipeline")
        self.assertEqual(config.llm_model, "gpt-4o-mini")
        config.validate_pipeline()

    def test_unknown_engine_fails_safe_to_realtime(self):
        config = VoiceConfig.from_metadata({"voice_engine": "inconnu"})
        self.assertEqual(config.voice_engine, "realtime")
        self.assertEqual(config.models_used(), {"realtime_model": "gpt-realtime"})

    def test_unsupported_pipeline_provider_is_rejected_for_fallback(self):
        config = VoiceConfig.from_metadata(
            {"voice_engine": "pipeline", "stt_provider": "fournisseur-inconnu"}
        )
        with self.assertRaises(ValueError):
            config.validate_pipeline()

    def test_cost_estimate_uses_connected_duration(self):
        self.assertEqual(estimate_ai_cost_usd("realtime", 60), 0.05)
        self.assertEqual(estimate_ai_cost_usd("pipeline", 45), 0.0075)
        self.assertEqual(estimate_ai_cost_usd("pipeline", -1), 0.0)


if __name__ == "__main__":
    unittest.main()

