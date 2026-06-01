from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.events import write_json_atomic
from core.paths import logs_dir, repo_logs_dir, runtime_dir


RUNTIME_CANDIDATE_HANDOFF_ROOT_CAUSE_SCHEMA_VERSION = 2
RUNTIME_CANDIDATE_HANDOFF_ROOT_CAUSE_SOURCE = "runtime_candidate_handoff_root_cause_counters_v1"
RUNTIME_CANDIDATE_HANDOFF_ROOT_CAUSE_FILENAME = "candidate_handoff_latest.json"


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


def _upper_text(value: Any) -> str:
    return str(value or "").strip().upper()


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _identity_key(candidate: Mapping[str, Any]) -> str:
    row = _as_mapping(candidate)
    trade_id = str(row.get("trade_id") or "").strip()
    if trade_id:
        return f"trade_id:{trade_id}"
    symbol = str(row.get("symbol") or "").strip().upper()
    token = _safe_float(row.get("instrument_token") or row.get("option_token"))
    strike = _safe_float(row.get("strike"))
    expiry = str(row.get("expiry") or row.get("expiry_date") or "").strip()
    side = str(row.get("side") or row.get("direction") or "").strip().upper()
    if symbol and token is not None:
        return f"symtok:{symbol}:{int(token)}:{side}"
    if symbol and strike is not None and expiry:
        return f"symstrike:{symbol}:{strike}:{expiry}:{side}"
    return "unknown_identity"


def _is_fallback_candidate(candidate: Mapping[str, Any]) -> bool:
    row = _as_mapping(candidate)
    if bool(row.get("synthetic_candidate")):
        return True
    if bool(row.get("forced_fallback_execution")):
        return True
    source_flags = row.get("source_flags")
    if isinstance(source_flags, dict):
        if bool(source_flags.get("recovered_fallback")):
            return True
        if bool(source_flags.get("fallback_applied")):
            return True
    return False

def _contains_any(haystack: Iterable[str], needles: set[str]) -> bool:
    for item in haystack:
        if _upper_text(item) in needles:
            return True
    return False


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
        text = _upper_text(row.get(key))
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
            text = _upper_text(item)
            if text:
                out.append(text)
    return out


def classify_primary_blocker_bucket(candidate: Mapping[str, Any]) -> tuple[str, str]:
    """Return (bucket, primary_blocker_code) for one candidate.

    Exactly one bucket is selected so counts remain explainable.
    """

    codes = _reason_codes(candidate)
    codes_set = set(codes)

    feed_codes = {
        "FEED_STALE",
        "NO_LIVE_OPTION_FEED",
        "WEBSOCKET_DISCONNECTED",
        "WS_DISCONNECTED",
        "NO_WS_TICKS",
        "TICK_STALLED",
        "DEPTH_STALE",
        "DEPTH_STALE_AGE",
    }
    quote_codes = {
        "STALE_QUOTE",
        "MISSING_QUOTE",
        "MISSING_LIVE_BIDASK",
        "MISSING_LIVE_TIMING_CONTEXT",
        "UNVERIFIED_SPREAD",
        "INCONSISTENT_QUOTE",
        "MISSING_SPREAD_CONTEXT",
        "UNKNOWN_QUOTE_SOURCE",
    }
    indicator_codes = {"INDICATORS_MISSING", "MISSING_INDICATORS", "INDICATOR_MISSING"}
    contract_codes = {
        "UNRESOLVED_CONTRACT",
        "MISSING_CONTRACT_FIELDS",
        "MISSING_OPTION_TOKEN",
        "NO_TOKEN",
        "MISSING_INSTRUMENT_TOKEN",
        "CONTRACT_RESOLUTION_FALLBACK_BLOCKED",
        "CONTRACT_FALLBACK",
    }
    latency_codes = {"LATENCY_GUARD", "LATENCY_BLOCKED", "LATENCY"}
    exec_ctx_codes = {"EXECUTION_CONTEXT_DEGRADED", "SOFT_EXECUTION_DEGRADED", "SOFT_EXECUTION_NOT_READY"}

    if codes and _contains_any(codes, feed_codes):
        for code in codes:
            if code in feed_codes:
                return "feed_blocked_count", code
        return "feed_blocked_count", codes[0]
    if codes and _contains_any(codes, indicator_codes):
        for code in codes:
            if code in indicator_codes:
                return "indicator_missing_count", code
        return "indicator_missing_count", codes[0]
    if codes and _contains_any(codes, contract_codes):
        for code in codes:
            if code in contract_codes:
                return "contract_unresolved_count", code
        return "contract_unresolved_count", codes[0]
    if codes and any(code.startswith("LATENCY") for code in codes_set) or _contains_any(codes, latency_codes):
        for code in codes:
            if code in latency_codes or code.startswith("LATENCY"):
                return "latency_blocked_count", code
        return "latency_blocked_count", codes[0]
    if bool(_as_mapping(candidate).get("execution_context_degraded")) or _contains_any(codes, exec_ctx_codes):
        for code in codes:
            if code in exec_ctx_codes:
                return "execution_context_degraded_count", code
        return "execution_context_degraded_count", "EXECUTION_CONTEXT_DEGRADED"
    if codes and _contains_any(codes, quote_codes):
        for code in codes:
            if code in quote_codes:
                return "quote_stale_count", code
        return "quote_stale_count", codes[0]

    # Unknown bucket still increments exactly one counter.
    primary = codes[0] if codes else "UNKNOWN_DROP_REASON"
    return "unknown_drop_reason_count", primary


