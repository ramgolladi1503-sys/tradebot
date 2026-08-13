from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace as dc_replace
from pathlib import Path
from typing import Any

from config import config as cfg
from core.feed_runtime import build_canonical_feed_truth_state
from core.market_context import derive_market_context
from core.paths import logs_dir
from core.feed_debug import get_feed_debug
from core.feed.runtime_provenance import validate_feed_runtime_provenance
from core.time_utils import compute_age_sec, now_utc_epoch
from core.trade_schema import build_instrument_id


def trade_attr(trade, name: str, default=None):
    if isinstance(trade, dict):
        return trade.get(name, default)
    return getattr(trade, name, default)


def candidate_origin(candidate) -> str:
    origin_value = trade_attr(candidate, "candidate_origin", None)
    if isinstance(origin_value, dict):
        return str(origin_value.get("candidate_origin") or origin_value.get("origin") or origin_value.get("source") or "").strip().lower()
    return str(origin_value or "").strip().lower()


def is_synthetic_candidate(candidate) -> bool:
    if candidate is None:
        return False
    origin = candidate_origin(candidate)
    source_flags = trade_attr(candidate, "source_flags", None)
    if not isinstance(source_flags, dict):
        source_flags = {}
    source_origin = str(source_flags.get("candidate_origin") or source_flags.get("origin") or source_flags.get("source") or "").strip().lower()
    soft_reason = str(source_flags.get("soft_reject_reason") or "").strip().lower()
    candidate_type = str(trade_attr(candidate, "candidate_type", "") or "").strip().lower()
    strategy_family = str(trade_attr(candidate, "strategy_family", "") or "").strip().lower()
    score_origin = str(trade_attr(candidate, "score_origin", "") or "").strip().lower()
    trade_id = str(trade_attr(candidate, "trade_id", "") or "").strip()
    permission = str(trade_attr(candidate, "permission", "") or "").strip().upper()
    final_action = str(trade_attr(candidate, "final_action", "") or "").strip().upper()
    execution_status = str(trade_attr(candidate, "execution_status", "") or "").strip().lower()
    advisory_lifecycle = permission == "ADVISORY_ONLY" or final_action == "ADVISORY_ONLY" or execution_status == "advisory_only"
    if candidate_type == "fallback_market_candidate":
        return True
    if trade_id.startswith(("softrej_", "tbsoft_")):
        return True
    if strategy_family == "synthetic_advisory":
        return True
    if score_origin == "soft_reject_seed":
        return True
    synthetic_origins = {"pre_builder_gate", "invalid_snapshot", "fallback", "fallback_min_breadth", "softened_builder_path", "softened", "planning_only"}
    if origin in synthetic_origins or source_origin in synthetic_origins:
        return True
    if bool(source_flags.get("recoverable_soft_reject")) or soft_reason:
        return True
    if advisory_lifecycle and (candidate_type.startswith("fallback") or origin in synthetic_origins or source_origin in synthetic_origins or trade_id.startswith(("softrej_", "tbsoft_"))):
        return True
    return False


def is_reportable_executable_candidate(candidate) -> bool:
    if candidate is None or is_synthetic_candidate(candidate):
        return False
    allow_status_fallback = bool(getattr(cfg, "ORCHESTRATOR_EXECUTABLE_REPORT_ALLOW_STATUS_FALLBACK", True))
    trade_id = str(trade_attr(candidate, "trade_id", "") or "").strip().lower()
    if trade_id.startswith(("softrej_", "tbsoft_")):
        return False
    strategy_family = str(trade_attr(candidate, "strategy_family", "") or "").strip().lower()
    if strategy_family == "synthetic_advisory":
        return False
    candidate_status = str(trade_attr(candidate, "candidate_status", "") or "").strip().lower()
    execution_status = str(trade_attr(candidate, "execution_status", "") or "").strip().lower()
    execution_entry_status = str(trade_attr(candidate, "execution_entry_status", "") or "").strip().lower()
    permission = str(trade_attr(candidate, "permission", "") or "").strip().upper()
    final_action = str(trade_attr(candidate, "final_action", "") or "").strip().upper()
    readiness = str(trade_attr(candidate, "readiness", "") or "").strip().upper()
    if bool(trade_attr(candidate, "execution_truth_blocked", False)) or bool(trade_attr(candidate, "execution_truth_blockers", None)):
        return False
    if candidate_status in {"advisory_only", "blocked", "blocked_contract"}:
        return False
    status_derived_executable = (
        allow_status_fallback
        and execution_status in {"", "none", "null"}
        and execution_entry_status == "executable"
        and bool(trade_attr(candidate, "execution_allowed", False))
        and candidate_status not in {"advisory_only", "blocked", "blocked_contract"}
    )
    if execution_status != "executable" and not status_derived_executable:
        return False
    if execution_entry_status != "executable":
        return False
    if permission in {"ADVISORY_ONLY", "QUEUE_ONLY", "BLOCK"}:
        return False
    if final_action in {"ADVISORY_ONLY", "QUEUE_ONLY", "BLOCK"}:
        return False
    if readiness in {"ADVISORY_ONLY", "QUEUE_ONLY", "BLOCKED"}:
        return False
    if not bool(trade_attr(candidate, "execution_allowed", False)):
        return False
    eligible_for_execution = trade_attr(candidate, "eligible_for_execution", None)
    if eligible_for_execution is None:
        eligible_for_execution = trade_attr(candidate, "execution_allowed", False)
    if not bool(eligible_for_execution):
        return False
    if bool(trade_attr(candidate, "execution_blocked", False)):
        return False
    if bool(trade_attr(candidate, "hard_blockers", None)) or bool(trade_attr(candidate, "blockers", None)):
        return False
    if bool(trade_attr(candidate, "unresolved_contract", False)):
        return False
    if trade_attr(candidate, "execution_entry", None) in (None, "", "None"):
        return False
    return True


