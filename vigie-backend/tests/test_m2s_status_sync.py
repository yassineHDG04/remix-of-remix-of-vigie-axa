import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.config import config
from app.importer import import_dossiers_list
from app.providers.m2s import map_m2s_payload


FULL_PAYLOAD = {
    "ref_sinistre": "M2S-STATUS-001",
    "constateur": "Constateur Test",
    "num_tel_constateur": "+212600000000",
    "assuré": "Client Test",
    "vehicule": "Dacia Sandero",
    "matricule": "12345-A-6",
    "lieu_sinistre": "Casablanca",
    "date_sinistre": "2026-07-20T08:00:00Z",
    "nom_assurance": "Assurance Test",
}


class _FakeRepo:
    def __init__(self):
        self.existing = SimpleNamespace(id="dossier-1", status="en_retard")
        self.updated_values = None
        self.applied_status = None

    @staticmethod
    def get_settings():
        return SimpleNamespace(sla_hours=6)

    @staticmethod
    def get_or_create_constateur(_nom, _telephone, _zone):
        return "constateur-1"

    def get_dossier_by_ref(self, _ref):
        return self.existing

    def update_m2s_fields(self, _dossier_id, values):
        self.updated_values = values

    def apply_m2s_status(self, _dossier_id, status):
        self.applied_status = status
        return True


class M2SStatusSyncTests(unittest.TestCase):
    def setUp(self):
        self.old_field = config.m2s_status_field
        self.old_validated = config.m2s_validated_status_values
        self.old_active = config.m2s_active_status_values

    def tearDown(self):
        config.m2s_status_field = self.old_field
        config.m2s_validated_status_values = self.old_validated
        config.m2s_active_status_values = self.old_active

    def test_mapper_does_not_guess_status_when_contract_is_unknown(self):
        config.m2s_status_field = ""
        config.m2s_validated_status_values = ""
        config.m2s_active_status_values = ""
        mapped = map_m2s_payload({**FULL_PAYLOAD, "statut": "validé"})
        self.assertIsNotNone(mapped)
        self.assertIsNone(mapped.status)

    def test_mapper_uses_confirmed_status_contract(self):
        config.m2s_status_field = "statut_dossier"
        config.m2s_validated_status_values = "validé, clôturé"
        config.m2s_active_status_values = "en cours"
        mapped = map_m2s_payload({**FULL_PAYLOAD, "statut_dossier": "VALIDÉ"})
        self.assertEqual(mapped.status, "valide")

    def test_existing_dossier_is_updated_and_validated_by_m2s_sync(self):
        config.m2s_status_field = "statut_dossier"
        config.m2s_validated_status_values = "validé"
        mapped = map_m2s_payload({**FULL_PAYLOAD, "statut_dossier": "validé"})
        repo = _FakeRepo()
        with patch("app.importer.get_repo", return_value=repo):
            result = import_dossiers_list(
                [mapped],
                sync_existing=True,
                allow_status_updates=True,
            )
        self.assertEqual(result.imported, 0)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.status_changed, 1)
        self.assertEqual(repo.applied_status, "valide")
        self.assertEqual(repo.updated_values["assure"], "Client Test")


if __name__ == "__main__":
    unittest.main()
