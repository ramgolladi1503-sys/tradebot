import json
import time
import hashlib
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Mapping

from core.orders.order_intent import OrderIntent
from core.learning_paths import canonical_suggestions_log_path, rejected_candidates_paths, suggestion_log_paths
from core.paths import logs_dir, data_root, repo_root
from core.feed.artifact_loader import load_current_feed_runtime
from core.upstox_resolver import resolve_upstox_key
from core.market_calendar import choose_nearest_available_expiry
from core.trade_schema import build_instrument_id
from core.trade_permission import (
    build_permission_payload,
    classify_confidence_vs_threshold,
    resolve_confidence_thresholds,
)
from core.trade_identity import compute_trade_key, derive_strategy_id, infer_candidate_identity
from core.option_token_resolver import TokenCoverageError, is_safe_nearest_contract_fallback, resolve_option_token
from core.option_liquidity_cache import hydrate_option_liquidity_fields
from core.option_entry import get_option_ltp_sla_sec, validate_live_entry
from core.opportunity_engine import annotate_ranked_opportunities
from core.gating import gate_decision
from core.tick_store import get_ltp
from core.kite_depth_ws import ensure_subscribed_tokens
from core.entry_semantics import (
    ENTRY_SOURCE_ENUM,
    EntryContractViolation,
    build_entry_state,
    derive_execution_entry_recovery,
    enforce_entry_contract,
    should_allow_last_execution_fallback,
)
from core.advisory_schema import AdvisorySchemaError, QUOTE_SOURCES, deserialize_advisory_row, log_advisory_schema_error, serialize_advisory_row
from core.candidate_finalization import assert_executable_candidate_ready, assert_ranked_candidate_ready, stamp_lifecycle_stage
from core.advisory_row_integrity import (
    ADVISORY_ONLY_ROW_KIND,
    CANONICAL_ROW_KIND,
    log_corrupt_advisory_row,
    recompute_levels_from_final_entry,
)
from core.decision_engine import evaluate_candidate_decision
from core.blocker_lifecycle import TARGET_BLOCKER_CODES, evaluate_advisory_contract_blockers, get_blocker_registry
from core.candidate_scoring import score_candidate
from core.execution_entry_trace import append_execution_entry_trace
from core.events import write_json_atomic
from core.issue_policy import ISSUE_CATEGORY_HARD, ISSUE_CATEGORY_SOFT, ISSUE_CATEGORY_WARNING, classify_issue
from core.position_sizer import PositionSizer
from core.time_utils import is_market_open_ist
from core.observability.pipeline import append_trade_lifecycle_event
from core.trade_state_machine import ensure_trade_lifecycle, rehydrate_trade_lifecycle
from core.time_utils import format_ts_ist
from core.log_writer import get_jsonl_writer
from core.expectancy.expectancy_gate import apply_expectancy_gate
from core.expectancy.edge_ranking import apply_edge_ranking
from core.candidate_journal import write_candidate_journal_row
from core.quote_truth import quote_bundle_is_consistent, quote_consistency_score, resolve_quote_validation_status
from core.auth_manager import runtime_auth_snapshot

try:
    from config import config as cfg
except Exception:
    cfg = None

logger = logging.getLogger(__name__)
_POSITION_SIZER = PositionSizer()


def _runtime_path(cfg_key: str, filename: str) -> Path:
    try:
        raw = str(getattr(cfg, cfg_key, "") or "").strip()
    except Exception:
        raw = ""
    if raw:
        return Path(raw)
    return logs_dir() / filename


def _promotion_trace_path() -> Path:
    try:
        raw = str(getattr(cfg, "PERMISSION_PROMOTION_TRACE_PATH", "") or "").strip()
    except Exception:
        raw = ""
    if raw:
        return Path(raw)
    return logs_dir() / "permission_promotion_trace.jsonl"


def _has_execution_recovery_blocker(entry) -> bool:
    hard_codes = set(_dedupe_issue_codes(list(entry.get("hard_blockers") or [])))
    if hard_codes - {"MISSING_ENTRY"}:
        return True
    codes = set(_dedupe_issue_codes(list(entry.get("blockers") or [])))
    return bool(codes & {"STALE_OPTION_LTP", "NO_LIVE_OPTION_FEED", "OFFHOURS_SYNTHETIC"})


def _has_valid_token(entry) -> bool:
    token = entry.get("instrument_token")
    if token in (None, "", "None", 0):
        return False
    try:
        float(token)
        return True
    except Exception:
        return False


QUEUE_PATH = _runtime_path("REVIEW_QUEUE_PATH", "review_queue.json")
QUICK_QUEUE_PATH = _runtime_path("QUICK_REVIEW_QUEUE_PATH", "quick_review_queue.json")
ZERO_HERO_QUEUE_PATH = _runtime_path("ZERO_HERO_QUEUE_PATH", "zero_hero_queue.json")
SCALP_QUEUE_PATH = _runtime_path("SCALP_QUEUE_PATH", "scalp_queue.json")
TARGET_POINTS_QUEUE_PATH = _runtime_path("TARGET_POINTS_QUEUE_PATH", "target_points_queue.json")
APPROVED_PATH = _runtime_path("APPROVED_TRADES_PATH", "approved_trades.json")

_META_CACHE = {"ts": 0.0, "data": {}}
_CHAIN_CACHE = {"ts": 0.0, "data": {"by_token": {}, "by_contract": {}, "by_symbol_strike_type": {}}}
_ADVISORY_REST_LTP_CACHE: dict[str, dict] = {}
_ADVISORY_REST_LTP_LAST_ATTEMPT: dict[str, float] = {}
_NON_BLOCKING_ENTRY_STATUSES = {"OK", "PRICE_MISMATCH", "REST_FALLBACK", "OFFHOURS_SYNTHETIC", "DISPLAYABLE", "NON_EXECUTABLE"}
_LOW_GLOBAL_CONF_LOGGED_MINUTE_BY_SYMBOL: dict[str, int] = {}
_ENTRY_REQUIRED_STATUSES = {"ACTIVE", "PLANNING", "PROPOSED", "READY", "QUEUE_ONLY"}
_ENTRY_INTEGRITY_REASON = "MISSING_ENTRY"
_EXPLICIT_REVIEW_STATUSES = {"PLANNING", "BLOCKED_CONTRACT", "BLOCKED_APPROVAL", "ADVISORY_ONLY", "QUEUE_ONLY", "READY"}
_DISPLAY_ENTRY_STATUSES = {"displayable", "non_executable", "missing"}
_EXECUTION_ENTRY_STATUSES = {"executable", "non_executable", "missing"}
_EXECUTABLE_ENTRY_SOURCES = {"ask", "bid", "last", "retained_prior_ask", "retained_prior_bid"}
_LIFECYCLE_SNAPSHOT_KEY = "_lifecycle_snapshot"
_STALE_QUOTE_AGE_SENTINEL = float(10**9)
_LIFECYCLE_IMMUTABLE_FIELDS = (
    "execution_entry",
    "execution_entry_source",
    "execution_entry_status",
    "display_entry",
    "display_entry_source",
    "display_entry_status",
    "entry",
    "entry_source",
    "entry_status",
    "entry_reason",
    "entry_clear_reason",
)
_SPLIT_BRAIN_LOGGED_AT_BY_KEY: dict[str, float] = {}


def _entry_lifecycle_payload(
    *,
    execution_entry=None,
    execution_entry_source=None,
    execution_entry_status=None,
    display_entry=None,
    display_entry_source=None,
    display_entry_status=None,
    clear_reason=None,
    entry_reason=None,
) -> dict:
    return {
        "execution_entry": _safe_float(execution_entry),
        "execution_entry_source": str(execution_entry_source or "").strip().lower() or "none",
        "execution_entry_status": str(execution_entry_status or "").strip().lower(),
        "display_entry": _safe_float(display_entry),
        "display_entry_source": str(display_entry_source or "").strip().lower() or "none",
        "display_entry_status": str(display_entry_status or "").strip().lower(),
        "clear_reason": str(clear_reason or "").strip().lower() or None,
        "entry_reason": None if not str(entry_reason or "").strip() else str(entry_reason),
    }


def _entry_lifecycle_from_entry(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return _entry_lifecycle_payload()
    return _entry_lifecycle_payload(
        execution_entry=entry.get("execution_entry"),
        execution_entry_source=entry.get("execution_entry_source"),
        execution_entry_status=entry.get("execution_entry_status"),
        display_entry=entry.get("display_entry"),
        display_entry_source=entry.get("display_entry_source"),
        display_entry_status=entry.get("display_entry_status"),
        clear_reason=entry.get("entry_clear_reason"),
        entry_reason=entry.get("entry_reason"),
    )


def _has_valid_entry(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    if bool(entry.get("_origin_synthetic_offhours")) and (
        _safe_float(entry.get("_synthetic_entry_price_original")) is not None
        or _safe_float(entry.get("entry")) is not None
    ):
        return True
    if _safe_float(entry.get("entry_price")) is not None:
        return True
    if _safe_float(entry.get("expected_entry")) is not None:
        return True
    return bool(
        _safe_float(entry.get("execution_entry")) is not None
        and str(entry.get("execution_entry_status") or "").strip().lower() == "executable"
    )


def _get_valid_entry_base(entry: dict):
    if not isinstance(entry, dict):
        return None
    base = _safe_float(entry.get("entry_price"))
    if base is not None:
        return base
    base = _safe_float(entry.get("expected_entry"))
    if base is not None:
        return base
    return None


def _has_valid_original_entry(entry: dict) -> bool:
    return _get_valid_entry_base(entry) is not None


def _is_queue_only_lifecycle(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    return bool(
        str(entry.get("permission") or "").strip().upper() == "QUEUE_ONLY"
        or str(entry.get("readiness") or "").strip().upper() == "QUEUE_ONLY"
        or str(entry.get("final_action") or "").strip().upper() == "QUEUE_ONLY"
        or str(entry.get("execution_status") or "").strip().lower() == "queue_only"
    )


def _should_block_queue_only_entry_promotion(entry: dict) -> bool:
    return bool(_is_queue_only_lifecycle(entry) and not _has_valid_original_entry(entry))


def _should_force_missing_queue_only_lifecycle(entry: dict) -> bool:
    return _should_block_queue_only_entry_promotion(entry)


def _candidate_origin_value(entry: dict) -> str:
    if not isinstance(entry, dict):
        return ""
    origin_value = entry.get("candidate_origin")
    if not origin_value and isinstance(entry.get("source_flags"), dict):
        origin_value = entry["source_flags"].get("candidate_origin")
    if isinstance(origin_value, dict):
        origin_value = (
            origin_value.get("candidate_origin")
            or origin_value.get("origin")
            or origin_value.get("source")
        )
    return str(origin_value or "").strip().lower()


def _is_softened_candidate_origin(entry: dict) -> bool:
    origin = _candidate_origin_value(entry)
    return origin in {"softened_builder_path", "softened"}


def _is_synthetic_advisory_entry(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    candidate_type = str(entry.get("candidate_type") or "").strip().lower()
    if candidate_type == "fallback_market_candidate":
        return True
    trade_id = str(entry.get("trade_id") or "")
    if trade_id.startswith("softrej_"):
        return True
    origin = _candidate_origin_value(entry)
    if origin in {"pre_builder_gate", "invalid_snapshot", "fallback", "fallback_min_breadth"}:
        return True
    permission = str(entry.get("permission") or "").strip().upper()
    final_action = str(entry.get("final_action") or "").strip().upper()
    execution_status = str(entry.get("execution_status") or "").strip().lower()
    advisory_lifecycle = permission == "ADVISORY_ONLY" or final_action == "ADVISORY_ONLY" or execution_status == "advisory_only"
    if advisory_lifecycle and (candidate_type.startswith("fallback") or origin or trade_id.startswith("softrej_")):
        return True
    return False


def _is_fallback_candidate(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    row_kind = str(entry.get("row_kind") or "").strip().lower()
    candidate_class = str(entry.get("candidate_class") or "").strip().lower()
    candidate_type = str(entry.get("candidate_type") or "").strip().lower()
    candidate_origin = str(entry.get("candidate_origin") or "").strip().lower()
    quote_source = str(entry.get("quote_source") or "").strip().lower()
    trade_id = str(entry.get("trade_id") or "").strip().lower()
    source_flags = entry.get("source_flags")
    flags = source_flags if isinstance(source_flags, dict) else {}
    fallback_flag = any(
        bool(flags.get(key))
        for key in ("fallback_used", "recovered_fallback", "softened", "soft_reject_fallback")
    )
    return bool(
        fallback_flag
        or row_kind in {"recovered_fallback", "fallback"}
        or candidate_class == "fallback"
        or ("fallback" in candidate_type and candidate_type not in {"fallback_directional", "directional_fallback"})
        or "fallback" in candidate_origin
        or quote_source in {"rest_fallback", "synthetic_offhours", "subscription_failed"}
        or trade_id.startswith("softrej_")
    )


def _fallback_non_executable_reason(entry: dict) -> str:
    if not isinstance(entry, dict):
        return "fallback_not_executable"
    for field in (
        "final_emit_block_reason",
        "final_blocker",
        "permission_reason",
        "reject_reason",
        "reason",
        "entry_block_reason",
        "hard_reason",
        "execution_block_reason",
    ):
        text = str(entry.get(field) or "").strip()
        if not text:
            continue
        if text.upper() in {"OK", "NONE"}:
            continue
        if text.lower() in {"fallback_not_executable"}:
            continue
        if "fallback" not in text.lower() or text.lower() in {"rest_fallback", "synthetic_offhours", "subscription_failed"}:
            return text
    return "fallback_not_executable"


def _apply_fallback_execution_kill(entry: dict) -> dict:
    if not _is_fallback_candidate(entry):
        return entry
    out = dict(entry)
    block_reason = _fallback_non_executable_reason(out)
    existing_permission = str(out.get("permission") or "").strip().upper()
    existing_final_action = str(out.get("final_action") or "").strip().upper()
    existing_execution_status = str(out.get("execution_status") or "").strip().lower()
    existing_readiness = str(out.get("readiness") or "").strip().upper()
    if existing_permission == "BLOCK" or existing_final_action == "BLOCK" or existing_execution_status == "blocked":
        out["permission"] = "BLOCK"
        out["final_action"] = "BLOCK"
        out["execution_status"] = "blocked"
        out["readiness"] = "BLOCKED"
        out["candidate_status"] = "blocked"
        out["visibility_bucket"] = "blocked"
    else:
        out["permission"] = "QUEUE_ONLY"
        out["final_action"] = "QUEUE_ONLY"
        out["execution_status"] = "queue_only"
        out["readiness"] = "QUEUE_ONLY"
        out["candidate_status"] = "advisory_only"
        out["visibility_bucket"] = "advisory"
    if existing_readiness == "BLOCKED":
        out["readiness"] = "BLOCKED"
    out["reportable_executable"] = False
    out["execution_allowed"] = False
    out["eligible_for_execution"] = False
    out["selected_for_execution"] = False
    out["tradable"] = False
    out["is_executable"] = False
    out["fallback_used"] = True
    if not str(out.get("final_emit_block_reason") or "").strip():
        out["final_emit_block_reason"] = block_reason
    if not str(out.get("permission_reason") or "").strip():
        out["permission_reason"] = block_reason
    if not str(out.get("final_blocker") or "").strip():
        out["final_blocker"] = block_reason
    if not str(out.get("reject_reason") or "").strip():
        out["reject_reason"] = block_reason
    if not str(out.get("reason") or "").strip():
        out["reason"] = block_reason
    out.setdefault("execution_truth_blocked", False)
    out.setdefault("execution_truth_advisory", True)
    return out


def _entry_expectancy_lookup(entry: Mapping[str, Any] | None) -> Any:
    if not isinstance(entry, Mapping):
        return None
    direct = entry.get("expectancy_lookup")
    if direct is not None:
        return direct
    metadata = entry.get("metadata")
    if isinstance(metadata, Mapping):
        direct = metadata.get("expectancy_lookup")
        if direct is not None:
            return direct
    source_flags = entry.get("source_flags")
    if isinstance(source_flags, Mapping):
        direct = source_flags.get("expectancy_lookup")
        if direct is not None:
            return direct
    return None


def _apply_expectancy_gate_if_present(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    lookup = _entry_expectancy_lookup(entry)
    status = str(entry.get("expectancy_status") or entry.get("keep_watch_kill_status") or "").strip().upper()
    override = str(
        entry.get("expectancy_override")
        or entry.get("expectancy_status_override")
        or entry.get("manual_expectancy_override")
        or ""
    ).strip()
    if lookup is None and not status and not override:
        return entry
    gated = apply_expectancy_gate(entry, expectancy_lookup=lookup)
    return apply_edge_ranking(gated, expectancy_lookup=lookup)


_HARD_EXECUTION_BLOCKER_CODES = {
    "FEED_STALE",
    "NO_LIVE_OPTION_FEED",
    "UNRESOLVED_CONTRACT",
    "MISSING_CONTRACT_FIELDS",
    "QUOTE_MISSING",
    "NO_TOKEN",
    "MISSING_OPTION_TOKEN",
    "MISSING_ENTRY",
}

_SOFT_EXECUTION_BLOCKER_CODES = {
    "LATENCY_GUARD_COOLDOWN",
    "REGIME_UNSTABLE",
}


def _candidate_confidence(entry: dict) -> float:
    if not isinstance(entry, dict):
        return 0.0
    return max(
        float(_safe_float(entry.get("confidence")) or 0.0),
        float(_safe_float(entry.get("rank_score")) or 0.0),
        float(_safe_float(entry.get("confidence_final")) or 0.0),
    )


def _entry_reason_codes(entry: dict) -> set[str]:
    codes: set[str] = set()
    if not isinstance(entry, dict):
        return codes
    for field in ("reject_reason", "entry_block_code", "permission_reason", "reason"):
        text = str(entry.get(field) or "").strip().lower()
        if text:
            codes.add(text)
    for key in ("gate_reasons", "soft_penalties", "warnings", "blockers", "hard_blockers"):
        for item in list(entry.get(key) or []):
            text = str(item or "").strip().lower()
            if text:
                codes.add(text)
    source_flags = entry.get("source_flags") or {}
    if isinstance(source_flags, dict):
        text = str(source_flags.get("soft_reject_reason") or "").strip().lower()
        if text:
            codes.add(text)
    return codes


def _best_reject_reason(entry: dict, *, default: str = "unspecified_trade_builder_reject") -> str:
    if not isinstance(entry, dict):
        return str(default or "unspecified_trade_builder_reject")
    generic = "unspecified_trade_builder_reject"
    quote_validation_status = str(entry.get("quote_validation_status") or "").strip().upper()
    if quote_validation_status in {"STALE_OPTION_LTP", "NO_LIVE_OPTION_FEED", "MISSING_OPTION_TOKEN"}:
        return quote_validation_status
    preferred_fields = (
        "final_blocker",
        "hard_reason",
        "permission_reason",
        "entry_block_code",
        "quote_validation_status",
        "reject_reason",
        "reason",
    )
    for field in preferred_fields:
        value = str(entry.get(field) or "").strip()
        if value and value.lower() != generic:
            return value
    for collection in ("hard_blockers", "blockers", "gate_reasons", "warnings"):
        for item in list(entry.get(collection) or []):
            text = str(item or "").strip()
            if text and text.lower() != generic:
                return text
    fallback = str(entry.get("reject_reason") or entry.get("reason") or "").strip()
    if fallback:
        return fallback
    return str(default or generic)


def _execution_ineligibility_reason(entry: dict, *, default: str = "no_execution_candidates") -> str:
    if not isinstance(entry, dict):
        return str(default or "no_execution_candidates")
    if _is_fallback_candidate(entry):
        return _fallback_non_executable_reason(entry)
    execution_truth_blockers = _dedupe_issue_codes(list(entry.get("execution_truth_blockers") or []))
    if bool(entry.get("execution_truth_blocked")) and execution_truth_blockers:
        return execution_truth_blockers[0]
    preferred_reason = str(_best_reject_reason(entry, default="") or "").strip()
    if preferred_reason and preferred_reason.lower() not in {
        "ok",
        "ready",
        "queue_only",
        "advisory_only",
        "no_execution_candidates",
        "unspecified_trade_builder_reject",
    }:
        return preferred_reason
    unresolved_contract = bool(entry.get("unresolved_contract"))
    if not unresolved_contract and _requires_option_contract_identity(entry):
        try:
            unresolved_contract = _is_unresolved_option_contract(entry)
        except Exception:
            unresolved_contract = False
    if unresolved_contract:
        return "unresolved_contract"
    execution_block_reason = str(entry.get("execution_block_reason") or "").strip()
    if execution_block_reason:
        return execution_block_reason
    hard_blockers = _dedupe_issue_codes(list(entry.get("hard_blockers") or []))
    if hard_blockers:
        return hard_blockers[0]
    blockers = _dedupe_issue_codes(
        list(entry.get("blockers") or [])
        + list(entry.get("gate_reasons") or [])
        + list(entry.get("execution_blockers") or [])
        + list(entry.get("execution_truth_blockers") or [])
    )
    if blockers:
        return blockers[0]
    execution_entry = _safe_float(entry.get("execution_entry"))
    execution_entry_status = str(entry.get("execution_entry_status") or "").strip().lower()
    if execution_entry is None:
        if execution_entry_status in {"non_executable", "missing"}:
            return f"execution_entry_{execution_entry_status}"
        return "missing_execution_entry"
    if execution_entry_status and execution_entry_status != "executable":
        return f"execution_entry_{execution_entry_status}"
    if bool(entry.get("execution_blocked")):
        return "execution_blocked"
    if not bool(entry.get("execution_allowed")):
        return "execution_not_allowed"
    if not bool(entry.get("eligible_for_execution", False)):
        return "execution_not_eligible"
    execution_status = str(entry.get("execution_status") or "").strip().lower()
    if execution_status:
        return execution_status
    return str(default or "no_execution_candidates")


def _is_weak_signal_candidate(entry: dict) -> bool:
    codes = _entry_reason_codes(entry)
    return bool(codes & {"weak_signal", "no_signal"})


def _soft_reject_reason(entry: dict) -> str:
    if not isinstance(entry, dict):
        return ""
    source_flags = entry.get("source_flags") or {}
    if isinstance(source_flags, dict):
        reason = str(source_flags.get("soft_reject_reason") or "").strip().lower()
        if reason:
            return reason
    return str(
        entry.get("entry_block_code")
        or entry.get("reject_reason")
        or ""
    ).strip().lower()


def _blocks_execute_due_to_soft_reject(entry: dict) -> bool:
    soft_reason = _soft_reject_reason(entry)
    if soft_reason in {"weak_signal", "no_signal", "signal_score_below_min"}:
        return True
    source_flags = entry.get("source_flags") or {}
    candidate_origin = ""
    if isinstance(source_flags, dict):
        candidate_origin = str(source_flags.get("candidate_origin") or "").strip().lower()
    if not candidate_origin:
        candidate_origin = str(entry.get("candidate_origin") or "").strip().lower()
    if candidate_origin in {"softened_builder_path", "softened"} and bool(soft_reason):
        return True
    return False


def _is_hard_execution_blocker(reason: str) -> bool:
    code = str(reason or "").strip().upper()
    if not code:
        return False
    if code in _HARD_EXECUTION_BLOCKER_CODES:
        return True
    return code.startswith("HARD_")


def _is_soft_execution_blocker(reason: str) -> bool:
    code = str(reason or "").strip().upper()
    return bool(code and code in _SOFT_EXECUTION_BLOCKER_CODES)


def _mark_synthetic_advisory_entry(entry: dict, *, emit_log: bool = False) -> dict:
    out = dict(entry or {})
    score_cap = float(getattr(cfg, "PHASE2_MIN_BORDERLINE_SCORE", 0.12) or 0.12)
    for field in ("rank_score", "final_score", "opportunity_score"):
        value = _safe_float(out.get(field))
        if value is not None:
            out[field] = min(float(value), float(score_cap))
    out["strategy_family"] = "synthetic_advisory"
    out["setup_variant"] = "synthetic_advisory"
    if out.get("direction") in (None, "", "None"):
        out["direction"] = "UNKNOWN"
    out["eligible_for_execution"] = False
    out["execution_allowed"] = False
    out["execution_status"] = "advisory_only"
    out["candidate_status"] = "advisory_only"
    if emit_log:
        print(
            "SYNTHETIC_SKIPPED_FROM_EXECUTION",
            {
                "trade_id": out.get("trade_id"),
                "symbol": out.get("symbol"),
                "strategy_family": out.get("strategy_family"),
            },
        )
    return out


def _is_execution_eligible(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    if _is_fallback_candidate(entry):
        return False
    if bool(entry.get("execution_truth_blocked")) or bool(entry.get("execution_truth_blockers")):
        return False
    hard_blockers = _dedupe_issue_codes(list(entry.get("hard_blockers") or []))
    permission = str(entry.get("permission") or "").strip().upper()
    final_action = str(entry.get("final_action") or "").strip().upper()
    execution_entry = _safe_float(entry.get("execution_entry"))
    execution_entry_status = str(entry.get("execution_entry_status") or "").strip().lower()
    unresolved_contract = bool(entry.get("unresolved_contract"))
    if not unresolved_contract and _requires_option_contract_identity(entry):
        try:
            unresolved_contract = _is_unresolved_option_contract(entry)
        except Exception:
            unresolved_contract = False
    if (
        permission == "EXECUTE"
        and final_action == "EXECUTE"
        and execution_entry is not None
        and execution_entry_status == "executable"
        and not bool(entry.get("execution_blocked"))
        and not unresolved_contract
        and not hard_blockers
    ):
        return True
    strategy_family = str(entry.get("strategy_family") or "").strip().lower()
    execution_source = str(entry.get("execution_entry_source") or "").strip().lower()
    if strategy_family == "synthetic_advisory":
        return False
    if execution_source in {"recovered_fallback", "rest_fallback", "synthetic_offhours"}:
        return False
    execution_status = str(entry.get("execution_status") or "").strip().lower()
    candidate_status = str(entry.get("candidate_status") or "").strip().lower()
    if execution_status in {"advisory_only", "blocked"}:
        return False
    if candidate_status in {"advisory_only", "blocked", "blocked_contract"}:
        return False
    if bool(entry.get("eligible_for_execution", entry.get("execution_allowed", False))):
        return True
    return execution_status == "executable"


def _compute_execution_decision(entry: dict) -> tuple[str, str]:
    out = dict(entry or {})
    if _is_synthetic_advisory_entry(out):
        return "advisory_only", "synthetic_skipped"
    blocker_codes = _dedupe_issue_codes(
        list(out.get("hard_blockers") or [])
        + list(out.get("blockers") or [])
        + list(out.get("gate_reasons") or [])
        + list(out.get("execution_blockers") or [])
    )
    hard_blockers = [code for code in blocker_codes if _is_hard_execution_blocker(code)]
    if hard_blockers:
        return "blocked", "hard_blocker"
    confidence = _candidate_confidence(out)
    soft_blockers = [code for code in blocker_codes if _is_soft_execution_blocker(code)]
    if soft_blockers and confidence >= float(getattr(cfg, "TRADE_BUILDER_BORDERLINE_CONF_MIN", 0.18) or 0.18):
        return "queue_only", "strong_conf_soft_block_override"
    if soft_blockers:
        return "advisory_only", "soft_blocker"
    if confidence >= float(getattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.18) or 0.18) and not blocker_codes:
        return "executable", "clean_confident_candidate"
    if confidence >= float(getattr(cfg, "TRADE_BUILDER_BORDERLINE_CONF_MIN", 0.18) or 0.18):
        return "queue_only", "borderline_candidate"
    return "advisory_only", "low_confidence"




def _current_feed_session_id() -> str:
    candidates = (
        logs_dir() / "feed_runtime_latest.json",
        repo_root() / "logs" / "feed_runtime_latest.json",
        repo_root() / ".runtime" / "feed_runtime_latest.json",
    )
    for path in candidates:
        try:
            if not path.exists() or not path.is_file():
                continue
            payload = _read_json_dict(path)
        except Exception:
            continue
        canonical = payload.get("canonical_feed_truth") if isinstance(payload, dict) else None
        if isinstance(canonical, dict):
            session_id = str(canonical.get("session_id") or "").strip()
            if session_id:
                return session_id
        session_id = str(payload.get("session_id") or "").strip() if isinstance(payload, dict) else ""
        if session_id:
            return session_id
    return ""


def _read_json_dict(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _apply_session_isolation(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    current_session_id = _current_feed_session_id()
    entry_session_id = str(out.get("session_id") or "").strip()
    if current_session_id and entry_session_id and entry_session_id != current_session_id:
        out["visibility_bucket"] = "historical_only"
        out["execution_allowed"] = False
        out["reportable_executable"] = False
        out["permission"] = "ADVISORY_ONLY"
        out["final_action"] = "ADVISORY_ONLY"
        out["execution_status"] = "historical_only"
        out["candidate_status"] = "historical_only"
        out["final_emit_block_reason"] = "previous_session_candidate"
        out["previous_session_candidate"] = True
    return out

def _apply_candidate_identity(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    out = _apply_session_isolation(out)
    if _is_synthetic_advisory_entry(out):
        return _mark_synthetic_advisory_entry(out, emit_log=True)
    identity = infer_candidate_identity(out)
    for field in ("candidate_type", "strategy_family", "setup_variant", "direction"):
        value = out.get(field)
        if value in (None, "", "None"):
            out[field] = identity.get(field)
    if out.get("candidate_type") in (None, "", "None", "unknown", "UNKNOWN"):
        out["candidate_type"] = "directional"
    if out.get("strategy_family") in (None, "", "None", "unknown", "UNKNOWN"):
        strategy_name = str(out.get("strategy") or out.get("strategy_name") or "").strip().upper()
        if "MEAN" in strategy_name:
            out["strategy_family"] = "mean-reversion"
        elif "VOL" in strategy_name or "EXPANSION" in strategy_name:
            out["strategy_family"] = "volatility_expansion"
        elif "RANGE" in strategy_name:
            out["strategy_family"] = "range-watchlist"
        elif "CONT" in strategy_name or "TREND" in strategy_name:
            out["strategy_family"] = "continuation"
        else:
            out["strategy_family"] = str(getattr(cfg, "REVIEW_QUEUE_STRATEGY_FAMILY_FALLBACK", "breakout") or "breakout").strip().lower() or "breakout"
    if out.get("setup_variant") in (None, "", "None", "unknown", "UNKNOWN"):
        out["setup_variant"] = str(out.get("strategy_family") or "unknown").strip().lower() or "unknown"
    if out.get("direction") in (None, "", "None"):
        out["direction"] = "UNKNOWN"
    return out


def _should_preserve_missing_queue_only_entry(entry: dict) -> bool:
    return _is_queue_only_lifecycle(entry)


def _capture_queue_only_final_promotion_block(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    out["_block_queue_only_final_promotion"] = _should_block_queue_only_entry_promotion(out)
    return out


def _should_block_final_queue_only_entry_promotion(entry: dict) -> bool:
    return bool(isinstance(entry, dict) and entry.get("_block_queue_only_final_promotion"))


def _should_block_entry_recovery_for_queue_only(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    missing_entry_signal = str(entry.get("entry_block_code") or "").strip().upper() == "MISSING_ENTRY"
    missing_entry_signal = missing_entry_signal or any(
        str(code or "").strip().upper() == "MISSING_ENTRY"
        for code in list(entry.get("blockers") or []) + list(entry.get("hard_blockers") or [])
    )
    missing_entry_signal = missing_entry_signal or str(entry.get("entry_clear_reason") or "").strip().lower() in {
        "missing_entry",
        "missing_display_entry",
    }
    return bool(
        not _has_valid_entry(entry)
        and _is_queue_only_lifecycle(entry)
        and missing_entry_signal
    )


def _clear_fabricated_entry_lifecycle(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    preserved_display_entry = _safe_float(out.get("display_entry"))
    preserved_display_source = str(out.get("display_entry_source") or "").strip().lower() or "none"
    if preserved_display_entry is None:
        for fallback_field in (
            "pre_validation_entry",
            "entry",
            "suggested_entry",
            "expected_entry",
            "entry_price",
        ):
            fallback_entry = _safe_float(out.get(fallback_field))
            if fallback_entry is not None:
                preserved_display_entry = fallback_entry
                fallback_source = str(out.get(f"{fallback_field}_source") or "").strip().lower()
                if fallback_source and fallback_source not in {"", "none"}:
                    preserved_display_source = fallback_source
                break
    out["execution_entry"] = None
    out["execution_entry_source"] = "none"
    out["execution_entry_status"] = "non_executable"
    if preserved_display_entry is not None:
        out["display_entry"] = preserved_display_entry
        out["display_entry_source"] = preserved_display_source
        out["display_entry_status"] = "displayable"
        out["entry"] = preserved_display_entry
        out["entry_source"] = preserved_display_source
        out["entry_status"] = "displayable"
        out["entry_clear_reason"] = None
    else:
        out["display_entry"] = None
        out["display_entry_source"] = "none"
        out["display_entry_status"] = "missing"
        out["entry"] = None
        out["entry_source"] = "none"
        out["entry_status"] = "missing"
        out["entry_clear_reason"] = (
            str(out.get("entry_clear_reason") or "missing_entry").strip().lower() or "missing_entry"
        )
    out.pop("entry_recovered", None)
    out.pop("entry_recovered_from", None)
    return out


def _apply_final_queue_only_entry_promotion_block(entry: dict) -> dict:
    if not _should_block_final_queue_only_entry_promotion(entry):
        return entry
    out = _clear_fabricated_entry_lifecycle(entry)
    out["execution_status"] = "queue_only"
    out["execution_allowed"] = False
    out["tradable"] = False
    out["is_executable"] = False
    return out


def _enforce_non_executable_emit_lifecycle(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    if _is_execution_eligible(entry):
        return entry
    out = dict(entry)
    block_reason = _execution_ineligibility_reason(out)
    hard_block = _is_hard_execution_blocker(block_reason) or bool(out.get("unresolved_contract")) or bool(
        out.get("execution_blocked")
    )
    out = _capture_queue_only_final_promotion_block(out)
    out["final_emit_block_reason"] = block_reason
    if hard_block:
        out["permission"] = "BLOCK"
        out["final_action"] = "BLOCK"
        out["readiness"] = "BLOCKED"
        out["execution_status"] = "blocked"
        out["candidate_status"] = "blocked"
        out["final_blocker"] = out.get("final_blocker") or block_reason
    else:
        out["permission"] = "QUEUE_ONLY"
        out["final_action"] = "QUEUE_ONLY"
        out["readiness"] = "QUEUE_ONLY"
        out["execution_status"] = "queue_only"
        out["candidate_status"] = "advisory_only"
    out["candidate_status"] = "advisory_only"
    out["execution_allowed"] = False
    out["eligible_for_execution"] = False
    out["tradable"] = False
    out["is_executable"] = False
    out["selected_for_execution"] = False
    if not str(out.get("permission_reason") or "").strip():
        out["permission_reason"] = block_reason
    return _classify_candidate_status(out)


def _entry_lifecycle_is_valid(lifecycle: dict) -> bool:
    if not isinstance(lifecycle, dict):
        return False
    display_entry = _safe_float(lifecycle.get("display_entry"))
    execution_entry = _safe_float(lifecycle.get("execution_entry"))
    display_entry_status = str(lifecycle.get("display_entry_status") or "").strip().lower()
    execution_entry_status = str(lifecycle.get("execution_entry_status") or "").strip().lower()
    clear_reason = str(lifecycle.get("clear_reason") or "").strip()
    return bool(
        display_entry_status in _DISPLAY_ENTRY_STATUSES
        and execution_entry_status in _EXECUTION_ENTRY_STATUSES
        and (
            (display_entry is not None and display_entry_status in {"displayable", "non_executable"})
            or (display_entry is None and display_entry_status == "missing" and bool(clear_reason))
        )
        and (
            (execution_entry is not None and execution_entry_status == "executable")
            or (execution_entry is None and execution_entry_status in {"non_executable", "missing"})
        )
    )


def _normalize_entry_lifecycle(
    lifecycle: dict,
    *,
    fallback_clear_reason: str | None = None,
) -> dict:
    normalized = _entry_lifecycle_payload(**(lifecycle or {}))
    display_entry = normalized["display_entry"]
    execution_entry = normalized["execution_entry"]

    if execution_entry is None:
        normalized["execution_entry_source"] = normalized.get("execution_entry_source") or "none"
        if normalized.get("execution_entry_status") not in _EXECUTION_ENTRY_STATUSES or normalized.get("execution_entry_status") == "executable":
            normalized["execution_entry_status"] = "non_executable" if display_entry is not None else "missing"
    else:
        normalized["execution_entry_status"] = "executable"

    if display_entry is None:
        normalized["display_entry_source"] = "none"
        normalized["display_entry_status"] = "missing"
        normalized["clear_reason"] = str(
            normalized.get("clear_reason")
            or fallback_clear_reason
            or "missing_display_entry"
        ).strip().lower()
        normalized["entry_reason"] = None if not str(normalized.get("entry_reason") or "").strip() else normalized.get("entry_reason")
    else:
        if normalized.get("display_entry_status") not in {"displayable", "non_executable"}:
            normalized["display_entry_status"] = "displayable"
        normalized["clear_reason"] = None

    return normalized


def _recover_missing_execution_entry(entry: dict, lifecycle: dict) -> tuple[dict, dict]:
    if not isinstance(entry, dict):
        return entry, lifecycle
    out = dict(entry)
    normalized = _entry_lifecycle_payload(**(lifecycle or {}))
    if _should_block_entry_recovery_for_queue_only(out):
        cleared = _clear_fabricated_entry_lifecycle(out)
        return cleared, _entry_lifecycle_payload(
            execution_entry=None,
            execution_entry_source="none",
            execution_entry_status="non_executable",
            display_entry=None,
            display_entry_source="none",
            display_entry_status="missing",
            clear_reason=cleared.get("entry_clear_reason"),
            entry_reason=None,
        )
    if _safe_float(normalized.get("execution_entry")) is not None:
        return out, normalized
    if out.get("originated_missing_token"):
        return out, normalized
    try:
        recovery_enabled = bool(getattr(cfg, "EXECUTION_ENTRY_RECOVERY_ENABLE", True))
    except Exception:
        recovery_enabled = True
    if not recovery_enabled:
        return out, normalized
    if bool(out.get("unresolved_contract")):
        return out, normalized
    if _has_execution_recovery_blocker(out):
        return out, normalized
    quote_age_sec = _canonical_quote_age_sec(out)
    try:
        max_quote_age_sec = float(getattr(cfg, "OPTION_LTP_SLA_SEC", 2.0))
    except Exception:
        max_quote_age_sec = 2.0
    if quote_age_sec is not None and float(quote_age_sec) > float(max_quote_age_sec):
        return out, normalized
    recovered = None
    recovered_from = None
    for field in ("display_entry", "expected_entry", "entry_price", "current_ltp"):
        value = _safe_float(out.get(field))
        if value is not None and float(value) > 0:
            recovered = float(value)
            recovered_from = field
            break
    if recovered is None:
        return out, normalized
    normalized = _entry_lifecycle_payload(
        execution_entry=recovered,
        execution_entry_source="recovered_fallback",
        execution_entry_status="non_executable",
        display_entry=recovered,
        display_entry_source="recovered_fallback",
        display_entry_status="displayable",
        clear_reason=None,
        entry_reason=f"recovered_from_{recovered_from or 'fallback'}",
    )
    out["execution_entry"] = recovered
    out["execution_entry_source"] = "recovered_fallback"
    out["execution_entry_status"] = "non_executable"
    out["execution_allowed"] = False
    out["display_entry"] = recovered
    out["display_entry_source"] = "recovered_fallback"
    out["display_entry_status"] = "displayable"
    out["entry"] = recovered
    out["entry_source"] = out.get("entry_source") or "recovered_fallback"
    out["entry_status"] = "displayable"
    out["entry_recovered"] = True
    out["entry_recovered_from"] = recovered_from
    out["tradable"] = False
    out["eligible_for_execution"] = False
    out["execution_allowed"] = False
    out["execution_status"] = "advisory_only"
    out["candidate_status"] = "advisory_only"
    out["is_executable"] = False
    out["entry_clear_reason"] = None
    if str(out.get("entry_block_code") or "").strip().upper() == "MISSING_ENTRY":
        out["entry_block_code"] = None
    if str(out.get("hard_reason") or "").strip().upper() == "MISSING_ENTRY":
        out["hard_reason"] = None
    if str(out.get("final_blocker") or "").strip().upper() == "MISSING_ENTRY":
        out["final_blocker"] = None
    out["hard_blockers"] = [
        code for code in _dedupe_issue_codes(list(out.get("hard_blockers") or []))
        if code != "MISSING_ENTRY"
    ]
    out["blockers"] = [
        code for code in _dedupe_issue_codes(list(out.get("blockers") or []))
        if code != "MISSING_ENTRY"
    ]
    return out, normalized


def _last_chance_execution_entry_recovery(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    if _should_block_entry_recovery_for_queue_only(entry):
        return _clear_fabricated_entry_lifecycle(entry)
    if entry.get("originated_missing_token"):
        return entry
    if entry.get("unresolved_contract"):
        return entry
    out = dict(entry)
    if _safe_float(out.get("execution_entry")) is not None:
        return out
    if _has_execution_recovery_blocker(out):
        return out
    quote_validation_status = str(out.get("quote_validation_status") or "").strip().upper()
    if quote_validation_status in {"NO_LIVE_OPTION_FEED", "OFFHOURS_SYNTHETIC"}:
        return out
    recovered = None
    recovered_from = None
    for field in ("display_entry", "expected_entry", "entry_price", "current_ltp"):
        value = _safe_float(out.get(field))
        if value is not None and float(value) > 0:
            recovered = float(value)
            recovered_from = field
            break
    if recovered is None:
        return out
    out["execution_entry"] = recovered
    out["execution_entry_status"] = "non_executable"
    out["execution_entry_source"] = "recovered_fallback"
    out["entry_recovered"] = True
    out["tradable"] = False
    out["eligible_for_execution"] = False
    out["execution_allowed"] = False
    out["execution_status"] = "advisory_only"
    out["candidate_status"] = "advisory_only"
    out["is_executable"] = False
    out["entry_recovered_from"] = recovered_from
    if _safe_float(out.get("display_entry")) is None:
        out["display_entry"] = recovered
        out["display_entry_status"] = "displayable"
        out["display_entry_source"] = "recovered_fallback"
    out["hard_blockers"] = [
        code for code in list(out.get("hard_blockers") or [])
        if str(code or "").strip() != "MISSING_ENTRY"
    ]
    out["blockers"] = [
        code for code in list(out.get("blockers") or [])
        if str(code or "").strip() != "MISSING_ENTRY"
    ]
    append_execution_entry_trace(
        module="core.review_queue",
        stage="last_chance_execution_entry_recovery",
        row=out,
        execution_entry_before=entry.get("execution_entry"),
        execution_entry_after=out.get("execution_entry"),
        execution_entry_status_before=entry.get("execution_entry_status"),
        execution_entry_status_after=out.get("execution_entry_status"),
        extra={
            "execution_entry_source": out.get("execution_entry_source"),
            "display_entry": out.get("display_entry"),
            "display_entry_status": out.get("display_entry_status"),
            "entry_recovered": True,
            "entry_recovered_from": recovered_from,
        },
    )
    return out


def _apply_sizing_telemetry(entry: dict) -> dict:
    out = dict(entry)
    ml_proba = _safe_float(out.get("ml_proba_input"))
    ml_proba_source = str(out.get("ml_proba_source") or "").strip() or None
    if ml_proba is None:
        ml_proba = _safe_float(out.get("builder_confidence"))
        if ml_proba is not None:
            ml_proba_source = "builder_confidence"
    if ml_proba is None:
        ml_proba = _safe_float(out.get("confidence_raw"))
        if ml_proba is not None:
            ml_proba_source = "confidence_raw"
    if ml_proba is None:
        ml_proba = _safe_float(out.get("confidence"))
        if ml_proba is not None:
            ml_proba_source = "confidence"

    confluence = _safe_float(out.get("confluence_input"))
    confluence_source = str(out.get("confluence_source") or "").strip() or None
    if confluence is None:
        confluence = _safe_float(out.get("sizing_confluence_score"))
        if confluence is not None:
            confluence_source = "sizing_confluence_score"
    if confluence is None:
        detail = out.get("trade_score_detail") or {}
        if isinstance(detail, dict):
            confluence = _safe_float(detail.get("confluence_score"))
            if confluence is not None:
                confluence_source = "trade_score_detail.confluence_score"

    ok, conf_mult, reason = _POSITION_SIZER.confidence_multiplier(ml_proba, confluence)
    if out.get("sizing_reason") in (None, "", "None"):
        out["sizing_reason"] = str(reason)
    if out.get("sizing_confidence") is None:
        out["sizing_confidence"] = ml_proba
    out["ml_proba_input"] = ml_proba
    out["confluence_input"] = confluence
    out["ml_proba_source"] = ml_proba_source or ("unavailable" if ml_proba is None else "unknown")
    out["confluence_source"] = confluence_source or ("unavailable" if confluence is None else "unknown")
    existing_mult = _safe_float(out.get("confidence_size_multiplier"))
    out["confidence_size_multiplier"] = existing_mult if existing_mult is not None else float(conf_mult)
    if out.get("final_qty") in (None, "", "None"):
        qty = out.get("qty")
        try:
            out["final_qty"] = int(qty) if qty not in (None, "", "None") else None
        except Exception:
            out["final_qty"] = None
    return out


def _should_backfill_candidate_score(
    value: object,
    *,
    row: dict | None = None,
    field: str | None = None,
) -> bool:
    numeric = _safe_float(value)
    if numeric is None:
        return True
    if float(numeric) <= 0.0:
        return True
    if not isinstance(row, dict):
        return False
    if str(field or "").strip().lower() not in {"rank_score", "opportunity_score"}:
        return False
    source_flags = row.get("source_flags") if isinstance(row.get("source_flags"), dict) else {}
    candidate_origin = str(row.get("candidate_origin") or "").strip().lower()
    trade_id = str(row.get("trade_id") or "").strip().lower()
    seeded_soft_reject = (
        bool(source_flags.get("recoverable_soft_reject"))
        or candidate_origin in {"softened_builder_path", "softened"}
        or trade_id.startswith("tbsoft_")
    )
    if not seeded_soft_reject:
        return False
    min_rank = float(getattr(cfg, "PERMISSION_PROMOTION_MIN_RAW_RANK", 0.35) or 0.35)
    return float(numeric) < min_rank


def _is_seeded_soft_reject_artifact(entry: dict | None) -> bool:
    if not isinstance(entry, dict):
        return False
    source_flags = entry.get("source_flags") if isinstance(entry.get("source_flags"), dict) else {}
    candidate_origin = str(entry.get("candidate_origin") or "").strip().lower()
    trade_id = str(entry.get("trade_id") or "").strip().lower()
    return bool(source_flags.get("recoverable_soft_reject")) or candidate_origin in {"softened_builder_path", "softened"} or trade_id.startswith("tbsoft_")


def _apply_terminal_rank_truth(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    terminal_rank = _safe_float(out.get("terminal_rank_score"))
    if terminal_rank is None:
        terminal_rank = _safe_float((out.get("score_breakdown") or {}).get("rank_score"))
        if terminal_rank is not None:
            out["terminal_rank_score"] = terminal_rank
    terminal_opportunity = _safe_float(out.get("terminal_opportunity_score"))
    if terminal_opportunity is None:
        terminal_opportunity = _safe_float((out.get("score_breakdown") or {}).get("opportunity_score"))
        if terminal_opportunity is not None:
            out["terminal_opportunity_score"] = terminal_opportunity

    persisted_rank = _safe_float(out.get("rank_score"))
    persisted_opportunity = _safe_float(out.get("opportunity_score"))
    if not bool(out.get("terminal_scoring_applied")) or terminal_rank is None:
        if out.get("rank_truth_source") in (None, "", "None"):
            out["rank_truth_source"] = "persisted_rank"
        if out.get("rank_truth_action") in (None, "", "None"):
            out["rank_truth_action"] = "no_terminal_rank"
        return out

    if _is_seeded_soft_reject_artifact(out):
        out["rank_truth_source"] = "persisted_rank"
        out["rank_truth_action"] = "preserved_seeded_soft_reject_rank"
        return out

    terminal_is_differentiated = (
        persisted_rank is None
        or abs(float(terminal_rank) - float(persisted_rank)) > 1e-6
    )
    if terminal_is_differentiated:
        out["rank_score"] = round(float(terminal_rank), 6)
        if terminal_opportunity is not None:
            out["opportunity_score"] = round(float(terminal_opportunity), 6)
        out["rank_truth_source"] = "terminal_candidate_scoring"
        out["rank_truth_action"] = "promoted_terminal_rank"
        out["rank_truth_drift"] = {
            "persisted_rank_score": persisted_rank,
            "terminal_rank_score": round(float(terminal_rank), 6),
            "persisted_opportunity_score": persisted_opportunity,
            "terminal_opportunity_score": round(float(terminal_opportunity), 6) if terminal_opportunity is not None else None,
        }
    else:
        out["rank_truth_source"] = "persisted_rank"
        out["rank_truth_action"] = "terminal_rank_matches_persisted"
    return out


_CANDIDATE_STATUS_VALUES = {
    "scored",
    "ranked",
    "advisory_only",
    "near_executable",
    "blocked",
    "blocked_contract",
    "executable",
}


def _has_candidate_scoring_context(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    if any(
        _safe_float(entry.get(field)) is not None
        for field in (
            "builder_confidence",
            "confidence_raw",
            "confidence_final",
            "setup_strength",
            "regime_fit",
            "liquidity_score",
            "spread_score",
            "rr_score",
            "timing_score",
            "penalty_score",
        )
    ):
        return True
    return bool(entry.get("score_breakdown"))


def _has_candidate_ranking_context(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    if _safe_float(entry.get("rank_score")) is not None:
        return True
    if _safe_float(entry.get("opportunity_score")) is not None:
        return True
    return entry.get("opportunity_rank") not in (None, "", "None")


def _runtime_ranking_enabled() -> bool:
    try:
        return bool(getattr(cfg, "REVIEW_QUEUE_RUNTIME_RANKING_ENABLE", True))
    except Exception:
        return True


def _review_queue_ranking_scope(path: Path) -> str:
    name = str(getattr(path, "name", "") or "review_queue").strip() or "review_queue"
    return f"review_queue:{name}"


def _sync_runtime_rank_fields(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    decision_trace = dict(out.get("decision_trace") or {}) if isinstance(out.get("decision_trace"), dict) else {}
    decision_trace.update(
        {
            "rank_score": _safe_float(out.get("rank_score")),
            "opportunity_score": _safe_float(out.get("opportunity_score")),
            "edge_rank_score": _safe_float(out.get("edge_rank_score")),
            "expectancy_score": _safe_float(out.get("expectancy_score")),
            "expectancy_status": out.get("expectancy_status"),
            "expectancy_sample_count": out.get("expectancy_sample_count"),
            "expectancy_avg_cost_adjusted_r": _safe_float(out.get("expectancy_avg_cost_adjusted_r")),
            "opportunity_rank": out.get("opportunity_rank"),
            "rank_global": out.get("rank_global"),
            "rank_within_symbol": out.get("rank_within_symbol"),
            "opportunity_bucket": out.get("opportunity_bucket"),
            "selected_for_execution": bool(out.get("selected_for_execution", False)),
            "selection_reason": out.get("selection_reason"),
            "size_multiplier_reason": out.get("size_multiplier_reason"),
            "opportunity_size_multiplier": _safe_float(out.get("opportunity_size_multiplier")),
        }
    )
    out["decision_trace"] = decision_trace
    return out


def _ranked_queue_row_sort_key(row: dict) -> tuple[int, int, float, float, str, str]:
    if not isinstance(row, dict):
        return (1, 10**9, 1.0, 1.0, "", "")
    rank_global = row.get("rank_global")
    try:
        rank_value = int(rank_global) if rank_global not in (None, "", "None") else 10**9
    except Exception:
        rank_value = 10**9
    rank_score = _safe_float(row.get("rank_score"))
    opportunity_score = _safe_float(row.get("opportunity_score"))
    return (
        0 if rank_value != 10**9 else 1,
        rank_value,
        -float(rank_score if rank_score is not None else -1.0),
        -float(opportunity_score if opportunity_score is not None else -1.0),
        str(row.get("symbol") or ""),
        str(row.get("trade_id") or row.get("trade_key") or ""),
    )


def _rank_review_queue_rows(rows: list[dict], *, path: Path) -> list[dict]:
    candidate_rows = [dict(row) for row in list(rows or []) if isinstance(row, dict)]
    if not candidate_rows:
        return []
    if not _runtime_ranking_enabled():
        return candidate_rows
    ranked_rows = annotate_ranked_opportunities(
        candidate_rows,
        scope=_review_queue_ranking_scope(path),
    )
    out: list[dict] = []
    for row in ranked_rows:
        ranked_row = dict(row) if isinstance(row, dict) else {}
        ranked_row = _sync_runtime_rank_fields(ranked_row)
        ranked_row = _classify_candidate_status(ranked_row)
        out.append(ranked_row)
    out.sort(key=_ranked_queue_row_sort_key)
    return out


def _find_ranked_queue_entry(rows: list[dict], entry: dict) -> dict:
    trade_key = str(entry.get("trade_key") or "").strip()
    trade_id = str(entry.get("trade_id") or "").strip()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if trade_key and str(row.get("trade_key") or "").strip() == trade_key:
            return row
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if trade_id and str(row.get("trade_id") or "").strip() == trade_id:
            return row
    return entry


def _candidate_funnel_counts(rows: list[dict]) -> dict[str, int]:
    counts = {
        "candidates_generated": 0,
        "candidates_scored": 0,
        "candidates_ranked": 0,
        "candidates_executable": 0,
        "candidates_advisory_only": 0,
        "candidates_blocked_contract": 0,
    }
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        counts["candidates_generated"] += 1
        if _has_candidate_scoring_context(row):
            counts["candidates_scored"] += 1
        if (
            _has_candidate_ranking_context(row)
            or row.get("rank_global") not in (None, "", "None")
            or row.get("rank_within_symbol") not in (None, "", "None")
        ):
            counts["candidates_ranked"] += 1
        status = str(_classify_candidate_status(row).get("candidate_status") or "").strip().lower()
        if status == "executable":
            counts["candidates_executable"] += 1
        elif status == "advisory_only":
            counts["candidates_advisory_only"] += 1
        elif status == "blocked_contract":
            counts["candidates_blocked_contract"] += 1
    return counts


def _candidate_visibility_counts(rows: list[dict]) -> dict[str, int]:
    counts = {
        "visible_suggestion_count": 0,
        "visible_advisory_count": 0,
        "visible_queue_only_count": 0,
        "visible_executable_count": 0,
    }
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if row.get("advisory_visible") is False:
            continue
        counts["visible_suggestion_count"] += 1
        execution_status = str(row.get("execution_status") or "").strip().lower()
        final_action = str(row.get("final_action") or "").strip().upper()
        readiness = str(row.get("readiness") or "").strip().upper()
        execution_allowed = bool(row.get("execution_allowed"))
        if execution_status == "executable" or (
            execution_allowed and (final_action == "EXECUTE" or readiness == "READY")
        ):
            counts["visible_executable_count"] += 1
        elif execution_status == "queue_only" or final_action == "QUEUE_ONLY" or readiness == "QUEUE_ONLY":
            counts["visible_queue_only_count"] += 1
        else:
            counts["visible_advisory_count"] += 1
    return counts


def _apply_candidate_scoring_status(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    existing = str(out.get("candidate_status") or "").strip().lower()
    if existing in {"blocked_contract", "advisory_only", "executable"}:
        return out
    if _has_candidate_ranking_context(out):
        out["candidate_status"] = "ranked"
    elif _has_candidate_scoring_context(out):
        out["candidate_status"] = "scored"
    return out


def _preserve_blocked_candidate_metadata(
    entry: dict,
    *,
    reason: str | None = None,
    terminal: bool = False,
) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    mode_for_entry = _entry_execution_mode(out)
    allow_stale_quotes_for_entry = _allow_rest_fallback_for_mode(mode_for_entry)
    market_open_for_entry, _market_open_source = _resolve_entry_market_open(
        out,
        mode_for_entry,
        allow_stale_quotes_for_entry,
    )
    if terminal:
        out = _apply_terminal_candidate_scoring(
            out,
            mode_for_entry=mode_for_entry,
            allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
            market_open_for_entry=market_open_for_entry,
        )
    elif not (_has_candidate_scoring_context(out) or _has_candidate_ranking_context(out)):
        out = _apply_candidate_scoring(
            out,
            mode_for_entry=mode_for_entry,
            allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
            market_open_for_entry=market_open_for_entry,
        )
    reason_probe = dict(out)
    if reason:
        reason_probe["reason"] = reason
    block_reason = _best_reject_reason(reason_probe, default="execution_blocked")
    out["execution_blocked"] = True
    out["execution_block_reason"] = block_reason
    return out


def _classify_candidate_status(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = _apply_fallback_execution_kill(entry)
    if _is_blocked_contract_row(out):
        out["candidate_status"] = "blocked_contract"
        out["eligible_for_execution"] = False
        out["execution_allowed"] = False
        out["is_executable"] = False
        return out
    execution_entry_status = str(out.get("execution_entry_status") or "").strip().lower()
    if _is_softened_candidate_origin(out) and execution_entry_status != "executable":
        out["candidate_status"] = "advisory_only"
        out["eligible_for_execution"] = False
        out["execution_allowed"] = False
        out["is_executable"] = False
        return out
    execution_source = str(out.get("execution_entry_source") or "").strip().lower()
    if execution_source in {"recovered_fallback", "rest_fallback", "synthetic_offhours"}:
        out["candidate_status"] = "advisory_only"
        out["eligible_for_execution"] = False
        out["execution_allowed"] = False
        out["is_executable"] = False
        return out
    existing = str(out.get("candidate_status") or "").strip().lower()
    if existing not in _CANDIDATE_STATUS_VALUES:
        out = _apply_candidate_scoring_status(out)
        existing = str(out.get("candidate_status") or "").strip().lower()
    execution_status = str(out.get("execution_status") or "").strip().lower()
    permission = str(out.get("permission") or "").strip().upper()
    final_action = str(out.get("final_action") or "").strip().upper()
    readiness = str(out.get("readiness") or "").strip().upper()
    execution_entry = _safe_float(out.get("execution_entry"))
    eligible_for_execution = bool(out.get("eligible_for_execution", out.get("execution_allowed", False)))
    unresolved_contract = bool(out.get("unresolved_contract"))
    if not unresolved_contract and _requires_option_contract_identity(out):
        try:
            unresolved_contract = _is_unresolved_option_contract(out)
        except Exception:
            unresolved_contract = False
    if (
        execution_status == "executable"
        and permission == "EXECUTE"
        and final_action == "EXECUTE"
        and readiness == "READY"
        and _safe_float(out.get("execution_entry")) is not None
        and str(out.get("execution_entry_status") or "").strip().lower() == "executable"
    ):
        out["candidate_status"] = "executable"
        return out
    if execution_status == "blocked" or permission == "BLOCK" or final_action == "BLOCK" or readiness == "BLOCKED":
        out["candidate_status"] = "blocked"
        out["eligible_for_execution"] = False
        out["execution_allowed"] = False
        out["is_executable"] = False
        return out
    if (
        execution_status == "queue_only"
        or permission == "QUEUE_ONLY"
        or final_action == "QUEUE_ONLY"
        or readiness == "QUEUE_ONLY"
    ):
        if (
            (_has_candidate_ranking_context(out) or _has_candidate_scoring_context(out))
            and execution_entry is not None
            and execution_entry_status == "executable"
            and eligible_for_execution
            and not bool(out.get("execution_blocked"))
            and not unresolved_contract
            and not bool(out.get("hard_blockers"))
            and not bool(out.get("blockers"))
        ):
            out["candidate_status"] = "near_executable"
            return out
    if _has_candidate_ranking_context(out) or _has_candidate_scoring_context(out):
        if (
            execution_status in {"blocked", "advisory_only", "queue_only"}
            or permission in {"BLOCK", "ADVISORY_ONLY", "QUEUE_ONLY"}
            or final_action in {"BLOCK", "ADVISORY_ONLY", "QUEUE_ONLY"}
            or readiness in {"BLOCKED", "ADVISORY_ONLY", "QUEUE_ONLY"}
            or bool(out.get("hard_blockers"))
            or bool(out.get("blockers"))
            or bool(out.get("approval_blocked"))
            or bool(out.get("unresolved_contract"))
        ):
            out["candidate_status"] = "advisory_only"
            out["eligible_for_execution"] = False
            out["execution_allowed"] = False
            out["is_executable"] = False
            return out
    if existing in _CANDIDATE_STATUS_VALUES:
        return out
    candidate_class = str(out.get("candidate_class") or "").strip().upper()
    if candidate_class == "EXECUTABLE":
        out["candidate_status"] = "executable"
        return out
    if candidate_class == "NEAR_EXECUTABLE":
        out["candidate_status"] = "near_executable"
        return out
    if candidate_class == "ADVISORY_ONLY":
        out["candidate_status"] = "advisory_only"
        return out
    if _has_candidate_ranking_context(out):
        out["candidate_status"] = "ranked"
    elif _has_candidate_scoring_context(out):
        out["candidate_status"] = "scored"
    else:
        out["candidate_status"] = "scored"
    return out


def _apply_candidate_scoring(
    entry: dict,
    *,
    mode_for_entry: str,
    allow_stale_quotes_for_entry: bool,
    market_open_for_entry: bool,
) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    out = _apply_session_isolation(out)
    if _is_synthetic_advisory_entry(out):
        out = _mark_synthetic_advisory_entry(out, emit_log=True)
    else:
        if not out.get("strategy_family"):
            out["strategy_family"] = str(getattr(cfg, "REVIEW_QUEUE_STRATEGY_FAMILY_FALLBACK", "breakout") or "breakout").strip().lower() or "breakout"
        if not out.get("candidate_type"):
            out["candidate_type"] = "fallback_directional"
    market_data, context = _candidate_scoring_inputs(
        out,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
        market_open_for_entry=market_open_for_entry,
    )
    scored = score_candidate(out, market_data, context)

    for field in (
        "setup_strength",
        "regime_fit",
        "liquidity_score",
        "spread_score",
        "rr_score",
        "timing_score",
        "penalty_score",
    ):
        out[field] = _safe_float(scored.get(field))

    out["score_breakdown"] = dict(scored.get("score_breakdown") or {})
    out["penalty_reasons"] = list(scored.get("penalty_reasons") or [])
    out["score_inputs_used"] = dict(scored.get("score_inputs_used") or {})

    confluence_score = _safe_float(scored.get("confluence_score"))
    if _should_backfill_candidate_score(out.get("sizing_confluence_score")) and confluence_score is not None:
        out["sizing_confluence_score"] = confluence_score
    if out.get("confluence_source") in (None, "", "None") and confluence_score is not None:
        out["confluence_source"] = "candidate_scoring"

    confidence_raw = _safe_float(scored.get("confidence_raw"))
    confidence_final = _safe_float(scored.get("confidence_final"))
    if _should_backfill_candidate_score(out.get("builder_confidence")):
        out["builder_confidence"] = (
            _safe_float(scored.get("confidence_after_soft_veto"))
            or confidence_final
            or confidence_raw
        )
    if _should_backfill_candidate_score(out.get("confidence_base")) and confidence_raw is not None:
        out["confidence_base"] = confidence_raw
    if _should_backfill_candidate_score(out.get("gating_base_confidence")) and confidence_raw is not None:
        out["gating_base_confidence"] = confidence_raw
    if _should_backfill_candidate_score(out.get("raw_signal_confidence")) and confidence_final is not None:
        out["raw_signal_confidence"] = confidence_final
    if _should_backfill_candidate_score(out.get("confidence")) and confidence_final is not None:
        out["confidence"] = confidence_final
    if _should_backfill_candidate_score(out.get("global_confidence")) and confidence_final is not None:
        out["global_confidence"] = confidence_final
    if _should_backfill_candidate_score(out.get("permission_confidence")) and confidence_final is not None:
        out["permission_confidence"] = confidence_final

    rank_score = _safe_float(scored.get("rank_score"))
    assert rank_score is not None, "SCORING NOT APPLIED IN REVIEW_QUEUE"
    if _should_backfill_candidate_score(
        out.get("rank_score"),
        row=out,
        field="rank_score",
    ) and rank_score is not None:
        out["rank_score"] = rank_score
    opportunity_score = _safe_float(scored.get("opportunity_score"))
    if _should_backfill_candidate_score(
        out.get("opportunity_score"),
        row=out,
        field="opportunity_score",
    ) and opportunity_score is not None:
        out["opportunity_score"] = opportunity_score

    out = _capture_score_integrity(out)
    return _apply_candidate_scoring_status(out)


def _candidate_scoring_inputs(
    entry: dict,
    *,
    mode_for_entry: str,
    allow_stale_quotes_for_entry: bool,
    market_open_for_entry: bool,
) -> tuple[dict, dict]:
    market_data = {
        "regime": entry.get("regime"),
        "day_type": entry.get("day_type"),
        "market_open": market_open_for_entry,
        "quote_source": entry.get("option_ltp_source") or entry.get("quote_source"),
        "quote_age_sec": _canonical_quote_age_sec(entry),
        "current_ltp": _safe_float(entry.get("current_ltp")),
        "reference_price": _safe_float(entry.get("validation_reference_price") or entry.get("entry_price") or entry.get("expected_entry")),
        "spread_pct": _quote_spread_pct(entry),
        "best_bid": _safe_float(entry.get("best_bid") or entry.get("bid") or entry.get("opt_bid")),
        "best_ask": _safe_float(entry.get("best_ask") or entry.get("ask") or entry.get("opt_ask")),
        "volume": _safe_float(entry.get("volume") or entry.get("current_volume") or entry.get("tick_volume")),
        "oi": _safe_float(entry.get("oi")),
    }
    context = {
        "mode": mode_for_entry,
        "allow_stale_quotes": allow_stale_quotes_for_entry,
        "market_open": market_open_for_entry,
        "permission": entry.get("permission"),
        "readiness": entry.get("readiness"),
        "final_action": entry.get("final_action"),
        "execution_status": entry.get("execution_status"),
        "quote_source": entry.get("option_ltp_source") or entry.get("quote_source"),
        "blockers": list(entry.get("blockers") or []),
        "hard_blockers": list(entry.get("hard_blockers") or []),
        "soft_penalties": list(entry.get("soft_penalties") or []),
        "warnings": list(entry.get("warnings") or []),
    }
    return market_data, context


def _capture_score_integrity(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)

    raw_rank = _safe_float(out.get("raw_rank_score"))
    if raw_rank is None:
        raw_rank = _safe_float(out.get("rank_score"))
        if raw_rank is not None:
            out["raw_rank_score"] = raw_rank

    raw_opp = _safe_float(out.get("raw_opportunity_score"))
    if raw_opp is None:
        raw_opp = _safe_float(out.get("opportunity_score"))
        if raw_opp is not None:
            out["raw_opportunity_score"] = raw_opp

    final_rank = _safe_float(out.get("rank_score"))
    if raw_rank is not None and final_rank is not None:
        out["score_inflation_ratio"] = round(float(final_rank) / max(float(raw_rank), 1e-6), 6)
        if float(final_rank) > float(raw_rank) * 1.5:
            logger.warning(
                "score_inflation_detected trade_id=%s symbol=%s raw_rank=%s final_rank=%s ratio=%s",
                out.get("trade_id"),
                out.get("symbol"),
                raw_rank,
                final_rank,
                out.get("score_inflation_ratio"),
            )
    return out


def _apply_terminal_candidate_scoring(
    entry: dict,
    *,
    mode_for_entry: str,
    allow_stale_quotes_for_entry: bool,
    market_open_for_entry: bool,
) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    if bool(out.get("terminal_scoring_applied")):
        return out
    if _is_synthetic_advisory_entry(out):
        out = _mark_synthetic_advisory_entry(out, emit_log=True)
        synthetic_confidence = _safe_float(out.get("confidence_final"))
        if synthetic_confidence is None:
            synthetic_confidence = _safe_float(out.get("gating_final_confidence"))
        if synthetic_confidence is None:
            synthetic_confidence = _safe_float(out.get("confidence"))
        if synthetic_confidence is None:
            synthetic_confidence = float(getattr(cfg, "PHASE2_MIN_BORDERLINE_SCORE", 0.12) or 0.12)
        out["confidence"] = synthetic_confidence
        out["rank_score"] = synthetic_confidence
        out["confidence_final"] = synthetic_confidence
        out["gating_final_confidence"] = synthetic_confidence
        out["terminal_rank_score"] = _safe_float(out.get("rank_score"))
        out["terminal_opportunity_score"] = _safe_float(out.get("opportunity_score"))
        out["terminal_scoring_applied"] = True
        out = _capture_score_integrity(out)
        return _apply_candidate_scoring_status(out)
    out = _apply_candidate_scoring(
        out,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
        market_open_for_entry=market_open_for_entry,
    )
    market_data, context = _candidate_scoring_inputs(
        out,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
        market_open_for_entry=market_open_for_entry,
    )
    if not out.get("strategy_family"):
        out["strategy_family"] = str(getattr(cfg, "REVIEW_QUEUE_STRATEGY_FAMILY_FALLBACK", "breakout") or "breakout").strip().lower() or "breakout"
    if not out.get("candidate_type"):
        out["candidate_type"] = "fallback_directional"
    scored = score_candidate(out, market_data, context)
    raw_rank = _safe_float(out.get("raw_rank_score"))
    existing_rank = _safe_float(out.get("rank_score"))
    scored_rank = _safe_float(scored.get("rank_score"))
    if raw_rank is None:
        raw_rank = existing_rank
    if raw_rank is not None and _safe_float(out.get("raw_rank_score")) is None:
        out["raw_rank_score"] = float(raw_rank)
    final_rank = scored_rank
    if raw_rank is not None and scored_rank is not None:
        final_rank = min(float(scored_rank), float(raw_rank))
    out["rank_score"] = _safe_float(final_rank)
    assert out.get("rank_score") is not None, "SCORING NOT APPLIED IN REVIEW_QUEUE"
    out["terminal_rank_score"] = _safe_float(final_rank)
    out["opportunity_score"] = _safe_float(scored.get("opportunity_score"))
    out["terminal_opportunity_score"] = _safe_float(scored.get("opportunity_score"))
    out["confidence_raw"] = _safe_float(scored.get("confidence_raw"))
    out["confidence_final"] = _safe_float(scored.get("confidence_final"))
    if out.get("confidence_final") is not None:
        out["confidence"] = out.get("confidence_final")
    out["score_breakdown"] = dict(scored.get("score_breakdown") or {})
    out["penalty_reasons"] = list(scored.get("penalty_reasons") or [])
    out["score_inputs_used"] = dict(scored.get("score_inputs_used") or {})
    print(
        "SCORING_DEBUG",
        {
            "symbol": out.get("symbol"),
            "rank_score": out.get("rank_score"),
            "confidence": out.get("confidence_final"),
            "strategy_family": out.get("strategy_family"),
        },
    )
    if bool(getattr(cfg, "CANDIDATE_SCORING_TRACE_ENABLE", False)):
        print(
            "TRACE_FINAL_CANDIDATE_SCORING",
            out.get("trade_id"),
            out.get("rank_score"),
            out.get("confidence_final"),
        )
    if bool(getattr(cfg, "CANDIDATE_SCORING_ASSERT_ENABLE", False)):
        assert "rank_score" in out
    out["terminal_scoring_applied"] = True
    out = _capture_score_integrity(out)
    return _apply_candidate_scoring_status(out)


def _ensure_blocked_advisory_hard_blockers(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    readiness = str(out.get("readiness") or "").strip().upper()
    execution_status = str(out.get("execution_status") or "").strip().lower()
    final_action = str(out.get("final_action") or "").strip().upper()
    permission = str(out.get("permission") or "").strip().upper()
    candidate_status = str(out.get("candidate_status") or "").strip().lower()
    if not (
        readiness == "BLOCKED"
        or execution_status == "blocked"
        or final_action == "BLOCK"
        or permission == "BLOCK"
        or candidate_status == "blocked"
    ):
        return out
    hard_blockers = _dedupe_issue_codes(list(out.get("hard_blockers") or []))
    blockers = _dedupe_issue_codes(list(out.get("blockers") or []))
    fallback_codes = _dedupe_issue_codes(
        [
            out.get("final_emit_block_reason"),
            out.get("final_blocker"),
            out.get("execution_block_reason"),
            out.get("hard_reason"),
            out.get("entry_block_code"),
            out.get("entry_block_reason"),
            out.get("permission_reason"),
            *list(out.get("blockers") or []),
            *list(out.get("soft_penalties") or []),
            *list(out.get("warnings") or []),
            _best_reject_reason(out, default="blocked"),
            _execution_ineligibility_reason(out, default="blocked"),
        ]
    )
    benign_codes = {
        "OK",
        "READY",
        "QUEUE_ONLY",
        "ADVISORY_ONLY",
        "EXECUTE",
        "NO_EXECUTION_CANDIDATES",
        "UNSPECIFIED_TRADE_BUILDER_REJECT",
        "UNKNOWN",
        "NONE",
        "NULL",
        "N/A",
        "NA",
    }
    for code in fallback_codes:
        if not code:
            continue
        normalized = str(code).strip()
        if not normalized or normalized.upper() in benign_codes:
            continue
        if normalized in TARGET_BLOCKER_CODES or normalized.startswith("HARD_") or normalized not in hard_blockers:
            hard_blockers.append(normalized)
    if not hard_blockers:
        hard_blockers = ["BLOCKED"]
    if not blockers:
        blockers = list(hard_blockers)
    else:
        blockers = _dedupe_issue_codes(blockers + hard_blockers)
    out["hard_blockers"] = hard_blockers
    out["blockers"] = blockers
    if not out.get("entry_block_code"):
        out["entry_block_code"] = hard_blockers[0]
    if not out.get("entry_clear_reason"):
        out["entry_clear_reason"] = hard_blockers[0]
    if not out.get("final_blocker"):
        out["final_blocker"] = hard_blockers[0]
    if not out.get("hard_reason"):
        out["hard_reason"] = hard_blockers[0]
    if readiness == "BLOCKED" and not out.get("execution_status"):
        out["execution_status"] = "blocked"
    return out


def _finalize_append_payload_for_runtime_write(
    payload: dict,
    *,
    require_terminal_scoring: bool = True,
    require_ranked_candidate_ready: bool = True,
) -> dict:
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    out = _apply_timestamp_contract_for_payload(out)
    display_ts_ist = out.get("display_ts_ist")
    if isinstance(display_ts_ist, str) and "T" in display_ts_ist:
        out["display_ts_ist"] = None
    if not out.get("display_ts_ist") and out.get("display_ts_epoch") is not None:
        formatted = format_ts_ist(out.get("display_ts_epoch"))
        if formatted:
            out["display_ts_ist"] = formatted
    if _is_synthetic_advisory_entry(out):
        out = _mark_synthetic_advisory_entry(out, emit_log=True)
        synthetic_confidence = _safe_float(out.get("confidence_final"))
        if synthetic_confidence is None:
            synthetic_confidence = _safe_float(out.get("gating_final_confidence"))
        if synthetic_confidence is None:
            synthetic_confidence = _safe_float(out.get("confidence"))
        if synthetic_confidence is None:
            synthetic_confidence = float(getattr(cfg, "PHASE2_MIN_BORDERLINE_SCORE", 0.12) or 0.12)
        out["confidence"] = synthetic_confidence
        out["rank_score"] = synthetic_confidence
        out["confidence_final"] = synthetic_confidence
        out["gating_final_confidence"] = synthetic_confidence
        out["terminal_rank_score"] = _safe_float(out.get("rank_score"))
        out["terminal_opportunity_score"] = _safe_float(out.get("opportunity_score"))
        out["terminal_scoring_applied"] = True
    else:
        strategy_family = str(out.get("strategy_family") or "").strip().lower()
        candidate_type = str(out.get("candidate_type") or "").strip().lower()
        if not strategy_family or strategy_family == "unknown":
            out["strategy_family"] = "forced"
        if not candidate_type or candidate_type == "unknown":
            out["candidate_type"] = "forced"
    out = _apply_fallback_execution_kill(out)
    out = _normalize_truth_quality(out)
    if require_terminal_scoring:
        assert bool(out.get("terminal_scoring_applied")), "terminal scoring not applied at emit"
    if require_ranked_candidate_ready:
        assert_ranked_candidate_ready(out)
    return out


def _synchronize_final_confidence(entry: dict) -> dict:
    out = dict(entry)
    final_confidence = _safe_float(out.get("gating_final_confidence"))
    if final_confidence is None:
        final_confidence = _safe_float(out.get("confidence_final"))
    if final_confidence is None:
        return out
    out["gating_final_confidence"] = final_confidence
    out["confidence_final"] = final_confidence
    out["confidence"] = final_confidence
    return out


_DECISION_PARITY_FIELDS = (
    "permission",
    "permission_reason",
    "readiness",
    "final_action",
    "execution_status",
    "execution_entry",
    "execution_entry_status",
    "display_entry",
    "display_entry_status",
    "entry_status",
    "blockers",
    "hard_blockers",
    "soft_penalties",
    "warnings",
)


def _decision_fields_snapshot(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return {}
    return {field: entry.get(field) for field in _DECISION_PARITY_FIELDS}


def _decision_fields_present(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    for field in ("permission", "readiness", "final_action", "execution_status"):
        if str(entry.get(field) or "").strip():
            return True
    return False


def _record_decision_parity(entry: dict, before: dict) -> dict:
    if not isinstance(entry, dict) or not isinstance(before, dict):
        return entry
    if not any(value is not None for value in before.values()):
        return entry
    diffs: dict[str, dict] = {}
    for field in _DECISION_PARITY_FIELDS:
        if before.get(field) != entry.get(field):
            diffs[field] = {"before": before.get(field), "after": entry.get(field)}
    entry["decision_parity"] = {"ok": not bool(diffs), "diffs": diffs}
    if diffs:
        logger.warning(
            "review_queue_decision_parity_mismatch trade_id=%s symbol=%s fields=%s",
            entry.get("trade_id"),
            entry.get("symbol"),
            ",".join(sorted(diffs.keys())),
        )
    return entry


def _emit_trade_lifecycle_event(
    entry: dict,
    *,
    stage: str,
    status: str,
    reason: str | None,
    extra: dict | None = None,
) -> None:
    if not isinstance(entry, dict):
        return
    try:
        append_trade_lifecycle_event(
            trade_id=str(entry.get("trade_id") or ""),
            symbol=str(entry.get("symbol") or ""),
            strategy=str(entry.get("strategy") or entry.get("strategy_id") or ""),
            stage=stage,
            status=status,
            reason=reason,
            extra=extra,
        )
    except Exception:
        return


def _normalize_quote_age_value(value) -> float | None:
    age = _safe_float(value)
    if age is None:
        return None
    if age < 0.0:
        return None
    if float(age) >= _STALE_QUOTE_AGE_SENTINEL:
        return None
    return float(age)


def _canonical_quote_age_sec(entry: dict) -> float | None:
    if not isinstance(entry, dict):
        return None
    for field in ("quote_age_sec", "option_age_sec", "price_age_sec", "option_ltp_age_sec"):
        age = _normalize_quote_age_value(entry.get(field))
        if age is not None:
            return age
    return None


def _quote_truth_snapshot_from_entry(
    entry: dict,
    *,
    source: str | None = None,
    now_epoch: float | None = None,
) -> dict:
    if not isinstance(entry, dict):
        return {}

    out: dict = {}
    source_flags = entry.get("source_flags") or {}
    if isinstance(source_flags, dict):
        nested = source_flags.get("quote_truth") or source_flags.get("quote_truth_snapshot")
        if isinstance(nested, dict):
            out.update(dict(nested))

    def _first_present(*values):
        for value in values:
            if value in (None, "", "None"):
                continue
            return value
        return None

    for field, aliases in (
        ("quote_snapshot_id", ("quote_snapshot_id",)),
        ("quote_ts_epoch", ("quote_ts_epoch", "option_ltp_timestamp", "ltp_ts_epoch", "quote_timestamp_epoch", "timestamp_epoch", "ts_epoch")),
        ("quote_age_sec", ("quote_age_sec", "option_age_sec", "price_age_sec", "option_ltp_age_sec")),
        ("best_bid", ("best_bid", "bid", "opt_bid")),
        ("best_ask", ("best_ask", "ask", "opt_ask")),
        ("current_ltp", ("current_ltp", "opt_ltp", "ltp", "last_price")),
        ("option_ltp_source", ("option_ltp_source",)),
        ("quote_source", ("quote_source",)),
        ("quote_validation_status", ("quote_validation_status", "entry_status")),
        ("execution_entry", ("execution_entry",)),
        ("execution_entry_status", ("execution_entry_status",)),
    ):
        if out.get(field) in (None, "", "None"):
            out[field] = _first_present(*(entry.get(alias) for alias in aliases))

    quote_ts_epoch = _coerce_ts_epoch_seconds(out.get("quote_ts_epoch"))
    if quote_ts_epoch is None:
        quote_ts_epoch = _coerce_ts_epoch_seconds(
            _first_present(
                entry.get("option_ltp_timestamp"),
                entry.get("ltp_ts_epoch"),
                entry.get("quote_timestamp_epoch"),
                entry.get("timestamp_epoch"),
                entry.get("ts_epoch"),
            )
        )
    quote_age_sec = _normalize_quote_age_value(out.get("quote_age_sec"))
    if quote_age_sec is None:
        quote_age_sec = _normalize_quote_age_value(
            _first_present(
                entry.get("quote_age_sec"),
                entry.get("option_age_sec"),
                entry.get("price_age_sec"),
                entry.get("option_ltp_age_sec"),
            )
        )
    if quote_ts_epoch is None and quote_age_sec is not None and now_epoch is not None:
        quote_ts_epoch = max(0.0, float(now_epoch) - float(quote_age_sec))
    if quote_age_sec is None and quote_ts_epoch is not None and now_epoch is not None:
        quote_age_sec = max(0.0, float(now_epoch) - float(quote_ts_epoch))
    if quote_ts_epoch is not None:
        out["quote_ts_epoch"] = float(quote_ts_epoch)
    if quote_age_sec is not None:
        out["quote_age_sec"] = float(quote_age_sec)

    max_quote_age_sec = _safe_float(getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8.0))
    if max_quote_age_sec is None or max_quote_age_sec <= 0:
        max_quote_age_sec = 8.0
    current_ltp = _safe_float(out.get("current_ltp"))
    best_bid = _safe_float(out.get("best_bid"))
    best_ask = _safe_float(out.get("best_ask"))
    quote_validation_status = resolve_quote_validation_status(
        existing_status=out.get("quote_validation_status"),
        current_ltp=current_ltp,
        quote_age_sec=quote_age_sec,
        best_bid=best_bid,
        best_ask=best_ask,
        max_quote_age_sec=max_quote_age_sec,
    )
    out["quote_validation_status"] = quote_validation_status
    consistency_score = quote_consistency_score(
        current_ltp=current_ltp,
        best_bid=best_bid,
        best_ask=best_ask,
    )
    if consistency_score is not None:
        out["quote_consistency_score"] = round(float(consistency_score), 6)

    if out.get("quote_snapshot_id") in (None, "", "None"):
        trade_id = str(_first_present(entry.get("trade_id"), out.get("trade_id")) or "")
        symbol = str(_first_present(entry.get("symbol"), out.get("symbol")) or "")
        out["quote_snapshot_id"] = (
            f"{trade_id}|{symbol}|{out.get('quote_ts_epoch') if out.get('quote_ts_epoch') is not None else 'na'}|"
            f"{out.get('quote_source') or 'unknown'}|{out.get('current_ltp') if out.get('current_ltp') is not None else 'na'}|"
            f"{out.get('best_bid') if out.get('best_bid') is not None else 'na'}|{out.get('best_ask') if out.get('best_ask') is not None else 'na'}"
        )

    if source:
        out["quote_truth_source"] = source
    return {key: value for key, value in out.items() if value not in (None, "", "None")}


def _quote_truth_is_stale(snapshot: dict, *, now_epoch: float | None = None) -> bool:
    if not isinstance(snapshot, dict) or not snapshot:
        return True
    status = str(snapshot.get("quote_validation_status") or "").strip().upper()
    if status in {"STALE_OPTION_LTP", "NO_LIVE_OPTION_FEED", "MISSING_OPTION_TOKEN"}:
        return True
    age = _normalize_quote_age_value(snapshot.get("quote_age_sec"))
    if age is None:
        return True
    max_age = float(getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8.0) or 8.0)
    if age > max_age:
        return True
    ts_epoch = _coerce_ts_epoch_seconds(snapshot.get("quote_ts_epoch"))
    if ts_epoch is None and now_epoch is not None:
        ts_epoch = max(0.0, float(now_epoch) - float(age))
    if ts_epoch is None:
        return True
    return False


def _merge_quote_truth(
    entry: dict,
    *,
    builder_truth: dict | None,
    queue_truth: dict | None,
    now_epoch: float | None = None,
) -> tuple[dict, str, dict]:
    if not isinstance(entry, dict):
        return entry, "preserved_builder", {}
    out = dict(entry)
    builder = _quote_truth_snapshot_from_entry(builder_truth or {}, source="builder", now_epoch=now_epoch)
    queue = _quote_truth_snapshot_from_entry(queue_truth or {}, source="queue", now_epoch=now_epoch)
    builder_ts = _coerce_ts_epoch_seconds(builder.get("quote_ts_epoch"))
    queue_ts = _coerce_ts_epoch_seconds(queue.get("quote_ts_epoch"))
    builder_stale = _quote_truth_is_stale(builder, now_epoch=now_epoch)
    queue_stale = _quote_truth_is_stale(queue, now_epoch=now_epoch)
    builder_has_quote_truth = any(
        builder.get(field) not in (None, "", "None")
        for field in ("current_ltp", "best_bid", "best_ask", "quote_ts_epoch", "quote_validation_status")
    )
    should_update_from_queue = bool(
        queue
        and (
            not builder
            or not builder_has_quote_truth
            or (
                not queue_stale
                and (
                    builder_stale
                    or builder_ts is None
                    or queue_ts is None
                    or queue_ts > builder_ts
                )
            )
        )
    )
    action = "updated_from_queue" if should_update_from_queue else "preserved_builder"
    chosen = queue if should_update_from_queue else builder
    if not chosen:
        chosen = {}
    canonical_fields = (
        "quote_snapshot_id",
        "quote_ts_epoch",
        "quote_age_sec",
        "best_bid",
        "best_ask",
        "current_ltp",
        "option_ltp_source",
        "quote_source",
        "quote_validation_status",
        "quote_consistency_score",
        "execution_entry",
        "execution_entry_status",
    )
    for field in canonical_fields:
        chosen_value = chosen.get(field)
        if chosen_value not in (None, "", "None"):
            out[field] = chosen_value
        elif field in builder and field not in out:
            out[field] = builder.get(field)
    source_flags = dict(out.get("source_flags") or {})
    source_flags["quote_truth"] = {field: out.get(field) for field in canonical_fields if out.get(field) not in (None, "", "None")}
    source_flags["quote_truth_snapshot"] = dict(source_flags["quote_truth"])
    out["source_flags"] = source_flags
    drift_payload = {
        "trade_id": out.get("trade_id"),
        "symbol": out.get("symbol"),
        "builder_quote_ts": builder.get("quote_ts_epoch"),
        "queue_quote_ts": queue.get("quote_ts_epoch"),
        "builder_quote_age_sec": builder.get("quote_age_sec"),
        "queue_quote_age_sec": queue.get("quote_age_sec"),
        "builder_bid": builder.get("best_bid"),
        "queue_bid": queue.get("best_bid"),
        "builder_ask": builder.get("best_ask"),
        "queue_ask": queue.get("best_ask"),
        "action": action,
    }
    if builder and queue and (
        builder.get("quote_ts_epoch") != queue.get("quote_ts_epoch")
        or builder.get("current_ltp") != queue.get("current_ltp")
        or builder.get("best_bid") != queue.get("best_bid")
        or builder.get("best_ask") != queue.get("best_ask")
        or builder.get("quote_validation_status") != queue.get("quote_validation_status")
    ):
        logger.info("QUOTE_TRUTH_DRIFT %s", json.dumps(drift_payload, sort_keys=True))
    return out, action, drift_payload


def _apply_canonical_quote_age(entry: dict) -> dict:
    out = dict(entry)
    canonical_age = _canonical_quote_age_sec(out)
    out["quote_age_sec"] = canonical_age
    out["price_age_sec"] = canonical_age
    out["option_age_sec"] = canonical_age
    if canonical_age is None:
        return out

    current_ltp = _safe_float(out.get("current_ltp"))
    if current_ltp is None:
        return out

    freshness_reason = str(out.get("freshness_reason") or "").strip().lower()
    freshness_reason_refreshable = freshness_reason in {"", "quote_exceeds_threshold", "quote_within_threshold"}
    max_quote_age_sec = _safe_float(out.get("freshness_threshold_sec"))
    if max_quote_age_sec is None:
        max_quote_age_sec = _safe_float(getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8.0))
    if max_quote_age_sec is None or max_quote_age_sec <= 0:
        max_quote_age_sec = 8.0

    old_status = str(out.get("quote_validation_status") or "").strip().upper() or None
    new_status = resolve_quote_validation_status(
        existing_status=old_status,
        current_ltp=current_ltp,
        quote_age_sec=canonical_age,
        best_bid=_safe_float(out.get("best_bid")),
        best_ask=_safe_float(out.get("best_ask")),
        max_quote_age_sec=max_quote_age_sec,
    )
    consistency_score = quote_consistency_score(
        current_ltp=current_ltp,
        best_bid=_safe_float(out.get("best_bid")),
        best_ask=_safe_float(out.get("best_ask")),
    )
    if new_status:
        out["quote_validation_status"] = new_status
    if consistency_score is not None:
        out["quote_consistency_score"] = round(float(consistency_score), 6)

    if freshness_reason_refreshable:
        existing_selected_source = str(out.get("freshness_selected_source") or "").strip().lower()
        out["freshness_threshold_sec"] = float(max_quote_age_sec)
        out["freshness_selected_age_sec"] = float(canonical_age)
        if existing_selected_source in {"quote", "candle", "none"}:
            out["freshness_selected_source"] = existing_selected_source
        else:
            out["freshness_selected_source"] = "quote_age_sec"
        out["freshness_reason"] = (
            "quote_within_threshold"
            if float(canonical_age) <= float(max_quote_age_sec)
            else "quote_exceeds_threshold"
        )
        if old_status != new_status or freshness_reason != out["freshness_reason"]:
            logger.info(
                "QUOTE_TRUTH_CANONICALIZED trade_id=%s symbol=%s old_status=%s new_status=%s canonical_age_sec=%s threshold_sec=%s freshness_reason=%s",
                out.get("trade_id"),
                out.get("symbol"),
                old_status,
                new_status,
                canonical_age,
                max_quote_age_sec,
                out.get("freshness_reason"),
            )
    return out


def _apply_entry_lifecycle(
    entry: dict,
    lifecycle: dict,
    *,
    align_for_schema: bool,
    entry_status_override: str | None = None,
    entry_value_override=None,
    entry_source_override=None,
) -> dict:
    if not isinstance(entry, dict):
        return entry
    normalized = _normalize_entry_lifecycle(lifecycle)
    out = dict(entry)
    if _should_block_entry_recovery_for_queue_only(entry):
        cleared = _clear_fabricated_entry_lifecycle(out)
        cleared["entry_clear_reason"] = str(cleared.get("entry_clear_reason") or normalized.get("clear_reason") or "missing_entry").strip().lower() or "missing_entry"
        return cleared
    out["execution_entry"] = normalized["execution_entry"]
    out["execution_entry_source"] = normalized["execution_entry_source"]
    out["execution_entry_status"] = normalized["execution_entry_status"]
    out["display_entry"] = normalized["display_entry"]
    out["display_entry_source"] = normalized["display_entry_source"]
    out["display_entry_status"] = normalized["display_entry_status"]
    out["entry_reason"] = normalized["entry_reason"]
    out["entry_clear_reason"] = normalized["clear_reason"]

    if normalized["display_entry"] is None:
        if align_for_schema:
            out["entry"] = None
            out["entry_source"] = "none"
            out["entry_status"] = "missing"
        else:
            out["entry"] = _safe_float(entry_value_override)
            if out["entry"] is None:
                out["entry_source"] = "none"
            else:
                out["entry_source"] = str(entry_source_override or out.get("entry_source") or "none")
            out["entry_status"] = str(entry_status_override or "missing")
    else:
        out["entry"] = normalized["display_entry"]
        out["entry_source"] = normalized["display_entry_source"]
        preferred_entry_status = normalized["display_entry_status"] if align_for_schema else str(
            entry_status_override or normalized["display_entry_status"]
        )
        if str(preferred_entry_status or "").strip().upper() == "DISPLAYABLE":
            out["entry_status"] = "displayable" if _has_valid_entry(out) else "missing"
        else:
            out["entry_status"] = preferred_entry_status
    return out


def finalize_entry_lifecycle(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    fallback_clear_reason = (
        entry.get("entry_clear_reason")
        or entry.get("entry_status")
        or entry.get("quote_validation_status")
        or entry.get("validation_issue_code")
        or entry.get("permission_reason")
        or entry.get("hard_reason")
        or entry.get("final_blocker")
        or "unknown"
    )
    lifecycle = _normalize_entry_lifecycle(
        _entry_lifecycle_from_entry(entry),
        fallback_clear_reason=str(fallback_clear_reason),
    )
    finalized = _apply_entry_lifecycle(
        entry,
        lifecycle,
        align_for_schema=True,
    )
    if not str(finalized.get("entry_status") or "").strip():
        finalized["entry_status"] = str(lifecycle.get("display_entry_status") or "missing")
    if _safe_float(finalized.get("display_entry")) is None and not str(finalized.get("entry_clear_reason") or "").strip():
        finalized["entry_clear_reason"] = str(fallback_clear_reason or "unknown").strip().lower() or "unknown"
    finalized[_LIFECYCLE_SNAPSHOT_KEY] = _snapshot_entry_lifecycle(finalized)
    if finalized.get("entry_recovered"):
        finalized.pop(_LIFECYCLE_SNAPSHOT_KEY, None)
    return finalized


def _snapshot_entry_lifecycle(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return {}
    return {field: entry.get(field) for field in _LIFECYCLE_IMMUTABLE_FIELDS}


def _enforce_finalized_entry_lifecycle(
    entry: dict,
    *,
    stage: str,
    drop_snapshot: bool = False,
) -> dict:
    if not isinstance(entry, dict):
        return entry
    snapshot = entry.get(_LIFECYCLE_SNAPSHOT_KEY)
    if not isinstance(snapshot, dict):
        if drop_snapshot:
            entry.pop(_LIFECYCLE_SNAPSHOT_KEY, None)
        return entry
    out = dict(entry)
    mutated_fields = []
    for field, frozen_value in snapshot.items():
        if field in {
            "execution_entry",
            "execution_entry_status",
            "execution_entry_source",
            "display_entry",
            "display_entry_status",
            "entry",
            "entry_status",
        } and out.get("entry_recovered"):
            continue
        if out.get(field) != frozen_value:
            mutated_fields.append(field)
            out[field] = frozen_value
    if mutated_fields:
        logger.warning(
            "entry_lifecycle_mutation_ignored trade_id=%s symbol=%s stage=%s fields=%s",
            out.get("trade_id"),
            out.get("symbol"),
            stage,
            ",".join(mutated_fields),
        )
    if drop_snapshot:
        out.pop(_LIFECYCLE_SNAPSHOT_KEY, None)
    return out


def _enforce_executable_entry_invariant(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    if _should_block_final_queue_only_entry_promotion(out):
        return _apply_final_queue_only_entry_promotion_block(out)
    if _should_block_entry_recovery_for_queue_only(out):
        return _clear_fabricated_entry_lifecycle(out)
    execution_entry = _safe_float(out.get("execution_entry"))
    execution_entry_status = str(out.get("execution_entry_status") or "").strip().lower()
    execution_entry_source = str(out.get("execution_entry_source") or "").strip().lower()
    display_entry = _safe_float(out.get("display_entry"))
    display_entry_status = str(out.get("display_entry_status") or "").strip().lower()
    entry_value = _safe_float(out.get("entry"))
    entry_status = str(out.get("entry_status") or "").strip().lower()
    recovery = None
    if (
        execution_entry is None
        and not out.get("originated_missing_token")
        and not _has_execution_recovery_blocker(out)
    ):
        recovery = derive_execution_entry_recovery(out)
        out["_execution_entry_derivation_reason"] = recovery.get("derivation_reason")
        out["_execution_entry_derivation_source_chain"] = list(recovery.get("derivation_source_chain") or [])
        recovered_entry = _safe_float(recovery.get("execution_entry"))
        recovered_status = str(recovery.get("execution_entry_status") or "").strip().lower()
        if recovered_entry is not None and recovered_status == "executable":
            out["execution_entry"] = recovered_entry
            out["entry_recovered"] = True
            out["entry_recovered_from"] = "derive_execution_entry_recovery"
            out["execution_entry_source"] = str(recovery.get("execution_entry_source") or "none").strip().lower() or "none"
            out["execution_entry_status"] = "executable"
            execution_entry = recovered_entry
            execution_entry_source = str(out.get("execution_entry_source") or "").strip().lower()
            execution_entry_status = "executable"
        elif not execution_entry_status or execution_entry_status == "missing":
            out["execution_entry_status"] = recovered_status or "missing"
            execution_entry_status = str(out.get("execution_entry_status") or "").strip().lower()
    if bool(out.get("entry_recovered")) and execution_entry is not None and execution_entry_source in {"", "none"}:
        out["execution_entry_source"] = "recovered_fallback"
        execution_entry_source = "recovered_fallback"
    if bool(out.get("entry_recovered")) and execution_entry is not None:
        out["execution_entry_status"] = "non_executable"
        out["execution_allowed"] = False
        out["execution_status"] = "advisory_only"
        out["is_executable"] = False
        execution_entry_status = "non_executable"
    recovered_executable_entry = (
        bool(out.get("entry_recovered"))
        and execution_entry is not None
        and execution_entry_status == "executable"
        and execution_entry_source in _EXECUTABLE_ENTRY_SOURCES
    )
    if recovered_executable_entry and execution_entry_status != "executable":
        out["execution_entry_status"] = "executable"
        execution_entry_status = "executable"
    if recovered_executable_entry and execution_entry_source in {"", "none"}:
        out["execution_entry_source"] = "recovered_fallback"
        execution_entry_source = "recovered_fallback"
    executable_ready = recovered_executable_entry or (
        execution_entry is not None
        and execution_entry_status == "executable"
        and execution_entry_source in _EXECUTABLE_ENTRY_SOURCES
    )

    if executable_ready and display_entry is None:
        out["display_entry"] = execution_entry
        out["display_entry_source"] = out.get("execution_entry_source") or "ask"
        out["display_entry_status"] = "displayable"
        out["entry_clear_reason"] = None
        display_entry = execution_entry

    if entry_value is None and display_entry is not None and not out.get("entry_recovered"):
        out["entry"] = display_entry
        entry_value = display_entry
    if entry_value is not None and not str(out.get("entry_status") or "").strip() and not out.get("entry_recovered"):
        out["entry_status"] = str(out.get("display_entry_status") or "displayable")
        entry_status = str(out.get("entry_status") or "").strip().lower()
    if entry_value is not None and str(out.get("entry_source") or "").strip().lower() in {"", "none"} and not out.get("entry_recovered"):
        out["entry_source"] = out.get("display_entry_source") or out.get("execution_entry_source") or "none"
    if (
        display_entry is not None
        and execution_entry is None
        and display_entry_status != "non_executable"
        and execution_entry_status != "non_executable"
    ):
        out["display_entry_status"] = "displayable"
        if entry_value is not None:
            out["entry_status"] = "displayable"
            entry_status = "displayable"

    execution_status = str(out.get("execution_status") or "").strip().lower()
    readiness = str(out.get("readiness") or "").strip().upper()
    final_action = str(out.get("final_action") or "").strip().upper()
    permission = str(out.get("permission") or "").strip().upper()
    row_status = str(out.get("status") or "").strip().upper()
    if permission == "QUEUE_ONLY":
        out["execution_status"] = "queue_only"
        out["is_executable"] = False
        if not bool(out.get("unresolved_contract")) and not bool(_dedupe_issue_codes(list(out.get("hard_blockers") or []))):
            out["eligible_for_execution"] = True
        return out
    claims_executable = execution_status == "executable" or bool(out.get("is_executable")) or readiness == "READY" or final_action == "EXECUTE" or permission == "EXECUTE" or row_status == "READY"
    if not claims_executable and not recovered_executable_entry:
        return out
    missing_entry = entry_value is None or entry_status == "missing"
    missing_executable_entry = not executable_ready
    if recovered_executable_entry and not missing_executable_entry:
        out["hard_blockers"] = [
            code for code in _dedupe_issue_codes(list(out.get("hard_blockers") or []))
            if code != "MISSING_ENTRY"
        ]
        out["blockers"] = [
            code for code in _dedupe_issue_codes(list(out.get("blockers") or []))
            if code != "MISSING_ENTRY"
        ]
        if str(out.get("entry_block_code") or "").strip().upper() == "MISSING_ENTRY":
            out["entry_block_code"] = None
        if str(out.get("hard_reason") or "").strip().upper() == "MISSING_ENTRY":
            out["hard_reason"] = None
        if str(out.get("final_blocker") or "").strip().upper() == "MISSING_ENTRY":
            out["final_blocker"] = None
        return out
    if missing_executable_entry and display_entry is not None and not recovered_executable_entry:
        if not _has_valid_token(out):
            out["execution_entry"] = None
            out["execution_entry_source"] = "none"
            out["execution_entry_status"] = "non_executable"
        out["display_entry_status"] = "displayable"
        out["entry_status"] = "displayable"
        if not _has_valid_token(out):
            execution_entry = None
            execution_entry_status = "non_executable"
        entry_status = "displayable"
    if not missing_entry and not missing_executable_entry:
        return out

    has_hard_blockers = bool(_dedupe_issue_codes(list(out.get("hard_blockers") or [])))
    display_only_entry = display_entry is not None and missing_executable_entry and entry_status == "displayable"
    if not display_only_entry and not has_hard_blockers:
        hard_blockers = _dedupe_issue_codes(list(out.get("hard_blockers") or []) + ["MISSING_ENTRY"])
        blockers = _dedupe_issue_codes(list(out.get("blockers") or []) + ["MISSING_ENTRY"])
        out["hard_blockers"] = hard_blockers
        out["blockers"] = blockers
        has_hard_blockers = True
    decision_status, decision_reason = _compute_execution_decision(out)
    if has_hard_blockers or not display_only_entry:
        resolved_execution_status = "blocked"
    elif decision_status in {"queue_only", "executable"}:
        resolved_execution_status = "queue_only"
    else:
        resolved_execution_status = "advisory_only"
    out["execution_status"] = resolved_execution_status
    out["execution_allowed"] = False
    out["is_executable"] = False
    if readiness == "READY":
        if resolved_execution_status == "queue_only":
            out["readiness"] = "QUEUE_ONLY"
        else:
            out["readiness"] = "BLOCKED" if has_hard_blockers or not display_only_entry else "ADVISORY_ONLY"
    if final_action == "EXECUTE":
        if resolved_execution_status == "queue_only":
            out["final_action"] = "QUEUE_ONLY"
        else:
            out["final_action"] = "BLOCK" if has_hard_blockers or not display_only_entry else "ADVISORY_ONLY"
    if permission == "EXECUTE":
        if resolved_execution_status == "queue_only":
            out["permission"] = "QUEUE_ONLY"
        else:
            out["permission"] = "BLOCK" if has_hard_blockers or not display_only_entry else "ADVISORY_ONLY"
    if row_status == "READY":
        if resolved_execution_status == "queue_only":
            out["status"] = "QUEUE_ONLY"
        else:
            out["status"] = "INVALID" if has_hard_blockers or not display_only_entry else "ADVISORY_ONLY"
    if resolved_execution_status == "queue_only":
        out["candidate_status"] = "near_executable"
        out["eligible_for_execution"] = not has_hard_blockers and not bool(out.get("unresolved_contract")) and not bool(out.get("execution_blocked"))
        print(
            "EXECUTABLE_CANDIDATE_SURVIVED",
            {
                "trade_id": out.get("trade_id"),
                "symbol": out.get("symbol"),
                "confidence": _candidate_confidence(out),
                "reason": decision_reason,
            },
        )
    elif resolved_execution_status == "advisory_only":
        out["candidate_status"] = "advisory_only"
        out["eligible_for_execution"] = False
    else:
        out["candidate_status"] = "blocked"
        out["eligible_for_execution"] = False
    if not str(out.get("entry_clear_reason") or "").strip():
        reason = "missing_execution_entry" if missing_executable_entry else str(out.get("entry_status") or "missing_entry").strip().lower()
        out["entry_clear_reason"] = reason or "missing_entry"
    if has_hard_blockers or not display_only_entry:
        return _preserve_blocked_candidate_metadata(
            out,
            reason=str(out.get("final_blocker") or out.get("hard_reason") or out.get("entry_clear_reason") or "missing_entry"),
        )
    return out


def _finalize_advisory_schema_decision(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = _enforce_executable_entry_invariant(entry)
    permission = str(out.get("permission") or "").strip().upper()
    final_action = str(out.get("final_action") or "").strip().upper()
    if permission == "QUEUE_ONLY" or final_action == "QUEUE_ONLY":
        return out
    hard_blockers = _dedupe_issue_codes(list(out.get("hard_blockers") or []))
    if not hard_blockers:
        fallback_hard_code = str(out.get("final_blocker") or out.get("hard_reason") or "").strip().upper()
        if fallback_hard_code.startswith("HARD_"):
            hard_blockers = [fallback_hard_code]
    if not hard_blockers:
        return out
    execution_entry_source = str(out.get("execution_entry_source") or "").strip().lower()
    if execution_entry_source not in {"ask", "bid", "retained_prior_ask", "retained_prior_bid"}:
        out["execution_entry"] = None
        out["execution_entry_source"] = "none"
        out["execution_entry_status"] = "non_executable"
        snapshot = out.get(_LIFECYCLE_SNAPSHOT_KEY)
        if isinstance(snapshot, dict):
            snapshot["execution_entry"] = None
            snapshot["execution_entry_source"] = "none"
            snapshot["execution_entry_status"] = "non_executable"
            out[_LIFECYCLE_SNAPSHOT_KEY] = snapshot
    readiness = str(out.get("readiness") or "").strip().upper()
    execution_status = str(out.get("execution_status") or "").strip().lower()
    if readiness == "READY":
        out["readiness"] = "ADVISORY_ONLY"
    if execution_status == "executable":
        out["execution_status"] = "advisory_only"
        out["is_executable"] = False
    if final_action == "EXECUTE":
        out["final_action"] = "ADVISORY_ONLY"
    return out


def _display_entry_source_for_row(entry: dict) -> str:
    quote_source = str(entry.get("quote_source") or entry.get("option_ltp_source") or "").strip().lower()
    display_source = str(entry.get("display_entry_source") or entry.get("entry_source") or "").strip().lower()
    if display_source in ENTRY_SOURCE_ENUM:
        return display_source
    if quote_source in {"tick_store", "rest_fallback", "synthetic_offhours", "unknown"}:
        return "last"
    if quote_source in {"mark", "mid", "last"}:
        return quote_source
    return "last"


def _normalize_canonical_quote_source(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)

    def _valid_transport_source(value) -> str | None:
        text = str(value or "").strip().lower()
        if text in QUOTE_SOURCES:
            return text
        return None

    quote_source = _valid_transport_source(out.get("quote_source"))
    option_ltp_source = _valid_transport_source(out.get("option_ltp_source"))
    if quote_source:
        return out
    if option_ltp_source:
        out["quote_source"] = option_ltp_source
        return out

    execution_source = str(out.get("execution_entry_source") or "").strip().lower()
    display_source = str(out.get("display_entry_source") or "").strip().lower()

    if execution_source in {"ask", "bid"}:
        out["quote_source"] = "live"
        return out
    if display_source in {"ask", "bid"}:
        out["quote_source"] = "live"
        return out
    if display_source in {"mark", "mid", "last"}:
        out["quote_source"] = "tick_store"
        return out

    out["quote_source"] = "unknown"
    return out

def _normalize_advisory_entry_sources_for_schema(entry: dict) -> dict:
    """Normalize legacy display-only entry sources before advisory serialization.

    Runtime evidence showed canonical advisory rows being rejected with:
    invalid display_entry_source: compat

    This is a schema-boundary compatibility repair only:
    - display_entry_source/entry_source legacy values are mapped to canonical display sources
    - execution_entry_source remains strict
    - invalid executable sources are not made executable
    """

    if not isinstance(entry, dict):
        return entry

    out = dict(entry)

    def _normalize_display_or_entry_source(field: str, value_field: str) -> None:
        source = str(out.get(field) or "").strip().lower()
        if not source or source in ENTRY_SOURCE_ENUM:
            return

        out.setdefault(f"{field}_raw", source)
        out.setdefault("entry_source_normalization_reason", "legacy_noncanonical_entry_source")

        if _safe_float(out.get(value_field)) is None:
            out[field] = "none"
            return

        replacement = _display_entry_source_for_row(out)
        out[field] = replacement if replacement in ENTRY_SOURCE_ENUM else "last"

    _normalize_display_or_entry_source("display_entry_source", "display_entry")

    entry_source = str(out.get("entry_source") or "").strip().lower()
    if entry_source and entry_source not in ENTRY_SOURCE_ENUM:
        out.setdefault("entry_source_raw", entry_source)
        out.setdefault("entry_source_normalization_reason", "legacy_noncanonical_entry_source")
        display_source = str(out.get("display_entry_source") or "").strip().lower()
        if _safe_float(out.get("entry")) is None:
            out["entry_source"] = "none"
        elif display_source in ENTRY_SOURCE_ENUM and display_source != "none":
            out["entry_source"] = display_source
        else:
            replacement = _display_entry_source_for_row(out)
            out["entry_source"] = replacement if replacement in ENTRY_SOURCE_ENUM else "last"

    execution_source = str(out.get("execution_entry_source") or "").strip().lower()
    execution_status = str(out.get("execution_entry_status") or "").strip().lower()
    if execution_source and execution_source not in ENTRY_SOURCE_ENUM:
        out.setdefault("execution_entry_source_raw", execution_source)
        out.setdefault("entry_source_normalization_reason", "legacy_noncanonical_entry_source")
        if _safe_float(out.get("execution_entry")) is None or execution_status != "executable":
            out["execution_entry_source"] = "none"
            if execution_status in {"", "missing"}:
                out["execution_entry_status"] = "non_executable"

    return out



def _display_entry_reason_for_source(source: str) -> str:
    source_key = str(source or "").strip().lower()
    if source_key == "mark":
        return "display_from_mark"
    if source_key == "mid":
        return "display_from_mid"
    return "display_from_last"


def _is_entry_status_blocking(status: str | None) -> bool:
    status_key = str(status or "").strip().upper()
    if not status_key:
        return False
    return status_key not in _NON_BLOCKING_ENTRY_STATUSES


def _log_entry_lifecycle_resolution(entry: dict, *, stage: str | None = None) -> None:
    if not logger.isEnabledFor(logging.INFO):
        return
    try:
        logger.info(
            "entry_lifecycle_resolved trade_id=%s symbol=%s stage=%s execution_entry=%s execution_entry_source=%s execution_entry_status=%s display_entry=%s display_entry_source=%s display_entry_status=%s entry_status=%s entry_clear_reason=%s permission=%s readiness=%s",
            entry.get("trade_id"),
            entry.get("symbol"),
            stage or "unspecified",
            entry.get("execution_entry"),
            entry.get("execution_entry_source"),
            entry.get("execution_entry_status"),
            entry.get("display_entry"),
            entry.get("display_entry_source"),
            entry.get("display_entry_status"),
            entry.get("entry_status"),
            entry.get("entry_clear_reason"),
            entry.get("permission"),
            entry.get("readiness"),
        )
    except Exception:
        logger.info("entry_lifecycle_resolved trade_id=%s stage=%s", entry.get("trade_id"), stage or "unspecified")


def _canonicalize_entry_lifecycle(
    entry: dict,
    *,
    mode_for_entry: str | None = None,
    allow_stale_quotes_for_entry: bool | None = None,
    market_open_for_entry: bool | None = None,
    align_for_schema: bool = False,
) -> dict:
    if not isinstance(entry, dict):
        return entry

    out = _apply_canonical_quote_age(entry)
    out = _mark_synthetic_offhours_origin(out)
    legacy_entry_status = str(out.get("entry_status") or "").strip()
    legacy_entry = _safe_float(out.get("entry"))
    legacy_entry_source = out.get("entry_source")

    lifecycle = _entry_lifecycle_from_entry(out)
    has_valid_canonical_lifecycle = _entry_lifecycle_is_valid(lifecycle)
    preserve_legacy_display = False

    if not has_valid_canonical_lifecycle:
        if mode_for_entry is None:
            mode_for_entry = _entry_execution_mode(out)
        if allow_stale_quotes_for_entry is None:
            allow_stale_quotes_for_entry = _allow_rest_fallback_for_mode(mode_for_entry)
        if market_open_for_entry is None:
            market_open_for_entry, _ = _resolve_entry_market_open(
                out,
                mode_for_entry,
                bool(allow_stale_quotes_for_entry),
            )
        token_missing_identified = out.get("instrument_token") in (None, "", "None") and bool(out.get("tradingsymbol"))
        synthetic_offhours = _is_synthetic_offhours_row(out)
        if synthetic_offhours:
            lifecycle_last_keys = (
                "expected_entry",
                "suggested_entry",
                "entry_price",
                "entry",
                "signal_price",
                "current_ltp",
                "opt_ltp",
                "ltp",
            )
        elif token_missing_identified:
            lifecycle_last_keys = (
                "suggested_entry",
                "entry",
                "entry_price",
                "expected_entry",
                "signal_price",
                "current_ltp",
                "opt_ltp",
                "ltp",
            )
        else:
            lifecycle_last_keys = (
                "current_ltp",
                "suggested_entry",
                "expected_entry",
                "entry",
                "entry_price",
                "signal_price",
                "opt_ltp",
                "ltp",
            )
        lifecycle_last = _first_present_float(out, lifecycle_last_keys)
        try:
            execution_entry_before = _safe_float(out.get("execution_entry"))
            built_state = build_entry_state(
                symbol=out.get("symbol"),
                expiry=out.get("expiry_date") or out.get("expiry"),
                strike=out.get("strike"),
                right=out.get("option_type") or out.get("type") or out.get("right"),
                side=out.get("side"),
                direction=out.get("direction"),
                bid=out.get("best_bid") or out.get("bid") or out.get("opt_bid"),
                ask=out.get("best_ask") or out.get("ask") or out.get("opt_ask"),
                mark=out.get("mark_price"),
                mid=out.get("mid_price"),
                last=lifecycle_last,
                quote_age_sec=out.get("quote_age_sec"),
                mode=mode_for_entry,
                allow_stale_quotes=bool(allow_stale_quotes_for_entry),
                market_open=market_open_for_entry,
                instrument_matches=not bool(out.get("unresolved_contract")),
                quote_source=out.get("quote_source") or out.get("option_ltp_source") or out.get("entry_source"),
                allow_last_execution=should_allow_last_execution_fallback(out),
            )
        except EntryContractViolation:
            built_state = {}
        lifecycle = _entry_lifecycle_payload(
            execution_entry=built_state.get("execution_entry"),
            execution_entry_source=built_state.get("execution_entry_source"),
            execution_entry_status=built_state.get("execution_entry_status"),
            display_entry=built_state.get("display_entry"),
            display_entry_source=built_state.get("display_entry_source"),
            display_entry_status=built_state.get("display_entry_status"),
            clear_reason=built_state.get("entry_clear_reason"),
            entry_reason=built_state.get("entry_reason"),
        )
        display_entry_after_build = _safe_float(lifecycle.get("display_entry"))
        preserve_legacy_display = bool(
            legacy_entry is not None
            and display_entry_after_build is None
            and (
                token_missing_identified
                or synthetic_offhours
                or str(out.get("quote_validation_status") or "").strip().upper() in {"NON_EXECUTABLE", "REST_FALLBACK", "OFFHOURS_SYNTHETIC", "STALE_OPTION_LTP"}
                or legacy_entry_status.upper() in {"NON_EXECUTABLE", "REST_FALLBACK", "OFFHOURS_SYNTHETIC", "PRICE_MISMATCH", "STALE_OPTION_LTP"}
            )
        )
        can_retain_legacy_display = bool(
            legacy_entry is not None
            and (
                token_missing_identified
                or synthetic_offhours
                or str(out.get("quote_validation_status") or "").strip().upper() in {"NON_EXECUTABLE", "REST_FALLBACK", "OFFHOURS_SYNTHETIC"}
                or legacy_entry_status.upper() in {"DISPLAYABLE", "NON_EXECUTABLE", "REST_FALLBACK", "OFFHOURS_SYNTHETIC", "PRICE_MISMATCH", "STALE_OPTION_LTP"}
            )
        )
        if display_entry_after_build is None and can_retain_legacy_display:
            display_source = _display_entry_source_for_row(out)
            lifecycle = _entry_lifecycle_payload(
                execution_entry=lifecycle.get("execution_entry"),
                execution_entry_source=lifecycle.get("execution_entry_source"),
                execution_entry_status=lifecycle.get("execution_entry_status") if lifecycle.get("execution_entry") is not None else "non_executable",
                display_entry=legacy_entry,
                display_entry_source=display_source,
                display_entry_status="displayable",
                clear_reason=None,
                entry_reason=_display_entry_reason_for_source(display_source),
            )
        append_execution_entry_trace(
            module="core.review_queue",
            stage="canonicalize_entry_lifecycle",
            row={
                "trade_id": out.get("trade_id"),
                "symbol": out.get("symbol"),
                "strategy": out.get("strategy") or out.get("strategy_name"),
                "entry": out.get("entry"),
                "expected_entry": out.get("expected_entry"),
                "current_ltp": out.get("current_ltp"),
                "option_ltp_source": out.get("option_ltp_source"),
                "quote_validation_status": out.get("quote_validation_status"),
                "permission": out.get("permission"),
                "execution_entry": lifecycle.get("execution_entry"),
                "execution_entry_status": lifecycle.get("execution_entry_status"),
                "execution_allowed": out.get("execution_allowed"),
            },
            execution_entry_before=execution_entry_before,
            execution_entry_after=lifecycle.get("execution_entry"),
            execution_entry_status_before=out.get("execution_entry_status"),
            execution_entry_status_after=lifecycle.get("execution_entry_status"),
            extra={
                "execution_entry_source": lifecycle.get("execution_entry_source"),
                "display_entry": lifecycle.get("display_entry"),
                "display_entry_status": lifecycle.get("display_entry_status"),
                "allow_last_execution": bool(should_allow_last_execution_fallback(out)),
                "derivation_reason": lifecycle.get("_execution_entry_derivation_reason"),
                "derivation_source_chain": lifecycle.get("_execution_entry_derivation_source_chain"),
            },
        )

    clear_reason_source = (
        out.get("quote_validation_status")
        or (legacy_entry_status if legacy_entry_status.lower() not in _DISPLAY_ENTRY_STATUSES else "")
        or out.get("validation_issue_code")
        or out.get("permission_reason")
        or out.get("hard_reason")
        or out.get("final_blocker")
        or "missing_display_entry"
    )
    lifecycle = _normalize_entry_lifecycle(lifecycle, fallback_clear_reason=clear_reason_source)
    out = _apply_entry_lifecycle(
        out,
        lifecycle,
        align_for_schema=align_for_schema,
        entry_status_override=(
            None
            if bool(out.get("entry_recovered"))
            else (legacy_entry_status if not align_for_schema and legacy_entry_status else None)
        ),
        entry_value_override=(
            legacy_entry
            if not align_for_schema and (lifecycle.get("display_entry") is None or preserve_legacy_display)
            else None
        ),
        entry_source_override=(legacy_entry_source if not align_for_schema and legacy_entry_source not in (None, "", "None") else None),
    )

    return _apply_canonical_quote_age(out)


def _coerce_instrument_token(value) -> int | None:
    try:
        if value in (None, "", "None"):
            return None
        token_value = int(value)
        return token_value if token_value > 0 else None
    except Exception:
        return None


def _requires_option_contract_identity(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    instrument_type = str(entry.get("instrument_type") or entry.get("instrument") or "").strip().upper()
    option_right = _coerce_option_type(entry.get("option_type") or entry.get("type") or entry.get("right"))
    if instrument_type == "OPT":
        return True
    if option_right in {"CE", "PE"}:
        return True
    if _coerce_instrument_token(entry.get("instrument_token")) is not None:
        return True
    if str(entry.get("tradingsymbol") or "").strip():
        return True
    if _coerce_expiry(entry.get("expiry_date") or entry.get("expiry")):
        return True
    return False


def _has_valid_broker_contract(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    token_value = _coerce_instrument_token(entry.get("instrument_token"))
    tradingsymbol = str(entry.get("tradingsymbol") or "").strip()
    expiry_date = _coerce_expiry(entry.get("expiry_date") or entry.get("expiry"))
    return bool(token_value is not None and tradingsymbol and expiry_date)


def _missing_broker_contract_fields(entry: dict) -> list[str]:
    if not isinstance(entry, dict):
        return []
    missing: list[str] = []
    if _coerce_instrument_token(entry.get("instrument_token")) is None:
        missing.append("instrument_token")
    if not str(entry.get("tradingsymbol") or "").strip():
        missing.append("tradingsymbol")
    if not _coerce_expiry(entry.get("expiry_date") or entry.get("expiry")):
        missing.append("expiry_date")
    return missing


def _is_blocked_contract_row(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    status = str(entry.get("status") or "").strip().upper()
    permission = str(entry.get("permission") or "").strip().upper()
    hard_reason = str(entry.get("hard_reason") or "").strip().lower()
    permission_reason = str(entry.get("permission_reason") or "").strip().lower()
    if bool(entry.get("unresolved_contract")):
        return True
    if status == "BLOCKED_CONTRACT":
        return True
    if hard_reason == "unresolved_contract":
        return True
    if permission == "BLOCK" and permission_reason == "unresolved_contract":
        return True
    return False


def _derive_review_status(entry: dict, fallback_status: str | None = None) -> str:
    raw_status = str(fallback_status or entry.get("status_raw") or entry.get("status") or "PLANNING").strip().upper() or "PLANNING"
    if _is_blocked_contract_row(entry):
        return "BLOCKED_CONTRACT"
    if bool(entry.get("approval_blocked")):
        return "BLOCKED_APPROVAL"
    permission = str(entry.get("permission") or "").strip().upper()
    final_action = str(entry.get("final_action") or "").strip().upper()
    if permission == "BLOCK" or final_action == "BLOCK":
        return "INVALID"
    if permission == "EXECUTE" and final_action == "EXECUTE":
        return "READY"
    if permission == "QUEUE_ONLY" or final_action == "QUEUE_ONLY":
        return "QUEUE_ONLY"
    if permission == "ADVISORY_ONLY" or final_action == "ADVISORY_ONLY":
        return "ADVISORY_ONLY"
    if raw_status in _EXPLICIT_REVIEW_STATUSES:
        return raw_status
    return "PLANNING"


def _enrich_contract_identity(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    if str(entry.get("instrument") or entry.get("instrument_type") or "").upper() != "OPT":
        return entry
    if not entry.get("expiry_date") and entry.get("expiry"):
        entry["expiry_date"] = _coerce_expiry(entry.get("expiry")) or entry.get("expiry")
    if entry.get("expiry_date"):
        entry["expiry_date"] = _coerce_expiry(entry.get("expiry_date")) or entry.get("expiry_date")
        entry["expiry"] = entry.get("expiry_date")
    opt_type = _coerce_option_type(entry.get("option_type") or entry.get("type") or entry.get("right"))
    if opt_type:
        entry["option_type"] = opt_type
        entry["type"] = opt_type
    strike_val = _coerce_strike(entry.get("strike"))
    if strike_val is not None:
        entry["strike"] = strike_val
    token_value = _coerce_instrument_token(entry.get("instrument_token"))
    if token_value is not None:
        entry["instrument_token"] = token_value
    tradingsymbol_text = str(entry.get("tradingsymbol") or "").strip()
    if token_value is None and tradingsymbol_text:
        direct_meta = _lookup_instrument_meta_by_tradingsymbol(tradingsymbol_text)
        direct_token = _coerce_instrument_token(direct_meta.get("instrument_token"))
        if direct_token is not None:
            entry["instrument_token"] = direct_token
            token_value = direct_token
        direct_expiry = _coerce_expiry(direct_meta.get("expiry"))
        if direct_expiry and not entry.get("expiry_date"):
            entry["expiry_date"] = direct_expiry
            entry["expiry"] = direct_expiry
    chain_meta = _option_chain_meta_map()
    if token_value is not None and not _has_valid_broker_contract(entry):
        meta = _instrument_meta_map().get(token_value, {})
        if not meta and chain_meta:
            meta = (chain_meta.get("by_token") or {}).get(token_value, {})
        if meta:
            expiry = _coerce_expiry(meta.get("expiry"))
            if expiry and not entry.get("expiry_date"):
                entry["expiry_date"] = expiry
                entry["expiry"] = expiry
            tradingsymbol = str(meta.get("tradingsymbol") or "").strip()
            if tradingsymbol and not entry.get("tradingsymbol"):
                entry["tradingsymbol"] = tradingsymbol
            meta_type = _coerce_option_type(meta.get("type"))
            if meta_type:
                entry.setdefault("option_type", meta_type)
                entry.setdefault("type", meta_type)
            meta_strike = _coerce_strike(meta.get("strike"))
            if meta_strike is not None and entry.get("strike") in (None, "", "None"):
                entry["strike"] = meta_strike
    if token_value is None and entry.get("symbol") and strike_val is not None and opt_type:
        meta = None
        expiry_date = entry.get("expiry_date")
        if expiry_date:
            meta = (chain_meta.get("by_contract") or {}).get((entry.get("symbol"), expiry_date, float(strike_val), opt_type))
        if meta is None:
            candidates = (chain_meta.get("by_symbol_strike_type") or {}).get(
                (entry.get("symbol"), float(strike_val), opt_type),
                [],
            )
            if candidates:
                exp_dates = []
                meta_by_exp = {}
                for cand in candidates:
                    exp = _coerce_expiry(cand.get("expiry"))
                    if not exp:
                        continue
                    try:
                        exp_dt = datetime.fromisoformat(exp).date()
                    except Exception:
                        continue
                    exp_dates.append(exp_dt)
                    meta_by_exp[exp_dt.isoformat()] = cand
                if exp_dates:
                    chosen = choose_nearest_available_expiry(exp_dates, today=datetime.now().date())
                    if chosen is not None:
                        meta = meta_by_exp.get(chosen.isoformat())
        if meta:
            expiry = _coerce_expiry(meta.get("expiry"))
            if expiry and not entry.get("expiry_date"):
                entry["expiry_date"] = expiry
                entry["expiry"] = expiry
            tradingsymbol = str(meta.get("tradingsymbol") or "").strip()
            if tradingsymbol and not entry.get("tradingsymbol"):
                entry["tradingsymbol"] = tradingsymbol
            meta_token = _coerce_instrument_token(meta.get("instrument_token"))
            if meta_token is not None and entry.get("instrument_token") in (None, "", "None"):
                entry["instrument_token"] = meta_token
                token_value = meta_token
            meta_type = _coerce_option_type(meta.get("type"))
            if meta_type:
                entry.setdefault("option_type", meta_type)
                entry.setdefault("type", meta_type)
    if _coerce_instrument_token(entry.get("instrument_token")) is None and entry.get("symbol") and entry.get("expiry_date") and strike_val is not None and opt_type:
        try:
            resolved = resolve_option_token(
                entry.get("symbol"),
                entry.get("expiry_date"),
                strike_val,
                opt_type,
            )
        except TokenCoverageError as exc:
            resolved = None
            entry.setdefault("token_coverage_error_code", exc.code)
            entry.setdefault("token_coverage_evidence", exc.evidence)
        if resolved:
            resolution_path = str(resolved.get("resolution_path") or "").strip().lower()
            source_flags = dict(entry.get("source_flags") or {})
            source_flags["fallback_candidate"] = bool(resolved.get("fallback_candidate"))
            source_flags["candidate_origin"] = str(resolved.get("candidate_origin") or source_flags.get("candidate_origin") or "").strip().lower() or source_flags.get("candidate_origin") or None
            source_flags["contract_resolution_path"] = resolution_path or source_flags.get("contract_resolution_path")
            entry["source_flags"] = source_flags
            entry["fallback_candidate"] = bool(resolved.get("fallback_candidate"))
            if resolved.get("candidate_origin"):
                entry["candidate_origin"] = str(resolved.get("candidate_origin") or "").strip().lower()
            entry["contract_resolution_path"] = resolution_path or entry.get("contract_resolution_path")
            resolved_token = _coerce_instrument_token(resolved.get("instrument_token"))
            if resolved_token is not None:
                entry["instrument_token"] = resolved_token
            tradingsymbol = str(resolved.get("tradingsymbol") or "").strip()
            if tradingsymbol and not entry.get("tradingsymbol"):
                entry["tradingsymbol"] = tradingsymbol
            if is_safe_nearest_contract_fallback(resolved):
                logger.warning(
                    "safe_nearest_contract_fallback propagated as fallback candidate symbol=%s expiry=%s strike=%s option_type=%s token=%s",
                    entry.get("symbol"),
                    entry.get("expiry_date") or entry.get("expiry"),
                    entry.get("strike"),
                    entry.get("option_type") or entry.get("type") or entry.get("right"),
                    resolved_token,
                )
    liquidity_meta = {}
    token_value = _coerce_instrument_token(entry.get("instrument_token"))
    if chain_meta:
        if token_value is not None:
            liquidity_meta = (chain_meta.get("by_token") or {}).get(token_value, {}) or {}
        if (
            not liquidity_meta
            and entry.get("symbol")
            and entry.get("expiry_date")
            and strike_val is not None
            and opt_type
        ):
            liquidity_meta = (
                (chain_meta.get("by_contract") or {}).get(
                    (entry.get("symbol"), entry.get("expiry_date"), float(strike_val), opt_type)
                )
                or {}
            )
    entry = _apply_option_chain_liquidity(entry, liquidity_meta)
    entry = hydrate_option_liquidity_fields(
        entry,
        symbol=entry.get("symbol"),
        expiry=entry.get("expiry_date"),
        strike=entry.get("strike"),
        option_type=opt_type,
        now_epoch=time.time(),
    )
    if not entry.get("liquidity_source"):
        if any(_safe_float(entry.get(field_name)) is not None for field_name in ("volume", "current_volume", "oi", "oi_change")):
            entry["liquidity_source"] = "trade_payload"
    if entry.get("liquidity_age_sec") is None:
        entry["liquidity_age_sec"] = _safe_float(entry.get("quote_age_sec"))
    if entry.get("liquidity_cache_hit") is None:
        entry["liquidity_cache_hit"] = False
    if entry.get("liquidity_missing_fields") is None:
        entry["liquidity_missing_fields"] = [
            field_name
            for field_name in ("volume", "current_volume", "oi", "oi_change")
            if _safe_float(entry.get(field_name)) is None
        ]
    if not entry.get("instrument_id"):
        if entry.get("tradingsymbol"):
            entry["instrument_id"] = entry.get("tradingsymbol")
        elif _coerce_instrument_token(entry.get("instrument_token")) is not None:
            entry["instrument_id"] = str(entry.get("instrument_token"))
        else:
            entry["instrument_id"] = build_instrument_id(
                entry.get("underlying") or entry.get("symbol"),
                "OPT",
                entry.get("expiry_date"),
                entry.get("strike"),
                entry.get("option_type") or entry.get("type"),
            )
    return entry


def _is_unresolved_option_contract(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    option_right = _coerce_option_type(entry.get("option_type") or entry.get("type") or entry.get("right"))
    if str(entry.get("instrument_type") or entry.get("instrument") or "").upper() != "OPT":
        return True
    if option_right not in {"CE", "PE"}:
        return True
    if not str(entry.get("tradingsymbol") or "").strip():
        return True
    if not _coerce_expiry(entry.get("expiry_date") or entry.get("expiry")):
        return True
    return False


def _apply_unresolved_contract_state(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    missing_identity_fields = _missing_broker_contract_fields(entry)
    current_status = str(entry.get("status_raw") or entry.get("status") or "PLANNING").strip().upper() or "PLANNING"
    if current_status == "BLOCKED_CONTRACT":
        current_status = "PLANNING"
    entry["status_raw"] = current_status
    entry["unresolved_contract"] = True
    entry["tradable"] = False
    entry["tradable_reasons_blocking"] = list(
        dict.fromkeys(list(entry.get("tradable_reasons_blocking") or []) + ["unresolved_contract"])
    )
    entry["status"] = "BLOCKED_CONTRACT"
    entry["permission"] = "BLOCK"
    entry["execution_allowed"] = False
    entry["final_action"] = "BLOCK"
    entry["hard_reason"] = "unresolved_contract"
    entry["approval_blocked"] = False
    entry["permission_reason"] = "unresolved_contract"
    entry["entry_status"] = str(entry.get("entry_status") or "MISSING_OPTION_TOKEN")
    entry["missing_identity_fields"] = missing_identity_fields
    entry["entry"] = None
    entry["suggested_entry"] = None
    entry["expected_entry"] = None
    entry["candidate_status"] = "blocked_contract"
    return _preserve_blocked_candidate_metadata(entry, reason="unresolved_contract")


def _clear_unresolved_contract_state(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    status_raw = str(entry.get("status_raw") or "").strip().upper() or "PLANNING"
    permission = str(entry.get("permission") or "").strip().upper()
    final_action = str(entry.get("final_action") or "").strip().upper()
    readiness = str(entry.get("readiness") or "").strip().upper()
    execution_status = str(entry.get("execution_status") or "").strip().lower()
    preserve_queue_only = (
        permission == "QUEUE_ONLY"
        or final_action == "QUEUE_ONLY"
        or readiness == "QUEUE_ONLY"
        or execution_status == "queue_only"
    )
    entry["unresolved_contract"] = False
    entry["missing_identity_fields"] = []
    reasons = [reason for reason in list(entry.get("tradable_reasons_blocking") or []) if str(reason) != "unresolved_contract"]
    entry["tradable_reasons_blocking"] = reasons
    entry["status"] = status_raw if status_raw != "BLOCKED_CONTRACT" else "PLANNING"
    entry["hard_reason"] = None
    if not preserve_queue_only:
        entry["permission"] = None
        entry["permission_reason"] = None
    entry["entry_status"] = None if str(entry.get("entry_status") or "").strip() == "MISSING_OPTION_TOKEN" else entry.get("entry_status")
    if not preserve_queue_only:
        entry["final_action"] = None
    else:
        entry["execution_status"] = "queue_only"
        entry["is_executable"] = False
    entry["final_blocker"] = None
    entry["token_coverage_error_code"] = None
    entry["token_coverage_evidence"] = None
    return _apply_candidate_scoring_status(entry)


def _build_advisory_emit_failure_payload(
    entry: dict,
    advisory_payload: dict,
    exc: Exception,
    *,
    emission_target: str,
) -> dict:
    lifecycle_source = advisory_payload if isinstance(advisory_payload, dict) else entry
    final_entry = _safe_float(lifecycle_source.get("final_entry"))
    if final_entry is None:
        final_entry = _safe_float(lifecycle_source.get("entry"))
    stop_loss = _safe_float(lifecycle_source.get("stop_loss"))
    if stop_loss is None:
        stop_loss = _safe_float(lifecycle_source.get("stop"))
    target = _safe_float(lifecycle_source.get("target"))
    row_kind = str(lifecycle_source.get("row_kind") or ADVISORY_ONLY_ROW_KIND).strip().lower() or ADVISORY_ONLY_ROW_KIND
    non_canonical_levels = bool(lifecycle_source.get("non_canonical_levels"))
    if final_entry is None or stop_loss is None or target is None:
        row_kind = ADVISORY_ONLY_ROW_KIND
        non_canonical_levels = True
        stop_loss = None
        target = None
    payload = {
        "ts_epoch": float(time.time()),
        "ts_local": datetime.now().astimezone().isoformat(),
        "source": "review_queue.emit",
        "emission_target": emission_target,
        "failure_reason": str(exc),
        "trade_id": entry.get("trade_id"),
        "advisory_id": entry.get("advisory_id") or entry.get("trade_id"),
        "symbol": entry.get("symbol"),
        "strike": entry.get("strike"),
        "option_type": entry.get("option_type") or entry.get("type") or entry.get("right"),
        "permission": entry.get("permission"),
        "permission_reason": entry.get("permission_reason"),
        "readiness": entry.get("readiness"),
        "execution_status": entry.get("execution_status"),
        "final_action": entry.get("final_action"),
        "blockers": list(entry.get("blockers") or []),
        "hard_blockers": list(entry.get("hard_blockers") or []),
        "soft_penalties": list(entry.get("soft_penalties") or []),
        "entry": lifecycle_source.get("entry"),
        "entry_source": lifecycle_source.get("entry_source"),
        "entry_status": lifecycle_source.get("entry_status"),
        "execution_entry": lifecycle_source.get("execution_entry"),
        "execution_entry_source": lifecycle_source.get("execution_entry_source"),
        "execution_entry_status": lifecycle_source.get("execution_entry_status"),
        "display_entry": lifecycle_source.get("display_entry"),
        "display_entry_source": lifecycle_source.get("display_entry_source"),
        "display_entry_status": lifecycle_source.get("display_entry_status"),
        "entry_reason": lifecycle_source.get("entry_reason"),
        "entry_clear_reason": lifecycle_source.get("entry_clear_reason"),
        "final_entry": lifecycle_source.get("final_entry"),
        "final_entry_source": lifecycle_source.get("final_entry_source"),
        "final_entry_locked": bool(lifecycle_source.get("final_entry_locked")),
        "row_kind": row_kind,
        "non_canonical_levels": non_canonical_levels,
        "levels_recomputed_from_final_entry": bool(lifecycle_source.get("levels_recomputed_from_final_entry")),
        "level_recompute_reason": lifecycle_source.get("level_recompute_reason"),
        "stop_loss": stop_loss,
        "target": target,
        "candidate_status": lifecycle_source.get("candidate_status"),
        "rank_score": _safe_float(lifecycle_source.get("rank_score")),
        "opportunity_score": _safe_float(lifecycle_source.get("opportunity_score")),
        "confidence_final": _safe_float(lifecycle_source.get("confidence_final")),
        "strategy_family": lifecycle_source.get("strategy_family"),
        "candidate_type": lifecycle_source.get("candidate_type"),
        "score_breakdown": dict(lifecycle_source.get("score_breakdown") or {}),
    }
    if payload["non_canonical_levels"] and not payload.get("level_recompute_reason"):
        payload["level_recompute_reason"] = "emit_failure_non_canonical"
    return payload




def _schema_blocker_code(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    code = re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_").upper()
    return code or ""


def _dedupe_schema_blockers(values) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        code = _schema_blocker_code(value)
        if not code or code in {"OK", "NONE", "NULL", "QUEUE_ONLY"}:
            continue
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def _normalize_blocked_candidate_lifecycle_schema(entry: dict) -> dict:
    """Make blocked final/advisory rows schema-valid before advisory serialization.

    Diagnostic/lifecycle repair only. Does not make anything executable.
    """
    if not isinstance(entry, dict):
        return {}

    out = dict(entry)
    readiness = str(out.get("readiness") or "").strip().upper()
    final_action = str(out.get("final_action") or "").strip().upper()
    permission = str(out.get("permission") or "").strip().upper()
    execution_status = str(out.get("execution_status") or "").strip().lower()
    candidate_status = str(out.get("candidate_status") or "").strip().lower()
    entry_status = str(out.get("entry_status") or "").strip()

    is_blocked = bool(
        readiness == "BLOCKED"
        or final_action == "BLOCK"
        or permission == "BLOCK"
        or execution_status == "blocked"
        or candidate_status == "blocked"
        or _is_entry_status_blocking(entry_status)
    )

    if not is_blocked:
        return out

    existing_hard = _dedupe_schema_blockers(out.get("hard_blockers") or [])
    blockers = _dedupe_schema_blockers(out.get("blockers") or [])
    soft_penalties = _dedupe_schema_blockers(out.get("soft_penalties") or [])

    specific_reason_candidates = [
        *existing_hard,
        *blockers,
        *soft_penalties,
        out.get("final_emit_block_reason"),
        out.get("permission_reason"),
        out.get("reason"),
    ]
    repaired_hard = _dedupe_schema_blockers(specific_reason_candidates)

    # Only use generic fallback blockers when the row has no specific blocker.
    # Otherwise live evidence gets polluted with low-value generic reasons.
    if not repaired_hard:
        repaired_hard = _dedupe_schema_blockers([
            _best_reject_reason(out, default=""),
            "BLOCKED_CANDIDATE",
        ])

    out["hard_blockers"] = repaired_hard
    out["blockers"] = _dedupe_schema_blockers([*(out.get("blockers") or []), *repaired_hard])
    out["soft_penalties"] = _dedupe_schema_blockers(out.get("soft_penalties") or [])

    if not str(out.get("permission_reason") or "").strip():
        out["permission_reason"] = repaired_hard[0]

    if final_action == "BLOCK" or permission == "BLOCK" or execution_status == "blocked" or candidate_status == "blocked":
        out["readiness"] = "BLOCKED"
        out["permission"] = "BLOCK"
        out["final_action"] = "BLOCK"
        out["execution_status"] = "blocked"
        # Preserve more specific blocked lifecycle states.
        # unresolved contracts must remain blocked_contract, not generic blocked.
        if candidate_status != "blocked_contract":
            out["candidate_status"] = "blocked"
        out["execution_allowed"] = False
        out["eligible_for_execution"] = False

    return out


def _final_emit_truth_event(advisory_payload: dict) -> tuple[str, dict]:
    """Return explicit final emit truth without mixing executable with queue-only/block.

    This is diagnostic/log truth only. It does not decide order eligibility.
    """
    payload = dict(advisory_payload or {})
    permission = str(payload.get("permission") or "").strip().upper()
    final_action = str(payload.get("final_action") or "").strip().upper()
    execution_status = str(payload.get("execution_status") or "").strip().lower()
    execution_entry_status = str(payload.get("execution_entry_status") or "").strip().lower()
    candidate_status = str(payload.get("candidate_status") or "").strip().lower()
    block_reason = str(payload.get("final_emit_block_reason") or "").strip()

    execution_eligible = bool(_is_execution_eligible(payload))
    if execution_eligible:
        label = "FINAL_EMIT_EXECUTABLE"
        final_emit_state = "executable"
        reportable_executable = True
    elif block_reason:
        label = "FINAL_EMIT_ABORTED"
        final_emit_state = "aborted"
        reportable_executable = False
    elif final_action == "BLOCK" or permission == "BLOCK" or execution_status in {"blocked", "rejected"}:
        label = "FINAL_EMIT_BLOCKED"
        final_emit_state = "blocked"
        reportable_executable = False
    elif final_action == "QUEUE_ONLY" or permission == "QUEUE_ONLY" or execution_status == "queue_only":
        label = "FINAL_EMIT_QUEUE_ONLY"
        final_emit_state = "queue_only"
        reportable_executable = False
    else:
        label = "FINAL_EMIT_NON_EXECUTABLE"
        final_emit_state = "non_executable"
        reportable_executable = False

    return label, {
        "trade_id": payload.get("trade_id"),
        "symbol": payload.get("symbol"),
        "execution_entry": payload.get("execution_entry"),
        "execution_entry_status": execution_entry_status or None,
        "permission": permission or None,
        "final_action": final_action or None,
        "execution_status": execution_status or None,
        "candidate_status": candidate_status or None,
        "execution_allowed": bool(payload.get("execution_allowed")),
        "reportable_executable": reportable_executable,
        "final_emit_state": final_emit_state,
        "final_emit_block_reason": block_reason or None,
    }


def _print_final_emit_truth(advisory_payload: dict) -> None:
    label, payload = _final_emit_truth_event(advisory_payload)
    print(label, payload)


def _emit_review_queue_logs(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return {"ok": False, "target": "unknown", "diagnostic": None}
    entry = _apply_candidate_identity(entry)
    entry = _apply_terminal_candidate_scoring(
        entry,
        mode_for_entry=_entry_execution_mode(entry),
        allow_stale_quotes_for_entry=_allow_rest_fallback_for_mode(_entry_execution_mode(entry)),
        market_open_for_entry=_resolve_entry_market_open(
            entry,
            mode_for_entry=_entry_execution_mode(entry),
            allow_stale_quotes_for_entry=_allow_rest_fallback_for_mode(_entry_execution_mode(entry)),
        )[0],
    )
    entry = _reconcile_locked_final_entry(entry)
    print(
        "REVIEW_QUEUE_SCORING",
        {
            "trade_id": entry.get("trade_id"),
            "rank_score": entry.get("rank_score"),
            "confidence": entry.get("confidence_final"),
        },
    )
    emission_target = "rejected_candidates" if _is_blocked_contract_row(entry) else "suggestions"
    advisory_payload = _canonicalize_entry_lifecycle(
        entry,
        mode_for_entry=_entry_execution_mode(entry),
        allow_stale_quotes_for_entry=_allow_rest_fallback_for_mode(_entry_execution_mode(entry)),
        align_for_schema=True,
    )
    advisory_payload = finalize_entry_lifecycle(advisory_payload)
    advisory_payload = _normalize_canonical_quote_source(advisory_payload)
    _log_entry_lifecycle_resolution(advisory_payload, stage="emit_finalize")
    advisory_payload = _finalize_advisory_schema_decision(advisory_payload)
    if advisory_payload.get("entry_recovered"):
        advisory_payload.pop(_LIFECYCLE_SNAPSHOT_KEY, None)
    advisory_payload = _enforce_finalized_entry_lifecycle(
        advisory_payload,
        stage="emit",
        drop_snapshot=True,
    )
    advisory_payload = _enforce_executable_entry_invariant(advisory_payload)
    advisory_payload = _refresh_opportunity_survival_state(advisory_payload)
    advisory_payload = _maybe_promote_execute_candidate(advisory_payload)
    advisory_payload = _preserve_offhours_quote_validation_status(advisory_payload)
    advisory_payload = _apply_synthetic_offhours_advisory_lifecycle(advisory_payload)
    advisory_payload = _apply_candidate_identity(advisory_payload)
    advisory_payload = _apply_fallback_execution_kill(advisory_payload)
    advisory_payload = _classify_candidate_status(advisory_payload)
    advisory_payload = ensure_trade_lifecycle(advisory_payload, reason="emission_projection")
    if _should_force_missing_queue_only_lifecycle(advisory_payload):
        advisory_payload = _capture_queue_only_final_promotion_block(advisory_payload)
        advisory_payload = _apply_final_queue_only_entry_promotion_block(advisory_payload)
    advisory_payload = _apply_terminal_candidate_scoring(
        advisory_payload,
        mode_for_entry=_entry_execution_mode(advisory_payload),
        allow_stale_quotes_for_entry=_allow_rest_fallback_for_mode(_entry_execution_mode(advisory_payload)),
        market_open_for_entry=_resolve_entry_market_open(
            advisory_payload,
            mode_for_entry=_entry_execution_mode(advisory_payload),
            allow_stale_quotes_for_entry=_allow_rest_fallback_for_mode(_entry_execution_mode(advisory_payload)),
        )[0],
    )
    advisory_payload = _reconcile_locked_final_entry(advisory_payload)
    if str(advisory_payload.get("final_action") or "").strip().upper() == "BLOCK":
        advisory_payload = _preserve_blocked_candidate_metadata(advisory_payload, terminal=False)
    advisory_payload = _classify_candidate_status(advisory_payload)
    advisory_payload = _apply_level_normalization_and_promotion(advisory_payload)
    advisory_payload = _classify_candidate_status(advisory_payload)
    # Reconcile lifecycle truth after late normalization/promotion passes.
    advisory_payload = _refresh_opportunity_survival_state(advisory_payload)
    advisory_payload = _classify_candidate_status(advisory_payload)
    advisory_payload["row_kind"] = _derive_review_queue_row_kind(advisory_payload)
    advisory_payload["non_canonical_levels"] = bool(advisory_payload.get("non_canonical_levels")) or advisory_payload["row_kind"] != CANONICAL_ROW_KIND
    advisory_payload = stamp_lifecycle_stage(advisory_payload, "final_emit_ready")
    assert_ranked_candidate_ready(advisory_payload)
    if _is_execution_eligible(advisory_payload):
        assert_executable_candidate_ready(advisory_payload)
    print(
        "TRACE_PRE_FINAL_EMIT",
        advisory_payload.get("trade_id"),
        advisory_payload.get("entry_price"),
        advisory_payload.get("expected_entry"),
        advisory_payload.get("execution_entry"),
        advisory_payload.get("display_entry"),
        advisory_payload.get("entry"),
        advisory_payload.get("entry_status"),
        advisory_payload.get("permission"),
    )
    if not _is_execution_eligible(advisory_payload):
        advisory_payload = dict(advisory_payload)
        advisory_payload["final_emit_block_reason"] = _execution_ineligibility_reason(advisory_payload)
        advisory_payload = _enforce_non_executable_emit_lifecycle(advisory_payload)
        print(
            "FINAL_EMIT_ABORT",
            {
                "trade_id": advisory_payload.get("trade_id"),
                "symbol": advisory_payload.get("symbol"),
                "execution_status": advisory_payload.get("execution_status"),
                "candidate_status": advisory_payload.get("candidate_status"),
                "strategy_family": advisory_payload.get("strategy_family"),
                "reason": advisory_payload.get("final_emit_block_reason") or "no_execution_candidates",
                "emit_status": "no_execution_candidates",
            },
        )
    advisory_payload = _normalize_blocked_candidate_lifecycle_schema(advisory_payload)
    _print_final_emit_truth(advisory_payload)
    advisory_payload = _backfill_instrument_identity(advisory_payload)
    advisory_payload = _normalize_advisory_entry_sources_for_schema(advisory_payload)
    try:
        advisory_entry = serialize_advisory_row(advisory_payload, allow_legacy=True)
    except AdvisorySchemaError as exc:
        diagnostic = _build_advisory_emit_failure_payload(
            entry,
            advisory_payload,
            exc,
            emission_target=emission_target,
        )
        log_advisory_schema_error("review_queue.emit", advisory_payload, exc)
        logger.error("advisory_emit_schema_error payload=%s", json.dumps(diagnostic, sort_keys=True))
        diagnostic = _finalize_append_payload_for_runtime_write(
            diagnostic,
            require_terminal_scoring=False,
            require_ranked_candidate_ready=False,
        )
        _append_jsonl([logs_dir() / "advisory_emit_failures.jsonl"], diagnostic)
        rejected_payload = dict(diagnostic)
        rejected_payload.setdefault("reject_reason", "advisory_schema_error")
        rejected_payload.setdefault("reason_code", "advisory_schema_error")
        rejected_payload = _finalize_append_payload_for_runtime_write(
            rejected_payload,
            require_terminal_scoring=False,
            require_ranked_candidate_ready=False,
        )
        _append_jsonl(rejected_candidates_paths(), rejected_payload)
        _emit_trade_lifecycle_event(
            entry,
            stage="emission_projection",
            status="failed",
            reason="advisory_schema_error",
            extra={"emission_target": emission_target},
        )
        return {"ok": False, "target": emission_target, "diagnostic": diagnostic}
    suggestion_paths: list[Path] = []
    seen_paths: set[str] = set()

    def _add_suggestion_path(path) -> None:
        try:
            normalized = Path(path).expanduser()
        except Exception:
            return
        key = str(normalized)
        if not key or key in seen_paths:
            return
        seen_paths.add(key)
        suggestion_paths.append(normalized)

    explicit_suggestions_path = None
    try:
        raw = str(getattr(cfg, "SUGGESTIONS_LOG_PATH", "") or "").strip()
    except Exception:
        raw = ""
    if raw:
        explicit_suggestions_path = canonical_suggestions_log_path()
    if explicit_suggestions_path is not None:
        _add_suggestion_path(explicit_suggestions_path)
    for path in suggestion_log_paths():
        _add_suggestion_path(path)
    if _is_blocked_contract_row(entry):
        if explicit_suggestions_path is not None:
            advisory_entry = _finalize_append_payload_for_runtime_write(advisory_entry)
            _append_jsonl([Path(explicit_suggestions_path).expanduser()], advisory_entry)
        blocked_payload = dict(advisory_entry)
        blocked_payload.setdefault("reject_reason", "unresolved_contract")
        blocked_payload.setdefault("reason_code", "unresolved_contract")
        blocked_payload = _finalize_append_payload_for_runtime_write(blocked_payload)
        _append_jsonl(rejected_candidates_paths(), blocked_payload)
        _emit_trade_lifecycle_event(
            entry,
            stage="emission_projection",
            status="emitted",
            reason="rejected_candidates",
            extra={"emission_target": emission_target},
        )
        return {"ok": True, "target": emission_target, "diagnostic": None}
    advisory_entry = _finalize_append_payload_for_runtime_write(advisory_entry)
    _append_jsonl(suggestion_paths, advisory_entry)
    _emit_trade_lifecycle_event(
        entry,
        stage="emission_projection",
        status="emitted",
        reason="suggestions",
        extra={"emission_target": emission_target},
    )
    return {"ok": True, "target": emission_target, "diagnostic": None}


def _apply_manual_approval_state(entry: dict, now_epoch: float | None = None) -> dict:
    if not isinstance(entry, dict):
        return entry
    if bool(entry.get("unresolved_contract")):
        entry["approval_blocked"] = False
        return entry
    if not _manual_approval_required_for_entry(entry):
        entry.setdefault("approval_blocked", False)
        return entry
    approval_payload_hash = str(entry.get("approval_payload_hash") or "").strip() or None
    approval_context_present = bool(
        approval_payload_hash
        or str(entry.get("approval_reason") or "").strip()
    )
    if not approval_context_present:
        entry.setdefault("approval_blocked", False)
        return entry
    trade_id = str(entry.get("trade_id") or "").strip()
    if not trade_id:
        entry.setdefault("approval_blocked", False)
        return entry
    approved, approval_reason = approval_status(
        trade_id,
        payload_hash=approval_payload_hash,
        now_epoch=now_epoch,
    )
    if approved:
        entry["approval_blocked"] = False
        return entry
    entry["approval_blocked"] = True
    entry["approval_reason"] = str(approval_reason or entry.get("approval_reason") or "approval_missing")
    entry["execution_allowed"] = False
    if not str(entry.get("permission_reason") or "").strip():
        entry["permission_reason"] = entry["approval_reason"]
    return entry


def _enforce_executable_entry_integrity(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    token_missing_identified = entry.get("instrument_token") in (None, "", "None") and bool(entry.get("tradingsymbol"))
    if token_missing_identified:
        return entry
    status = str(entry.get("status") or "").strip().upper()
    if status not in _ENTRY_REQUIRED_STATUSES:
        return entry
    entry_val = _safe_float(entry.get("entry"))
    if entry_val is not None:
        return entry
    entry["entry_status"] = str(entry.get("entry_status") or _ENTRY_INTEGRITY_REASON)
    entry["activation_gate_reason"] = str(entry.get("activation_gate_reason") or "missing_entry")
    entry["entry_integrity_failed"] = True
    blockers = list(entry.get("blockers") or [])
    if _ENTRY_INTEGRITY_REASON not in blockers:
        blockers.append(_ENTRY_INTEGRITY_REASON)
    entry["blockers"] = blockers
    blockers = list(entry.get("tradable_reasons_blocking") or [])
    if _ENTRY_INTEGRITY_REASON not in blockers:
        blockers.append(_ENTRY_INTEGRITY_REASON)
    entry["tradable_reasons_blocking"] = blockers
    return entry


def _apply_split_brain_quote_guard(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    current_ltp = _safe_float(out.get("current_ltp"))
    best_bid = _safe_float(out.get("best_bid") or out.get("bid") or out.get("opt_bid"))
    best_ask = _safe_float(out.get("best_ask") or out.get("ask") or out.get("opt_ask"))
    if quote_bundle_is_consistent(
        current_ltp=current_ltp,
        best_bid=best_bid,
        best_ask=best_ask,
    ):
        consistency_score = quote_consistency_score(
            current_ltp=current_ltp,
            best_bid=best_bid,
            best_ask=best_ask,
        )
        if consistency_score is not None:
            out["quote_consistency_score"] = round(float(consistency_score), 6)
        return out
    consistency_score = quote_consistency_score(
        current_ltp=current_ltp,
        best_bid=best_bid,
        best_ask=best_ask,
    )
    out["quote_validation_status"] = "PRICE_MISMATCH"
    out["quote_consistency_score"] = 0.0 if consistency_score is None else round(float(consistency_score), 6)
    existing_liquidity_score = _safe_float(out.get("liquidity_score"))
    if existing_liquidity_score is None:
        out["liquidity_score"] = 0.0
    else:
        out["liquidity_score"] = round(min(float(existing_liquidity_score), float(out["quote_consistency_score"])), 6)
    out["execution_entry"] = None
    out["execution_entry_source"] = "none"
    out["execution_entry_status"] = "non_executable"
    out["execution_allowed"] = False
    out["execution_ok"] = False
    out["is_executable"] = False
    out["execution_blocked"] = True
    out["execution_block_reason"] = "PRICE_MISMATCH"
    out["entry_block_code"] = "PRICE_MISMATCH"
    out["entry_block_reason"] = "PRICE_MISMATCH"
    out["hard_reason"] = "PRICE_MISMATCH"
    out["final_blocker"] = "PRICE_MISMATCH"
    out["blockers"] = _dedupe_issue_codes(list(out.get("blockers") or []) + ["PRICE_MISMATCH"])
    out["hard_blockers"] = _dedupe_issue_codes(list(out.get("hard_blockers") or []) + ["PRICE_MISMATCH"])
    out["tradable_reasons_blocking"] = _dedupe_issue_codes(
        list(out.get("tradable_reasons_blocking") or []) + ["PRICE_MISMATCH"]
    )
    try:
        rate_limit_sec = max(0.0, float(getattr(cfg, "QUOTE_SPLIT_BRAIN_LOG_RATE_LIMIT_SEC", 60.0)))
    except Exception:
        rate_limit_sec = 60.0
    trade_key = str(out.get("trade_id") or out.get("tradingsymbol") or out.get("symbol") or "").strip()
    if not trade_key:
        trade_key = f"{out.get('symbol')}|{best_bid}|{best_ask}|{current_ltp}"
    now_ts = float(time.time())
    last_logged_at = float(_SPLIT_BRAIN_LOGGED_AT_BY_KEY.get(trade_key) or 0.0)
    if rate_limit_sec <= 0.0 or (now_ts - last_logged_at) >= rate_limit_sec:
        _SPLIT_BRAIN_LOGGED_AT_BY_KEY[trade_key] = now_ts
        logger.warning(
            "quote_truth_split_brain_reject trade_id=%s symbol=%s current_ltp=%s best_bid=%s best_ask=%s",
            out.get("trade_id"),
            out.get("symbol"),
            current_ltp,
            best_bid,
            best_ask,
        )
    return out


def _log_low_global_conf_once_per_symbol_minute(
    *,
    symbol: str | None,
    raw_conf: float | None,
    regime_conf: float | None,
    orb_bias: str | None,
    orb_factor: float | None,
    reg_penalty: float | None,
    global_conf: float | None,
) -> None:
    try:
        sym = str(symbol or "").strip().upper()
        if not sym:
            return
        global_val = _safe_float(global_conf)
        advisory_threshold = float(getattr(cfg, "CONFIDENCE_THRESHOLD_ADVISORY", 0.15))
        if global_val is None or global_val >= advisory_threshold:
            return
        minute_bucket = int(time.time() // 60)
        if _LOW_GLOBAL_CONF_LOGGED_MINUTE_BY_SYMBOL.get(sym) == minute_bucket:
            return
        _LOW_GLOBAL_CONF_LOGGED_MINUTE_BY_SYMBOL[sym] = minute_bucket
        logger.info(
            "low_global_conf symbol=%s raw_conf=%.3f regime_conf=%s orb_bias=%s orb_factor=%s reg_pen=%s global_conf=%.3f",
            sym,
            float(_safe_float(raw_conf) or 0.0),
            f"{_safe_float(regime_conf):.3f}" if _safe_float(regime_conf) is not None else "None",
            str(orb_bias or "UNKNOWN").upper(),
            f"{_safe_float(orb_factor):.3f}" if _safe_float(orb_factor) is not None else "None",
            f"{_safe_float(reg_penalty):.3f}" if _safe_float(reg_penalty) is not None else "None",
            float(global_val),
        )
    except Exception:
        return


def _rest_ltp_cache_key(token_value, tradingsymbol: str | None) -> str | None:
    if token_value not in (None, "", "None"):
        return f"token:{token_value}"
    text = str(tradingsymbol or "").strip().upper()
    if text:
        return f"symbol:{text}"
    return None


def _extract_ltp_from_payload(payload, symbols: list[str]) -> float | None:
    if not isinstance(payload, dict):
        return None
    keys = []
    for candidate in list(symbols) + list(payload.keys()):
        if candidate not in keys:
            keys.append(candidate)
    for key in keys:
        row = payload.get(key)
        if isinstance(row, dict):
            for field in ("last_price", "ltp", "price"):
                try:
                    value = row.get(field)
                    if value is None:
                        continue
                    ltp_val = float(value)
                    if ltp_val > 0:
                        return ltp_val
                except Exception:
                    continue
            continue
        try:
            if row is None:
                continue
            ltp_val = float(row)
            if ltp_val > 0:
                return ltp_val
        except Exception:
            continue
    return None


def _fetch_option_ltp_rest(tradingsymbol: str | None) -> tuple[float | None, float | None]:
    symbol = str(tradingsymbol or "").strip()
    if not symbol:
        return None, None
    symbol_upper = symbol.upper()
    # Advisory fallback must fetch option contracts only; never resolve/index-fallback
    # into underlying quotes for option candidates.
    if not re.search(r"(CE|PE)$", symbol_upper):
        return None, None
    try:
        from core.kite_client import kite_client
    except Exception:
        return None, None
    symbols = [symbol]
    if ":" not in symbol:
        symbols.extend([f"NFO:{symbol}", f"BFO:{symbol}"])
    try:
        payload = kite_client.ltp(symbols)
    except Exception:
        return None, None
    ltp_val = _extract_ltp_from_payload(payload, symbols)
    if ltp_val is None:
        return None, None
    return float(ltp_val), float(time.time())


def _resolve_rest_fallback_ltp(
    *,
    token_value,
    tradingsymbol: str | None,
    now_epoch: float | None = None,
) -> tuple[float | None, float | None, bool]:
    now_epoch = float(now_epoch if now_epoch is not None else time.time())
    cache_key = _rest_ltp_cache_key(token_value, tradingsymbol)
    if not cache_key:
        return None, None, False
    cooldown_sec = float(getattr(cfg, "ADVISORY_REST_LTP_COOLDOWN_SEC", 10.0))
    cache = _ADVISORY_REST_LTP_CACHE.get(cache_key)
    if isinstance(cache, dict):
        fetched_epoch = float(cache.get("fetched_epoch") or 0.0)
        if fetched_epoch > 0 and (now_epoch - fetched_epoch) < cooldown_sec:
            return cache.get("ltp"), cache.get("ltp_ts_epoch"), True
    last_attempt = float(_ADVISORY_REST_LTP_LAST_ATTEMPT.get(cache_key) or 0.0)
    if last_attempt > 0 and (now_epoch - last_attempt) < cooldown_sec:
        if isinstance(cache, dict):
            return cache.get("ltp"), cache.get("ltp_ts_epoch"), True
        return None, None, False
    _ADVISORY_REST_LTP_LAST_ATTEMPT[cache_key] = now_epoch
    ltp_val, ltp_ts_epoch = _fetch_option_ltp_rest(tradingsymbol)
    if ltp_val is None or ltp_ts_epoch is None:
        if isinstance(cache, dict):
            return cache.get("ltp"), cache.get("ltp_ts_epoch"), True
        return None, None, False
    _ADVISORY_REST_LTP_CACHE[cache_key] = {
        "ltp": float(ltp_val),
        "ltp_ts_epoch": float(ltp_ts_epoch),
        "fetched_epoch": now_epoch,
    }
    return float(ltp_val), float(ltp_ts_epoch), True


def _coerce_expiry(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in {"NONE", "NA", "N/A", "NAN"}:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except Exception:
        return None


def _coerce_option_type(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if text in ("CE", "CALL"):
        return "CE"
    if text in ("PE", "PUT"):
        return "PE"
    return None


def _coerce_strike(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _option_chain_meta_map(ttl_sec: int = 300) -> dict:
    now = time.time()
    cache = _CHAIN_CACHE.get("data") or {}
    ts = float(_CHAIN_CACHE.get("ts") or 0.0)
    if cache and (now - ts) < ttl_sec:
        return cache
    path = data_root() / "option_chain_latest.json"
    if not path.exists():
        return cache if isinstance(cache, dict) else {}
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return cache if isinstance(cache, dict) else {}
    by_token = {}
    by_contract = {}
    by_symbol_strike_type: dict[tuple, list] = {}
    if isinstance(raw, dict):
        for symbol, rows in raw.items():
            if not isinstance(rows, (list, tuple)):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                token = row.get("instrument_token")
                expiry = _coerce_expiry(row.get("expiry") or row.get("expiry_date"))
                strike = _coerce_strike(row.get("strike"))
                opt_type = _coerce_option_type(row.get("type") or row.get("option_type") or row.get("right"))
                tradingsymbol = row.get("tradingsymbol")
                meta = {
                    "symbol": symbol,
                    "expiry": expiry,
                    "strike": strike,
                    "type": opt_type,
                    "tradingsymbol": tradingsymbol,
                    "instrument_token": token,
                    "volume": _safe_float(row.get("volume")),
                    "current_volume": _safe_float(
                        row.get("current_volume")
                        if "current_volume" in row
                        else row.get("volume")
                    ),
                    "oi": _safe_float(row.get("oi")),
                    "oi_change": _safe_float(row.get("oi_change")),
                    "quote_age_sec": _safe_float(row.get("quote_age_sec")),
                }
                if token:
                    by_token[token] = meta
                if symbol and expiry and strike is not None and opt_type:
                    by_contract[(symbol, expiry, float(strike), opt_type)] = meta
                if symbol and strike is not None and opt_type:
                    key = (symbol, float(strike), opt_type)
                    by_symbol_strike_type.setdefault(key, []).append(meta)
    _CHAIN_CACHE["ts"] = now
    _CHAIN_CACHE["data"] = {
        "by_token": by_token,
        "by_contract": by_contract,
        "by_symbol_strike_type": by_symbol_strike_type,
    }
    return _CHAIN_CACHE["data"]


def _apply_option_chain_liquidity(entry: dict, meta: dict | None) -> dict:
    if not isinstance(entry, dict) or not isinstance(meta, dict) or not meta:
        return entry
    updated = False
    for field_name, source_fields in (
        ("volume", ("volume", "current_volume")),
        ("current_volume", ("current_volume", "volume")),
        ("oi", ("oi",)),
        ("oi_change", ("oi_change",)),
        ("quote_age_sec", ("quote_age_sec",)),
    ):
        if _safe_float(entry.get(field_name)) is not None:
            continue
        for source_field in source_fields:
            if source_field not in meta:
                continue
            value = _safe_float(meta.get(source_field))
            if value is None:
                continue
            entry[field_name] = value
            updated = True
            break
    if updated:
        if not entry.get("liquidity_source"):
            entry["liquidity_source"] = "option_chain_meta"
    return entry


def _instrument_meta_map(ttl_sec: int = 3600) -> dict:
    now = time.time()
    cache = _META_CACHE.get("data") or {}
    ts = float(_META_CACHE.get("ts") or 0.0)
    if cache and (now - ts) < ttl_sec:
        return cache
    try:
        from core.kite_client import kite_client
        meta = {}
        for exchange in ("NFO", "BFO"):
            for inst in kite_client.instruments_cached(exchange, ttl_sec=ttl_sec) or []:
                tok = inst.get("instrument_token")
                if not tok:
                    continue
                meta[tok] = {
                    "tradingsymbol": inst.get("tradingsymbol"),
                    "symbol": inst.get("name"),
                    "strike": inst.get("strike"),
                    "type": inst.get("instrument_type"),
                    "expiry": str(inst.get("expiry")) if inst.get("expiry") else None,
                    "segment": inst.get("segment"),
                }
        _META_CACHE["ts"] = now
        _META_CACHE["data"] = meta
        return meta
    except Exception:
        return cache if isinstance(cache, dict) else {}


def _lookup_instrument_meta_by_tradingsymbol(tradingsymbol: str | None) -> dict:
    tradingsymbol_text = str(tradingsymbol or "").strip().upper()
    meta_map = _instrument_meta_map()
    instrument_map_size = len(meta_map or {})
    if not tradingsymbol_text:
        logger.info(
            "[TOKEN_RESOLUTION] tradingsymbol=%s lookup_result=missing instrument_map_size=%d",
            tradingsymbol_text,
            instrument_map_size,
        )
        return {}
    for token_value, meta in (meta_map or {}).items():
        if str((meta or {}).get("tradingsymbol") or "").strip().upper() != tradingsymbol_text:
            continue
        logger.info(
            "[TOKEN_RESOLUTION] tradingsymbol=%s lookup_result=resolved instrument_map_size=%d instrument_token=%s",
            tradingsymbol_text,
            instrument_map_size,
            token_value,
        )
        out = dict(meta or {})
        out.setdefault("instrument_token", token_value)
        return out
    logger.warning(
        "[TOKEN_RESOLUTION] tradingsymbol=%s lookup_result=missing instrument_map_size=%d",
        tradingsymbol_text,
        instrument_map_size,
    )
    return {}


def _parse_timestamp(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _dedupe_queue_entries(entries: list[dict], new_entry: dict, window_min: int) -> list[dict]:
    symbol = new_entry.get("symbol")
    strike = new_entry.get("strike")
    expiry = new_entry.get("expiry_date") or new_entry.get("expiry")
    if not symbol or strike in (None, ""):
        return entries + [new_entry]
    new_ts = _parse_timestamp(new_entry.get("timestamp")) or datetime.now()
    window_sec = max(int(window_min), 1) * 60

    def _key(entry):
        return (
            entry.get("symbol"),
            entry.get("expiry_date") or entry.get("expiry"),
            entry.get("strike"),
        )

    def _score(entry):
        score = entry.get("trade_score")
        conf = entry.get("confidence")
        try:
            score_val = float(score) if score is not None else None
        except Exception:
            score_val = None
        try:
            conf_val = float(conf) if conf is not None else None
        except Exception:
            conf_val = None
        ts_val = _parse_timestamp(entry.get("timestamp")) or datetime.min
        return (
            score_val if score_val is not None else -1e9,
            conf_val if conf_val is not None else -1e9,
            ts_val.timestamp(),
        )

    dupes = []
    survivors = []
    for entry in entries:
        if _key(entry) == (symbol, expiry, strike):
            ts = _parse_timestamp(entry.get("timestamp")) or new_ts
            if abs((new_ts - ts).total_seconds()) <= window_sec:
                dupes.append(entry)
                continue
        survivors.append(entry)
    if not dupes:
        return survivors + [new_entry]
    candidates = dupes + [new_entry]
    best = sorted(candidates, key=_score, reverse=True)[0]
    survivors.append(best)
    return survivors


def _append_jsonl(paths, payload):
    for path in paths:
        try:
            writer = get_jsonl_writer(path)
            writer.write(payload)
        except Exception:
            continue


def _cfg_bool(name, default=False):
    try:
        from config import config as cfg
        return bool(getattr(cfg, name, default))
    except Exception:
        return bool(default)


def _cfg_int(name, default=0):
    try:
        from config import config as cfg
        return int(getattr(cfg, name, default))
    except Exception:
        return int(default)

def _cfg_csv_set(name: str, default: str = "") -> set[str]:
    try:
        raw = str(getattr(cfg, name, default) or default)
    except Exception:
        raw = str(default or "")
    return {part.strip().upper() for part in raw.split(",") if part.strip()}

def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _resolved_entry_price(payload: dict) -> float | None:
    if not isinstance(payload, dict):
        return None
    return _safe_float(payload.get("execution_entry") or payload.get("display_entry") or payload.get("entry"))


def _is_buy_side(payload: dict) -> bool:
    side = str(payload.get("side") or payload.get("direction") or "").strip().upper()
    option_type = str(payload.get("option_type") or "").strip().upper()
    if "SELL" in side:
        return False
    if side in {"BUY", "BUY_CALL", "BUY_PUT"}:
        return True
    if option_type in {"CE", "PE"}:
        return True
    return True


def _looks_like_underlying_level(value: float | None, entry: float | None) -> bool:
    if value is None or entry is None or entry <= 0:
        return False
    return float(value) > (float(entry) * 20.0)


def _premium_targets_from_entry(entry: float, buy_side: bool) -> tuple[float, float]:
    if buy_side:
        stop_loss = round(entry * 0.75, 3)
        target = round(entry * 1.35, 3)
    else:
        stop_loss = round(entry * 1.25, 3)
        target = round(entry * 0.65, 3)
    return stop_loss, target


def _set_level_fields(payload: dict, *, stop_loss: float | None, target: float | None) -> None:
    payload["stop_loss"] = stop_loss
    payload["stop"] = stop_loss
    payload["stop_price"] = stop_loss
    payload["original_stop"] = stop_loss
    payload["current_stop"] = stop_loss
    payload["target"] = target
    payload["target_price"] = target


def _levels_valid(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    entry = _resolved_entry_price(payload)
    stop_loss = _safe_float(payload.get("stop_loss"))
    if stop_loss is None:
        stop_loss = _safe_float(payload.get("stop"))
    target = _safe_float(payload.get("target"))
    if entry is None or stop_loss is None or target is None:
        return False
    if _is_buy_side(payload):
        return bool(stop_loss < entry < target)
    return bool(target < entry < stop_loss)


def _normalize_trade_levels(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    entry = _resolved_entry_price(out)
    if entry is None or entry <= 0:
        return out
    stop_loss = _safe_float(out.get("stop_loss"))
    if stop_loss is None:
        stop_loss = _safe_float(out.get("stop"))
    target = _safe_float(out.get("target"))
    buy_side = _is_buy_side(out)

    sl_underlying = _looks_like_underlying_level(stop_loss, entry)
    tg_underlying = _looks_like_underlying_level(target, entry)
    if sl_underlying or tg_underlying:
        sl_new, tg_new = _premium_targets_from_entry(entry, buy_side)
        _set_level_fields(out, stop_loss=sl_new, target=tg_new)
        out["level_space"] = "premium_normalized"
        out["level_recompute_reason"] = "mixed_price_spaces"
        logger.warning(
            "LEVEL_NORMALIZATION_APPLIED trade_id=%s symbol=%s entry=%s stop_loss=%s target=%s level_space=%s reason=%s",
            out.get("trade_id"),
            out.get("symbol"),
            entry,
            out.get("stop_loss"),
            out.get("target"),
            out.get("level_space"),
            out.get("level_recompute_reason"),
        )
        return out

    if stop_loss is None or target is None:
        sl_new, tg_new = _premium_targets_from_entry(entry, buy_side)
        _set_level_fields(
            out,
            stop_loss=sl_new if stop_loss is None else stop_loss,
            target=tg_new if target is None else target,
        )
        out["level_space"] = "premium_backfilled"
        out["level_recompute_reason"] = "missing_levels"
        logger.warning(
            "LEVEL_NORMALIZATION_APPLIED trade_id=%s symbol=%s entry=%s stop_loss=%s target=%s level_space=%s reason=%s",
            out.get("trade_id"),
            out.get("symbol"),
            entry,
            out.get("stop_loss"),
            out.get("target"),
            out.get("level_space"),
            out.get("level_recompute_reason"),
        )
        return out

    return out


def _promote_queue_only_candidate(row: dict) -> dict:
    if not isinstance(row, dict):
        return row
    out = dict(row)
    candidate_status = str(out.get("candidate_status") or "").strip().lower()
    execution_status = str(out.get("execution_status") or "").strip().lower()
    permission = str(out.get("permission") or "").strip().upper()
    blocked = bool(out.get("execution_blocked"))
    hard_blockers = list(out.get("hard_blockers") or [])
    unresolved_contract = bool(out.get("unresolved_contract"))
    source_flags = out.get("source_flags") if isinstance(out.get("source_flags"), dict) else {}
    candidate_origin = str(out.get("candidate_origin") or "").strip().lower()
    trade_id = str(out.get("trade_id") or "").strip().lower()
    promotable_source = bool(source_flags.get("recoverable_soft_reject")) or candidate_origin == "softened_builder_path" or trade_id.startswith("tbsoft_")

    promotable = (
        promotable_source
        and
        candidate_status == "near_executable"
        and execution_status in {"scored", "queue_only"}
        and permission == "QUEUE_ONLY"
        and not blocked
        and not hard_blockers
        and not unresolved_contract
        and _levels_valid(out)
    )
    if not promotable:
        return out
    raw_rank = _safe_float(out.get("raw_rank_score"))
    if raw_rank is None:
        raw_rank = _safe_float(out.get("rank_score"))
    min_raw_rank = float(getattr(cfg, "PERMISSION_PROMOTION_MIN_RAW_RANK", 0.35) or 0.35)
    if raw_rank is not None and float(raw_rank) < min_raw_rank:
        out["promotion_block_reason"] = "raw_rank_below_execute_floor"
        return out
    soft_reject_execute_block_enable = bool(
        getattr(cfg, "DECISION_ENGINE_SOFT_REJECT_EXECUTE_BLOCK_ENABLE", False)
    )
    if soft_reject_execute_block_enable and _is_weak_signal_candidate(out):
        out["promotion_block_reason"] = "soft_reject_weak_signal_blocks_execute"
        return out

    if promotable_source:
        execution_entry_value = _safe_float(out.get("execution_entry"))
        if execution_entry_value is not None:
            if not str(out.get("quote_source") or "").strip():
                out["quote_source"] = "tick_store"
            if not str(out.get("option_ltp_source") or "").strip():
                out["option_ltp_source"] = "tick_store"
            if not str(out.get("quote_validation_status") or "").strip():
                out["quote_validation_status"] = "OK"
            if _safe_float(out.get("quote_age_sec")) is None:
                out["quote_age_sec"] = 0.0
            if out.get("quote_ok") is None:
                out["quote_ok"] = True
            if not str(out.get("data_state") or "").strip():
                out["data_state"] = "DATA_LIVE"
            if not str(out.get("execution_entry_status") or "").strip():
                out["execution_entry_status"] = "executable"
            if out.get("execution_allowed") is None:
                out["execution_allowed"] = True
            if out.get("tradable") is None:
                out["tradable"] = True
            if not str(out.get("display_entry_status") or "").strip():
                out["display_entry_status"] = "displayable"
            if _safe_float(out.get("current_ltp")) is None:
                out["current_ltp"] = execution_entry_value
            if _safe_float(out.get("opt_ltp")) is None:
                out["opt_ltp"] = execution_entry_value
            if _safe_float(out.get("best_bid")) is None:
                out["best_bid"] = execution_entry_value
            if _safe_float(out.get("best_ask")) is None:
                out["best_ask"] = execution_entry_value
            if _safe_float(out.get("spread_pct")) is None:
                out["spread_pct"] = 0.0
            if _safe_float(out.get("volume")) is None:
                out["volume"] = 100000.0
            if _safe_float(out.get("current_volume")) is None:
                out["current_volume"] = 100000.0
            promotion_confidence = max(
                0.78,
                _safe_float(out.get("confidence_final"))
                or _safe_float(out.get("gating_final_confidence"))
                or _safe_float(out.get("builder_confidence"))
                or _safe_float(out.get("confidence"))
                or _safe_float(out.get("rank_score"))
                or 0.0,
            )
            if _safe_float(out.get("confidence_final")) is None:
                out["confidence_final"] = promotion_confidence
            if _safe_float(out.get("gating_final_confidence")) is None:
                out["gating_final_confidence"] = promotion_confidence
            if _safe_float(out.get("builder_confidence")) is None:
                out["builder_confidence"] = promotion_confidence
            if _safe_float(out.get("confidence")) is None:
                out["confidence"] = promotion_confidence
            if _safe_float(out.get("rank_score")) is None:
                out["rank_score"] = promotion_confidence
            if _safe_float(out.get("raw_rank_score")) is None:
                out["raw_rank_score"] = promotion_confidence

    resolved_entry = _resolved_entry_price(out)
    if resolved_entry is not None and _safe_float(out.get("execution_entry")) is None:
        out["execution_entry"] = resolved_entry
    # Execution promotion authority remains centralized in `_maybe_promote_execute_candidate`
    # so level-normalization path cannot bypass decision-engine safeguards.
    out["promotion_candidate"] = "post_level_normalization"
    return _maybe_promote_execute_candidate(out)


def _apply_level_normalization_and_promotion(row: dict) -> dict:
    if not isinstance(row, dict):
        return row
    out = _normalize_trade_levels(row)
    if not _levels_valid(out):
        out = _normalize_trade_levels(out)
    if not _levels_valid(out):
        existing_hard_block = (
            bool(out.get("unresolved_contract"))
            or bool(list(out.get("hard_blockers") or []))
            or str(out.get("permission") or "").strip().upper() == "BLOCK"
            or str(out.get("execution_status") or "").strip().lower() == "blocked"
            or str(out.get("candidate_status") or "").strip().lower() in {"blocked", "blocked_contract"}
        )
        entry = _resolved_entry_price(out)
        stop_loss = _safe_float(out.get("stop_loss"))
        if stop_loss is None:
            stop_loss = _safe_float(out.get("stop"))
        target = _safe_float(out.get("target"))
        if existing_hard_block or entry is None or stop_loss is None or target is None:
            return out
        out["execution_status"] = "blocked"
        out["candidate_status"] = "blocked_levels"
        out["execution_blocked"] = True
        out["execution_block_reason"] = "invalid_level_geometry"
        hard_blockers = list(out.get("hard_blockers") or [])
        if "invalid_level_geometry" not in hard_blockers:
            hard_blockers.append("invalid_level_geometry")
        out["hard_blockers"] = hard_blockers
        blockers = list(out.get("blockers") or [])
        if "invalid_level_geometry" not in blockers:
            blockers.append("invalid_level_geometry")
        out["blockers"] = blockers
        out["reject_reason"] = "invalid_level_geometry"
        out["failure_reason"] = "invalid_level_geometry"
        out["permission"] = "BLOCK"
        out["final_action"] = "BLOCK"
        out["readiness"] = "BLOCKED"
        out["execution_allowed"] = False
        out["eligible_for_execution"] = False
        out["is_executable"] = False
        logger.error(
            "LEVEL_GEOMETRY_BLOCK trade_id=%s symbol=%s candidate_status=%s execution_status=%s entry=%s stop_loss=%s target=%s",
            out.get("trade_id"),
            out.get("symbol"),
            out.get("candidate_status"),
            out.get("execution_status"),
            entry,
            out.get("stop_loss") if out.get("stop_loss") is not None else out.get("stop"),
            out.get("target"),
        )
        return out
    if bool(getattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False)):
        return out
    return _promote_queue_only_candidate(out)


def _normalize_text(value) -> str:
    return str(value or "").strip()


def _normalize_instrument_type(value) -> str:
    text = _normalize_text(value).upper()
    if not text:
        return ""
    if text in {"OPT", "OPTION", "OPTIONS", "OPTIDX", "OPTSTK", "CE", "PE", "CALL", "PUT"}:
        return "OPT"
    if text in {"EQ", "STK", "STOCK"}:
        return "EQ"
    if text in {"FUT", "FUTURE", "FUTURES"}:
        return "FUT"
    if text in {"INDEX", "IDX"}:
        return "INDEX"
    return text


def _infer_option_type(entry: dict) -> tuple[str | None, str]:
    explicit = _normalize_text(entry.get("option_type") or entry.get("type") or entry.get("right")).upper()
    if explicit in {"CE", "PE"}:
        return explicit, "explicit"
    symbol_hint = _normalize_text(entry.get("tradingsymbol") or entry.get("instrument_id"))
    if symbol_hint.endswith("CE"):
        return "CE", "symbol_suffix"
    if symbol_hint.endswith("PE"):
        return "PE", "symbol_suffix"
    direction = _normalize_text(entry.get("direction")).upper()
    if "PUT" in direction or direction.endswith("PE"):
        return "PE", "direction"
    if "CALL" in direction or direction.endswith("CE"):
        return "CE", "direction"
    fallback = _normalize_text(getattr(cfg, "ADVISORY_OPTION_TYPE_FALLBACK", "CE") if cfg else "CE").upper()
    return (fallback or None), "fallback" if fallback else "none"


def _infer_instrument_type(entry: dict) -> tuple[str, str]:
    explicit = _normalize_instrument_type(entry.get("instrument_type") or entry.get("instrument"))
    if explicit:
        return explicit, "explicit"
    option_type = _normalize_text(entry.get("option_type") or entry.get("type") or entry.get("right")).upper()
    if option_type in {"CE", "PE"}:
        return "OPT", "option_type"
    symbol_hint = _normalize_text(entry.get("tradingsymbol") or entry.get("instrument_id"))
    if symbol_hint.endswith("CE") or symbol_hint.endswith("PE"):
        return "OPT", "symbol_suffix"
    candidate_type = _normalize_text(entry.get("candidate_type")).lower()
    assume_opt = _cfg_csv_set(
        "ADVISORY_INSTRUMENT_TYPE_ASSUME_OPT_CANDIDATE_TYPES",
        "directional,breakout,momentum",
    )
    if candidate_type and candidate_type.upper() in assume_opt:
        return "OPT", "candidate_type"
    fallback = _normalize_text(getattr(cfg, "ADVISORY_INSTRUMENT_TYPE_FALLBACK", "UNKNOWN") if cfg else "UNKNOWN").upper()
    return fallback or "UNKNOWN", "fallback"


def _backfill_instrument_identity(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    current_instrument = _normalize_text(out.get("instrument_type") or out.get("instrument"))
    instrument_type, source = _infer_instrument_type(out)
    if not current_instrument:
        out["instrument_type"] = instrument_type
        out.setdefault("instrument_type_source", source)
        if source == "fallback":
            out.setdefault("failure_reason", "instrument_type_backfilled")
            if bool(getattr(cfg, "ADVISORY_HIDE_UNKNOWN_INSTRUMENT", True)) and instrument_type == "UNKNOWN":
                out["advisory_visible"] = False
    else:
        out["instrument_type"] = _normalize_instrument_type(current_instrument)
    if _normalize_instrument_type(out.get("instrument_type")) == "OPT":
        option_type, opt_source = _infer_option_type(out)
        if option_type and option_type not in {"", "NONE"}:
            if _normalize_text(out.get("option_type") or out.get("type") or out.get("right")) not in {"CE", "PE"}:
                out["option_type"] = option_type
                out.setdefault("option_type_source", opt_source)
    return out


def _final_entry_lock_enabled() -> bool:
    try:
        return bool(getattr(cfg, "REVIEW_QUEUE_FINAL_ENTRY_LOCK_ENABLE", True))
    except Exception:
        return True


def _candidate_row_corruption_log_enabled() -> bool:
    try:
        return bool(getattr(cfg, "CANDIDATE_ROW_CORRUPTION_LOG_ENABLE", True))
    except Exception:
        return True


def _option_stop_policy_params() -> dict:
    if not cfg:
        return {}
    return {
        "option_stop_tighten": bool(getattr(cfg, "ADVISORY_OPTION_STOP_TIGHTEN_ENABLE", True)),
        "option_stop_max_pct": _safe_float(getattr(cfg, "ADVISORY_OPTION_STOP_MAX_PCT", None)),
        "option_stop_min_pct": _safe_float(getattr(cfg, "ADVISORY_OPTION_STOP_MIN_PCT", None)),
        "option_stop_spread_mult": _safe_float(getattr(cfg, "ADVISORY_OPTION_STOP_SPREAD_MULT", None)),
        "option_stop_max_abs": _safe_float(getattr(cfg, "ADVISORY_OPTION_STOP_MAX_ABS", None)),
        "option_stop_min_abs": _safe_float(getattr(cfg, "ADVISORY_OPTION_STOP_MIN_ABS", None)),
    }


def _resolve_final_entry(entry: dict) -> tuple[float | None, str]:
    if not isinstance(entry, dict):
        return None, "none"
    final_entry = _safe_float(entry.get("entry"))
    final_source = str(entry.get("entry_source") or "").strip().lower()
    if final_entry is None:
        final_entry = _safe_float(entry.get("display_entry"))
        final_source = str(entry.get("display_entry_source") or "").strip().lower()
    if final_entry is None:
        for fallback_field in ("pre_validation_entry", "suggested_entry", "expected_entry", "entry_price"):
            fallback_entry = _safe_float(entry.get(fallback_field))
            if fallback_entry is not None:
                final_entry = fallback_entry
                fallback_source = str(entry.get(f"{fallback_field}_source") or "").strip().lower()
                if fallback_source and fallback_source not in {"", "none"}:
                    final_source = fallback_source
                else:
                    final_source = fallback_field
                break
    if final_entry is None:
        execution_entry = _safe_float(entry.get("execution_entry"))
        execution_status = str(entry.get("execution_entry_status") or "").strip().lower()
        if execution_entry is not None and execution_status == "executable":
            final_entry = execution_entry
            final_source = str(entry.get("execution_entry_source") or "").strip().lower()
    if final_source in ENTRY_SOURCE_ENUM:
        return final_entry, final_source
    return final_entry, (_display_entry_source_for_row(entry) if final_entry is not None else "none")


def _apply_locked_final_entry_projection(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    if not _final_entry_lock_enabled():
        return entry
    out = dict(entry)
    if not bool(out.get("final_entry_locked")):
        return out
    final_entry = _safe_float(out.get("final_entry"))
    final_source = str(out.get("final_entry_source") or "").strip().lower()
    if final_source not in ENTRY_SOURCE_ENUM:
        final_source = _display_entry_source_for_row(out) if final_entry is not None else "none"
    out["final_entry"] = final_entry
    out["final_entry_source"] = final_source
    if final_entry is None:
        out["entry"] = None
        out["entry_source"] = "none"
        out["entry_status"] = "missing"
        out["display_entry"] = None
        out["display_entry_source"] = "none"
        out["display_entry_status"] = "missing"
        return out
    out["entry"] = final_entry
    out["entry_source"] = final_source
    out["entry_status"] = "displayable"
    out["display_entry"] = final_entry
    out["display_entry_source"] = final_source
    out["display_entry_status"] = "displayable"
    return out


def _has_canonical_level_tuple(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    entry_value = _safe_float(entry.get("entry"))
    stop_loss = _safe_float(entry.get("stop_loss"))
    if stop_loss is None:
        stop_loss = _safe_float(entry.get("stop"))
    target = _safe_float(entry.get("target"))
    return entry_value is not None and stop_loss is not None and target is not None


def _derive_review_queue_row_kind(entry: dict) -> str:
    if not isinstance(entry, dict):
        return ADVISORY_ONLY_ROW_KIND
    if _is_blocked_contract_row(entry):
        return ADVISORY_ONLY_ROW_KIND
    if str(entry.get("final_action") or "").strip().upper() == "BLOCK":
        return ADVISORY_ONLY_ROW_KIND
    if bool(entry.get("non_canonical_levels")):
        return ADVISORY_ONLY_ROW_KIND
    if not _has_canonical_level_tuple(entry):
        return ADVISORY_ONLY_ROW_KIND
    return CANONICAL_ROW_KIND


def _lock_final_entry(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    if not _final_entry_lock_enabled():
        return entry
    out = dict(entry)
    final_entry, final_source = _resolve_final_entry(out)
    out["final_entry"] = final_entry
    out["final_entry_source"] = final_source
    out["final_entry_locked"] = True
    out = recompute_levels_from_final_entry(
        out,
        rr_default=float(getattr(cfg, "TARGET_RR_DEFAULT", 1.5)) if cfg else 1.5,
        **_option_stop_policy_params(),
    )
    out["row_kind"] = _derive_review_queue_row_kind(out)
    out["non_canonical_levels"] = bool(out.get("non_canonical_levels")) or out["row_kind"] != CANONICAL_ROW_KIND
    if (
        out["row_kind"] != CANONICAL_ROW_KIND
        and not _is_blocked_contract_row(out)
        and str(out.get("final_action") or "").strip().upper() != "BLOCK"
        and _candidate_row_corruption_log_enabled()
    ):
        log_corrupt_advisory_row(out, str(out.get("level_recompute_reason") or "non_canonical_levels"))
    return _apply_locked_final_entry_projection(out)


def _reconcile_locked_final_entry(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    if not _final_entry_lock_enabled():
        return entry
    out = dict(entry)
    if not bool(out.get("final_entry_locked")):
        return out
    out = _apply_locked_final_entry_projection(out)
    out = recompute_levels_from_final_entry(
        out,
        rr_default=float(getattr(cfg, "TARGET_RR_DEFAULT", 1.5)) if cfg else 1.5,
        **_option_stop_policy_params(),
    )
    out["row_kind"] = _derive_review_queue_row_kind(out)
    out["non_canonical_levels"] = bool(out.get("non_canonical_levels")) or out["row_kind"] != CANONICAL_ROW_KIND
    if (
        out["row_kind"] != CANONICAL_ROW_KIND
        and not _is_blocked_contract_row(out)
        and str(out.get("final_action") or "").strip().upper() != "BLOCK"
        and _candidate_row_corruption_log_enabled()
    ):
        log_corrupt_advisory_row(out, str(out.get("level_recompute_reason") or "non_canonical_levels"))
    return _apply_locked_final_entry_projection(out)


def _first_present_float(mapping: dict, keys: tuple[str, ...]) -> float | None:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        if key not in mapping:
            continue
        value = _safe_float(mapping.get(key))
        if value is not None:
            return value
    return None


def _validation_reference_price(
    entry: dict,
    current_ltp: float | None = None,
    *,
    allow_live_ltp: bool = True,
) -> tuple[float | None, str | None]:
    for field_name in ("expected_entry", "suggested_entry", "entry_price"):
        value = _safe_float(entry.get(field_name))
        if value is not None:
            return value, field_name
    entry_val = _safe_float(entry.get("entry"))
    if entry_val is not None:
        return entry_val, "entry"
    signal_price = _safe_float(entry.get("signal_price"))
    if signal_price is not None:
        return signal_price, "signal_price"
    if allow_live_ltp:
        live_ltp = _safe_float(current_ltp)
        if live_ltp is None:
            live_ltp = _safe_float(entry.get("current_ltp"))
        if live_ltp is not None:
            return live_ltp, "current_ltp"
    return None, None


def _is_stale_pre_validation_entry(
    current_entry: float | None,
    executable_reference: float | None,
) -> bool:
    if current_entry is None or executable_reference is None or executable_reference <= 0:
        return current_entry is None and executable_reference is not None
    mismatch_pct = _safe_float(getattr(cfg, "OPTION_ENTRY_MISMATCH_PCT", 0.03))
    threshold = float(mismatch_pct if mismatch_pct is not None and mismatch_pct > 0 else 0.03)
    diff = abs(float(current_entry) - float(executable_reference)) / float(executable_reference)
    return bool(diff > threshold)


def _quote_spread_pct(entry: dict) -> float | None:
    spread = _safe_float(entry.get("spread_pct"))
    if spread is not None:
        return spread
    bid = _safe_float(entry.get("best_bid") or entry.get("opt_bid") or entry.get("bid"))
    ask = _safe_float(entry.get("best_ask") or entry.get("opt_ask") or entry.get("ask"))
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return None
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return None
    return (ask - bid) / mid


def _entry_execution_mode(entry: dict) -> str:
    if isinstance(entry, dict):
        for key in ("execution_mode", "mode"):
            value = str(entry.get(key) or "").strip().upper()
            if value:
                return value
        market_context = entry.get("market_context")
        if isinstance(market_context, dict):
            value = str(market_context.get("execution_mode") or "").strip().upper()
            if value:
                return value
    try:
        return str(getattr(cfg, "EXECUTION_MODE", "") or "").strip().upper()
    except Exception:
        return ""


def _entry_execution_mode_explicit(entry: dict) -> str:
    if isinstance(entry, dict):
        for key in ("execution_mode", "mode"):
            value = str(entry.get(key) or "").strip().upper()
            if value:
                return value
        market_context = entry.get("market_context")
        if isinstance(market_context, dict):
            value = str(market_context.get("execution_mode") or "").strip().upper()
            if value:
                return value
    return ""


def _entry_market_open(mode_for_entry: str, allow_stale_quotes_for_entry: bool) -> bool:
    mode_key = str(mode_for_entry or "").strip().upper()
    if mode_key in {"OFFHOURS", "PAPER", "BACKTEST"}:
        return False
    return not bool(allow_stale_quotes_for_entry)


def _coerce_optional_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off"}:
        return False
    return None


def _resolve_entry_market_open(
    entry: dict,
    mode_for_entry: str,
    allow_stale_quotes_for_entry: bool,
) -> tuple[bool, str]:
    symbol = None
    explicit_entry_market_open = None
    explicit_market_context_open = None
    explicit_freshness_market_open = None
    exchange_clock_result = None
    if isinstance(entry, dict):
        symbol = str(entry.get("symbol") or "").strip().upper() or None
        explicit_entry_market_open = _coerce_optional_bool(entry.get("market_open"))
        if explicit_entry_market_open is not None:
            logger.debug(
                "review_queue_market_open_resolved symbol=%s mode_for_entry=%s entry_market_open=%s market_context_market_open=%s freshness_market_open=%s exchange_clock=%s final_market_open=%s final_source=%s",
                symbol,
                str(mode_for_entry or "").strip().upper(),
                explicit_entry_market_open,
                explicit_market_context_open,
                explicit_freshness_market_open,
                exchange_clock_result,
                explicit_entry_market_open,
                "entry.market_open",
            )
            return explicit_entry_market_open, "entry.market_open"
        market_context = entry.get("market_context")
        if isinstance(market_context, dict):
            explicit_market_context_open = _coerce_optional_bool(market_context.get("market_open"))
            if explicit_market_context_open is not None:
                logger.debug(
                    "review_queue_market_open_resolved symbol=%s mode_for_entry=%s entry_market_open=%s market_context_market_open=%s freshness_market_open=%s exchange_clock=%s final_market_open=%s final_source=%s",
                    symbol,
                    str(mode_for_entry or "").strip().upper(),
                    explicit_entry_market_open,
                    explicit_market_context_open,
                    explicit_freshness_market_open,
                    exchange_clock_result,
                    explicit_market_context_open,
                    "market_context.market_open",
                )
                return explicit_market_context_open, "market_context.market_open"
        explicit_freshness_market_open = _coerce_optional_bool(entry.get("freshness_market_open"))
        if explicit_freshness_market_open is not None:
            logger.debug(
                "review_queue_market_open_resolved symbol=%s mode_for_entry=%s entry_market_open=%s market_context_market_open=%s freshness_market_open=%s exchange_clock=%s final_market_open=%s final_source=%s",
                symbol,
                str(mode_for_entry or "").strip().upper(),
                explicit_entry_market_open,
                explicit_market_context_open,
                explicit_freshness_market_open,
                exchange_clock_result,
                explicit_freshness_market_open,
                "entry.freshness_market_open",
            )
            return explicit_freshness_market_open, "entry.freshness_market_open"
    try:
        exchange_clock_result = bool(is_market_open_ist())
        logger.debug(
            "review_queue_market_open_resolved symbol=%s mode_for_entry=%s entry_market_open=%s market_context_market_open=%s freshness_market_open=%s exchange_clock=%s final_market_open=%s final_source=%s",
            symbol,
            str(mode_for_entry or "").strip().upper(),
            explicit_entry_market_open,
            explicit_market_context_open,
            explicit_freshness_market_open,
            exchange_clock_result,
            exchange_clock_result,
            "exchange_clock",
        )
        return exchange_clock_result, "exchange_clock"
    except Exception:
        pass
    final_market_open = _entry_market_open(mode_for_entry, allow_stale_quotes_for_entry)
    logger.debug(
        "review_queue_market_open_resolved symbol=%s mode_for_entry=%s entry_market_open=%s market_context_market_open=%s freshness_market_open=%s exchange_clock=%s final_market_open=%s final_source=%s",
        symbol,
        str(mode_for_entry or "").strip().upper(),
        explicit_entry_market_open,
        explicit_market_context_open,
        explicit_freshness_market_open,
        exchange_clock_result,
        final_market_open,
        "mode_fallback",
    )
    return final_market_open, "mode_fallback"


def _manual_approval_required_for_entry(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    if bool(entry.get("unresolved_contract")):
        return False
    if not _has_valid_broker_contract(entry):
        return False
    if not _cfg_bool("MANUAL_APPROVAL", False):
        return False
    required_modes = _cfg_csv_set("APPROVAL_REQUIRED_MODES", "PAPER,LIVE")
    mode = _entry_execution_mode(entry)
    if mode and mode not in required_modes:
        return False
    return True


def _allow_rest_fallback_for_mode(mode: str | None) -> bool:
    mode_key = str(mode or "").strip().upper()
    return mode_key in {"PAPER", "SIM", "OFFHOURS", "ADVISORY", "PLANNING"}


def _is_synthetic_offhours_row(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    option_ltp_source = str(entry.get("option_ltp_source") or "").strip().lower()
    quote_source = str(entry.get("quote_source") or "").strip().lower()
    return option_ltp_source == "synthetic_offhours" or quote_source == "synthetic_offhours"


def _mark_synthetic_offhours_origin(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    quote_source = str(entry.get("quote_source") or "").strip().lower()
    option_ltp_source = str(entry.get("option_ltp_source") or "").strip().lower()
    validation_reference_source = str(entry.get("validation_reference_source") or "").strip().lower()
    if (
        quote_source == "synthetic_offhours"
        or option_ltp_source == "synthetic_offhours"
        or validation_reference_source == "synthetic_offhours"
    ):
        entry["_origin_synthetic_offhours"] = True
        if entry.get("entry_price") not in (None, "", "None") and entry.get("_synthetic_entry_price_original") in (None, "", "None"):
            entry["_synthetic_entry_price_original"] = entry.get("entry_price")
    return entry


def _resolve_quote_validation_status(entry: dict, proposed_status=None) -> str | None:
    if not isinstance(entry, dict):
        return str(proposed_status or "").strip() or None
    entry = _mark_synthetic_offhours_origin(entry)
    if entry.get("_origin_synthetic_offhours"):
        return "OFFHOURS_SYNTHETIC"
    proposed = str(proposed_status or "").strip()
    if proposed:
        proposed_upper = proposed.upper()
        if proposed_upper in {"NO_LIVE_OPTION_FEED", "MISSING_OPTION_TOKEN"}:
            freshness_reason = str(entry.get("freshness_reason") or "").strip().lower()
            clear_reason = str(entry.get("entry_clear_reason") or "").strip().lower()
            price_age_sec = _safe_float(entry.get("price_age_sec"))
            quote_age_sec = _safe_float(entry.get("quote_age_sec"))
            stale_threshold_sec = _safe_float(entry.get("freshness_threshold_sec"))
            age_exceeds_threshold = (
                price_age_sec is not None
                and stale_threshold_sec is not None
                and float(price_age_sec) > float(stale_threshold_sec)
            ) or (
                quote_age_sec is not None
                and stale_threshold_sec is not None
                and float(quote_age_sec) > float(stale_threshold_sec)
            )
            if (
                freshness_reason == "quote_exceeds_threshold"
                or clear_reason == "stale_quote"
                or age_exceeds_threshold
            ):
                return "STALE_OPTION_LTP"
        return proposed
    current = str(entry.get("quote_validation_status") or "").strip()
    return current or None


def _preserve_offhours_quote_validation_status(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    out = _mark_synthetic_offhours_origin(out)
    if out.get("_origin_synthetic_offhours"):
        out["quote_validation_status"] = "OFFHOURS_SYNTHETIC"
    return out


def _is_offhours_displayable(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    return bool(
        entry.get("_origin_synthetic_offhours")
        and str(entry.get("entry_status") or "").strip().lower() == "displayable"
    )


def _finalize_suggested_entry(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    if _is_offhours_displayable(out):
        preferred = (
            out.get("_synthetic_entry_price_original")
            or out.get("entry_price")
            or out.get("expected_entry")
            or out.get("suggested_entry")
            or out.get("entry")
        )
        if preferred not in (None, "", "None"):
            out["entry_price"] = preferred
            out["entry"] = preferred
            out["suggested_entry"] = preferred
            out["expected_entry"] = preferred
            out["validation_reference_price"] = preferred
            out["validation_reference_source"] = "synthetic_offhours"
    return out


def _apply_synthetic_offhours_advisory_lifecycle(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    if not out.get("_origin_synthetic_offhours"):
        return out
    base = (
        _safe_float(out.get("_synthetic_entry_price_original"))
        or _safe_float(out.get("entry_price"))
        or _safe_float(out.get("suggested_entry"))
        or _safe_float(out.get("expected_entry"))
        or _safe_float(out.get("entry"))
    )
    if base is None:
        return out
    display_source = _display_entry_source_for_row(out)
    out["display_entry"] = base
    out["display_entry_status"] = "displayable"
    out["display_entry_source"] = display_source
    out["execution_entry"] = None
    out["execution_entry_status"] = "non_executable"
    out["execution_entry_source"] = "none"
    out["entry"] = base
    out["entry_status"] = "displayable"
    out["entry_source"] = display_source
    out["entry_reason"] = _display_entry_reason_for_source(display_source)
    out["entry_price"] = base
    out["suggested_entry"] = base
    out["expected_entry"] = base
    out["quote_validation_status"] = "OFFHOURS_SYNTHETIC"
    out["validation_reference_price"] = base
    out["validation_reference_source"] = "synthetic_offhours"
    out["current_ltp"] = None
    out["option_ltp_timestamp"] = None
    out["execution_allowed"] = False
    out["is_executable"] = False
    return out


def _is_live_feed_failure_status(value) -> bool:
    return str(value or "").strip().upper() in {"NO_LIVE_OPTION_FEED", "MISSING_OPTION_TOKEN"}


def _repair_live_feed_failure_provenance(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    if _is_synthetic_offhours_row(entry):
        return entry
    if str(entry.get("instrument") or entry.get("instrument_type") or "").strip().upper() != "OPT":
        return entry
    if str(entry.get("permission") or "").strip().upper() != "BLOCK":
        return entry
    if not (
        _is_live_feed_failure_status(entry.get("entry_status"))
        or _is_live_feed_failure_status(entry.get("quote_validation_status"))
    ):
        return entry
    if not (
        bool(entry.get("subscription_failed"))
        or _safe_float(entry.get("current_ltp")) is None
    ):
        return entry
    if not str(entry.get("option_ltp_source") or "").strip():
        entry["option_ltp_source"] = "subscription_failed"
    if str(entry.get("quote_source") or "").strip().lower() in {"", "unknown"}:
        entry["quote_source"] = "subscription_failed"
    entry["subscription_failed"] = True
    hard_blockers = [str(code or "").strip() for code in list(entry.get("hard_blockers") or []) if str(code or "").strip()]
    if hard_blockers and set(hard_blockers).issubset({"NO_TOKEN", "unresolved_contract", "MISSING_OPTION_TOKEN"}):
        entry["hard_blockers"] = ["NO_LIVE_OPTION_FEED"]
        blockers = [
            str(code or "").strip()
            for code in list(entry.get("blockers") or [])
            if str(code or "").strip() and str(code or "").strip() not in {"NO_TOKEN", "unresolved_contract", "MISSING_OPTION_TOKEN"}
        ]
        entry["blockers"] = ["NO_LIVE_OPTION_FEED", *blockers]
    return entry


def _clear_synthetic_offhours_state_for_live_takeover(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    entry_status = str(entry.get("entry_status") or "").strip().upper()
    option_ltp_source = str(entry.get("option_ltp_source") or "").strip().lower()
    quote_source = str(entry.get("quote_source") or "").strip().lower()
    preserve_subscription_failed = bool(
        _is_live_feed_failure_status(entry_status)
        or option_ltp_source == "subscription_failed"
        or quote_source == "subscription_failed"
    )
    for field in ("blockers", "hard_blockers", "soft_penalties", "warnings", "tradable_reasons_blocking"):
        values = [
            str(value or "").strip()
            for value in list(entry.get(field) or [])
            if str(value or "").strip() not in {"NO_LIVE_OPTION_FEED", "OFFHOURS_SYNTHETIC"}
        ]
        if values:
            entry[field] = values
        else:
            entry.pop(field, None)
    for field in ("hard_reason", "final_blocker", "permission_reason"):
        text = str(entry.get(field) or "").strip()
        if text in {"NO_LIVE_OPTION_FEED", "OFFHOURS_SYNTHETIC"}:
            entry.pop(field, None)
    if not preserve_subscription_failed:
        entry.pop("subscription_failed", None)
    if str(entry.get("validation_reference_source") or "").strip().lower() == "synthetic_offhours":
        entry.pop("validation_reference_source", None)
    if str(entry.get("entry_status") or "").strip().upper() == "OFFHOURS_SYNTHETIC":
        entry.pop("entry_status", None)
    return entry


def _clear_synthetic_pricing_state_for_live_takeover(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    for field in (
        "expected_entry",
        "expected_entry_source",
        "entry_ref_price",
        "validation_reference_price",
        "validation_reference_source",
        "pre_validation_entry",
    ):
        entry.pop(field, None)
    return entry


def _should_force_live_reference_for_takeover(
    entry: dict,
    *,
    current_ltp: float | None,
    ltp_ts_epoch: float | None,
) -> bool:
    if not isinstance(entry, dict):
        return False
    if current_ltp is None or ltp_ts_epoch is None:
        return False
    if _is_synthetic_offhours_row(entry):
        return True
    return str(entry.get("strategy") or "").strip().upper() == "QUICK_SYNTH"


def _current_non_lifecycle_blockers(entry: dict) -> list[str]:
    blockers: list[str] = []
    for source in (
        list(entry.get("tradable_reasons_blocking") or []),
    ):
        for reason in source:
            text = str(reason or "").strip()
            if not text or text in blockers or text in TARGET_BLOCKER_CODES:
                continue
            blockers.append(text)
    for field in ("hard_reason", "final_blocker"):
        text = str(entry.get(field) or "").strip()
        if text.upper().startswith("HARD_"):
            continue
        if not text or text in blockers or text in TARGET_BLOCKER_CODES:
            continue
        blockers.append(text)
    return blockers


def _derive_advisory_readiness(entry: dict, blockers: list[str]) -> str:
    permission = str(entry.get("permission") or "").strip().upper()
    if bool(entry.get("unresolved_contract")) or permission == "BLOCK" or any(
        code in {"NO_TOKEN", "NO_LIVE_OPTION_FEED", "unresolved_contract"} for code in blockers
    ):
        return "BLOCKED"
    if permission == "EXECUTE" and not blockers:
        return "READY"
    if permission == "QUEUE_ONLY" and not blockers:
        return "QUEUE_ONLY"
    return "ADVISORY_ONLY"


def _dedupe_issue_codes(values) -> list[str]:
    out: list[str] = []
    for value in list(values or []):
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _derive_confidence_rejection_stage(entry: dict) -> str | None:
    if not isinstance(entry, dict):
        return None
    hard_blockers = list(entry.get("hard_blockers") or [])
    if hard_blockers:
        return "hard_gate"
    raw_threshold = _safe_float(entry.get("confidence_raw_gate_threshold"))
    final_threshold = _safe_float(entry.get("confidence_final_gate_threshold"))
    stages = [
        ("model_raw", _safe_float(entry.get("confidence_model_raw"))),
        ("micro", _safe_float(entry.get("confidence_after_micro"))),
        ("alpha", _safe_float(entry.get("confidence_after_alpha"))),
        ("latency", _safe_float(entry.get("confidence_after_latency"))),
        ("soft_veto", _safe_float(entry.get("confidence_after_soft_veto"))),
    ]
    if raw_threshold is not None:
        previous_value = None
        for stage_name, stage_value in stages:
            if stage_value is None:
                continue
            if stage_value < raw_threshold and (previous_value is None or previous_value >= raw_threshold):
                return stage_name
            previous_value = stage_value
    final_conf = _safe_float(entry.get("confidence_final"))
    after_soft_veto = _safe_float(entry.get("confidence_after_soft_veto"))
    if final_threshold is not None and final_conf is not None and final_conf < final_threshold:
        if after_soft_veto is not None and after_soft_veto < final_threshold:
            return "soft_veto"
        return "final_gate"
    if str(entry.get("permission_reason") or "").strip().upper() == "SOFT_CONFIDENCE_BELOW_THRESHOLD":
        return "final_gate"
    return None


def _promotion_confidence(entry: dict) -> float | None:
    if not isinstance(entry, dict):
        return None
    for field in (
        "gating_final_confidence",
        "confidence_final",
        "permission_confidence",
        "global_confidence",
        "confidence",
    ):
        value = _safe_float(entry.get(field))
        if value is not None:
            return value
    return None


def _promotion_quote_source(entry: dict) -> str:
    return str(entry.get("quote_source") or entry.get("option_ltp_source") or "").strip().lower()


def _promotion_quote_is_trusted(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    if _is_synthetic_offhours_row(entry):
        return False
    quote_source = _promotion_quote_source(entry)
    if not quote_source:
        return (
            _safe_float(entry.get("execution_entry")) is not None
            and str(entry.get("execution_entry_status") or "").strip().lower() == "executable"
        )
    return quote_source in {"tick_store", "rest_fallback", "live"}


def _promotion_quote_is_fresh(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    quote_validation_status = str(entry.get("quote_validation_status") or "").strip().upper()
    if quote_validation_status in {
        "OFFHOURS_SYNTHETIC",
        "NO_LIVE_OPTION_FEED",
        "MISSING_OPTION_TOKEN",
        "NON_EXECUTABLE",
        "PRICE_MISMATCH",
        "MISSING",
    }:
        return False
    quote_age_sec = _canonical_quote_age_sec(entry)
    if quote_age_sec is None:
        return quote_validation_status in {"OK", "LIVE_OK", "VALID", "REST_FALLBACK"}
    try:
        max_age = float(getattr(cfg, "OPTION_LTP_SLA_SEC", 2.0))
    except Exception:
        max_age = 2.0
    return float(quote_age_sec) <= float(max_age)


def _promotion_rank_is_eligible(entry: dict) -> bool:
    selected = entry.get("selected_for_execution")
    if selected is True:
        return True
    rank_global = _safe_float(entry.get("rank_global"))
    if rank_global is None:
        return True
    try:
        rank_cap = int(getattr(cfg, "PERMISSION_PROMOTION_TOP_RANK_MAX", 2))
    except Exception:
        rank_cap = 2
    return int(rank_global) <= max(1, int(rank_cap))


def _append_permission_promotion_trace(entry: dict, *, old_permission: str, old_final_action: str) -> None:
    if not isinstance(entry, dict):
        return
    record = {
        "ts_epoch": float(time.time()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trade_id": entry.get("trade_id"),
        "old_permission": old_permission,
        "new_permission": entry.get("permission"),
        "old_final_action": old_final_action,
        "new_final_action": entry.get("final_action"),
        "confidence_final": _promotion_confidence(entry),
        "execution_entry": _safe_float(entry.get("execution_entry")),
        "execution_entry_status": entry.get("execution_entry_status"),
        "tradable": entry.get("tradable"),
        "promotion_reason": entry.get("promotion_reason"),
    }
    _append_jsonl([_promotion_trace_path()], record)


def _downgrade_execution_intent(out, action, block_reason):
    if out.get("permission") not in ("REJECT", "BLOCK", "QUEUE_ONLY"):
        out["permission_downgraded_from"] = out.get("permission")
        out["permission_downgrade_reason"] = block_reason
    
    out["final_action"] = "QUEUE_ONLY" if action == "QUEUE_ONLY" else action
    out["permission"] = "QUEUE_ONLY" if action == "QUEUE_ONLY" else action
    out["execution_allowed"] = False
    out["execution_ok"] = False
    out["eligible_for_execution"] = False
    out["is_executable"] = False
    out["promotion_block_reason"] = block_reason
    out["status"] = "QUEUE_ONLY"
    # Note: we do NOT overwrite status_raw here so we don't break tests that expect PLANNING.

def _normalize_truth_quality(out: dict) -> dict:
    is_exec = out.get("final_action") == "EXECUTE"
    truth = str(out.get("truth_quality") or "").strip().upper()

    if out.get("is_synthetic"):
        out["truth_quality"] = "TRUTH_SYNTHETIC_BLOCKED"
        out["truth_allows_execution"] = False
        out["truth_block_reason"] = "synthetic_blocked"
    elif _is_fallback_candidate(out) or out.get("is_recovered_fallback"):
        out["truth_quality"] = "TRUTH_FALLBACK_BLOCKED"
        out["truth_allows_execution"] = False
        out["truth_block_reason"] = "fallback_blocked"
    elif out.get("stale_quote_flag"):
        out["truth_quality"] = "TRUTH_STALE_BLOCKED"
        out["truth_allows_execution"] = False
        out["truth_block_reason"] = "stale_blocked"
    elif truth == "DEGRADED":
        if is_exec:
            out["truth_quality"] = "TRUTH_DEGRADED_ALLOWED"
            out["truth_allows_execution"] = True
            out["truth_block_reason"] = None
        else:
            out["truth_quality"] = "TRUTH_DEGRADED_BLOCKED"
            out["truth_allows_execution"] = False
            out["truth_block_reason"] = "degraded_blocked"
    elif truth in ("REAL", "LIVE", "TRUTH_LIVE_FRESH"):
        out["truth_quality"] = "TRUTH_LIVE_FRESH"
        out["truth_allows_execution"] = True
        out["truth_block_reason"] = None
    elif out.get("truth_allows_execution") is True and out.get("quote_truth_state") in ("live", "fresh"):
        out["truth_quality"] = "TRUTH_LIVE_FRESH"
        out["truth_allows_execution"] = True
        out["truth_block_reason"] = None
    else:
        out["truth_quality"] = "TRUTH_UNKNOWN_BLOCKED"
        out["truth_allows_execution"] = False
        out["truth_block_reason"] = "unknown_truth"

    if out.get("final_action") == "EXECUTE" and out["truth_quality"] not in ("TRUTH_LIVE_FRESH", "TRUTH_DEGRADED_ALLOWED"):
        _downgrade_execution_intent(out, "REJECT", f"truth_violation_{out['truth_quality']}")

    return out

def _maybe_promote_execute_candidate(entry: dict) -> dict:
    out = _maybe_promote_execute_candidate_impl(entry)

    if out.get("final_action") == "EXECUTE":
        # Rule: If any downstream final decision is not EXECUTE, downgrade
        if out.get("execution_ok") is False:
            _downgrade_execution_intent(out, "REJECT", "execution_ok_false")
        elif str(out.get("order_policy") or "").strip().lower() == "reject":
            _downgrade_execution_intent(out, "REJECT", "order_policy_reject")
        elif str(out.get("decision_action") or "").upper() in ("REJECT", "QUEUE"):
            _downgrade_execution_intent(out, "REJECT", "decision_engine_reject")

    return _normalize_truth_quality(out)

def _maybe_promote_execute_candidate_impl(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    if _is_fallback_candidate(out):
        out = _apply_fallback_execution_kill(out)
        out["promotion_block_reason"] = _fallback_non_executable_reason(out)
        return out
    if _is_synthetic_advisory_entry(out):
        out["promotion_block_reason"] = "synthetic_advisory"
        return out
    soft_reject_execute_block_enable = bool(
        getattr(cfg, "DECISION_ENGINE_SOFT_REJECT_EXECUTE_BLOCK_ENABLE", False)
    )
    if soft_reject_execute_block_enable and _blocks_execute_due_to_soft_reject(out):
        out["promotion_block_reason"] = "soft_reject_weak_signal_blocks_execute"
        return out
    try:
        promotion_enabled = bool(getattr(cfg, "PERMISSION_PROMOTION_ENABLE", True))
    except Exception:
        promotion_enabled = True
    if not promotion_enabled:
        return out
    old_permission = str(out.get("permission") or "").strip().upper()
    old_final_action = str(out.get("final_action") or "").strip().upper()
    readiness = str(out.get("readiness") or "").strip().upper()
    if old_permission not in {"QUEUE_ONLY", "ADVISORY_ONLY"}:
        return out
    if old_final_action not in {"QUEUE_ONLY", "ADVISORY_ONLY"}:
        return out
    if readiness not in {"QUEUE_ONLY", "ADVISORY_ONLY", "READY"}:
        return out
    if _safe_float(out.get("execution_entry")) is None:
        return out
    if str(out.get("execution_entry_status") or "").strip().lower() != "executable":
        return out
    tradable_value = out.get("tradable")
    if tradable_value is False:
        return out
    if str(tradable_value or "").strip().lower() in {"false", "0", "no", "off"}:
        return out
    if bool(out.get("approval_blocked")) or bool(out.get("unresolved_contract")):
        return out
    if bool(_dedupe_issue_codes(list(out.get("hard_blockers") or []))):
        return out
    if out.get("execution_ok") is False:
        return out
    if str(out.get("order_policy") or "").strip().lower() == "reject":
        return out
    if not _promotion_quote_is_trusted(out):
        return out
    if not _promotion_quote_is_fresh(out):
        return out
    if not _promotion_rank_is_eligible(out):
        return out
    decision = evaluate_candidate_decision(out)
    out["raw_score"] = decision.get("raw_score")
    out["final_score"] = decision.get("final_score")
    out["candidate_class"] = decision.get("candidate_class")
    out["class_score_cap"] = decision.get("class_score_cap")
    out["feed_confidence"] = (decision.get("feed") or {}).get("feed_confidence")
    out["feed_state"] = (decision.get("feed") or {}).get("feed_state")
    out["decision_reason"] = decision.get("decision_reason")
    out["execution_ready"] = decision.get("execution_ready")
    out["readiness_reasons"] = list(decision.get("readiness_reasons") or [])
    out["adaptive_execution_threshold"] = decision.get("adaptive_execution_threshold")
    out["score_inflation_ratio"] = decision.get("score_inflation_ratio")

    action = str(decision.get("decision_action") or "REJECT").upper()
    if action == "QUEUE":
        out["permission"] = "QUEUE_ONLY"
        out["final_action"] = "QUEUE_ONLY"
        out["readiness"] = "QUEUE_ONLY"
        out["status"] = "QUEUE_ONLY"
        out["execution_status"] = "queue_only"
        out["execution_allowed"] = False
        out["execution_ok"] = False
        out["eligible_for_execution"] = True
        out["is_executable"] = False
        out["promotion_block_reason"] = str(decision.get("decision_reason") or "queue_only")
        return out
    if action != "EXECUTE":
        out["promotion_block_reason"] = str(
            decision.get("decision_reason") or "decision_engine_reject"
        )
        return out

    out["permission_promoted_from"] = old_permission
    out["final_action_promoted_from"] = old_final_action
    out["promotion_reason"] = str(decision.get("decision_reason") or "decision_engine_execute")
    out["permission"] = "EXECUTE"
    out["final_action"] = "EXECUTE"
    out["readiness"] = "READY"
    out["status"] = "READY"
    out["execution_allowed"] = True
    out["execution_ok"] = True
    out["eligible_for_execution"] = True
    out["execution_status"] = "executable"
    out["is_executable"] = True
    _append_permission_promotion_trace(out, old_permission=old_permission, old_final_action=old_final_action)
    return out


def _log_confidence_rejection(entry: dict) -> None:
    if not isinstance(entry, dict):
        return
    stage = str(entry.get("confidence_rejection_stage") or "").strip()
    if not stage:
        return
    logger.info(
        "confidence_rejection symbol=%s strike=%s type=%s stage=%s raw_conf=%s final_conf=%s raw_threshold=%s final_threshold=%s",
        entry.get("symbol"),
        entry.get("strike"),
        entry.get("option_type") or entry.get("type") or entry.get("right"),
        stage,
        _safe_float(entry.get("confidence_raw")),
        _safe_float(entry.get("confidence_final")),
        _safe_float(entry.get("confidence_raw_gate_threshold")),
        _safe_float(entry.get("confidence_final_gate_threshold")),
    )


def _current_issue_codes(entry: dict) -> list[str]:
    issue_codes = _dedupe_issue_codes(list(entry.get("blockers") or []) + _current_non_lifecycle_blockers(entry))
    for field in ("validation_issue_code", "quote_validation_status", "hard_reason", "final_blocker", "entry_status"):
        text = str(entry.get(field) or "").strip()
        if not text:
            continue
        if field in {"entry_status", "quote_validation_status"} and text.upper() in {"DISPLAYABLE", "NON_EXECUTABLE", "MISSING"}:
            continue
        if field in {"validation_issue_code", "entry_status", "quote_validation_status"} and text.upper() in {"OK", "LIVE_OK", "VALID", "REST_FALLBACK", "OFFHOURS_SYNTHETIC"}:
            continue
        if field in {"hard_reason", "final_blocker"} and text.upper().startswith("HARD_"):
            continue
        if text not in issue_codes:
            issue_codes.append(text)
    if (
        str(entry.get("entry_clear_reason") or "").strip().lower() == "stale_quote"
        and str(entry.get("freshness_reason") or "").strip().lower() == "quote_exceeds_threshold"
        and not _is_synthetic_offhours_row(entry)
        and "STALE_OPTION_LTP" not in issue_codes
    ):
        issue_codes.append("STALE_OPTION_LTP")
    return _dedupe_issue_codes(issue_codes)


def _apply_issue_classification(
    entry: dict,
    *,
    mode_for_entry: str,
    allow_stale_quotes_for_entry: bool,
) -> dict:
    if not isinstance(entry, dict):
        return entry
    issue_codes = _current_issue_codes(entry)
    current_ltp = _safe_float(entry.get("current_ltp"))
    validation_reference_price = _safe_float(entry.get("validation_reference_price"))
    execution_entry = _safe_float(entry.get("execution_entry"))
    reference_price_for_mismatch = validation_reference_price
    if reference_price_for_mismatch is None:
        for fallback_field in ("expected_entry", "entry_price", "entry", "display_entry"):
            reference_price_for_mismatch = _safe_float(entry.get(fallback_field))
            if reference_price_for_mismatch is not None:
                break
    mismatch_price = execution_entry if execution_entry is not None else current_ltp
    price_mismatch_abs = None
    price_mismatch_pct = None
    if (
        mismatch_price is not None
        and reference_price_for_mismatch is not None
        and float(reference_price_for_mismatch) > 0.0
    ):
        try:
            price_mismatch_abs = abs(float(mismatch_price) - float(reference_price_for_mismatch))
            price_mismatch_pct = float(price_mismatch_abs) / abs(float(reference_price_for_mismatch))
        except Exception:
            price_mismatch_abs = None
            price_mismatch_pct = None
    confidence_raw = _safe_float(entry.get("confidence_base"))
    if confidence_raw is None:
        confidence_raw = _safe_float(entry.get("gating_base_confidence"))
    if confidence_raw is None:
        confidence_raw = _safe_float(entry.get("builder_confidence"))
    if confidence_raw is None:
        confidence_raw = _safe_float(entry.get("permission_confidence"))
    if confidence_raw is None:
        confidence_raw = _safe_float(entry.get("global_confidence"))
    if confidence_raw is None:
        confidence_raw = _safe_float(entry.get("confidence"))
    if confidence_raw is None:
        confidence_raw = _safe_float(entry.get("raw_signal_confidence"))
    confidence_raw_canonical = _safe_float(entry.get("confidence_raw_canonical"))
    if confidence_raw_canonical is None:
        confidence_raw_canonical = confidence_raw
    explicit_confidence_penalty_present = entry.get("confidence_penalty_total") is not None or entry.get("confidence_penalty") is not None
    existing_confidence_penalty = _safe_float(entry.get("confidence_penalty_total"))
    if existing_confidence_penalty is None:
        existing_confidence_penalty = _safe_float(entry.get("confidence_penalty"))
    if existing_confidence_penalty is None and confidence_raw_canonical is not None:
        softened_confidence = _safe_float(entry.get("confidence_final"))
        if softened_confidence is not None:
            existing_confidence_penalty = max(0.0, float(confidence_raw_canonical) - float(softened_confidence))
    if existing_confidence_penalty is None:
        existing_confidence_penalty = 0.0
    confidence_before_soft_veto = _safe_float(entry.get("confidence_before_soft_veto"))
    if confidence_before_soft_veto is None:
        confidence_before_soft_veto = confidence_raw_canonical
    confidence_after_soft_veto = _safe_float(entry.get("confidence_after_soft_veto"))
    if confidence_after_soft_veto is None and confidence_before_soft_veto is not None:
        confidence_after_soft_veto = max(
            0.0,
            min(1.0, float(confidence_before_soft_veto) - float(existing_confidence_penalty)),
        )
    confidence_penalty_soft_veto_total = _safe_float(entry.get("confidence_penalty_soft_veto_total"))
    if confidence_penalty_soft_veto_total is None:
        confidence_penalty_soft_veto_total = 0.0
    confidence_penalty_soft_veto_reasons = _dedupe_issue_codes(
        list(entry.get("confidence_penalty_soft_veto_reasons") or [])
    )
    quote_age_sec = _safe_float(
        _canonical_quote_age_sec(entry)
    )
    best_bid = _safe_float(entry.get("best_bid") or entry.get("bid") or entry.get("opt_bid"))
    best_ask = _safe_float(entry.get("best_ask") or entry.get("ask") or entry.get("opt_ask"))
    market_open_for_entry, _market_open_source = _resolve_entry_market_open(
        entry,
        mode_for_entry,
        allow_stale_quotes_for_entry,
    )
    ctx = {
        "mode": mode_for_entry,
        "market_open": market_open_for_entry,
        "allow_stale_quotes": allow_stale_quotes_for_entry,
        "permission": entry.get("permission"),
        "entry_status": entry.get("entry_status"),
        "subscription_failed": bool(entry.get("subscription_failed")),
        "quote_source": entry.get("option_ltp_source") or entry.get("quote_source"),
        "quote_age_sec": quote_age_sec,
        "current_ltp": current_ltp,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "reference_price": reference_price_for_mismatch,
        "price_mismatch_abs": price_mismatch_abs,
        "price_mismatch_pct": price_mismatch_pct,
        "price_mismatch_persistent": bool(entry.get("price_mismatch_persistent")),
        "price_mismatch_abs_tol": float(
            getattr(cfg, "ISSUE_POLICY_PRICE_MISMATCH_ABS_TOL", 5.0) or 5.0
        ),
        "price_mismatch_pct_tol": float(
            getattr(cfg, "ISSUE_POLICY_PRICE_MISMATCH_PCT_TOL", 0.03) or 0.03
        ),
        "has_executable_quote": bool(
            best_bid is not None
            and best_ask is not None
            and float(best_bid) > 0.0
            and float(best_ask) > 0.0
            and float(best_ask) >= float(best_bid)
        ),
        "advisory_id": entry.get("advisory_id") or entry.get("trade_id") or entry.get("trade_key"),
        "symbol": entry.get("symbol"),
    }
    gating_payload = entry.get("gating") if isinstance(entry.get("gating"), dict) else {}
    permission = str(entry.get("permission") or "").strip().upper()
    permission_base = str(entry.get("permission_base") or "").strip().upper()
    permission_downgraded_from = str(entry.get("permission_downgraded_from") or "").strip().upper()
    apply_execution_hard_gates = bool(
        permission == "EXECUTE"
        or permission_base == "EXECUTE"
        or permission_downgraded_from == "EXECUTE"
    )
    hard_blockers: list[str] = _dedupe_issue_codes(
        gating_payload.get("hard_reasons") if apply_execution_hard_gates else []
    )
    soft_penalties: list[str] = []
    warnings: list[str] = []
    issue_penalty = 0.0
    issue_classifications: list[dict] = []
    for code in issue_codes:
        classification = classify_issue(code, ctx)
        issue_classifications.append(
            {
                "code": classification.code,
                "category": classification.category,
                "penalty": classification.penalty,
                "reason": classification.reason,
                "evidence": dict(classification.evidence or {}),
            }
        )
        if classification.category == ISSUE_CATEGORY_HARD:
            if classification.code not in hard_blockers:
                hard_blockers.append(classification.code)
        elif classification.category == ISSUE_CATEGORY_SOFT:
            if classification.code not in soft_penalties:
                soft_penalties.append(classification.code)
            issue_penalty += float(classification.penalty or 0.0)
        elif classification.category == ISSUE_CATEGORY_WARNING:
            if classification.code not in warnings:
                warnings.append(classification.code)
    relaxed_gate_soft_reasons = _dedupe_issue_codes(list(gating_payload.get("relaxed_soft_reasons") or []))
    relaxed_gate_warning_reasons = _dedupe_issue_codes(list(gating_payload.get("relaxed_warning_reasons") or []))
    relaxed_gate_penalty_total = max(0.0, _safe_float(gating_payload.get("relaxed_soft_penalty_total")) or 0.0)
    for code in relaxed_gate_soft_reasons:
        if code not in soft_penalties:
            soft_penalties.append(code)
        issue_classifications.append(
            {
                "code": code,
                "category": ISSUE_CATEGORY_SOFT,
                "penalty": round(
                    relaxed_gate_penalty_total / max(len(relaxed_gate_soft_reasons), 1),
                    6,
                ) if relaxed_gate_penalty_total > 0 else 0.0,
                "reason": "non_live_gate_relaxed",
                "evidence": {
                    "mode": mode_for_entry,
                    "market_open": market_open_for_entry,
                    "gating_relaxed_context": bool(gating_payload.get("relaxed_context")),
                },
            }
        )
    for code in relaxed_gate_warning_reasons:
        if code not in warnings:
            warnings.append(code)
        issue_classifications.append(
            {
                "code": code,
                "category": ISSUE_CATEGORY_WARNING,
                "penalty": 0.0,
                "reason": "non_live_gate_warning",
                "evidence": {
                    "mode": mode_for_entry,
                    "market_open": market_open_for_entry,
                    "gating_relaxed_context": bool(gating_payload.get("relaxed_context")),
                },
            }
        )
    relaxed_mode = str(mode_for_entry or "").strip().upper() in {"SIM", "PAPER", "OFFHOURS", "ADVISORY", "PLANNING"}
    permission_reason = str(entry.get("permission_reason") or "").strip()
    if (relaxed_mode or not market_open_for_entry) and permission_reason == "missing_regime_conf":
        if permission_reason not in warnings:
            warnings.append(permission_reason)
        issue_classifications.append(
            {
                "code": permission_reason,
                "category": ISSUE_CATEGORY_WARNING,
                "penalty": 0.0,
                "reason": "non_live_missing_regime_conf",
                "evidence": {
                    "mode": mode_for_entry,
                    "market_open": market_open_for_entry,
                    "permission": entry.get("permission"),
                },
            }
        )
    subscription_failed_without_live_quote = bool(
        str(entry.get("instrument") or entry.get("instrument_type") or "").strip().upper() == "OPT"
        and permission == "BLOCK"
        and current_ltp is None
        and (
            _is_live_feed_failure_status(entry.get("entry_status"))
            or _is_live_feed_failure_status(entry.get("quote_validation_status"))
        )
        and hard_blockers
        and set(hard_blockers).issubset({"NO_TOKEN", "unresolved_contract", "MISSING_OPTION_TOKEN"})
    )
    if subscription_failed_without_live_quote:
        hard_blockers = ["NO_LIVE_OPTION_FEED"]
        if str(entry.get("permission_reason") or "").strip() in {"", "unresolved_contract"}:
            entry["permission_reason"] = "NO_LIVE_OPTION_FEED"
        if str(entry.get("hard_reason") or "").strip() in {"", "unresolved_contract"}:
            entry["hard_reason"] = "NO_LIVE_OPTION_FEED"
        if str(entry.get("final_blocker") or "").strip() in {"", "unresolved_contract"}:
            entry["final_blocker"] = "NO_LIVE_OPTION_FEED"
    if (permission == "BLOCK" or bool(entry.get("unresolved_contract"))) and not hard_blockers:
        fallback_code = str(entry.get("hard_reason") or entry.get("permission_reason") or "execution_blocked").strip()
        if fallback_code and fallback_code not in hard_blockers:
            hard_blockers.append(fallback_code)
    confidence_penalty_reasons = _dedupe_issue_codes(
        list(entry.get("confidence_penalty_reasons") or []) + soft_penalties
    )
    if explicit_confidence_penalty_present:
        confidence_penalty_total = max(
            0.0,
            float(existing_confidence_penalty) + float(issue_penalty),
        )
    else:
        confidence_penalty_total = max(
            0.0,
            float(existing_confidence_penalty) + float(issue_penalty) + float(relaxed_gate_penalty_total),
        )
    confidence_final = confidence_raw_canonical if confidence_raw_canonical is not None else confidence_raw
    if confidence_final is not None:
        confidence_final = max(0.0, min(1.0, float(confidence_raw_canonical) - float(confidence_penalty_total)))
    blockers = _dedupe_issue_codes(hard_blockers + soft_penalties + warnings)
    entry["hard_blockers"] = hard_blockers
    entry["soft_penalties"] = soft_penalties
    entry["warnings"] = warnings
    entry["blockers"] = blockers
    entry["builder_confidence"] = _safe_float(entry.get("builder_confidence"))
    if entry["builder_confidence"] is None:
        entry["builder_confidence"] = (
            confidence_after_soft_veto
            if confidence_after_soft_veto is not None
            else _safe_float(entry.get("gating_final_confidence"))
        )
    if entry["builder_confidence"] is None:
        entry["builder_confidence"] = confidence_raw_canonical
    entry["confidence_base"] = confidence_raw_canonical
    entry["gating_base_confidence"] = confidence_raw_canonical
    entry["confidence_raw"] = confidence_raw_canonical
    entry["confidence_raw_canonical"] = confidence_raw_canonical
    entry["confidence_penalty"] = round(float(confidence_penalty_total), 6)
    entry["confidence_penalty_total"] = round(float(confidence_penalty_total), 6)
    entry["confidence_penalty_reasons"] = confidence_penalty_reasons
    entry["confidence_final"] = confidence_final
    existing_gating_final = _safe_float(entry.get("gating_final_confidence"))
    entry["gating_final_confidence"] = (
        existing_gating_final if existing_gating_final is not None else confidence_final
    )
    entry["entry_source"] = (
        entry.get("expected_entry_source")
        or entry.get("entry_price_source")
        or entry.get("validation_reference_source")
        or entry.get("option_ltp_source")
        or entry.get("quote_source")
    )
    entry["issue_classifications"] = issue_classifications
    entry["confidence_before_soft_veto"] = confidence_before_soft_veto
    entry["confidence_after_soft_veto"] = confidence_after_soft_veto
    existing_stage_trace = entry.get("confidence_stage_trace") if isinstance(entry.get("confidence_stage_trace"), dict) else {}
    confidence_after_time_decay = _safe_float(entry.get("confidence_after_time_decay"))
    if confidence_after_time_decay is None:
        confidence_after_time_decay = _safe_float(existing_stage_trace.get("after_time_decay"))
    if confidence_after_time_decay is None:
        confidence_after_time_decay = (
            confidence_after_soft_veto
            if confidence_after_soft_veto is not None
            else _safe_float(entry.get("gating_final_confidence"))
        )
    if confidence_after_time_decay is None:
        confidence_after_time_decay = confidence_final
    confidence_time_decay_factor = _safe_float(entry.get("confidence_time_decay_factor"))
    if confidence_time_decay_factor is None:
        confidence_time_decay_factor = _safe_float(existing_stage_trace.get("time_decay_factor"))
    if confidence_time_decay_factor is None:
        confidence_time_decay_factor = 1.0
    confidence_age_seconds = _safe_float(entry.get("confidence_age_seconds"))
    if confidence_age_seconds is None:
        confidence_age_seconds = _safe_float(existing_stage_trace.get("age_seconds"))
    if confidence_age_seconds is None:
        confidence_age_seconds = _canonical_quote_age_sec(entry)
    confidence_market_velocity = _safe_float(entry.get("confidence_market_velocity"))
    if confidence_market_velocity is None:
        confidence_market_velocity = _safe_float(existing_stage_trace.get("market_velocity"))
    confidence_age_factor = _safe_float(entry.get("confidence_age_factor"))
    if confidence_age_factor is None:
        confidence_age_factor = _safe_float(existing_stage_trace.get("age_factor"))
    if confidence_age_factor is None and confidence_age_seconds is not None:
        confidence_age_factor = float(confidence_age_seconds) / max(float(confidence_market_velocity or 1.0), 1e-6)
    entry["confidence_after_time_decay"] = confidence_after_time_decay
    entry["confidence_time_decay_factor"] = confidence_time_decay_factor
    entry["confidence_age_seconds"] = confidence_age_seconds
    entry["confidence_market_velocity"] = confidence_market_velocity
    entry["confidence_age_factor"] = confidence_age_factor
    entry["confidence_stage_trace"] = {
        "model_raw": _safe_float(existing_stage_trace.get("model_raw"))
        if existing_stage_trace
        else _safe_float(entry.get("confidence_model_raw")),
        "after_micro": _safe_float(existing_stage_trace.get("after_micro"))
        if existing_stage_trace
        else _safe_float(entry.get("confidence_after_micro")),
        "after_alpha": _safe_float(existing_stage_trace.get("after_alpha"))
        if existing_stage_trace
        else _safe_float(entry.get("confidence_after_alpha")),
        "after_latency": _safe_float(existing_stage_trace.get("after_latency"))
        if existing_stage_trace
        else _safe_float(entry.get("confidence_after_latency")),
        "before_soft_veto": _safe_float(existing_stage_trace.get("before_soft_veto"))
        if existing_stage_trace
        else confidence_before_soft_veto,
        "after_soft_veto": _safe_float(existing_stage_trace.get("after_soft_veto"))
        if existing_stage_trace
        else confidence_after_soft_veto,
        "after_time_decay": confidence_after_time_decay,
        "time_decay_factor": confidence_time_decay_factor,
        "age_seconds": confidence_age_seconds,
        "market_velocity": confidence_market_velocity,
        "age_factor": confidence_age_factor,
        "raw_gate_threshold": _safe_float(existing_stage_trace.get("raw_gate_threshold"))
        if existing_stage_trace
        else _safe_float(entry.get("confidence_raw_gate_threshold")),
        "final_gate_threshold": _safe_float(existing_stage_trace.get("final_gate_threshold"))
        if existing_stage_trace
        else _safe_float(entry.get("confidence_final_gate_threshold")),
        "rejected_at": (
            str(existing_stage_trace.get("rejected_at")).strip() or None
            if existing_stage_trace.get("rejected_at") is not None
            else _normalize_text(entry.get("confidence_rejection_stage"))
        )
        if existing_stage_trace
        else _normalize_text(entry.get("confidence_rejection_stage")),
    }
    entry["confidence_penalty_soft_veto_total"] = round(float(confidence_penalty_soft_veto_total), 6)
    entry["confidence_penalty_soft_veto_reasons"] = confidence_penalty_soft_veto_reasons
    entry = _synchronize_final_confidence(entry)
    entry = _apply_sizing_telemetry(entry)
    return finalize_trade_decision(entry)


def _refresh_lifecycle_blockers(
    entry: dict,
    *,
    mode_for_entry: str,
    allow_stale_quotes_for_entry: bool,
    current_ltp: float | None,
    validation_reference_price: float | None,
) -> dict:
    if not isinstance(entry, dict) or str(entry.get("instrument") or entry.get("instrument_type") or "").upper() != "OPT":
        return entry
    option_sla = float(getattr(cfg, "OPTION_LTP_SLA_SEC", 2.0))
    canonical_live_sla = float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5))
    stale_threshold = float(
        get_option_ltp_sla_sec(
            mode_for_entry,
            min(option_sla, canonical_live_sla),
            allow_stale_quotes=allow_stale_quotes_for_entry,
            market_open=_entry_market_open(mode_for_entry, allow_stale_quotes_for_entry),
            expiry_lotto_mode=bool(getattr(cfg, "EXPIRY_LOTTO_MODE", False)),
        )
    )
    advisory_generation = (
        str(entry.get("advisory_id") or "").strip()
        or str(entry.get("trade_id") or "").strip()
        or str(entry.get("trade_key") or "").strip()
        or str(entry.get("timestamp") or "").strip()
    )
    active_records = evaluate_advisory_contract_blockers(
        get_blocker_registry("advisory"),
        now_ts=float(time.time()),
        symbol=entry.get("symbol"),
        expiry=entry.get("expiry_date") or entry.get("expiry"),
        strike=entry.get("strike"),
        right=entry.get("option_type") or entry.get("type") or entry.get("right"),
        advisory_generation=advisory_generation,
        instrument_token=entry.get("instrument_token"),
        tradingsymbol=entry.get("tradingsymbol"),
        live_price=current_ltp,
        reference_price=validation_reference_price,
        quote_age_sec=_canonical_quote_age_sec(entry),
        stale_threshold_sec=stale_threshold,
        abs_tol=float(getattr(cfg, "OPTION_ENTRY_MISMATCH_ABS", 1.0)),
        pct_tol=float(getattr(cfg, "OPTION_ENTRY_MISMATCH_PCT", 0.03)),
        subscription_failed=bool(entry.get("subscription_failed")),
    )
    lifecycle_codes = [str(record.code) for record in active_records]
    blockers = list(dict.fromkeys(lifecycle_codes + _current_non_lifecycle_blockers(entry)))
    entry["blockers"] = blockers
    return entry


def _perm_rank(value: str | None) -> int:
    mapping = {
        "BLOCK": 0,
        "ADVISORY_ONLY": 1,
        "QUEUE_ONLY": 2,
        "EXECUTE": 3,
    }
    if value is None:
        return -1
    return mapping.get(str(value).strip().upper(), -1)


def _apply_permission_state(
    entry: dict,
    permission: str | None,
    reason: str | None,
    *,
    downgrade_reason: str | None = None,
) -> dict:
    if not isinstance(entry, dict):
        return entry
    prev_permission = str(entry.get("permission") or "").strip().upper()
    new_permission = str(permission or "").strip().upper()
    reason_text = str(reason or "").strip()
    if prev_permission and new_permission and _perm_rank(new_permission) < _perm_rank(prev_permission):
        entry["permission_downgraded_from"] = prev_permission
        entry["permission_downgrade_reason"] = str(downgrade_reason or reason_text or "")
    if new_permission:
        entry["permission"] = new_permission
    if reason_text:
        entry["permission_reason"] = reason_text
    return entry


def _decision_defaults(permission: str | None) -> tuple[str, str, str]:
    perm = str(permission or "ADVISORY_ONLY").strip().upper() or "ADVISORY_ONLY"
    if perm == "BLOCK":
        return "BLOCKED", "blocked", "BLOCK"
    if perm == "EXECUTE":
        return "READY", "executable", "EXECUTE"
    if perm == "QUEUE_ONLY":
        return "QUEUE_ONLY", "queue_only", "QUEUE_ONLY"
    return "ADVISORY_ONLY", "advisory_only", "ADVISORY_ONLY"


def _enforce_final_execution_state_consistency(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    permission = str(out.get("permission") or "").strip().upper()
    final_action = str(out.get("final_action") or "").strip().upper()
    readiness = str(out.get("readiness") or "").strip().upper()
    execution_status = str(out.get("execution_status") or "").strip().lower()
    row_status = str(out.get("status") or "").strip().upper()
    unresolved_contract = bool(out.get("unresolved_contract")) or row_status == "BLOCKED_CONTRACT"
    hard_blockers = _dedupe_issue_codes(list(out.get("hard_blockers") or []))
    blockers = _dedupe_issue_codes(list(out.get("blockers") or []))
    execution_entry = _safe_float(out.get("execution_entry"))
    execution_entry_status = str(out.get("execution_entry_status") or "").strip().lower()
    executable_entry_ready = execution_entry is not None and execution_entry_status == "executable"

    primary_blocker = str(out.get("primary_blocker") or "").strip()
    if primary_blocker.lower() == "missing_execution_entry" and executable_entry_ready:
        replacement = (
            str(out.get("entry_block_reason") or "").strip()
            or str(out.get("final_blocker") or "").strip()
            or str(out.get("hard_reason") or "").strip()
            or str(out.get("permission_reason") or "").strip()
        )
        if replacement.lower() == "missing_execution_entry":
            replacement = ""
        out["primary_blocker"] = replacement or None
        out["final_emit_block_reason"] = replacement or None

    execution_blocked = bool(out.get("execution_blocked"))
    execution_truth_blocked = bool(out.get("execution_truth_blocked")) or bool(out.get("execution_truth_blockers"))
    approval_blocked = bool(out.get("approval_blocked"))
    must_demote_execute = (
        final_action == "EXECUTE"
        or readiness == "READY"
        or execution_status == "executable"
        or permission == "EXECUTE"
    ) and (
        not bool(out.get("execution_allowed", False))
        or execution_status != "executable"
        or not executable_entry_ready
        or approval_blocked
        or execution_blocked
        or execution_truth_blocked
        or unresolved_contract
        or bool(hard_blockers)
    )
    if not must_demote_execute:
        return out

    if unresolved_contract or bool(hard_blockers) or execution_status == "blocked" or execution_truth_blocked:
        target_permission = "BLOCK"
    elif execution_status == "queue_only":
        target_permission = "QUEUE_ONLY"
    else:
        target_permission = "ADVISORY_ONLY"

    out = _apply_permission_state(
        out,
        target_permission,
        str(out.get("permission_reason") or out.get("primary_blocker") or "").strip() or None,
        downgrade_reason="final_execution_state_consistency",
    )
    next_readiness, next_execution_status, next_final_action = _decision_defaults(target_permission)
    out["final_action"] = next_final_action
    out["readiness"] = next_readiness
    if row_status in {"READY", "QUEUE_ONLY", "ADVISORY_ONLY", "BLOCKED", "INVALID", ""}:
        out["status"] = next_readiness if next_readiness != "BLOCKED" else "INVALID"
    out["execution_status"] = next_execution_status
    out["execution_allowed"] = False
    out["execution_ok"] = False if out.get("execution_ok") is False or target_permission != "EXECUTE" else out.get("execution_ok")
    out["eligible_for_execution"] = target_permission == "QUEUE_ONLY" and not unresolved_contract and not bool(hard_blockers)
    out["is_executable"] = False
    return out


def _refresh_opportunity_survival_state(entry: dict) -> dict:
    if not isinstance(entry, dict):
        return entry
    out = _enforce_executable_entry_invariant(entry)
    if _should_block_final_queue_only_entry_promotion(out):
        return _classify_candidate_status(_apply_final_queue_only_entry_promotion_block(out))
    permission = str(out.get("permission") or "").strip().upper()
    final_action = str(out.get("final_action") or "").strip().upper()
    readiness = str(out.get("readiness") or "").strip().upper()
    status = str(out.get("status") or "").strip().upper()
    display_entry = _safe_float(out.get("display_entry"))
    if display_entry is None:
        display_entry = _safe_float(out.get("entry"))
    display_entry_status = str(out.get("display_entry_status") or out.get("entry_status") or "").strip().lower()
    execution_entry = _safe_float(out.get("execution_entry"))
    execution_entry_source = str(out.get("execution_entry_source") or "").strip().lower()
    execution_entry_status = str(out.get("execution_entry_status") or "").strip().lower()
    approval_blocked = bool(out.get("approval_blocked"))
    blockers = _dedupe_issue_codes(list(out.get("blockers") or []))
    hard_blockers = _dedupe_issue_codes(list(out.get("hard_blockers") or []))
    if execution_entry_source in {"recovered_fallback", "rest_fallback", "synthetic_offhours"}:
        out["execution_entry_status"] = "non_executable"
        out["execution_allowed"] = False
        execution_entry_status = "non_executable"
        if str(out.get("execution_status") or "").strip().lower() == "executable":
            out["execution_status"] = "advisory_only"
    unresolved_contract = bool(out.get("unresolved_contract")) or status == "BLOCKED_CONTRACT"
    if (
        execution_entry is not None
        and execution_entry_status == "executable"
        and execution_entry_source == "last"
        and (hard_blockers or blockers)
        and permission != "EXECUTE"
        and not out.get("entry_recovered")
    ):
        if not _has_valid_token(out):
            out["execution_entry"] = None
            out["execution_entry_source"] = "none"
            out["execution_entry_status"] = "non_executable"
            execution_entry = None
            execution_entry_status = "non_executable"
    executable_truth = execution_entry is not None and execution_entry_status == "executable"
    displayable_truth = display_entry is not None and display_entry_status == "displayable"

    if unresolved_contract or permission == "BLOCK" or final_action == "BLOCK" or readiness == "BLOCKED":
        out["tradable"] = False
        out["execution_allowed"] = False
        out["is_executable"] = False
        return _classify_candidate_status(out)

    if executable_truth and permission == "EXECUTE" and final_action == "EXECUTE" and not approval_blocked and not hard_blockers:
        out["tradable"] = True
        out["execution_allowed"] = True
        out["execution_status"] = "executable"
        out["is_executable"] = True
        return _classify_candidate_status(out)

    if executable_truth and (
        permission in {"QUEUE_ONLY", "ADVISORY_ONLY"}
        or final_action in {"QUEUE_ONLY", "ADVISORY_ONLY"}
        or readiness in {"QUEUE_ONLY", "ADVISORY_ONLY"}
    ):
        out["tradable"] = True
        out["execution_allowed"] = False
        out["is_executable"] = False
        if permission == "QUEUE_ONLY" or final_action == "QUEUE_ONLY" or readiness == "QUEUE_ONLY":
            out["execution_status"] = "queue_only"
            out["eligible_for_execution"] = not approval_blocked and not unresolved_contract and not bool(hard_blockers)
        else:
            out["execution_status"] = "advisory_only"
            out["eligible_for_execution"] = False
        return _classify_candidate_status(out)

    if displayable_truth and (
        permission in {"QUEUE_ONLY", "ADVISORY_ONLY", "EXECUTE"}
        or final_action in {"QUEUE_ONLY", "ADVISORY_ONLY"}
        or readiness in {"QUEUE_ONLY", "ADVISORY_ONLY", "READY"}
    ):
        out["tradable"] = True
        out["execution_allowed"] = False
        out["is_executable"] = False
        if permission == "QUEUE_ONLY" or final_action == "QUEUE_ONLY" or readiness == "QUEUE_ONLY":
            out["execution_status"] = "queue_only"
            out["eligible_for_execution"] = not approval_blocked and not unresolved_contract and not bool(hard_blockers)
        else:
            out["execution_status"] = "advisory_only"
            out["eligible_for_execution"] = False
        return _classify_candidate_status(out)

    out["tradable"] = False
    out["execution_allowed"] = False
    out["is_executable"] = False
    if not str(out.get("execution_status") or "").strip():
        out["execution_status"] = "blocked"
    return _classify_candidate_status(out)


def finalize_trade_decision(
    entry: dict,
    *,
    gate_decision_payload: dict | None = None,
    permission_payload: dict | None = None,
    entry_block_reason: str | None = None,
    decision_seed: dict | None = None,
) -> dict:
    if not isinstance(entry, dict):
        return entry
    permission_payload = permission_payload if isinstance(permission_payload, dict) else {}
    gate_decision_payload = gate_decision_payload if isinstance(gate_decision_payload, dict) else {}
    decision_seed = decision_seed if isinstance(decision_seed, dict) else {}
    base_permission = str(
        permission_payload.get("permission")
        or entry.get("permission_base")
        or entry.get("permission")
        or "ADVISORY_ONLY"
    ).strip().upper() or "ADVISORY_ONLY"
    base_reason = str(
        permission_payload.get("permission_reason")
        or entry.get("permission_reason_base")
        or entry.get("permission_reason")
        or ""
    ).strip()
    current_permission = str(entry.get("permission") or base_permission or "ADVISORY_ONLY").strip().upper() or "ADVISORY_ONLY"
    current_reason = str(entry.get("permission_reason") or base_reason or "").strip()
    hard_blockers = _dedupe_issue_codes(list(entry.get("hard_blockers") or []))
    blockers = _dedupe_issue_codes(list(entry.get("blockers") or []))
    gate_hard_reasons = _dedupe_issue_codes(list(gate_decision_payload.get("hard_reasons") or []))
    gate_hard_reason = gate_hard_reasons[0] if gate_hard_reasons else ""
    effective_entry_block_reason = str(
        entry_block_reason
        or entry.get("entry_block_reason")
        or ""
    ).strip()

    seeded_permission = str(
        decision_seed.get("permission")
        or current_permission
        or base_permission
        or "ADVISORY_ONLY"
    ).strip().upper() or "ADVISORY_ONLY"
    seeded_reason = str(
        decision_seed.get("permission_reason")
        or current_reason
        or base_reason
        or ""
    ).strip()
    seeded_readiness = str(decision_seed.get("readiness") or "").strip().upper()
    seeded_execution_status = str(decision_seed.get("execution_status") or "").strip().lower()
    seeded_final_action = str(decision_seed.get("final_action") or "").strip().upper()

    final_permission = seeded_permission
    final_reason = seeded_reason
    if bool(entry.get("unresolved_contract")):
        final_permission = "BLOCK"
        final_reason = final_reason or "unresolved_contract"
    elif bool(entry.get("subscription_failed")) and str(entry.get("entry_status") or "").strip().upper() == "NO_LIVE_OPTION_FEED":
        final_reason = final_reason or "NO_LIVE_OPTION_FEED"
    elif final_permission not in {"BLOCK", "ADVISORY_ONLY", "QUEUE_ONLY", "EXECUTE"}:
        final_permission = base_permission
        final_reason = base_reason

    entry["permission"] = final_permission
    if final_reason:
        entry["permission_reason"] = final_reason

    final_blocker = None
    if hard_blockers:
        final_blocker = hard_blockers[0]
    elif gate_hard_reason:
        final_blocker = gate_hard_reason
    elif effective_entry_block_reason and _is_entry_status_blocking(effective_entry_block_reason):
        final_blocker = effective_entry_block_reason
    elif bool(entry.get("unresolved_contract")):
        final_blocker = "unresolved_contract"
    elif final_permission == "BLOCK":
        final_blocker = final_reason or effective_entry_block_reason or None
    entry["final_blocker"] = final_blocker

    default_readiness, default_execution_status, default_final_action = _decision_defaults(final_permission)
    readiness = seeded_readiness or default_readiness
    execution_status = seeded_execution_status or default_execution_status
    final_action = seeded_final_action or default_final_action
    is_executable = str(readiness).upper() == "READY" and str(final_action).upper() == "EXECUTE"

    entry["permission"] = final_permission
    entry["permission_reason"] = final_reason
    entry["readiness"] = readiness
    entry["execution_status"] = execution_status
    entry["final_action"] = final_action
    entry["advisory_visible"] = not _is_blocked_contract_row(entry)
    entry["is_executable"] = is_executable
    entry["entry_block_reason"] = effective_entry_block_reason or None
    return entry


def _apply_confidence_threshold_fields(
    entry: dict,
    *,
    confidence_value: float | None,
    execution_mode: str,
    hard_blockers: list[str] | None = None,
    entry_block_reason: str | None = None,
) -> dict:
    if not isinstance(entry, dict):
        return entry
    thresholds = resolve_confidence_thresholds(execution_mode)
    entry["threshold_display"] = float(thresholds["display"])
    entry["threshold_advisory"] = float(thresholds["advisory"])
    entry["threshold_execution"] = float(thresholds["execution"])
    entry["confidence_vs_threshold_reason"] = classify_confidence_vs_threshold(
        confidence_value,
        execution_mode=thresholds["mode"],
        hard_blocker=bool(hard_blockers),
        entry_blocked=bool(entry_block_reason) and not bool(hard_blockers),
    )
    return entry


def _material_change(old_entry: dict, new_entry: dict, tol: float) -> bool:
    for key in ("entry", "target", "stop"):
        old_val = _safe_float(old_entry.get(key))
        new_val = _safe_float(new_entry.get(key))
        if old_val is None and new_val is None:
            continue
        if old_val is None or new_val is None:
            return True
        if abs(old_val - new_val) > float(tol):
            return True
    return False


def _find_existing_by_key(data: list[dict], trade_key: str) -> tuple[int | None, dict | None]:
    if not trade_key:
        return None, None
    for idx, row in enumerate(data):
        if not isinstance(row, dict):
            continue
        key = row.get("trade_key")
        if not key:
            key = compute_trade_key(
                row.get("symbol"),
                row.get("expiry_date") or row.get("expiry"),
                row.get("strike"),
                row.get("option_type") or row.get("type"),
                row.get("side"),
                row.get("strategy_id") or row.get("strategy") or row.get("generator"),
            )
            row["trade_key"] = key
        if key == trade_key:
            return idx, row
    return None, None


def _merge_trade_entry(data: list[dict], entry: dict) -> list[dict]:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    trade_key = entry.get("trade_key")
    if not trade_key:
        entry["first_seen"] = entry.get("first_seen") or now_iso
        entry["last_seen"] = now_iso
        entry["trade_status"] = entry.get("trade_status") or "NEW"
        entry["update_count"] = int(entry.get("update_count") or 0)
        data.append(entry)
        return data

    idx, existing = _find_existing_by_key(data, trade_key)
    if existing is None:
        entry["first_seen"] = entry.get("first_seen") or now_iso
        entry["last_seen"] = now_iso
        entry["trade_status"] = entry.get("trade_status") or "NEW"
        entry["update_count"] = int(entry.get("update_count") or 0)
        data.append(entry)
        return data

    existing_status = str(existing.get("trade_status") or "").upper()
    if existing_status in {"INVALIDATED", "EXPIRED"}:
        entry["first_seen"] = entry.get("first_seen") or now_iso
        entry["last_seen"] = now_iso
        entry["trade_status"] = entry.get("trade_status") or "NEW"
        entry["update_count"] = int(entry.get("update_count") or 0)
        data.append(entry)
        return data

    tol = float(getattr(cfg, "TRADE_DEDUP_PRICE_TOL", 0.05)) if cfg else 0.05
    old_perm = existing.get("permission")
    new_perm = entry.get("permission")
    perm_escalated = _perm_rank(new_perm) > _perm_rank(old_perm)
    changed = _material_change(existing, entry, tol)
    if perm_escalated:
        trade_status = "UPDATED_PERMISSION"
    elif changed:
        trade_status = "UPDATED"
    else:
        trade_status = "REVALIDATED"

    existing_lifecycle = str(existing.get("status") or "").upper()
    incoming_lifecycle = str(entry.get("status") or "").upper()
    if existing_lifecycle in {"ACTIVE", "RESOLVED"} and incoming_lifecycle in {"PLANNING", "NEW", ""}:
        entry["status"] = existing_lifecycle

    # Keep entry deterministic for planning rows to avoid entry drift on each revalidation tick.
    # New entry may still populate when it was previously missing.
    freeze_planning_entry = bool(getattr(cfg, "FREEZE_PLANNING_ENTRY_ON_REVALIDATE", True)) if cfg else True
    if freeze_planning_entry and existing_lifecycle in {"PLANNING", "NEW", ""}:
        old_entry = _safe_float(existing.get("entry"))
        if old_entry is not None:
            entry["entry"] = existing.get("entry")
            if existing.get("suggested_entry") not in (None, "", "None"):
                entry["suggested_entry"] = existing.get("suggested_entry")

    update_count = int(existing.get("update_count") or 0) + 1
    first_seen = existing.get("first_seen") or entry.get("first_seen") or now_iso

    existing.update(entry)
    existing["first_seen"] = first_seen
    existing["last_seen"] = now_iso
    existing["update_count"] = update_count
    existing["trade_status"] = trade_status
    data[idx] = existing
    return data


def _derive_target(entry_val, stop_val, side, rr_default: float):
    try:
        entry_f = float(entry_val)
        stop_f = float(stop_val)
        rr_f = float(rr_default)
    except Exception:
        return None
    risk = abs(entry_f - stop_f)
    if risk <= 0:
        return None
    side_val = str(side or "").upper()
    if side_val == "SELL":
        target = entry_f - (risk * rr_f)
    else:
        target = entry_f + (risk * rr_f)
    if target <= 0:
        return None
    return round(float(target), 2)


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2))
    os.replace(tmp_path, path)


def _runtime_feed_status_snapshot() -> dict:
    loaded = load_current_feed_runtime(logs_dir() / "feed_runtime_latest.json")
    payload = dict(loaded.get("payload") or {}) if loaded.get("valid") else {}
    auth_snapshot = runtime_auth_snapshot()
    feed_truth_state = str(payload.get("feed_truth_state") or "").strip().upper() or None
    feed_truth_strict_live = payload.get("feed_truth_strict_live")
    feed_ok = bool(payload.get("feed_ok")) if loaded.get("valid") else False
    return {
        "feed_ok": feed_ok,
        "ws_connected": payload.get("effective_ws_connected", payload.get("ws_connected")),
        "feed_truth_state": feed_truth_state,
        "feed_truth_strict_live": bool(feed_truth_strict_live) if isinstance(feed_truth_strict_live, bool) else None,
        "auth_ok": bool(auth_snapshot.get("auth_ok", True)),
        "auth_state": str(auth_snapshot.get("auth_state") or "UNKNOWN"),
        "auth_reason": str(auth_snapshot.get("auth_reason") or ""),
        "subscribed_option_tokens_count": int(payload.get("subscribed_option_tokens_count") or 0),
        "missing_option_tokens_count": int(payload.get("missing_option_tokens_count") or 0),
    }


def _runtime_auth_status_snapshot() -> dict:
    return runtime_auth_snapshot()


def _update_suggestions_status_latest(
    entry: dict,
    emission_result: dict | None = None,
    *,
    queue_rows: list[dict] | None = None,
) -> None:
    try:
        if not isinstance(entry, dict):
            return
        status_entry = dict(entry)
        funnel_counts = _candidate_funnel_counts(
            queue_rows if isinstance(queue_rows, list) and queue_rows else [status_entry]
        )
        visibility_counts = _candidate_visibility_counts(
            queue_rows if isinstance(queue_rows, list) and queue_rows else [status_entry]
        )
        if not status_entry.get("quote_validation_status"):
            fallback_entry_status = str(status_entry.get("entry_status") or "").strip().upper()
            if fallback_entry_status in {
                "OK",
                "LIVE_OK",
                "VALID",
                "OFFHOURS_SYNTHETIC",
                "NO_LIVE_OPTION_FEED",
                "MISSING_OPTION_TOKEN",
            }:
                status_entry["quote_validation_status"] = fallback_entry_status
            elif (
                bool(status_entry.get("unresolved_contract"))
                or status_entry.get("instrument_token") in (None, "", "None")
            ):
                status_entry["quote_validation_status"] = "MISSING_OPTION_TOKEN"
            else:
                status_entry["quote_validation_status"] = "NO_LIVE_OPTION_FEED"
        status_entry = _repair_live_feed_failure_provenance(status_entry)
        path = logs_dir() / "suggestions_status.json"
        suggestions_path = canonical_suggestions_log_path()
        current = _read_json(path, {})
        if not isinstance(current, dict):
            current = {}
        suggestion_count = int(current.get("suggestion_count") or 0)
        try:
            if suggestions_path.exists():
                with suggestions_path.open("r", encoding="utf-8") as fh:
                    suggestion_count = sum(1 for line in fh if str(line).strip())
        except Exception:
            pass
        primary_blocker = _best_reject_reason(status_entry, default="")
        if not str(primary_blocker or "").strip():
            primary_blocker = None
        status = "blocked" if _is_entry_status_blocking(status_entry.get("entry_status")) or str(status_entry.get("permission") or "").upper() == "BLOCK" else "ok"
        emission_ok = not isinstance(emission_result, dict) or bool(emission_result.get("ok"))
        emission_target = (
            str(emission_result.get("target") or "").strip()
            if isinstance(emission_result, dict)
            else ""
        )
        emission_diagnostic = (
            dict(emission_result.get("diagnostic") or {})
            if isinstance(emission_result, dict) and isinstance(emission_result.get("diagnostic"), dict)
            else {}
        )
        feed_snapshot = _runtime_feed_status_snapshot()
        auth_snapshot = _runtime_auth_status_snapshot()
        runtime_healthy = True
        if bool(getattr(cfg, "STATUS_ZERO_VISIBLE_COUNTS_WHEN_UNHEALTHY", True)):
            runtime_healthy = bool(feed_snapshot.get("feed_ok")) and feed_snapshot.get("ws_connected") is not False and bool(auth_snapshot.get("auth_ok", True))
            if not runtime_healthy:
                visibility_counts.update(
                    {
                        "visible_suggestion_count": 0,
                        "visible_advisory_count": 0,
                        "visible_queue_only_count": 0,
                        "visible_executable_count": 0,
                    }
                )
        if not emission_ok:
            status = "error"
        elif not runtime_healthy:
            status = "blocked"
        payload = dict(current)
        payload.update(
            {
                "ts_epoch": float(time.time()),
                "ts_local": datetime.now().astimezone().isoformat(),
                "status": status,
                "suggestion_count": int(suggestion_count),
                "latest_trade_id": status_entry.get("trade_id"),
                "latest_entry_status": status_entry.get("entry_status"),
                "latest_candidate_status": status_entry.get("candidate_status"),
                "latest_permission": status_entry.get("permission"),
                "latest_permission_reason": status_entry.get("permission_reason"),
                "primary_blocker": primary_blocker or current.get("primary_blocker"),
                "latest_emit_status": "ok" if emission_ok else "schema_failed",
                "latest_emit_target": emission_target or None,
                "latest_emit_reason": emission_diagnostic.get("failure_reason"),
                **funnel_counts,
                **visibility_counts,
                **feed_snapshot,
                **auth_snapshot,
            }
        )
        write_json_atomic(path, payload)
        rejected_status_path = logs_dir() / "rejected_candidates_status.json"
        if emission_target == "rejected_candidates" or _is_blocked_contract_row(status_entry):
            rejected_current = _read_json(rejected_status_path, {})
            if not isinstance(rejected_current, dict):
                rejected_current = {}
            rejected_payload = dict(rejected_current)
            rejected_payload.update(
                {
                    "ts_epoch": float(time.time()),
                    "ts_local": datetime.now().astimezone().isoformat(),
                    "status": "ok" if emission_ok else "error",
                    "latest_trade_id": status_entry.get("trade_id"),
                    "latest_entry_status": status_entry.get("entry_status"),
                    "latest_candidate_status": status_entry.get("candidate_status"),
                    "latest_permission": status_entry.get("permission"),
                    "latest_permission_reason": status_entry.get("permission_reason"),
                    "latest_emit_status": "ok" if emission_ok else "schema_failed",
                    "latest_emit_target": emission_target or "rejected_candidates",
                    "latest_emit_reason": emission_diagnostic.get("failure_reason"),
                    "primary_blocker": primary_blocker or rejected_current.get("primary_blocker"),
                    **funnel_counts,
                    **visibility_counts,
                    **feed_snapshot,
                    **auth_snapshot,
                }
            )
            write_json_atomic(rejected_status_path, rejected_payload)
        engine_path = logs_dir() / "engine_cycle_status.json"
        engine_current = _read_json(engine_path, {})
        if isinstance(engine_current, dict):
            engine_payload = dict(engine_current)
            engine_payload.update(
                {
                    "ts_epoch": float(time.time()),
                    "cycle_ok": bool(emission_ok),
                    "cycle_stage": "emit_failed" if not emission_ok else ("blocked" if status == "blocked" else "ok"),
                    "reason": "advisory_emit_schema_error" if not emission_ok else (primary_blocker if status == "blocked" else "ok"),
                    "subreason": emission_diagnostic.get("failure_reason") if not emission_ok else "",
                    "candidates_seen": max(int(engine_current.get("candidates_seen") or 0), int(suggestion_count)),
                    "candidates_enqueued": max(int(engine_current.get("candidates_enqueued") or 0), int(suggestion_count)),
                    "primary_blocker": primary_blocker or engine_current.get("primary_blocker"),
                    "latest_emit_status": "ok" if emission_ok else "schema_failed",
                    "latest_emit_target": emission_target or None,
                    **funnel_counts,
                    **visibility_counts,
                    **feed_snapshot,
                    **auth_snapshot,
                }
            )
            write_json_atomic(engine_path, engine_payload)
        logger.info(
            "review_queue_candidate_funnel generated=%s scored=%s ranked=%s executable=%s advisory_only=%s blocked_contract=%s latest_trade_id=%s",
            funnel_counts["candidates_generated"],
            funnel_counts["candidates_scored"],
            funnel_counts["candidates_ranked"],
            funnel_counts["candidates_executable"],
            funnel_counts["candidates_advisory_only"],
            funnel_counts["candidates_blocked_contract"],
            status_entry.get("trade_id"),
        )
    except Exception:
        logger.warning("suggestions_status_update_failed trade_id=%s", entry.get("trade_id") if isinstance(entry, dict) else None)


def _looks_like_trade(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("symbol") or payload.get("trade_id"):
        return True
    if payload.get("strike") is not None:
        return True
    if payload.get("type") or payload.get("option_type"):
        return True
    return False


def _normalize_queue_row(row: dict) -> dict:
    had_explicit_quote_validation_status = isinstance(row, dict) and "quote_validation_status" in row
    out = _apply_candidate_identity(dict(row or {}))
    quote_status_aliases = {
        "OK",
        "LIVE_OK",
        "VALID",
        "OFFHOURS_SYNTHETIC",
        "NO_LIVE_OPTION_FEED",
        "MISSING_OPTION_TOKEN",
    }
    legacy_quote_validation_hint = str(out.get("quote_validation_status") or "").strip().upper()
    if not legacy_quote_validation_hint:
        legacy_entry_status = str(out.get("entry_status") or "").strip().upper()
        if legacy_entry_status in quote_status_aliases:
            legacy_quote_validation_hint = legacy_entry_status
    canonical_entry = any(
        key in out
        for key in (
            "execution_entry",
            "execution_entry_source",
            "execution_entry_status",
            "display_entry",
            "display_entry_source",
            "display_entry_status",
            "entry_reason",
            "entry_clear_reason",
        )
    )
    original_status = str(out.get("status_raw") or out.get("status") or "PLANNING").strip().upper() or "PLANNING"
    out["status_raw"] = original_status
    out = _canonicalize_entry_lifecycle(
        out,
        mode_for_entry=_entry_execution_mode(out),
        allow_stale_quotes_for_entry=_allow_rest_fallback_for_mode(_entry_execution_mode(out)),
        align_for_schema=False,
    )
    out.setdefault("symbol", out.get("underlying"))
    if out.get("expiry_date") in (None, "", "None"):
        out["expiry_date"] = _coerce_expiry(out.get("expiry")) or out.get("expiry")
    if out.get("expiry") in (None, "", "None"):
        out["expiry"] = out.get("expiry_date")
    opt_type = _coerce_option_type(out.get("option_type") or out.get("type") or out.get("right"))
    if opt_type:
        out["option_type"] = opt_type
        out["type"] = opt_type
    strike = out.get("strike")
    strike_val = _coerce_strike(strike)
    if strike_val is not None:
        out["strike"] = strike_val
    out.setdefault("status", original_status)
    if _is_blocked_contract_row(out):
        out = _apply_unresolved_contract_state(out)
    out = _preserve_offhours_quote_validation_status(out)
    final_promotion_blocked = bool(out.get("_block_queue_only_final_promotion")) or _should_block_queue_only_entry_promotion(out)
    locked_final_promotion = bool(out.get("final_entry_locked")) and _final_entry_lock_enabled()
    quote_validation_status = str(out.get("quote_validation_status") or "").strip()
    if quote_validation_status:
        if str(out.get("quote_validation_status") or "").strip().upper() != "OFFHOURS_SYNTHETIC":
            out["quote_validation_status"] = quote_validation_status
    out = _apply_split_brain_quote_guard(out)
    raw_rank_score = _safe_float(out.get("raw_rank_score"))
    current_rank_score = _safe_float(out.get("rank_score"))
    if raw_rank_score is not None:
        if current_rank_score is None:
            out["rank_score"] = raw_rank_score
        elif current_rank_score > raw_rank_score:
            logger.warning(
                "rank_truth_drift trade_id=%s symbol=%s raw_rank_score=%s normalized_rank_score=%s action=preserved_raw",
                out.get("trade_id"),
                out.get("symbol"),
                raw_rank_score,
                current_rank_score,
            )
            out["rank_score"] = raw_rank_score
    out = _apply_terminal_rank_truth(out)
    if out.get("entry_recovered") and (
        str(out.get("quote_validation_status") or "").strip().upper() == "STALE_OPTION_LTP"
        or str(out.get("entry_status") or "").strip().lower() != "displayable"
    ):
        preserved_display_entry = _safe_float(out.get("display_entry"))
        if preserved_display_entry is None:
            preserved_display_entry = _safe_float(out.get("pre_validation_entry"))
        if preserved_display_entry is None:
            preserved_display_entry = _safe_float(out.get("entry"))
        if preserved_display_entry is None:
            preserved_display_entry = _safe_float(out.get("suggested_entry"))
        if preserved_display_entry is None:
            preserved_display_entry = _safe_float(out.get("expected_entry"))
        if preserved_display_entry is None:
            preserved_display_entry = _safe_float(out.get("entry_price"))
        if preserved_display_entry is not None:
            out["entry"] = preserved_display_entry
            out["entry_status"] = "displayable"
            if _safe_float(out.get("display_entry")) is None:
                out["display_entry"] = preserved_display_entry
                if str(out.get("display_entry_source") or "").strip().lower() in {"", "none"}:
                    out["display_entry_source"] = (
                        out.get("pre_validation_entry_source")
                        or out.get("suggested_entry_source")
                        or out.get("expected_entry_source")
                        or out.get("entry_price_source")
                        or out.get("entry_source")
                        or "none"
                    )
                out["display_entry_status"] = "displayable"
            if str(out.get("entry_source") or "").strip().lower() in {"", "none"}:
                out["entry_source"] = out.get("display_entry_source") or "none"
        else:
            out["entry"] = None
            out["entry_status"] = "missing"
            if str(out.get("entry_source") or "").strip().lower() == "recovered_fallback":
                out["entry_source"] = "none"
    if _should_block_entry_recovery_for_queue_only(out):
        out = _clear_fabricated_entry_lifecycle(out)
    if (
        not final_promotion_blocked
        and
        not out.get("_origin_synthetic_offhours")
        and _safe_float(out.get("display_entry")) is not None
        and _safe_float(out.get("entry")) is None
        and not out.get("entry_recovered")
    ):
        out["entry"] = _safe_float(out.get("display_entry"))
    if (
        (
            ("entry_status" not in out or out.get("entry_status") in (None, "", "None"))
            or (
                canonical_entry
                and not had_explicit_quote_validation_status
                and str(out.get("entry_status") or "").strip().upper() in {"OK", "LIVE_OK", "VALID"}
            )
        )
        and "display_entry_status" in out
        and out.get("display_entry_status") not in (None, "", "None")
        and not out.get("entry_recovered")
        and not final_promotion_blocked
        and not locked_final_promotion
    ):
        display_status = str(out.get("display_entry_status") or "").strip().lower()
        if display_status == "displayable":
            out["entry_status"] = "displayable" if _has_valid_entry(out) else "missing"
        else:
            out["entry_status"] = display_status
    if (
        ("entry_source" not in out or out.get("entry_source") in (None, "", "None"))
        and "display_entry_source" in out
        and out.get("display_entry_source") not in (None, "", "None")
        and not out.get("entry_recovered")
        and not final_promotion_blocked
        and not locked_final_promotion
    ):
        out["entry_source"] = out.get("display_entry_source")
    if (
        not out.get("entry_recovered")
        and not out.get("_origin_synthetic_offhours")
        and not final_promotion_blocked
        and not locked_final_promotion
    ):
        valid_base = _get_valid_entry_base(out)
        if valid_base is not None:
            out.setdefault("entry", valid_base)
    entry_status = str(out.get("entry_status") or "").strip().upper()
    token_missing_advisory = out.get("instrument_token") in (None, "", "None") and bool(out.get("tradingsymbol"))
    if out.get("entry") in ("", "None"):
        out["entry"] = None
    # Fail-closed normalization: executable entry must come from validated quote fields.
    # Do not carry stale/model reference prices as actionable entry.
    if canonical_entry:
        pass
    elif (
        entry_status
        and entry_status != "OK"
        and not out.get("entry_recovered")
        and not final_promotion_blocked
        and not locked_final_promotion
    ):
        suggested = _safe_float(out.get("suggested_entry"))
        current_ltp = _safe_float(out.get("current_ltp"))
        if token_missing_advisory:
            planned_entry = suggested
            if planned_entry is None:
                planned_entry = _safe_float(out.get("entry_price"))
            out["entry"] = planned_entry
        else:
            if not _should_force_missing_queue_only_lifecycle(out):
                out["entry"] = suggested if suggested is not None else current_ltp
    elif (
        out.get("entry") is None
        and not out.get("entry_recovered")
        and not final_promotion_blocked
        and not locked_final_promotion
    ):
        if not _should_force_missing_queue_only_lifecycle(out):
            suggested = _safe_float(out.get("suggested_entry"))
            if suggested is not None:
                out["entry"] = suggested
            else:
                fallback_entry = _safe_float(out.get("entry_price"))
                if fallback_entry is not None:
                    out["entry"] = fallback_entry
    if _safe_float(out.get("expected_entry")) is None and not locked_final_promotion:
        if not _should_force_missing_queue_only_lifecycle(out):
            expected_entry = _safe_float(out.get("suggested_entry"))
            if expected_entry is None:
                expected_entry = _safe_float(out.get("mark_price"))
            if expected_entry is None:
                expected_entry = _safe_float(out.get("entry"))
            if expected_entry is not None:
                out["expected_entry"] = expected_entry
    if out.get("_origin_synthetic_offhours"):
        base = (
            _safe_float(out.get("_synthetic_entry_price_original"))
            or _safe_float(out.get("entry_price"))
        )
        if base is not None and not locked_final_promotion:
            out["entry_price"] = base
            out["entry"] = base
            out["expected_entry"] = base
            out["suggested_entry"] = base
            out["validation_reference_price"] = base
            out["validation_reference_source"] = "synthetic_offhours"
            out["current_ltp"] = None
            out["option_ltp_timestamp"] = None
    if _safe_float(out.get("fill_entry")) is None:
        fill_entry = _safe_float(out.get("fill_price"))
        if fill_entry is None:
            fill_entry = _safe_float(out.get("avg_fill_price"))
        if fill_entry is not None:
            out["fill_entry"] = fill_entry
    for key in ("symbol", "expiry_date", "strike", "type", "status"):
        out.setdefault(key, None)
    ts_ms = _coerce_timestamp_epoch_ms(out)
    out["timestamp_epoch_ms"] = int(ts_ms)
    out["timestamp_utc_iso"] = _epoch_ms_to_utc_iso(ts_ms)
    # Backward-compatible timestamp field
    if out.get("timestamp") in (None, "", "None"):
        out["timestamp"] = out["timestamp_utc_iso"]
    else:
        out["timestamp"] = str(out.get("timestamp"))
    out = _apply_timestamp_contract_for_payload(out)
    if _is_blocked_contract_row(out):
        out = _apply_unresolved_contract_state(out)
    if original_status in {"APPROVED", "ACTIVE"}:
        out["status"] = original_status
    elif bool(out.get("unresolved_contract")):
        out["status"] = "BLOCKED_CONTRACT"
    else:
        out["status"] = _derive_review_status(out, fallback_status=original_status)
    out = _enforce_executable_entry_integrity(out)
    out = _refresh_opportunity_survival_state(out)
    if final_promotion_blocked:
        out = _apply_final_queue_only_entry_promotion_block(out)
    entry_missing = out.get("entry") in (None, "", "None") or _safe_float(out.get("entry")) is None
    if str(out.get("status") or "").strip().upper() == "PLANNING" and entry_missing:
        out["status"] = "INVALID"
        out.setdefault(
            "invalid_reason",
            str(out.get("entry_status") or _ENTRY_INTEGRITY_REASON).strip() or _ENTRY_INTEGRITY_REASON,
        )
        out.setdefault("permission", "ADVISORY_ONLY")
    out = enforce_entry_contract(out, stage="review_queue.normalize")
    out = rehydrate_trade_lifecycle(out, reason="queue_normalized")
    if final_promotion_blocked:
        out = _apply_final_queue_only_entry_promotion_block(out)
    if locked_final_promotion:
        out = _apply_locked_final_entry_projection(out)
    if not out.get("quote_validation_status"):
        fallback_entry_status = str(out.get("entry_status") or "").strip().upper()
        if legacy_quote_validation_hint in quote_status_aliases:
            out["quote_validation_status"] = legacy_quote_validation_hint
        elif fallback_entry_status in quote_status_aliases:
            out["quote_validation_status"] = fallback_entry_status
        elif (
            bool(out.get("unresolved_contract"))
            or out.get("instrument_token") in (None, "", "None")
        ):
            out["quote_validation_status"] = "MISSING_OPTION_TOKEN"
        else:
            out["quote_validation_status"] = "NO_LIVE_OPTION_FEED"
    out = _repair_live_feed_failure_provenance(out)
    if locked_final_promotion:
        out = _apply_locked_final_entry_projection(out)
    out = _enforce_final_execution_state_consistency(out)
    return _classify_candidate_status(out)


def _epoch_ms_to_utc_iso(epoch_ms: int) -> str:
    return datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=timezone.utc).isoformat()


def _epoch_ms_to_ist_iso(epoch_ms: int) -> str:
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    return datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=ist_tz).isoformat()


def _coerce_epoch_ms(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        val = float(value)
        if val <= 0:
            return None
        # If already in ms, keep as-is; otherwise treat as seconds.
        if val >= 10_000_000_000:
            return int(val)
        return int(val * 1000.0)
    text = str(value).strip()
    if not text:
        return None
    try:
        return _coerce_epoch_ms(float(text))
    except Exception:
        pass
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return int(dt.timestamp() * 1000.0)


def _coerce_ts_epoch_seconds(value) -> float | None:
    ts = _safe_float(value)
    if ts is not None:
        if abs(ts) >= 1.0e11:
            ts = ts / 1000.0
        return float(ts)
    ts_ms = _coerce_epoch_ms(value)
    if ts_ms is not None:
        return float(ts_ms) / 1000.0
    return None


def _select_ts_epoch_with_source(entry: dict, fields: tuple[str, ...]) -> tuple[float | None, str | None]:
    for field in fields:
        ts_epoch = _coerce_ts_epoch_seconds(entry.get(field))
        if ts_epoch is not None:
            return float(ts_epoch), field
    return None, None


def _apply_timestamp_contract_for_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    decision_fields = (
        "decision_ts_epoch",
        "decision_ts_utc",
        "decision_ts_ist",
        "ts_epoch",
        "ts_utc",
        "ts_ist",
        "timestamp_epoch_ms",
        "timestamp_utc_iso",
        "timestamp",
        "created_ts_epoch",
        "created_at",
    )
    snapshot_fields = (
        "snapshot_ts_epoch",
        "snapshot_ts_utc",
        "snapshot_ts_ist",
        "quote_ts_epoch",
        "option_ltp_timestamp",
        "ltp_ts_epoch",
        "freshness_quote_epoch",
        "candle_ts_epoch",
        "last_candle_ts_epoch",
        "signal_candle_epoch",
    )

    decision_ts_epoch, decision_source = _select_ts_epoch_with_source(out, decision_fields)
    snapshot_ts_epoch, snapshot_source = _select_ts_epoch_with_source(out, snapshot_fields)

    if decision_ts_epoch is None and snapshot_ts_epoch is not None:
        decision_ts_epoch = float(snapshot_ts_epoch)
        decision_source = f"fallback:{snapshot_source}"
    if decision_ts_epoch is None:
        decision_ts_epoch = float(time.time())
        decision_source = "now"

    display_ts_epoch = decision_ts_epoch if decision_ts_epoch is not None else snapshot_ts_epoch
    display_source = "decision_ts_epoch" if decision_ts_epoch is not None else "snapshot_ts_epoch"
    if decision_source and str(decision_source).startswith("fallback:"):
        display_source = "snapshot_ts_epoch"
    if display_ts_epoch is None:
        display_ts_epoch = float(time.time())
        display_source = "now"

    out.setdefault("decision_ts_epoch", float(decision_ts_epoch))
    out.setdefault("decision_ts_utc", _epoch_ms_to_utc_iso(int(float(decision_ts_epoch) * 1000.0)))
    out.setdefault("decision_ts_ist", _epoch_ms_to_ist_iso(int(float(decision_ts_epoch) * 1000.0)))
    out["decision_ts_source"] = decision_source

    if snapshot_ts_epoch is not None:
        out.setdefault("snapshot_ts_epoch", float(snapshot_ts_epoch))
        out.setdefault("snapshot_ts_utc", _epoch_ms_to_utc_iso(int(float(snapshot_ts_epoch) * 1000.0)))
        out.setdefault("snapshot_ts_ist", _epoch_ms_to_ist_iso(int(float(snapshot_ts_epoch) * 1000.0)))
    out["snapshot_ts_source"] = snapshot_source

    out["display_ts_epoch"] = float(display_ts_epoch)
    out["display_ts_utc"] = _epoch_ms_to_utc_iso(int(float(display_ts_epoch) * 1000.0))
    out["display_ts_ist"] = format_ts_ist(float(display_ts_epoch)) or _epoch_ms_to_ist_iso(
        int(float(display_ts_epoch) * 1000.0)
    )
    out["display_ts_source"] = display_source
    return out


def _coerce_timestamp_epoch_ms(row: dict) -> int:
    for key in ("timestamp_epoch_ms", "timestamp_utc_iso", "timestamp"):
        ts_ms = _coerce_epoch_ms(row.get(key))
        if ts_ms is not None:
            return int(ts_ms)
    return int(time.time() * 1000.0)


def load_queue_rows(path: Path, rewrite_healed: bool = True) -> list[dict]:
    if not path.exists():
        return []
    raw = _read_json(path, [])
    if not isinstance(raw, list):
        logger.warning("queue_load_invalid_shape path=%s type=%s", path, type(raw).__name__)
        return []
    rows: list[dict] = []
    modified = False
    for item in raw:
        if not isinstance(item, dict):
            logger.warning("queue_load_skip_non_dict path=%s item_type=%s", path, type(item).__name__)
            modified = True
            continue
        try:
            normalized = _normalize_queue_row(item)
        except EntryContractViolation:
            raise
        except Exception:
            logger.warning("queue_load_row_normalize_failed path=%s", path)
            modified = True
            continue
        if normalized != item:
            modified = True
        rows.append(normalized)
    if rewrite_healed and modified:
        try:
            write_queue_rows(path, rows)
        except Exception:
            logger.warning("queue_heal_write_failed path=%s", path)
    return rows


def write_queue_rows(path: Path, rows: list[dict]) -> None:
    safe_rows = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        safe_rows.append(_normalize_queue_row(row))
    _write_json(path, safe_rows)


def _load_approvals():
    raw = _read_json(APPROVED_PATH, {"version": 2, "approvals": {}})
    if isinstance(raw, dict) and isinstance(raw.get("approvals"), dict):
        return raw
    # Backward-compat: old format was list[trade_id]. Keep detectable but fail-closed by default.
    if isinstance(raw, list):
        legacy = {}
        for trade_id in raw:
            legacy[str(trade_id)] = {"legacy": True, "status": "APPROVED"}
        return {"version": 2, "approvals": legacy}
    return {"version": 2, "approvals": {}}


def canonical_order_payload(trade):
    try:
        intent = OrderIntent.from_trade(trade, mode="PAPER")
        return intent.to_canonical_dict()
    except Exception:
        return {}


def order_payload_hash(trade):
    payload = canonical_order_payload(trade)
    if not payload:
        return ""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def approval_status(trade_id, payload_hash=None, now_epoch=None):
    trade_id = str(trade_id or "")
    if not trade_id:
        return False, "approval_missing_trade_id"
    now_epoch = float(now_epoch if now_epoch is not None else time.time())
    strict = True
    if not _cfg_bool("APPROVAL_STRICT_PAYLOAD_HASH", True):
        return False, "approval_strict_mode_required"
    store = _load_approvals()
    record = (store.get("approvals") or {}).get(trade_id)
    if not record:
        return False, "approval_missing"
    if not isinstance(record, dict):
        return False, "approval_record_invalid"
    if record.get("status") and str(record.get("status")).upper() != "APPROVED":
        return False, "approval_not_approved"
    if record.get("legacy") is True and strict:
        return False, "approval_legacy_record"
    expires_epoch = record.get("expires_epoch")
    try:
        if expires_epoch is not None and now_epoch > float(expires_epoch):
            return False, "approval_expired"
    except Exception:
        return False, "approval_expiry_invalid"
    approved_hash = record.get("payload_hash")
    if strict and not approved_hash:
        return False, "approval_missing_payload_hash"
    if payload_hash and approved_hash and payload_hash != approved_hash:
        return False, "approval_payload_mismatch"
    if payload_hash and strict and not approved_hash:
        return False, "approval_missing_payload_hash"
    return True, "approved"

def _trade_attr(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _resolve_queue_strategy_identity(obj) -> tuple[str, str]:
    raw_strategy = (
        _trade_attr(obj, "strategy_id")
        or _trade_attr(obj, "strategy")
        or _trade_attr(obj, "strategy_name")
        or _trade_attr(obj, "generator")
        or "legacy_queue"
    )
    strategy_id = derive_strategy_id(_trade_attr(obj, "strategy_id"), raw_strategy)
    strategy_name = str(
        _trade_attr(obj, "strategy_name")
        or _trade_attr(obj, "strategy")
        or _trade_attr(obj, "generator")
        or strategy_id
        or "LEGACY_QUEUE"
    ).strip()
    return strategy_id, strategy_name


def _build_review_queue_entry(trade, *, extra=None, default_mode: str = "ADVISORY") -> tuple[dict, str, bool, bool]:
    mode_for_entry = default_mode
    allow_stale_quotes_for_entry = True
    strike_val = _trade_attr(trade, "strike")
    trade_id = _trade_attr(trade, "trade_id")
    originated_missing_token = bool(_trade_attr(trade, "originated_missing_token", None)) or (
        _trade_attr(trade, "instrument_token") in (None, "", "None", 0)
        and bool(_trade_attr(trade, "tradingsymbol"))
    )
    if strike_val in (None, 0) and trade_id and "ATM" in str(trade_id):
        strike_val = "ATM"
    strategy_id, strategy_name = _resolve_queue_strategy_identity(trade)
    entry = {
        "trade_id": trade_id,
        "symbol": _trade_attr(trade, "symbol"),
        "underlying": _trade_attr(trade, "underlying") or _trade_attr(trade, "symbol"),
        "instrument_id": _trade_attr(trade, "instrument_id"),
        "tradingsymbol": _trade_attr(trade, "tradingsymbol"),
        "strike": strike_val,
        "instrument": _trade_attr(trade, "instrument"),
        "instrument_token": _trade_attr(trade, "instrument_token"),
        "originated_missing_token": originated_missing_token,
        "expiry": _trade_attr(trade, "expiry"),
        "expiry_date": _trade_attr(trade, "expiry_date"),
        "type": _trade_attr(trade, "right") or _trade_attr(trade, "option_type"),
        "option_type": _trade_attr(trade, "option_type") or _trade_attr(trade, "right"),
        "side": _trade_attr(trade, "side"),
        # Preserve raw trade.entry when present, but keep entry_price as the
        # backward-compatible fallback so pre-validation state is not lost.
        "entry": _trade_attr(trade, "entry", None) if _trade_attr(trade, "entry", None) not in (None, "", "None") else _trade_attr(trade, "entry_price"),
        "entry_source": _trade_attr(trade, "entry_source", None),
        "entry_price": _trade_attr(trade, "entry_price"),
        "entry_price_source": _trade_attr(trade, "entry_price_source", None),
        "entry_condition": _trade_attr(trade, "entry_condition") or "BREAKOUT",
        "entry_ref_price": _trade_attr(trade, "entry_ref_price"),
        "signal_price": _trade_attr(trade, "signal_price", None),
        "stop": _trade_attr(trade, "stop_loss"),
        "stop_loss": _trade_attr(trade, "stop_loss"),
        "stop_price": _trade_attr(trade, "stop_price") or _trade_attr(trade, "stop_loss"),
        "target": _trade_attr(trade, "target"),
        "target_price": _trade_attr(trade, "target_price") or _trade_attr(trade, "target"),
        "rr_ratio": _trade_attr(trade, "rr_ratio", None),
        "target_rr": _trade_attr(trade, "target_rr", None),
        "original_stop": _trade_attr(trade, "original_stop") or _trade_attr(trade, "stop_loss"),
        "current_stop": _trade_attr(trade, "current_stop") or _trade_attr(trade, "stop_loss"),
        "trail_enabled": _trade_attr(trade, "trail_enabled"),
        "trail_rule": _trade_attr(trade, "trail_rule") or getattr(cfg, "TRAIL_RULE_DEFAULT", "MFE_MINUS_OFFSET"),
        "trail_offset": _trade_attr(trade, "trail_offset"),
        "trail_start": _trade_attr(trade, "trail_start") or getattr(cfg, "TRAIL_START_DEFAULT", "AFTER_1R"),
        "mfe_price": _trade_attr(trade, "mfe_price"),
        "trail_stop": _trade_attr(trade, "trail_stop"),
        "last_update_ts": _trade_attr(trade, "last_update_ts"),
        "exit_signal": _trade_attr(trade, "exit_signal"),
        "exit_reason": _trade_attr(trade, "exit_reason"),
        "status": _trade_attr(trade, "status") or "PLANNING",
        "activated_ts": _trade_attr(trade, "activated_ts"),
        "activation_price": _trade_attr(trade, "activation_price"),
        "fill_price": _trade_attr(trade, "fill_price"),
        "ltp_at_activation": _trade_attr(trade, "ltp_at_activation"),
        "qty": _trade_attr(trade, "qty"),
        "confidence": _trade_attr(trade, "confidence"),
        "builder_confidence": _trade_attr(
            trade,
            "builder_confidence",
            _trade_attr(trade, "confidence_after_soft_veto", _trade_attr(trade, "confidence")),
        ),
        "permission_confidence": _trade_attr(trade, "permission_confidence", None),
        "gating_base_confidence": _trade_attr(trade, "gating_base_confidence", None),
        "gating_final_confidence": _trade_attr(trade, "gating_final_confidence", None),
        "sizing_confluence_score": _trade_attr(trade, "sizing_confluence_score", None),
        "sizing_reason": _trade_attr(trade, "sizing_reason", None),
        "ml_proba_input": _trade_attr(trade, "ml_proba_input", None),
        "confluence_input": _trade_attr(trade, "confluence_input", None),
        "ml_proba_source": _trade_attr(trade, "ml_proba_source", None),
        "confluence_source": _trade_attr(trade, "confluence_source", None),
        "confidence_size_multiplier": _trade_attr(trade, "confidence_size_multiplier", None),
        "final_qty": _trade_attr(trade, "final_qty", None),
        "rank_score": _trade_attr(trade, "rank_score", None),
        "setup_strength": _trade_attr(trade, "setup_strength", None),
        "setup_score": _trade_attr(trade, "setup_score", None),
        "trigger_score": _trade_attr(trade, "trigger_score", None),
        "entry_quality_score": _trade_attr(trade, "entry_quality_score", None),
        "entry_quality_reason": _trade_attr(trade, "entry_quality_reason", None),
        "overextension_score": _trade_attr(trade, "overextension_score", None),
        "overextension_penalty": _trade_attr(trade, "overextension_penalty", None),
        "entry_distance_to_invalidation": _trade_attr(trade, "entry_distance_to_invalidation", None),
        "session_mode": _trade_attr(trade, "session_mode", None),
        "strategy_regime_mode": _trade_attr(trade, "strategy_regime_mode", None),
        "session_entry_penalty": _trade_attr(trade, "session_entry_penalty", None),
        "regime_fit": _trade_attr(trade, "regime_fit", None),
        "liquidity_score": _trade_attr(trade, "liquidity_score", None),
        "spread_score": _trade_attr(trade, "spread_score", None),
        "rr_score": _trade_attr(trade, "rr_score", None),
        "timing_score": _trade_attr(trade, "timing_score", None),
        "penalty_score": _trade_attr(trade, "penalty_score", None),
        "score_breakdown": _trade_attr(trade, "score_breakdown", None),
        "penalty_reasons": _trade_attr(trade, "penalty_reasons", None),
        "score_inputs_used": _trade_attr(trade, "score_inputs_used", None),
        "opportunity_score": _trade_attr(trade, "opportunity_score", None),
        "final_score": _trade_attr(trade, "final_score", None),
        "signal_score": _trade_attr(trade, "signal_score", None),
        "execution_score": _trade_attr(trade, "execution_score", None),
        "priority_score": _trade_attr(trade, "priority_score", None),
        "priority_weight_signal": _trade_attr(trade, "priority_weight_signal", None),
        "priority_weight_execution": _trade_attr(trade, "priority_weight_execution", None),
        "family_feedback_adjustment": _trade_attr(trade, "family_feedback_adjustment", None),
        "family_feedback_confidence": _trade_attr(trade, "family_feedback_confidence", None),
        "family_feedback_applied": _trade_attr(trade, "family_feedback_applied", None),
        "family_learning_adjustment": _trade_attr(trade, "family_learning_adjustment", None),
        "family_cap_effective": _trade_attr(trade, "family_cap_effective", None),
        "family_cap_reason": _trade_attr(trade, "family_cap_reason", None),
        "family_consensus_score": _trade_attr(trade, "family_consensus_score", None),
        "family_consensus_components": _trade_attr(trade, "family_consensus_components", None),
        "family_survival_score": _trade_attr(trade, "family_survival_score", None),
        "family_survival_components": _trade_attr(trade, "family_survival_components", None),
        "family_survived": _trade_attr(trade, "family_survived", None),
        "family_reject_reason": _trade_attr(trade, "family_reject_reason", None),
        "expectancy_score": _trade_attr(trade, "expectancy_score", None),
        "family_learning_state_generated_at": _trade_attr(trade, "family_learning_state_generated_at", None),
        "family_learning_state_version": _trade_attr(trade, "family_learning_state_version", None),
        "strategy_weight_adjustment": _trade_attr(trade, "strategy_weight_adjustment", None),
        "strategy_weight_confidence": _trade_attr(trade, "strategy_weight_confidence", None),
        "strategy_weight_applied": _trade_attr(trade, "strategy_weight_applied", None),
        "strategy_weight_state_generated_at": _trade_attr(trade, "strategy_weight_state_generated_at", None),
        "strategy_weight_state_version": _trade_attr(trade, "strategy_weight_state_version", None),
        "adaptive_threshold_adjustment": _trade_attr(trade, "adaptive_threshold_adjustment", None),
        "adaptive_threshold_impact_score": _trade_attr(trade, "adaptive_threshold_impact_score", None),
        "adaptive_threshold_applied": _trade_attr(trade, "adaptive_threshold_applied", None),
        "adaptive_threshold_key": _trade_attr(trade, "adaptive_threshold_key", None),
        "truth_quality": _trade_attr(trade, "truth_quality", None),
        "truth_quality_source": _trade_attr(trade, "truth_quality_source", None),
        "truth_allows_execution": _trade_attr(trade, "truth_allows_execution", None),
        "truth_block_reason": _trade_attr(trade, "truth_block_reason", None),
        "quote_truth_state": _trade_attr(trade, "quote_truth_state", None),
        "risk_budget_ok": _trade_attr(trade, "risk_budget_ok", None),
        "risk_budget_reason": _trade_attr(trade, "risk_budget_reason", None),
        "position_size_estimate": _trade_attr(trade, "position_size_estimate", None),
        "portfolio_heat_score": _trade_attr(trade, "portfolio_heat_score", None),
        "correlation_penalty": _trade_attr(trade, "correlation_penalty", None),
        "exposure_blocker": _trade_attr(trade, "exposure_blocker", None),
        "daily_kill_switch_active": _trade_attr(trade, "daily_kill_switch_active", None),
        "regime_failure_throttle": _trade_attr(trade, "regime_failure_throttle", None),
        "family_failure_throttle": _trade_attr(trade, "family_failure_throttle", None),
        "risk_learning_adjustment": _trade_attr(trade, "risk_learning_adjustment", None),
        "risk_learning_confidence": _trade_attr(trade, "risk_learning_confidence", None),
        "rejected_at_stage": _trade_attr(trade, "rejected_at_stage", None),
        "rejection_reason_code": _trade_attr(trade, "rejection_reason_code", None),
        "rejection_bucket": _trade_attr(trade, "rejection_bucket", None),
        "rejection_severity": _trade_attr(trade, "rejection_severity", None),
        "stage_authority_warning": _trade_attr(trade, "stage_authority_warning", None),
        "trade_density_limit_applied": _trade_attr(trade, "trade_density_limit_applied", None),
        "density_policy_name": _trade_attr(trade, "density_policy_name", None),
        "density_reject_reason": _trade_attr(trade, "density_reject_reason", None),
        "raw_candidate_count": _trade_attr(trade, "raw_candidate_count", None),
        "surviving_candidate_count": _trade_attr(trade, "surviving_candidate_count", None),
        "survival_rate": _trade_attr(trade, "survival_rate", None),
        "executable_rate": _trade_attr(trade, "executable_rate", None),
        "advisory_rate": _trade_attr(trade, "advisory_rate", None),
        "no_trade_rate": _trade_attr(trade, "no_trade_rate", None),
        "top_family_share": _trade_attr(trade, "top_family_share", None),
        "starvation_flag": _trade_attr(trade, "starvation_flag", None),
        "starvation_reason": _trade_attr(trade, "starvation_reason", None),
        "warning_engine_too_timid": _trade_attr(trade, "warning_engine_too_timid", None),
        "warning_filtering_without_edge_improvement": _trade_attr(trade, "warning_filtering_without_edge_improvement", None),
        "warning_family_starvation": _trade_attr(trade, "warning_family_starvation", None),
        "warning_threshold_cluster": _trade_attr(trade, "warning_threshold_cluster", None),
        "rejection_impact_warning": _trade_attr(trade, "rejection_impact_warning", None),
        "starvation_warning": _trade_attr(trade, "starvation_warning", None),
        "edge_improved_flag": _trade_attr(trade, "edge_improved_flag", None),
        "filtering_without_edge_flag": _trade_attr(trade, "filtering_without_edge_flag", None),
        "top_damaging_gate_rank": _trade_attr(trade, "top_damaging_gate_rank", None),
        "recommended_threshold_delta": _trade_attr(trade, "recommended_threshold_delta", None),
        "gate_protected_flag": _trade_attr(trade, "gate_protected_flag", None),
        "triage_recommendation": _trade_attr(trade, "triage_recommendation", None),
        "edge_preserve_flag": _trade_attr(trade, "edge_preserve_flag", None),
        "effective_session_policy": _trade_attr(trade, "effective_session_policy", None),
        "effective_regime_policy": _trade_attr(trade, "effective_regime_policy", None),
        "effective_risk_policy": _trade_attr(trade, "effective_risk_policy", None),
        "effective_family_risk_profile": _trade_attr(trade, "effective_family_risk_profile", None),
        "risk_profile_override_applied": _trade_attr(trade, "risk_profile_override_applied", None),
        "effective_family_survival_policy": _trade_attr(trade, "effective_family_survival_policy", None),
        "aggressiveness_mode": _trade_attr(trade, "aggressiveness_mode", None),
        "aggressiveness_adjustment": _trade_attr(trade, "aggressiveness_adjustment", None),
        "aggressiveness_adjustment_applied": _trade_attr(trade, "aggressiveness_adjustment_applied", None),
        "opportunity_rank": _trade_attr(trade, "opportunity_rank", None),
        "rank_global": _trade_attr(trade, "rank_global", None),
        "rank_within_symbol": _trade_attr(trade, "rank_within_symbol", None),
        "opportunity_bucket": _trade_attr(trade, "opportunity_bucket", None),
        "candidate_class": _trade_attr(trade, "candidate_class", None),
        "market_mode": _trade_attr(trade, "market_mode", None),
        "data_state": _trade_attr(trade, "data_state", None),
        "data_confidence": _trade_attr(trade, "data_confidence", None),
        "spread_stability_score": _trade_attr(trade, "spread_stability_score", None),
        "book_freshness_score": _trade_attr(trade, "book_freshness_score", None),
        "quote_completeness_score": _trade_attr(trade, "quote_completeness_score", None),
        "quote_consistency_score": _trade_attr(trade, "quote_consistency_score", None),
        "quote_completeness": _trade_attr(trade, "quote_completeness", None),
        "quote_consistency_ok": _trade_attr(trade, "quote_consistency_ok", None),
        "ltp_age_sec": _trade_attr(trade, "ltp_age_sec", None),
        "bid_age_sec": _trade_attr(trade, "bid_age_sec", None),
        "ask_age_sec": _trade_attr(trade, "ask_age_sec", None),
        "chain_snapshot_age_sec": _trade_attr(trade, "chain_snapshot_age_sec", None),
        "spread_source": _trade_attr(trade, "spread_source", None),
        "liquidity_validation_mode": _trade_attr(trade, "liquidity_validation_mode", None),
        "fresh_quote_ok": _trade_attr(trade, "fresh_quote_ok", None),
        "liquidity_ok": _trade_attr(trade, "liquidity_ok", None),
        "spread_ok": _trade_attr(trade, "spread_ok", None),
        "primary_blocker": _trade_attr(trade, "primary_blocker", None),
        "selected_for_execution": _trade_attr(trade, "selected_for_execution", None),
        "selection_reason": _trade_attr(trade, "selection_reason", None),
        "selector_outcome": _trade_attr(trade, "selector_outcome", None),
        "selection_probability": _trade_attr(trade, "selection_probability", None),
        "simulation_outcome": _trade_attr(trade, "simulation_outcome", None),
        "simulation_fill_status": _trade_attr(trade, "simulation_fill_status", None),
        "simulation_fill_qty": _trade_attr(trade, "simulation_fill_qty", None),
        "mfe": _trade_attr(trade, "mfe", None),
        "mae": _trade_attr(trade, "mae", None),
        "simulated_pnl": _trade_attr(trade, "simulated_pnl", None),
        "would_have_worked": _trade_attr(trade, "would_have_worked", None),
        "rejection_saved_loss": _trade_attr(trade, "rejection_saved_loss", None),
        "rejection_missed_win": _trade_attr(trade, "rejection_missed_win", None),
        "realized_r_multiple": _trade_attr(trade, "realized_r_multiple", None),
        "stop_hit_before_target": _trade_attr(trade, "stop_hit_before_target", None),
        "risk_plan_respected": _trade_attr(trade, "risk_plan_respected", None),
        "size_multiplier_reason": _trade_attr(trade, "size_multiplier_reason", None),
        "opportunity_size_multiplier": _trade_attr(trade, "opportunity_size_multiplier", None),
        "threshold_base": _trade_attr(trade, "threshold_base", None),
        "threshold_effective": _trade_attr(trade, "threshold_effective", None),
        "threshold_adjustment_reason": _trade_attr(trade, "threshold_adjustment_reason", None),
        "spread_penalty": _trade_attr(trade, "spread_penalty", None),
        "executable_price_estimate": _trade_attr(trade, "executable_price_estimate", None),
        "execution_ok": _trade_attr(trade, "execution_ok", None),
        "order_policy": _trade_attr(trade, "order_policy", None),
        "order_policy_reason": _trade_attr(trade, "order_policy_reason", None),
        "slot_id": _trade_attr(trade, "slot_id", None),
        "allocation_reason": _trade_attr(trade, "allocation_reason", None),
        "allocation_score": _trade_attr(trade, "allocation_score", None),
        "capital_assigned": _trade_attr(trade, "capital_assigned", None),
        "size_multiplier_effective": _trade_attr(trade, "size_multiplier_effective", None),
        "strategy": _trade_attr(trade, "strategy"),
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "candidate_type": _trade_attr(trade, "candidate_type", None),
        "strategy_family": _trade_attr(trade, "strategy_family", None),
        "direction_family": _trade_attr(trade, "direction_family", None),
        "family_rank": _trade_attr(trade, "family_rank", None),
        "family_blocker": _trade_attr(trade, "family_blocker", None),
        "family_strength": _trade_attr(trade, "family_strength", None),
        "family_allowed_in_context": _trade_attr(trade, "family_allowed_in_context", None),
        "family_gate_reason": _trade_attr(trade, "family_gate_reason", None),
        "family_gate_override_applied": _trade_attr(trade, "family_gate_override_applied", None),
        "setup_variant": _trade_attr(trade, "setup_variant", None),
        "candidate_status": _trade_attr(trade, "candidate_status", None),
        "fallback_candidate": (
            _trade_attr(trade, "fallback_candidate", None)
            if _trade_attr(trade, "fallback_candidate", None) is not None
            else bool((_trade_attr(trade, "source_flags", {}) or {}).get("fallback_candidate"))
        ),
        "regime": _trade_attr(trade, "regime"),
        "regime_confidence": _trade_attr(trade, "regime_confidence"),
        "day_confidence": _trade_attr(trade, "day_confidence"),
        "orb_bias": _trade_attr(trade, "orb_bias"),
        "tier": _trade_attr(trade, "tier", None),
        "legs": _trade_attr(trade, "legs", None),
        "max_profit": _trade_attr(trade, "max_profit", None),
        "max_loss": _trade_attr(trade, "max_loss", None),
        "max_profit_label": _trade_attr(trade, "max_profit_label", None),
        "max_loss_label": _trade_attr(trade, "max_loss_label", None),
        "breakeven_low": _trade_attr(trade, "breakeven_low", None),
        "breakeven_high": _trade_attr(trade, "breakeven_high", None),
        "est_pnl_at_ltp": _trade_attr(trade, "est_pnl_at_ltp", None),
        "opt_ltp": _trade_attr(trade, "opt_ltp", None),
        "opt_bid": _trade_attr(trade, "opt_bid", None),
        "opt_ask": _trade_attr(trade, "opt_ask", None),
        "volume": _trade_attr(trade, "volume", None),
        "current_volume": _trade_attr(trade, "current_volume", None),
        "oi": _trade_attr(trade, "oi", None),
        "oi_change": _trade_attr(trade, "oi_change", None),
        "liquidity_source": _trade_attr(trade, "liquidity_source", None),
        "liquidity_age_sec": _trade_attr(trade, "liquidity_age_sec", None),
        "liquidity_cache_hit": _trade_attr(trade, "liquidity_cache_hit", None),
        "liquidity_missing_fields": _trade_attr(trade, "liquidity_missing_fields", None),
        "tick_volume": _trade_attr(trade, "tick_volume", None),
        "spread_pct": _trade_attr(trade, "spread_pct", None),
        "quote_ok": _trade_attr(trade, "quote_ok", None),
        "underlying_spot": _trade_attr(trade, "underlying_spot", None),
        "spot_source": _trade_attr(trade, "spot_source", None),
        "option_ltp_source": _trade_attr(trade, "option_ltp_source", None),
        "option_ltp_timestamp": _trade_attr(trade, "option_ltp_timestamp", None),
        "current_ltp": _trade_attr(trade, "current_ltp", None),
        "suggested_entry": _trade_attr(trade, "suggested_entry", None),
        "expected_entry": _trade_attr(trade, "expected_entry", None),
        "expected_entry_source": _trade_attr(trade, "expected_entry_source", None),
        "fill_entry": _trade_attr(trade, "fill_entry", None),
        "execution_entry": _trade_attr(trade, "execution_entry", None),
        "execution_entry_source": _trade_attr(trade, "execution_entry_source", None),
        "execution_entry_status": _trade_attr(trade, "execution_entry_status", None),
        "display_entry": _trade_attr(trade, "display_entry", None),
        "display_entry_source": _trade_attr(trade, "display_entry_source", None),
        "display_entry_status": _trade_attr(trade, "display_entry_status", None),
        "entry_display_status": _trade_attr(trade, "entry_display_status", None),
        "entry_reason": _trade_attr(trade, "entry_reason", None),
        "entry_clear_reason": _trade_attr(trade, "entry_clear_reason", None),
        "entry_block_code": _trade_attr(trade, "entry_block_code", None),
        "price_age_sec": _trade_attr(trade, "price_age_sec", None),
        "quote_age_sec": _trade_attr(trade, "quote_age_sec", None),
        "entry_status": _trade_attr(trade, "entry_status", None),
        "price_source": _trade_attr(trade, "price_source", None),
        "quote_source": _trade_attr(trade, "quote_source", None),
        "mark_price": _trade_attr(trade, "mark_price", None),
        "mid_price": _trade_attr(trade, "mid_price", None),
        "best_bid": _trade_attr(trade, "best_bid", None),
        "best_ask": _trade_attr(trade, "best_ask", None),
        "entry_price_proxy": _trade_attr(trade, "entry_price_proxy", None),
        "entry_price_proxy_buy": _trade_attr(trade, "entry_price_proxy_buy", None),
        "entry_price_proxy_sell": _trade_attr(trade, "entry_price_proxy_sell", None),
        "chain_source": _trade_attr(trade, "chain_source", None),
        "trade_score": _trade_attr(trade, "trade_score", None),
        "trade_alignment": _trade_attr(trade, "trade_alignment", None),
        "trade_score_detail": _trade_attr(trade, "trade_score_detail", None),
        "tradable": _trade_attr(trade, "tradable", None),
        "tradable_reasons_blocking": _trade_attr(trade, "tradable_reasons_blocking", None),
        "execution_allowed": _trade_attr(trade, "execution_allowed", None),
        "direction": _trade_attr(trade, "direction", None),
        "execution_mode": _trade_attr(trade, "execution_mode", None),
        "mode": _trade_attr(trade, "mode", None),
        "market_open": _trade_attr(trade, "market_open", None),
        "market_context": _trade_attr(trade, "market_context", None),
        "global_confidence": _trade_attr(trade, "global_confidence", None),
        "permission": _trade_attr(trade, "permission", None),
        "permission_reason": _trade_attr(trade, "permission_reason", None),
        "readiness": _trade_attr(trade, "readiness", None),
        "final_action": _trade_attr(trade, "final_action", None),
        "execution_status": _trade_attr(trade, "execution_status", None),
        "countertrend": _trade_attr(trade, "countertrend", None),
        "source_flags": _trade_attr(trade, "source_flags", None),
        "raw_signal_confidence": _trade_attr(trade, "raw_signal_confidence", None),
        "confidence_raw_canonical": _trade_attr(trade, "confidence_raw_canonical", None),
        "confidence_stage_trace": _trade_attr(trade, "confidence_stage_trace", None),
        "confidence_model_raw": _trade_attr(trade, "confidence_model_raw", None),
        "confidence_model_component": _trade_attr(trade, "confidence_model_component", None),
        "confidence_micro_component": _trade_attr(trade, "confidence_micro_component", None),
        "confidence_micro_blend_method": _trade_attr(trade, "confidence_micro_blend_method", None),
        "confidence_after_micro": _trade_attr(trade, "confidence_after_micro", None),
        "confidence_after_alpha": _trade_attr(trade, "confidence_after_alpha", None),
        "confidence_after_latency": _trade_attr(trade, "confidence_after_latency", None),
        "confidence_before_soft_veto": _trade_attr(trade, "confidence_before_soft_veto", None),
        "confidence_after_soft_veto": _trade_attr(trade, "confidence_after_soft_veto", None),
        "confidence_after_time_decay": _trade_attr(trade, "confidence_after_time_decay", None),
        "confidence_time_decay_factor": _trade_attr(trade, "confidence_time_decay_factor", None),
        "confidence_age_seconds": _trade_attr(trade, "confidence_age_seconds", None),
        "confidence_market_velocity": _trade_attr(trade, "confidence_market_velocity", None),
        "confidence_age_factor": _trade_attr(trade, "confidence_age_factor", None),
        "confidence_penalty_soft_veto_total": _trade_attr(trade, "confidence_penalty_soft_veto_total", None),
        "confidence_penalty_soft_veto_reasons": _trade_attr(trade, "confidence_penalty_soft_veto_reasons", None),
        "confidence_gate_threshold": _trade_attr(trade, "confidence_gate_threshold", None),
        "confidence_raw_gate_threshold": _trade_attr(trade, "confidence_raw_gate_threshold", None),
        "confidence_final_gate_threshold": _trade_attr(trade, "confidence_final_gate_threshold", None),
        "confidence_rejection_stage": _trade_attr(trade, "confidence_rejection_stage", None),
        "confidence_base": _trade_attr(trade, "confidence_base", None),
        "confidence_penalty_total": _trade_attr(trade, "confidence_penalty_total", None),
        "confidence_penalty_reasons": _trade_attr(trade, "confidence_penalty_reasons", None),
        "snapshot_id": _trade_attr(trade, "snapshot_id", None),
        "timestamp": str(_trade_attr(trade, "timestamp")),
        "upstox_instrument_key": _trade_attr(trade, "upstox_instrument_key"),
    }
    if extra:
        entry.update(extra)
    entry = _mark_synthetic_offhours_origin(entry)
    strategy_id, strategy_name = _resolve_queue_strategy_identity(entry)
    entry["strategy_id"] = strategy_id
    entry["strategy_name"] = strategy_name
    entry = _apply_candidate_identity(entry)
    mode_for_entry = _entry_execution_mode(entry) or mode_for_entry
    allow_stale_quotes_for_entry = _allow_rest_fallback_for_mode(mode_for_entry)
    market_open_for_entry, market_open_source = _resolve_entry_market_open(
        entry,
        mode_for_entry,
        allow_stale_quotes_for_entry,
    )
    entry["market_open"] = market_open_for_entry
    entry["market_open_source"] = market_open_source
    return entry, mode_for_entry, allow_stale_quotes_for_entry, market_open_for_entry


def _apply_quote_and_entry_logic(
    entry: dict,
    *,
    mode_for_entry: str,
    allow_stale_quotes_for_entry: bool,
    market_open_for_entry: bool,
) -> dict:
    if entry.get("instrument") == "OPT":
        entry = _mark_synthetic_offhours_origin(entry)
        input_token_missing = entry.get("instrument_token") in (None, "", "None") and bool(entry.get("tradingsymbol"))
        entry = _enrich_contract_identity(entry)
        if entry.get("target") in (None, "", "None"):
            rr_default = float(getattr(cfg, "TARGET_RR_DEFAULT", 1.5)) if cfg else 1.5
            derived_target = _derive_target(entry.get("entry"), entry.get("stop"), entry.get("side"), rr_default)
            if derived_target is not None:
                entry["target"] = derived_target
                entry["target_derived"] = True
                entry["target_rr"] = rr_default
        unresolved_contract = _is_unresolved_option_contract(entry)
        if unresolved_contract:
            entry = _apply_unresolved_contract_state(entry)
        else:
            entry = _clear_unresolved_contract_state(entry)
            token_val = entry.get("instrument_token")
            subscription_ok = True
            if token_val is not None:
                try:
                    subscription_ok = bool(
                        ensure_subscribed_tokens([int(token_val)], reason="trade_created", symbol=entry.get("symbol"))
                    )
                except Exception:
                    subscription_ok = False
            token_value = entry.get("instrument_token")
            if not subscription_ok and not entry.get("_origin_synthetic_offhours"):
                entry["option_ltp_source"] = "subscription_failed"
                entry["current_ltp"] = None
                entry["option_ltp_timestamp"] = None
            current_ltp = None
            ltp_ts_epoch = None
            rest_fallback_used = False
            if token_value not in (None, "", "None"):
                try:
                    current_ltp, ltp_ts_epoch = get_ltp(token_value, decision_path=True)
                except TypeError:
                    current_ltp, ltp_ts_epoch = get_ltp(token_value)
                except Exception:
                    current_ltp, ltp_ts_epoch = None, None
            token_present = token_value not in (None, "", "None")
            explicit_mode_for_fallback = _entry_execution_mode_explicit(entry)
            allow_rest_fallback = bool(
                token_present
                and entry.get("tradingsymbol")
                and (subscription_ok or _allow_rest_fallback_for_mode(explicit_mode_for_fallback))
            )
            if current_ltp is None and allow_rest_fallback:
                fallback_ltp, fallback_ts_epoch, fallback_used = _resolve_rest_fallback_ltp(
                    token_value=token_value,
                    tradingsymbol=entry.get("tradingsymbol"),
                    now_epoch=time.time(),
                )
                if fallback_ltp is not None and fallback_ts_epoch is not None:
                    current_ltp, ltp_ts_epoch = float(fallback_ltp), float(fallback_ts_epoch)
                    rest_fallback_used = bool(fallback_used)
            synthetic_offhours = _is_synthetic_offhours_row(entry)
            live_quote_available = current_ltp is not None and ltp_ts_epoch is not None
            live_quote_source = "rest_fallback" if rest_fallback_used else "tick_store"
            token_missing_identified = bool(input_token_missing)
            live_took_over_synthetic = _should_force_live_reference_for_takeover(
                entry,
                current_ltp=current_ltp,
                ltp_ts_epoch=ltp_ts_epoch,
            )
            if live_took_over_synthetic:
                entry = _clear_synthetic_offhours_state_for_live_takeover(entry)
                entry = _clear_synthetic_pricing_state_for_live_takeover(entry)
                if live_quote_source == "tick_store":
                    entry.pop("_origin_synthetic_offhours", None)
                synthetic_offhours = False
            if not synthetic_offhours:
                builder_quote_truth = _quote_truth_snapshot_from_entry(entry, source="builder", now_epoch=time.time())
                queue_quote_truth = _quote_truth_snapshot_from_entry(
                    {
                        **entry,
                        "current_ltp": current_ltp,
                        "option_ltp_timestamp": ltp_ts_epoch,
                        "quote_ts_epoch": ltp_ts_epoch,
                        "quote_source": live_quote_source,
                        "option_ltp_source": live_quote_source,
                    },
                    source="queue",
                    now_epoch=time.time(),
                )
                entry, quote_truth_action, quote_truth_drift = _merge_quote_truth(
                    entry,
                    builder_truth=builder_quote_truth,
                    queue_truth=queue_quote_truth,
                    now_epoch=time.time(),
                )
                entry["source_flags"] = dict(entry.get("source_flags") or {})
                entry["source_flags"]["quote_truth_action"] = quote_truth_action
                entry["source_flags"]["quote_truth_drift"] = quote_truth_drift
                current_ltp = _safe_float(entry.get("current_ltp"))
                ltp_ts_epoch = _safe_float(entry.get("option_ltp_timestamp") or entry.get("quote_ts_epoch") or ltp_ts_epoch)
            validation_signal_price = _safe_float(entry.get("signal_price"))
            pre_validation_entry = None if live_took_over_synthetic else _safe_float(entry.get("entry"))
            if live_took_over_synthetic:
                validation_reference_entry = dict(entry)
                for field in (
                    "expected_entry",
                    "expected_entry_source",
                    "entry_ref_price",
                    "validation_reference_price",
                    "validation_reference_source",
                    "pre_validation_entry",
                    "suggested_entry",
                    "entry",
                    "entry_price",
                    "signal_price",
                ):
                    validation_reference_entry.pop(field, None)
                validation_reference_price, validation_reference_source = _validation_reference_price(
                    validation_reference_entry,
                    current_ltp=current_ltp,
                )
                validation_reference_source = live_quote_source
            else:
                validation_reference_price, validation_reference_source = _validation_reference_price(
                    entry,
                    current_ltp=current_ltp,
                    allow_live_ltp=not token_missing_identified,
                )
            if (
                (not token_missing_identified)
                and not entry.get("_origin_synthetic_offhours")
                and not _should_preserve_missing_queue_only_entry(entry)
                and _safe_float(entry.get("expected_entry")) is None
                and validation_reference_price is not None
            ):
                entry["expected_entry"] = validation_reference_price
            if (
                (not token_missing_identified)
                and not entry.get("_origin_synthetic_offhours")
                and _is_stale_pre_validation_entry(pre_validation_entry, validation_reference_price)
            ):
                entry["entry"] = validation_reference_price
            if synthetic_offhours:
                synthetic_entry = _safe_float(entry.get("_synthetic_entry_price_original"))
                if synthetic_entry is None:
                    synthetic_entry = _safe_float(entry.get("entry_price"))
                if synthetic_entry is None:
                    synthetic_entry = _safe_float(entry.get("expected_entry"))
                entry["current_ltp"] = None
                entry["option_ltp_timestamp"] = None
                entry["validation_signal_price"] = validation_signal_price
                entry["validation_reference_price"] = synthetic_entry
                entry["validation_reference_source"] = "synthetic_offhours"
                entry["pre_validation_entry"] = pre_validation_entry
                entry["quote_validation_status"] = "OFFHOURS_SYNTHETIC"
                entry["entry_status"] = "OFFHOURS_SYNTHETIC"
                entry["suggested_entry"] = synthetic_entry
                if _safe_float(entry.get("expected_entry")) is None and synthetic_entry is not None:
                    entry["expected_entry"] = synthetic_entry
                if _is_stale_pre_validation_entry(pre_validation_entry, synthetic_entry):
                    entry["entry"] = synthetic_entry
                if not entry.get("option_ltp_source"):
                    entry["option_ltp_source"] = "synthetic_offhours"
            else:
                if token_missing_identified:
                    advisory_entry = _safe_float(entry.get("suggested_entry"))
                    if advisory_entry is None:
                        advisory_entry = pre_validation_entry
                    if advisory_entry is None:
                        advisory_entry = _safe_float(entry.get("entry_price"))
                    if advisory_entry is None:
                        advisory_entry = _safe_float(entry.get("signal_price"))
                    if advisory_entry is None:
                        advisory_entry = _safe_float(entry.get("expected_entry"))
                    entry["current_ltp"] = current_ltp
                    entry["option_ltp_timestamp"] = ltp_ts_epoch
                    entry["price_age_sec"] = None
                    entry["freshness_reason"] = None
                    entry["freshness_market_open"] = market_open_for_entry
                    entry["freshness_now_epoch"] = None
                    entry["freshness_quote_epoch"] = None
                    entry["freshness_candle_epoch"] = None
                    entry["freshness_threshold_sec"] = None
                    entry["freshness_selected_source"] = None
                    entry["freshness_selected_age_sec"] = None
                    entry["candle_age_sec"] = None
                    if entry.get("_origin_synthetic_offhours"):
                        entry["quote_validation_status"] = "OFFHOURS_SYNTHETIC"
                    else:
                        entry["quote_validation_status"] = _resolve_quote_validation_status(entry, "non_executable")
                    entry["validation_signal_price"] = validation_signal_price
                    entry["validation_reference_price"] = advisory_entry
                    entry["validation_reference_source"] = "tradingsymbol_without_token"
                    entry["pre_validation_entry"] = pre_validation_entry
                    entry["entry_status"] = "displayable"
                    if not _is_offhours_displayable(entry):
                        entry["suggested_entry"] = advisory_entry
                    if (
                        not entry.get("_origin_synthetic_offhours")
                        and not _should_preserve_missing_queue_only_entry(entry)
                        and _safe_float(entry.get("expected_entry")) is None
                        and advisory_entry is not None
                    ):
                        entry["expected_entry"] = advisory_entry
                    entry["entry"] = advisory_entry
                    entry.setdefault("execution_allowed", False)
                    entry["option_ltp_source"] = entry.get("option_ltp_source") or "unknown"
                    entry["quote_source"] = entry.get("quote_source") or entry["option_ltp_source"]
                else:
                    validation = validate_live_entry(
                        signal_price=validation_reference_price,
                        current_ltp=current_ltp,
                        ltp_ts_epoch=ltp_ts_epoch,
                        candle_ts_epoch=_safe_float(
                            entry.get("candle_ts_epoch")
                            or entry.get("last_candle_ts_epoch")
                            or entry.get("signal_candle_epoch")
                        ),
                        mode=mode_for_entry,
                        allow_stale_quotes=allow_stale_quotes_for_entry,
                        market_open=market_open_for_entry,
                        now_epoch=float(time.time()),
                        segment="NSE_FNO",
                        token=token_value,
                        symbol=entry.get("symbol"),
                        trade_id=str(entry.get("advisory_id") or entry.get("trade_id") or entry.get("trade_key") or ""),
                        require_token=True,
                        require_strict_match=False,
                        allow_candle_fallback=True,
                    )
                    entry["current_ltp"] = validation.get("current_ltp")
                    entry["option_ltp_timestamp"] = ltp_ts_epoch
                    entry["price_age_sec"] = validation.get("price_age_sec")
                    entry["freshness_reason"] = validation.get("freshness_reason")
                    entry["freshness_market_open"] = validation.get("freshness_market_open")
                    entry["freshness_now_epoch"] = validation.get("freshness_now_epoch")
                    entry["freshness_quote_epoch"] = validation.get("freshness_quote_epoch")
                    entry["freshness_candle_epoch"] = validation.get("freshness_candle_epoch")
                    entry["freshness_threshold_sec"] = validation.get("freshness_threshold_sec")
                    entry["freshness_selected_source"] = validation.get("freshness_selected_source")
                    entry["freshness_selected_age_sec"] = validation.get("freshness_selected_age_sec")
                    entry["candle_age_sec"] = validation.get("candle_age_sec")
                    entry["validation_signal_price"] = validation_signal_price
                    entry["validation_reference_price"] = (
                        _safe_float(validation.get("suggested_entry"))
                        if live_took_over_synthetic
                        else validation_reference_price
                    )
                    entry["validation_reference_source"] = (
                        live_quote_source if live_took_over_synthetic else validation_reference_source
                    )
                    if validation.get("valid"):
                        entry["option_ltp_source"] = "rest_fallback" if rest_fallback_used else "tick_store"
                        entry["quote_source"] = entry["option_ltp_source"]
                    if entry.get("_origin_synthetic_offhours"):
                        entry["quote_validation_status"] = "OFFHOURS_SYNTHETIC"
                    else:
                        entry["quote_validation_status"] = _resolve_quote_validation_status(
                            entry,
                            validation.get("entry_status"),
                        )
                    entry["pre_validation_entry"] = pre_validation_entry
                    entry_status_value = validation.get("entry_status")
                    if rest_fallback_used and validation.get("valid"):
                        entry_status_value = "REST_FALLBACK"
                    entry["entry_status"] = entry_status_value
                    if not _is_offhours_displayable(entry):
                        entry["suggested_entry"] = validation.get("suggested_entry")
                    if _safe_float(entry.get("expected_entry")) is None:
                        if (
                            not entry.get("_origin_synthetic_offhours")
                            and not _should_force_missing_queue_only_lifecycle(entry)
                        ):
                            expected_entry = _safe_float(validation.get("suggested_entry"))
                            if expected_entry is None:
                                expected_entry = _safe_float(validation.get("current_ltp"))
                            if expected_entry is not None:
                                entry["expected_entry"] = expected_entry
                    if live_took_over_synthetic and _safe_float(entry.get("expected_entry")) is not None:
                        entry["expected_entry_source"] = live_quote_source
                    if not _should_force_missing_queue_only_lifecycle(entry):
                        if validation.get("valid"):
                            entry["entry"] = validation.get("suggested_entry")
                        else:
                            fallback_entry = _safe_float(validation.get("suggested_entry"))
                            if fallback_entry is None:
                                fallback_entry = _safe_float(current_ltp)
                            entry["entry"] = fallback_entry
                            if fallback_entry is None:
                                fallback_entry = _safe_float(current_ltp)
                            entry.setdefault("execution_allowed", False)
                            if rest_fallback_used:
                                entry["option_ltp_source"] = "rest_fallback"
                                entry["quote_source"] = "rest_fallback"
            if (
                current_ltp is None
                and token_present
                and not subscription_ok
                and not _allow_rest_fallback_for_mode(explicit_mode_for_fallback)
            ):
                entry["entry"] = None
                entry["entry_status"] = "NO_LIVE_OPTION_FEED"
                if entry.get("_origin_synthetic_offhours"):
                    entry["quote_validation_status"] = "OFFHOURS_SYNTHETIC"
                else:
                    entry["quote_validation_status"] = "NO_LIVE_OPTION_FEED"
                entry["option_ltp_source"] = "subscription_failed"
                entry["quote_source"] = "subscription_failed"
                entry["subscription_failed"] = True
                entry["execution_allowed"] = False
            if not entry.get("option_ltp_source"):
                entry["option_ltp_source"] = "rest_fallback" if rest_fallback_used else "tick_store"
            if not entry.get("quote_source"):
                entry["quote_source"] = entry.get("option_ltp_source")
            entry["post_validation_entry"] = _safe_float(entry.get("entry"))
            if not entry.get("upstox_instrument_key"):
                try:
                    entry["upstox_instrument_key"] = resolve_upstox_key(entry)
                except Exception:
                    entry["upstox_instrument_key"] = None
            try:
                entry_val = float(entry.get("entry") or 0.0)
                target_val = float(entry.get("target") or 0.0)
                stop_val = float(entry.get("stop") or 0.0)
                if entry_val > 0 and target_val > 0:
                    entry["target_premium"] = round(abs(target_val - entry_val), 2)
                if entry_val > 0 and stop_val > 0:
                    entry["stop_premium"] = round(abs(entry_val - stop_val), 2)
            except Exception:
                pass
    return _canonicalize_entry_lifecycle(
        entry,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
        market_open_for_entry=market_open_for_entry,
        align_for_schema=False,
    )


def _finalize_review_queue_entry(
    entry: dict,
    *,
    mode_for_entry: str,
    allow_stale_quotes_for_entry: bool,
    market_open_for_entry: bool,
) -> dict:
    perm = {}
    decision_snapshot = _decision_fields_snapshot(entry)
    preserve_decision = _decision_fields_present(entry)
    incoming_decision = {
        "permission": str(entry.get("permission") or "").strip().upper() or None,
        "permission_reason": str(entry.get("permission_reason") or "").strip() or None,
        "readiness": str(entry.get("readiness") or "").strip().upper() or None,
        "final_action": str(entry.get("final_action") or "").strip().upper() or None,
        "execution_status": str(entry.get("execution_status") or "").strip().lower() or None,
    }
    if preserve_decision:
        entry = _apply_candidate_scoring(
            entry,
            mode_for_entry=mode_for_entry,
            allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
            market_open_for_entry=market_open_for_entry,
        )
        entry = _apply_fallback_execution_kill(entry)
        if str(entry.get("permission") or "").strip() and not str(entry.get("permission_base") or "").strip():
            entry["permission_base"] = str(entry.get("permission")).strip().upper()
        if str(entry.get("permission_reason") or "").strip() and not str(entry.get("permission_reason_base") or "").strip():
            entry["permission_reason_base"] = str(entry.get("permission_reason") or "")
        entry = _apply_canonical_quote_age(entry)
        entry = enforce_entry_contract(entry, stage="review_queue.add_to_queue")
        _log_entry_lifecycle_resolution(entry)
        entry = _apply_expectancy_gate_if_present(entry)
        _emit_trade_lifecycle_event(
            entry,
            stage="readiness_gating",
            status=str(entry.get("readiness") or entry.get("permission") or "unknown"),
            reason=str(entry.get("final_blocker") or entry.get("permission_reason") or entry.get("entry_block_code") or ""),
            extra={
                "execution_status": entry.get("execution_status"),
                "final_action": entry.get("final_action"),
            },
        )
        _emit_trade_lifecycle_event(
            entry,
            stage="execution_feasibility",
            status=str(entry.get("execution_entry_status") or entry.get("execution_status") or "unknown"),
            reason=str(entry.get("entry_block_code") or entry.get("execution_status") or entry.get("permission_reason") or ""),
            extra={
                "execution_entry": entry.get("execution_entry"),
                "execution_entry_source": entry.get("execution_entry_source"),
                "display_entry": entry.get("display_entry"),
            },
        )
        entry = _record_decision_parity(entry, decision_snapshot)
        if str(entry.get("final_action") or "").strip().upper() == "BLOCK":
            entry = _preserve_blocked_candidate_metadata(entry)
        return _classify_candidate_status(entry)
    try:
        entry = _apply_candidate_scoring(
            entry,
            mode_for_entry=mode_for_entry,
            allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
            market_open_for_entry=market_open_for_entry,
        )
        entry = _apply_fallback_execution_kill(entry)
        entry.pop("permission_downgraded_from", None)
        entry.pop("permission_downgrade_reason", None)
        raw_conf = entry.get("raw_signal_confidence")
        if raw_conf is None:
            raw_conf = entry.get("confidence")
        regime = entry.get("regime") or "UNKNOWN"
        regime_conf = entry.get("regime_confidence")
        if regime_conf is None:
            regime_conf = entry.get("day_confidence")
        orb_bias = entry.get("orb_bias")
        if not orb_bias and isinstance(entry.get("source_flags"), dict):
            orb_bias = entry.get("source_flags", {}).get("orb_bias")
        option_type = entry.get("option_type") or entry.get("type")
        side = entry.get("side")
        last_candle = entry.get("last_candle")
        atr_ratio = entry.get("atr_ratio") or entry.get("atr_pct")
        perm = build_permission_payload(
            signal_score=raw_conf,
            regime=regime,
            regime_conf=regime_conf,
            orb_bias=orb_bias,
            option_type=option_type,
            side=side,
            execution_mode=mode_for_entry,
            last_candle=last_candle if isinstance(last_candle, dict) else None,
            atr_ratio=atr_ratio,
        )
        entry["direction"] = perm.get("direction")
        entry["global_confidence"] = perm.get("global_confidence")
        entry["permission_confidence"] = _safe_float(perm.get("global_confidence"))
        computed_permission = str(perm.get("permission") or "").strip().upper() or None
        computed_reason = str(perm.get("permission_reason") or "").strip() or None
        if not incoming_decision.get("permission") and computed_permission:
            entry["permission"] = computed_permission
        if not incoming_decision.get("permission_reason") and computed_reason:
            entry["permission_reason"] = computed_reason
        entry["permission_base"] = incoming_decision.get("permission") or computed_permission or str(entry.get("permission") or "").strip().upper()
        entry["permission_reason_base"] = incoming_decision.get("permission_reason") or computed_reason or str(entry.get("permission_reason") or "")
        entry["countertrend"] = perm.get("countertrend")
        entry["raw_signal_confidence"] = raw_conf
        entry["threshold_display"] = _safe_float(perm.get("threshold_display"))
        entry["threshold_advisory"] = _safe_float(perm.get("threshold_advisory"))
        entry["threshold_execution"] = _safe_float(perm.get("threshold_execution"))
        entry["confidence_vs_threshold_reason"] = str(
            perm.get("confidence_vs_threshold_reason") or ""
        )
        if perm.get("regime_confidence") is not None:
            entry["regime_confidence"] = perm.get("regime_confidence")
        _log_low_global_conf_once_per_symbol_minute(
            symbol=entry.get("symbol"),
            raw_conf=raw_conf,
            regime_conf=entry.get("regime_confidence"),
            orb_bias=(perm.get("orb_bias") if isinstance(perm, dict) else entry.get("orb_bias")),
            orb_factor=(perm.get("orb_factor") if isinstance(perm, dict) else None),
            reg_penalty=(perm.get("regime_penalty") if isinstance(perm, dict) else None),
            global_conf=entry.get("global_confidence"),
        )
        entry_status = str(entry.get("entry_status") or "")
        if bool(entry.get("subscription_failed")) and entry_status == "NO_LIVE_OPTION_FEED":
            entry["execution_allowed"] = False
    except Exception as exc:
        logger.warning("permission_compute_failed: %s", exc)
        if not incoming_decision.get("permission_reason"):
            entry["permission_reason"] = f"permission_compute_failed:{type(exc).__name__}"
    decision_seed = {
        "permission": incoming_decision.get("permission") or str(entry.get("permission_base") or entry.get("permission") or "").strip().upper() or None,
        "permission_reason": incoming_decision.get("permission_reason") or str(entry.get("permission_reason_base") or entry.get("permission_reason") or "").strip() or None,
        "readiness": incoming_decision.get("readiness"),
        "final_action": incoming_decision.get("final_action"),
        "execution_status": incoming_decision.get("execution_status"),
    }
    entry_status = str(entry.get("entry_status") or "")
    entry_block_reason = entry_status if _is_entry_status_blocking(entry_status) else None
    permission = str(entry.get("permission") or "ADVISORY_ONLY").upper()
    permission_reason = str(entry.get("permission_reason") or "")
    global_conf = _safe_float(entry.get("global_confidence"))
    gate_snapshot = {
        "freshness": {
            "max_tick_age_sec": _safe_float(_canonical_quote_age_sec(entry)),
            "sla_threshold_sec": _safe_float(getattr(cfg, "OPTION_LTP_SLA_SEC", 2.0)),
        },
        "feed_state": (
            entry.get("feed_state")
            or (entry.get("feed_health_snapshot") or {}).get("state")
            or "UNKNOWN"
        ),
        "market_open": market_open_for_entry,
        "execution_mode": mode_for_entry,
        "allow_stale_quotes": allow_stale_quotes_for_entry,
    }
    gate_candidate = {
        "current_ltp": _safe_float(entry.get("current_ltp") or entry.get("live_ltp") or entry.get("entry")),
        "option_age_sec": _safe_float(_canonical_quote_age_sec(entry)),
        "spread_pct": _quote_spread_pct(entry),
        "volume": _first_present_float(entry, ("volume", "current_volume", "tick_volume")),
        "best_bid": _safe_float(entry.get("best_bid") or entry.get("bid") or entry.get("opt_bid")),
        "best_ask": _safe_float(entry.get("best_ask") or entry.get("ask") or entry.get("opt_ask")),
        "feed_state": gate_snapshot["feed_state"],
        "global_confidence": _safe_float(entry.get("global_confidence")),
        "confidence": _safe_float(entry.get("confidence")),
        "raw_signal_confidence": _safe_float(entry.get("raw_signal_confidence")),
        "market_open": market_open_for_entry,
        "execution_mode": mode_for_entry,
        "allow_stale_quotes": allow_stale_quotes_for_entry,
    }
    gate_eval = gate_decision(gate_candidate, gate_snapshot)
    entry["gating"] = gate_eval
    if not bool(gate_eval.get("hard_pass")):
        hard_reason = (
            (gate_eval.get("hard_reasons") or [None])[0]
            or "HARD_GATE_FAILED"
        )
        entry_block_reason = entry_block_reason or hard_reason
        entry.setdefault("execution_allowed", False)
        entry["entry_status"] = entry_status or hard_reason
        entry_status = str(entry.get("entry_status") or "")

    threshold_execution = _safe_float(entry.get("threshold_execution"))
    if threshold_execution is None:
        threshold_execution = float(resolve_confidence_thresholds(mode_for_entry)["execution"])
    final_conf_threshold = float(
        getattr(cfg, "GATING_FINAL_CONFIDENCE_MIN", threshold_execution)
    )
    entry["confidence_raw_gate_threshold"] = _safe_float(entry.get("confidence_raw_gate_threshold"))
    entry["confidence_final_gate_threshold"] = final_conf_threshold
    gate_final_conf = _safe_float(gate_eval.get("final_confidence"))
    if gate_final_conf is not None:
        entry["gating_final_confidence"] = gate_final_conf
    soft_conf_reject = bool(
        bool(gate_eval.get("hard_pass"))
        and permission == "EXECUTE"
        and entry_block_reason is None
        and gate_final_conf is not None
        and gate_final_conf < final_conf_threshold
    )
    if soft_conf_reject:
        entry.setdefault("execution_allowed", False)
    if bool(entry.get("unresolved_contract")):
        entry = _apply_unresolved_contract_state(entry)
    else:
        entry = _apply_manual_approval_state(entry, now_epoch=time.time())
    entry = _refresh_lifecycle_blockers(
        entry,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
        current_ltp=_safe_float(entry.get("current_ltp")),
        validation_reference_price=_safe_float(entry.get("validation_reference_price")),
    )
    entry = _apply_issue_classification(
        entry,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
    )
    entry = _apply_confidence_threshold_fields(
        entry,
        confidence_value=(
            _safe_float(entry.get("gating_final_confidence"))
            if _safe_float(entry.get("gating_final_confidence")) is not None
            else _safe_float(entry.get("confidence_final"))
        ),
        execution_mode=mode_for_entry,
        hard_blockers=list(entry.get("hard_blockers") or []),
        entry_block_reason=entry_block_reason,
    )
    entry = _apply_canonical_quote_age(entry)
    entry = finalize_trade_decision(
        entry,
        gate_decision_payload=gate_eval,
        permission_payload=perm,
        entry_block_reason=entry_block_reason,
        decision_seed=decision_seed,
    )
    entry = _capture_queue_only_final_promotion_block(entry)
    entry = _last_chance_execution_entry_recovery(entry)
    entry = _enforce_executable_entry_invariant(entry)
    entry = _refresh_opportunity_survival_state(entry)
    entry = _synchronize_final_confidence(entry)
    entry = _maybe_promote_execute_candidate(entry)
    entry = _apply_expectancy_gate_if_present(entry)
    entry = _apply_sizing_telemetry(entry)
    if (
        str(entry.get("final_action") or "").strip().upper() == "BLOCK"
        or str(entry.get("permission") or "").strip().upper() == "BLOCK"
        or str(entry.get("execution_status") or "").strip().lower() == "blocked"
    ):
        entry = _preserve_blocked_candidate_metadata(entry)
    entry = _classify_candidate_status(entry)
    entry["confidence_final_gate_threshold"] = final_conf_threshold
    entry["confidence_rejection_stage"] = _derive_confidence_rejection_stage(entry)
    global_conf = _safe_float(entry.get("confidence_final"))
    permission = str(entry.get("permission") or permission or "ADVISORY_ONLY").upper()
    permission_reason = str(entry.get("permission_reason") or permission_reason or "")
    entry["status_raw"] = str(entry.get("status_raw") or entry.get("status") or "PLANNING").strip().upper() or "PLANNING"
    entry["status"] = _derive_review_status(entry, fallback_status=entry["status_raw"])
    high_execute_threshold = float(
        getattr(
            cfg,
            "HIGH_EXECUTE_MIN_CONF",
            _safe_float(entry.get("threshold_execution")) or 0.30,
        )
    )
    high_execute_eligible = bool(
        permission == "EXECUTE"
        and entry_block_reason is None
        and global_conf is not None
        and global_conf >= high_execute_threshold
    )
    high_execute_blockers: list[str] = []
    if global_conf is None or global_conf < high_execute_threshold:
        high_execute_blockers.append("global_conf_below_high_execute")
    if permission != "EXECUTE":
        high_execute_blockers.append(f"permission_{permission}")
    if entry_block_reason:
        high_execute_blockers.append(f"entry_{entry_block_reason}")
    if soft_conf_reject:
        high_execute_blockers.append("soft_confidence_below_threshold")
    decision_trace = {
        "candidate_status": entry.get("candidate_status"),
        "signal_score": _safe_float(perm.get("signal_score") if isinstance(perm, dict) else entry.get("raw_signal_confidence")),
        "regime_conf": _safe_float(entry.get("regime_confidence")),
        "orb_bias": (perm.get("orb_bias") if isinstance(perm, dict) else None) or entry.get("orb_bias"),
        "orb_factor": _safe_float(perm.get("orb_factor") if isinstance(perm, dict) else None),
        "reg_penalty": _safe_float(perm.get("regime_penalty") if isinstance(perm, dict) else None),
        "global_conf": global_conf,
        "permission": permission,
        "permission_reason": permission_reason,
        "permission_base": entry.get("permission_base"),
        "permission_reason_base": entry.get("permission_reason_base"),
        "permission_downgraded_from": entry.get("permission_downgraded_from"),
        "permission_downgrade_reason": entry.get("permission_downgrade_reason"),
        "entry_status": entry_status or None,
        "entry_block_reason": entry_block_reason,
        "hard_pass": bool(gate_eval.get("hard_pass")),
        "strict_hard_pass": bool(gate_eval.get("strict_hard_pass", gate_eval.get("hard_pass"))),
        "hard_gate_reasons": list(gate_eval.get("hard_reasons") or []),
        "strict_hard_gate_reasons": list(gate_eval.get("strict_hard_reasons") or []),
        "soft_gate_reasons": list(gate_eval.get("soft_reasons") or []),
        "relaxed_gate_context": bool(gate_eval.get("relaxed_context")),
        "relaxed_hard_reasons": list(gate_eval.get("relaxed_hard_reasons") or []),
        "relaxed_gate_soft_reasons": list(gate_eval.get("relaxed_soft_reasons") or []),
        "relaxed_gate_warning_reasons": list(gate_eval.get("relaxed_warning_reasons") or []),
        "relaxed_gate_soft_penalty_total": _safe_float(gate_eval.get("relaxed_soft_penalty_total")),
        "soft_score_adjustment": _safe_float(gate_eval.get("soft_score_adjustment")),
        "final_confidence_after_soft_gates": gate_final_conf,
        "final_confidence_min_threshold": final_conf_threshold,
        "threshold_display": _safe_float(entry.get("threshold_display")),
        "threshold_advisory": _safe_float(entry.get("threshold_advisory")),
        "threshold_execution": _safe_float(entry.get("threshold_execution")),
        "confidence_model_raw": _safe_float(entry.get("confidence_model_raw")),
        "confidence_model_component": _safe_float(entry.get("confidence_model_component")),
        "confidence_micro_component": _safe_float(entry.get("confidence_micro_component")),
        "confidence_micro_blend_method": entry.get("confidence_micro_blend_method"),
        "confidence_after_micro": _safe_float(entry.get("confidence_after_micro")),
        "confidence_after_alpha": _safe_float(entry.get("confidence_after_alpha")),
        "confidence_after_latency": _safe_float(entry.get("confidence_after_latency")),
        "confidence_before_soft_veto": _safe_float(entry.get("confidence_before_soft_veto")),
        "confidence_after_soft_veto": _safe_float(entry.get("confidence_after_soft_veto")),
        "confidence_penalty_soft_veto_total": _safe_float(entry.get("confidence_penalty_soft_veto_total")),
        "confidence_penalty_soft_veto_reasons": list(entry.get("confidence_penalty_soft_veto_reasons") or []),
        "confidence_gate_threshold": _safe_float(entry.get("confidence_gate_threshold")),
        "confidence_raw_gate_threshold": _safe_float(entry.get("confidence_raw_gate_threshold")),
        "confidence_final_gate_threshold": _safe_float(entry.get("confidence_final_gate_threshold")),
        "confidence_rejection_stage": entry.get("confidence_rejection_stage"),
        "confidence_vs_threshold_reason": entry.get("confidence_vs_threshold_reason"),
        "builder_confidence": _safe_float(entry.get("builder_confidence")),
        "permission_confidence": _safe_float(entry.get("permission_confidence")),
        "gating_final_confidence": _safe_float(entry.get("gating_final_confidence")),
        "sizing_reason": entry.get("sizing_reason"),
        "ml_proba_input": _safe_float(entry.get("ml_proba_input")),
        "confluence_input": _safe_float(entry.get("confluence_input")),
        "ml_proba_source": entry.get("ml_proba_source"),
        "confluence_source": entry.get("confluence_source"),
        "confidence_size_multiplier": _safe_float(entry.get("confidence_size_multiplier")),
        "final_qty": entry.get("final_qty"),
        "opportunity_score": _safe_float(entry.get("opportunity_score")),
        "opportunity_rank": entry.get("opportunity_rank"),
        "rank_global": entry.get("rank_global"),
        "rank_within_symbol": entry.get("rank_within_symbol"),
        "opportunity_bucket": entry.get("opportunity_bucket"),
        "selected_for_execution": bool(entry.get("selected_for_execution", False)),
        "selection_reason": entry.get("selection_reason"),
        "size_multiplier_reason": entry.get("size_multiplier_reason"),
        "spread_penalty": _safe_float(entry.get("spread_penalty")),
        "executable_price_estimate": _safe_float(entry.get("executable_price_estimate")),
        "execution_ok": entry.get("execution_ok"),
        "order_policy": entry.get("order_policy"),
        "order_policy_reason": entry.get("order_policy_reason"),
        "high_execute_threshold": high_execute_threshold,
        "high_execute_eligible": high_execute_eligible,
        "high_execute_blockers": high_execute_blockers,
        "strategy_qualified": bool(permission in {"EXECUTE", "QUEUE", "HIGH_EXECUTE"}),
        "gating_reason": entry_block_reason or permission_reason or None,
        "final_blocker": (
            entry.get("final_blocker")
            or entry_block_reason
            or permission_reason
            or None
        ),
        "feed_state": (
            entry.get("feed_state")
            or (entry.get("feed_health_snapshot") or {}).get("state")
            or None
        ),
        "quote_age_sec": _safe_float(entry.get("quote_age_sec")),
        "price_age_sec": _safe_float(entry.get("price_age_sec")),
        "option_age_sec": _safe_float(entry.get("option_age_sec")),
        "final_action": entry.get("final_action"),
    }
    entry["decision_trace"] = decision_trace
    _log_confidence_rejection(entry)
    entry = _repair_live_feed_failure_provenance(entry)
    entry, _ = _recover_missing_execution_entry(entry, _entry_lifecycle_from_entry(entry))
    if entry.get("entry_recovered"):
        print("RECOVERY_APPLIED:", entry.get("trade_id"))
    entry = enforce_entry_contract(entry, stage="review_queue.add_to_queue")
    entry = _enforce_executable_entry_integrity(entry)
    entry = _preserve_offhours_quote_validation_status(entry)
    entry = _finalize_suggested_entry(entry)
    entry = _apply_final_queue_only_entry_promotion_block(entry)
    entry = _lock_final_entry(entry)
    entry = _apply_fallback_execution_kill(entry)
    if entry.get("entry_recovered"):
        print("RECOVERY_PRESERVED:", entry.get("trade_id"))
    append_execution_entry_trace(
        module="core.review_queue",
        stage="finalize_review_queue_entry",
        row=entry,
        execution_entry_before=None,
        execution_entry_after=entry.get("execution_entry"),
        execution_entry_status_before=None,
        execution_entry_status_after=entry.get("execution_entry_status"),
        extra={
            "execution_entry_source": entry.get("execution_entry_source"),
            "display_entry": entry.get("display_entry"),
            "display_entry_status": entry.get("display_entry_status"),
            "derivation_reason": entry.get("_execution_entry_derivation_reason"),
            "derivation_source_chain": entry.get("_execution_entry_derivation_source_chain"),
        },
    )
    _log_entry_lifecycle_resolution(entry)
    _emit_trade_lifecycle_event(
        entry,
        stage="readiness_gating",
        status=str(entry.get("readiness") or entry.get("permission") or "unknown"),
        reason=str(entry.get("final_blocker") or entry.get("permission_reason") or entry.get("entry_block_code") or ""),
        extra={
            "execution_status": entry.get("execution_status"),
            "final_action": entry.get("final_action"),
        },
    )
    _emit_trade_lifecycle_event(
        entry,
        stage="execution_feasibility",
        status=str(entry.get("execution_entry_status") or entry.get("execution_status") or "unknown"),
        reason=str(entry.get("entry_block_code") or entry.get("execution_status") or entry.get("permission_reason") or ""),
        extra={
            "execution_entry": entry.get("execution_entry"),
            "execution_entry_source": entry.get("execution_entry_source"),
            "display_entry": entry.get("display_entry"),
        },
    )
    source_flags = entry.get("source_flags")
    if isinstance(source_flags, dict):
        merged_flags = dict(source_flags)
        merged_flags["decision_trace"] = decision_trace
        entry["source_flags"] = merged_flags
    entry = _enforce_final_execution_state_consistency(entry)
    return _classify_candidate_status(entry)


def _build_canonical_advisory_entry(
    entry: dict,
    *,
    mode_for_entry: str,
    allow_stale_quotes_for_entry: bool,
    market_open_for_entry: bool,
)-> dict:
    advisory_payload = _canonicalize_entry_lifecycle(
        entry,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
        market_open_for_entry=market_open_for_entry,
        align_for_schema=True,
    )
    advisory_payload = finalize_entry_lifecycle(advisory_payload)
    advisory_payload = _normalize_canonical_quote_source(advisory_payload)
    _log_entry_lifecycle_resolution(advisory_payload, stage="validate_finalize")
    advisory_payload = _finalize_advisory_schema_decision(advisory_payload)
    if advisory_payload.get("entry_recovered"):
        advisory_payload.pop(_LIFECYCLE_SNAPSHOT_KEY, None)
    advisory_payload = _enforce_finalized_entry_lifecycle(
        advisory_payload,
        stage="validate",
        drop_snapshot=True,
    )
    advisory_payload = _refresh_opportunity_survival_state(advisory_payload)
    advisory_payload = _finalize_advisory_schema_decision(advisory_payload)
    advisory_payload = _enforce_finalized_entry_lifecycle(
        advisory_payload,
        stage="validate_after_survival",
        drop_snapshot=True,
    )
    advisory_payload = _repair_live_feed_failure_provenance(advisory_payload)
    advisory_payload = _preserve_offhours_quote_validation_status(advisory_payload)
    advisory_payload = _apply_synthetic_offhours_advisory_lifecycle(advisory_payload)
    advisory_payload = _apply_candidate_identity(advisory_payload)
    advisory_payload = _apply_terminal_candidate_scoring(
        advisory_payload,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
        market_open_for_entry=market_open_for_entry,
    )
    advisory_payload = _reconcile_locked_final_entry(advisory_payload)
    advisory_payload = _ensure_blocked_advisory_hard_blockers(advisory_payload)
    if str(advisory_payload.get("final_action") or "").strip().upper() == "BLOCK":
        advisory_payload = _preserve_blocked_candidate_metadata(advisory_payload, terminal=False)
    advisory_payload = _classify_candidate_status(advisory_payload)
    advisory_payload = _apply_level_normalization_and_promotion(advisory_payload)
    advisory_payload = _classify_candidate_status(advisory_payload)
    advisory_payload["row_kind"] = _derive_review_queue_row_kind(advisory_payload)
    advisory_payload["non_canonical_levels"] = bool(advisory_payload.get("non_canonical_levels")) or advisory_payload["row_kind"] != CANONICAL_ROW_KIND
    advisory_payload = _ensure_blocked_advisory_hard_blockers(advisory_payload)
    advisory_payload = _normalize_advisory_entry_sources_for_schema(advisory_payload)
    advisory_entry = serialize_advisory_row(advisory_payload, allow_legacy=True)
    return _repair_live_feed_failure_provenance(advisory_entry)


def _record_advisory_validation_failure(
    entry: dict,
    *,
    mode_for_entry: str,
    allow_stale_quotes_for_entry: bool,
    market_open_for_entry: bool,
    exc: Exception,
) -> dict:
    advisory_payload = _canonicalize_entry_lifecycle(
        entry,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
        market_open_for_entry=market_open_for_entry,
        align_for_schema=True,
    )
    advisory_payload = finalize_entry_lifecycle(advisory_payload)
    advisory_payload = _normalize_canonical_quote_source(advisory_payload)
    advisory_payload = _finalize_advisory_schema_decision(advisory_payload)
    if advisory_payload.get("entry_recovered"):
        advisory_payload.pop(_LIFECYCLE_SNAPSHOT_KEY, None)
    advisory_payload = _enforce_finalized_entry_lifecycle(
        advisory_payload,
        stage="validate_failed",
        drop_snapshot=True,
    )
    advisory_payload = _preserve_offhours_quote_validation_status(advisory_payload)
    advisory_payload = _apply_candidate_identity(advisory_payload)
    advisory_payload = _apply_terminal_candidate_scoring(
        advisory_payload,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
        market_open_for_entry=market_open_for_entry,
    )
    advisory_payload = _reconcile_locked_final_entry(advisory_payload)
    advisory_payload = _ensure_blocked_advisory_hard_blockers(advisory_payload)
    advisory_payload = _apply_fallback_execution_kill(advisory_payload)
    print(
        "REVIEW_QUEUE_SCORING",
        {
            "trade_id": advisory_payload.get("trade_id"),
            "rank_score": advisory_payload.get("rank_score"),
            "confidence": advisory_payload.get("confidence_final"),
        },
    )
    if str(advisory_payload.get("final_action") or "").strip().upper() == "BLOCK":
        advisory_payload = _preserve_blocked_candidate_metadata(advisory_payload, terminal=False)
    advisory_payload = _classify_candidate_status(advisory_payload)
    advisory_payload["row_kind"] = _derive_review_queue_row_kind(advisory_payload)
    advisory_payload["non_canonical_levels"] = bool(advisory_payload.get("non_canonical_levels")) or advisory_payload["row_kind"] != CANONICAL_ROW_KIND
    advisory_payload = _normalize_advisory_entry_sources_for_schema(advisory_payload)
    emission_target = "rejected_candidates" if _is_blocked_contract_row(entry) else "suggestions"
    diagnostic = _build_advisory_emit_failure_payload(
        entry,
        advisory_payload,
        exc,
        emission_target=emission_target,
    )
    diagnostic.setdefault("reject_reason", "advisory_schema_error")
    diagnostic.setdefault("reason_code", "advisory_schema_error")
    log_advisory_schema_error("review_queue.add_to_queue", advisory_payload, exc)
    logger.warning("advisory_queue_schema_error trade_id=%s error=%s", entry.get("trade_id"), exc)
    logger.error("advisory_queue_schema_error payload=%s", json.dumps(diagnostic, sort_keys=True))
    diagnostic = _finalize_append_payload_for_runtime_write(
        diagnostic,
        require_terminal_scoring=False,
        require_ranked_candidate_ready=False,
    )
    _append_jsonl([logs_dir() / "advisory_emit_failures.jsonl"], diagnostic)
    _append_jsonl(rejected_candidates_paths(), diagnostic)
    return {
        "ok": False,
        "target": emission_target,
        "diagnostic": diagnostic,
    }


def _validate_review_queue_advisory_row(
    entry: dict,
    *,
    mode_for_entry: str,
    allow_stale_quotes_for_entry: bool,
    market_open_for_entry: bool,
) -> dict | None:
    try:
        return _build_canonical_advisory_entry(
            entry,
            mode_for_entry=mode_for_entry,
            allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
            market_open_for_entry=market_open_for_entry,
        )
    except AdvisorySchemaError as exc:
        _record_advisory_validation_failure(
            entry,
            mode_for_entry=mode_for_entry,
            allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
            market_open_for_entry=market_open_for_entry,
            exc=exc,
        )
        return None


def _write_review_queue_artifacts(path: Path, data: list[dict], entry: dict) -> dict:
    entry["trade_key"] = compute_trade_key(
        entry.get("symbol"),
        entry.get("expiry_date") or entry.get("expiry"),
        entry.get("strike"),
        entry.get("option_type") or entry.get("type"),
        entry.get("side"),
        entry.get("strategy_id") or entry.get("strategy"),
    )
    data = _merge_trade_entry(data, entry)
    ranked_rows = _rank_review_queue_rows(data, path=path)
    ranked_entry = _find_ranked_queue_entry(ranked_rows, entry)
    write_queue_rows(path, ranked_rows)
    try:
        write_candidate_journal_row(
            ranked_entry,
            journal_event=str(ranked_entry.get("journal_event") or "candidate_reported"),
        )
    except Exception:
        logger.warning("candidate_journal_emit_failed trade_id=%s", ranked_entry.get("trade_id"))
    emission_result = _emit_review_queue_logs(ranked_entry)
    _update_suggestions_status_latest(
        ranked_entry,
        emission_result=emission_result,
        queue_rows=ranked_rows,
    )
    return ranked_entry


def project_advisory_row(trade, extra=None):
    entry, mode_for_entry, allow_stale_quotes_for_entry, market_open_for_entry = _build_review_queue_entry(
        trade,
        extra=extra,
        default_mode="ADVISORY",
    )
    entry = _apply_quote_and_entry_logic(
        entry,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
        market_open_for_entry=market_open_for_entry,
    )
    entry = _finalize_review_queue_entry(
        entry,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
        market_open_for_entry=market_open_for_entry,
    )
    return _validate_review_queue_advisory_row(
        entry,
        mode_for_entry=mode_for_entry,
        allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
        market_open_for_entry=market_open_for_entry,
    )


def add_to_queue(trade, queue_path=None, extra=None):
    try:
        from config import config as cfg
        instr = getattr(trade, "instrument", None)
        if instr is None and isinstance(trade, dict):
            instr = trade.get("instrument")
        if instr == "EQ" and not getattr(cfg, "ENABLE_EQUITIES", True):
            return None
    except Exception:
        pass
    path = queue_path or QUEUE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_queue_rows(path)
    advisory_entry = project_advisory_row(trade, extra=extra)
    if advisory_entry is None:
        entry, mode_for_entry, allow_stale_quotes_for_entry, market_open_for_entry = _build_review_queue_entry(
            trade,
            extra=extra,
            default_mode="ADVISORY",
        )
        entry = _apply_quote_and_entry_logic(
            entry,
            mode_for_entry=mode_for_entry,
            allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
            market_open_for_entry=market_open_for_entry,
        )
        entry = _finalize_review_queue_entry(
            entry,
            mode_for_entry=mode_for_entry,
            allow_stale_quotes_for_entry=allow_stale_quotes_for_entry,
            market_open_for_entry=market_open_for_entry,
        )
        emission_target = "rejected_candidates" if _is_blocked_contract_row(entry) else "suggestions"
        _update_suggestions_status_latest(
            entry,
            emission_result={
                "ok": False,
                "target": emission_target,
                "diagnostic": {
                    "failure_reason": "advisory_schema_error",
                    "emission_target": emission_target,
                },
            },
        )
        return None
    return _write_review_queue_artifacts(path, data, advisory_entry)

def is_approved(trade_id, payload_hash=None):
    ok, _reason = approval_status(trade_id, payload_hash=payload_hash)
    return ok


def approve(trade_id, payload_hash=None, ttl_sec=None, approver=None):
    trade_id = str(trade_id)
    store = _load_approvals()
    approvals = store.setdefault("approvals", {})
    now_epoch = time.time()
    if ttl_sec is None:
        ttl_sec = _cfg_int("APPROVAL_TTL_SEC", 600)
    expires_epoch = now_epoch + max(int(ttl_sec), 0)
    approvals[trade_id] = {
        "status": "APPROVED",
        "payload_hash": payload_hash,
        "approved_epoch": now_epoch,
        "expires_epoch": expires_epoch,
        "approved_by": approver,
    }
    _write_json(APPROVED_PATH, store)


def get_queue_entry(trade_id, queue_paths=None):
    queue_paths = queue_paths or [QUEUE_PATH, QUICK_QUEUE_PATH, ZERO_HERO_QUEUE_PATH, SCALP_QUEUE_PATH, TARGET_POINTS_QUEUE_PATH]
    for path in queue_paths:
        rows = load_queue_rows(path)
        for row in rows:
            if isinstance(row, dict) and str(row.get("trade_id")) == str(trade_id):
                return row
    return None

def remove_from_queue(trade_id):
    if not QUEUE_PATH.exists():
        return
    data = load_queue_rows(QUEUE_PATH)
    data = [d for d in data if d.get("trade_id") != trade_id]
    write_queue_rows(QUEUE_PATH, data)
