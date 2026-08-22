from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from core import live_session_attestation_producer as producer

IST = ZoneInfo("Asia/Kolkata")
D = date(2026, 8, 24)
SHA = "a" * 40
KEY = "trusted-live-attestation-key-32-bytes-minimum"
TOKENS = producer.TRUSTED_INDEX_TOKENS


def evidence():
    token_by_symbol = dict(TOKENS)
    lifecycle = {}
    for symbol, token in TOKENS.items():
        lifecycle[str(token)] = {
            "feed_session_id": "kite-depth-test",
            "subscribe_call_succeeded_epoch": 1.0,
            "first_post_request_tick_epoch": 2.0,
            "first_full_payload_epoch": 3.0,
            "final_current_generation_local_mode_is_full": True,
        }
    return {
        "subscription_evidence_id": "sub-proof-test",
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "feed_session_id": "kite-depth-test",
        "token_by_symbol": token_by_symbol,
        "token_lifecycle": lifecycle,
    }


def when():
    return datetime(2026, 8, 24, 15, 31, tzinfo=IST)


def test_builds_only_from_exact_three_index_subscription_truth():
    att = producer.build_live_session_attestation(
        session_date=D,
        code_sha=SHA,
        subscription_evidence=evidence(),
        attested_at_ist=when(),
        attestation_key=KEY,
    )
    assert att["schema"] == "tradebot-live-session-attestation-v1"
    assert att["source"] == "tradebot_live_runtime_bridge"
    assert att["status"] == "VERIFIED_LIVE_SESSION"
    assert att["live_feed_session_id"] == "kite-depth-test"
    assert att["indices"]["NIFTY"]["instrument_token"] == 256265
    assert att["broker_write_authority"] is False
    assert att["order_authority"] is False
    assert att["paper_authorized"] is False
    assert att["live_authorized"] is False
    assert len(att["attestation_hmac_sha256"]) == 64


def test_wrong_positive_token_is_rejected():
    row = evidence()
    row["token_by_symbol"]["NIFTY"] = 999999
    with pytest.raises(ValueError, match="LIVE_INDEX_IDENTITY_INVALID:NIFTY"):
        producer.build_live_session_attestation(
            session_date=D, code_sha=SHA, subscription_evidence=row,
            attested_at_ist=when(), attestation_key=KEY,
        )


@pytest.mark.parametrize("field", [
    "subscribe_call_succeeded_epoch",
    "first_post_request_tick_epoch",
    "first_full_payload_epoch",
])
def test_missing_request_scoped_lifecycle_proof_is_rejected(field):
    row = evidence()
    row["token_lifecycle"][str(TOKENS["BANKNIFTY"])][field] = None
    with pytest.raises(ValueError, match="LIVE_INDEX_FULL_SUBSCRIPTION_UNPROVEN:BANKNIFTY"):
        producer.build_live_session_attestation(
            session_date=D, code_sha=SHA, subscription_evidence=row,
            attested_at_ist=when(), attestation_key=KEY,
        )


def test_feed_session_mismatch_is_rejected():
    row = evidence()
    row["token_lifecycle"][str(TOKENS["SENSEX"])]["feed_session_id"] = "other"
    with pytest.raises(ValueError, match="LIVE_INDEX_SESSION_MISMATCH:SENSEX"):
        producer.build_live_session_attestation(
            session_date=D, code_sha=SHA, subscription_evidence=row,
            attested_at_ist=when(), attestation_key=KEY,
        )


def test_before_1530_and_non_exact_sha_fail_closed():
    with pytest.raises(ValueError, match="SESSION_NOT_COMPLETE_FOR_ATTESTATION"):
        producer.build_live_session_attestation(
            session_date=D, code_sha=SHA, subscription_evidence=evidence(),
            attested_at_ist=datetime(2026, 8, 24, 15, 29, tzinfo=IST),
            attestation_key=KEY,
        )
    with pytest.raises(ValueError, match="CODE_SHA_EXACT_REQUIRED"):
        producer.build_live_session_attestation(
            session_date=D, code_sha="UNKNOWN", subscription_evidence=evidence(),
            attested_at_ist=when(), attestation_key=KEY,
        )


def test_short_or_missing_key_fails_closed(monkeypatch):
    monkeypatch.delenv("TRADEBOT_LIVE_SESSION_ATTESTATION_KEY", raising=False)
    with pytest.raises(ValueError, match="TRUSTED_LIVE_ATTESTATION_KEY_REQUIRED"):
        producer.build_live_session_attestation(
            session_date=D, code_sha=SHA, subscription_evidence=evidence(),
            attested_at_ist=when(),
        )


def test_runtime_adapter_uses_kite_subscription_authority(monkeypatch):
    from core import kite_depth_ws

    seen = {}
    def fake(tokens):
        seen.update(tokens)
        return evidence()
    monkeypatch.setattr(kite_depth_ws, "market_event_graph_subscription_evidence_for_tokens", fake)
    att = producer.produce_from_kite_depth_ws(
        session_date=D, code_sha=SHA, attested_at_ist=when(), attestation_key=KEY
    )
    assert seen == TOKENS
    assert att["live_feed_session_id"] == "kite-depth-test"


def test_immutable_write_is_idempotent_and_conflict_fails(tmp_path):
    att = producer.build_live_session_attestation(
        session_date=D, code_sha=SHA, subscription_evidence=evidence(),
        attested_at_ist=when(), attestation_key=KEY,
    )
    path = tmp_path / "attestation.json"
    assert producer.write_attestation(path, att)["status"] == "SEALED"
    assert producer.write_attestation(path, att)["status"] == "IDEMPOTENT"
    changed = dict(att)
    changed["live_feed_session_id"] = "forged"
    with pytest.raises(FileExistsError, match="IMMUTABLE_ATTESTATION_CONFLICT"):
        producer.write_attestation(path, changed)
