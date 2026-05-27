from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Mapping

from core.events import write_json_atomic
from core.paths import data_root

RUNTIME_CANDIDATE_HANDOFF_SCHEMA_VERSION = 1
RUNTIME_CANDIDATE_HANDOFF_SOURCE = "runtime_candidate_handoff_evidence_v1"
RUNTIME_CANDIDATE_HANDOFF_FILENAME = "runtime_candidate_handoff_latest.json"


_NON_ACTION_FLAGS = {
    "read_only": True,
    "append": False,
    "is_order_action": False,
    "broker_api_called": False,
    "live_order_action": False,
    "broker_order_action": False,
}


def runtime_candidate_handoff_path(path: str | Path | None = None) -> Path:
    """Return the latest runtime candidate handoff evidence path."""

    if path is not None:
        return Path(path).expanduser()
    return data_root() / RUNTIME_CANDIDATE_HANDOFF_FILENAME


def build_runtime_candidate_handoff_payload(
    *,
    symbol: str,
    trade_builder_raw_count: int = 0,
    post_scan_survivor_count: int = 0,
    post_soft_reject_count: int | None = None,
    post_real_filter_count: int = 0,
    post_executable_filter_count: int = 0,
    ranked_total_count: int = 0,
    ranked_executable_count: int = 0,
    top_reportable_executable: Mapping[str, Any] | None = None,
    cycle_ranked_candidates_count_before_append: int | None = None,
    cycle_ranked_candidates_count_after_append: int | None = None,
    phase2_input_count: int | None = None,
    top_opportunities_payload: Mapping[str, Any] | None = None,
    generated_epoch: float | None = None,
) -> dict[str, Any]:
    """Build read-only evidence for candidate movement across runtime boundaries.

    The payload is intentionally diagnostic-only. It does not mutate candidates,
    run Phase 2, score trades, loosen gates, or call brokers.
    """

    top_payload = dict(top_opportunities_payload or {})
    phase2_input = _non_negative_int(
        phase2_input_count
        if phase2_input_count is not None
        else top_payload.get("source_candidate_count")
    )
    top_source_count = _non_negative_int(top_payload.get("source_candidate_count"))
    top_executable_count = _non_negative_int(top_payload.get("top_executable_count"))
    ranked_exec_count = _non_negative_int(ranked_executable_count)
    top_exec = _safe_mapping(top_reportable_executable)
    top_exec_trade_id = _text(
        top_exec.get("trade_id")
        or top_exec.get("candidate_id")
        or top_exec.get("id")
    ) or None
    has_reportable_executable = bool(top_exec) or ranked_exec_count > 0
    handoff_mismatch = bool(
        has_reportable_executable
        and (phase2_input == 0 or top_source_count == 0 or top_executable_count == 0)
    )
    mismatch_reason = ""
    if handoff_mismatch:
        mismatch_reason = "trade_builder_reportable_executable_candidates_not_visible_to_phase2_or_top_opportunities"

    payload = {
        "schema_version": RUNTIME_CANDIDATE_HANDOFF_SCHEMA_VERSION,
        "source": RUNTIME_CANDIDATE_HANDOFF_SOURCE,
        **_NON_ACTION_FLAGS,
        "symbol": _symbol(symbol),
        "trade_builder_raw_count": _non_negative_int(trade_builder_raw_count),
        "post_scan_survivor_count": _non_negative_int(post_scan_survivor_count),
        "post_soft_reject_count": _non_negative_int(post_soft_reject_count),
        "post_real_filter_count": _non_negative_int(post_real_filter_count),
        "post_executable_filter_count": _non_negative_int(post_executable_filter_count),
        "ranked_total_count": _non_negative_int(ranked_total_count),
        "ranked_executable_count": ranked_exec_count,
        "top_reportable_executable_trade_id": top_exec_trade_id,
        "top_reportable_executable": bool(has_reportable_executable),
        "top_reportable_executable_snapshot": top_exec,
        "cycle_ranked_candidates_count_before_append": _optional_non_negative_int(cycle_ranked_candidates_count_before_append),
        "cycle_ranked_candidates_count_after_append": _optional_non_negative_int(cycle_ranked_candidates_count_after_append),
        "phase2_input_count": phase2_input,
        "top_opportunities_source_candidate_count": top_source_count,
        "top_opportunities_executable_count": top_executable_count,
        "top_opportunities_phase2_state": _text(top_payload.get("phase2_state")) or None,
        "top_opportunities_selector_outcome": _text(top_payload.get("selector_outcome")) or None,
        "handoff_mismatch": handoff_mismatch,
        "mismatch_reason": mismatch_reason,
        "generated_epoch": float(time.time() if generated_epoch is None else generated_epoch),
        "metadata": {
            "runtime_evidence_file": RUNTIME_CANDIDATE_HANDOFF_FILENAME,
            "does_not_change_gate_decision": True,
            "does_not_change_candidate_state": True,
            "does_not_run_phase2": True,
            "does_not_compute_indicators": True,
            "does_not_call_broker": True,
        },
    }
    return payload


def write_runtime_candidate_handoff_evidence(
    *,
    path: str | Path | None = None,
    **payload_kwargs: Any,
) -> Path:
    """Write latest read-only candidate handoff evidence atomically."""

    payload = build_runtime_candidate_handoff_payload(**payload_kwargs)
    return write_json_atomic(runtime_candidate_handoff_path(path), payload)


def _safe_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def _optional_non_negative_int(value: Any) -> int | None:
    if value is None:
        return None
    return _non_negative_int(value)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _symbol(value: Any) -> str:
    return _text(value).upper().replace(" ", "_").replace("-", "_") or "UNKNOWN"


__all__ = [
    "RUNTIME_CANDIDATE_HANDOFF_FILENAME",
    "RUNTIME_CANDIDATE_HANDOFF_SCHEMA_VERSION",
    "RUNTIME_CANDIDATE_HANDOFF_SOURCE",
    "build_runtime_candidate_handoff_payload",
    "runtime_candidate_handoff_path",
    "write_runtime_candidate_handoff_evidence",
]
