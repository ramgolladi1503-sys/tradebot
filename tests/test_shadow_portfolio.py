from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import pytest

from core.analytics.schema import TradeIntentEvent
from core.analytics.shadow_portfolio import build_shadow_portfolio_report, simulate_shadow_trade


def _ts_ms_ist(day: str, hh: int, mm: int, ss: int = 0) -> int:
    dt = datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:{ss:02d}+05:30")
    return int(dt.timestamp() * 1000.0)


def _candles(*rows: tuple[int, float, float, float, float]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["time_ms", "open", "high", "low", "close"])


def test_simulate_shadow_trade_target_hit_with_spread_slippage() -> None:
    ts_ms = 1_772_272_400_000
    trade = {
        "ts_epoch_ms": ts_ms,
        "is_sell": False,
        "entry_price": 100.0,
        "target_price": 102.0,
        "stop_price": 99.0,
        "mark_price": 100.0,
        "spread_pct": 0.01,
        "qty_units": 1.0,
    }
    candles = _candles(
        (ts_ms, 100.0, 100.2, 99.9, 100.0),
        (ts_ms + 60_000, 100.1, 102.5, 100.0, 102.0),
    )

    result = simulate_shadow_trade(
        trade,
        candles,
        lookahead_minutes=5,
        slippage_model="spread",
        slippage_bps=0.0,
        spread_slippage_mult=0.5,
        entry_mode="MARK",
    )

    assert result["status"] == "SIMULATED"
    assert result["exit_reason"] == "TARGET_HIT"
    assert result["target_hit"] is True
    assert result["stop_hit"] is False
    assert result["entry_exec_price"] == pytest.approx(100.5)
    assert result["exit_exec_price"] == pytest.approx(101.49)
    assert result["pnl_points"] == pytest.approx(0.99)
    assert result["pnl_value"] == pytest.approx(0.99)


