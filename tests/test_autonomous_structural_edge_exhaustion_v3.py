from __future__ import annotations

import numpy as np
import pandas as pd

from research.autonomous_structural_edge_exhaustion_v1 import batch_b as B
from research.autonomous_structural_edge_exhaustion_v1 import batch_c as C3
from research.autonomous_structural_edge_exhaustion_v1 import certification_v3 as V3
from research.autonomous_structural_edge_exhaustion_v1 import common as C


def _returns(rows: int = 18, symbols: int = 45, seed: int = 7, common_strength: float = 0.0):
    rng = np.random.default_rng(seed)
    common = rng.normal(0.0, 0.002, size=rows)
    idio = rng.normal(0.0, 0.002, size=(rows, symbols))
    values = common_strength * common[:, None] + (1.0 - common_strength) * idio
    index = common_strength * common + (1.0 - common_strength) * rng.normal(0.0, 0.0015, size=rows)
    times = pd.date_range("2025-01-02 09:15", periods=rows, freq="5min", tz=C.TZ)
    frame = pd.DataFrame(values, index=times, columns=[f"S{i:02d}" for i in range(symbols)])
    return frame, pd.Series(index, index=times)


def test_batch_c_session_metrics_are_prefix_invariant() -> None:
    frame, index = _returns(rows=18, common_strength=0.35)
    full = C3._session_metrics(frame, index)
    prefix = C3._session_metrics(frame.iloc[:12], index.iloc[:12])
    columns = sorted({name for features in C3.BATCH_C_FEATURES.values() for name in features})
    left = full.loc[full["timestamp"].isin(prefix["timestamp"]), columns].reset_index(drop=True).to_numpy(float)
    right = prefix[columns].reset_index(drop=True).to_numpy(float)
    assert left.shape == right.shape
    assert np.allclose(left, right, atol=1e-12, rtol=0.0, equal_nan=True)


def test_correlation_spectrum_detects_common_factor_concentration() -> None:
    independent, independent_index = _returns(rows=18, seed=11, common_strength=0.0)
    common, common_index = _returns(rows=18, seed=11, common_strength=0.90)
    a = C3._session_metrics(independent, independent_index)
    b = C3._session_metrics(common, common_index)
    a_value = float(a["first_eigen_share6"].dropna().median())
    b_value = float(b["first_eigen_share6"].dropna().median())
    assert b_value > a_value
    assert b_value > 0.50


def test_rank_mobility_changes_when_constituent_order_reverses() -> None:
    symbols = [f"S{i:02d}" for i in range(45)]
    times = pd.date_range("2025-01-02 09:15", periods=4, freq="5min", tz=C.TZ)
    base = np.linspace(-0.01, 0.01, 45)
    matrix = np.vstack([base, base, base[::-1], base[::-1]])
    frame = pd.DataFrame(matrix, index=times, columns=symbols)
    index = pd.Series(np.zeros(4), index=times)
    result = C3._session_metrics(frame, index)
    first_stable = float(result.loc[result["timestamp"].eq(times[1]), "rank_corr_lag1"].iloc[0])
    reversal = float(result.loc[result["timestamp"].eq(times[2]), "rank_corr_lag1"].iloc[0])
    assert first_stable > 0.99
    assert reversal < -0.99


def _screen_outcomes(p: float) -> dict:
    stats = {"n": 40, "mean_bps": 4.0, "median_bps": 3.0, "hit_rate": 0.70, "ci90": [1.0, 7.0], "sign_p": p}
    return {"records": [{"hypothesis": {"hypothesis_id": "H::C::TEST", "family": "CORRELATION_SPECTRUM"}, "stats": {"observation": {"directional_excess": dict(stats)}, "replication": {"directional_excess": dict(stats)}}}]}


def test_three_batch_screen_tightens_campaign_q_to_two_point_five_percent() -> None:
    failed = V3.structural_screen_v3(_screen_outcomes(0.03))
    passed = V3.structural_screen_v3(_screen_outcomes(0.02))
    assert failed["campaign_global_q_threshold"] == 0.025
    assert failed["survivor_hypothesis_ids"] == []
    assert passed["survivor_hypothesis_ids"] == ["H::C::TEST"]


def test_three_batches_cover_eighteen_distinct_information_families() -> None:
    combined = tuple(C.FAMILY_FEATURES) + tuple(B.BATCH_B_FEATURES) + tuple(C3.BATCH_C_FEATURES)
    assert len(combined) == 18
    assert len(set(combined)) == 18
    assert set(combined) == set(V3.ALL_FAMILIES_V3)
    assert set(C3.BATCH_C_FEATURES).isdisjoint(set(C.FAMILY_FEATURES))
    assert set(C3.BATCH_C_FEATURES).isdisjoint(set(B.BATCH_B_FEATURES))
