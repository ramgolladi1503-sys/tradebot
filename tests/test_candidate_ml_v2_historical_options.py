from __future__ import annotations

import pandas as pd
import pytest

from core.analytics.candidate_ml_v2.dataset import feature_columns
from core.analytics.candidate_ml_v2.historical_option_reconstruction import (
    HistoricalOptionDataError,
    build_historical_option_datasets,
)


def _intent(identity: str, minute: int, *, option_type: str = "CE") -> dict[str, object]:
    signal = pd.Timestamp(f"2026-01-05 09:{minute:02d}:00", tz="Asia/Kolkata")
    direction = "BUY_CALL" if option_type == "CE" else "BUY_PUT"
    return {
        "strategy_id": "VWAP_RECLAIM",
        "underlying": "NIFTY",
        "signal_timestamp": signal.isoformat(),
        "earliest_entry_timestamp": (signal + pd.Timedelta(minutes=1)).isoformat(),
        "direction": direction,
        "signal_time_underlying_price": 24012.0,
        "intended_option_type": option_type,
        "signal_identity_hash": identity,
        "candidate_raw_score": 0.61,
        "candidate_confidence_score": 0.64,
        "candidate_price_structure_score": 0.67,
        "candidate_blockers": "[]",
        "candidate_warnings": '["LOW_VOLUME"]',
    }


def _trade(
    identity: str,
    minute: int,
    *,
    strike: float,
    option_type: str = "CE",
    unit_net_pnl: float = 10.0,
) -> dict[str, object]:
    signal = pd.Timestamp(f"2026-01-05 09:{minute:02d}:00", tz="Asia/Kolkata")
    entry = signal + pd.Timedelta(minutes=1)
    return {
        "strategy_id": "VWAP_RECLAIM",
        "signal_identity_hash": identity,
        "signal_timestamp": signal.isoformat(),
        "underlying": "NIFTY",
        "option_type": option_type,
        "expiry": "2026-01-06",
        "atm_strike": 24000.0,
        "strike": strike,
        "entry_timestamp": entry.isoformat(),
        "entry_price": 100.0,
        "exit_timestamp": (entry + pd.Timedelta(minutes=10)).isoformat(),
        "exit_price": 110.0,
        "exit_reason": "target" if unit_net_pnl > 0 else "stop",
        "unit_net_pnl": unit_net_pnl,
        "unit_friction_cost": 0.10,
        "net_return_pct": unit_net_pnl,
        "partition": "development",
    }


def test_exact_and_nearest_strike_evidence_are_physically_separated() -> None:
    intents = pd.DataFrame(
        [
            _intent("exact", 20),
            _intent("proxy", 25, option_type="PE"),
            _intent("unmatched", 30),
            _intent("too_far", 35),
        ]
    )
    trades = pd.DataFrame(
        [
            _trade("exact", 20, strike=24000.0),
            _trade("proxy", 25, strike=24050.0, option_type="PE"),
            _trade("too_far", 35, strike=24200.0),
        ]
    )

    exact, proxy, evidence = build_historical_option_datasets(
        intents,
        trades,
        nearest_proxy_max_points=100.0,
    )

    assert exact.shape[0] == 1
    assert proxy.shape[0] == 1
    assert exact.iloc[0]["event_id"] == "exact"
    assert proxy.iloc[0]["event_id"] == "proxy"
    assert exact.iloc[0]["match_quality"] == "EXACT_ATM"
    assert proxy.iloc[0]["match_quality"] == "NEAREST_STRIKE_PROXY"
    assert evidence["unmatched_intents"] == 1
    assert evidence["distance_rejected_rows"] == 1
    assert evidence["reconciliation_passed"] is True
    assert evidence["nearest_strike_authority"] == "SEPARATE_PROXY_ONLY_NOT_MIXED_WITH_EXACT_ATM"


def test_real_option_outcome_builds_post_cost_r_without_future_features() -> None:
    intents = pd.DataFrame([_intent("winner", 20)])
    trades = pd.DataFrame([_trade("winner", 20, strike=24000.0, unit_net_pnl=12.5)])

    exact, proxy, evidence = build_historical_option_datasets(intents, trades)

    assert proxy.shape[0] == 0
    assert exact.shape[0] == 1
    assert exact.iloc[0]["target"] == 1
    assert exact.iloc[0]["exec_feasible"] == 1
    assert exact.iloc[0]["future_net_r"] == pytest.approx(0.5)
    assert exact.iloc[0]["friction_r"] == pytest.approx(0.004)
    assert exact.iloc[0]["feature_cutoff_ts_epoch_ms"] == exact.iloc[0]["decision_ts_epoch_ms"]
    assert exact.iloc[0]["outcome_ts_epoch_ms"] > exact.iloc[0]["decision_ts_epoch_ms"]
    features = feature_columns(exact)
    assert set(features) == {
        "atm_distance_steps",
        "candidate_blocker_count",
        "candidate_confidence_score",
        "candidate_price_structure_score",
        "candidate_raw_score",
        "candidate_warning_count",
        "direction_put",
        "expiry_days",
        "minutes_since_open",
        "requested_entry_delay_minutes",
        "signal_underlying_price",
        "time_cos",
        "time_sin",
    }
    assert evidence["label_semantics"] == "POST_COST_POSITIVE_OPTION_OUTCOME"
    assert evidence["execution_grade"] is False


def test_duplicate_trade_identity_fails_closed() -> None:
    intents = pd.DataFrame([_intent("duplicate", 20)])
    duplicate = _trade("duplicate", 20, strike=24000.0)
    trades = pd.DataFrame([duplicate, duplicate])

    with pytest.raises(HistoricalOptionDataError, match="duplicate_trade_identity"):
        build_historical_option_datasets(intents, trades)


def test_noncausal_entry_fails_closed() -> None:
    intents = pd.DataFrame([_intent("noncausal", 20)])
    trade = _trade("noncausal", 20, strike=24000.0)
    trade["entry_timestamp"] = trade["signal_timestamp"]
    trades = pd.DataFrame([trade])

    with pytest.raises(HistoricalOptionDataError, match="option_entry_not_causal"):
        build_historical_option_datasets(intents, trades)
