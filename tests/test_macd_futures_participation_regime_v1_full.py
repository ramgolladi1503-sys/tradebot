from __future__ import annotations

import pandas as pd
import pytest

from research.macd_futures_participation_regime_v1.full_gates import (
    FullGateBlocked,
    benjamini_hochberg,
    canonicalize_per_signal,
    chronological_fold_results,
    evaluate_full_gates,
    validate_delay_ledger,
)
from research.macd_futures_participation_regime_v1.independent_oracle import (
    verify_primary_ledger,
)


def _ledger(active_delta: float = 8.0, inactive_delta: float = -2.0) -> pd.DataFrame:
    rows = []
    for i in range(80):
        active = i < 40
        delta = active_delta if active else inactive_delta
        rows.append(
            {
                "signal_trade_id": f"T{i:03d}",
                "signal_origin": pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
                + pd.Timedelta(days=i),
                "signal_session_date": str(
                    (pd.Timestamp("2024-01-01") + pd.Timedelta(days=i)).date()
                ),
                "signal_state": active,
                "signal_net_6bps": delta + 1.0,
                "placebo_mean_net_6bps": 1.0,
                "delta_net_6bps": delta,
                "compatible_placebo_n": 100,
            }
        )
    return pd.DataFrame(rows)


def test_canonical_delta_identity_and_folds() -> None:
    x = canonicalize_per_signal(_ledger())
    assert len(x) == 80
    folds = chronological_fold_results(x, folds=4)
    assert len(folds) == 4


def test_bh_adjustment() -> None:
    got = benjamini_hochberg({"a": 0.001, "b": 0.02, "c": 0.5}, q=0.05)
    assert got["tests"]["a"]["pass"] is True
    assert got["tests"]["c"]["pass"] is False


def test_missing_delay_and_multiplicity_inputs_block_full_numeric_gate() -> None:
    x = _ledger()
    result, folds, loqo = evaluate_full_gates(
        x,
        delay1=None,
        delay2=None,
        hypothesis_id="TEST_H1",
        external_multiplicity_pvalues=None,
    )
    assert "MISSING_CANONICAL_DELAY_1_LEDGER" in result["blockers"]
    assert "MISSING_CANONICAL_DELAY_2_LEDGER" in result["blockers"]
    assert "MISSING_GLOBAL_MULTIPLICITY_LEDGER" in result["blockers"]
    assert result["full_numeric_gates_pass"] is False
    assert result["structural_edge_certified"] is False
    assert len(folds) == 4
    assert len(loqo) > 0


def test_independent_oracle_detects_mutation() -> None:
    x = _ledger()
    result, _, _ = evaluate_full_gates(
        x,
        delay1=None,
        delay2=None,
        hypothesis_id="TEST_H1",
        external_multiplicity_pvalues={"prior_test": 0.5},
    )
    assert verify_primary_ledger(x, result)["status"] == "PASS"

    bad = dict(result)
    bad["summary"] = dict(result["summary"])
    bad["summary"]["active_delta_net_6bps"] += 1.0
    assert verify_primary_ledger(x, bad)["status"] == "FAIL"


def test_delay_ledgers_must_preserve_signal_ids() -> None:
    x = _ledger()
    delay = _ledger(active_delta=4.0, inactive_delta=-1.0)
    delay.loc[0, "signal_trade_id"] = "DIFFERENT"
    with pytest.raises(FullGateBlocked, match="SIGNAL_ID_SET_MISMATCH"):
        validate_delay_ledger(x, delay, delay_bars=1)
