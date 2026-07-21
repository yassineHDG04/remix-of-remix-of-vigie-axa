import unittest
from types import SimpleNamespace

from app.providers.call_routing import attempts_exhausted, next_channel


def attempt(channel: str, fallback_reason: str | None = None):
    return SimpleNamespace(call_channel_used=channel, fallback_reason=fallback_reason)


class CallRoutingTests(unittest.TestCase):
    def test_sip_strategy_never_uses_whatsapp(self):
        self.assertEqual(next_channel("sip", [], 2), "sip")

    def test_mixed_strategy_uses_whatsapp_then_sip(self):
        self.assertEqual(next_channel("whatsapp_then_sip", [], 2), "whatsapp")
        self.assertEqual(
            next_channel("whatsapp_then_sip", [attempt("whatsapp")], 2),
            "whatsapp",
        )
        self.assertEqual(
            next_channel(
                "whatsapp_then_sip",
                [attempt("whatsapp"), attempt("whatsapp")],
                2,
            ),
            "sip",
        )

    def test_provider_rejection_forces_sip_fallback(self):
        self.assertEqual(
            next_channel(
                "whatsapp_then_sip",
                [attempt("whatsapp", "meta_permission_refused")],
                3,
            ),
            "sip",
        )

    def test_mixed_strategy_handoff_only_after_sip_quota(self):
        whatsapp_only = [attempt("whatsapp"), attempt("whatsapp")]
        self.assertFalse(
            attempts_exhausted(
                "whatsapp_then_sip",
                whatsapp_only,
                sip_max_attempts=2,
                whatsapp_max_attempts=2,
            )
        )
        all_attempts = whatsapp_only + [attempt("sip"), attempt("sip")]
        self.assertTrue(
            attempts_exhausted(
                "whatsapp_then_sip",
                all_attempts,
                sip_max_attempts=2,
                whatsapp_max_attempts=2,
            )
        )


if __name__ == "__main__":
    unittest.main()
