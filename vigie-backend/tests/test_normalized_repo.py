import unittest
from datetime import datetime

from app.repo import SupabaseRepo


class _FakeAuth:
    @staticmethod
    def get_session():
        return object()


class _FakeRpcResult:
    data = "dossier-cree"


class _FakeSupabase:
    def __init__(self) -> None:
        self.auth = _FakeAuth()
        self.function_name = None
        self.payload = None

    def rpc(self, function_name, payload):
        self.function_name = function_name
        self.payload = payload
        return self

    @staticmethod
    def execute():
        return _FakeRpcResult()


class NormalizedSupabaseRepoTests(unittest.TestCase):
    def test_view_row_is_flattened_to_existing_contract(self) -> None:
        row = SupabaseRepo._dossier(
            {
                "id": "d1",
                "sinistre_id": "s1",
                "ref_m2s": "M2S-001",
                "constateur_id": "c1",
                "constateurs": {
                    "nom": "Constateur Test",
                    "telephone": "+212600000000",
                    "zone": "Rabat",
                },
                "arrival_at": "2026-07-16T08:00:00+00:00",
                "sla_hours": 24,
                "deadline_at": "2026-07-17T08:00:00+00:00",
                "status": "en_retard",
                "current_stage": 1,
                "stage_attempts": 1,
                "stage_answered": 0,
                "assure": "Assuré Test",
                "num_tel_client": "+212611111111",
                "matricule": "12345-A-6",
                "vehicule": "Véhicule Test",
                "nom_assurance": "AXA",
                "adresse": "Rabat",
                "zone": "Rabat",
                "date_sinistre": "2026-07-15T10:00:00+00:00",
            }
        )

        self.assertEqual(row.ref_m2s, "M2S-001")
        self.assertEqual(row.constateur_nom, "Constateur Test")
        self.assertEqual(row.assure, "Assuré Test")
        self.assertEqual(row.matricule, "12345-A-6")
        self.assertEqual(row.zone, "Rabat")

    def test_supabase_insert_uses_normalized_rpc(self) -> None:
        fake = _FakeSupabase()
        repo = SupabaseRepo.__new__(SupabaseRepo)
        repo.sb = fake

        dossier_id = repo.insert_dossier(
            {
                "id": "d1",
                "ref_m2s": "M2S-002",
                "constateur_id": "c1",
                "arrival_at": datetime(2026, 7, 16, 8, 0),
                "sla_hours": 24,
                "deadline_at": datetime(2026, 7, 17, 8, 0),
                "status": "en_retard",
                "current_stage": 0,
                "assure": "Assuré Test",
                "matricule": "12345-A-6",
            }
        )

        self.assertEqual(dossier_id, "dossier-cree")
        self.assertEqual(fake.function_name, "create_dossier_normalise")
        self.assertEqual(fake.payload["p_ref_m2s"], "M2S-002")
        self.assertEqual(fake.payload["p_dossier_id"], "d1")
        self.assertEqual(fake.payload["p_assure"], "Assuré Test")
        self.assertEqual(fake.payload["p_matricule"], "12345-A-6")


if __name__ == "__main__":
    unittest.main()
