from __future__ import annotations

import numpy as np
import pandas as pd

from research.autonomous_structural_edge_exhaustion_v1 import batch_b as B
from research.autonomous_structural_edge_exhaustion_v1 import certification_v2 as C2
from research.autonomous_structural_edge_exhaustion_v1 import common as C


def test_symmetric_distribution_has_near_zero_shape_asymmetry() -> None:
    values = np.linspace(-0.01, 0.01, 81)
    result = B._distribution_shape(values)

    assert abs(result["cross_skew"]) < 1e-12
    assert abs(result["tail_log_magnitude_ratio"]) < 1e-12
    assert abs(result["tail_count_imbalance"]) < 1e-12
    assert abs(result["median_mean_gap_norm"]) < 1e-12
    assert abs(result["wing_asymmetry"]) < 1e-12


def test_clock_norms_are_fit_from_observation_only() -> None:
    rows = []
    for day, split, offset in (
        ("2025-01-02", "observation", 0.0),
        ("2025-01-03", "observation", 1.0),
        ("2025-01-06", "replication", 1000.0),
    ):
        for i in range(24):
            rows.append(
                {
                    "session_date": day,
                    "timestamp": pd.Timestamp(f"{day} 09:15", tz=C.TZ) + pd.Timedelta(minutes=5 * i),
                    "split": split,
                    "breadth_imbalance": offset + i * 0.01,
                    "dispersion_std": offset + 1.0 + i * 0.01,
                    "top5_abs_share": offset + 2.0 + i * 0.01,
                    "index_eqw_divergence": offset + 3.0 + i * 0.01,
                    "median_volume_ratio": offset + 4.0 + i * 0.01,
                    "cross_skew": offset + 5.0 + i * 0.01,
                }
            )
    frame = pd.DataFrame(rows)
    first = B.fit_clock_norms(frame)
    mutated = frame.copy()
    mutated.loc[mutated["split"].eq("replication"), list(B.CLOCK_METRICS)] = -999999.0
    second = B.fit_clock_norms(mutated)

    assert first["semantic_sha256"] == second["semantic_sha256"]
    assert first["fit_scope"] == "observation_only"
    assert first["outcomes_seen"] is False


def _temporal_frame(rows: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "session_date": ["2025-01-02"] * rows,
            "timestamp": pd.date_range("2025-01-02 09:15", periods=rows, freq="5min", tz=C.TZ),
            "breadth_clock_resid": np.linspace(-1.0, 1.0, rows),
            "dispersion_clock_resid": np.sin(np.arange(rows) / 2.0),
            "concentration_clock_resid": np.cos(np.arange(rows) / 3.0),
            "divergence_clock_resid": np.linspace(1.0, -1.0, rows),
        }
    )


def test_batch_b_temporal_features_are_prefix_invariant() -> None:
    full_source = _temporal_frame(12)
    prefix_source = full_source.iloc[:8].copy()
    full = B.add_temporal_batch_b_features(full_source)
    prefix = B.add_temporal_batch_b_features(prefix_source)
    columns = [
        "breadth_sign_run",
        "divergence_sign_run",
        "dispersion_high_run",
        "concentration_high_run",
        "breadth_flip_count6",
        "divergence_flip_count6",
        "breadth_peak_age6",
        "dispersion_peak_age6",
        "concentration_peak_age6",
        "divergence_peak_age6",
        "breadth_dispersion_phase6",
        "divergence_concentration_phase6",
        "breadth_path_efficiency6",
        "dispersion_path_efficiency6",
        "concentration_path_efficiency6",
        "divergence_path_efficiency6",
        "breadth_dispersion_loop_area6",
        "divergence_concentration_loop_area6",
    ]
    left = full.loc[:7, columns].to_numpy(float)
    right = prefix.loc[:, columns].to_numpy(float)

    assert np.allclose(left, right, atol=1e-12, rtol=0.0, equal_nan=True)


def _screen_outcomes(replication_p: float) -> dict:
    stats = {
        "n": 30,
        "mean_bps": 4.0,
        "median_bps": 3.0,
        "hit_rate": 0.70,
        "ci90": [1.0, 7.0],
        "sign_p": replication_p,
    }
    return {
        "records": [
            {
                "hypothesis": {
                    "hypothesis_id": "H::B::TEST",
                    "family": "TAIL_SHAPE_ASYMMETRY",
                },
                "stats": {
                    "observation": {"directional_excess": dict(stats)},
                    "replication": {"directional_excess": dict(stats)},
                },
            }
        ]
    }


def test_two_batch_screen_tightens_global_q_to_five_percent() -> None:
    result = C2.structural_screen_v2(_screen_outcomes(0.06))

    assert result["campaign_global_q_threshold"] == 0.05
    assert result["survivor_hypothesis_ids"] == []
    assert result["results"][0]["gates"]["campaign_global_bh_q_le_5pct"] is False
    assert "global_bh_q_le_10pct" not in result["results"][0]["gates"]


def test_two_batch_screen_can_pass_only_below_stricter_global_q() -> None:
    result = C2.structural_screen_v2(_screen_outcomes(0.04))

    assert result["survivor_hypothesis_ids"] == ["H::B::TEST"]
    assert result["results"][0]["gates"]["campaign_global_bh_q_le_5pct"] is True


def test_two_batch_family_set_is_twelve_distinct_information_families() -> None:
    combined = tuple(C.FAMILY_FEATURES) + tuple(B.BATCH_B_FEATURES)

    assert set(combined) == set(C2.ALL_FAMILIES)
    assert len(set(combined)) == 12
    assert set(C.FAMILY_FEATURES).isdisjoint(set(B.BATCH_B_FEATURES))
