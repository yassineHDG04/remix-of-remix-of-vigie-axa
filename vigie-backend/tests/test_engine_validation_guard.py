import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from app.engine import apply_call_result


class _EngineRepo:
    def __init__(self):
        self.dossier_updates = []
        self.call_updates = []

    @staticmethod
    def get_settings():
        return SimpleNamespace(max_attempts=3, retry_interval_min=10)

    def update_call(self, call_id, values):
        self.call_updates.append((call_id, values))

    @staticmethod
    def insert_transcript(_call_id, _turns):
        return None

    @staticmethod
    def get_dossier(_dossier_id):
        return SimpleNamespace(id="dossier-1", ref_m2s="M2S-001", status="valide")

    def update_dossier(self, dossier_id, values):
        self.dossier_updates.append((dossier_id, values))


class EngineValidationGuardTests(unittest.TestCase):
    def test_late_call_result_cannot_schedule_after_m2s_validation(self):
        repo = _EngineRepo()
        call = SimpleNamespace(id="call-1")
        stale_dossier = SimpleNamespace(
            id="dossier-1",
            ref_m2s="M2S-001",
            status="en_retard",
            stage_attempts=1,
            deadline_at=datetime.utcnow() + timedelta(hours=1),
        )

        with patch("app.engine.get_repo", return_value=repo):
            apply_call_result(
                call,
                stale_dossier,
                status="non_joignable",
                duration_sec=4,
                voice_engine_used="pipeline",
                models_used={"stt_model": "gpt-4o-mini-transcribe"},
                estimated_cost_usd=0.001,
            )

        self.assertEqual(len(repo.call_updates), 1)
        call_update = repo.call_updates[0][1]
        self.assertEqual(call_update["voice_engine_used"], "pipeline")
        self.assertEqual(call_update["models_used"]["stt_model"], "gpt-4o-mini-transcribe")
        self.assertEqual(call_update["estimated_cost_usd"], 0.001)
        self.assertEqual(repo.dossier_updates, [])


if __name__ == "__main__":
    unittest.main()
