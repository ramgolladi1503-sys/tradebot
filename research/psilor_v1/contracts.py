from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

import pandas as pd

from .calibration import PSILORError, ensure_no_future_fields


_REQUIRED_EVENT_FIELDS = (
    "timestamp",
    "source_max_timestamp",
    "shock_direction",
    "participation_shock_z",
    "index_underreaction_z",
    "participation_persistence_z",
    "participation_collapse_z",
    "index_catchup_z",
    "index_reversal_z",
)


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _finite(row: Mapping[str, Any], field: str) -> float:
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise PSILORError(f"{field} must be numeric") from exc
    if not math.isfinite(value):
        raise PSILORError(f"{field} must be finite")
    return value


def evaluate_event_location(
    snapshot: Mapping[str, Any],
    *,
    specification: Mapping[str, Any],
    branch: str,
) -> dict[str, Any]:
    missing = [field for field in _REQUIRED_EVENT_FIELDS if field not in snapshot]
    if missing:
        raise PSILORError(f"event snapshot missing fields: {missing}")
    ensure_no_future_fields(snapshot)
    branch_name = str(branch).upper()
    if branch_name not in {"REVERSAL", "CONTINUATION"}:
        raise PSILORError("branch must be REVERSAL or CONTINUATION")
    direction = str(snapshot["shock_direction"]).upper()
    if direction not in {"UP", "DOWN"}:
        raise PSILORError("shock_direction must be UP or DOWN")

    decision_ts = pd.Timestamp(snapshot["timestamp"])
    source_ts = pd.Timestamp(snapshot["source_max_timestamp"])
    decision_ts = (
        decision_ts.tz_localize("UTC")
        if decision_ts.tzinfo is None
        else decision_ts.tz_convert("UTC")
    )
    source_ts = (
        source_ts.tz_localize("UTC")
        if source_ts.tzinfo is None
        else source_ts.tz_convert("UTC")
    )

    reasons: list[str] = []
    if source_ts > decision_ts:
        reasons.append("SOURCE_TIMESTAMP_AFTER_DECISION")
    thresholds = specification["event_location"]
    if _finite(snapshot, "participation_shock_z") < float(
        thresholds["participation_shock_z_min"]
    ):
        reasons.append("PARTICIPATION_SHOCK_TOO_WEAK")
    if _finite(snapshot, "index_underreaction_z") < float(
        thresholds["index_underreaction_z_min"]
    ):
        reasons.append("INDEX_UNDERREACTION_TOO_WEAK")

    if branch_name == "REVERSAL":
        if _finite(snapshot, "participation_collapse_z") < float(
            thresholds["participation_collapse_z_min"]
        ):
            reasons.append("PARTICIPATION_DID_NOT_COLLAPSE")
        if _finite(snapshot, "index_reversal_z") < float(
            thresholds["index_reversal_z_min"]
        ):
            reasons.append("INDEX_REVERSAL_NOT_CONFIRMED")
        trade_direction = "BEARISH" if direction == "UP" else "BULLISH"
    else:
        if _finite(snapshot, "participation_persistence_z") < float(
            thresholds["participation_persistence_z_min"]
        ):
            reasons.append("PARTICIPATION_DID_NOT_PERSIST")
        if _finite(snapshot, "index_catchup_z") < float(
            thresholds["index_catchup_z_min"]
        ):
            reasons.append("INDEX_CATCHUP_NOT_CONFIRMED")
        trade_direction = "BULLISH" if direction == "UP" else "BEARISH"

    option_type = "CE" if trade_direction == "BULLISH" else "PE"
    economic = {
        "strategy_id": specification["strategy_id"],
        "branch": branch_name,
        "shock_direction": direction,
        "trade_direction": trade_direction,
        "option_type": option_type,
        "event_window_seconds": dict(specification["elapsed_windows_seconds"]),
    }
    return {
        "eligible": not reasons,
        "rejection_reasons": sorted(set(reasons)),
        "branch": branch_name,
        "trade_direction": trade_direction,
        "option_type": option_type,
        "event_rule_hash": canonical_hash(economic),
        "read_only": True,
        "is_order_action": False,
        "allowed_for_live_execution": False,
    }


def event_signal_fingerprint(
    snapshots: list[Mapping[str, Any]],
    *,
    specification: Mapping[str, Any],
    branch: str,
) -> str:
    rows = []
    for snapshot in snapshots:
        clean = {
            key: value
            for key, value in snapshot.items()
            if not any(
                token in str(key).lower()
                for token in ("future", "outcome", "realized", "exit_")
            )
        }
        result = evaluate_event_location(
            clean, specification=specification, branch=branch
        )
        rows.append(
            {
                "timestamp": str(clean["timestamp"]),
                "eligible": result["eligible"],
                "rejection_reasons": result["rejection_reasons"],
                "event_rule_hash": result["event_rule_hash"],
            }
        )
    return canonical_hash(rows)
