from __future__ import annotations

import pandas as pd

from core.analytics.candidate_ml_v2 import CandidateMLConfig, fit_candidate_ml
from core.analytics.candidate_ml_v2.replay_ledger import (
    REPLAY_LEDGER_REQUIRED_FEATURES,
    build_replay_ledger_dataset,
)


def _records(days: int = 40) -> list[dict]:
    records: list[dict] = []
    base = pd.Timestamp("2024-07-01 09:30:00", tz="Asia/Kolkata")
    for day in range(days):
        signal = base + pd.Timedelta(days=day)
        direction = "LONG" if day % 2 == 0 else "SHORT"
        target_hit = day % 3 != 0
        entry = 20_000.0 + day
        risk = 20.0 + day % 5
        stop = entry - risk if direction == "LONG" else entry + risk
        target = entry + risk * 1.5 if direction == "LONG" else entry - risk * 1.5
        exit_price = target if target_hit else stop
        records.append(
            {
                "strategy_id": "MEAN_REVERSION_EXTENSION",
                "symbol": "NIFTY" if day % 4 else "BANKNIFTY",
                "signal_time": signal.isoformat(),
                "entry_time": (signal + pd.Timedelta(minutes=1)).isoformat(),
                "exit_time": (signal + pd.Timedelta(minutes=10)).isoformat(),
                "direction": direction,
                "entry_price": entry,
                "signal_close": entry - 0.5,
                "exit_price": exit_price,
                "stop_loss": stop,
                "target": target,
                "exit_reason": "TARGET" if target_hit else "STOP_LOSS",
                "candidate_id": f"candidate-{day}",
                "decision_id": f"decision-{day}",
                "setup_type": "FAILED_BREAKDOWN_LONG" if direction == "LONG" else "FAILED_BREAKOUT_SHORT",
                "failed_level": entry - 3.0,
                "reclaim_or_reject_level": entry - 0.5,
                "htf_regime": "NEUTRAL/BULLISH" if direction == "LONG" else "NEUTRAL/BEARISH",
                "rejection_quality": 0.55 + (day % 5) * 0.05,
                "wick_ratio": 0.55 + (day % 5) * 0.05,
                "cost_hurdle_margin": 10.0 + day % 7,
                "planned_target_distance": risk * 1.5,
                "entry_delay_bars": 1,
                "time_stop_minutes": 30,
                "proxy_option_execution_cost": 1.5,
                "proxy_option_net_pnl": risk * 0.5 * (1.4 if target_hit else -1.1),
                "rr_realized": 1.5 if target_hit else -1.0,
                "execution_grade": False,
                "execution_allowed": False,
            }
        )
    return records


def test_replay_ledger_builds_causal_candidate_dataset_and_model():
    dataset, evidence = build_replay_ledger_dataset(_records())

    assert dataset.shape[0] == 40
    assert dataset["session_date"].nunique() == 40
    assert dataset["target"].nunique() == 2
    assert (dataset["outcome_ts_epoch_ms"] > dataset["decision_ts_epoch_ms"]).all()
    assert dataset["is_order_action"].eq(False).all()
    assert dataset["broker_api_called"].eq(False).all()
    assert evidence["candidate_lineage_available"] is True
    assert evidence["execution_grade"] is False
    assert evidence["candidate_edge_certification_allowed"] is False

    bundle = fit_candidate_ml(
        dataset,
        CandidateMLConfig(
            min_train_rows=25,
            min_validation_rows=8,
            min_strategy_rows=10_000,
            min_positive_rows=5,
            validation_fraction=0.20,
            purge_rows=0,
            required_features=tuple(REPLAY_LEDGER_REQUIRED_FEATURES),
        ),
    )
    assert bundle.global_model is not None
    assert bundle.safety["allowed_for_live_execution"] is False


def test_replay_ledger_rejects_noncausal_timestamp_row():
    records = _records(days=5)
    records[0]["exit_time"] = records[0]["entry_time"]
    dataset, evidence = build_replay_ledger_dataset(records)

    assert dataset.shape[0] == 4
    assert evidence["rejected_rows"] == 1
    assert "exit_not_after_entry" in evidence["rejections"][0]["reason"]
