from __future__ import annotations

import json

from core.sensitive_redaction import REDACTED, redact_sensitive_data, redact_text


def test_redacts_sensitive_keys_recursively():
    payload = {
        "safe": "visible",
        "access_token": "abc123",
        "nested": {
            "api_key": "kite-key",
            "items": [{"session_id": "sess-1"}, {"symbol": "NIFTY"}],
        },
    }

    redacted = redact_sensitive_data(payload)

    assert redacted["safe"] == "visible"
    assert redacted["access_token"] == REDACTED
    assert redacted["nested"]["api_key"] == REDACTED
    assert redacted["nested"]["items"][0]["session_id"] == REDACTED
    assert redacted["nested"]["items"][1]["symbol"] == "NIFTY"


def test_redacts_token_like_text_before_json_logging():
    payload = {
        "reason": "request failed with Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
        "error": "access_token=abc123 secret:xyz789",
    }

    redacted = redact_sensitive_data(payload)
    serialized = json.dumps(redacted)

    assert "abcdefghijklmnopqrstuvwxyz" not in serialized
    assert "abc123" not in serialized
    assert "xyz789" not in serialized
    assert REDACTED in serialized


def test_redact_text_preserves_non_sensitive_content():
    assert redact_text("NIFTY feed stale") == "NIFTY feed stale"
