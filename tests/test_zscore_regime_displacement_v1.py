from __future__ import annotations

import numpy as np
import pandas as pd

from research.zscore_regime_displacement_v1 import core as Z


def _frame(prices: list[float], breadth: list[float] | None = None) -> pd.DataFrame:
    n = len(prices)
    if breadth is None:
        breadth = [0.0] * n
    return pd.DataFrame(
        {
            "session_date": ["2026-01-05"] * n,
            "timestamp": pd.date_range(
                "2026-01-05 09:15", periods=n, freq="5min", tz="Asia/Kolkata"
            ),
            "index_close": prices,
            "breadth_imbalance": breadth,
            "volume_shock_share": [0.0] * n,
            "high_volume_signed_mean": [0.0] * n,
        }
    )


def test_zscore_uses_only_prior_completed_bars() -> None:
    prices = [100 + (i % 3) for i in range(20)]
    frame = Z.add_causal_zscore(_frame(prices))
    before = frame.loc[14, "price_z12"]

    changed = prices.copy()
    changed[19] = 10000.0
    frame2 = Z.add_causal_zscore(_frame(changed))
    assert frame2.loc[14, "price_z12"] == before


def test_hypotheses_are_frozen_and_direction_not_learned() -> None:
    catalog = Z.freeze_hypotheses()
    assert catalog["hypothesis_count"] == 4
    assert catalog["policy"]["outcomes_seen_when_frozen"] is False
    assert catalog["policy"]["direction_predeclared"] is True
    assert all(
        h["direction_selected_from_outcomes"] is False
        for h in catalog["hypotheses"]
    )


def test_reversal_signal_is_opposite_extreme_and_requires_breadth_disagreement() -> None:
    class Row:
        pass

    p = Row()
    p.price_z12 = 2.4
    p.breadth_imbalance = -0.2
    c = Row()
    c.price_z12 = 1.3
    ok, direction = Z._reversal_event(p, c)
    assert ok is True
    assert direction == -1

    p.breadth_imbalance = 0.3
    ok2, _ = Z._reversal_event(p, c)
    assert ok2 is False


def test_continuation_requires_aligned_breadth_and_high_volume_flow() -> None:
    class Row:
        pass

    r = Row()
    r.price_z12 = -2.2
    r.breadth_imbalance = -0.4
    r.volume_shock_share = 0.1
    r.high_volume_signed_mean = -0.0003
    ok, direction = Z._continuation_event(r)
    assert ok is True
    assert direction == -1

    r.high_volume_signed_mean = 0.0003
    ok2, _ = Z._continuation_event(r)
    assert ok2 is False


def test_signal_table_emits_at_most_one_signal_per_mechanism_per_session() -> None:
    n = 20
    frame = _frame([100.0] * n)
    frame["price_z12"] = np.nan
    frame.loc[13, "price_z12"] = 2.4
    frame.loc[13, "breadth_imbalance"] = -0.2
    frame.loc[14, "price_z12"] = 1.4
    frame.loc[14, "breadth_imbalance"] = -0.1
    frame.loc[15, "price_z12"] = 2.6
    frame.loc[15, "breadth_imbalance"] = -0.2
    frame.loc[16, "price_z12"] = 1.2

    signals = Z.signal_table(frame)
    rev = signals["EXTREME_REENTRY_CROSS_SECTIONAL_DISAGREEMENT"]
    assert len(rev) == 1
    only = next(iter(rev.values()))
    assert pd.Timestamp(only["timestamp"]) == frame.loc[14, "timestamp"]


def test_structural_screen_requires_positive_observation_for_predeclared_direction() -> None:
    outcomes = {
        "records": [
            {
                "hypothesis": {"hypothesis_id": "H", "family": Z.FAMILY},
                "stats": {
                    "observation": {
                        "directional_excess": {
                            "n": 30,
                            "mean_bps": -4.0,
                            "median_bps": -2.0,
                            "hit_rate": 0.40,
                            "ci90": [-6.0, -2.0],
                            "sign_p": 1.0,
                        }
                    },
                    "replication": {
                        "directional_excess": {
                            "n": 20,
                            "mean_bps": 4.0,
                            "median_bps": 3.0,
                            "hit_rate": 0.70,
                            "ci90": [1.0, 7.0],
                            "sign_p": 0.001,
                        }
                    },
                },
            }
        ]
    }
    screen = Z.structural_screen(outcomes)
    assert screen["survivor_hypothesis_ids"] == []
    gate = screen["results"][0]["gates"]
    assert gate["observation_directional_mean_ge_2bps"] is False


def test_final_authority_never_opens_tail_automatically() -> None:
    h = Z.freeze_hypotheses()
    empty = {"semantic_sha256": "x", "survivor_hypothesis_ids": []}
    robust = {"semantic_sha256": "r", "survivor_hypothesis_ids": ["candidate"]}
    out = Z.final_authority(h, {"semantic_sha256": "o"}, empty, empty, robust)
    assert out["unopened_sessions_scored"] is False
    assert out["unopened_tail_access_authorized"] is False
    assert out["shadow_authorized"] is False
    assert out["live_authorized"] is False
