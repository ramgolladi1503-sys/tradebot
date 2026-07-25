from __future__ import annotations

from copy import deepcopy

import pytest

from research.option_e2e_recertification_v4.all_strategy_authority_closure_v1.signal_authority import (
    CONCLUSIONS,
    assess_signal_ledger_authority,
)


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64


def _canonical() -> dict[str, object]:
    return {
        "dataset_family_id": "FAMILY:NIFTY_SPOT:spot:NSE:5m",
        "dataset_version_id": "VERSION:FAMILY:NIFTY_SPOT:spot:NSE:5m:0123456789abcdef",
        "implementation_hash": HASH_A,
        "parameter_hash": HASH_B,
        "dataset_hash": HASH_C,
        "dataset_authority": "CANONICAL_DATASET_VERSION",
        "feature_cutoff_ts": "2026-01-05T09:20:00+05:30",
        "signal_ts": "2026-01-05T09:20:00+05:30",
        "earliest_entry_ts": "2026-01-05T09:21:00+05:30",
        "fold_identity": "walk-forward-fold-03",
        "split_identity": HASH_D,
        "freeze_provenance": "immutable-manifest:signal-freeze-v1",
        "freeze_ts": "2026-01-05T09:20:30+05:30",
        "outcome_available_ts": "2026-01-05T15:30:00+05:30",
        "outcome_or_pnl_contamination": False,
        "option_price_contamination": False,
        "tuned_after_outcome": False,
        "holdout_contamination": False,
        "historically_invalidated": False,
        "signal_id_unique": True,
        "row_count": 12,
    }


def test_canonical_ledger_requires_all_independent_authorities() -> None:
    result = assess_signal_ledger_authority(_canonical())

    assert result["authority_conclusion"] == "CANONICAL_PRE_OUTCOME_SIGNAL_LEDGER"
    assert set(result["field_authority"].values()) == {"PROVEN", "CLEAR"}
    assert result["authority_reason_codes"] == []
    assert result["read_only"] is True
    assert result["is_order_action"] is False
    assert result["broker_api_called"] is False
    assert result["allowed_for_live_execution"] is False
    assert result["append"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("implementation_hash", ""),
        ("parameter_hash", "not-a-hash"),
        ("dataset_hash", None),
        ("dataset_authority", "CLAIMED"),
        ("feature_cutoff_ts", None),
        ("fold_identity", ""),
        ("split_identity", "d" * 63),
        ("freeze_provenance", None),
        ("outcome_or_pnl_contamination", None),
        ("option_price_contamination", "unknown"),
        ("tuned_after_outcome", None),
        ("holdout_contamination", None),
        ("historically_invalidated", None),
    ],
)
def test_one_missing_authority_field_fails_closed(field: str, value: object) -> None:
    evidence = _canonical()
    evidence[field] = value
    evidence.update({"status": "VALID", "accepted": True, "authority_conclusion": "CANONICAL_PRE_OUTCOME_SIGNAL_LEDGER"})

    result = assess_signal_ledger_authority(evidence)

    assert result["authority_conclusion"] == "INSUFFICIENT_PROVENANCE"
    assert result["authority_reason_codes"]


def test_limited_but_authoritative_dataset_is_not_promoted_to_canonical() -> None:
    evidence = _canonical()
    evidence["dataset_authority"] = "USABLE_WITH_LIMITATIONS"

    result = assess_signal_ledger_authority(evidence)

    assert result["authority_conclusion"] == "VALID_PRECOMPUTED_SIGNALS_WITH_LIMITATIONS"
    assert result["field_authority"]["dataset_authority"] == "PROVEN_WITH_LIMITATIONS"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ({"feature_cutoff_ts": "2026-01-05T09:22:00+05:30"}, "INVALID_SIGNAL_LEDGER"),
        ({"signal_ts": "2026-01-05T09:21:00+05:30"}, "INVALID_SIGNAL_LEDGER"),
        ({"signal_id_unique": False}, "INVALID_SIGNAL_LEDGER"),
        ({"row_count": 0}, "INVALID_SIGNAL_LEDGER"),
        ({"outcome_or_pnl_contamination": True}, "POST_OUTCOME_OR_TUNED"),
        ({"option_price_contamination": True}, "POST_OUTCOME_OR_TUNED"),
        ({"tuned_after_outcome": True}, "POST_OUTCOME_OR_TUNED"),
        ({"freeze_ts": "2026-01-05T15:30:00+05:30"}, "POST_OUTCOME_OR_TUNED"),
        ({"holdout_contamination": True}, "HOLDOUT_CONTAMINATED"),
        ({"historically_invalidated": True}, "INVALIDATED_HISTORICAL_EVIDENCE"),
    ],
)
def test_material_mutations_select_specific_fail_closed_conclusions(
    mutation: dict[str, object], expected: str
) -> None:
    evidence = deepcopy(_canonical())
    evidence.update(mutation)

    result = assess_signal_ledger_authority(evidence)

    assert result["authority_conclusion"] == expected
    assert result["authority_conclusion"] in CONCLUSIONS


def test_precedence_keeps_historical_invalidation_and_holdout_leakage_distinct() -> None:
    invalidated = _canonical()
    invalidated.update({"historically_invalidated": True, "holdout_contamination": True, "tuned_after_outcome": True})
    holdout = _canonical()
    holdout.update({"holdout_contamination": True, "tuned_after_outcome": True})

    assert assess_signal_ledger_authority(invalidated)["authority_conclusion"] == "INVALIDATED_HISTORICAL_EVIDENCE"
    assert assess_signal_ledger_authority(holdout)["authority_conclusion"] == "HOLDOUT_CONTAMINATED"


def test_non_mapping_input_is_invalid_and_cannot_raise_open() -> None:
    result = assess_signal_ledger_authority(None)  # type: ignore[arg-type]

    assert result["authority_conclusion"] == "INVALID_SIGNAL_LEDGER"
    assert result["authority_reason_codes"] == ["ledger_not_mapping"]


def test_malformed_contamination_value_fails_closed_without_raising() -> None:
    evidence = _canonical()
    evidence["option_price_contamination"] = {"claimed": False}

    result = assess_signal_ledger_authority(evidence)

    assert result["authority_conclusion"] == "INSUFFICIENT_PROVENANCE"
    assert "option_price_contamination_unproven" in result["authority_reason_codes"]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("dataset_family_id", "VERSION:FAMILY:NIFTY_SPOT:spot:NSE:5m:0123456789abcdef", "dataset_family_id_invalid"),
        ("dataset_version_id", "FAMILY:NIFTY_SPOT:spot:NSE:5m", "dataset_version_id_invalid"),
    ],
)
def test_dataset_authority_identifiers_are_typed_and_cannot_be_interchanged(
    field: str, value: str, reason: str
) -> None:
    evidence = _canonical()
    evidence[field] = value

    result = assess_signal_ledger_authority(evidence)

    assert result["authority_conclusion"] == "INVALID_SIGNAL_LEDGER"
    assert reason in result["authority_reason_codes"]
