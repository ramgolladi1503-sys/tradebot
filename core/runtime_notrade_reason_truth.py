from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from core.events import write_json_atomic
from core.paths import logs_dir, repo_logs_dir, runtime_dir


RUNTIME_NOTRADE_REASON_TRUTH_SCHEMA_VERSION = 2
RUNTIME_NOTRADE_REASON_TRUTH_SOURCE = "runtime_notrade_reason_truth_v1"
RUNTIME_NOTRADE_REASON_TRUTH_FILENAME = "notrade_reason_truth_latest.json"


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


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _count_top_reasons(top_map: Mapping[str, Any] | None) -> Counter[str]:
    out: Counter[str] = Counter()
    for k, v in dict(top_map or {}).items():
        key = _lower(k)
        if not key:
            continue
        try:
            out[key] += int(v or 0)
        except Exception:
            out[key] += 1
    return out


def _infer_indicator_ready(row: Mapping[str, Any] | None) -> bool | None:
    if not isinstance(row, Mapping):
        return None
    if "ready" in row:
        try:
            return bool(row.get("ready"))
        except Exception:
            return None
    if "indicators_ok" in row:
        try:
            return bool(row.get("indicators_ok"))
        except Exception:
            return None
    missing_inputs = [str(x).strip().lower() for x in _as_list(row.get("indicator_missing_inputs")) if str(x or "").strip()]
    if missing_inputs:
        return False
    present_keys = ("rsi_present", "ema_present", "atr_present", "vwap_present")
    if any(key in row for key in present_keys):
        try:
            return all(bool(row.get(key)) for key in present_keys if key in row)
        except Exception:
            return False
    return None


