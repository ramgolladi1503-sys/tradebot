from __future__ import annotations

from pathlib import Path

from core.expectancy import setup_fingerprint


def _row(**overrides: object) -> dict[str, object]:
    row = {
        "candidate_id": "cand-1",
        "trade_id": "trade-1",
        "strategy_family": "breakout",
        "regime": "LIVE",
        "volatility": 0.42,
        "volume": 12500,
        "spread_pct": 0.18,
        "signal_epoch": 1_717_173_600.0,
        "expiry_type": "WEEKLY",
        "direction": "BUY",
        "index": "NIFTY",
        "option_type": "CE",
    }
    row.update(overrides)
    return row


def test_same_input_produces_same_setup_id() -> None:
    first = setup_fingerprint.build_setup_fingerprint(_row())
    second = setup_fingerprint.build_setup_fingerprint(_row())
    assert first.setup_id == second.setup_id
    assert first.setup_family == "breakout"
    assert first.strategy_family == "breakout"


def test_different_regime_changes_setup_id() -> None:
    baseline = setup_fingerprint.build_setup_fingerprint(_row(regime="LIVE"))
    altered = setup_fingerprint.build_setup_fingerprint(_row(regime="TREND"))
    assert baseline.setup_id != altered.setup_id
    assert baseline.regime_bucket == "LIVE"
    assert altered.regime_bucket == "TREND"


def test_different_spread_bucket_changes_setup_id() -> None:
    baseline = setup_fingerprint.build_setup_fingerprint(_row(spread_pct=0.0008))
    altered = setup_fingerprint.build_setup_fingerprint(_row(spread_pct=0.01))
    assert baseline.setup_id != altered.setup_id
    assert baseline.spread_bucket == "TIGHT"
    assert altered.spread_bucket == "VERY_WIDE"


def test_missing_fields_use_unknown_buckets_without_crashing() -> None:
    fingerprint = setup_fingerprint.build_setup_fingerprint({"strategy_family": "mean_reversion"})
    assert fingerprint.setup_id
    assert fingerprint.setup_family == "mean-reversion"
    assert fingerprint.regime_bucket == "UNKNOWN"
    assert fingerprint.volatility_bucket == "UNKNOWN"
    assert fingerprint.volume_bucket == "UNKNOWN"
    assert fingerprint.spread_bucket == "UNKNOWN"
    assert fingerprint.time_of_day_bucket == "UNKNOWN"
    assert fingerprint.expiry_bucket == "UNKNOWN"
    assert fingerprint.direction_bucket == "UNKNOWN"
    assert fingerprint.index_bucket == "UNKNOWN"
    assert fingerprint.option_type_bucket == "UNKNOWN"


def test_attach_setup_fingerprint_preserves_row_and_metadata() -> None:
    enriched = setup_fingerprint.attach_setup_fingerprint(_row())
    assert enriched["setup_id"].startswith("breakout__LIVE__")
    assert enriched["setup_family"] == "breakout"
    assert enriched["metadata"]["setup_fingerprint"]["setup_id"] == enriched["setup_id"]


def test_setup_fingerprint_module_avoids_broker_and_order_imports() -> None:
    source = Path(setup_fingerprint.__file__).read_text(encoding="utf-8")
    forbidden = ("broker", "order_router", "live_trade", "kite", "upstox")
    assert not any(f"from core.{name}" in source or f"import {name}" in source for name in forbidden)
