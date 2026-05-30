from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from core.events import write_json_atomic
from core.paths import logs_dir, runtime_dir


RUNTIME_NOTRADE_REASON_TRUTH_SCHEMA_VERSION = 1
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


def build_notrade_reason_truth_payload(
    *,
    candidate_handoff: Mapping[str, Any] | None,
    phase2_rejection: Mapping[str, Any] | None,
    feed_truth: Mapping[str, Any] | None,
    top_opportunities: Mapping[str, Any] | None,
) -> dict[str, Any]:
    handoff = _as_mapping(candidate_handoff)
    phase2 = _as_mapping(phase2_rejection)
    feed = _as_mapping(feed_truth)
    top = _as_mapping(top_opportunities)

    precedence = [
        "market_closed",
        "feed_stale",
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
    logs_target = Path(logs_path) if logs_path is not None else (logs_dir() / RUNTIME_NOTRADE_REASON_TRUTH_FILENAME)
    runtime_target = Path(runtime_path) if runtime_path is not None else (runtime_dir() / RUNTIME_NOTRADE_REASON_TRUTH_FILENAME)
    logs_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    out = dict(payload) if isinstance(payload, Mapping) else {}
    write_json_atomic(logs_target, out)
    write_json_atomic(runtime_target, out)
    return logs_target, runtime_target


__all__ = [
    "RUNTIME_NOTRADE_REASON_TRUTH_FILENAME",
    "build_notrade_reason_truth_payload",
    "write_notrade_reason_truth_latest",
]

