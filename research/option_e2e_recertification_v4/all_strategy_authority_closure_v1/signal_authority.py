from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


CONCLUSIONS = frozenset(
    {
        "CANONICAL_PRE_OUTCOME_SIGNAL_LEDGER",
        "VALID_PRECOMPUTED_SIGNALS_WITH_LIMITATIONS",
        "INSUFFICIENT_PROVENANCE",
        "POST_OUTCOME_OR_TUNED",
        "HOLDOUT_CONTAMINATED",
        "INVALIDATED_HISTORICAL_EVIDENCE",
        "INVALID_SIGNAL_LEDGER",
    }
)

_CANONICAL_DATASET_AUTHORITIES = {
    "CANONICAL_DATASET",
    "CANONICAL_DATASET_VERSION",
    "CANONICAL_UNDERLYING_DATASET",
    "PROVEN",
}
_LIMITED_DATASET_AUTHORITIES = {"USABLE_WITH_LIMITATIONS", "PROVEN_WITH_LIMITATIONS"}

_DERIVED_INVALIDATION_REASON = "DERIVED_THROUGH_PROVEN_INVALIDATED_GENERATOR_BINDING"
_DERIVED_INVALIDATION_REASON_PUBLIC = "derived_through_proven_invalidated_generator_binding"
_INVALIDATED_LEDGER_HASH = "b9736aa6af68a07c32a01dbc2bc60220acf8337181e3878940abfab540398bed"
_INVALIDATED_LEDGER_ROWS = 24
_INVALIDATED_ARTIFACT_KIND = "MULTI_OWNER_BLOCKED_PLACEHOLDER_INVENTORY"
_BROKER_CALL_FIELD = "broker_api_called"
_ORDER_ACTION_FIELD = "is_order_action"


