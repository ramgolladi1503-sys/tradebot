from __future__ import annotations

import numpy as np
import pandas as pd

from research.history_first_pattern_miner_v1 import miner as M


def _session(rows: int = 24) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "session_date": ["2025-01-02"] * rows,
            "timestamp": pd.date_range("2025-01-02 09:15", periods=rows, freq="5min", tz="Asia/Kolkata"),
            "session_progress": np.linspace(0.0, 1.0, rows),
            "index_path": np.linspace(0.0, 0.01, rows),
            "breadth_imbalance": np.linspace(-0.5, 0.5, rows),
            "dispersion_std": np.linspace(0.001, 0.003, rows),
            "top5_abs_share": np.linspace(0.2, 0.4, rows),
            "index_eqw_divergence": np.linspace(-0.001, 0.001, rows),
            "median_volume_ratio": np.linspace(0.8, 1.4, rows),
            "leader_churn": np.linspace(0.1, 0.5, rows),
            "participation_ratio": np.linspace(0.9, 1.0, rows),
            "breadth_delta3": np.linspace(-0.1, 0.1, rows),
            "dispersion_delta3": np.linspace(-0.001, 0.001, rows),
            "concentration_delta3": np.linspace(-0.05, 0.05, rows),
            "divergence_delta3": np.linspace(-0.001, 0.001, rows),
            "split": ["observation"] * rows,
        }
    )


def test_prefix_embedding_is_invariant_to_future_suffix_mutation() -> None:
    full = _session(24)
    cutoff = 0.50
    grid = M._prefix_grid(cutoff)
    original = M._interp_session(full.loc[full["session_progress"].le(cutoff)], M.PREFIX_FEATURES, grid)
    mutated = full.copy()
    suffix = mutated["session_progress"].gt(cutoff)
    for feature in M.PREFIX_FEATURES:
        mutated.loc[suffix, feature] = 999999.0
    after = M._interp_session(mutated.loc[mutated["session_progress"].le(cutoff)], M.PREFIX_FEATURES, grid)
    assert np.allclose(original, after, atol=0.0, rtol=0.0)


def test_effect_requires_directionally_stable_replication() -> None:
    a = np.asarray([2.0, 2.2, 2.4, 2.6, 2.8])
    b = np.asarray([0.0, 0.2, 0.4, 0.6, 0.8])
    obs = M._effect(a, b)
    rep_same = M._effect(a + 0.1, b + 0.1)
    rep_flip = M._effect(b, a)
    assert obs > M.MIN_EFFECT_OBS
    assert rep_same > M.MIN_EFFECT_REP
    assert np.sign(obs) == np.sign(rep_same)
    assert np.sign(obs) != np.sign(rep_flip)


def test_cluster_model_rejects_tiny_observation_clusters() -> None:
    rng = np.random.default_rng(7)
    large_a = rng.normal(-2.0, 0.1, size=(20, 4))
    large_b = rng.normal(2.0, 0.1, size=(20, 4))
    vectors = np.vstack([large_a, large_b])
    scaler, pca, model, authority = M._fit_cluster_model(vectors, min_cluster=10)
    assert authority["fit_scope"] == "observation_only"
    assert min(authority["observation_cluster_counts"]) >= 10
    assert model.n_clusters >= 3 or model.n_clusters == 2
    assert scaler is not None
    assert pca is not None


def _synthetic_embedding_table() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    rows = []
    for split, n in (("observation", 120), ("replication", 48)):
        for i in range(n):
            archetype = i % 3
            base = np.zeros(len(M.DAY_FEATURES) * len(M.DAY_GRID), dtype=float)
            base[archetype :: 3] = 3.0
            vector = base + rng.normal(0.0, 0.08, size=base.shape)
            rows.append({"session_date": f"{split}-{i:03d}", "split": split, "vector": vector})
    return pd.DataFrame(rows)


def test_day_archetype_model_fits_observation_and_assigns_replication(monkeypatch) -> None:
    table = _synthetic_embedding_table()
    monkeypatch.setattr(M, "build_session_embeddings", lambda frame, features, grid: table.copy())
    catalog, assigned, _ = M.discover_day_archetypes(pd.DataFrame({"dummy": [1]}))
    assert catalog["fit"]["fit_scope"] == "observation_only"
    assert catalog["replication_sessions"] == 48
    assert catalog["outcomes_opened"] is False
    assert catalog["unopened_sessions_used"] is False
    assert set(assigned["split"]) == {"observation", "replication"}


def test_discriminator_catalog_does_not_authorize_strategy_or_outcomes() -> None:
    empty = M.discover_branch_discriminators(_session(), [])
    assert empty["principal_verdict"] == "NO_STABLE_PRE_BRANCH_DISCRIMINATOR_FOUND"
    assert empty["outcomes_opened"] is False
    assert empty["validation_sessions_used"] is False
    assert empty["unopened_sessions_used"] is False
