from __future__ import annotations

import copy
import json
import logging
import math
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from types import MappingProxyType

import pandas as pd

from config import config as cfg
from core.feed_runtime import build_canonical_feed_truth_state
from core.paths import logs_dir
from core.feed.artifact_loader import load_current_feed_runtime
from core.risk_utils import to_pct
from core.time_utils import now_ist, now_utc_epoch


logger = logging.getLogger(__name__)


def _perf_ms(start_perf: float) -> float:
    try:
        import time

        return (time.perf_counter() - float(start_perf)) * 1000.0
    except Exception:
        return 0.0


def _env_debug_enabled(name: str) -> bool:
    import os

    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _log_option_chain_debug(message: str, *args) -> None:
    if _env_debug_enabled("TRADEBOT_DEBUG_OPTION_CHAIN"):
        logger.debug(message, *args)


def _log_freshness_debug(message: str, *args) -> None:
    if _env_debug_enabled("TRADEBOT_DEBUG_FRESHNESS"):
        logger.debug(message, *args)


def _log_advisory_debug(message: str, *args) -> None:
    if _env_debug_enabled("TRADEBOT_DEBUG_ADVISORY"):
        logger.debug(message, *args)


def _trade_attr(trade, name: str, default=None):
    if isinstance(trade, dict):
        return trade.get(name, default)
    return getattr(trade, name, default)


def _candidate_origin(candidate) -> str:
    if candidate is None:
        return ""
    if isinstance(candidate, dict):
        for key in ("candidate_origin", "origin", "source"):
            value = candidate.get(key)
            if value:
                return str(value)
        source_flags = candidate.get("source_flags")
        if isinstance(source_flags, dict):
            for key in ("candidate_origin", "origin", "source"):
                value = source_flags.get(key)
                if value:
                    return str(value)
    return str(getattr(candidate, "candidate_origin", "") or getattr(candidate, "origin", "") or "")


def _is_synthetic_candidate(candidate) -> bool:
    origin = _candidate_origin(candidate).strip().lower()
    trade_id = str(_trade_attr(candidate, "trade_id", "") or "")
    strategy_family = str(_trade_attr(candidate, "strategy_family", "") or "").strip().lower()
    return bool(
        strategy_family == "synthetic_advisory"
        or origin in {"pre_builder_gate", "invalid_snapshot", "fallback", "fallback_min_breadth"}
        or trade_id.startswith("PRE_BUILDER_GATE-")
    )


def _is_reportable_executable_candidate(candidate) -> bool:
    if candidate is None:
        return False
    if _is_synthetic_candidate(candidate):
        return False
    if bool(_trade_attr(candidate, "blocked", False)):
        return False
    return True


def _candidate_visibility_bucket(candidate) -> str:
    if candidate is None:
        return "unknown"
    if _is_synthetic_candidate(candidate):
        return "synthetic"
    if bool(_trade_attr(candidate, "blocked", False)):
        return "blocked"
    return "visible"


def _candidate_runtime_truth_summary(candidate) -> dict:
    return {
        "trade_id": _trade_attr(candidate, "trade_id"),
        "symbol": _trade_attr(candidate, "symbol"),
        "strategy": _trade_attr(candidate, "strategy"),
        "origin": _candidate_origin(candidate),
        "visibility_bucket": _candidate_visibility_bucket(candidate),
        "reportable": _is_reportable_executable_candidate(candidate),
    }


def _candidate_trace_payload(candidate, *, execution_truth_context: dict | None = None) -> dict:
    payload = dict(_candidate_runtime_truth_summary(candidate))
    if execution_truth_context:
        payload["execution_truth_context"] = dict(execution_truth_context)
    return payload


def _regime_unstable_diagnostic_payload(market_data: dict, gate_reasons: list[str] | None = None) -> dict:
    return {
        "symbol": market_data.get("symbol"),
        "regime": market_data.get("regime"),
        "gate_reasons": list(gate_reasons or []),
        "market_open": market_data.get("market_open"),
        "execution_mode": market_data.get("execution_mode") or getattr(cfg, "EXECUTION_MODE", "SIM"),
    }


def _is_structurally_valid_cycle_candidate(candidate) -> bool:
    if candidate is None:
        return False
    return bool(_trade_attr(candidate, "symbol") and _trade_attr(candidate, "strategy"))


def _filter_invalid_cycle_candidates(candidates, *, symbol: str | None = None) -> tuple[list, list[dict]]:
    valid: list = []
    rejected: list[dict] = []
    for candidate in list(candidates or []):
        if not _is_structurally_valid_cycle_candidate(candidate):
            rejected.append({"symbol": symbol, "reason": "structural_invalid", "candidate": _candidate_trace_payload(candidate)})
            continue
        valid.append(candidate)
    return valid, rejected


def _replace_trade_fields(trade, updates: dict):
    if trade is None:
        return None
    if isinstance(trade, dict):
        merged = dict(trade)
        merged.update(dict(updates or {}))
        return merged
    try:
        from dataclasses import replace

        return replace(trade, **dict(updates or {}))
    except Exception:
        return trade


def _coerce_trade_dict_to_schema(trade, market_data: dict | None = None):
    if trade is None:
        return None
    if isinstance(trade, dict):
        return dict(trade)
    return {
        "trade_id": _trade_attr(trade, "trade_id"),
        "symbol": _trade_attr(trade, "symbol"),
        "strategy": _trade_attr(trade, "strategy"),
        "side": _trade_attr(trade, "side"),
        "market_data": dict(market_data or {}),
    }