def build_notrade_reason_truth_payload(
    *,
    candidate_handoff: Mapping[str, Any] | None,
    phase2_rejection: Mapping[str, Any] | None,
    feed_truth: Mapping[str, Any] | None,
    top_opportunities: Mapping[str, Any] | None,
    cycle_blockers: Mapping[str, Any] | None = None,
    indicator_readiness: Mapping[str, Any] | None = None,
    regime_truth: Mapping[str, Any] | None = None,
    latency_guard: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    handoff = _as_mapping(candidate_handoff)
    phase2 = _as_mapping(phase2_rejection)
    feed = _as_mapping(feed_truth)
    top = _as_mapping(top_opportunities)
    blockers = _as_mapping(cycle_blockers)
    indicator = _as_mapping(indicator_readiness)
    regime = _as_mapping(regime_truth)
    latency = _as_mapping(latency_guard)

    precedence = [
        "market_closed",
        "feed_stale",
        "indicators_missing",
        "regime_unstable",
        "unresolved_contract",
        "missing_quote_truth",
        "fallback_blocked",
        "queue_only",
        "score_below_threshold",
        "strategy_no_edge",
        "unknown",
    ]

    supporting: list[str] = []
    reason_counts: Counter[str] = Counter()

    market_closed_detected = bool(feed.get("market_closed_detected"))
    feed_fresh = bool(feed.get("feed_fresh")) if "feed_fresh" in feed else None
    option_tick_fresh = bool(feed.get("option_tick_fresh")) if "option_tick_fresh" in feed else None
    phase2_input_candidate_count = int(handoff.get("phase2_input_candidate_count") or 0)

    # Upstream gate blockers (pre-Phase2). These are evidence-only and must not
    # change decision logic. They exist to prevent "unknown" when upstream gates
    # are clearly blocking candidate generation.
    upstream_gate_counts: Counter[str] = Counter()
    for key, value in blockers.items():
        code = _upper(key)
        if not code:
            continue
        try:
            count = int(value or 0)
        except Exception:
            count = 1
        if count <= 0:
            continue
        upstream_gate_counts[code] += count

    indicators_missing_count = int(upstream_gate_counts.get("INDICATORS_MISSING") or 0)
    regime_unstable_count = int(upstream_gate_counts.get("REGIME_UNSTABLE") or 0)

    indicator_detail_available = bool(indicator)
    regime_detail_available = bool(regime)
    latency_detail_available = bool(latency)

    missing_indicators_by_symbol = indicator.get("by_symbol") if isinstance(indicator.get("by_symbol"), dict) else {}
    missing_indicators_by_strategy = indicator.get("by_strategy") if isinstance(indicator.get("by_strategy"), dict) else {}
    missing_indicator_counts: Counter[str] = Counter()
    warmup_candle_counts_by_symbol: dict[str, int] = {}
    required_warmup_candle_counts_by_symbol: dict[str, int] = {}
    indicator_ready_by_symbol: dict[str, bool] = {}
    indicator_ready_by_strategy: dict[str, bool] = {}
    indicator_age_sec_by_symbol: dict[str, float | None] = {}
    indicator_source_by_symbol: dict[str, str | None] = {}
    indicator_blocker_reason_counts: Counter[str] = Counter()
    indicator_ready_symbol_count = 0
    indicator_blocked_symbol_count = 0
    for sym, row in dict(missing_indicators_by_symbol or {}).items():
        if not isinstance(row, Mapping):
            continue
        for code in _as_list(row.get("indicator_missing_inputs")):
            name = str(code or "").strip().lower()
            if name:
                missing_indicator_counts[name] += 1
        try:
            warmup_candle_counts_by_symbol[str(sym)] = int(row.get("ohlc_bars_count") or 0)
        except Exception:
            pass
        try:
            required_warmup_candle_counts_by_symbol[str(sym)] = int(row.get("warmup_min_bars") or 0)
        except Exception:
            pass
        ready = _infer_indicator_ready(row)
        if ready is not None:
            indicator_ready_by_symbol[str(sym)] = bool(ready)
            if ready is True:
                indicator_ready_symbol_count += 1
            else:
                indicator_blocked_symbol_count += 1
        indicator_age_sec_by_symbol[str(sym)] = row.get("indicators_age_sec")
        indicator_source_by_symbol[str(sym)] = row.get("source")
        for code in _as_list(row.get("blockers")):
            c = _upper(code)
            if c:
                indicator_blocker_reason_counts[c] += 1

    for strat, row in dict(missing_indicators_by_strategy or {}).items():
        if not isinstance(row, Mapping):
            continue
        try:
            inferred = _infer_indicator_ready(row)
            if inferred is not None:
                indicator_ready_by_strategy[str(strat)] = bool(inferred)
        except Exception:
            pass

    effective_indicators_missing_count = int(indicators_missing_count)
    if effective_indicators_missing_count > 0 and indicator_detail_available:
        all_symbols_ready = bool(indicator_ready_by_symbol) and all(bool(value) for value in indicator_ready_by_symbol.values())
        no_missing_indicator_values = not bool(missing_indicator_counts)
        if all_symbols_ready and no_missing_indicator_values:
            effective_indicators_missing_count = 0

    # Aggregate the most actionable Phase2 evidence buckets.
    feed_stale_count = int(phase2.get("feed_stale_hard_block_count") or 0)
    unresolved_contract_count = int(phase2.get("unresolved_contract_hard_block_count") or 0)
    missing_quote_age = int(phase2.get("missing_quote_age_count") or 0)
    missing_spread = int(phase2.get("missing_spread_count") or 0)
    missing_liquidity = int(phase2.get("missing_liquidity_count") or 0)
    unknown_quote_source = int(phase2.get("unknown_quote_source_count") or 0)
    fallback_quote = int(phase2.get("fallback_quote_count") or 0)
    recovered_fallback = int(phase2.get("recovered_fallback_count") or 0)
    queue_only_count = int(phase2.get("queue_only_count") or 0)

    top_nonexec = _count_top_reasons(phase2.get("top_non_executable_reasons"))
    for k, v in top_nonexec.items():
        if v:
            reason_counts[k] += int(v)

    # Infer primary reason without changing any gates: evidence-only.
    primary_reason = "unknown"
    primary_source = "unknown"

    if market_closed_detected:
        primary_reason = "market_closed"
        primary_source = "feed_truth_latest"
    elif feed_stale_count > 0 or feed_fresh is False or option_tick_fresh is False:
        primary_reason = "feed_stale"
        primary_source = "phase2_rejection_latest" if feed_stale_count > 0 else "feed_truth_latest"
    elif feed_fresh is True and phase2_input_candidate_count <= 0 and effective_indicators_missing_count > 0:
        primary_reason = "indicators_missing"
        primary_source = "cycle_blockers"
    elif feed_fresh is True and phase2_input_candidate_count <= 0 and regime_unstable_count > 0:
        primary_reason = "regime_unstable"
        primary_source = "cycle_blockers"
    elif unresolved_contract_count > 0:
        primary_reason = "unresolved_contract"
        primary_source = "phase2_rejection_latest"
    elif (missing_quote_age + missing_spread + missing_liquidity + unknown_quote_source) > 0:
        primary_reason = "missing_quote_truth"
        primary_source = "phase2_rejection_latest"
    elif (fallback_quote + recovered_fallback) > 0:
        primary_reason = "fallback_blocked"
        primary_source = "phase2_rejection_latest"
    elif queue_only_count > 0:
        primary_reason = "queue_only"
        primary_source = "phase2_rejection_latest"
    else:
        # Fall back to Phase2 top non-executable reasons if present.
        if reason_counts:
            primary_reason = reason_counts.most_common(1)[0][0]
            primary_source = "phase2_rejection_latest"

    # Supporting reasons (ordered, stable).
    if market_closed_detected:
        supporting.append("market_closed")
    if feed_stale_count > 0 or feed_fresh is False or option_tick_fresh is False:
        supporting.append("feed_stale")
    if effective_indicators_missing_count > 0:
        supporting.append("indicators_missing")
    if regime_unstable_count > 0:
        supporting.append("regime_unstable")
    if unresolved_contract_count > 0:
        supporting.append("unresolved_contract")
    if missing_quote_age > 0:
        supporting.append("missing_quote_age")
    if missing_spread > 0:
        supporting.append("missing_spread")
    if missing_liquidity > 0:
        supporting.append("missing_liquidity")
    if unknown_quote_source > 0:
        supporting.append("unknown_quote_source")
    if fallback_quote > 0:
        supporting.append("fallback_quote")
    if recovered_fallback > 0:
        supporting.append("recovered_fallback")

    # Preserve any operator-facing hints already produced elsewhere.
    phase2_state = top.get("phase2_state") or phase2.get("phase2_state")

    payload = {
        "schema_version": RUNTIME_NOTRADE_REASON_TRUTH_SCHEMA_VERSION,
        "source": RUNTIME_NOTRADE_REASON_TRUTH_SOURCE,
        "writer_name": "runtime_notrade_reason_truth",
        "writer_module": __name__,
        "writer_schema_version": RUNTIME_NOTRADE_REASON_TRUTH_SCHEMA_VERSION,
        "primary_reason": primary_reason,
        "primary_reason_source": primary_source,
        "supporting_reasons": supporting,
        "reason_counts": dict(reason_counts),
        "reason_precedence_order": precedence,
        "phase2_state": str(phase2_state or "").strip() or None,
        "top_non_executable_reasons": dict(phase2.get("top_non_executable_reasons") or {}),
        "feed_stale_hard_block_count": int(feed_stale_count),
        "unresolved_contract_hard_block_count": int(unresolved_contract_count),
        "missing_quote_age_count": int(missing_quote_age),
        "missing_spread_count": int(missing_spread),
        "missing_liquidity_count": int(missing_liquidity),
        "unknown_quote_source_count": int(unknown_quote_source),
        "fallback_quote_count": int(fallback_quote),
        "recovered_fallback_count": int(recovered_fallback),
        "queue_only_count": int(queue_only_count),
        "market_closed_detected": bool(market_closed_detected),
        "feed_fresh": feed_fresh,
        "option_tick_fresh": option_tick_fresh,
        "selected_contract_quote_fresh": feed.get("selected_contract_quote_fresh"),
        "phase2_input_candidate_count": int(phase2_input_candidate_count),
        "upstream_gate_reason_counts": dict(upstream_gate_counts),
        "indicator_detail_available": bool(indicator_detail_available),
        "indicator_detail_missing_reason": None if indicator_detail_available else "live_indicator_readiness_runtime_evidence_missing",
        "indicator_missing_count": int(effective_indicators_missing_count),
        "missing_indicator_counts": dict(missing_indicator_counts),
        "missing_indicators_by_symbol": dict(missing_indicators_by_symbol or {}),
        "missing_indicators_by_strategy": dict(missing_indicators_by_strategy or {}),
        "warmup_candle_counts_by_symbol": warmup_candle_counts_by_symbol,
        "required_warmup_candle_counts_by_symbol": required_warmup_candle_counts_by_symbol,
        "indicator_ready_by_symbol": indicator_ready_by_symbol,
        "indicator_ready_by_strategy": indicator_ready_by_strategy,
        "indicator_ready_symbol_count": int(indicator_ready_symbol_count),
        "indicator_blocked_symbol_count": int(indicator_blocked_symbol_count),
        "indicator_age_sec_by_symbol": indicator_age_sec_by_symbol,
        "indicator_source_by_symbol": indicator_source_by_symbol,
        "indicator_blocker_reason_counts": dict(indicator_blocker_reason_counts),
        "regime_detail_available": bool(regime_detail_available),
        "regime_detail_missing_reason": None if regime_detail_available else "regime_truth_not_provided",
        "regime_unstable_count": int(regime_unstable_count),
        "regime_gate_reasons": dict(regime.get("gate_reasons") or {}) if isinstance(regime.get("gate_reasons"), Mapping) else {},
        "regime_by_symbol": dict(regime.get("by_symbol") or {}) if isinstance(regime.get("by_symbol"), Mapping) else {},
        "latency_guard_detail_available": bool(latency_detail_available),
        "latency_guard_detail_missing_reason": None if latency_detail_available else "latency_guard_not_provided",
        "latency_guard_triggered": latency.get("latency_guard_triggered") if latency else None,
        "latency_guard_mode": latency.get("latency_guard_mode") if latency else None,
        "latency_guard_action": latency.get("latency_guard_action") if latency else None,
        "latency_guard_source": latency.get("latency_guard_source") if latency else None,
        "latency_guard_reason": latency.get("latency_guard_reason") if latency else None,
        "latency_guard_metric": latency.get("latency_guard_metric") if latency else None,
        "latency_guard_value": latency.get("latency_guard_value") if latency else None,
        "latency_guard_threshold": latency.get("latency_guard_threshold") if latency else None,
        "latency_guard_age_sec": latency.get("latency_guard_age_sec") if latency else None,
        "latency_guard_last_ok_at": latency.get("latency_guard_last_ok_at") if latency else None,
        "latency_guard_last_bad_at": latency.get("latency_guard_last_bad_at") if latency else None,
        "latency_guard_recovery_required": latency.get("latency_guard_recovery_required") if latency else None,
        "generated_epoch": float(time.time()),
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
    }
    return json.loads(json.dumps(payload, ensure_ascii=True, default=str))


def write_notrade_reason_truth_latest(
    *,
    payload: Mapping[str, Any],
    logs_path: Path | None = None,
    runtime_path: Path | None = None,
) -> tuple[Path, Path]:
    # Contract: write both repo-local `logs/` and runtime `.runtime/` latest artifacts.
    # For backward compatibility, also mirror into runtime `logs_dir()` (usually `.runtime/logs`).
    logs_target = Path(logs_path) if logs_path is not None else (repo_logs_dir() / RUNTIME_NOTRADE_REASON_TRUTH_FILENAME)
    runtime_target = Path(runtime_path) if runtime_path is not None else (runtime_dir() / RUNTIME_NOTRADE_REASON_TRUTH_FILENAME)
    runtime_logs_target = logs_dir() / RUNTIME_NOTRADE_REASON_TRUTH_FILENAME
    logs_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_logs_target.parent.mkdir(parents=True, exist_ok=True)
    out = dict(payload) if isinstance(payload, Mapping) else {}
    write_json_atomic(logs_target, out)
    write_json_atomic(runtime_target, out)
    write_json_atomic(runtime_logs_target, out)
    return logs_target, runtime_target


__all__ = [
    "RUNTIME_NOTRADE_REASON_TRUTH_FILENAME",
    "build_notrade_reason_truth_payload",
    "write_notrade_reason_truth_latest",
]