def build_candidate_handoff_root_cause_payload(
    *,
    cycle_ts_epoch: float,
    strategy_generated_count: int,
    phase2_raw_candidates: list[Mapping[str, Any]] | None,
    phase2_ranked_count: int,
    source: str = RUNTIME_CANDIDATE_HANDOFF_ROOT_CAUSE_SOURCE,
) -> dict[str, Any]:
    raw = list(phase2_raw_candidates or [])
    raw_count = len(raw)
    counters: dict[str, int] = {
        "strategy_generated_count": max(0, int(strategy_generated_count)),
        "feed_blocked_count": 0,
        "quote_stale_count": 0,
        "indicator_missing_count": 0,
        "contract_unresolved_count": 0,
        "latency_blocked_count": 0,
        "execution_context_degraded_count": 0,
        "unknown_drop_reason_count": 0,
        "phase2_raw_count": raw_count,
        "phase2_ranked_count": max(0, int(phase2_ranked_count)),
    }
    counters["pre_phase2_drop_count"] = max(0, int(counters["strategy_generated_count"]) - int(raw_count))

    # Pre-Phase2 shape/identity diagnostics (do not alter candidates; evidence only).
    missing_trade_id = 0
    missing_symbol = 0
    missing_instrument_token = 0
    missing_expiry = 0
    missing_strike = 0
    invalid_shape = 0
    unresolved_contract = 0
    fallback_candidate_count = 0
    recovered_fallback_candidate_count = 0

    identity_keys: Counter[str] = Counter()
    drop_reasons: Counter[str] = Counter()
    for candidate in raw:
        row = _as_mapping(candidate)
        if not row:
            invalid_shape += 1
            continue
        trade_id = str(row.get("trade_id") or "").strip()
        symbol = str(row.get("symbol") or "").strip()
        token = _safe_float(row.get("instrument_token") or row.get("option_token"))
        strike = _safe_float(row.get("strike"))
        expiry = str(row.get("expiry") or row.get("expiry_date") or "").strip()
        hard_blockers = set(_upper_text(v) for v in _as_list(row.get("hard_blockers")) if _upper_text(v))
        if "UNRESOLVED_CONTRACT" in hard_blockers:
            unresolved_contract += 1
        if not trade_id:
            missing_trade_id += 1
        if not symbol:
            missing_symbol += 1
        if token is None:
            missing_instrument_token += 1
        if strike is None:
            missing_strike += 1
        if not expiry:
            missing_expiry += 1
        if _is_fallback_candidate(row):
            fallback_candidate_count += 1
            sf = row.get("source_flags")
            if isinstance(sf, dict) and bool(sf.get("recovered_fallback")):
                recovered_fallback_candidate_count += 1
        identity_keys[_identity_key(row)] += 1

        bucket, primary = classify_primary_blocker_bucket(candidate)
        counters[bucket] = int(counters.get(bucket, 0)) + 1
        drop_reasons[str(primary or "UNKNOWN_DROP_REASON")] += 1

    duplicate_key_counts = {k: int(v) for k, v in identity_keys.items() if int(v) > 1}
    duplicate_count = sum(int(v) - 1 for v in duplicate_key_counts.values())

    top_drop_reasons = {reason: int(count) for reason, count in drop_reasons.most_common(10)}
    return {
        "schema_version": RUNTIME_CANDIDATE_HANDOFF_ROOT_CAUSE_SCHEMA_VERSION,
        "source": str(source),
        "cycle_ts_epoch": float(cycle_ts_epoch),
        **counters,
        "normalized_candidate_count": raw_count,
        "deduped_candidate_count": raw_count,
        "phase2_input_candidate_count": raw_count,
        "invalid_shape_count": int(invalid_shape),
        "missing_trade_id_count": int(missing_trade_id),
        "missing_symbol_count": int(missing_symbol),
        "missing_instrument_token_count": int(missing_instrument_token),
        "missing_expiry_count": int(missing_expiry),
        "missing_strike_count": int(missing_strike),
        "unresolved_contract_count": int(unresolved_contract),
        "duplicate_count": int(duplicate_count),
        "duplicate_key_counts": duplicate_key_counts,
        "fallback_candidate_count": int(fallback_candidate_count),
        "recovered_fallback_candidate_count": int(recovered_fallback_candidate_count),
        "normalization_drop_reason_counts": {},
        "dedup_drop_reason_counts": {},
        "top_drop_reasons": top_drop_reasons,
        "generated_epoch": float(time.time()),
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
    }


def write_candidate_handoff_root_cause_latest(
    *,
    payload: Mapping[str, Any],
    logs_path: Path | None = None,
    runtime_path: Path | None = None,
) -> tuple[Path, Path]:
    # Contract: write both repo-local `logs/` and runtime `.runtime/` latest artifacts.
    # For backward compatibility, also mirror into runtime `logs_dir()` (usually `.runtime/logs`).
    logs_target = Path(logs_path) if logs_path is not None else (repo_logs_dir() / RUNTIME_CANDIDATE_HANDOFF_ROOT_CAUSE_FILENAME)
    runtime_target = Path(runtime_path) if runtime_path is not None else (runtime_dir() / RUNTIME_CANDIDATE_HANDOFF_ROOT_CAUSE_FILENAME)
    runtime_logs_target = logs_dir() / RUNTIME_CANDIDATE_HANDOFF_ROOT_CAUSE_FILENAME
    logs_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_logs_target.parent.mkdir(parents=True, exist_ok=True)
    out = dict(payload) if isinstance(payload, Mapping) else {}
    write_json_atomic(logs_target, out)
    write_json_atomic(runtime_target, out)
    write_json_atomic(runtime_logs_target, out)
    return logs_target, runtime_target


__all__ = [
    "RUNTIME_CANDIDATE_HANDOFF_ROOT_CAUSE_FILENAME",
    "build_candidate_handoff_root_cause_payload",
    "classify_primary_blocker_bucket",
    "write_candidate_handoff_root_cause_latest",
]