def candidate_visibility_bucket(candidate) -> str:
    candidate_status = str(trade_attr(candidate, "candidate_status", "") or "").strip().lower()
    execution_status = str(trade_attr(candidate, "execution_status", "") or "").strip().lower()
    permission = str(trade_attr(candidate, "permission", "") or "").strip().upper()
    final_action = str(trade_attr(candidate, "final_action", "") or "").strip().upper()
    if is_synthetic_candidate(candidate):
        return "synthetic"
    if candidate_status in {"advisory_only", "blocked", "blocked_contract"}:
        return "blocked"
    if execution_status == "executable" and permission not in {"ADVISORY_ONLY", "QUEUE_ONLY", "BLOCK"} and final_action not in {"ADVISORY_ONLY", "QUEUE_ONLY", "BLOCK"}:
        return "visible"
    return "unknown"


def candidate_runtime_truth_summary(candidate) -> dict:
    return {
        "trade_id": trade_attr(candidate, "trade_id"),
        "symbol": trade_attr(candidate, "symbol"),
        "strategy": trade_attr(candidate, "strategy"),
        "origin": candidate_origin(candidate),
        "visibility_bucket": candidate_visibility_bucket(candidate),
        "reportable": is_reportable_executable_candidate(candidate),
    }


def candidate_trace_payload(candidate, *, execution_truth_context: dict | None = None) -> dict:
    payload = dict(candidate_runtime_truth_summary(candidate))
    if execution_truth_context:
        payload["execution_truth_context"] = dict(execution_truth_context)
    return payload


def regime_unstable_diagnostic_payload(market_data: dict, gate_reasons: list[str] | None = None) -> dict:
    return {
        "symbol": market_data.get("symbol"),
        "regime": market_data.get("regime"),
        "gate_reasons": list(gate_reasons or []),
        "market_open": market_data.get("market_open"),
        "execution_mode": market_data.get("execution_mode") or getattr(cfg, "EXECUTION_MODE", "SIM"),
    }


def structurally_valid_cycle_candidate(candidate) -> bool:
    if candidate is None:
        return False
    return bool(trade_attr(candidate, "symbol") and trade_attr(candidate, "strategy"))


def filter_invalid_cycle_candidates(candidates, *, symbol: str | None = None) -> tuple[list, list[dict]]:
    valid: list = []
    rejected: list[dict] = []
    for candidate in list(candidates or []):
        if not structurally_valid_cycle_candidate(candidate):
            rejected.append({"symbol": symbol, "reason": "structural_invalid", "candidate": candidate_trace_payload(candidate)})
            continue
        valid.append(candidate)
    return valid, rejected


def replace_trade_fields(trade, updates: dict):
    if trade is None:
        return None
    if isinstance(trade, dict):
        merged = dict(trade)
        merged.update(dict(updates or {}))
        return merged
    try:
        return dc_replace(trade, **dict(updates or {}))
    except Exception:
        return trade


def coerce_trade_dict_to_schema(trade, market_data: dict | None = None):
    if trade is None:
        return None
    if isinstance(trade, dict):
        return dict(trade)
    return {"trade_id": trade_attr(trade, "trade_id"), "symbol": trade_attr(trade, "symbol"), "strategy": trade_attr(trade, "strategy"), "side": trade_attr(trade, "side"), "market_data": dict(market_data or {})}


def read_json_dict(path: Path) -> dict:
    try:
        if not path.exists():
            return {}
        return json.loads(path.read_text())
    except Exception:
        return {}


def safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def normalize_feed_runtime_payload(raw: dict) -> dict:
    return dict(raw or {})


def read_latest_feed_runtime_payload() -> tuple[dict, Path | None]:
    path = logs_dir() / "feed_runtime_latest.json"
    payload = read_json_dict(path)
    if payload:
        current_generation = (get_feed_debug() or {}).get("recovery_generation_id")
        provenance = validate_feed_runtime_provenance(payload, current_generation=current_generation)
        payload["provenance"] = provenance
        if not provenance["valid"]:
            payload["feed_ok"] = False
            payload["execution_feed_ready"] = False
    return payload, path if path.exists() else None


def canonical_feed_truth_state_payload(feed_runtime_payload: dict | None) -> dict:
    return build_canonical_feed_truth_state(feed_runtime_payload or {})


def feed_truth_cycle_gate(feed_runtime_payload: dict | None) -> dict:
    payload = canonical_feed_truth_state_payload(feed_runtime_payload)
    return {"feed_state": payload.get("state"), "feed_reason": payload.get("reason"), "allowed": bool(payload.get("execution_feed_ready"))}


def build_snapshot_numbers(market_data: dict) -> dict:
    return {k: safe_float(market_data.get(k)) for k in ("open", "high", "low", "close")}


def snapshot_atm_strike(market_data: dict) -> float | None:
    value = safe_float(market_data.get("atm_strike") or market_data.get("strike"))
    return float(value) if value is not None else None
