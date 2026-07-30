from core.trade_builder_characterization import (
    assert_repeatable,
    characterize_builder,
    hash_builder_output,
    normalize_builder_output,
)


class DeterministicBuilder:
    def build(self, snapshot):
        return {
            "symbol": snapshot["symbol"],
            "confidence": snapshot.get("confidence", 0.5),
            "timestamp": snapshot.get("timestamp"),
            "blockers": set(snapshot.get("blockers", [])),
        }


class FailingBuilder:
    def build(self, snapshot):
        raise RuntimeError(f"boom:{snapshot['symbol']}")


def test_volatile_fields_do_not_change_hash():
    left = {"symbol": "NIFTY", "timestamp": 1, "score": 0.7}
    right = {"symbol": "NIFTY", "timestamp": 999, "score": 0.7}
    assert hash_builder_output(left) == hash_builder_output(right)


def test_builder_characterization_is_repeatable():
    snapshots = [
        {"case_id": "valid", "symbol": "NIFTY", "confidence": 0.7},
        {"case_id": "blocked", "symbol": "SENSEX", "blockers": ["stale_quote"]},
    ]
    first = characterize_builder(DeterministicBuilder(), snapshots)
    second = characterize_builder(DeterministicBuilder(), snapshots)
    assert_repeatable(first, second)
    assert [row.case_id for row in first] == ["valid", "blocked"]


def test_builder_exception_is_characterized_not_lost():
    records = characterize_builder(
        FailingBuilder(),
        [{"case_id": "failure", "symbol": "NIFTY"}],
    )
    assert records[0].raised is True
    assert records[0].error_type == "RuntimeError"
    assert records[0].normalized_output["error_message"] == "boom:NIFTY"


def test_normalization_sorts_sets_and_mapping_keys():
    normalized = normalize_builder_output(
        {"z": {3, 1, 2}, "a": {"b": 2, "a": 1}}
    )
    assert normalized == {"a": {"a": 1, "b": 2}, "z": [1, 2, 3]}
