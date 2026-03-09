from __future__ import annotations

from core.decision_snapshot import DecisionSnapshot
from core.gates.quote_age_gate import validate_quote_age


def _snapshot(*, index_age_ms: float, option_age_ms: float) -> DecisionSnapshot:
    return DecisionSnapshot.build(
        timestamp=1_772_700_001.0,
        index_price=24_850.0,
        option_bid=120.0,
        option_ask=121.0,
        option_ltp=120.5,
        spread=0.008,
        depth={"bid_qty": 50, "ask_qty": 45},
        index_quote_age_ms=index_age_ms,
        option_quote_age_ms=option_age_ms,
        source="kite_ws",
    )


def test_validate_quote_age_passes_for_fresh_quotes():
    snap = _snapshot(index_age_ms=350.0, option_age_ms=800.0)
    out = validate_quote_age(snap, {"index_max_age_ms": 1500.0, "option_max_age_ms": 1500.0})
    assert out["pass"] is True
    assert out["reason_code"] is None


def test_validate_quote_age_fails_for_stale_option():
    snap = _snapshot(index_age_ms=300.0, option_age_ms=1700.0)
    out = validate_quote_age(snap, {"index_max_age_ms": 1500.0, "option_max_age_ms": 1500.0})
    assert out["pass"] is False
    assert out["reason_code"] == "STALE_OPTION_LTP"
    assert out["option_age_ms"] == 1700.0


def test_validate_quote_age_fails_for_stale_index():
    snap = _snapshot(index_age_ms=2200.0, option_age_ms=200.0)
    out = validate_quote_age(snap, {"index_max_age_ms": 1500.0, "option_max_age_ms": 1500.0})
    assert out["pass"] is False
    assert out["reason_code"] == "STALE_INDEX"
    assert out["index_age_ms"] == 2200.0

