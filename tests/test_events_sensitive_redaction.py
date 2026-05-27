from __future__ import annotations

import json

from core.events import write_json_atomic

REDACTED = "[REDACTED]"


def test_write_json_atomic_preserves_safe_fields_and_redacts_sensitive_contract(tmp_path):
    target = tmp_path / "evidence.json"
    original_payload = {
        "strategy": "breakout",
        "sample_count": 7,
        "password": "plain-password",
        "nested": {
            "api_key": "plain-api-key",
            "safe": "visible",
            "items": [
                {"client_secret": "plain-client-secret", "score": 0.91},
                {"token": "plain-token", "status": "review"},
            ],
        },
    }

    returned_path = write_json_atomic(target, original_payload)

    assert returned_path == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {
        "strategy": "breakout",
        "sample_count": 7,
        "password": REDACTED,
        "nested": {
            "api_key": REDACTED,
            "safe": "visible",
            "items": [
                {"client_secret": REDACTED, "score": 0.91},
                {"token": REDACTED, "status": "review"},
            ],
        },
    }
    assert original_payload["password"] == "plain-password"
    assert original_payload["nested"]["api_key"] == "plain-api-key"
    assert original_payload["nested"]["items"][0]["client_secret"] == "plain-client-secret"
    assert original_payload["nested"]["items"][1]["token"] == "plain-token"
