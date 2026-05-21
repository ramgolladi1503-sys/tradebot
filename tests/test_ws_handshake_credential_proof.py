from __future__ import annotations

from pathlib import Path

from core.ws_handshake_credential_proof import (
    build_handshake_credential_proof,
    build_ws_auth_failure_proof_event,
    build_ws_handshake_attempt_event,
    extract_latest_auth_failure_proof_from_lines,
    extract_latest_handshake_proof_from_lines,
    read_recent_log_lines,
)


def _public_key_sample() -> str:
    return "abcdefghijkl-oi2n"


def _token_sample() -> str:
    return "abcdefghijklmnopqrstuvwxyz12R7J6"


def test_build_handshake_credential_proof_strips_edges_and_flags_internal_whitespace():
    proof = build_handshake_credential_proof(
        public_key=" key-oi2n\n",
        access_token=" token R7J6\n",
        source="unit",
    )

    assert proof.public_key_tail4 == "oi2n"
    assert proof.access_token_tail4 == "R7J6"
    assert proof.access_token_len == len("token R7J6")
    assert proof.access_token_has_internal_whitespace is True
    assert proof.source == "unit"


def test_handshake_attempt_event_contains_no_full_secret():
    event = build_ws_handshake_attempt_event(
        public_key=_public_key_sample(),
        access_token=_token_sample(),
        token_count=70,
        profile_verified=True,
    )

    assert event["event"] == "FEED_WS_HANDSHAKE_CREDENTIAL_PROOF"
    assert event["public_key_tail4"] == "oi2n"
    assert event["access_token_tail4"] == "R7J6"
    assert event["access_token_len"] == 32
    assert event["access_token_has_internal_whitespace"] is False
    assert event["token_count"] == 70
    assert event["profile_verified"] is True
    assert _token_sample() not in str(event)


def test_auth_failure_event_carries_safe_credential_context():
    event = build_ws_auth_failure_proof_event(
        public_key=_public_key_sample(),
        access_token=_token_sample(),
        code=1006,
        reason="WebSocket connection upgrade failed (403 - Forbidden)",
        auth_required_latch=True,
    )

    assert event["event"] == "FEED_WS_AUTH_FAILURE_PROOF"
    assert event["public_key_tail4"] == "oi2n"
    assert event["access_token_tail4"] == "R7J6"
    assert event["code"] == 1006
    assert "403 - Forbidden" in event["reason"]
    assert event["auth_required_latch"] is True
    assert _token_sample() not in str(event)


def test_extract_latest_handshake_and_failure_proof_from_json_lines():
    lines = [
        '{"event":"FEED_WS_HANDSHAKE_CREDENTIAL_PROOF","public_key_tail4":"old1"}',
        '{"event":"FEED_WS_AUTH_FAILURE_PROOF","code":1006,"access_token_tail4":"R7J6"}',
        '{"event":"FEED_WS_HANDSHAKE_CREDENTIAL_PROOF","public_key_tail4":"oi2n","access_token_tail4":"R7J6"}',
    ]

    assert extract_latest_handshake_proof_from_lines(lines)["public_key_tail4"] == "oi2n"
    assert extract_latest_auth_failure_proof_from_lines(lines)["code"] == 1006


def test_extract_key_value_fallback_and_read_recent_lines(tmp_path):
    path = Path(tmp_path) / "depth.log"
    path.write_text(
        "\n".join(
            [
                "noise",
                "FEED_WS_HANDSHAKE_CREDENTIAL_PROOF public_key_tail4=oi2n access_token_tail4=R7J6 access_token_len=32",
            ]
        ),
        encoding="utf-8",
    )

    lines = read_recent_log_lines(path, max_lines=5)
    proof = extract_latest_handshake_proof_from_lines(lines)

    assert proof["event"] == "FEED_WS_HANDSHAKE_CREDENTIAL_PROOF"
    assert proof["public_key_tail4"] == "oi2n"
    assert proof["access_token_tail4"] == "R7J6"
    assert proof["access_token_len"] == "32"
