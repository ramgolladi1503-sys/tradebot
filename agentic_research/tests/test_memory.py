from agentic_research.contracts import HypothesisRecord
from agentic_research.memory import HypothesisRegistry


def record(identifier="H1"):
    return HypothesisRecord(
        hypothesis_id=identifier,
        strategy_id="trend_pullback_v1",
        observed_failure="range losses",
        economic_reasoning="continuation requires directionality",
        proposed_change="add frozen regime gate",
        changed_fields=["minimum_adx"],
        rejection_condition="OOS expectancy remains non-positive",
        dataset_hash="abc",
    )


def test_registry_rejects_duplicate_hypothesis(tmp_path):
    registry = HypothesisRegistry(tmp_path / "hypotheses.sqlite")
    created, _ = registry.register(record("H1"))
    duplicate, existing = registry.register(record("H2"))
    assert created is True
    assert duplicate is False
    assert existing.hypothesis_id == "H1"
    assert len(registry.list_for_strategy("trend_pullback_v1")) == 1
