from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from core.events import write_json_atomic
from core.paths import logs_dir, runtime_dir


RUNTIME_PHASE2_REJECTION_EVIDENCE_SCHEMA_VERSION = 1
RUNTIME_PHASE2_REJECTION_EVIDENCE_SOURCE = "runtime_phase2_rejection_evidence_v1"
RUNTIME_PHASE2_REJECTION_EVIDENCE_FILENAME = "phase2_rejection_latest.json"


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if value in (None, "", "None"):
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _lower_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _reason_codes(candidate: Mapping[str, Any]) -> list[str]:
    row = _as_mapping(candidate)
    out: list[str] = []
    for key in (
        "primary_blocker",
        "reject_reason",
        "entry_block_code",
        "execution_block_reason",
        "order_policy_reason",
        "execution_quality_reason_code",
        "quote_validation_status",
    ):
        text = _lower_text(row.get(key))
        if text:
            out.append(text)
    for key in (
        "gate_reasons",
        "blockers",
        "hard_blockers",
        "soft_blockers",
        "execution_blockers",
        "penalty_reasons",
        "confidence_penalty_reasons",
        "phase2_soft_penalties",
    ):
        for item in _as_list(row.get(key)):
            text = _lower_text(item)
            if text:
                out.append(text)
    return out


def build_phase2_rejection_evidence_payload(
    *,
    phase2_state: str | None,
    raw_candidates: list[Mapping[str, Any]] | None,
    ranked_candidates: list[Mapping[str, Any]] | None,
    drop_reason_counts: Mapping[str, int] | None,
) -> dict[str, Any]:
    raw_list = list(raw_candidates or [])
    ranked_list = list(ranked_candidates or [])
    drop_counts = {str(k): int(v or 0) for k, v in dict(drop_reason_counts or {}).items() if str(k)}

    missing_quote_age = 0
    missing_spread = 0
    missing_liquidity = 0
    unknown_quote_source = 0
    fallback_quote = 0
    recovered_fallback = 0
    feed_stale_hard = 0
    unresolved_contract_hard = 0
    queue_only = 0
    advisory = 0
    executable = 0
    enter_present = 0
    selected_present = 0
    invalid_selected_payload = 0

    gate_reason_counter: Counter[str] = Counter()
    execution_quality_counter: Counter[str] = Counter()
    hard_blocker_counter: Counter[str] = Counter()
    top_nonexec_counter: Counter[str] = Counter()

    for row in ranked_list:
        c = _as_mapping(row)
        if c.get("selected_candidate"):
            selected_present += 1
        if str(c.get("action") or "").strip().upper() in {"ENTER", "BUY", "SELL"}:
            enter_present += 1
        if not isinstance(c.get("selected_payload"), (dict, type(None))):
            invalid_selected_payload += 1

        candidate_status = _lower_text(c.get("candidate_status"))
        if candidate_status in {"advisory", "advisory_only", "watchlist"}:
            advisory += 1
        if candidate_status == "queue_only":
            queue_only += 1
        if candidate_status in {"executable", "enter"} and bool(c.get("execution_ok", True)):
            executable += 1

        if bool(c.get("phase2_missing_quote_age_sec")):
            missing_quote_age += 1
        if bool(c.get("phase2_missing_spread_context")):
            missing_spread += 1
        if bool(c.get("phase2_missing_liquidity_validation")):
            missing_liquidity += 1
        if _lower_text(c.get("quote_source")) in {"", "unknown", "none"}:
            unknown_quote_source += 1

        if bool(c.get("phase2_spread_fallback_used")) or bool(c.get("phase2_liquidity_fallback_used")):
            fallback_quote += 1
        source_flags = c.get("source_flags")
        if isinstance(source_flags, dict) and bool(source_flags.get("recovered_fallback")):
            recovered_fallback += 1

        codes = _reason_codes(c)
        for code in codes:
            gate_reason_counter[code] += 1
        eq = _lower_text(c.get("execution_quality_reason_code"))
        if eq:
            execution_quality_counter[eq] += 1
        for hb in _as_list(c.get("hard_blockers")):
            hb_text = _lower_text(hb)
            if hb_text:
                hard_blocker_counter[hb_text] += 1
        primary = _lower_text(c.get("execution_quality_reason_code") or "") or (
            _lower_text(c.get("primary_blocker") or "") or ""
        )
        if primary and not bool(c.get("execution_ok", True)):
            top_nonexec_counter[primary] += 1

        if any(code in {"feed_stale", "no_ws_ticks", "tick_stalled", "depth_stale", "depth_stale_age"} for code in codes):
            feed_stale_hard += 1
        if any(code in {"unresolved_contract", "missing_contract_fields", "missing_option_token", "no_token"} for code in codes):
            unresolved_contract_hard += 1

    payload = {
        "schema_version": RUNTIME_PHASE2_REJECTION_EVIDENCE_SCHEMA_VERSION,
        "source": RUNTIME_PHASE2_REJECTION_EVIDENCE_SOURCE,
        "phase2_state": str(phase2_state or "").strip() or None,
        "input_candidate_count": int(len(raw_list)),
        "ranked_candidate_count": int(len(ranked_list)),
        "executable_candidate_count": int(executable),
        "advisory_candidate_count": int(advisory),
        "queue_only_count": int(queue_only),
        "selected_candidate_present": bool(selected_present > 0),
        "enter_candidate_present": bool(enter_present > 0),
        "missing_quote_age_count": int(missing_quote_age),
        "missing_spread_count": int(missing_spread),
        "missing_liquidity_count": int(missing_liquidity),
        "unknown_quote_source_count": int(unknown_quote_source),
        "fallback_quote_count": int(fallback_quote),
        "recovered_fallback_count": int(recovered_fallback),
        "feed_stale_hard_block_count": int(feed_stale_hard),
        "unresolved_contract_hard_block_count": int(unresolved_contract_hard),
        "invalid_selected_payload_count": int(invalid_selected_payload),
        "gate_reason_counts": dict(gate_reason_counter),
        "execution_quality_reason_code_counts": dict(execution_quality_counter),
        "hard_blocker_counts": dict(hard_blocker_counter),
        "drop_reason_counts": drop_counts,
        "top_non_executable_reasons": dict(top_nonexec_counter.most_common(12)),
        "generated_epoch": float(time.time()),
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
    }
    return json_roundtrip(payload)


def json_roundtrip(payload: dict[str, Any]) -> dict[str, Any]:
    # Ensures deterministic json-serializable payload without surprising types.
    return {k: payload[k] for k in payload.keys()}


def write_phase2_rejection_evidence_latest(
    *,
    payload: Mapping[str, Any],
    logs_path: Path | None = None,
    runtime_path: Path | None = None,
) -> tuple[Path, Path]:
    logs_target = Path(logs_path) if logs_path is not None else (logs_dir() / RUNTIME_PHASE2_REJECTION_EVIDENCE_FILENAME)
    runtime_target = Path(runtime_path) if runtime_path is not None else (runtime_dir() / RUNTIME_PHASE2_REJECTION_EVIDENCE_FILENAME)
    logs_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    out = dict(payload) if isinstance(payload, Mapping) else {}
    write_json_atomic(logs_target, out)
    write_json_atomic(runtime_target, out)
    return logs_target, runtime_target


__all__ = [
    "RUNTIME_PHASE2_REJECTION_EVIDENCE_FILENAME",
    "build_phase2_rejection_evidence_payload",
    "write_phase2_rejection_evidence_latest",
]

