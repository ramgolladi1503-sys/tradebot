from pathlib import Path

import pytest

from core.live_consumer_contract import CANONICAL_CONSUMERS
from core.read_only_subscription_authority import build_subscription_authority


SHA = "a" * 40
AUTH = {"session_date": "2026-08-24", "source_sha": SHA, "verdict": "PASS", "raw_instrument_sha256": "b" * 64}
ROWS = [
    {"instrument_token": 256265, "name": "NIFTY", "exchange": "NSE", "tradingsymbol": "NIFTY 50"},
    {"instrument_token": 260105, "name": "BANKNIFTY", "exchange": "NSE", "tradingsymbol": "NIFTY BANK"},
]


def test_current_session_authority_has_provenance_and_cas_requirements(tmp_path: Path):
    payload = build_subscription_authority(
        rows=ROWS, session_id="session", session_date="2026-08-24", source_sha=SHA,
        instrument_authority=AUTH, consumer_registry=CANONICAL_CONSUMERS,
        output_path=tmp_path / "subscription_tokens.json",
    )
    assert payload["subscription_tokens"] == [256265, 260105]
    assert payload["subscription_count"] == 2
    assert {item["consumer_id"] for item in payload["requirements"]} >= {"regime", "strategies", "cas_v2"}
    assert all(item["instrument_authority_sha256"] == AUTH["raw_instrument_sha256"] for item in payload["token_provenance"])
    assert payload["broker_write_authority"] is False
    assert payload["order_authority"] is False


@pytest.mark.parametrize("field, value, error", [
    ("session_date", "2026-08-23", "SESSION_MISMATCH"),
    ("source_sha", "c" * 40, "SOURCE_SHA_MISMATCH"),
])
def test_stale_or_mismatched_authority_fails_closed(tmp_path: Path, field: str, value: str, error: str):
    authority = dict(AUTH)
    authority[field] = value
    with pytest.raises(ValueError, match=error):
        build_subscription_authority(
            rows=ROWS, session_id="session", session_date="2026-08-24", source_sha=SHA,
            instrument_authority=authority, consumer_registry=CANONICAL_CONSUMERS,
            output_path=tmp_path / "subscription_tokens.json",
        )


def test_missing_required_symbol_fails_closed(tmp_path: Path):
    with pytest.raises(ValueError, match="REQUIRED_SYMBOL_MISSING:BANKNIFTY"):
        build_subscription_authority(
            rows=ROWS[:1], session_id="session", session_date="2026-08-24", source_sha=SHA,
            instrument_authority=AUTH, consumer_registry=CANONICAL_CONSUMERS,
            output_path=tmp_path / "subscription_tokens.json",
        )


def test_ambiguous_identity_fails_closed(tmp_path: Path):
    with pytest.raises(ValueError, match="AMBIGUOUS_IDENTITY:NIFTY"):
        build_subscription_authority(
            rows=ROWS + [{"instrument_token": 999, "name": "NIFTY", "exchange": "NSE"}],
            session_id="session", session_date="2026-08-24", source_sha=SHA,
            instrument_authority=AUTH, consumer_registry=CANONICAL_CONSUMERS,
            output_path=tmp_path / "subscription_tokens.json",
        )
