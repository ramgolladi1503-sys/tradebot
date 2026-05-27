from __future__ import annotations

import json

from core.events import append_event, read_events, write_json_atomic


def test_write_json_atomic_redacts_sensitive_values_recursively(tmp_path):
    target = tmp_path / "evidence.json"

    write_json_atomic(
        target,
        {
            "strategy": "breakout",
            "password": "plain-password",
            "nested": {
                "api_key": "plain-api-key",
                "safe": "visible",
                "items": [
                    {"client_secret": "plain-client-secret"},
                    {"token": "plain-token"},
                ],
            },
        },
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["strategy"] == "breakout"
    assert payload["password"] == "[REDACTED]"
    assert payload["nested"]["api_key"] == "[REDACTED]"
    assert payload["nested"]["safe"] == "visible"
    assert payload["nested"]["items"][0]["client_secret"] == "[REDACTED]"
    assert payload["nested"]["items"][1]["token"] == "[REDACTED]"
    assert "plain-password" not in target.read_text(encoding="utf-8")
    assert "plain-api-key" not in target.read_text(encoding="utf-8")
    assert "plain-client-secret" not in target.read_text(encoding="utf-8")
    assert "plain-token" not in target.read_text(encoding="utf-8")


def test_append_event_redacts_sensitive_values_in_events_jsonl(tmp_path):
    target = tmp_path / "events.jsonl"

    append_event(
        "auth_check",
        {
            "run_id": "run-1",
            "authorization": "Bearer plain-token",
            "nested": {"session_cookie": "plain-cookie"},
        },
        path=target,
    )

    rows = read_events(path=target, run_id="run-1")
    assert len(rows) == 1
    payload = rows[0]["payload"]
    assert payload["authorization"] == "[REDACTED]"
    assert payload["nested"]["session_cookie"] == "[REDACTED]"
    raw = target.read_text(encoding="utf-8")
    assert "Bearer plain-token" not in raw
    assert "plain-cookie" not in raw
