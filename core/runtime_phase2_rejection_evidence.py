from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from core.events import write_json_atomic
from core.paths import logs_dir, repo_logs_dir, runtime_dir


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


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _candidate_identity_key(candidate: Mapping[str, Any]) -> str:
    row = _as_mapping(candidate)
    trade_id = str(row.get("trade_id") or "").strip()
    if trade_id:
        return f"trade_id:{trade_id}"
    symbol = str(row.get("symbol") or "").strip().upper()
    token = _safe_float(row.get("instrument_token") or row.get("option_token"))
    strike = _safe_float(row.get("strike"))
    expiry = str(row.get("expiry") or row.get("expiry_date") or "").strip()
    if symbol and token is not None:
        return f"symtok:{symbol}:{int(token)}"
    if symbol and strike is not None and expiry:
        return f"symstrike:{symbol}:{strike}:{expiry}"
    return f"row:{id(row)}"


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


def _hard_execution_blocker_category(reason_code: str) -> str:
    code = _lower_text(reason_code)
    if not code:
        return "unknown"
    if code in {"feed_stale", "no_ws_ticks", "tick_stalled", "depth_stale", "depth_stale_age", "no_live_option_feed", "ws_disconnected", "global_feed_unhealthy", "stale_option_ltp", "ltp_stale"}:
        return "feed"
    if code.startswith("latency_guard_"):
        return "latency_guard"
    if code in {"unresolved_contract", "missing_contract_fields", "missing_option_token", "no_token"}:
        return "contract"
    if code in {"hard_liquidity", "hard_spread_too_wide", "spread_breached"}:
        return "liquidity_or_spread"
    return "unknown"


def _phase2_drop_category(candidate: Mapping[str, Any]) -> str:
    row = _as_mapping(candidate)
    codes = { _lower_text(code) for code in _reason_codes(row) if _lower_text(code) }
    candidate_status = _lower_text(row.get("candidate_status"))
    execution_status = _lower_text(row.get("execution_status"))
    source_flags = row.get("source_flags")
    if isinstance(source_flags, Mapping):
        if bool(source_flags.get("recovered_fallback")) or bool(source_flags.get("fallback_applied")):
            return "synthetic_or_fallback"
    if bool(row.get("synthetic_candidate")) or bool(row.get("forced_fallback_execution")):
        return "synthetic_or_fallback"
    if candidate_status in {"advisory", "advisory_only", "watchlist"} or execution_status in {"advisory_only", "queue_only"}:
        return "advisory_or_queue_only"
    if "feed_truth_blocked" in codes or any(code in {"feed_stale", "no_ws_ticks", "tick_stalled", "depth_stale", "depth_stale_age", "no_live_option_feed", "ws_disconnected", "global_feed_unhealthy", "recovery_blocked", "process_restart_required"} for code in codes):
        return "feed_truth_blocked"
    if any(code in {"feed_stale", "no_ws_ticks", "tick_stalled", "depth_stale", "depth_stale_age", "no_live_option_feed", "ws_disconnected", "global_feed_unhealthy", "recovery_blocked", "process_restart_required"} for code in codes):
        return "feed_truth_blocked"
    if any(code in {"stale_option_ltp", "ltp_stale"} for code in codes):
        return "stale_option_ltp"
    if not bool(row.get("execution_ok", True)) or any(code.startswith("hard_execution") for code in codes) or "hard_execution" in codes:
        return "hard_execution"
    if bool(row.get("phase2_missing_quote_age_sec")) or _safe_float(row.get("quote_age_sec")) is None:
        return "missing_live_timing_context"
    if bool(row.get("phase2_missing_spread_context")) or _safe_float(row.get("spread_pct")) is None:
        return "missing_spread_context"
    if bool(row.get("phase2_missing_liquidity_validation")) or _safe_float(row.get("liquidity_score")) is None:
        return "missing_liquidity_context"
    if _lower_text(row.get("quote_source")) in {"", "unknown", "none"}:
        return "unknown_quote_source"
    return "unknown_drop_reason"


