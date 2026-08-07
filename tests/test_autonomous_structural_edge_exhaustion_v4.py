from __future__ import annotations

import numpy as np
import pandas as pd

from research.autonomous_structural_edge_exhaustion_v1 import batch_b as B
from research.autonomous_structural_edge_exhaustion_v1 import batch_c as C3
from research.autonomous_structural_edge_exhaustion_v1 import batch_d as D
from research.autonomous_structural_edge_exhaustion_v1 import certification_v4 as V4
from research.autonomous_structural_edge_exhaustion_v1 import common as C


def _matrices(rows: int = 20, symbols: int = 45):
    rng = np.random.default_rng(101)
    times = pd.date_range("2025-01-02 09:15", periods=rows, freq="5min", tz=C.TZ)
    ret = rng.normal(0.0, 0.002, size=(rows, symbols))
    volume = 1000.0 + np.abs(ret) * 2_000_000.0 + rng.normal(0, 25, size=(rows, symbols))
    volume = np.clip(volume, 1.0, None)
    index = ret.mean(axis=1)
    columns = [f"S{i:02d}" for i in range(symbols)]
    return pd.DataFrame(ret, index=times, columns=columns), pd.DataFrame(volume, index=times, columns=columns), pd.Series(index, index=times)


def test_batch_d_session_metrics_are_prefix_invariant() -> None:
    ret, volume, index = _matrices()
    full = D._session_metrics(ret, volume, index)
    prefix = D._session_metrics(ret.iloc[:14], volume.iloc[:14], index.iloc[:14])
    columns = sorted({name for features in D.BATCH_D_FEATURES.values() for name in features})
    left = full.loc[full["timestamp"].isin(prefix["timestamp"]), columns].reset_index(drop=True).to_numpy(float)
    right = prefix[columns].reset_index(drop=True).to_numpy(float)
    assert left.shape == right.shape
    assert np.allclose(left, right, atol=1e-12, rtol=0.0, equal_nan=True)


def test_return_volume_coupling_detects_abs_return_volume_relation() -> None:
    ret, volume, index = _matrices()
    result = D._session_metrics(ret, volume, index)
    values = result["absret_volume_corr"].dropna().to_numpy(float)
    assert float(np.median(values)) > 0.25


def test_relative_strength_memory_recognizes_persistent_cross_section() -> None:
    symbols = 45
    rows = 16
    times = pd.date_range("2025-01-02 09:15", periods=rows, freq="5min", tz=C.TZ)
    base = np.linspace(-0.002, 0.002, symbols)
    ret = pd.DataFrame(np.tile(base, (rows, 1)), index=times, columns=[f"S{i:02d}" for i in range(symbols)])
    volume = pd.DataFrame(np.full((rows, symbols), 1000.0), index=times, columns=ret.columns)
    index = pd.Series(np.zeros(rows), index=times)
    result = D._session_metrics(ret, volume, index)
    assert float(result["rank_alignment_3_6"].dropna().median()) > 0.99
    assert float(result["top_quintile_persistence_3_6"].dropna().median()) > 0.99


def _screen_outcomes(p: float) -> dict:
    stats = {"n": 50, "mean_bps": 5.0, "median_bps": 4.0, "hit_rate": 0.72, "ci90": [1.5, 8.0], "sign_p": p}
    return {"records": [{"hypothesis": {"hypothesis_id": "H::D::TEST", "family": "RETURN_VOLUME_COUPLING"}, "stats": {"observation": {"directional_excess": dict(stats)}, "replication": {"directional_excess": dict(stats)}}}]}


def test_four_batch_screen_halves_campaign_q_again() -> None:
    failed = V4.structural_screen_v4(_screen_outcomes(0.015))
    passed = V4.structural_screen_v4(_screen_outcomes(0.01))
    assert failed["campaign_global_q_threshold"] == 0.0125
    assert failed["survivor_hypothesis_ids"] == []
    assert passed["survivor_hypothesis_ids"] == ["H::D::TEST"]


def test_four_batches_cover_twenty_four_distinct_information_families() -> None:
    combined = tuple(C.FAMILY_FEATURES) + tuple(B.BATCH_B_FEATURES) + tuple(C3.BATCH_C_FEATURES) + tuple(D.BATCH_D_FEATURES)
    assert len(combined) == 24
    assert len(set(combined)) == 24
    assert set(combined) == set(V4.ALL_FAMILIES_V4)
