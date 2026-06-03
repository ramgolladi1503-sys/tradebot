from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from core.events import write_json_atomic
from core.paths import logs_dir, repo_logs_dir, runtime_dir


RUNTIME_CANDIDATE_STARVATION_TRACE_SCHEMA_VERSION = 1
RUNTIME_CANDIDATE_STARVATION_TRACE_SOURCE = "runtime_candidate_starvation_trace_v1"
RUNTIME_CANDIDATE_STARVATION_TRACE_FILENAME = "candidate_starvation_trace_latest.json"


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if value in (None, "", "None"):
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return [value]


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], (), {}):
            return value
    return None


def _regime_metrics_from_snapshot(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    row = _as_mapping(snapshot)
    regime = _as_mapping(row.get("regime"))
    feed_health = _as_mapping(_first_non_empty(row.get("feed_health"), row.get("feed_truth"), row.get("feed")))
    quote_health = _as_mapping(_first_non_empty(row.get("quote_health"), row.get("quote"), feed_health.get("quote_health")))
    probs = _as_mapping(_first_non_empty(row.get("regime_probs"), regime.get("regime_probs")))
    numeric_probs = [_safe_float(value) for value in probs.values()]
    numeric_probs = [value for value in numeric_probs if value is not None]
    unstable_reasons = [str(item).strip() for item in _as_list(_first_non_empty(row.get("unstable_reasons"), regime.get("unstable_reasons"))) if str(item or "").strip()]
    regime_ok_value = _first_non_empty(row.get("regime_ok"), regime.get("regime_ok"))
    regime_ok_false = False
    if regime_ok_value is False:
        regime_ok_false = True
    elif isinstance(regime_ok_value, str) and regime_ok_value.strip().lower() in {"0", "false", "no", "off"}:
        regime_ok_false = True
    return {
        "primary_regime": _upper(
            _first_non_empty(
                row.get("primary_regime"),
                row.get("regime"),
                regime.get("primary_regime"),
                regime.get("regime"),
            )
        )
        or None,
        "regime_entropy": _safe_float(_first_non_empty(row.get("regime_entropy"), regime.get("regime_entropy"))),
        "regime_entropy_max": _safe_float(
            _first_non_empty(
                row.get("regime_entropy_max"),
                regime.get("regime_entropy_max"),
                row.get("regime_entropy_threshold"),
            )
        ),
        "regime_prob_max": _safe_float(
            _first_non_empty(row.get("regime_prob_max"), regime.get("regime_prob_max"), max(numeric_probs) if numeric_probs else None)
        ),
        "regime_prob_min": _safe_float(
            _first_non_empty(
                row.get("regime_prob_min"),
                regime.get("regime_prob_min"),
                min(numeric_probs) if numeric_probs else None,
            )
        ),
        "regime_unstable_streak": _safe_int(
            _first_non_empty(row.get("regime_unstable_streak"), regime.get("regime_unstable_streak"))
        ),
        "regime_unstable_block_after": _safe_int(
            _first_non_empty(row.get("regime_unstable_block_after"), regime.get("regime_unstable_block_after"))
        ),
        "regime_unstable_debounced": bool(
            _first_non_empty(row.get("regime_unstable_debounced"), regime.get("regime_unstable_debounced"), False)
        ),
        "unstable_reasons": unstable_reasons,
        "regime_unstable": bool(
            unstable_reasons
            or _upper(_first_non_empty(row.get("decision_gate_reason"), regime.get("decision_gate_reason"))) == "REGIME_UNSTABLE"
            or regime_ok_false
        ),
        "feed_runtime_state": _upper(_first_non_empty(feed_health.get("runtime_state"), row.get("runtime_state"))) or None,
        "ws_connected": _first_non_empty(feed_health.get("ws_connected"), row.get("ws_connected")),
        "option_feed_block_reason": _upper(
            _first_non_empty(
                feed_health.get("option_feed_block_reason"),
                row.get("option_feed_block_reason"),
            )
        )
        or None,
        "quote_health_state": _upper(_first_non_empty(quote_health.get("state"), row.get("quote_health_state"))) or None,
        "quote_health_stale_reasons": [str(item).strip() for item in _as_list(_first_non_empty(quote_health.get("stale_reasons"), row.get("stale_reasons"))) if str(item or "").strip()],
        "ltp_age_sec": _safe_float(_first_non_empty(quote_health.get("ltp_age_sec"), row.get("ltp_age_sec"))),
    }


def _choose_reject_reason(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, Mapping):
            for item in value.keys():
                text = str(item or "").strip()
                if text:
                    return text
            continue
        for item in _as_list(value):
            text = str(item or "").strip()
            if text:
                return text
    return None


def _normalize_top_reject_reasons(*sources: Mapping[str, Any] | None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for source in sources:
        for reason, count in dict(source or {}).items():
            code = str(reason or "").strip()
            if not code:
                continue
            try:
                counts[code] += int(count or 0)
            except Exception:
                counts[code] += 1
    return dict(counts)


def _merge_top_reject_reasons(
    *,
    base: Mapping[str, Any] | None,
    overlay: Mapping[str, Any] | None,
    fallback: Mapping[str, Any] | None,
) -> dict[str, int]:
    merged: dict[str, int] = {}
    for source in (base, overlay):
        for reason, count in dict(source or {}).items():
            code = str(reason or "").strip()
            if not code:
                continue
            try:
                merged[code] = max(int(count or 0), merged.get(code, 0))
            except Exception:
                merged[code] = max(1, merged.get(code, 0))
    for reason, count in dict(fallback or {}).items():
        code = str(reason or "").strip()
        if not code or code in merged:
            continue
        try:
            merged[code] = int(count or 0)
        except Exception:
            merged[code] = 1
    return merged


def _top_blockers(blockers: Mapping[str, Any] | None, limit: int = 10) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for reason, count in dict(blockers or {}).items():
        code = str(reason or "").strip()
        if not code:
            continue
        rows.append({"reason": code, "count": _safe_int(count)})
    rows.sort(key=lambda item: (-int(item["count"]), str(item["reason"])))
    return rows[: max(0, int(limit))]


def _first_zero_stage(
    *,
    raw_candidate_count: int,
    post_scan_survivor_count: int,
    post_soft_reject_count: int,
    post_real_filter_count: int,
    post_executable_filter_count: int,
) -> str:
    if raw_candidate_count <= 0:
        return "no_raw_candidates"
    if post_scan_survivor_count <= 0:
        return "post_scan_survivor_zero"
    if post_soft_reject_count <= 0:
        return "post_soft_reject_zero"
    if post_real_filter_count <= 0:
        return "post_real_filter_zero"
    if post_executable_filter_count <= 0:
        return "post_executable_filter_zero"
    return "not_starved"


def build_candidate_starvation_trace_payload(
    *,
    execution_mode: str | None,
    market_open: bool | None,
    market_data_list: list[Mapping[str, Any]] | None,
    cycle_blockers: Mapping[str, Any] | None,
    feed_runtime: Mapping[str, Any] | None,
    candidate_starvation_snapshots: list[Mapping[str, Any]] | None,
    candidate_handoff_root_cause: Mapping[str, Any] | None = None,
    phase2_rejection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    symbols: list[str] = []
    for row in list(market_data_list or []):
        md = _as_mapping(row)
        symbol = _upper(md.get("symbol"))
        if symbol and symbol not in symbols:
            symbols.append(symbol)

    by_symbol: dict[str, dict[str, Any]] = {}
    unstable_reason_counts: Counter[str] = Counter()
    regime_unstable_symbol_count = 0
    raw_candidate_count = 0
    post_scan_survivor_count = 0
    post_soft_reject_count = 0
    post_real_filter_count = 0
    post_executable_filter_count = 0
    reject_reason_counts: Counter[str] = Counter()
    reject_reason_sources: dict[str, set[str]] = {}

    for row in list(candidate_starvation_snapshots or []):
        snap = _as_mapping(row)
        symbol = _upper(snap.get("symbol"))
        if not symbol:
            continue
        regime = _as_mapping(snap.get("regime"))
        if not regime:
            regime = _regime_metrics_from_snapshot(snap)
        by_symbol[symbol] = {
            "symbol": symbol,
            "regime": regime,
            "raw_candidate_count": _safe_int(snap.get("raw_candidate_count")),
            "post_scan_survivor_count": _safe_int(snap.get("post_scan_survivor_count")),
            "post_soft_reject_count": _safe_int(snap.get("post_soft_reject_count")),
            "post_real_filter_count": _safe_int(snap.get("post_real_filter_count")),
            "post_executable_filter_count": _safe_int(snap.get("post_executable_filter_count")),
            "reject_reason": str(snap.get("reject_reason") or "").strip() or None,
            "reject_gate_reasons": [str(item).strip() for item in _as_list(snap.get("reject_gate_reasons")) if str(item or "").strip()],
            "scan_reject_counts": _normalize_top_reject_reasons(_as_mapping(snap.get("scan_reject_counts"))),
            "feed_runtime_state": _upper(snap.get("feed_runtime_state")) or None,
            "ws_connected": snap.get("ws_connected"),
            "option_feed_block_reason": _upper(snap.get("option_feed_block_reason")) or None,
            "quote_health_state": _upper(snap.get("quote_health_state")) or None,
            "quote_health_stale_reasons": [str(item).strip() for item in _as_list(snap.get("quote_health_stale_reasons")) if str(item or "").strip()],
            "ltp_age_sec": _safe_float(snap.get("ltp_age_sec")),
            "candidate_funnel_stage": _first_zero_stage(
                raw_candidate_count=_safe_int(snap.get("raw_candidate_count")),
                post_scan_survivor_count=_safe_int(snap.get("post_scan_survivor_count")),
                post_soft_reject_count=_safe_int(snap.get("post_soft_reject_count")),
                post_real_filter_count=_safe_int(snap.get("post_real_filter_count")),
                post_executable_filter_count=_safe_int(snap.get("post_executable_filter_count")),
            ),
        }

        regime_row = by_symbol[symbol]["regime"]
        if bool(regime_row.get("regime_unstable")):
            regime_unstable_symbol_count += 1
            for reason in regime_row.get("unstable_reasons") or []:
                unstable_reason_counts[str(reason)] += 1

        if by_symbol[symbol]["reject_reason"] is None and by_symbol[symbol]["scan_reject_counts"]:
            by_symbol[symbol]["reject_reason"] = max(
                by_symbol[symbol]["scan_reject_counts"].items(),
                key=lambda item: (int(item[1] or 0), str(item[0])),
            )[0]

        raw_candidate_count += by_symbol[symbol]["raw_candidate_count"]
        post_scan_survivor_count += by_symbol[symbol]["post_scan_survivor_count"]
        post_soft_reject_count += by_symbol[symbol]["post_soft_reject_count"]
        post_real_filter_count += by_symbol[symbol]["post_real_filter_count"]
        post_executable_filter_count += by_symbol[symbol]["post_executable_filter_count"]

        for reason, count in by_symbol[symbol]["scan_reject_counts"].items():
            reject_reason_counts[str(reason)] += int(count or 0)
            reject_reason_sources.setdefault(str(reason), set()).add("scan_reject_counts")
        reject_reason = by_symbol[symbol]["reject_reason"]
        if reject_reason:
            reject_reason_counts[reject_reason] += 1
            reject_reason_sources.setdefault(reject_reason, set()).add("reject_reason")
        for reason in by_symbol[symbol]["reject_gate_reasons"]:
            reject_reason_counts[reason] += 1
            reject_reason_sources.setdefault(reason, set()).add("reject_gate_reasons")

    # Backfill all known symbols with empty rows so the latest artifact remains explanatory.
    for symbol in symbols:
        by_symbol.setdefault(
            symbol,
            {
                "symbol": symbol,
                "regime": _regime_metrics_from_snapshot({"symbol": symbol}),
                "raw_candidate_count": 0,
                "post_scan_survivor_count": 0,
                "post_soft_reject_count": 0,
                "post_real_filter_count": 0,
                "post_executable_filter_count": 0,
                "reject_reason": None,
                "reject_gate_reasons": [],
                "scan_reject_counts": {},
                "feed_runtime_state": None,
                "ws_connected": None,
                "option_feed_block_reason": None,
                "quote_health_state": None,
                "quote_health_stale_reasons": [],
                "ltp_age_sec": None,
                "candidate_funnel_stage": "no_data",
            },
        )

    root_cause = _as_mapping(candidate_handoff_root_cause)
    phase2 = _as_mapping(phase2_rejection)
    feed = _as_mapping(feed_runtime)
    top_reject_reasons = _merge_top_reject_reasons(
        base=_as_mapping(root_cause.get("top_drop_reasons")),
        overlay=_as_mapping(phase2.get("top_non_executable_reasons")),
        fallback=reject_reason_counts,
    )

    reject_reason_details = {
        "confidence_raw_gate": {
            "count": int(top_reject_reasons.get("confidence_raw_gate", 0) or 0),
            "sources": sorted(reject_reason_sources.get("confidence_raw_gate", set())),
        },
        "iv_z_bounds": {
            "count": int(top_reject_reasons.get("iv_z_bounds", 0) or 0),
            "sources": sorted(reject_reason_sources.get("iv_z_bounds", set())),
        },
        "no_viable_candidates": {
            "count": int(top_reject_reasons.get("no_viable_candidates", 0) or 0),
            "sources": sorted(reject_reason_sources.get("no_viable_candidates", set())),
        },
    }

    feed_truth = {
        "ws_connected": feed.get("ws_connected"),
        "runtime_state": _upper(feed.get("runtime_state")) or None,
        "option_feed_block_reason": (
            _upper(_first_non_empty(
                feed.get("option_feed_block_reason"),
                next(iter(dict(feed.get("option_feed_block_reason_by_symbol") or {}).values()), None)
                if isinstance(feed.get("option_feed_block_reason_by_symbol"), Mapping)
                else None,
            ))
            or None
        ),
        "subscribed_tokens_count": _safe_int(feed.get("subscribed_tokens_count")),
        "subscribed_option_tokens_count": _safe_int(feed.get("subscribed_option_tokens_count")),
        "feed_fresh": feed.get("feed_fresh"),
        "underlying_tick_fresh": feed.get("underlying_tick_fresh"),
        "option_tick_fresh": feed.get("option_tick_fresh"),
        "depth_fresh": feed.get("depth_fresh"),
        "stale_reasons": [str(item).strip() for item in _as_list(feed.get("stale_reason")) if str(item or "").strip()],
    }

    quote_health_state = None
    quote_stale_reasons: list[str] = []
    ltp_age_sec = None
    for symbol in symbols:
        row = by_symbol.get(symbol, {})
        if row.get("quote_health_state"):
            quote_health_state = row.get("quote_health_state")
        quote_stale_reasons.extend([reason for reason in row.get("quote_health_stale_reasons") or [] if reason not in quote_stale_reasons])
        if ltp_age_sec is None and row.get("ltp_age_sec") is not None:
            ltp_age_sec = row.get("ltp_age_sec")

    payload = {
        "schema_version": RUNTIME_CANDIDATE_STARVATION_TRACE_SCHEMA_VERSION,
        "source": RUNTIME_CANDIDATE_STARVATION_TRACE_SOURCE,
        "writer_name": "runtime_candidate_starvation_trace",
        "writer_module": __name__,
        "writer_schema_version": RUNTIME_CANDIDATE_STARVATION_TRACE_SCHEMA_VERSION,
        "generated_epoch": float(time.time()),
        "execution_mode": _upper(execution_mode) or "SIM",
        "market_open": bool(market_open) if market_open is not None else None,
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "market_data_symbol_count": int(len(symbols)),
        "market_data_symbols": list(symbols),
        "regime_unstable_symbol_count": int(regime_unstable_symbol_count),
        "regime_unstable_reason_counts": dict(unstable_reason_counts),
        "raw_candidate_count": int(raw_candidate_count),
        "post_scan_survivor_count": int(post_scan_survivor_count),
        "post_soft_reject_count": int(post_soft_reject_count),
        "post_real_filter_count": int(post_real_filter_count),
        "post_executable_filter_count": int(post_executable_filter_count),
        "survivor_count": int(post_executable_filter_count),
        "first_zero_stage": _first_zero_stage(
            raw_candidate_count=int(raw_candidate_count),
            post_scan_survivor_count=int(post_scan_survivor_count),
            post_soft_reject_count=int(post_soft_reject_count),
            post_real_filter_count=int(post_real_filter_count),
            post_executable_filter_count=int(post_executable_filter_count),
        ),
        "top_reject_reasons": dict(sorted(top_reject_reasons.items(), key=lambda item: (-int(item[1]), str(item[0])))),
        "reject_reason_details": reject_reason_details,
        "feed_truth": feed_truth,
        "quote_health_state": quote_health_state,
        "quote_health_stale_reasons": quote_stale_reasons,
        "ltp_age_sec": ltp_age_sec,
        "blocker_counts": {str(key): _safe_int(value) for key, value in dict(cycle_blockers or {}).items() if str(key).strip()},
        "top_blockers": _top_blockers(cycle_blockers),
        "cycle_blockers": {str(key): _safe_int(value) for key, value in dict(cycle_blockers or {}).items() if str(key).strip()},
        "by_symbol": dict(sorted(by_symbol.items(), key=lambda item: item[0])),
        "notes": [
            "Evidence-only trace. Does not change regime thresholds, strategy logic, ranking, Phase2, broker, or order behavior.",
            "Counts are derived from the current cycle snapshots and scan reject counts already produced by the orchestrator.",
            "Missing evidence is left as null/empty rather than inferred.",
        ],
    }
    return json.loads(json.dumps(payload, ensure_ascii=True, default=str))


def write_candidate_starvation_trace_latest(
    *,
    payload: Mapping[str, Any],
    logs_path: Path | None = None,
    runtime_path: Path | None = None,
    runtime_logs_path: Path | None = None,
) -> tuple[Path, Path, Path]:
    logs_target = (
        Path(logs_path)
        if logs_path is not None
        else (repo_logs_dir() / RUNTIME_CANDIDATE_STARVATION_TRACE_FILENAME)
    )
    runtime_target = (
        Path(runtime_path)
        if runtime_path is not None
        else (runtime_dir() / RUNTIME_CANDIDATE_STARVATION_TRACE_FILENAME)
    )
    runtime_logs_target = (
        Path(runtime_logs_path)
        if runtime_logs_path is not None
        else (logs_dir() / RUNTIME_CANDIDATE_STARVATION_TRACE_FILENAME)
    )
    logs_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    runtime_logs_target.parent.mkdir(parents=True, exist_ok=True)
    out = dict(payload) if isinstance(payload, Mapping) else {}
    write_json_atomic(logs_target, out)
    write_json_atomic(runtime_target, out)
    write_json_atomic(runtime_logs_target, out)
    return logs_target, runtime_target, runtime_logs_target


__all__ = [
    "RUNTIME_CANDIDATE_STARVATION_TRACE_FILENAME",
    "build_candidate_starvation_trace_payload",
    "write_candidate_starvation_trace_latest",
]
