from __future__ import annotations

from core.market_snapshot_builder import build_market_snapshot, build_symbol_market_snapshot
from core.market_snapshot_schema import (
    SNAPSHOT_SCHEMA_VERSION,
    build_empty_market_snapshot_state,
    validate_market_snapshot,
)


def test_valid_snapshot_passes_validation():
    snapshot = build_market_snapshot(
        generated_at="2026-03-08T14:00:00Z",
        market_open=True,
        symbols_payload={
            "NIFTY": build_symbol_market_snapshot(
                spot=22500.0,
                ltp=22510.0,
                regime={"trend": "TREND", "volatility_state": "NORMAL", "confidence": 0.8},
            )
        },
        warnings=[],
        compute_ms=4.5,
        loop_id="loop-1",
    )

    ok, errors = validate_market_snapshot(snapshot)

    assert ok is True
    assert errors == []
    assert snapshot["schema_version"] == SNAPSHOT_SCHEMA_VERSION


def test_missing_required_top_level_field_fails_validation():
    snapshot = build_empty_market_snapshot_state("missing")
    snapshot.pop("generated_at", None)

    ok, errors = validate_market_snapshot(snapshot)

    assert ok is False
    assert "generated_at_missing_or_invalid" in errors


def test_missing_nested_subsections_are_normalized_by_builder():
    snapshot = build_market_snapshot(
        generated_at="2026-03-08T14:00:00Z",
        market_open=False,
        symbols_payload={"BANKNIFTY": {"spot": 48000.0}},
        warnings=["cross_asset_missing"],
        compute_ms=None,
        loop_id=None,
    )

    ok, errors = validate_market_snapshot(snapshot)
    payload = snapshot["symbols"]["BANKNIFTY"]

    assert ok is True
    assert errors == []
    assert payload["ohlc"] == {"open": None, "high": None, "low": None, "close": None}
    assert payload["regime"] == {"trend": None, "volatility_state": None, "confidence": None}
    assert payload["cross_asset"] == {"available": False, "signals": {}}
