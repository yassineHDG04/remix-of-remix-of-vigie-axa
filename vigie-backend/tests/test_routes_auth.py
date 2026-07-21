import hashlib
import hmac
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import config
from app.main import app


class ProtectedRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_api_key = config.vigie_api_key
        self.previous_app_secret = config.whatsapp_app_secret
        config.vigie_api_key = "test-api-key"
        config.whatsapp_app_secret = "test-meta-secret"
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        config.vigie_api_key = self.previous_api_key
        config.whatsapp_app_secret = self.previous_app_secret

    def test_healthcheck_remains_public(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_sensitive_routers_reject_missing_key(self) -> None:
        requests = (
            ("GET", "/api/dossiers", None),
            ("GET", "/api/settings", None),
            ("GET", "/api/kpi", None),
            ("GET", "/api/calls/inconnu", None),
            ("POST", "/api/engine/tick", None),
            ("POST", "/api/webhooks/calls/inconnu/result", {}),
        )

        for method, path, body in requests:
            with self.subTest(path=path):
                response = self.client.request(method, path, json=body)
                self.assertEqual(response.status_code, 401)

    def test_whatsapp_webhook_rejects_missing_meta_signature(self) -> None:
        response = self.client.post("/api/webhooks/whatsapp", json={})
        self.assertEqual(response.status_code, 401)

    def test_whatsapp_webhook_accepts_valid_meta_signature(self) -> None:
        body = b"{}"
        digest = hmac.new(
            config.whatsapp_app_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

        response = self.client.post(
            "/api/webhooks/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": f"sha256={digest}",
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_legacy_validation_route_is_locked(self) -> None:
        fake_repo = SimpleNamespace(get_dossier=lambda _id: SimpleNamespace(id=_id))
        with patch("app.routers.dossiers.get_repo", return_value=fake_repo):
            response = self.client.post(
                "/api/dossiers/dossier-1/validate",
                headers={"X-API-Key": config.vigie_api_key},
            )
        self.assertEqual(response.status_code, 403)
        self.assertIn("M2S", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