def _read_json_dict(path: Path) -> dict:
    try:
        if not path.exists():
            return {}
        return json.loads(path.read_text())
    except Exception:
        return {}


def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _normalize_feed_runtime_payload(raw: dict) -> dict:
    return dict(raw or {})


def _read_latest_feed_runtime_payload() -> tuple[dict, Path | None]:
    path = logs_dir() / "feed_runtime_latest.json"
    loaded = load_current_feed_runtime(path)
    if not loaded.get("valid"):
        return {}, None
    return dict(loaded.get("payload") or {}), path


def freeze_cycle_feed_truth_payload(feed_truth_payload: Mapping[str, Any] | None) -> MappingProxyType:
    """Return an immutable per-cycle feed truth view.

    The orchestrator can pass this through multiple downstream consumers
    without re-reading or mutating the source payload.
    """
    return MappingProxyType(dict(feed_truth_payload or {}))


def _canonical_feed_truth_state_payload(feed_runtime_payload: dict | None) -> dict:
    return build_canonical_feed_truth_state(feed_runtime_payload or {})


def _feed_truth_cycle_gate(feed_runtime_payload: dict | None) -> dict:
    payload = _canonical_feed_truth_state_payload(feed_runtime_payload)
    return {
        "feed_state": payload.get("state"),
        "feed_reason": payload.get("reason"),
        "allowed": bool(payload.get("execution_feed_ready")),
    }


def _count_jsonl_rows(path: Path) -> int:
    try:
        if not path.exists():
            return 0
        return sum(1 for _ in path.open("r", encoding="utf-8"))
    except Exception:
        return 0


def _build_cycle_latency_snapshot(
    *,
    cycle_started_at: float | None = None,
    cycle_completed_at: float | None = None,
    feed_epoch: float | None = None,
) -> dict:
    return {
        "cycle_started_at": cycle_started_at,
        "cycle_completed_at": cycle_completed_at,
        "cycle_elapsed_ms": None if cycle_started_at is None or cycle_completed_at is None else max(0.0, (cycle_completed_at - cycle_started_at) * 1000.0),
        "feed_epoch": feed_epoch,
    }


def _latency_budget_config(*, execution_mode: str | None) -> dict[str, float | int | bool | str]:
    mode = str(execution_mode or getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
    base = {
        "execution_mode": mode,
        "max_cycle_ms": 1000.0 if mode == "SIM" else 500.0,
        "skip_trade_builder": False,
        "skip_maintenance": False,
    }
    return base


def _should_skip_trade_builder_for_latency_guard(
    latency_state: Mapping[str, Any] | None,
    latency_stats: Mapping[str, Any] | None,
) -> bool:
    return bool((latency_state or {}).get("skip_trade_builder") or (latency_stats or {}).get("skip_trade_builder"))


def _should_skip_background_maintenance_for_latency_guard(
    latency_state: Mapping[str, Any] | None,
    latency_stats: Mapping[str, Any] | None,
) -> bool:
    return bool((latency_state or {}).get("skip_maintenance") or (latency_stats or {}).get("skip_maintenance"))


def _latency_guard_metric_context(latency_state: Mapping[str, Any] | None, latency_stats: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        "latency_state": dict(latency_state or {}),
        "latency_stats": dict(latency_stats or {}),
    }


def _scan_visible_suggestions(path: Path) -> dict:
    return {"path": str(path), "visible_count": _count_jsonl_rows(path)}


def _zero_visible_counts(counts: dict) -> dict:
    out = dict(counts or {})
    for key in list(out.keys()):
        if isinstance(out[key], (int, float)):
            out[key] = 0
    return out


def _build_pipeline_funnel_payload(*, counts: dict | None = None) -> dict:
    return {"counts": dict(counts or {})}


def _build_top_opportunities_payload(*, rows: list | None = None, label: str | None = None) -> dict:
    return {"label": label, "rows": list(rows or [])}


def _build_ranked_pipeline_runtime_report(*, rows: list | None = None, label: str | None = None) -> dict:
    return {"label": label, "rows": list(rows or [])}


def _write_ranked_pipeline_runtime_evidence(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def _top_blockers_payload(blocker_counts: Counter, limit: int = 5) -> list[dict]:
    return [{"reason": reason, "count": count} for reason, count in blocker_counts.most_common(limit)]


def _coerce_snapshot_number(value):
    try:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return value
        text = str(value).strip()
        if not text:
            return None
        if "." in text:
            return float(text)
        return int(text)
    except Exception:
        return None


def _snapshot_ohlc_payload(market_data: dict) -> dict:
    return {k: _coerce_snapshot_number(market_data.get(k)) for k in ("open", "high", "low", "close")}


def _snapshot_atm_strike(market_data: dict) -> float | None:
    value = _coerce_snapshot_number(market_data.get("atm_strike") or market_data.get("strike"))
    return float(value) if value is not None else None


def _snapshot_symbol_payload(market_data: dict, warnings: list[str]) -> dict:
    return {
        "symbol": market_data.get("symbol"),
        "warnings": list(warnings or []),
        "ohlc": _snapshot_ohlc_payload(market_data),
        "atm_strike": _snapshot_atm_strike(market_data),
    }


def _min_breadth_target(execution_mode: str | None) -> int:
    mode = str(execution_mode or getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
    return 3 if mode == "LIVE" else 1


def _build_min_breadth_backfill(*, market_data: list[dict] | None = None) -> list[dict]:
    return list(market_data or [])


def _is_recoverable_depth_ws_startup_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}:{exc}".lower()
    return any(token in text for token in ("timeout", "tempor", "connection"))