def build_phase2_rejection_evidence_payload(
    *,
    phase2_state: str | None,
    raw_candidates: list[Mapping[str, Any]] | None,
    ranked_candidates: list[Mapping[str, Any]] | None,
    drop_reason_counts: Mapping[str, int] | None,
    feed_truth: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    raw_list = list(raw_candidates or [])
    ranked_list = list(ranked_candidates or [])
    drop_counts = {str(k): int(v or 0) for k, v in dict(drop_reason_counts or {}).items() if str(k)}
    feed_truth_row = _as_mapping(feed_truth)
    feed_truth_state = _lower_text(
        feed_truth_row.get("feed_truth_state")
        or feed_truth_row.get("state")
        or feed_truth_row.get("runtime_state")
    ) or None
    feed_truth_allows_executable_candidates = feed_truth_row.get("feed_truth_allows_executable_candidates")
    if isinstance(feed_truth_allows_executable_candidates, str):
        feed_truth_allows_executable_candidates = _lower_text(feed_truth_allows_executable_candidates) in {"1", "true", "yes", "on"}
    if feed_truth_allows_executable_candidates is not None:
        feed_truth_allows_executable_candidates = bool(feed_truth_allows_executable_candidates)
    feed_truth_block_reason = _lower_text(
        feed_truth_row.get("feed_truth_block_reason")
        or feed_truth_row.get("block_reason")
        or feed_truth_row.get("reconnect_blocked_reason")
        or feed_truth_row.get("last_error")
    ) or None
    feed_truth_blocked = bool(
        feed_truth_state in {"dead", "recovery_blocked", "subscribe_failed", "auth_blocked", "import_missing"}
        or feed_truth_allows_executable_candidates is False
        or feed_truth_row.get("ws_connected") is False
    )

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
    category_counter: Counter[str] = Counter()

    for row in ranked_list:
        c = _as_mapping(row)
        if c.get("selected_candidate"):
            selected_present += 1
        if str(c.get("action") or "").strip().upper() in {"ENTER", "BUY", "SELL"}:
            enter_present += 1
        if not isinstance(c.get("selected_payload"), (dict, type(None))):
            invalid_selected_payload += 1

    for row in raw_list:
        c = _as_mapping(row)
        candidate_status = _lower_text(c.get("candidate_status"))
        if candidate_status in {"advisory", "advisory_only", "watchlist"}:
            advisory += 1
        if candidate_status == "queue_only":
            queue_only += 1
        if candidate_status in {"executable", "enter"} and bool(c.get("execution_ok", True)):
            executable += 1

        if bool(c.get("phase2_missing_quote_age_sec")) or _safe_float(c.get("quote_age_sec")) is None:
            missing_quote_age += 1
        if bool(c.get("phase2_missing_spread_context")) or _safe_float(c.get("spread_pct")) is None:
            missing_spread += 1
        if bool(c.get("phase2_missing_liquidity_validation")) or _safe_float(c.get("liquidity_score")) is None:
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

        category = _phase2_drop_category(c)
        category_counter[category] += 1
        if any(code in {"feed_stale", "no_ws_ticks", "tick_stalled", "depth_stale", "depth_stale_age"} for code in codes):
            feed_stale_hard += 1
        if any(code in {"unresolved_contract", "missing_contract_fields", "missing_option_token", "no_token"} for code in codes):
            unresolved_contract_hard += 1

    input_count = int(len(raw_list))
    output_count = int(len(ranked_list))
    rejected_count = max(0, input_count - output_count)
    if input_count <= 0:
        phase2_input_state = "NO_INPUT"
    elif output_count <= 0:
        phase2_input_state = "INPUT_DROPPED"
    elif rejected_count > 0:
        phase2_input_state = "PARTIALLY_DROPPED"
    else:
        phase2_input_state = "ACCEPTED"

    starvation_reason = "upstream_starvation"
    if input_count <= 0:
        if feed_truth_blocked:
            starvation_reason = feed_truth_block_reason or feed_truth_state or "feed_truth_blocked"
        elif feed_truth_state:
            starvation_reason = feed_truth_state
    elif output_count <= 0:
        if category_counter:
            starvation_reason = category_counter.most_common(1)[0][0]

    payload = {
        "schema_version": RUNTIME_PHASE2_REJECTION_EVIDENCE_SCHEMA_VERSION,
        "source": RUNTIME_PHASE2_REJECTION_EVIDENCE_SOURCE,
        "phase2_state": str(phase2_state or "").strip() or None,
        "phase2_input_count": input_count,
        "phase2_output_count": output_count,
        "phase2_accepted_count": output_count,
        "phase2_rejected_count": rejected_count,
        "phase2_input_state": phase2_input_state,
        "phase2_starvation_reason": starvation_reason if input_count <= 0 or output_count <= 0 else None,
        "input_candidate_count": int(input_count),
        "ranked_candidate_count": int(output_count),
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
        "selected_contract_quote_missing_count": int(
            sum(
                1
                for row in ranked_list
                if _safe_float(_as_mapping(row).get("quote_ts_epoch")) is None
                and _safe_float(_as_mapping(row).get("quote_age_sec")) is None
            )
        ),
        "selected_contract_token_missing_count": int(
            sum(
                1
                for row in ranked_list
                if _safe_float(_as_mapping(row).get("instrument_token")) is None
                and _safe_float(_as_mapping(row).get("option_token")) is None
            )
        ),
        "invalid_selected_payload_count": int(invalid_selected_payload),
        "gate_reason_counts": dict(gate_reason_counter),
        "execution_quality_reason_code_counts": dict(execution_quality_counter),
        "hard_blocker_counts": dict(hard_blocker_counter),
        "hard_execution_blocker_details": [
            {
                "reason_code": str(reason).strip().upper(),
                "count": int(count),
                "category": _hard_execution_blocker_category(reason),
            }
            for reason, count in sorted(
                ((str(reason), int(count or 0)) for reason, count in hard_blocker_counter.items() if str(reason).strip()),
                key=lambda item: (-int(item[1]), str(item[0])),
            )
        ],
        "drop_reason_counts": drop_counts,
        "phase2_drop_counts": dict(drop_counts),
        "phase2_drop_reasons_by_category": dict(category_counter),
        "hard_blocker_source_counts": {
            "FEED_STALE": int(drop_counts.get("hard_feed_stale", 0) or 0),
            "UNRESOLVED_CONTRACT": int(drop_counts.get("hard_unresolved_contract", 0) or 0),
        },
        "hard_execution": int(category_counter.get("hard_execution", 0)),
        "missing_live_timing_context": int(category_counter.get("missing_live_timing_context", 0)),
        "missing_spread_context": int(category_counter.get("missing_spread_context", 0)),
        "missing_liquidity_context": int(category_counter.get("missing_liquidity_context", 0)),
        "unknown_quote_source": int(category_counter.get("unknown_quote_source", 0)),
        "feed_truth_blocked": int(category_counter.get("feed_truth_blocked", 0)),
        "stale_option_ltp": int(category_counter.get("stale_option_ltp", 0)),
        "advisory_or_queue_only": int(category_counter.get("advisory_or_queue_only", 0)),
        "synthetic_or_fallback": int(category_counter.get("synthetic_or_fallback", 0)),
        "top_non_executable_reasons": dict(top_nonexec_counter.most_common(12)),
        "feed_truth_state": feed_truth_state,
        "feed_truth_allows_executable_candidates": feed_truth_allows_executable_candidates,
        "feed_truth_blocked_flag": bool(feed_truth_blocked),
        "feed_truth_block_reason": feed_truth_block_reason,
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
    # Contract: write both repo-local `logs/` and runtime `.runtime/` latest artifacts.
    # For backward compatibility, also mirror into runtime `logs_dir()` (usually `.runtime/logs`).
    logs_target = Path(logs_path) if logs_path is not None else (repo_logs_dir() / RUNTIME_PHASE2_REJECTION_EVIDENCE_FILENAME)
    runtime_target = Path(runtime_path) if runtime_path is not None else (runtime_dir() / RUNTIME_PHASE2_REJECTION_EVIDENCE_FILENAME)
    runtime_logs_target = logs_dir() / RUNTIME_PHASE2_REJECTION_EVIDENCE_FILENAME
    logs_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_logs_target.parent.mkdir(parents=True, exist_ok=True)
    out = dict(payload) if isinstance(payload, Mapping) else {}
    write_json_atomic(logs_target, out)
    write_json_atomic(runtime_target, out)
    write_json_atomic(runtime_logs_target, out)
    return logs_target, runtime_target


__all__ = [
    "RUNTIME_PHASE2_REJECTION_EVIDENCE_FILENAME",
    "build_phase2_rejection_evidence_payload",
    "write_phase2_rejection_evidence_latest",
]
