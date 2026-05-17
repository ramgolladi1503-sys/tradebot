import pytest

from core.movement_contract import MovementContractError, StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.movement_registry import (
    MovementStrategyDefinition,
    MovementStrategyRegistry,
    create_empty_movement_strategy_registry,
)


def _candidate(strategy_id="stub_strategy", movement_type="COMPRESSION_BREAKOUT"):
    return StrategyCandidate(
        schema_version=1,
        strategy_id=strategy_id,
        movement_type=movement_type,
        symbol="NIFTY",
        direction="BUY_CALL",
        status="VALIDATED_CANDIDATE",
        raw_score=0.7,
        confidence_score=0.7,
        price_structure_score=0.7,
        option_confirmation_score=0.7,
        liquidity_score=0.7,
        freshness_score=1.0,
        volatility_score=0.6,
        regime_alignment_score=0.8,
        entry_trigger="unit_test_trigger",
        invalid_if="unit_test_invalid",
        rank_reason="unit test candidate",
    )


def _regime(**scores):
    base = {
        "TREND_UP": 0.0,
        "TREND_DOWN": 0.0,
        "RANGE": 0.0,
        "CHOP": 0.0,
        "COMPRESSION": 0.0,
        "VOLATILITY_EXPANSION": 0.0,
        "TRAP_RISK": 0.0,
        "EXHAUSTION_RISK": 0.0,
        "EXPIRY_CONTEXT": 0.0,
        "INCONCLUSIVE": 0.0,
    }
    base.update(scores)
    return MovementRegimeResult(schema_version=1, primary_regime="COMPRESSION", scores=base)


def test_empty_registry_runs_safely_with_no_candidates():
    registry = create_empty_movement_strategy_registry()
    result = registry.run(StrategyContext(symbol="NIFTY"), regime=_regime())

    assert result.candidates == ()
    assert result.activated_strategy_ids == ()
    assert result.suppressed_strategy_ids == ()
    assert result.error_counts == {}


def test_registry_registers_and_runs_enabled_strategy():
    def handler(context, regime):
        assert context.symbol == "NIFTY"
        assert regime.scores["COMPRESSION"] == 0.8
        return _candidate()

    registry = MovementStrategyRegistry()
    registry.register(
        MovementStrategyDefinition(
            strategy_id="stub_strategy",
            handler=handler,
            movement_types=("COMPRESSION_BREAKOUT",),
            min_regime_scores={"COMPRESSION": 0.5},
        )
    )

    result = registry.run(StrategyContext(symbol="nifty"), regime=_regime(COMPRESSION=0.8))

    assert registry.list_strategy_ids() == ("stub_strategy",)
    assert result.activated_strategy_ids == ("stub_strategy",)
    assert result.suppressed_strategy_ids == ()
    assert len(result.candidates) == 1
    assert result.candidates[0].strategy_id == "stub_strategy"


def test_registry_suppresses_strategy_when_regime_threshold_not_met():
    registry = MovementStrategyRegistry(
        [
            MovementStrategyDefinition(
                strategy_id="compression_strategy",
                handler=lambda context, regime: _candidate("compression_strategy"),
                min_regime_scores={"COMPRESSION": 0.75},
            )
        ]
    )

    result = registry.run(StrategyContext(symbol="NIFTY"), regime=_regime(COMPRESSION=0.4))

    assert result.candidates == ()
    assert result.activated_strategy_ids == ()
    assert result.suppressed_strategy_ids == ("compression_strategy",)


def test_registry_captures_strategy_errors_without_killing_run():
    def bad_handler(context, regime):
        raise RuntimeError("boom")

    registry = MovementStrategyRegistry(
        [MovementStrategyDefinition(strategy_id="bad", handler=bad_handler)]
    )

    result = registry.run(StrategyContext(symbol="NIFTY"), regime=_regime())

    assert result.candidates == ()
    assert result.activated_strategy_ids == ("bad",)
    assert result.error_counts == {"bad": 1}
    assert result.errors[0].startswith("strategy_error:bad:RuntimeError:boom")


def test_registry_fail_fast_raises_on_strategy_error():
    registry = MovementStrategyRegistry(
        [MovementStrategyDefinition(strategy_id="bad", handler=lambda context, regime: {"bad": "payload"})]
    )

    with pytest.raises(MovementContractError, match="strategy_error:bad"):
        registry.run(StrategyContext(symbol="NIFTY"), regime=_regime(), fail_fast=True)


def test_registry_rejects_duplicate_strategy_ids_and_bad_definitions():
    registry = MovementStrategyRegistry()
    definition = MovementStrategyDefinition(strategy_id="same", handler=lambda context, regime: None)
    registry.register(definition)

    with pytest.raises(MovementContractError, match="duplicate_strategy_id:same"):
        registry.register(definition)

    with pytest.raises(MovementContractError, match="strategy_handler_not_callable"):
        MovementStrategyDefinition(strategy_id="bad", handler=None)  # type: ignore[arg-type]

    with pytest.raises(MovementContractError, match="strategy_min_regime_score_out_of_range"):
        MovementStrategyDefinition(
            strategy_id="bad_score",
            handler=lambda context, regime: None,
            min_regime_scores={"COMPRESSION": 1.2},
        )
