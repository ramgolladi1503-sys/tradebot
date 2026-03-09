import pytest

from core.contracts.invariants import InvariantViolation, assert_invariants


def _valid_snapshot() -> dict:
    return {
        "schema_version": 1,
        "snapshot_id": "snap-001",
        "timestamp_epoch": 1772428800.123,
        "token_coverage": {
            "index_token": 256265,
            "option_tokens_count": 73,
        },
        "freshness": {
            "max_tick_age_sec": 1.2,
            "sla_threshold_sec": 2.5,
        },
        "data_sources": {
            "ticks": "db",
            "depth": "db",
        },
    }


def test_valid_snapshot_passes() -> None:
    snapshot = _valid_snapshot()
    assert_invariants(snapshot, stage="unit_test")


@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (lambda s: s.pop("schema_version", None), "INV_SCHEMA_FIELDS_REQUIRED"),
        (lambda s: s.pop("snapshot_id", None), "INV_SCHEMA_FIELDS_REQUIRED"),
        (lambda s: s.pop("token_coverage", None), "INV_TOKEN_COVERAGE_REQUIRED"),
        (lambda s: s.pop("freshness", None), "INV_FRESHNESS_REQUIRED"),
        (lambda s: s.__setitem__("data_sources", {"ticks": "memory"}), "INV_DATA_SOURCES_DB_ONLY"),
    ],
)
def test_missing_or_invalid_fields_fail_with_codes(mutator, code: str) -> None:
    snapshot = _valid_snapshot()
    mutator(snapshot)
    with pytest.raises(InvariantViolation) as exc:
        assert_invariants(snapshot, stage="unit_test")
    assert exc.value.code == code


def test_forbidden_timestamp_keys_fail() -> None:
    snapshot = _valid_snapshot()
    snapshot["payload"] = {
        "inner": {
            "ts_epoch": 123.0,
        }
    }
    with pytest.raises(InvariantViolation) as exc:
        assert_invariants(snapshot, stage="unit_test")
    assert exc.value.code == "INV_TIMESTAMP_KEYS_FORBIDDEN"
