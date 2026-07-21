import hashlib
import hmac
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import config
from app.main import app
from app.schemas import ImportResult


class _WebhookRepo:
    def __init__(self):
        self.events = {}
        self.completed = []
        self.dossier = SimpleNamespace(id="dossier-1")

    def get_m2s_webhook_event(self, event_id):
        return self.events.get(event_id)

    def claim_m2s_webhook_event(self, event_id, payload_sha256):
        if event_id in self.events:
            return False
        self.events[event_id] = {
            "event_id": event_id,
            "payload_sha256": payload_sha256,
            "processing_status": "processing",
        }
        return True

    def get_dossier_by_ref(self, _ref):
        return self.dossier

    def complete_m2s_webhook_event(self, event_id, **values):
        self.events[event_id].update(values)
        self.completed.append((event_id, values))


class M2SWebhookTests(unittest.TestCase):
    def setUp(self):
        self.old_values = (
            config.m2s_webhook_secret,
            config.m2s_status_field,
            config.m2s_validated_status_values,
            config.m2s_active_status_values,
        )
        config.m2s_webhook_secret = "secret-webhook-test"
        config.m2s_status_field = "statut_dossier"
        config.m2s_validated_status_values = "validé"
        config.m2s_active_status_values = "en cours"
        self.repo = _WebhookRepo()
        self.patches = [
            patch("app.routers.m2s_webhook.get_repo", return_value=self.repo),
            patch(
                "app.routers.m2s_webhook.get_m2s_runtime_config",
                return_value=SimpleNamespace(mode="webhook"),
            ),
            patch(
                "app.routers.m2s_webhook.import_dossiers_list",
                return_value=ImportResult(
                    imported=0,
                    skipped_existing=[],
                    updated=1,
                    status_changed=1,
                ),
            ),
        ]
        for patcher in self.patches:
            patcher.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        for patcher in reversed(self.patches):
            patcher.stop()
        (
            config.m2s_webhook_secret,
            config.m2s_status_field,
            config.m2s_validated_status_values,
            config.m2s_active_status_values,
        ) = self.old_values

    def _signed_request(self, body: bytes):
        digest = hmac.new(
            config.m2s_webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        return self.client.post(
            "/api/webhooks/m2s/dossier-status",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-M2S-Signature-256": f"sha256={digest}",
            },
        )

    def test_signed_event_is_processed_once(self):
        body = json.dumps({
            "event_id": "evt-001",
            "data": {
                "ref_sinistre": "M2S-001",
                "constateur": "Test",
                "num_tel_constateur": "+212600000000",
                "statut_dossier": "validé",
            },
        }).encode()

        first = self._signed_request(body)
        second = self._signed_request(body)

        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()["duplicate"])
        self.assertTrue(first.json()["status_changed"])
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["duplicate"])
        self.assertEqual(len(self.repo.completed), 1)

    def test_invalid_signature_is_rejected(self):
        response = self.client.post(
            "/api/webhooks/m2s/dossier-status",
            json={"event_id": "evt-002"},
            headers={"X-M2S-Signature-256": "sha256=incorrect"},
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
