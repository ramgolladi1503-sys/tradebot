from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from research.ml_strategy_discovery.contracts import BarrierSpec
from research.ml_strategy_discovery.labels import (
    Bar,
    BarrierOutcome,
    Side,
    label_triple_barrier,
)
from research.ml_strategy_discovery.models import (
    DiscoveryModelConfig,
    fit_shallow_tree,
)
from research.ml_strategy_discovery.negative_controls import (
    delayed_series,
    deterministic_permutation,
    parameter_neighborhood,
    randomized_entry_offsets,
)
from research.ml_strategy_discovery.rules import (
    extract_positive_leaf_rules,
)

UTC = timezone.utc
T0 = datetime(2026, 1, 2, 9, 30, tzinfo=UTC)


def bar(
    minute: int,
    open_: float,
    high: float,
    low: float,
    close: float,
) -> Bar:
    return Bar(
        T0 + timedelta(minutes=minute),
        open_,
        high,
        low,
        close,
    )


def test_triple_barrier_uses_strictly_future_entry_bar() -> None:
    result = label_triple_barrier(
        decision_at=T0,
        bars=[
            bar(0, 100, 100.5, 99.5, 100),
            bar(1, 101, 103, 100.5, 102),
        ],
        side=Side.LONG,
        barrier=BarrierSpec(
            target_distance=2,
            stop_distance=1,
            max_holding_bars=2,
        ),
    )
    assert result.entry_at == T0 + timedelta(minutes=1)
    assert result.entry_price == 101
    assert result.outcome is BarrierOutcome.TARGET_FIRST


def test_same_bar_target_and_stop_is_conservative_stop() -> None:
    result = label_triple_barrier(
        decision_at=T0,
        bars=[bar(1, 100, 103, 98, 101)],
        side=Side.LONG,
        barrier=BarrierSpec(
            target_distance=2,
            stop_distance=1,
            max_holding_bars=1,
        ),
    )
    assert result.outcome is BarrierOutcome.STOP_FIRST
    assert result.ambiguous_same_bar is True


def test_short_barrier_direction_is_correct() -> None:
    result = label_triple_barrier(
        decision_at=T0,
        bars=[bar(1, 100, 100.5, 97.5, 98)],
        side=Side.SHORT,
        barrier=BarrierSpec(
            target_distance=2,
            stop_distance=1,
            max_holding_bars=1,
        ),
    )
    assert result.outcome is BarrierOutcome.TARGET_FIRST
    assert result.target_price == 98
    assert result.stop_price == 101


def test_no_future_bar_is_no_legal_entry() -> None:
    result = label_triple_barrier(
        decision_at=T0,
        bars=[bar(0, 100, 101, 99, 100)],
        side=Side.LONG,
        barrier=BarrierSpec(
            target_distance=2,
            stop_distance=1,
            max_holding_bars=1,
        ),
    )
    assert result.outcome is BarrierOutcome.NO_LEGAL_ENTRY
    assert result.entry_price is None


def test_neither_reports_excursions() -> None:
    result = label_triple_barrier(
        decision_at=T0,
        bars=[
            bar(1, 100, 100.8, 99.6, 100.2),
            bar(2, 100.2, 101.0, 99.7, 100.5),
        ],
        side=Side.LONG,
        barrier=BarrierSpec(
            target_distance=2,
            stop_distance=1,
            max_holding_bars=2,
        ),
    )
    assert result.outcome is BarrierOutcome.NEITHER
    assert result.mfe == pytest.approx(1.0)
    assert result.mae == pytest.approx(-0.4)


def test_negative_controls_are_deterministic_and_conservative() -> None:
    values = tuple(range(20))
    first = deterministic_permutation(
        values,
        seed_material="dataset-hash",
    )
    second = deterministic_permutation(
        values,
        seed_material="dataset-hash",
    )
    assert first == second
    assert sorted(first) == list(values)
    assert first != values
    assert delayed_series((10, 11, 12), lag=1) == (None, 10, 11)
    assert randomized_entry_offsets(
        count=5,
        maximum_offset_bars=7,
        seed_material="x",
    ) == randomized_entry_offsets(
        count=5,
        maximum_offset_bars=7,
        seed_material="x",
    )


def test_parameter_neighborhood_includes_base_and_bounds() -> None:
    values = parameter_neighborhood(
        100,
        lower_bound=95,
        upper_bound=105,
    )
    assert values == (95.0, 100.0, 105.0)


def test_model_config_rejects_opaque_tree_depth() -> None:
    with pytest.raises(ValueError, match="interpretable"):
        DiscoveryModelConfig(max_depth=8).validate()


def test_shallow_tree_can_be_extracted_into_readable_rules() -> None:
    X = [
        [0.0],
        [0.1],
        [0.2],
        [0.8],
        [0.9],
        [1.0],
        [1.1],
        [1.2],
    ]
    y = [0, 0, 0, 1, 1, 1, 1, 1]
    model = fit_shallow_tree(
        X,
        y,
        config=DiscoveryModelConfig(
            max_depth=2,
            min_samples_leaf=2,
        ),
    )
    rules = extract_positive_leaf_rules(
        model,
        ("relative_volume",),
        minimum_probability=0.6,
        minimum_support=2,
    )
    assert rules
    assert any(
        "relative_volume" in rule.render() for rule in rules
    )
    assert all(len(rule.conditions) <= 2 for rule in rules)
