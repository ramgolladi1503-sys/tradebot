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


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


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


def _row_count_score(row: Mapping[str, Any] | None) -> int:
    if not isinstance(row, Mapping):
        return 0
    return sum(
        max(0, _safe_int(row.get(field)))
        for field in (
            "raw_candidate_count",
            "post_scan_survivor_count",
            "post_soft_reject_count",
            "post_real_filter_count",
            "post_executable_filter_count",
        )
    )


def _merge_reason_lists(*values: Any) -> list[str]:
    merged: list[str] = []
    for value in values:
        for item in _as_list(value):
            text = str(item or "").strip()
            if text and text not in merged:
                merged.append(text)
    return merged


def _merge_counts(*sources: Mapping[str, Any] | None) -> dict[str, int]:
    merged: dict[str, int] = {}
    for source in sources:
        for key, value in dict(source or {}).items():
            code = str(key or "").strip()
            if not code:
                continue
            merged[code] = max(merged.get(code, 0), _safe_int(value))
    return merged


def _merge_regime_rows(*rows: Mapping[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    regime_fields = (
        "primary_regime",
        "regime_entropy",
        "regime_entropy_max",
        "regime_prob_max",
        "regime_prob_min",
        "regime_unstable_streak",
        "regime_unstable_block_after",
        "regime_unstable_debounced",
        "unstable_reasons",
        "regime_unstable",
        "feed_runtime_state",
        "ws_connected",
        "option_feed_block_reason",
        "quote_health_state",
        "quote_health_stale_reasons",
        "ltp_age_sec",
    )
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        for field in regime_fields:
            value = row.get(field)
            if field in {"regime_entropy", "regime_entropy_max", "regime_prob_max", "regime_prob_min", "ltp_age_sec"}:
                if merged.get(field) is None and value is not None:
                    merged[field] = value
                elif value is not None:
                    try:
                        merged[field] = max(_safe_float(merged.get(field)) or float("-inf"), _safe_float(value) or float("-inf"))
                    except Exception:
                        merged[field] = value
                continue
            if field in {"regime_unstable_streak", "regime_unstable_block_after"}:
                merged[field] = max(_safe_int(merged.get(field)), _safe_int(value))
                continue
            if field in {"regime_unstable_debounced", "regime_unstable"}:
                merged[field] = bool(merged.get(field)) or bool(value)
                continue
            if field in {"unstable_reasons", "quote_health_stale_reasons"}:
                merged[field] = _merge_reason_lists(merged.get(field), value)
                continue
            if field in {"primary_regime", "feed_runtime_state", "option_feed_block_reason", "quote_health_state"}:
                if value not in (None, "", [], (), {}):
                    merged[field] = value
                continue
            if field == "ws_connected":
                if merged.get(field) is None and value is not None:
                    merged[field] = value
                elif value is not None:
                    merged[field] = bool(merged.get(field)) or bool(value)
                continue
        if row.get("feed_health") and not merged.get("feed_health"):
            merged["feed_health"] = dict(row.get("feed_health") or {})
        if row.get("quote_health") and not merged.get("quote_health"):
            merged["quote_health"] = dict(row.get("quote_health") or {})
    if "unstable_reasons" not in merged:
        merged["unstable_reasons"] = []
    if "quote_health_stale_reasons" not in merged:
        merged["quote_health_stale_reasons"] = []
    return merged


def _merge_symbol_trace_rows(*rows: Mapping[str, Any] | None) -> dict[str, Any]:
    chosen_rows = [dict(row) for row in rows if isinstance(row, Mapping) and row]
    if not chosen_rows:
        return {}
    chosen_rows.sort(key=_row_count_score)
    merged: dict[str, Any] = {}
    for row in chosen_rows:
        for key, value in row.items():
            if key == "regime":
                merged["regime"] = _merge_regime_rows(merged.get("regime"), value)
                continue
            if key in {"raw_candidate_count", "post_scan_survivor_count", "post_soft_reject_count", "post_real_filter_count", "post_executable_filter_count", "ltp_age_sec"}:
                current = merged.get(key)
                if key == "ltp_age_sec":
                    if current is None and value is not None:
                        merged[key] = value
                    elif value is not None:
                        try:
                            merged[key] = max(_safe_float(current) or float("-inf"), _safe_float(value) or float("-inf"))
                        except Exception:
                            merged[key] = value
                else:
                    merged[key] = max(_safe_int(current), _safe_int(value))
                continue
            if key in {"reject_gate_reasons", "quote_health_stale_reasons"}:
                merged[key] = _merge_reason_lists(merged.get(key), value)
                continue
            if key in {"scan_reject_counts", "blocker_counts"}:
                merged[key] = _merge_counts(merged.get(key), value)
                continue
            if key in {"ws_connected"}:
                if merged.get(key) is None and value is not None:
                    merged[key] = value
                elif value is not None:
                    merged[key] = bool(merged.get(key)) or bool(value)
                continue
            if key in {"reject_reason", "final_emit_block_reason", "candidate_reason", "candidate_funnel_stage", "feed_runtime_state", "option_feed_block_reason", "quote_health_state"}:
                if value not in (None, "", [], (), {}):
                    merged[key] = value
                continue
            if key not in merged and value not in (None, "", [], (), {}):
                merged[key] = value
    if "candidate_funnel_stage" not in merged:
        merged["candidate_funnel_stage"] = _first_zero_stage(
            raw_candidate_count=_safe_int(merged.get("raw_candidate_count")),
            post_scan_survivor_count=_safe_int(merged.get("post_scan_survivor_count")),
            post_soft_reject_count=_safe_int(merged.get("post_soft_reject_count")),
            post_real_filter_count=_safe_int(merged.get("post_real_filter_count")),
            post_executable_filter_count=_safe_int(merged.get("post_executable_filter_count")),
        )
    regime = _as_mapping(merged.get("regime"))
    if regime:
        merged["regime"] = regime
    if "reject_gate_reasons" not in merged:
        merged["reject_gate_reasons"] = []
    if "scan_reject_counts" not in merged:
        merged["scan_reject_counts"] = {}
    if "quote_health_stale_reasons" not in merged:
        merged["quote_health_stale_reasons"] = []
    return merged


def _normalize_latest_global_blocker(value: Any) -> tuple[str | None, int | None]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        reason = str(value[0] or "").strip()
        count = _safe_int(value[1])
        return (reason or None, count)
    if isinstance(value, str):
        reason = value.strip()
        return (reason or None, None)
    if isinstance(value, Mapping):
        reason = next(iter(value.keys()), None)
        if reason is None:
            return (None, None)
        return (str(reason).strip() or None, _safe_int(value.get(reason)))
    return (None, None)


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
    previous_payload: Mapping[str, Any] | None = None,
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
            "candidate_reason": str(_first_non_empty(snap.get("candidate_reason"), snap.get("reject_reason"))) if _first_non_empty(snap.get("candidate_reason"), snap.get("reject_reason")) not in (None, "", [], (), {}) else None,
            "final_emit_block_reason": str(_first_non_empty(snap.get("final_emit_block_reason"), snap.get("candidate_reason"), snap.get("reject_reason"))) if _first_non_empty(snap.get("final_emit_block_reason"), snap.get("candidate_reason"), snap.get("reject_reason")) not in (None, "", [], (), {}) else None,
            "reason_category": str(snap.get("reason_category") or "").strip() or None,
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
    previous = _as_mapping(previous_payload)
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

    previous_symbol_traces = _as_mapping(previous.get("symbol_traces"))
    previous_last_symbol_snapshot = _as_mapping(previous.get("last_symbol_snapshot"))
    previous_had_symbol_candidates = bool(previous.get("had_symbol_candidates_this_session_or_cycle"))
    current_symbol_traces = dict(sorted(by_symbol.items(), key=lambda item: item[0]))
    current_has_symbols = bool(current_symbol_traces)
    existing_latest_payload = _read_json_file(repo_logs_dir() / RUNTIME_CANDIDATE_STARVATION_TRACE_FILENAME)
    existing_symbol_traces = _as_mapping(existing_latest_payload.get("symbol_traces"))
    existing_last_symbol_snapshot = _as_mapping(existing_latest_payload.get("last_symbol_snapshot"))
    existing_had_symbol_candidates = bool(existing_latest_payload.get("had_symbol_candidates_this_session_or_cycle"))
    merged_symbol_keys = sorted(
        {str(key).strip() for source in (existing_symbol_traces, previous_symbol_traces, current_symbol_traces) for key in dict(source or {}).keys() if str(key).strip()}
    )
    symbol_traces: dict[str, Any] = {}
    for symbol in merged_symbol_keys:
        symbol_traces[symbol] = _merge_symbol_trace_rows(
            existing_symbol_traces.get(symbol),
            previous_symbol_traces.get(symbol),
            current_symbol_traces.get(symbol),
        )
    if symbol_traces:
        last_symbol_snapshot = dict(list(symbol_traces.values())[-1])
    elif previous_symbol_traces:
        symbol_traces = dict(previous_symbol_traces)
        last_symbol_snapshot = dict(previous_last_symbol_snapshot)
    elif existing_symbol_traces:
        symbol_traces = dict(existing_symbol_traces)
        last_symbol_snapshot = dict(existing_last_symbol_snapshot)
    else:
        last_symbol_snapshot = {}

    latest_global_blocker_reason: str | None = None
    latest_global_blocker_count: int | None = None
    if cycle_blockers:
        latest_global_blocker_reason, latest_global_blocker_count = max(
            ((str(reason).strip(), _safe_int(count)) for reason, count in dict(cycle_blockers).items() if str(reason).strip()),
            key=lambda item: (item[1], item[0]),
            default=None,
        )
    if latest_global_blocker_reason is None:
        previous_global_reason, previous_global_count = _normalize_latest_global_blocker(previous.get("latest_global_blocker"))
        if previous_global_reason:
            latest_global_blocker_reason = previous_global_reason
            latest_global_blocker_count = previous_global_count
    if latest_global_blocker_reason is None:
        existing_global_reason, existing_global_count = _normalize_latest_global_blocker(existing_latest_payload.get("latest_global_blocker"))
        if existing_global_reason:
            latest_global_blocker_reason = existing_global_reason
            latest_global_blocker_count = existing_global_count or _safe_int(existing_latest_payload.get("latest_global_blocker_count"))

    latest_global_blocker_counts = dict(sorted({str(k): _safe_int(v) for k, v in dict(cycle_blockers or {}).items() if str(k).strip()}.items(), key=lambda item: (-item[1], item[0])))
    if not latest_global_blocker_counts and isinstance(previous.get("latest_global_blocker_counts"), Mapping):
        latest_global_blocker_counts = dict(previous.get("latest_global_blocker_counts") or {})
    if not latest_global_blocker_counts and isinstance(existing_latest_payload.get("latest_global_blocker_counts"), Mapping):
        latest_global_blocker_counts = dict(existing_latest_payload.get("latest_global_blocker_counts") or {})

    had_symbol_candidates_this_session_or_cycle = bool(
        raw_candidate_count > 0
        or post_scan_survivor_count > 0
        or post_soft_reject_count > 0
        or post_real_filter_count > 0
        or post_executable_filter_count > 0
        or any(_row_count_score(row) > 0 for row in symbol_traces.values())
        or previous_had_symbol_candidates
        or existing_had_symbol_candidates
    )

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
        "market_data_symbol_count": int(len(symbol_traces) if symbol_traces else len(symbols)),
        "market_data_symbols": list(symbol_traces.keys()) if symbol_traces else list(symbols),
        "symbol_count": int(len(symbol_traces) if symbol_traces else len(symbols)),
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
        "latest_global_blocker": latest_global_blocker_reason,
        "latest_global_blocker_count": latest_global_blocker_count,
        "latest_global_blocker_counts": latest_global_blocker_counts,
        "last_symbol_snapshot": last_symbol_snapshot,
        "symbol_traces": symbol_traces,
        "had_symbol_candidates_this_session_or_cycle": had_symbol_candidates_this_session_or_cycle,
        "last_candidate_funnel_by_symbol": {
            symbol: {
                "raw_candidate_count": row.get("raw_candidate_count"),
                "post_scan_survivor_count": row.get("post_scan_survivor_count"),
                "post_soft_reject_count": row.get("post_soft_reject_count"),
                "post_real_filter_count": row.get("post_real_filter_count"),
                "post_executable_filter_count": row.get("post_executable_filter_count"),
            }
            for symbol, row in symbol_traces.items()
            if isinstance(row, Mapping)
        },
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
