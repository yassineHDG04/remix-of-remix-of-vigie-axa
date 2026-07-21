import hashlib
import hmac
import unittest

from fastapi import HTTPException

from app.config import config
from app.security import require_api_key, valid_m2s_signature, valid_whatsapp_signature


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.old_api_key = config.vigie_api_key
        self.old_whatsapp_secret = config.whatsapp_app_secret
        self.old_m2s_secret = config.m2s_webhook_secret

    def tearDown(self):
        config.vigie_api_key = self.old_api_key
        config.whatsapp_app_secret = self.old_whatsapp_secret
        config.m2s_webhook_secret = self.old_m2s_secret

    def test_api_key_is_fail_closed_when_not_configured(self):
        config.vigie_api_key = ""
        with self.assertRaises(HTTPException) as ctx:
            require_api_key(None, None)
        self.assertEqual(ctx.exception.status_code, 503)

    def test_api_key_accepts_header_and_bearer(self):
        config.vigie_api_key = "secret-test"
        require_api_key("secret-test", None)
        require_api_key(None, "Bearer secret-test")

    def test_api_key_rejects_wrong_value(self):
        config.vigie_api_key = "secret-test"
        with self.assertRaises(HTTPException) as ctx:
            require_api_key("wrong", None)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_whatsapp_signature(self):
        config.whatsapp_app_secret = "meta-secret"
        payload = b'{"object":"whatsapp_business_account"}'
        signature = "sha256=" + hmac.new(
            b"meta-secret",
            payload,
            hashlib.sha256,
        ).hexdigest()
        self.assertTrue(valid_whatsapp_signature(payload, signature))
        self.assertFalse(valid_whatsapp_signature(payload + b"x", signature))

    def test_m2s_signature(self):
        config.m2s_webhook_secret = "m2s-secret"
        payload = b'{"event_id":"evt-1"}'
        signature = "sha256=" + hmac.new(
            b"m2s-secret",
            payload,
            hashlib.sha256,
        ).hexdigest()
        self.assertTrue(valid_m2s_signature(payload, signature))
        self.assertFalse(valid_m2s_signature(payload + b"x", signature))


if __name__ == "__main__":
    unittest.main()