def _value(evidence: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in evidence:
            return evidence[name]
    return None


def _present(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdef" for character in value.lower())


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _explicit_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes"}:
            return True
        if normalized in {"0", "false", "no"}:
            return False
    return None


def _historical_status(value: bool | None) -> str:
    if value is False:
        return "CLEAR"
    if value is True:
        return "UNBOUND_ASSERTION"
    return "UNRESOLVED"


def _derived_invalidation_failures(evidence: Mapping[str, Any]) -> list[str]:
    checks = {
        "ledger_hash": (
            _value(evidence, "physical_hash", "physical_sha256", "sha256")
            == _value(evidence, "provenance_ledger_hash")
            == _INVALIDATED_LEDGER_HASH
        ),
        "row_count": (
            _value(evidence, "row_count")
            == _value(evidence, "provenance_row_count")
            == _INVALIDATED_LEDGER_ROWS
        ),
        "artifact_kind": _value(evidence, "artifact_kind") == _INVALIDATED_ARTIFACT_KIND,
        "artifact_verdict": _value(evidence, "artifact_verdict") == "SIGNAL_LEDGER_INVALIDATED",
        "direct_authority": _value(evidence, "direct_ledger_invalidation_authority") == "UNRESOLVED",
        "implementation_authority": _value(evidence, "implementation_invalidation_authority") == "CONFIRMED",
        "derived_authority": _value(evidence, "derived_ledger_invalidation_authority") == "CONFIRMED",
        "derived_reason": _value(evidence, "derived_invalidation_reason_code") == _DERIVED_INVALIDATION_REASON,
        "generator_binding": _value(evidence, "generator_output_binding_status") == "PROVEN",
        "primary_oracle": _value(evidence, "primary_oracle_agreement") == "AGREEMENT",
        "aggregate_owner": _value(evidence, "aggregate_canonical_strategy_id") is None,
        "research_only": _value(evidence, "research_only") is True,
        "read_only": _value(evidence, "read_only") is True,
        "allowed_for_live_execution": _value(evidence, "allowed_for_live_execution") is False,
        "broker_non_action": _value(evidence, _BROKER_CALL_FIELD) is False,
        "order_non_action": _value(evidence, _ORDER_ACTION_FIELD) is False,
    }
    return [name for name, valid in checks.items() if not valid]


def assess_signal_ledger_authority(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Independently classify a precomputed signal ledger from primary fields.

    Upstream status, conclusion, accepted, and valid markers are deliberately
    ignored. Authority must be reconstructable from the evidence fields below.
    """

    if not isinstance(evidence, Mapping):
        return _result("INVALID_SIGNAL_LEDGER", {"ledger": "INVALID"}, ["ledger_not_mapping"])

    implementation_hash = _value(evidence, "implementation_hash", "implementation_sha", "implementation_file_hash")
    parameter_hash = _value(evidence, "parameter_hash", "params_hash")
    dataset_hash = _value(evidence, "dataset_hash", "dataset_source_hash", "source_hash")
    dataset_authority = _value(evidence, "dataset_authority", "dataset_authority_status")
    feature_cutoff = _timestamp(_value(evidence, "feature_cutoff_ts"))
    signal_ts = _timestamp(_value(evidence, "signal_ts"))
    entry_ts = _timestamp(_value(evidence, "earliest_entry_ts", "earliest_legal_entry_ts"))
    fold_identity = _value(evidence, "fold_identity", "fold_id")
    split_identity = _value(evidence, "split_identity", "split_hash")
    freeze_provenance = _value(evidence, "freeze_provenance", "pre_outcome_freeze_provenance")
    freeze_ts = _timestamp(_value(evidence, "freeze_ts", "pre_outcome_freeze_ts"))
    outcome_available_ts = _timestamp(_value(evidence, "outcome_available_ts", "outcome_ts"))
    outcome_contamination = _explicit_bool(_value(evidence, "outcome_or_pnl_contamination", "outcome_contamination"))
    option_price_contamination = _explicit_bool(_value(evidence, "option_price_contamination"))
    tuned_after_outcome = _explicit_bool(_value(evidence, "tuned_after_outcome", "post_outcome_tuning"))
    holdout_contamination = _explicit_bool(_value(evidence, "holdout_contamination"))
    historically_invalidated = _explicit_bool(
        _value(evidence, "historically_invalidated", "historical_invalidation")
    )

    invalid_reasons: list[str] = []
    dataset_family_id = _value(evidence, "dataset_family_id")
    dataset_version_id = _value(evidence, "dataset_version_id")
    if dataset_family_id is not None and (
        not isinstance(dataset_family_id, str)
        or not dataset_family_id.startswith("FAMILY:")
        or dataset_family_id.startswith("VERSION:")
    ):
        invalid_reasons.append("dataset_family_id_invalid")
    if dataset_version_id is not None and (
        not isinstance(dataset_version_id, str) or not dataset_version_id.startswith("VERSION:")
    ):
        invalid_reasons.append("dataset_version_id_invalid")

    fields = {
        "implementation_hash": "PROVEN" if _sha256(implementation_hash) else "MISSING_OR_INVALID",
        "parameter_hash": "PROVEN" if _sha256(parameter_hash) else "MISSING_OR_INVALID",
        "dataset_hash": "PROVEN" if _sha256(dataset_hash) else "MISSING_OR_INVALID",
        "dataset_authority": (
            "PROVEN"
            if dataset_authority in _CANONICAL_DATASET_AUTHORITIES
            else "PROVEN_WITH_LIMITATIONS"
            if dataset_authority in _LIMITED_DATASET_AUTHORITIES
            else "UNPROVEN"
        ),
        "causal_timestamps": (
            "PROVEN"
            if feature_cutoff and signal_ts and entry_ts and feature_cutoff <= signal_ts < entry_ts
            else "INVALID"
            if feature_cutoff and signal_ts and entry_ts
            else "MISSING_OR_INVALID"
        ),
        "fold_identity": "PROVEN" if _present(fold_identity) else "MISSING",
        "split_identity": "PROVEN" if _sha256(split_identity) else "MISSING_OR_INVALID",
        "freeze_provenance": "PROVEN" if _present(freeze_provenance) and freeze_ts else "MISSING_OR_INVALID",
        "outcome_or_pnl_contamination": _bool_status(outcome_contamination),
        "option_price_contamination": _bool_status(option_price_contamination),
        "tuned_after_outcome": _bool_status(tuned_after_outcome),
        "holdout_contamination": _bool_status(holdout_contamination),
        "historical_invalidation": _historical_status(historically_invalidated),
    }

    if fields["causal_timestamps"] == "INVALID":
        invalid_reasons.append("causal_timestamp_order_invalid")
    if freeze_ts and outcome_available_ts and freeze_ts >= outcome_available_ts:
        outcome_contamination = True
        fields["outcome_or_pnl_contamination"] = "CONTAMINATED"
    if _value(evidence, "signal_id_unique") is False:
        invalid_reasons.append("signal_id_not_unique")
    row_count = _value(evidence, "row_count")
    if row_count is not None and (isinstance(row_count, bool) or not isinstance(row_count, int) or row_count <= 0):
        invalid_reasons.append("row_count_invalid")

    if invalid_reasons:
        return _result("INVALID_SIGNAL_LEDGER", fields, invalid_reasons)
    derived_authority = _value(evidence, "derived_ledger_invalidation_authority")
    if derived_authority == "CONFIRMED":
        derived_failures = _derived_invalidation_failures(evidence)
        if derived_failures:
            return _result(
                "INVALID_SIGNAL_LEDGER",
                fields,
                [f"derived_invalidation_{failure}_invalid" for failure in derived_failures],
            )
        fields["historical_invalidation"] = "DERIVED_CONFIRMED"
        return _result(
            "INVALIDATED_HISTORICAL_EVIDENCE",
            fields,
            [_DERIVED_INVALIDATION_REASON_PUBLIC],
        )
    if holdout_contamination is True:
        return _result("HOLDOUT_CONTAMINATED", fields, ["holdout_contamination_proven"])
    if outcome_contamination is True or option_price_contamination is True or tuned_after_outcome is True:
        reasons = []
        if outcome_contamination is True:
            reasons.append("outcome_or_pnl_contamination_proven")
        if option_price_contamination is True:
            reasons.append("option_price_contamination_proven")
        if tuned_after_outcome is True:
            reasons.append("post_outcome_tuning_proven")
        return _result("POST_OUTCOME_OR_TUNED", fields, reasons)

    required = (
        "implementation_hash",
        "parameter_hash",
        "dataset_hash",
        "causal_timestamps",
        "fold_identity",
        "split_identity",
        "freeze_provenance",
    )
    missing = [name for name in required if fields[name] != "PROVEN"]
    missing.extend(
        name
        for name in (
            "outcome_or_pnl_contamination",
            "option_price_contamination",
            "tuned_after_outcome",
            "holdout_contamination",
            "historical_invalidation",
        )
        if fields[name] in {"UNRESOLVED", "UNBOUND_ASSERTION"}
    )
    if fields["dataset_authority"] == "UNPROVEN":
        missing.append("dataset_authority")
    if missing:
        return _result("INSUFFICIENT_PROVENANCE", fields, [f"{name}_unproven" for name in sorted(set(missing))])
    if fields["dataset_authority"] == "PROVEN_WITH_LIMITATIONS":
        return _result(
            "VALID_PRECOMPUTED_SIGNALS_WITH_LIMITATIONS",
            fields,
            ["dataset_authority_has_limitations"],
        )
    return _result("CANONICAL_PRE_OUTCOME_SIGNAL_LEDGER", fields, [])


def _bool_status(value: bool | None) -> str:
    if value is True:
        return "CONTAMINATED"
    if value is False:
        return "CLEAR"
    return "UNRESOLVED"


def _result(conclusion: str, fields: Mapping[str, str], reasons: list[str]) -> dict[str, Any]:
    if conclusion not in CONCLUSIONS:  # pragma: no cover - internal invariant
        raise ValueError(f"unsupported signal-ledger conclusion: {conclusion}")
    return {
        "authority_conclusion": conclusion,
        "field_authority": dict(fields),
        "authority_reason_codes": sorted(set(reasons)),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "append": False,
    }


# Explicit alias for callers that use an audit-oriented verb.
audit_signal_ledger_authority = assess_signal_ledger_authority
