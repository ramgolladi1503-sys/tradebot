from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path

from core.analytics.extreme_movers import (
    bot_visibility_and_rejects,
    build_extreme_movers_table,
    identify_extreme_movers,
    reconstruct_pre_move_features,
    replay_outcome_for_mover,
    write_outputs,
)


DAY = "2026-02-27"


def _ts_ms(minute_offset: int) -> int:
    base = datetime.fromisoformat(f"{DAY}T09:15:00+05:30")
    dt = base + timedelta(minutes=int(minute_offset))
    return int(dt.timestamp() * 1000.0)


def _quote_event(symbol: str, minute_offset: int, price: float, *, spread_bps: float = 20.0, quote_age: float = 1.0) -> dict:
    bid = price * (1.0 - spread_bps / 20000.0)
    ask = price * (1.0 + spread_bps / 20000.0)
    return {
        "event_type": "TICK",
        "symbol": symbol,
        "ts_epoch_ms": _ts_ms(minute_offset),
        "bid": round(bid, 4),
        "ask": round(ask, 4),
        "ltp": round(price, 4),
        "quote_age_sec": quote_age,
    }


def _fixture_events() -> list[dict]:
    events: list[dict] = []

    ce_symbol = "NIFTY-27FEB26-22500-CE"
    pe_symbol = "NIFTY-27FEB26-22500-PE"
    illiquid_symbol = "NIFTY-27FEB26-22300-CE"

    # Index context stream.
    for i in range(50):
        idx_price = 22100.0 + i * 3.0
        events.append(_quote_event("NIFTY", i, idx_price, spread_bps=5.0, quote_age=0.5))

    # Liquid CE extreme mover: open ~100, high ~200 with >30 observations.
    for i in range(45):
        if i < 15:
            px = 100.0 + i * 0.5
        elif i < 30:
            px = 132.0 + (i - 15) * 4.6
        else:
            px = 200.0 - (i - 30) * 1.1
        events.append(_quote_event(ce_symbol, i, px, spread_bps=25.0, quote_age=1.0))

    # Liquid PE moderate mover.
    for i in range(40):
        px = 85.0 + i * 0.9
        events.append(_quote_event(pe_symbol, i, px, spread_bps=30.0, quote_age=1.2))

    # Illiquid contract with huge move but too few observations.
    for i in range(20):
        px = 90.0 + i * 9.0
        events.append(_quote_event(illiquid_symbol, i, px, spread_bps=20.0, quote_age=1.0))

    # Rejection near CE T0.
    events.append(
        {
            "event_type": "REJECTED_TRADE",
            "symbol": ce_symbol,
            "ts_epoch_ms": _ts_ms(17),
            "gate_reasons": ["spread_pct_fail"],
            "reject_reason": "spread_pct_fail",
            "feed_state": "DEGRADED",
        }
    )
    return events


def test_identify_extreme_movers_filters_liquidity():
    events = _fixture_events()
    movers = identify_extreme_movers(events, DAY, top_k=10)
    symbols = {row["symbol"] for row in movers}
    assert "NIFTY-27FEB26-22500-CE" in symbols
    assert "NIFTY-27FEB26-22500-PE" in symbols
    assert "NIFTY-27FEB26-22300-CE" not in symbols


def test_reconstruct_pre_move_features_computes_t0_and_features():
    events = _fixture_events()
    movers = identify_extreme_movers(events, DAY, top_k=10)
    ce = next(row for row in movers if row["symbol"].endswith("CE"))
    features = reconstruct_pre_move_features(events, ce, lookback_min=30, trigger_pct=0.30)
    assert features["t0_ts_epoch_ms"] is not None
    assert features["t0_price"] is not None
    assert features["pre_return_5m"] is not None
    assert features["volume_burst_ratio"] is not None


def test_bot_visibility_reject_reason_extraction():
    events = _fixture_events()
    rows = build_extreme_movers_table(events, DAY, top_k=10, trigger_pct=0.30, lookback_min=30, horizon_min=45)
    ce = next(row for row in rows if row["symbol"].endswith("CE"))
    visibility = bot_visibility_and_rejects(events, ce)
    assert visibility["bot_saw"] is True
    assert visibility["bot_rejected"] is True
    assert "spread_pct_fail" in visibility["reject_reasons"]


def test_replay_outcome_computation():
    events = _fixture_events()
    rows = build_extreme_movers_table(events, DAY, top_k=10, trigger_pct=0.30, lookback_min=30, horizon_min=45)
    ce = next(row for row in rows if row["symbol"].endswith("CE"))
    outcome = replay_outcome_for_mover(events, ce, horizon_min=45, target_pct=0.30, sl_pct=0.15)
    assert outcome["outcome"] in {"HIT", "SL", "NO_HIT"}
    assert outcome["mfe"] is not None
    assert outcome["mae"] is not None


def test_outputs_written_atomic(tmp_path: Path):
    events = _fixture_events()
    rows = build_extreme_movers_table(events, DAY, top_k=10, trigger_pct=0.30, lookback_min=30, horizon_min=45)
    md_path, json_path = write_outputs(rows, tmp_path / "runtime" / "analytics" / "reports" / DAY)
    assert md_path.exists()
    assert json_path.exists()
    parsed = json.loads(json_path.read_text(encoding="utf-8"))
    assert parsed["day"] == DAY
    assert "rows" in parsed
    assert not list((tmp_path / "runtime" / "analytics" / "reports" / DAY).glob("*.tmp"))
