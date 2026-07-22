from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.generate_mean_reversion_trade_ledger import _ledger_row


def _active_trade() -> dict[str, object]:
    return {
        "signal_time": "2026-01-05T09:15:00",
        "entry_time": "2026-01-05T09:20:00",
        "entry_ts": pd.Timestamp("2026-01-05T09:20:00"),
        "signal_close": 99.0,
        "entry_price": 100.0,
        "entry_delay_bars": 1,
        "direction": "LONG",
        "stop_loss": 95.0,
        "target": 110.0,
        "setup_type": "FAILED_BREAKDOWN_LONG",
        "failed_level": 98.0,
        "reclaim_or_reject_level": 99.0,
        "htf_regime": "NEUTRAL/BULLISH",
        "rejection_quality": 0.7,
        "cost_hurdle_margin": 3.5,
        "planned_target_distance": 10.0,
        "trace_id": "trace",
        "parent_trace_id": "parent",
        "candidate_id": "candidate",
        "source_snapshot_id": "snapshot",
        "ranking_id": "ranking",
        "decision_id": "decision",
        "contract_key": "NIFTY_OPT_MOCK",
    }


def test_underlying_and_option_proxy_costs_are_kept_in_separate_units():
    row = _ledger_row(
        symbol="NIFTY",
        active_trade=_active_trade(),
        exit_ts=pd.Timestamp("2026-01-05T09:25:00"),
        exit_price=110.0,
        exit_reason="TARGET",
        time_stop_minutes=30,
        proxy_delta=0.5,
        proxy_exec_cost=1.5,
        underlying_cost=8.5,
        source_data_path=Path("runtime/upstox_candidate_replay/20260105/underlying/NIFTY_20260105.parquet"),
        v2_version="1.0",
    )

    assert row["underlying_gross_pnl"] == 10.0
    assert row["underlying_execution_cost"] == 8.5
    assert row["underlying_net_pnl_after_index_cost"] == 1.5
    assert row["proxy_option_gross_pnl"] == 5.0
    assert row["proxy_option_execution_cost"] == 1.5
    assert row["proxy_option_net_pnl"] == 3.5
    assert row["gross_pnl"] == row["underlying_gross_pnl"]
    assert row["costs"] == row["underlying_execution_cost"]
    assert row["net_pnl"] == row["underlying_net_pnl_after_index_cost"]


def test_ledger_rejects_nonpositive_holding_interval():
    with pytest.raises(ValueError, match="exit timestamp must be after entry timestamp"):
        _ledger_row(
            symbol="NIFTY",
            active_trade=_active_trade(),
            exit_ts=pd.Timestamp("2026-01-05T09:20:00"),
            exit_price=100.0,
            exit_reason="TIME_STOP",
            time_stop_minutes=30,
            proxy_delta=0.5,
            proxy_exec_cost=1.5,
            underlying_cost=8.5,
            source_data_path=Path("runtime/upstox_candidate_replay/20260105/underlying/NIFTY_20260105.parquet"),
            v2_version="1.0",
        )
