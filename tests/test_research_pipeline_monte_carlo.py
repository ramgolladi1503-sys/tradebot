"""Synthetic-only tests for the research pipeline's trade-level bootstrap."""
from copy import deepcopy

import pytest

from core.research_pipeline import ResearchPipeline


def trades(values):
    return [{"strategy": "synthetic", "pnl_adj": value} for value in values]


def monte_carlo(rows, *, n=200, seed=17):
    # Avoid __init__: it creates the default output directory. The statistic
    # must operate only on the supplied inline rows.
    pipeline = object.__new__(ResearchPipeline)
    return pipeline._monte_carlo(rows, n=n, seed=seed)


def test_bootstrap_is_seed_reproducible_and_non_degenerate():
    rows = trades([-8, -3, -1, 0, 1, 2, 4, 7, 11, 20])
    before = deepcopy(rows)
    first = monte_carlo(rows, n=250, seed=23)["synthetic"]
    repeated = monte_carlo(rows, n=250, seed=23)["synthetic"]
    other_seed = monte_carlo(rows, n=250, seed=29)["synthetic"]

    assert first == repeated
    assert first["mc_p05"] < first["mc_p95"]
    assert first != other_seed
    assert rows == before


def test_short_samples_remain_omitted():
    assert monte_carlo(trades(range(9))) == {}


@pytest.mark.parametrize("n", [0, -1, 1.5, True])
def test_invalid_replication_count_fails_explicitly(n):
    with pytest.raises(ValueError, match="positive integer"):
        monte_carlo(trades(range(10)), n=n)


@pytest.mark.parametrize("seed", [1.5, True, "17"])
def test_invalid_seed_fails_explicitly(seed):
    with pytest.raises(ValueError, match="seed must be an integer"):
        monte_carlo(trades(range(10)), seed=seed)