def test_build_shadow_portfolio_report_deterministic_equity_curve(tmp_path) -> None:
    date_key = "2026-02-28"
    ts_1 = _ts_ms_ist(date_key, 10, 0)
    ts_2 = _ts_ms_ist(date_key, 10, 10)

    advisory_target = TradeIntentEvent(
        trade_key="NIFTY|2026-03-05|25000|CE|BUY|alpha_a",
        event_id="evt_advisory_target",
        intent="advisory",
        ts_epoch_ms=ts_1,
        symbol="NIFTY",
        expiry="2026-03-05",
        strike=25000.0,
        option_type="CE",
        side="BUY",
        source="unit_test",
        metrics_snapshot={
            "entry_price": 100.0,
            "target": 102.0,
            "stop": 99.0,
            "mark_price": 100.0,
            "strategy_id": "alpha_a",
            "spread_pct": 0.0,
            "qty_units": 1.0,
        },
    )
    advisory_stop = TradeIntentEvent(
        trade_key="NIFTY|2026-03-05|25100|CE|BUY|alpha_b",
        event_id="evt_advisory_stop",
        intent="advisory",
        ts_epoch_ms=ts_2,
        symbol="NIFTY",
        expiry="2026-03-05",
        strike=25100.0,
        option_type="CE",
        side="BUY",
        source="unit_test",
        metrics_snapshot={
            "entry_price": 104.0,
            "target": 106.0,
            "stop": 103.0,
            "mark_price": 104.0,
            "strategy_id": "alpha_b",
            "spread_pct": 0.0,
            "qty_units": 1.0,
        },
    )
    rejected = TradeIntentEvent(
        trade_key="NIFTY|2026-03-05|25200|CE|BUY|alpha_r",
        event_id="evt_rejected",
        intent="rejected",
        ts_epoch_ms=ts_2,
        symbol="NIFTY",
        expiry="2026-03-05",
        strike=25200.0,
        option_type="CE",
        side="BUY",
        source="unit_test",
        metrics_snapshot={
            "entry_price": 200.0,
            "target": 210.0,
            "stop": 190.0,
            "mark_price": 200.0,
            "strategy_id": "alpha_r",
        },
    )

    candles_map = {
        "evt_advisory_target": _candles(
            (ts_1, 100.0, 100.1, 99.9, 100.0),
            (ts_1 + 60_000, 100.2, 102.5, 100.1, 102.2),
        ),
        "evt_advisory_stop": _candles(
            (ts_2, 104.0, 104.2, 103.8, 104.0),
            (ts_2 + 60_000, 103.8, 104.0, 102.8, 103.0),
        ),
        "evt_rejected": _candles(
            (ts_2, 200.0, 201.0, 198.0, 199.0),
            (ts_2 + 60_000, 199.0, 199.5, 189.0, 191.0),
        ),
    }

    def _provider(trade: dict, start_ms: int, end_ms: int, interval: str) -> pd.DataFrame:
        del start_ms, end_ms, interval
        event_id = str(trade.get("event_id") or "")
        return candles_map.get(event_id, pd.DataFrame())

    output_path = tmp_path / "runtime" / "analytics" / "reports" / date_key / "shadow_portfolio.json"
    payload = build_shadow_portfolio_report(
        date_key,
        events=[advisory_target, advisory_stop, rejected],
        include_advisory=True,
        include_rejected=False,
        lookahead_minutes=15,
        slippage_model="bps",
        slippage_bps=0.0,
        spread_slippage_mult=0.0,
        starting_equity=1000.0,
        candle_provider=_provider,
        output_path=output_path,
    )

    assert payload["counts"]["scanned_events"] == 3
    assert payload["counts"]["eligible_events"] == 2
    assert payload["counts"]["simulated_trades"] == 2
    assert payload["summary"]["total_pnl_points"] == 1.0
    assert payload["summary"]["total_pnl_value"] == 1.0
    assert payload["summary"]["hit_rate"] == 0.5
    assert payload["summary"]["ending_equity"] == 1001.0
    assert payload["summary"]["max_drawdown_points"] == 1.0
    assert len(payload["equity_curve"]) == 2
    assert all(row["intent"] == "advisory" for row in payload["rows"])

    by_strategy = {row["strategy_id"]: row for row in payload["per_strategy"]}
    assert by_strategy["alpha_a"]["total_pnl_points"] == 2.0
    assert by_strategy["alpha_b"]["total_pnl_points"] == -1.0

    assert output_path.exists()
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["summary"]["ending_equity"] == 1001.0
    assert written["counts"]["simulated_trades"] == 2


def test_build_shadow_portfolio_report_include_rejected_toggle(tmp_path) -> None:
    date_key = "2026-02-28"
    ts_ms = _ts_ms_ist(date_key, 11, 0)
    rejected = TradeIntentEvent(
        trade_key="NIFTY|2026-03-05|25300|PE|SELL|alpha_r",
        event_id="evt_rej_only",
        intent="rejected",
        ts_epoch_ms=ts_ms,
        symbol="NIFTY",
        expiry="2026-03-05",
        strike=25300.0,
        option_type="PE",
        side="SELL",
        source="unit_test",
        metrics_snapshot={
            "entry_price": 120.0,
            "target": 118.0,
            "stop": 121.0,
            "mark_price": 120.0,
            "strategy_id": "alpha_r",
        },
    )

    def _provider(trade: dict, start_ms: int, end_ms: int, interval: str) -> pd.DataFrame:
        del trade, start_ms, end_ms, interval
        return _candles((ts_ms, 120.0, 120.2, 117.8, 118.5))

    payload = build_shadow_portfolio_report(
        date_key,
        events=[rejected],
        include_advisory=False,
        include_rejected=True,
        lookahead_minutes=15,
        slippage_model="bps",
        slippage_bps=0.0,
        spread_slippage_mult=0.0,
        starting_equity=500.0,
        candle_provider=_provider,
        output_path=tmp_path / "shadow_portfolio.json",
    )

    assert payload["counts"]["eligible_events"] == 1
    assert payload["counts"]["simulated_trades"] == 1
    assert payload["rows"][0]["intent"] == "rejected"
    assert payload["rows"][0]["exit_reason"] == "TARGET_HIT"
