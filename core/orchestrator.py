
def _pace_loop(poll_interval: float, loop_start_time: float) -> None:
    import time
    elapsed = time.perf_counter() - loop_start_time
    print('elapsed =', elapsed)
    print('poll_interval =', poll_interval)
    sleep_time = max(0.0, poll_interval - elapsed)
    if sleep_time > 0:
        time.sleep(sleep_time)

import time
import json
import argparse
import copy
import logging
import multiprocessing
import os
from collections import Counter
from collections.abc import Mapping
from typing import Any
from types import MappingProxyType
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta, timezone
from dataclasses import fields, replace
from strategies.trade_builder import TradeBuilder
from core.market_data import fetch_live_market_data, ensure_startup_warmup_bootstrap, refresh_index_quote_from_rest
from core.risk_engine import RiskEngine
from core.execution_guard import ExecutionGuard
from core.trade_logger import log_trade, update_trade_outcome, update_trade_fill
from core.telegram_alerts import send_telegram_message, send_trade_ticket
from core.trade_ticket import TradeTicket
from core.trade_schema import Trade, build_instrument_id, validate_trade_identity
from core.auto_retrain import AutoRetrain
from ml.trade_predictor import TradePredictor
from core.execution_engine import ExecutionEngine, evaluate as evaluate_execution_decision
from core.execution_router import ExecutionRouter
from core.fill_quality import log_fill_quality
from core.risk_state import RiskState
from core.strategy_gatekeeper import StrategyGatekeeper, GateResult
from core.portfolio_risk_allocator import PortfolioRiskAllocator
from core.exposure_ledger import ExposureLedger
from core.circuit_breaker import CircuitBreaker
from core.run_lock import RunLock
from core.governance import record_governance
from core.audit_log import append_event as audit_append, verify_chain as verify_audit_chain
from core.incidents import create_incident, trigger_audit_chain_fail
from core.events import append_event as append_runtime_event, write_json_atomic
from core.heartbeat_status import derive_cycle_semantics
from core.ml_governance import log_ab_trial
from rl.size_agent import SizeRLAgent, build_features
from core.runtime_boot_identity import stamp_runtime_payload
from core.orchestrator_helpers import (
    _perf_ms as _orchestrator_perf_ms,
    freeze_cycle_feed_truth_payload as _freeze_cycle_feed_truth_payload,
)


from config import config as cfg
from core.strategy_tracker import StrategyTracker
from ml.strategy_decay_predictor import generate_decay_report, telegram_summary
from core.kite_client import kite_client
from core import model_registry
from core.strategy_allocator import StrategyAllocator
from core.review_queue import (
    QUICK_QUEUE_PATH,
    SCALP_QUEUE_PATH,
    TARGET_POINTS_QUEUE_PATH,
    ZERO_HERO_QUEUE_PATH,
    _enrich_contract_identity,
    _has_valid_broker_contract,
    _missing_broker_contract_fields,
    _append_jsonl as _append_review_jsonl,
    add_to_queue,
    approval_status,
    order_payload_hash,
    project_advisory_row,
)
from core.learning_paths import rejected_candidates_paths
from core.candidate_soft_reject import (
    apply_latency_penalty,
    build_min_breadth_candidates,
    build_soft_reject_candidate,
    critical_reject_reasons,
    is_critical_reject_reason,
    soft_reject_enabled,
    soft_reject_max_per_symbol,
)
from core.v2_pipeline import run_v2_pipeline
from core.pro_strategy_pipeline import run_pro_strategy_pipeline
from core.blocked_tracker import BlockedTradeTracker
from core.trade_store import (
    fetch_open_positions_dict,
    insert_execution_stat,
    update_trailing_state,
    insert_trail_event,
    insert_trade_leg,
    update_trade_close,
)
from core.depth_store import depth_store
from core.kite_depth_ws import start_depth_ws, restart_depth_ws
from core.kite_ws_subprocess import start_depth_ws_subprocess, monitor_depth_ws_subprocess, stop_depth_ws_subprocess
from core.auto_tune import maybe_auto_tune
from core import risk_halt
from core.decision_logger import log_decision, update_execution, update_outcome
from core.risk_utils import to_pct
from core.feed_runtime import build_canonical_feed_truth_state
from core.time_utils import now_ist, now_utc_epoch, is_market_open_ist
from core.meta_model import MetaModel
from core.decision_trace import decision_config_snapshot
from core.reports.daily_audit import build_daily_audit, write_daily_audit_placeholder
from core.reports.execution_report import build_execution_report, write_execution_report_placeholder
from core.reject_logger import append_reject_reasons
from core.orchestrator_parts.cycle import run_live_monitoring
from core.orchestrator_parts import data as orchestrator_data
from core.orchestrator_parts import decisions as orchestrator_decisions
from core.orchestrator_parts import finalize as orchestrator_finalize
from core.session_guard import auto_clear_risk_halt_if_safe
from core.decision_store import DecisionStore
from core.decision_builder import build_decision
from core.decision_snapshot import DecisionSnapshot
from core.snapshot_builder import build_snapshot
from core.signal_engine import evaluate as evaluate_signal
from core.gates.quote_age_gate import validate_quote_age
from core.review_packet import build_review_packet, format_review_packet
from core.gate_status_log import append_gate_status, build_gate_status_record
from core.regime_session_context import resolve_canonical_session_context
from core.telemetry_streams import (
    append_candidate_stream_event,
    append_decision_stream_event,
    compute_candidate_id,
)
from core.trade_log_paths import ensure_trade_log_exists
from core.runtime_health import write_runtime_health_snapshot
from core.paths import logs_dir, repo_logs_dir, runtime_dir
from core.auth_manager import runtime_auth_snapshot
from core.observability.pipeline import write_pipeline_funnel
from core.outcome_labels import attach_candidate_outcome_labels
from core.engine_phase2_adapter import run_engine_phase2
from core.market_snapshot_builder import (
    build_market_snapshot as build_dashboard_market_snapshot,
    build_symbol_market_snapshot,
)
from core.market_snapshot_store import write_market_snapshot_atomic
from core.runtime_snapshot_producer import produce_and_store_runtime_snapshots
from core.runtime_snapshot_store import write_top_opportunities_snapshots
from core.ranked_pipeline_evidence import write_ranked_pipeline_evidence
from core.runtime_execution_truth import (
    build_execution_truth_context,
    normalize_candidate_execution_truth_payload,
)
from core.runtime_candidate_handoff import write_runtime_candidate_handoff_evidence
from core.candidate_lineage_ledger import write_candidate_lineage_ledger
from core.runtime_candidate_handoff_root_cause import (
    build_candidate_handoff_root_cause_payload,
    write_candidate_handoff_root_cause_latest,
)
from core.phase1_observability import build_phase1_observation, record_phase1_observation
from core.runtime_notrade_reason_truth import (
    build_notrade_reason_truth_payload,
    write_notrade_reason_truth_latest,
)
from core.candidate_row_classification import classify_candidate_row
from core.runtime_ranking_quality_evidence import (
    build_ranking_quality_evidence_payload,
    write_ranking_quality_latest,
)
from core.runtime_live_workload_evidence import (
    build_live_workload_payload,
    write_live_workload_latest,
)
from core.runtime_candidate_flow_trace import (
    build_candidate_flow_trace_payload,
    write_candidate_flow_trace_latest,
)
from core.runtime_candidate_starvation_trace import (
    build_candidate_starvation_trace_payload,
    write_candidate_starvation_trace_latest,
)
from core.runtime_strategy_no_qualified_reasons import (
    build_strategy_attempt_from_gate,
    build_strategy_attempt_from_trade_builder,
    build_strategy_no_qualified_reasons_payload,
    write_strategy_no_qualified_reasons_latest,
)
from core.live_indicator_readiness import (
    build_live_indicator_readiness_report,
    write_live_indicator_readiness_latest,
)
from core.event_log import validate_and_repair as validate_and_repair_event_log
from core.decision_dag import (
    NODE_N1_MARKET_OPEN,
    NODE_N2_FEED_FRESH,
    NODE_N3_WARMUP_DONE,
    NODE_N4_QUOTE_OK,
    NODE_N5_REGIME_OK,
    NODE_N6_RISK_OK,
    NODE_N7_GOVERNANCE_LOCKS_OK,
    build_market_snapshot,
    evaluate_decision,
)
from core.decision_telemetry_health import append_decision_write_error
from core.decision_side_effects import handle_post_decision_side_effects
from core.market_context import derive_market_context
from core.slo_guard import evaluate_slo_status
from core.slippage_guard import evaluate_slippage_budget
from core.execution_optimizer import build_execution_plan
from core.exit_intelligence import ExitAction, evaluate_exit
from core.exit_manager import evaluate_exit_action
from core.position_state_engine import (
    PositionState,
    apply_exit_action as apply_position_exit_action,
    initialize_position_state,
    position_state_to_dict,
    update_position_state,
)
from core.position_state_store import load_position_state, save_position_state
from core.suggestion_reliability import (
    evaluate_suggestion_reliability,
    persist_suggestion_reliability,
)
from core.latency_monitor import LatencyMonitor
from core.latency_guard import (
    ACTION_COOLDOWN,
    ACTION_DEGRADE_EXIT_ONLY,
    ACTION_HALT_ALL,
    ACTION_OK,
    LatencyGuard,
)
from core.decision_breakers import DecisionCircuitBreakers
from core.auth_manager import is_auth_error
from core.regime_monitor import get_regime_monitor
from core.learning_paths import (
    canonical_suggestions_log_path,
    canonical_suggestion_eval_log_path,
    suggestion_eval_log_paths,
    suggestion_log_paths,
)
from core.orchestrator_helpers import _perf_ms as _orchestrator_perf_ms
from core.orchestrator_pro_shadow import (
    build_pro_shadow_report as _build_pro_shadow_report,
    create_pro_shadow_process as _create_pro_shadow_process,
    pro_shadow_report_path as _pro_shadow_report_path,
    run_pro_shadow_pipeline_worker_entry as _run_pro_shadow_pipeline_worker_entry,
    sanitize_pro_shadow_rows as _sanitize_pro_shadow_rows,
)
from core.orchestrator_truth import (
    build_snapshot_numbers as _build_snapshot_numbers,
    canonical_feed_truth_state_payload as _canonical_feed_truth_state_payload,
    candidate_origin as _candidate_origin,
    candidate_runtime_truth_summary as _candidate_runtime_truth_summary,
    candidate_trace_payload as _candidate_trace_payload,
    candidate_visibility_bucket as _candidate_visibility_bucket,
    coerce_trade_dict_to_schema as _coerce_trade_dict_to_schema,
    feed_truth_cycle_gate as _feed_truth_cycle_gate,
    filter_invalid_cycle_candidates as _filter_invalid_cycle_candidates,
    is_reportable_executable_candidate as _is_reportable_executable_candidate,
    is_synthetic_candidate as _is_synthetic_candidate,
    normalize_feed_runtime_payload as _normalize_feed_runtime_payload,
    read_json_dict as _read_json_dict,
    read_latest_feed_runtime_payload as _read_latest_feed_runtime_payload,
    regime_unstable_diagnostic_payload as _regime_unstable_diagnostic_payload,
    replace_trade_fields as _replace_trade_fields,
    safe_float as _safe_float,
    snapshot_atm_strike as _snapshot_atm_strike,
    structurally_valid_cycle_candidate as _is_structurally_valid_cycle_candidate,
    trade_attr as _trade_attr,
)
from core.feed.artifact_loader import load_current_feed_runtime

_perf_ms = _orchestrator_perf_ms
from core.orchestrator_latency import (
    build_cycle_latency_snapshot as _build_cycle_latency_snapshot,
    build_min_breadth_backfill as _build_min_breadth_backfill,
    count_jsonl_rows as _count_jsonl_rows,
    is_recoverable_depth_ws_startup_error as _is_recoverable_depth_ws_startup_error,
    latency_budget_config as _latency_budget_config,
    latency_guard_metric_context as _latency_guard_metric_context,
    min_breadth_target as _min_breadth_target,
    should_skip_background_maintenance_for_latency_guard as _should_skip_background_maintenance_for_latency_guard,
    should_skip_trade_builder_for_latency_guard as _should_skip_trade_builder_for_latency_guard,
    top_blockers_payload as _top_blockers_payload,
)
from core.orchestrator_reports import (
    build_pipeline_funnel_payload as _build_pipeline_funnel_payload,
    build_ranked_pipeline_runtime_report as _build_ranked_pipeline_runtime_report,
    build_top_opportunities_payload as _build_top_opportunities_payload,
    load_truth_dataset_for_reports,
    scan_visible_suggestions as _scan_visible_suggestions,
    snapshot_symbol_payload as _snapshot_symbol_payload,
    write_cycle_reports,
    write_ranked_pipeline_runtime_evidence as _write_ranked_pipeline_runtime_evidence,
    zero_visible_counts as _zero_visible_counts,
)


logger = logging.getLogger(__name__)


def _env_debug_enabled(name: str) -> bool:
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


def resolve_global_halt_reason(circuit_breaker) -> str | None:
    """
    Authoritative runtime halt resolution.
    Priority: manual kill switch -> persisted risk halt -> circuit breaker.
    """
    if bool(getattr(cfg, "KILL_SWITCH", False)):
        return "KILL_SWITCH"
    try:
        if risk_halt.is_halted():
            return "RISK_HALT"
    except Exception:
        return "RISK_HALT_STATE_ERROR"
    try:
        if circuit_breaker and circuit_breaker.is_halted():
            return str(circuit_breaker.halt_reason or "CB_ACTIVE")
    except Exception:
        return "CB_STATE_ERROR"
    return None


def _trade_attr(trade, name: str, default=None):
    if isinstance(trade, dict):
        return trade.get(name, default)
    return getattr(trade, name, default)


def _candidate_origin(candidate) -> str:
    origin_value = _trade_attr(candidate, "candidate_origin", None)
    if isinstance(origin_value, dict):
        return str(
            origin_value.get("candidate_origin")
            or origin_value.get("origin")
            or origin_value.get("source")
            or ""
        ).strip().lower()
    return str(origin_value or "").strip().lower()


def _is_synthetic_candidate(candidate) -> bool:
    if candidate is None:
        return False
    origin = _candidate_origin(candidate)
    source_flags = _trade_attr(candidate, "source_flags", None)
    if not isinstance(source_flags, dict):
        source_flags = {}
    source_origin = str(
        source_flags.get("candidate_origin")
        or source_flags.get("origin")
        or source_flags.get("source")
        or ""
    ).strip().lower()
    soft_reason = str(source_flags.get("soft_reject_reason") or "").strip().lower()
    candidate_type = str(_trade_attr(candidate, "candidate_type", "") or "").strip().lower()
    strategy_family = str(_trade_attr(candidate, "strategy_family", "") or "").strip().lower()
    score_origin = str(_trade_attr(candidate, "score_origin", "") or "").strip().lower()
    trade_id = str(_trade_attr(candidate, "trade_id", "") or "").strip()
    permission = str(_trade_attr(candidate, "permission", "") or "").strip().upper()
    final_action = str(_trade_attr(candidate, "final_action", "") or "").strip().upper()
    execution_status = str(_trade_attr(candidate, "execution_status", "") or "").strip().lower()
    advisory_lifecycle = (
        permission == "ADVISORY_ONLY"
        or final_action == "ADVISORY_ONLY"
        or execution_status == "advisory_only"
    )
    if candidate_type == "fallback_market_candidate":
        return True
    if trade_id.startswith(("softrej_", "tbsoft_")):
        return True
    if strategy_family == "synthetic_advisory":
        return True
    if score_origin == "soft_reject_seed":
        return True
    synthetic_origins = {
        "pre_builder_gate",
        "invalid_snapshot",
        "fallback",
        "fallback_min_breadth",
        "softened_builder_path",
        "softened",
        "planning_only",
    }
    if origin in synthetic_origins or source_origin in synthetic_origins:
        return True
    if bool(source_flags.get("recoverable_soft_reject")):
        return True
    if soft_reason:
        return True
    if advisory_lifecycle and (
        candidate_type.startswith("fallback")
        or origin in synthetic_origins
        or source_origin in synthetic_origins
        or trade_id.startswith(("softrej_", "tbsoft_"))
    ):
        return True
    return False


def _is_reportable_executable_candidate(candidate) -> bool:
    if candidate is None or _is_synthetic_candidate(candidate):
        return False
    allow_status_fallback = bool(
        getattr(cfg, "ORCHESTRATOR_EXECUTABLE_REPORT_ALLOW_STATUS_FALLBACK", True)
    )
    trade_id = str(_trade_attr(candidate, "trade_id", "") or "").strip().lower()
    if trade_id.startswith(("softrej_", "tbsoft_")):
        return False
    strategy_family = str(_trade_attr(candidate, "strategy_family", "") or "").strip().lower()
    if strategy_family == "synthetic_advisory":
        return False
    candidate_status = str(_trade_attr(candidate, "candidate_status", "") or "").strip().lower()
    execution_status = str(_trade_attr(candidate, "execution_status", "") or "").strip().lower()
    execution_entry_status = str(_trade_attr(candidate, "execution_entry_status", "") or "").strip().lower()
    permission = str(_trade_attr(candidate, "permission", "") or "").strip().upper()
    final_action = str(_trade_attr(candidate, "final_action", "") or "").strip().upper()
    readiness = str(_trade_attr(candidate, "readiness", "") or "").strip().upper()
    if bool(_trade_attr(candidate, "execution_truth_blocked", False)):
        return False
    if bool(_trade_attr(candidate, "execution_truth_blockers", None)):
        return False
    if candidate_status in {"advisory_only", "blocked", "blocked_contract"}:
        return False
    status_derived_executable = (
        allow_status_fallback
        and execution_status in {"", "none", "null"}
        and execution_entry_status == "executable"
        and bool(_trade_attr(candidate, "execution_allowed", False))
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
    if not bool(_trade_attr(candidate, "execution_allowed", False)):
        return False
    eligible_for_execution = _trade_attr(candidate, "eligible_for_execution", None)
    if eligible_for_execution is None:
        eligible_for_execution = _trade_attr(candidate, "execution_allowed", False)
    if not bool(eligible_for_execution):
        return False
    if bool(_trade_attr(candidate, "execution_blocked", False)):
        return False
    if bool(_trade_attr(candidate, "hard_blockers", None)) or bool(_trade_attr(candidate, "blockers", None)):
        return False
    if bool(_trade_attr(candidate, "unresolved_contract", False)):
        return False
    if _trade_attr(candidate, "execution_entry", None) in (None, "", "None"):
        return False
    return True


def _candidate_visibility_bucket(candidate) -> str:
    candidate_status = str(_trade_attr(candidate, "candidate_status", "") or "").strip().lower()
    execution_status = str(_trade_attr(candidate, "execution_status", "") or "").strip().lower()
    permission = str(_trade_attr(candidate, "permission", "") or "").strip().upper()
    final_action = str(_trade_attr(candidate, "final_action", "") or "").strip().upper()
    readiness = str(_trade_attr(candidate, "readiness", "") or "").strip().upper()
    hard_blocked = (
        candidate_status == "blocked"
        or execution_status == "blocked"
        or permission == "BLOCK"
        or final_action == "BLOCK"
        or readiness == "BLOCKED"
        or bool(_trade_attr(candidate, "execution_blocked", False))
        or bool(_trade_attr(candidate, "hard_blockers", None))
        or bool(_trade_attr(candidate, "blockers", None))
        or bool(_trade_attr(candidate, "unresolved_contract", False))
    )
    if _is_reportable_executable_candidate(candidate):
        return "executable"
    if hard_blocked:
        return "blocked"
    if (
        candidate_status in {"advisory_only", "ranked", "scored"}
        or execution_status in {"advisory_only", "queue_only"}
        or permission in {"ADVISORY_ONLY", "QUEUE_ONLY"}
        or final_action in {"ADVISORY_ONLY", "QUEUE_ONLY"}
        or readiness in {"ADVISORY_ONLY", "QUEUE_ONLY"}
        or bool(_trade_attr(candidate, "planning_only", False))
    ):
        return "advisory"
    return "blocked"



def _candidate_runtime_truth_summary(candidate) -> dict:
    """
    Runtime/UI truth guard.

    This does not decide trading eligibility. It explains whether an emitted trace
    is actually reportable as executable or only looks executable because one
    legacy field still says executable/READY/allowed.
    """
    reportable_executable = bool(_is_reportable_executable_candidate(candidate))
    visibility_bucket = _candidate_visibility_bucket(candidate)
    synthetic_candidate = bool(_is_synthetic_candidate(candidate))

    execution_status = str(_trade_attr(candidate, "execution_status", "") or "").strip().lower()
    execution_entry_status = str(_trade_attr(candidate, "execution_entry_status", "") or "").strip().lower()
    permission = str(_trade_attr(candidate, "permission", "") or "").strip().upper()
    final_action = str(_trade_attr(candidate, "final_action", "") or "").strip().upper()
    readiness = str(_trade_attr(candidate, "readiness", "") or "").strip().upper()
    candidate_status = str(_trade_attr(candidate, "candidate_status", "") or "").strip().lower()

    executable_signals = []
    if execution_status == "executable":
        executable_signals.append("execution_status")
    if execution_entry_status == "executable":
        executable_signals.append("execution_entry_status")
    if permission == "EXECUTE":
        executable_signals.append("permission")
    if final_action == "EXECUTE":
        executable_signals.append("final_action")
    if readiness == "READY":
        executable_signals.append("readiness")
    if bool(_trade_attr(candidate, "execution_allowed", False)):
        executable_signals.append("execution_allowed")
    if bool(_trade_attr(candidate, "eligible_for_execution", False)):
        executable_signals.append("eligible_for_execution")

    reasons: list[str] = []
    if executable_signals and not reportable_executable:
        reasons.append("executable_signals_not_reportable")
    if reportable_executable and visibility_bucket != "executable":
        reasons.append("reportable_executable_visibility_mismatch")
    if synthetic_candidate and reportable_executable:
        reasons.append("synthetic_candidate_marked_executable")
    if candidate_status in {"advisory_only", "blocked", "blocked_contract"} and executable_signals:
        reasons.append("blocked_or_advisory_candidate_has_executable_signals")

    return {
        "visibility_bucket": visibility_bucket,
        "reportable_executable": reportable_executable,
        "synthetic_candidate": synthetic_candidate,
        "runtime_truth_consistent": not bool(reasons),
        "runtime_truth_reasons": reasons,
        "executable_signals": executable_signals,
    }


def _candidate_trace_payload(candidate, *, execution_truth_context: dict | None = None) -> dict:
    runtime_truth = _candidate_runtime_truth_summary(candidate)
    payload = {
        "symbol": _trade_attr(candidate, "symbol"),
        "trade_id": _trade_attr(candidate, "trade_id"),
        "strategy_family": _trade_attr(candidate, "strategy_family"),
        "candidate_type": _trade_attr(candidate, "candidate_type"),
        "rank_score": _trade_attr(candidate, "rank_score"),
        "candidate_status": _trade_attr(candidate, "candidate_status"),
        "execution_status": _trade_attr(candidate, "execution_status"),
        "execution_entry_status": _trade_attr(candidate, "execution_entry_status"),
        "permission": _trade_attr(candidate, "permission"),
        "final_action": _trade_attr(candidate, "final_action"),
        "readiness": _trade_attr(candidate, "readiness"),
        "execution_allowed": _trade_attr(candidate, "execution_allowed"),
        "eligible_for_execution": _trade_attr(candidate, "eligible_for_execution"),
        "reason": _trade_attr(candidate, "reason"),
        "entry_price": _trade_attr(candidate, "entry_price"),
        "stop_loss": _trade_attr(candidate, "stop_loss"),
        "target_price": _trade_attr(candidate, "target_price"),
        "visibility_bucket": _trade_attr(candidate, "visibility_bucket"),
        "subscription_ok": _trade_attr(candidate, "subscription_ok"),
        "reportable_executable": _trade_attr(candidate, "reportable_executable"),
        "synthetic_candidate": _trade_attr(candidate, "synthetic_candidate"),
        **runtime_truth,
    }
    if execution_truth_context is not None:
        payload = normalize_candidate_execution_truth_payload(payload, execution_truth_context=execution_truth_context)
    return payload


def _regime_unstable_diagnostic_payload(market_data: dict, gate_reasons: list[str] | None = None) -> dict:
    reasons = [str(reason or "").strip().upper() for reason in list(gate_reasons or []) if str(reason or "").strip()]
    unstable_markers = {"REGIME_UNSTABLE", "PROB_TOO_LOW", "ENTROPY_TOO_HIGH"}
    if not any(reason in unstable_markers or reason.startswith("REGIME_") for reason in reasons):
        return {}

    row = dict(market_data or {})
    symbol = str(row.get("symbol") or "UNKNOWN").strip().upper() or "UNKNOWN"
    market_context = row.get("market_context") if isinstance(row.get("market_context"), dict) else {}
    execution_mode = str(
        market_context.get("mode")
        or market_context.get("execution_mode")
        or row.get("execution_mode")
        or getattr(cfg, "EXECUTION_MODE", "SIM")
    ).strip().upper() or "SIM"

    regime_probs = row.get("regime_probs") if isinstance(row.get("regime_probs"), dict) else {}
    regime_prob_max = _safe_float(row.get("regime_prob_max"))
    if regime_prob_max is None and regime_probs:
        numeric_probs = [_safe_float(value) for value in regime_probs.values()]
        numeric_probs = [value for value in numeric_probs if value is not None]
        regime_prob_max = max(numeric_probs) if numeric_probs else None

    regime_prob_min = float(getattr(cfg, "REGIME_PROB_MIN", 0.45))
    if execution_mode != "LIVE" and bool(getattr(cfg, "PAPER_RELAX_GATES", True)):
        regime_prob_min = float(getattr(cfg, "PAPER_REGIME_PROB_MIN", regime_prob_min))

    from core.regime_entropy_gate import evaluate_regime_entropy_gate
    session_bucket = str(row.get("session_bucket") or "").strip().upper()
    if not session_bucket:
        session_bucket = resolve_canonical_session_context(
            row.get("timestamp_ist")
            or row.get("timestamp")
            or row.get("quote_ts")
            or row.get("quote_ts_epoch")
            or row.get("ltp_ts_epoch")
            or row.get("candle_ts_epoch"),
            segment=str(row.get("segment") or "NSE_FNO"),
            is_expiry_day=bool(row.get("is_expiry_day")),
            is_event_mode=bool(row.get("is_event_mode")),
        ).canonical_session_bucket
    entropy_gate = evaluate_regime_entropy_gate(
        raw_entropy=_safe_float(row.get("regime_entropy")),
        probabilities=regime_probs,
        session_bucket=session_bucket,
        market_data=row,
        primary_regime=row.get("primary_regime") or row.get("regime") or "",
        regime_prob_max=row.get("regime_prob_max") or row.get("regime_probs_max"),
    )

    if entropy_gate.get("gate_passed") is False or entropy_gate.get("uncertain"):
        reasons.append("entropy_too_high")

    return {
        "symbol": symbol,
        "gate_reasons": reasons,
        "execution_mode": execution_mode,
        "primary_regime": row.get("primary_regime") or row.get("regime"),
        "regime_prob_max": regime_prob_max,
        "regime_entropy": entropy_gate["raw_entropy"],
        "regime_entropy_normalized": entropy_gate["normalized_entropy"],
        "regime_prob_min": regime_prob_min,
        "regime_entropy_max": entropy_gate["threshold"],
        "regime_entropy_max_source": entropy_gate["threshold_source"],
        "unstable_reasons": [str(x) for x in list(row.get("unstable_reasons") or []) if str(x).strip()],
        "regime_unstable_streak": int(row.get("regime_unstable_streak") or 0),
        "regime_unstable_block_after": int(row.get("regime_unstable_block_after") or 0),
        "regime_unstable_debounced": bool(row.get("regime_unstable_debounced", False)),
        "feed_health": row.get("feed_health") if isinstance(row.get("feed_health"), dict) else {},
        "quote_health": row.get("quote_health") if isinstance(row.get("quote_health"), dict) else {},
    }


def _is_structurally_valid_cycle_candidate(candidate) -> bool:
    if candidate is None:
        return False
    required_fields = (
        "trade_id",
        "symbol",
        "strategy_family",
        "candidate_status",
    )
    for field in required_fields:
        if _trade_attr(candidate, field) in (None, "", "None"):
            return False
            
    if _trade_attr(candidate, "candidate_status") != "advisory_only":
        trade_id = str(_trade_attr(candidate, "trade_id") or "")
        if not trade_id.startswith(("tbsoft_", "softrej_")):
            if _trade_attr(candidate, "rank_score") in (None, "", "None"):
                return False
            
    return True


def _filter_invalid_cycle_candidates(candidates, *, symbol: str | None = None) -> tuple[list, list[dict]]:
    valid: list = []
    invalid_samples: list[dict] = []
    sample_limit = max(
        0,
        int(getattr(cfg, "ORCHESTRATOR_INVALID_CYCLE_CANDIDATE_SAMPLE_LIMIT", 5) or 5),
    )
    for candidate in list(candidates or []):
        if _is_structurally_valid_cycle_candidate(candidate):
            valid.append(candidate)
            continue
        if len(invalid_samples) < sample_limit:
            invalid_samples.append(
                {
                    "type": type(candidate).__name__ if candidate is not None else "NoneType",
                    "symbol": _trade_attr(candidate, "symbol"),
                    "trade_id": _trade_attr(candidate, "trade_id"),
                    "candidate_status": _trade_attr(candidate, "candidate_status"),
                    "execution_status": _trade_attr(candidate, "execution_status"),
                }
            )
    if invalid_samples:
        logger.warning(
            "orchestrator_invalid_cycle_candidates symbol=%s count=%s sample=%s",
            str(symbol or "").strip().upper() or None,
            max(0, len(list(candidates or [])) - len(valid)),
            invalid_samples,
        )
    return valid, invalid_samples


def _replace_trade_fields(trade, updates: dict):
    if not updates:
        return trade
    safe_updates = {}
    if isinstance(trade, dict):
        out = dict(trade)
        out.update(updates)
        return out
    for key, value in dict(updates or {}).items():
        if hasattr(trade, key):
            safe_updates[key] = value
    if not safe_updates:
        return trade
    try:
        return replace(trade, **safe_updates)
    except Exception:
        for key, value in safe_updates.items():
            try:
                setattr(trade, key, value)
            except Exception:
                continue
        return trade


def _coerce_trade_dict_to_schema(trade, market_data: dict | None = None):
    if not isinstance(trade, dict):
        return trade
    payload = dict(trade or {})
    symbol = str(payload.get("symbol") or (market_data or {}).get("symbol") or "UNKNOWN").strip().upper() or "UNKNOWN"
    instrument = str(payload.get("instrument") or payload.get("instrument_type") or "OPT").strip().upper() or "OPT"
    direction = str(payload.get("direction") or "").strip().upper()
    side = str(payload.get("side") or "").strip().upper()
    if not side:
        side = "BUY" if direction in {"BUY_CALL", "BUY_PUT", "BUY"} else "SELL" if direction in {"SELL_CALL", "SELL_PUT", "SELL"} else "BUY"
    entry_price = float(
        payload.get("entry_price")
        or payload.get("execution_entry")
        or payload.get("display_entry")
        or payload.get("current_ltp")
        or (market_data or {}).get("ltp")
        or 0.0
    )
    if entry_price <= 0.0:
        entry_price = 1.0
    stop_loss = float(payload.get("stop_loss") or max(entry_price * 0.98, 0.5))
    target = float(payload.get("target") or max(entry_price * 1.02, entry_price + 0.5))
    qty = int(payload.get("qty") or 1)
    allowed_fields = {field.name for field in fields(Trade)}
    trade_payload = {
        "trade_id": str(payload.get("trade_id") or f"{symbol}-SOFT-{int(time.time() * 1000)}"),
        "timestamp": payload.get("timestamp") if isinstance(payload.get("timestamp"), datetime) else datetime.now(),
        "symbol": symbol,
        "instrument": instrument,
        "instrument_token": payload.get("instrument_token"),
        "strike": int(payload.get("strike") or 0),
        "expiry": str(payload.get("expiry") or ""),
        "side": side,
        "entry_price": float(entry_price),
        "stop_loss": float(stop_loss),
        "target": float(target),
        "qty": int(max(1, qty)),
        "capital_at_risk": float(payload.get("capital_at_risk") or abs(float(entry_price) - float(stop_loss))),
        "expected_slippage": float(payload.get("expected_slippage") or 0.0),
        "confidence": float(payload.get("confidence") or payload.get("rank_score") or 0.0),
        "strategy": str(payload.get("strategy") or payload.get("strategy_name") or payload.get("strategy_family") or "SOFT_REJECT"),
        "regime": str(payload.get("regime") or (market_data or {}).get("regime") or "NEUTRAL"),
    }
    for key, value in payload.items():
        if key in allowed_fields and key not in trade_payload:
            trade_payload[key] = value
    try:
        return Trade(**trade_payload)
    except Exception:
        return trade


_JSON_READ_CACHE = {}

def _read_json_dict(path: Path) -> dict:
    try:
        if not path.exists():
            return {}
        mtime = path.stat().st_mtime
        cache_key = str(path)
        cached = _JSON_READ_CACHE.get(cache_key)
        if cached and cached["mtime"] == mtime:
            return dict(cached["data"])  # Shallow copy to prevent mutation

        raw = json.loads(path.read_text(encoding="utf-8"))
        res = raw if isinstance(raw, dict) else {}
        _JSON_READ_CACHE[cache_key] = {"mtime": mtime, "data": res}
        return dict(res)
    except Exception:
        return {}


def _load_cycle_feed_truth_payload(path: Path | None = None) -> Mapping[str, Any]:
    target = path or (logs_dir() / "feed_truth_latest.json")
    return _freeze_cycle_feed_truth_payload(_read_json_dict(target))


def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _normalize_feed_runtime_payload(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return {}
    payload = raw.get("payload")
    if isinstance(payload, dict):
        return dict(payload)
    return dict(raw)


def _read_latest_feed_runtime_payload() -> tuple[dict, Path | None]:
    path = logs_dir() / "feed_runtime_latest.json"
    loaded = load_current_feed_runtime(path)
    payload = dict(loaded.get("payload") or {}) if loaded.get("valid") else {}
    payload["provenance"] = {"valid": bool(loaded.get("valid")), "reasons": list(loaded.get("reasons") or []), "reason_code": loaded.get("reason_code")}
    if not loaded.get("valid"):
        payload["feed_ok"] = False
        payload["execution_feed_ready"] = False
    return payload, path if path.exists() else None


def _canonical_feed_truth_state_payload(feed_runtime_payload: dict | None) -> dict:
    payload = dict(feed_runtime_payload or {})
    canonical_payload = payload.get("canonical_feed_truth") if isinstance(payload.get("canonical_feed_truth"), dict) else None
    if isinstance(canonical_payload, dict):
        return dict(canonical_payload)
    try:
        return build_canonical_feed_truth_state(payload).to_payload()
    except Exception:
        return {}


def _feed_truth_cycle_gate(feed_runtime_payload: dict | None) -> dict:
    canonical = _canonical_feed_truth_state_payload(feed_runtime_payload)
    state = str(canonical.get("state") or "").strip().upper()
    reason_code = str(canonical.get("reason_code") or "").strip().upper()
    if state in {"BOOTING", "CONNECTING", "SUBSCRIBED", "VERIFYING_OPTION_TICKS"}:
        return {"skip": True, "reason": "NO_TRADE_FEED_WARMUP", "state": state, "reason_code": reason_code}
    if state == "DEGRADED":
        return {"skip": True, "reason": "NO_TRADE_FEED_UNVERIFIED", "state": state, "reason_code": reason_code}
    return {"skip": False, "reason": "", "state": state, "reason_code": reason_code}


def _count_jsonl_rows(path: Path) -> int:
    try:
        if not path.exists():
            return 0
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for line in handle if str(line).strip())
    except Exception:
        return 0


def _build_cycle_latency_snapshot(
    *,
    latency_monitor: LatencyMonitor,
    cycle_perf_start: float,
    critical_path_end_perf: float | None,
    feature_build_ms: float,
    decision_build_ms: float,
    execution_route_ms: float,
    use_critical_path_only: bool | None = None,
) -> dict:
    cycle_end_perf = time.perf_counter()
    guard_uses_critical_path = bool(
        getattr(cfg, "LATENCY_GUARD_USE_CRITICAL_PATH_ONLY", True)
        if use_critical_path_only is None
        else use_critical_path_only
    )
    effective_critical_end = float(critical_path_end_perf or cycle_end_perf)
    critical_path_ms = max(0.0, (effective_critical_end - float(cycle_perf_start)) * 1000.0)
    full_cycle_ms = max(critical_path_ms, (cycle_end_perf - float(cycle_perf_start)) * 1000.0)
    background_overhead_ms = max(0.0, full_cycle_ms - critical_path_ms)
    guard_total_ms = critical_path_ms if guard_uses_critical_path else full_cycle_ms

    latency_monitor.record("feature_build", feature_build_ms)
    latency_monitor.record("decision_build", decision_build_ms)
    latency_monitor.record("execution_route", execution_route_ms)
    latency_stats = dict(latency_monitor.tick_end(guard_total_ms) or {})
    latency_stats["cycle"] = {
        "critical_path_ms": float(critical_path_ms),
        "full_cycle_ms": float(full_cycle_ms),
        "background_overhead_ms": float(background_overhead_ms),
        "guard_total_ms": float(guard_total_ms),
        "guard_uses_critical_path": bool(guard_uses_critical_path),
    }
    return latency_stats


def _latency_budget_config(*, execution_mode: str | None) -> dict[str, float | int | bool | str]:
    mode = str(execution_mode or "SIM").strip().upper()
    is_live = mode == "LIVE"
    if is_live:
        return {
            "scope": "live",
            "max_p95_total_ms": float(getattr(cfg, "LIVE_MAX_P95_TOTAL_MS", getattr(cfg, "MAX_P95_TOTAL_MS", 120.0))),
            "max_p95_decision_ms": float(
                getattr(cfg, "LIVE_MAX_P95_DECISION_MS", getattr(cfg, "MAX_P95_DECISION_MS", 80.0))
            ),
            "sustained_windows": int(getattr(cfg, "LIVE_SUSTAINED_WINDOWS", getattr(cfg, "SUSTAINED_WINDOWS", 3))),
            "cooldown_sec": float(
                getattr(cfg, "LIVE_EXIT_ONLY_COOLDOWN_S", getattr(cfg, "EXIT_ONLY_COOLDOWN_S", 30.0))
            ),
            "halt_on_breach": bool(getattr(cfg, "LIVE_HALT_ON_BREACH", getattr(cfg, "HALT_ON_BREACH", True))),
        }
    return {
        "scope": "default",
        "max_p95_total_ms": float(getattr(cfg, "MAX_P95_TOTAL_MS", 120.0)),
        "max_p95_decision_ms": float(getattr(cfg, "MAX_P95_DECISION_MS", 80.0)),
        "sustained_windows": int(getattr(cfg, "SUSTAINED_WINDOWS", 3)),
        "cooldown_sec": float(getattr(cfg, "EXIT_ONLY_COOLDOWN_S", 30.0)),
        "halt_on_breach": bool(getattr(cfg, "HALT_ON_BREACH", True)),
    }


def _should_skip_trade_builder_for_latency_guard(
    *,
    latency_soften_active: bool,
    execution_mode: str | None,
) -> bool:
    if not bool(latency_soften_active):
        return False
    if str(execution_mode or "").strip().upper() != "LIVE":
        return False
    return bool(getattr(cfg, "LATENCY_GUARD_LIVE_SKIP_TRADE_BUILDER", True))


def _should_skip_background_maintenance_for_latency_guard(
    *,
    latency_action: str | None,
    execution_mode: str | None,
    feed_ok: bool | None,
) -> bool:
    if str(execution_mode or "").strip().upper() != "LIVE":
        return False
    if not bool(getattr(cfg, "LATENCY_GUARD_LIVE_SKIP_BACKGROUND_MAINTENANCE", True)):
        return False
    if feed_ok is False:
        return True
    return str(latency_action or ACTION_OK).strip().upper() != ACTION_OK


def _latency_guard_metric_context(latency_state: Mapping[str, Any] | None, latency_stats: Mapping[str, Any] | None) -> dict[str, Any]:
    state = dict(latency_state or {})
    stats = dict(latency_stats or {})
    thresholds = stats.get("thresholds") if isinstance(stats.get("thresholds"), Mapping) else {}
    stages = stats.get("stages") if isinstance(stats.get("stages"), Mapping) else {}
    breach = stats.get("breach") if isinstance(stats.get("breach"), Mapping) else {}

    candidates: list[dict[str, Any]] = []

    def _stage_metric(stage_name: str, *, breach_metric: str, threshold_metric: str, metric_label: str) -> None:
        stage = stages.get(stage_name) if isinstance(stages, Mapping) else {}
        if not isinstance(stage, Mapping):
            return
        if not bool(breach.get(breach_metric)):
            return
        value = stage.get("p95_ms")
        threshold = thresholds.get(threshold_metric)
        try:
            value_f = float(value)
        except Exception:
            value_f = None
        try:
            threshold_f = float(threshold)
        except Exception:
            threshold_f = None
        ratio = None
        if value_f is not None and threshold_f not in (None, 0.0):
            try:
                ratio = float(value_f) / float(threshold_f)
            except Exception:
                ratio = None
        candidates.append(
            {
                "latency_guard_metric": metric_label,
                "latency_guard_value": value_f,
                "latency_guard_threshold": threshold_f,
                "latency_guard_source": f"latency_monitor.stages.{stage_name}.p95_ms",
                "latency_guard_breach_metric": breach_metric,
                "latency_guard_ratio": ratio,
            }
        )

    _stage_metric("total_loop", breach_metric="sustained_total_breach", threshold_metric="max_p95_total_ms", metric_label="total_loop.p95_ms")
    _stage_metric("decision_build", breach_metric="sustained_decision_breach", threshold_metric="max_p95_decision_ms", metric_label="decision_build.p95_ms")
    _stage_metric("total_loop", breach_metric="p95_total_breach", threshold_metric="max_p95_total_ms", metric_label="total_loop.p95_ms")
    _stage_metric("decision_build", breach_metric="p95_decision_breach", threshold_metric="max_p95_decision_ms", metric_label="decision_build.p95_ms")

    chosen = None
    if candidates:
        candidates = sorted(
            candidates,
            key=lambda item: (
                0 if item.get("latency_guard_breach_metric", "").startswith("sustained") else 1,
                -(float(item.get("latency_guard_ratio") or 0.0)),
            ),
        )
        chosen = candidates[0]

    action = str(state.get("action") or ACTION_OK).upper()
    reason = str(state.get("reason") or "latency_within_budget")
    unknown_state = not bool(stats) or not bool(stages)
    triggered = action in {ACTION_COOLDOWN, ACTION_DEGRADE_EXIT_ONLY, ACTION_HALT_ALL} or reason not in {
        "latency_within_budget",
        "market_closed",
    }
    if unknown_state:
        triggered = True
        reason = "latency_guard_state_unknown"
    out = {
        "latency_guard_triggered": bool(triggered),
        "latency_guard_mode": str(getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM").strip().upper(),
        "latency_guard_action": action,
        "latency_guard_source": None,
        "latency_guard_reason": reason,
        "latency_guard_metric": None,
        "latency_guard_value": None,
        "latency_guard_threshold": None,
        "latency_guard_age_sec": None,
        "latency_guard_last_ok_at": state.get("last_ok_at"),
        "latency_guard_last_bad_at": state.get("last_bad_at"),
        "latency_guard_recovery_required": bool(action in {ACTION_COOLDOWN, ACTION_DEGRADE_EXIT_ONLY, ACTION_HALT_ALL}),
    }
    if chosen is not None:
        out.update(
            {
                "latency_guard_source": chosen.get("latency_guard_source"),
                "latency_guard_metric": chosen.get("latency_guard_metric"),
                "latency_guard_value": chosen.get("latency_guard_value"),
                "latency_guard_threshold": chosen.get("latency_guard_threshold"),
            }
        )
    if out["latency_guard_source"] is None and triggered:
        out["latency_guard_source"] = "latency_guard_state"
    if unknown_state:
        out["latency_guard_recovery_required"] = True
    if state.get("cooldown_until_ts"):
        try:
            out["latency_guard_age_sec"] = max(0.0, float(now_utc_epoch()) - float(state.get("ts_epoch") or 0.0))
        except Exception:
            out["latency_guard_age_sec"] = None
    return out


def _scan_visible_suggestions(path: Path) -> dict:
    counts = {
        "visible_suggestion_count": 0,
        "visible_advisory_count": 0,
        "visible_queue_only_count": 0,
        "visible_executable_count": 0,
        "visible_ready_count": 0,
        "visible_executable_status_count": 0,
        "primary_blocker": None,
    }
    blocker_counts: Counter = Counter()

    def _source_is_fresh(source_path: Path) -> bool:
        max_age_sec = float(getattr(cfg, "STATUS_VISIBLE_SOURCE_MAX_AGE_SEC", 180.0) or 180.0)
        if max_age_sec <= 0.0:
            return True
        try:
            age_sec = max(0.0, time.time() - float(source_path.stat().st_mtime))
        except Exception:
            return False
        return bool(age_sec <= max_age_sec)

    def _ingest_row(row: dict) -> None:
        if not isinstance(row, dict):
            return
        if row.get("advisory_visible") is False:
            return
        counts["visible_suggestion_count"] += 1
        execution_status = str(row.get("execution_status") or "").strip().lower()
        final_action = str(row.get("final_action") or "").strip().upper()
        readiness = str(row.get("readiness") or "").strip().upper()
        execution_allowed = bool(row.get("execution_allowed"))
        if readiness == "READY":
            counts["visible_ready_count"] += 1
        if execution_status == "executable":
            counts["visible_executable_status_count"] += 1
        executable_visible = bool(
            execution_status == "executable"
            or (
                execution_allowed
                and (final_action == "EXECUTE" or readiness == "READY")
            )
        )
        if executable_visible:
            counts["visible_executable_count"] += 1
        elif execution_status == "queue_only" or final_action == "QUEUE_ONLY" or readiness == "QUEUE_ONLY":
            counts["visible_queue_only_count"] += 1
        else:
            counts["visible_advisory_count"] += 1
        for field in ("hard_blockers", "blockers", "soft_penalties", "warnings"):
            for blocker in list(row.get(field) or []):
                text = str(blocker or "").strip()
                if text:
                    blocker_counts[text] += 1
        for field in ("hard_reason", "final_blocker"):
            text = str(row.get(field) or "").strip()
            if text:
                blocker_counts[text] += 1

    try:
        use_review_queue_snapshot = bool(
            getattr(cfg, "STATUS_VISIBLE_COUNTS_USE_REVIEW_QUEUE_SNAPSHOT", True)
        )
        review_queue_path = Path(
            str(getattr(cfg, "REVIEW_QUEUE_PATH", logs_dir() / "review_queue.json"))
        ).expanduser()
        if use_review_queue_snapshot and review_queue_path.exists() and _source_is_fresh(review_queue_path):
            review_rows = json.loads(review_queue_path.read_text(encoding="utf-8"))
            if isinstance(review_rows, list):
                for row in review_rows:
                    _ingest_row(row)
                if blocker_counts:
                    counts["primary_blocker"] = str(blocker_counts.most_common(1)[0][0])
                return counts
        if not path.exists() or not _source_is_fresh(path):
            return counts
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = str(raw_line or "").strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                _ingest_row(row)
        if blocker_counts:
            counts["primary_blocker"] = str(blocker_counts.most_common(1)[0][0])
        return counts
    except Exception:
        return counts


def _zero_visible_counts(counts: dict) -> dict:
    out = dict(counts or {})
    out["visible_suggestion_count"] = 0
    out["visible_advisory_count"] = 0
    out["visible_queue_only_count"] = 0
    out["visible_executable_count"] = 0
    out["visible_ready_count"] = 0
    out["visible_executable_status_count"] = 0
    return out


def _build_pipeline_funnel_payload(
    *,
    universe: int,
    candidates: int,
    scored: int,
    visible_counts: dict | None,
    emitted: int,
    returned: int = 0,
) -> dict:
    counts = dict(visible_counts or {})
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "universe": int(universe),
        "candidates": int(candidates),
        "scored": int(scored),
        "ready": int(counts.get("visible_ready_count") or 0),
        "executable": int(counts.get("visible_executable_status_count") or 0),
        "emitted": int(emitted),
        "advisory": int(counts.get("visible_advisory_count") or 0),
        "queue_only": int(counts.get("visible_queue_only_count") or 0),
        "returned": int(returned),
    }


def _build_top_opportunities_payload(
    *,
    candidates: list,
    executable_top_n: int | None = None,
    advisory_top_n: int | None = None,
    active_trade: dict | None = None,
    execution_truth_context: dict | None = None,
    cycle_primary_reason: str | None = None,
) -> dict:
    candidates, _ = _filter_invalid_cycle_candidates(candidates, symbol="GLOBAL")
    exec_limit = max(0, int(executable_top_n if executable_top_n is not None else getattr(cfg, "TOP_EXECUTABLE_OPPORTUNITIES_N", 5)))
    advisory_limit = max(0, int(advisory_top_n if advisory_top_n is not None else getattr(cfg, "TOP_ADVISORY_OPPORTUNITIES_N", 5)))
    phase2_top_n = max(1, int(getattr(cfg, "PHASE2_TOP_N", max(exec_limit, advisory_limit, 1)) or max(exec_limit, advisory_limit, 1)))
    phase2_result = run_engine_phase2(
        candidates or [],
        active_trade=active_trade,
        top_n=phase2_top_n,
        min_enter_score=float(getattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.70) or 0.70),
    )
    logger.info(
        "phase2_decision_snapshot state=%s reason=%s selected_trade_id=%s ranked_count=%s",
        phase2_result.get("state"),
        phase2_result.get("reason"),
        _trade_attr(phase2_result.get("selected"), "trade_id"),
        len(list(phase2_result.get("ranked") or [])),
    )
    notes: list[str] = []

    def _project(rows: list, label: str) -> list[dict]:
        projected: list[dict] = []
        for candidate in rows or []:
            advisory_row = project_advisory_row(candidate)
            if isinstance(advisory_row, dict):
                try:
                    cls = classify_candidate_row(
                        row=advisory_row,
                        phase2_state=str(phase2_result.get("state") or "NO_TRADE"),
                        cycle_primary_reason=cycle_primary_reason,
                    )
                    advisory_row.update(cls.to_dict())
                    advisory_row.setdefault(
                        "primary_reason",
                        advisory_row.get("execution_quality_reason_code")
                        or advisory_row.get("execution_block_reason")
                        or advisory_row.get("permission_reason")
                        or advisory_row.get("phase2_soft_degrade_reason")
                        or None,
                    )
                    advisory_row.setdefault(
                        "execution_block_reason",
                        advisory_row.get("execution_quality_reason_code")
                        or advisory_row.get("execution_block_reason")
                        or advisory_row.get("permission_reason")
                        or None,
                    )
                    for key in ("quote_source", "quote_age_sec", "spread_pct"):
                        advisory_row.setdefault(key, None)
                    sf = advisory_row.get("source_flags") if isinstance(advisory_row.get("source_flags"), dict) else {}
                    if isinstance(sf, dict):
                        advisory_row.setdefault("recovered_fallback", bool(sf.get("recovered_fallback")))
                except Exception:
                    pass
                projected.append(advisory_row)
            else:
                trade_id = getattr(candidate, "trade_id", None) if not isinstance(candidate, dict) else candidate.get("trade_id")
                notes.append(f"{label}_projection_failed:{trade_id}")
        return projected

    phase2_state = str(phase2_result.get("state") or "NO_TRADE").strip().upper() or "NO_TRADE"
    ranked = list(phase2_result.get("ranked") or [])
    selected = phase2_result.get("selected")
    selected_id = str(_trade_attr(selected, "trade_id", "") or "").strip() if selected is not None else ""

    top_executable_seed: list = []
    if selected is not None and phase2_state in {"ENTER", "REPLACE", "HOLD"}:
        top_executable_seed.append(selected)
    if exec_limit > 0:
        top_executable_seed = top_executable_seed[:exec_limit]
    else:
        top_executable_seed = []

    top_advisory_seed: list = []
    for candidate in ranked:
        trade_id = str(_trade_attr(candidate, "trade_id", "") or "").strip()
        if selected_id and trade_id and trade_id == selected_id:
            continue
        top_advisory_seed.append(candidate)
        if advisory_limit > 0 and len(top_advisory_seed) >= advisory_limit:
            break

    top_executable = _project(top_executable_seed, "executable")
    top_advisory = _project(top_advisory_seed, "advisory")
    top_executable_evidence = [
        normalize_candidate_execution_truth_payload(row, execution_truth_context=execution_truth_context)
        for row in top_executable
    ] if execution_truth_context is not None else list(top_executable)
    top_advisory_evidence = [
        normalize_candidate_execution_truth_payload(row, execution_truth_context=execution_truth_context)
        for row in top_advisory
    ] if execution_truth_context is not None else list(top_advisory)
    if execution_truth_context is None:
        top_executable_truth = list(top_executable_evidence)
        top_advisory_truth = list(top_advisory_evidence)
        top_blocked_truth = []
    else:
        top_executable_truth = [row for row in top_executable_evidence if bool(row.get("reportable_executable"))]
        top_advisory_truth = [row for row in top_advisory_evidence if str(row.get("visibility_bucket") or "").strip().lower() == "advisory"]
        top_blocked_truth = [row for row in top_executable_evidence if str(row.get("visibility_bucket") or "").strip().lower() == "blocked"]
    top_executable_block_reasons = []
    if execution_truth_context is not None and top_executable_truth:
        for row in top_executable_truth:
            top_executable_block_reasons.extend([str(reason) for reason in list(row.get("execution_truth_blockers") or []) if str(reason).strip()])
    if execution_truth_context is not None and top_blocked_truth:
        for row in top_blocked_truth:
            top_executable_block_reasons.extend([str(reason) for reason in list(row.get("execution_truth_blockers") or []) if str(reason).strip()])
    truth_executable_count = sum(1 for row in top_executable_truth if bool(row.get("reportable_executable")))
    if truth_executable_count > 0 and phase2_state in {"ENTER", "REPLACE", "HOLD"}:
        selector_outcome = "EXECUTE_TOP"
    elif phase2_state == "WATCHLIST":
        selector_outcome = "WATCHLIST_ONLY"
    else:
        selector_outcome = "NO_EXECUTABLE_OPPORTUNITY"
    return {
        "top_executable_opportunities": top_executable_truth,
        "top_advisory_opportunities": top_advisory_truth,
        "top_blocked_opportunities": top_blocked_truth,
        "top_executable_count": int(truth_executable_count),
        "top_advisory_count": int(len(top_advisory_truth)),
        "top_blocked_count": int(len(top_blocked_truth)),
        "source_candidate_count": int(len(candidates or [])),
        "selector_outcome": selector_outcome,
        "phase2_state": phase2_state,
        "phase2_reason": str(phase2_result.get("reason") or ""),
        "phase2_ranked_count": int(len(ranked)),
        "phase2_selected_trade_id": selected_id or None,
        "execution_truth_blockers": list(dict.fromkeys(top_executable_block_reasons)),
        "top_executable_block_reasons": list(dict.fromkeys(top_executable_block_reasons)),
        "cycle_primary_reason": cycle_primary_reason,
        "_phase2_next_active_trade": phase2_result.get("next_active_trade"),
        "notes": notes,
    }


def _build_ranked_pipeline_runtime_report(
    *,
    top_payload: dict,
    cycle_ranked_candidates: list,
    market_open: bool,
    feed_truth_payload: dict | None,
    indicator_payload: dict | None,
    cycle_blockers: dict,
) -> dict:
    ranked_candidates = [cand for cand in list(cycle_ranked_candidates or []) if isinstance(cand, dict)]
    feed_truth_payload = dict(feed_truth_payload or {})
    canonical_feed_truth = feed_truth_payload.get("canonical_feed_truth") if isinstance(feed_truth_payload.get("canonical_feed_truth"), dict) else {}
    feed_truth_state = str(feed_truth_payload.get("feed_truth_state") or canonical_feed_truth.get("state") or "").strip()
    feed_truth_reason_code = str(feed_truth_payload.get("feed_truth_reason_code") or canonical_feed_truth.get("reason_code") or "").strip()
    report = {
        "schema_version": 1,
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "ranked_candidate_count": int(len(ranked_candidates)),
        "source_candidate_count": int(len(ranked_candidates)),
        "top_rank_strategy_id": str(top_payload.get("phase2_selected_trade_id") or "") or None,
        "phase2_state": str(top_payload.get("phase2_state") or ""),
        "phase2_reason": str(top_payload.get("phase2_reason") or ""),
        "phase2_ranked_count": int(top_payload.get("phase2_ranked_count") or 0),
        "phase2_input_candidate_count": int(len(ranked_candidates)),
        "top_executable_count": int(top_payload.get("top_executable_count") or 0),
        "top_advisory_count": int(top_payload.get("top_advisory_count") or 0),
        "market_open": bool(market_open),
        "feed_truth_state": feed_truth_state,
        "feed_truth_reason_code": feed_truth_reason_code,
        "indicator_readiness_state": str((indicator_payload or {}).get("indicator_readiness_state") or ""),
        "indicator_readiness_reason_code": str((indicator_payload or {}).get("indicator_readiness_reason_code") or ""),
        "blocker_counts": {str(k): int(v) for k, v in dict(cycle_blockers or {}).items()},
        "metadata": {
            "orchestrator": "ranked_opportunity_pipeline_v1",
            "scope": "read_only_no_execution_no_dashboard_no_live_wiring",
            "producer": "orchestrator",
        },
    }
    return report


def _write_ranked_pipeline_runtime_evidence(
    *,
    top_payload: dict,
    cycle_ranked_candidates: list,
    market_open: bool,
    feed_truth_payload: dict | None,
    indicator_payload: dict | None,
    cycle_blockers: dict,
) -> dict | None:
    ranked_pipeline_report = _build_ranked_pipeline_runtime_report(
        top_payload=top_payload,
        cycle_ranked_candidates=list(cycle_ranked_candidates or []),
        market_open=bool(market_open),
        feed_truth_payload=feed_truth_payload if isinstance(feed_truth_payload, dict) else {},
        indicator_payload=indicator_payload if isinstance(indicator_payload, dict) else {},
        cycle_blockers=dict(cycle_blockers),
    )
    write_ranked_pipeline_evidence(ranked_pipeline_report, output_dir=logs_dir())
    return ranked_pipeline_report


def _top_blockers_payload(blocker_counts: Counter, limit: int = 5) -> list[dict]:
    out: list[dict] = []
    for reason, count in blocker_counts.most_common(max(1, int(limit))):
        out.append({"reason": str(reason), "count": int(count)})
    return out


def _coerce_snapshot_number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except Exception:
        return None
    if out != out:
        return None
    return out


def _snapshot_ohlc_payload(market_data: dict) -> dict:
    cache = market_data.get("index_quote_cache") if isinstance(market_data.get("index_quote_cache"), dict) else {}
    last_candle = market_data.get("last_candle") if isinstance(market_data.get("last_candle"), dict) else {}
    return {
        "open": _coerce_snapshot_number(last_candle.get("open", cache.get("open"))),
        "high": _coerce_snapshot_number(last_candle.get("high", cache.get("high"))),
        "low": _coerce_snapshot_number(last_candle.get("low", cache.get("low"))),
        "close": _coerce_snapshot_number(last_candle.get("close", cache.get("close"))),
    }


def _snapshot_atm_strike(market_data: dict) -> float | None:
    explicit = _coerce_snapshot_number(market_data.get("atm_strike"))
    if explicit is not None:
        return explicit
    chain = market_data.get("option_chain") if isinstance(market_data.get("option_chain"), list) else []
    ltp = _coerce_snapshot_number(market_data.get("ltp"))
    strikes: list[float] = []
    for row in list(chain or []):
        if not isinstance(row, dict):
            continue
        strike = _coerce_snapshot_number(row.get("strike"))
        if strike is not None:
            strikes.append(strike)
    if not strikes:
        return None
    if ltp is None:
        return min(strikes)
    return min(strikes, key=lambda strike: abs(float(strike) - float(ltp)))


def _snapshot_symbol_payload(market_data: dict, warnings: list[str]) -> dict:
    symbol = str(market_data.get("symbol") or "").upper()
    cross_quality = market_data.get("cross_asset_quality") if isinstance(market_data.get("cross_asset_quality"), dict) else {}
    option_chain_health = market_data.get("option_chain_health") if isinstance(market_data.get("option_chain_health"), dict) else {}
    feed_health = market_data.get("feed_health") if isinstance(market_data.get("feed_health"), dict) else {}
    cross_asset_available = bool(cross_quality) and not bool(cross_quality.get("disabled", False))
    if not cross_asset_available:
        warnings.append(f"{symbol}:cross_asset_unavailable")
    chain_quality = option_chain_health.get("status")
    if chain_quality in (None, "", "None"):
        warnings.append(f"{symbol}:option_chain_summary_missing")
    return build_symbol_market_snapshot(
        spot=_coerce_snapshot_number(market_data.get("spot", market_data.get("ltp"))),
        ltp=_coerce_snapshot_number(market_data.get("ltp")),
        change_pct=_coerce_snapshot_number(
            market_data.get("change_pct", market_data.get("ltp_change"))
        ),
        ohlc=_snapshot_ohlc_payload(market_data),
        regime={
            "trend": market_data.get("primary_regime") or market_data.get("regime"),
            "volatility_state": market_data.get("day_type"),
            "confidence": _coerce_snapshot_number(market_data.get("regime_confidence")),
        },
        cross_asset={
            "available": bool(cross_asset_available),
            "signals": {
                key: value
                for key, value in {
                    "quality": cross_quality.get("status") or cross_quality.get("quality"),
                    "any_stale": cross_quality.get("any_stale"),
                    "disabled_reason": cross_quality.get("disabled_reason"),
                }.items()
                if value not in (None, "", [], {})
            },
        },
        option_chain_summary={
            "atm_strike": _snapshot_atm_strike(market_data),
            "pcr": _coerce_snapshot_number(market_data.get("pcr")),
            "max_pain": _coerce_snapshot_number(market_data.get("max_pain")),
            "chain_quality": None if chain_quality in (None, "", "None") else str(chain_quality),
        },
        feed_health={
            "underlying_quote_age_sec": _coerce_snapshot_number(market_data.get("quote_age_sec")),
            "option_quote_age_sec": _coerce_snapshot_number(
                option_chain_health.get("quote_age_sec", feed_health.get("option_quote_age_sec"))
            ),
            "status": feed_health.get("status") or option_chain_health.get("status"),
        },
    )


def produce_and_store_market_snapshot(
    *,
    market_data_list: list[dict] | None,
    market_open: bool,
    compute_ms: float | None = None,
    loop_id: str | None = None,
) -> dict:
    warnings: list[str] = []
    symbols_payload: dict[str, dict] = {}
    for market_data in list(market_data_list or []):
        if not isinstance(market_data, dict):
            continue
        symbol = str(market_data.get("symbol") or "").upper()
        if not symbol:
            continue
        symbols_payload[symbol] = _snapshot_symbol_payload(market_data, warnings)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    snapshot = build_dashboard_market_snapshot(
        generated_at=generated_at,
        market_open=bool(market_open),
        symbols_payload=symbols_payload,
        warnings=list(dict.fromkeys(warnings)),
        compute_ms=compute_ms,
        loop_id=loop_id,
    )
    started = time.perf_counter()
    try:
        path = write_market_snapshot_atomic(snapshot)
        elapsed_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
        logger.info(
            "[MARKET_SNAPSHOT_WRITE] path=%s symbols=%d compute_ms=%.2f write_ms=%.2f",
            path,
            len(symbols_payload),
            float(compute_ms or 0.0),
            elapsed_ms,
        )
        return snapshot
    except Exception as exc:
        logger.error(
            "[MARKET_SNAPSHOT_WRITE_ERROR] symbols=%d error=%s:%s",
            len(symbols_payload),
            type(exc).__name__,
            exc,
        )
        raise


def _prepare_trade_for_review_queue(trade):
    if str(_trade_attr(trade, "instrument", "") or "").upper() != "OPT":
        return trade, True, []
    entry = {
        "symbol": _trade_attr(trade, "symbol"),
        "underlying": _trade_attr(trade, "underlying"),
        "instrument": _trade_attr(trade, "instrument"),
        "instrument_type": _trade_attr(trade, "instrument_type"),
        "instrument_token": _trade_attr(trade, "instrument_token"),
        "tradingsymbol": _trade_attr(trade, "tradingsymbol"),
        "expiry_date": _trade_attr(trade, "expiry_date"),
        "expiry": _trade_attr(trade, "expiry"),
        "strike": _trade_attr(trade, "strike"),
        "option_type": _trade_attr(trade, "option_type"),
        "type": _trade_attr(trade, "type"),
        "right": _trade_attr(trade, "right"),
        "instrument_id": _trade_attr(trade, "instrument_id"),
    }
    enriched = _enrich_contract_identity(entry)
    trade = _replace_trade_fields(
        trade,
        {
            "instrument_token": enriched.get("instrument_token"),
            "tradingsymbol": enriched.get("tradingsymbol"),
            "expiry_date": enriched.get("expiry_date"),
            "expiry": enriched.get("expiry"),
            "strike": enriched.get("strike"),
            "option_type": enriched.get("option_type"),
            "right": enriched.get("right") or enriched.get("type"),
            "instrument_id": enriched.get("instrument_id"),
        },
    )
    if _has_valid_broker_contract(enriched):
        return trade, True, []
    return trade, False, _missing_broker_contract_fields(enriched)


def _queue_review_candidate(
    trade,
    *,
    queue_path=None,
    extra: dict | None = None,
    reject_source: str = "orchestrator_review_queue",
    allow_unresolved_for_analytics: bool = False,
):
    prepared_trade, contract_ok, missing_fields = _prepare_trade_for_review_queue(trade)
    if contract_ok or allow_unresolved_for_analytics:
        add_to_queue(prepared_trade, queue_path=queue_path, extra=extra)
        return True, prepared_trade
    append_reject_reasons(
        symbol=_trade_attr(prepared_trade, "symbol"),
        strategy=_trade_attr(prepared_trade, "strategy"),
        reasons=["unresolved_contract"],
        mode=str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper(),
        source=reject_source,
        extra={
            **dict(extra or {}),
            "trade_id": _trade_attr(prepared_trade, "trade_id"),
            "queue_path": str(queue_path) if queue_path is not None else "default",
            "missing_fields": list(missing_fields or []),
            "identity_scope": "broker_tradable",
            "broker_contract_required": True,
        },
    )
    return False, prepared_trade


def _queue_rejected_candidate_for_analytics(
    ranked_candidates,
    *,
    gate_reasons: list[str] | None = None,
    reject_reason: str | None = None,
    queue_path=None,
    reject_source: str = "orchestrator_gate_rejected_candidate",
    extra: dict | None = None,
    exclude_trade_ids: set[str] | None = None,
):
    if not bool(getattr(cfg, "QUEUE_REJECTED_CANDIDATES_ENABLE", True)):
        return False, None
    excluded = {str(tid) for tid in (exclude_trade_ids or set()) if str(tid)}
    candidates = []
    for candidate in list(ranked_candidates or []):
        if candidate is None:
            continue
        trade_id = _trade_attr(candidate, "trade_id")
        if trade_id and str(trade_id) in excluded:
            continue
        candidates.append(candidate)
    if not candidates:
        return False, None
    selected = candidates[0]
    reasons = [str(reason) for reason in (gate_reasons or []) if str(reason).strip()]
    block_reason = str(reject_reason or (reasons[0] if reasons else "gate_rejected")).strip() or "gate_rejected"
    if bool(getattr(cfg, "GATE_REJECT_TRACE_ENABLE", True)):
        print(
            "ORCH_GATE_REJECT_SOURCE",
            {
                "reject_source": reject_source,
                "reject_reason": reject_reason,
                "reasons": list(reasons),
                "symbol": _trade_attr(selected, "symbol"),
            },
        )
    payload_extra = dict(extra or {})
    payload_extra.setdefault("category", "gate_rejected_candidate")
    payload_extra.setdefault("tier", "ANALYTICS")
    payload_extra.setdefault("gate_reasons", list(reasons))
    payload_extra.setdefault("builder_reject_reason", block_reason)
    payload_extra.setdefault("execution_blocked", True)
    payload_extra.setdefault("execution_block_reason", block_reason)
    if bool(getattr(cfg, "QUEUE_REJECTED_CANDIDATES_FORCE_ADVISORY", True)):
        payload_extra.setdefault("permission", "ADVISORY_ONLY")
        payload_extra.setdefault("readiness", "ADVISORY_ONLY")
        payload_extra.setdefault("final_action", "ADVISORY_ONLY")
        payload_extra.setdefault("execution_status", "scored")
        payload_extra.setdefault("candidate_status", "scored")
        payload_extra.setdefault("eligible_for_execution", False)
    payload_extra.setdefault("analytics_only", True)
    advisory_row = project_advisory_row(selected, extra=payload_extra)
    if advisory_row is None:
        return False, None
    paths = rejected_candidates_paths()
    _append_review_jsonl(paths, advisory_row)
    return True, advisory_row


def _queue_market_data_fallback_candidate_for_analytics(
    market_data: dict,
    *,
    gate_reasons: list[str] | None = None,
    reject_reason: str | None = None,
    queue_path=None,
    reject_source: str = "orchestrator_market_data_fallback",
    enabled_flag: str = "QUEUE_PREBUILDER_GATE_CANDIDATES_ENABLE",
    candidate_origin: str = "pre_builder_gate",
    strategy_name: str = "PRE_BUILDER_FALLBACK",
    setup_variant: str = "pre_builder_gate",
    category: str = "pre_builder_gate_candidate",
    decision_stage: str = "pre_builder_gate",
):
    if not bool(getattr(cfg, enabled_flag, True)):
        return False, None
    data = dict(market_data or {})
    symbol = str(data.get("symbol") or "").strip().upper()
    if not symbol:
        return False, None
    reasons = [str(reason) for reason in (gate_reasons or []) if str(reason).strip()]
    normalized_origin = str(candidate_origin or "fallback").strip().lower() or "fallback"
    block_reason = str(reject_reason or (reasons[0] if reasons else normalized_origin)).strip() or normalized_origin
    trade_prefix = normalized_origin.upper().replace("-", "_").replace(" ", "_")
    candidate = {
        "trade_id": f"{trade_prefix[:24]}-{symbol}-{int(time.time() * 1000)}",
        "symbol": symbol,
        "underlying": symbol,
        "instrument": str(data.get("instrument") or "OPT").strip().upper() or "OPT",
        "instrument_id": data.get("instrument_id") or f"PREBUILDER::{symbol}",
        "instrument_token": data.get("instrument_token"),
        "tradingsymbol": data.get("tradingsymbol"),
        "expiry": data.get("expiry"),
        "expiry_date": data.get("expiry_date"),
        "strike": data.get("strike"),
        "option_type": data.get("option_type") or data.get("right"),
        "right": data.get("right") or data.get("option_type"),
        "side": data.get("side") or data.get("direction"),
        "entry_price": None,
        "expected_entry": None,
        "signal_price": data.get("ltp") or data.get("spot") or data.get("underlying_spot"),
        "stop_loss": None,
        "target": None,
        "strategy": strategy_name,
        "strategy_family": "fallback",
        "candidate_type": "fallback",
        "setup_variant": setup_variant,
        "confidence": 0.1,
        "builder_confidence": 0.1,
        "global_confidence": 0.1,
        "permission_confidence": 0.1,
        "timestamp": now_ist().isoformat(),
        "source_flags": {
            "candidate_origin": normalized_origin,
            "gate_reasons": list(reasons),
        },
    }
    payload_extra = {
        "category": category,
        "tier": "ANALYTICS",
        "decision_stage": decision_stage,
        "gate_reasons": list(reasons),
        "builder_reject_reason": block_reason,
        "execution_blocked": True,
        "execution_block_reason": block_reason,
        "permission": "ADVISORY_ONLY",
        "readiness": "ADVISORY_ONLY",
        "final_action": "ADVISORY_ONLY",
        "execution_status": "advisory_only",
        "analytics_only": True,
    }
    advisory_row = project_advisory_row(candidate, extra=payload_extra)
    if advisory_row is None:
        return False, None
    _append_review_jsonl(rejected_candidates_paths(), advisory_row)
    return True, advisory_row


def _queue_prebuilder_gate_candidate_for_analytics(
    market_data: dict,
    *,
    gate_reasons: list[str] | None = None,
    reject_reason: str | None = None,
    queue_path=None,
    reject_source: str = "orchestrator_prebuilder_gate",
):
    return _queue_market_data_fallback_candidate_for_analytics(
        market_data,
        gate_reasons=gate_reasons,
        reject_reason=reject_reason,
        queue_path=queue_path,
        reject_source=reject_source,
        enabled_flag="QUEUE_PREBUILDER_GATE_CANDIDATES_ENABLE",
        candidate_origin="pre_builder_gate",
        strategy_name="PRE_BUILDER_FALLBACK",
        setup_variant="pre_builder_gate",
        category="pre_builder_gate_candidate",
        decision_stage="pre_builder_gate",
    )


def _queue_invalid_snapshot_candidate_for_analytics(
    market_data: dict,
    *,
    gate_reasons: list[str] | None = None,
    reject_reason: str | None = None,
    queue_path=None,
    reject_source: str = "orchestrator_invalid_snapshot",
):
    return _queue_market_data_fallback_candidate_for_analytics(
        market_data,
        gate_reasons=gate_reasons,
        reject_reason=reject_reason,
        queue_path=queue_path,
        reject_source=reject_source,
        enabled_flag="QUEUE_INVALID_SNAPSHOT_CANDIDATES_ENABLE",
        candidate_origin="invalid_snapshot",
        strategy_name="INVALID_SNAPSHOT_FALLBACK",
        setup_variant="invalid_snapshot",
        category="invalid_snapshot_candidate",
        decision_stage="invalid_snapshot",
    )


def _consume_trade_builder_ranked_candidates(builder) -> list:
    ranked = list(getattr(builder, "_last_ranked_candidates", []) or [])
    try:
        builder._set_last_ranked_candidates([])
    except Exception:
        try:
            builder._last_ranked_candidates = []
        except Exception:
            pass
    return ranked


def _best_trade_builder_reject_reason(
    reject_ctx: dict | None,
    *,
    fallback: str = "unspecified_trade_builder_reject",
) -> str:
    generic = "unspecified_trade_builder_reject"
    ctx = dict(reject_ctx or {})
    for field in (
        "reason",
        "reject_reason",
        "final_blocker",
        "hard_reason",
        "permission_reason",
        "entry_block_code",
        "quote_validation_status",
    ):
        value = str(ctx.get(field) or "").strip()
        if value and value.lower() != generic:
            return value
    for collection in ("gate_reasons", "hard_blockers", "blockers", "warnings"):
        for item in list(ctx.get(collection) or []):
            text = str(item or "").strip()
            if text and text.lower() != generic:
                return text
    fallback_value = str(ctx.get("reason") or ctx.get("reject_reason") or fallback).strip()
    return fallback_value or fallback


def _soft_option_scan_gate_reasons() -> set[str]:
    raw = str(getattr(cfg, "OPTION_SCAN_SOFT_GATE_REASONS", "type_mismatch,iv_skew_curvature,iv_bounds") or "")
    return {item.strip().upper() for item in raw.split(",") if item and item.strip()}


def _should_harden_soft_scan_reason(reason: str) -> bool:
    code = str(reason or "").strip().upper()
    if code == "TYPE_MISMATCH":
        return bool(getattr(cfg, "OPTION_TYPE_MISMATCH_HARD_REJECT", False))
    if code == "IV_BOUNDS":
        return bool(getattr(cfg, "OPTION_IV_BOUNDS_HARD_REJECT", False))
    if code == "IV_SKEW_CURVATURE":
        return bool(getattr(cfg, "OPTION_IV_SKEW_CURVATURE_HARD_REJECT", False))
    return False


def _augment_ranked_candidates_with_soft_reject(
    *,
    trade_builder,
    ranked_candidates: list | None,
    market_data: dict,
    execution_mode: str,
    symbol: str,
) -> tuple[list, list[dict], str, list[str]]:
    ranked = list(ranked_candidates or [])
    reject_ctx = {}
    try:
        reject_ctx = dict(getattr(trade_builder, "_reject_ctx", {}) or {})
    except Exception:
        reject_ctx = {}
    reject_reason = _best_trade_builder_reject_reason(
        reject_ctx,
        fallback="unspecified_trade_builder_reject",
    )
    if str(reject_reason).strip().lower() == "unspecified_trade_builder_reject":
        try:
            scan_counts = dict(getattr(trade_builder, "_scan_reject_counts", {}) or {})
        except Exception:
            scan_counts = {}
        ranked_scan_reasons = sorted(
            (
                (str(code or "").strip(), int(count or 0))
                for code, count in scan_counts.items()
                if str(code or "").strip()
                and str(code or "").strip().lower() != "unspecified_trade_builder_reject"
            ),
            key=lambda item: (-int(item[1]), str(item[0])),
        )
        if ranked_scan_reasons:
            reject_reason = str(ranked_scan_reasons[0][0]).strip() or reject_reason
            reject_ctx = dict(reject_ctx)
            reject_ctx.setdefault("gate_reasons", [reject_reason])
    if str(reject_reason).strip().lower() == "unspecified_trade_builder_reject":
        logger.warning("trade_builder_reject_reason_missing symbol=%s", symbol)
    reject_gate_reasons = [str(x) for x in (reject_ctx.get("gate_reasons") or []) if str(x).strip()]
    if bool(getattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False)):
        logger.info(
            "soft_reject_strict_mode_skip symbol=%s reason=%s",
            symbol,
            reject_reason,
        )
        return ranked, [], reject_reason, reject_gate_reasons
    mode = str(execution_mode or "").strip().upper()
    if reject_reason == "trend_vwap_fallback":
        return ranked, [], reject_reason, reject_gate_reasons
    if reject_reason == "no_candidates_survived" and mode == "LIVE":
        return ranked, [], reject_reason, reject_gate_reasons
    hard_reason_raw = str(
        getattr(
            cfg,
            "TRADE_BUILDER_HARD_REJECT_REASONS",
            "feed_stale,quote_missing,unresolved_contract,invalid_risk_levels,missing_live_quote,no_live_option_feed",
        )
        or ""
    )
    hard_reason_codes = {
        item.strip().upper()
        for item in hard_reason_raw.split(",")
        if item and item.strip()
    }
    hard_reason_codes.update(
        {
            "MISSING_LIVE_BIDASK",
            "MISSING_CONTRACT_FIELDS",
            "MISSING_OPTION_TOKEN",
            "NO_TOKEN",
            "NO_QUOTE",
            "NO_LIVE_QUOTE",
            "STALE_OPTION_TICK",
            "STALE_OPTION_QUOTE",
        }
    )
    soft_scan_reasons = _soft_option_scan_gate_reasons()
    reject_gate_reasons = [
        reason
        for reason in reject_gate_reasons
        if (
            str(reason or "").strip().upper() not in soft_scan_reasons
            or _should_harden_soft_scan_reason(reason)
        )
    ]
    if not reject_gate_reasons:
        normalized_reject_reason = str(reject_reason or "").strip().upper()
        if normalized_reject_reason in hard_reason_codes:
            reject_gate_reasons = [str(reject_reason)]
        elif str(reject_reason or "").strip():
            reject_gate_reasons = [str(reject_reason).strip()]

    def _should_keep_as_advisory(candidate_reasons: list[str]) -> bool:
        for code in candidate_reasons:
            text = str(code or "").strip().upper()
            if not text:
                continue
            if text in hard_reason_codes or text.startswith("HARD_"):
                return True
        return False

    soft_reject_candidates: list[dict] = []
    rankable_soft_reject_candidates: list[dict] = []
    soft_enabled = soft_reject_enabled(execution_mode)
    critical_reasons = critical_reject_reasons()
    is_critical = is_critical_reject_reason(reject_reason, critical_reasons)
    logger.info(
        "soft_reject_check symbol=%s mode=%s enabled=%s critical=%s reason=%s",
        symbol,
        execution_mode,
        soft_enabled,
        is_critical,
        reject_reason or "none",
    )
    if reject_reason == "unknown_reject":
        logger.info(
            "soft_reject_check_unknown symbol=%s reason=%s critical=%s",
            symbol,
            reject_reason,
            is_critical,
        )
    if soft_enabled and not is_critical:
        bases = list(ranked or [])
        if not bases:
            bases = [None]
        max_soft = soft_reject_max_per_symbol()
        for base in bases[:max_soft]:
            soft_candidate = build_soft_reject_candidate(
                market_data,
                reject_reason=reject_reason or "trade_builder_reject",
                reject_source="orchestrator_trade_builder_reject",
                gate_reasons=reject_gate_reasons,
                base_candidate=base if isinstance(base, dict) else None,
                execution_mode=execution_mode,
            )
            if soft_candidate:
                candidate_reason = str(
                    soft_candidate.get("reason")
                    or soft_candidate.get("reject_reason")
                    or ""
                ).strip()
                if (
                    candidate_reason
                    and candidate_reason.lower() != "unspecified_trade_builder_reject"
                    and str(reject_reason).strip().lower() == "unspecified_trade_builder_reject"
                ):
                    reject_reason = candidate_reason
                    reject_gate_reasons = [candidate_reason]
                source_flags = dict(soft_candidate.get("source_flags") or {})
                source_flags["candidate_origin"] = "softened_builder_path"
                source_flags["soft_reject_reason"] = reject_reason or "trade_builder_reject"
                soft_candidate["source_flags"] = source_flags
                soft_candidate["candidate_origin"] = "softened_builder_path"
                trade_id = str(soft_candidate.get("trade_id") or "").strip()
                if trade_id.startswith("softrej_"):
                    soft_candidate["trade_id"] = f"tbsoft_{symbol}_{trade_id.rsplit('_', 1)[-1]}"
                if str(soft_candidate.get("candidate_type") or "").strip().lower() in {"", "unknown"}:
                    soft_candidate["candidate_type"] = "directional"
                if str(soft_candidate.get("strategy_family") or "").strip().lower() in {"", "unknown"}:
                    soft_candidate["strategy_family"] = "builder_soft_reject"
                if str(soft_candidate.get("setup_variant") or "").strip().lower() in {"", "unknown"}:
                    soft_candidate["setup_variant"] = "softened_builder_path"
                try:
                    attach_contract = getattr(trade_builder, "_attach_softened_candidate_contract", None)
                    if callable(attach_contract):
                        enriched_candidate = attach_contract(soft_candidate, market_data=market_data)
                        if isinstance(enriched_candidate, dict):
                            soft_candidate = enriched_candidate
                except Exception:
                    logger.exception("soft_candidate_contract_enrichment_failed symbol=%s", symbol)
                candidate_reasons = list(reject_gate_reasons or [reject_reason])
                if _should_keep_as_advisory(candidate_reasons):
                    soft_candidate["candidate_status"] = "advisory_only"
                    soft_candidate["execution_status"] = "advisory_only"
                    soft_candidate["eligible_for_execution"] = False
                    soft_candidate["execution_allowed"] = False
                    soft_candidate["execution_ok"] = False
                    soft_candidate["execution_blocked"] = True
                    print(
                        "SOFT_REJECT_WATCHLIST_ONLY",
                        {
                            "symbol": soft_candidate.get("symbol"),
                            "trade_id": soft_candidate.get("trade_id"),
                            "reason": soft_candidate.get("reason") or soft_candidate.get("reject_reason"),
                        },
                    )
                else:
                    conf_floor = float(getattr(cfg, "TRADE_BUILDER_BORDERLINE_CONF_MIN", 0.18) or 0.18)
                    soft_candidate["confidence"] = max(float(soft_candidate.get("confidence") or 0.0), conf_floor)
                    soft_candidate["confidence_final"] = max(float(soft_candidate.get("confidence_final") or 0.0), conf_floor)
                    soft_candidate["soft_reject_seed_confidence"] = float(conf_floor)
                    soft_candidate.setdefault("score_origin", "soft_reject_seed")
                    soft_candidate["rank_score"] = None
                    soft_candidate["opportunity_score"] = None
                    soft_candidate["candidate_status"] = "near_executable"
                    soft_candidate["execution_status"] = "scored"
                    soft_candidate["eligible_for_execution"] = True
                    soft_candidate["execution_allowed"] = True
                    soft_candidate["execution_ok"] = True
                    soft_candidate["execution_blocked"] = False
                    soft_candidate["execution_block_reason"] = None
                    soft_candidate["permission"] = "QUEUE_ONLY"
                    soft_candidate["final_action"] = "QUEUE_ONLY"
                    soft_candidate["readiness"] = "QUEUE_ONLY"
                    source_flags = dict(soft_candidate.get("source_flags") or {})
                    source_flags["soft_blockers"] = [str(code) for code in candidate_reasons if str(code).strip()]
                    soft_candidate["source_flags"] = source_flags
                soft_reject_candidates.append(soft_candidate)
                if _is_structurally_valid_cycle_candidate(soft_candidate):
                    rankable_soft_reject_candidates.append(soft_candidate)
        if soft_reject_candidates:
            for soft_candidate in soft_reject_candidates:
                logger.info(
                    "soft_reject_candidate_ranked symbol=%s trade_id=%s rank_score=%s",
                    soft_candidate.get("symbol"),
                    soft_candidate.get("trade_id"),
                    soft_candidate.get("rank_score"),
                )
            ranked.extend(rankable_soft_reject_candidates)
            dropped_soft_candidates = max(0, len(soft_reject_candidates) - len(rankable_soft_reject_candidates))
            if dropped_soft_candidates > 0:
                logger.info(
                    "soft_reject_unrankable_filtered symbol=%s dropped=%s kept=%s reason=%s",
                    symbol,
                    dropped_soft_candidates,
                    len(rankable_soft_reject_candidates),
                    reject_reason or "trade_builder_reject",
                )
            logger.warning(
                "soft_reject_triggered symbol=%s count=%s reason=%s gate_reasons=%s",
                symbol,
                len(soft_reject_candidates),
                reject_reason or "trade_builder_reject",
                ",".join(reject_gate_reasons),
            )
    return ranked, soft_reject_candidates, reject_reason, reject_gate_reasons


def _apply_latency_soften_to_candidates(
    ranked_candidates: list[dict] | None,
    *,
    latency_action: str | None,
    execution_mode: str,
    symbol: str | None,
) -> tuple[list[dict], int]:
    candidates = list(ranked_candidates or [])
    if not candidates:
        return candidates, 0
    softened: list[dict] = []
    softened_count = 0
    sample_limit = max(0, int(getattr(cfg, "LATENCY_SOFTEN_LOG_SAMPLE_LIMIT", 5) or 5))
    softened_samples: list[dict] = []
    for candidate in candidates:
        confidence_before = _trade_attr(candidate, "confidence_final") or _trade_attr(candidate, "confidence")
        updated = apply_latency_penalty(
            candidate,
            latency_action=latency_action,
            execution_mode=execution_mode,
        )
        confidence_after = _trade_attr(updated, "confidence_final") or _trade_attr(updated, "confidence")
        if len(softened_samples) < sample_limit:
            softened_samples.append(
                {
                    "trade_id": _trade_attr(updated, "trade_id"),
                    "symbol": _trade_attr(updated, "symbol"),
                    "strategy_family": _trade_attr(updated, "strategy_family"),
                    "candidate_status": _trade_attr(updated, "candidate_status"),
                    "execution_status": _trade_attr(updated, "execution_status"),
                    "confidence_before": confidence_before,
                    "confidence_after": confidence_after,
                }
            )
        softened.append(updated)
        softened_count += 1
    logger.info(
        "LATENCY_SOFTEN_APPLIED symbol=%s action=%s count=%s sample=%s",
        symbol,
        latency_action,
        softened_count,
        softened_samples,
    )
    return softened, softened_count


def _min_breadth_target(execution_mode: str | None) -> int:
    target = int(getattr(cfg, "MIN_CANDIDATES_PER_SYMBOL", getattr(cfg, "CANDIDATE_BREADTH_MIN", 0)))
    if str(execution_mode or "").strip().upper() in {"LIVE", "REAL"}:
        target = int(
            getattr(
                cfg,
                "MIN_CANDIDATES_PER_SYMBOL_LIVE",
                getattr(cfg, "CANDIDATE_BREADTH_MIN_LIVE", 0),
            )
        )
    return target


def _build_min_breadth_backfill(
    *,
    ranked_candidates: list[dict],
    soft_reject_candidates: list[dict],
    market_data: dict,
    execution_mode: str | None,
) -> tuple[list[dict], int]:
    if not bool(getattr(cfg, "MIN_BREADTH_FALLBACK_ENABLE", True)):
        return [], _min_breadth_target(execution_mode)
    min_breadth = _min_breadth_target(execution_mode)
    if min_breadth <= 0 or len(ranked_candidates or []) >= min_breadth:
        return [], min_breadth
    needed = max(0, min_breadth - len(ranked_candidates or []))
    seed_candidate = ranked_candidates[0] if ranked_candidates else (soft_reject_candidates[0] if soft_reject_candidates else None)
    fallback_candidates = build_min_breadth_candidates(
        market_data,
        execution_mode=execution_mode,
        seed_candidate=seed_candidate,
        min_needed=needed,
    )
    return fallback_candidates, min_breadth


def _is_recoverable_depth_ws_startup_error(exc: Exception) -> bool:
    text = str(exc or "").strip().lower()
    name = type(exc).__name__.strip().lower()
    if not text and not name:
        return False
    network_markers = (
        "connectionerror",
        "maxretryerror",
        "name resolution",
        "failed to resolve",
        "nodename nor servname provided",
        "temporary failure",
        "timeout",
        "timed out",
        "connection refused",
        "connection reset",
        "ssl",
        "gaierror",
    )
    if any(marker in text for marker in network_markers) or any(marker in name for marker in network_markers):
        return True
    auth_markers = (
        "tokenexception",
        "permissionexception",
        "authenticationerror",
        "invalid api_key",
        "invalid api key",
        "invalid session",
        "profile_failed",
        "missing_user_id",
    )
    return any(marker in text for marker in auth_markers) or any(marker in name for marker in auth_markers)


class Orchestrator:
    def __init__(self, total_capital=100000, poll_interval=30, start_depth_ws_enabled=True):
        """
        Main orchestrator initializing all components
        """
        try:
            auto_clear_risk_halt_if_safe()
        except Exception as exc:
            logger.warning("session_guard_startup_check_error err=%s", exc)

        try:
            ensure_trade_log_exists()
        except Exception as exc:
            logger.warning("startup_trade_log_init_failed err=%s", exc)

        try:
            events_file = logs_dir() / "events.jsonl"
            repair_status = validate_and_repair_event_log(events_file)

            if bool(repair_status.get("repaired")):
                logger.info(
                    "startup_events_log_repaired bytes_trimmed=%d path=%s",
                    int(repair_status.get("bytes_trimmed") or 0),
                    events_file,
                )
        except Exception as exc:
            logger.warning("startup_events_log_repair_failed err=%s", exc)
        try:
            intents_path = Path(
                str(
                    getattr(cfg, "EXECUTION_INTENTS_LOG_PATH", str(logs_dir() / "execution_intents.jsonl"))
                    or str(logs_dir() / "execution_intents.jsonl")
                )
            )
            intents_path.parent.mkdir(parents=True, exist_ok=True)
            intents_path.touch(exist_ok=True)
            for raw_path in (
                getattr(cfg, "DECISION_LOG_PATH", None),
                getattr(cfg, "REJECT_REASONS_LOG_PATH", None),
            ):
                if not raw_path:
                    continue
                p = Path(str(raw_path))
                p.parent.mkdir(parents=True, exist_ok=True)
                p.touch(exist_ok=True)
        except Exception as exc:
            logger.warning("startup_intent_log_init_failed err=%s", exc)
        self._auth_runtime_guard = self._run_preopen_auth_warm_check()
        self.total_capital = total_capital
        self.poll_interval = poll_interval
        try:
            active_flags = cfg.v2_flags_active()
            if active_flags:
                logger.info("v2_flags_active %s", active_flags)
        except Exception as exc:
            logger.debug("v2_flags_active_log_failed err=%s", exc)

        # Unified RiskState
        self.risk_state = RiskState(start_capital=total_capital)

        # Phase C: Trade generation
        self.predictor = TradePredictor()
        self.execution_engine = ExecutionEngine()
        self.execution_router = ExecutionRouter()
        self.gatekeeper = StrategyGatekeeper()
        self.trade_builder = None

        # Start reconciliation daemon + one-shot reconcile
        self._recon_daemon_started = False
        try:
            if bool(getattr(cfg, "ORDER_RECON_DAEMON_ENABLE", True)):
                interval_sec = float(getattr(cfg, "ORDER_RECON_INTERVAL_SEC", 5.0))
                broker_api = getattr(kite_client, "kite", None)
                self.execution_engine.start_reconciliation_daemon(
                    broker_api=broker_api,
                    interval_sec=interval_sec,
                )
                try:
                    self.execution_engine.reconcile_orders_once()
                except Exception as exc:
                    logger.warning("recon_startup_reconcile_failed err=%s", exc)
                self._recon_daemon_started = True
                try:
                    audit_append(
                        {
                            "event": "EXEC_RECONCILIATION_STARTED",
                            "interval_sec": interval_sec,
                            "has_broker_api": bool(broker_api),
                            "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                        }
                    )
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("recon_startup_failed err=%s", exc)

        # Phase B: Risk and execution
        self.risk_engine = RiskEngine(risk_state=self.risk_state)
        self.execution_guard = ExecutionGuard(risk_state=self.risk_state)
        self.portfolio_allocator = PortfolioRiskAllocator()

        # Phase F: Strategy tracking + Auto-retraining
        self.strategy_tracker = StrategyTracker()
        live_strategy_perf_path = logs_dir() / "strategy_perf.json"
        shadow_strategy_perf_path = logs_dir() / "suggestion_strategy_perf.json"
        perf_paths = [str(live_strategy_perf_path)]
        if bool(getattr(cfg, "LIVE_STRATEGY_PERF_SHADOW_FALLBACK_ENABLE", True)):
            perf_paths.append(str(shadow_strategy_perf_path))
        selected_strategy_perf_path = None
        # Backward-compat: older StrategyTracker implementations only expose `load()`.
        if hasattr(self.strategy_tracker, "load_first_available"):
            selected_strategy_perf_path = self.strategy_tracker.load_first_available(perf_paths)
        else:
            for path in perf_paths:
                try:
                    self.strategy_tracker.load(path)
                    selected_strategy_perf_path = str(path)
                    break
                except Exception:
                    continue
        if selected_strategy_perf_path and selected_strategy_perf_path != str(live_strategy_perf_path):
            logger.warning(
                "strategy_perf_shadow_fallback_used primary=%s fallback=%s selected=%s",
                live_strategy_perf_path,
                shadow_strategy_perf_path,
                selected_strategy_perf_path,
            )
        self.trade_builder = TradeBuilder(self.predictor, self.execution_engine, strategy_tracker=self.strategy_tracker)
        self.retrainer = AutoRetrain(self.predictor, risk_state=self.risk_state, strategy_tracker=self.strategy_tracker)
        self.strategy_allocator = StrategyAllocator(self.strategy_tracker, risk_state=self.risk_state)
        self.meta_model = MetaModel() if getattr(cfg, "META_MODEL_ENABLED", False) else None
        self.open_trades = {}
        self.trade_meta = {}
        self.position_states: dict[str, PositionState] = {}
        self.last_trade_sync = 0
        self.blocked_tracker = BlockedTradeTracker()
        self.last_md_by_symbol = {}
        self._latency_guard_soft_ts = {}
        self.best_trade_logged = False
        self.best_trade_by_regime = {}
        self._last_decay_date = None
        self._pilot_check_cache = {"ts": 0, "ok": True, "reasons": []}
        self._decision_traces = []
        self._phase2_active_trade = None
        self.circuit_breaker = CircuitBreaker()
        self.run_lock = RunLock()
        self.exposure_ledger = ExposureLedger(total_capital=total_capital)
        self.decision_store = None
        if getattr(cfg, "DECISION_LOG_ENABLED", False):
            try:
                self.decision_store = DecisionStore(getattr(cfg, "DECISION_DB_PATH", cfg.TRADE_DB_PATH))
            except Exception as exc:
                logger.warning("decision_store_init_failed err=%s", exc)
                self.decision_store = None

        # Portfolio tracking
        self.portfolio = {
            "capital": total_capital,
            "trades": [],
            "daily_loss": 0.0,
            "daily_profit": 0.0,
            "symbol_profit": {},
            "trades_today": 0,
            "equity_high": total_capital
        }
        self.last_trade_time = {}
        self.symbol_epsilon = {}
        self._load_symbol_eps()
        self.loss_streak = {}
        self._pilot_unlock_clean_cycles = 0
        self._pilot_unlock_day = now_ist().date().isoformat()
        self._pilot_unlock_used_day = None
        self._audit_chain_ok = True
        self._audit_chain_status = None
        self._last_global_halt_reason = None
        self._slo_failover_runtime_clear_streak = 0
        self._regime_unstable_streak_by_symbol: dict[str, int] = {}
        self._feed_auto_repair_state: dict[str, dict] = {}
        self._last_suggestion_reliability_eval_ts = 0.0
        self.quote_age_gate_metrics = {
            "stale_index_count": 0,
            "stale_option_count": 0,
        }
        self.regime_monitor = get_regime_monitor()
        self._regime_monitor_enabled = bool(getattr(cfg, "REGIME_MONITOR_ENABLED", True))
        self._regime_monitor_status = {}
        latency_budget = _latency_budget_config(
            execution_mode=str(getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))).upper()
        )
        self.latency_monitor = LatencyMonitor(
            window_size=int(getattr(cfg, "LATENCY_MONITOR_WINDOW_SIZE", 120)),
            max_p95_total_ms=float(latency_budget["max_p95_total_ms"]),
            max_p95_decision_ms=float(latency_budget["max_p95_decision_ms"]),
            sustained_windows=int(latency_budget["sustained_windows"]),
        )
        self.latency_guard = LatencyGuard(
            max_p95_total_ms=float(latency_budget["max_p95_total_ms"]),
            max_p95_decision_ms=float(latency_budget["max_p95_decision_ms"]),
            sustained_windows=int(latency_budget["sustained_windows"]),
            cooldown_sec=float(latency_budget["cooldown_sec"]),
            halt_on_breach=bool(latency_budget["halt_on_breach"]),
        )
        logger.info(
            "latency_budget_config scope=%s total_ms=%.1f decision_ms=%.1f sustained_windows=%d cooldown_sec=%.1f halt_on_breach=%s",
            str(latency_budget["scope"]),
            float(latency_budget["max_p95_total_ms"]),
            float(latency_budget["max_p95_decision_ms"]),
            int(latency_budget["sustained_windows"]),
            float(latency_budget["cooldown_sec"]),
            bool(latency_budget["halt_on_breach"]),
        )
        self.decision_breakers = DecisionCircuitBreakers()
        self._decision_breaker_failure_counters = {"BROKER_REJECT": 0, "NETWORK": 0}
        self._latency_guard_state = {
            "action": ACTION_OK,
            "reason": "init",
            "cooldown_until_ts": 0.0,
            "ts_epoch": now_utc_epoch(),
        }
        self._latency_last_reported_action = ACTION_OK
        self._last_latency_stats = {}
        try:
            ok, status, _ = verify_audit_chain()
            self._audit_chain_ok = ok
            self._audit_chain_status = status
            if not ok:
                try:
                    trigger_audit_chain_fail({"status": status})
                except Exception:
                    pass
        except Exception:
            pass
        self._startup_warmup_rows = self._run_startup_warmup_bootstrap()
        self._start_depth_ws_or_raise(start_depth_ws_enabled=bool(start_depth_ws_enabled))
        self.eps_history = []
        self._load_suggestion_eval()
        self.rl_size_agent = SizeRLAgent(cfg.RL_SIZE_MODEL_PATH) if getattr(cfg, "RL_ENABLED", False) else None

    def _start_depth_ws_or_raise(self, *, start_depth_ws_enabled: bool) -> None:
        runtime_mode = str(getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))).upper()
        dry_run_mode = bool(getattr(cfg, "DRY_RUN", False))
        should_start_depth_ws = bool(start_depth_ws_enabled and runtime_mode in {"LIVE", "PAPER"} and not dry_run_mode)
        if not should_start_depth_ws:
            logger.info(
                "depth_ws_start_skipped mode=%s dry_run=%s enabled=%s",
                runtime_mode,
                dry_run_mode,
                bool(start_depth_ws_enabled),
            )
            return
        try:
            from core.auth import get_kite_credentials

            get_kite_credentials()
        except Exception as exc:
            logger.warning(
                "depth_ws_start_skipped_missing_credentials mode=%s dry_run=%s enabled=%s err=%s",
                runtime_mode,
                dry_run_mode,
                bool(start_depth_ws_enabled),
                exc,
            )
            return
        logger.info(
            "depth_ws_start_attempt mode=%s dry_run=%s enabled=%s",
            runtime_mode,
            dry_run_mode,
            bool(start_depth_ws_enabled),
        )
        try:
            self._start_depth_ws()
        except Exception as exc:
            logger.error("DEPTH_WS_FATAL: %s", exc, exc_info=True)
            if bool(getattr(cfg, "DEPTH_WS_STARTUP_FAIL_OPEN_ON_RECOVERABLE_ERRORS", True)) and _is_recoverable_depth_ws_startup_error(exc):
                logger.warning(
                    "depth_ws_start_failed_recoverable err=%s fail_closed=%s",
                    exc,
                    bool(getattr(cfg, "DEPTH_WS_STARTUP_FAIL_CLOSED", True)),
                )
                return
            fail_closed = bool(getattr(cfg, "DEPTH_WS_STARTUP_FAIL_CLOSED", True))
            if fail_closed:
                raise
            logger.warning("depth_ws_start_failed_fail_open err=%s", exc)

    def _build_decision_snapshot(
        self,
        *,
        market_data: dict,
        trade=None,
        ts_epoch: float | None = None,
    ) -> DecisionSnapshot | None:
        if not bool(getattr(cfg, "USE_DECISION_SNAPSHOT", False)):
            return None
        ts_val = float(ts_epoch if ts_epoch is not None else time.time())
        return build_snapshot(market_data=market_data, trade=trade, now_ts=ts_val)

    def _infer_opt_type(self, trade_id: str | None):
        if not trade_id:
            return None
        tid = trade_id.upper()
        if "-CE-" in tid or tid.endswith("CE") or "CE-" in tid:
            return "CE"
        if "-PE-" in tid or tid.endswith("PE") or "PE-" in tid:
            return "PE"
        return None

    def _match_option_snapshot(self, trade, market_data: dict):
        chain = market_data.get("option_chain", []) or []
        if not chain:
            return None
        # Prefer instrument_token
        tok = getattr(trade, "instrument_token", None)
        if tok:
            for opt in chain:
                if opt.get("instrument_token") == tok:
                    return opt
        # Fallback: strike + type
        opt_type = self._infer_opt_type(getattr(trade, "trade_id", None))
        for opt in chain:
            if opt.get("strike") == getattr(trade, "strike", None):
                if opt_type and opt.get("type") != opt_type:
                    continue
                return opt
        return None

    def _apply_exit_state_patch(self, trade, meta: dict, state_patch: dict, current_price: float):
        patch = dict(state_patch or {})
        if not patch:
            return meta
        prev_sl = float(meta.get("current_sl", meta.get("trail_stop", trade.stop_loss)) or trade.stop_loss)
        prev_tp = float(meta.get("current_tp", trade.target) or trade.target)
        prev_phase = str(meta.get("exit_intel_phase") or "INIT")
        meta.update(patch)
        if "current_sl" in patch and patch.get("current_sl") is not None:
            meta["trail_stop"] = float(patch.get("current_sl"))
        elif "trail_stop" in meta and meta.get("trail_stop") is not None:
            meta["current_sl"] = float(meta.get("trail_stop"))
        if "current_tp" not in meta:
            meta["current_tp"] = float(trade.target)
        self.trade_meta[trade.trade_id] = meta

        next_sl = float(meta.get("current_sl", prev_sl) or prev_sl)
        next_tp = float(meta.get("current_tp", prev_tp) or prev_tp)
        next_phase = str(meta.get("exit_intel_phase") or prev_phase)
        sl_changed = abs(next_sl - prev_sl) > 1e-9
        tp_changed = abs(next_tp - prev_tp) > 1e-9
        if sl_changed:
            meta["trail_updates"] = int(meta.get("trail_updates", 0) or 0) + 1
            try:
                insert_trail_event(trade.trade_id, float(next_sl), float(current_price), "EXIT_INTEL_SL_UPDATE")
            except Exception:
                pass
        try:
            update_trailing_state(
                trade.trade_id,
                trailing_enabled=bool(meta.get("trailing_enabled", True)),
                trailing_method=str(meta.get("trailing_method", "EXIT_INTEL")),
                trailing_atr_mult=float(meta.get("trailing_atr_mult", getattr(cfg, "TRAILING_STOP_ATR_MULT", 0.8))),
                trail_stop_init=float(meta.get("trail_stop_init", trade.stop_loss)),
                trail_stop_last=float(next_sl),
                trail_updates=int(meta.get("trail_updates", 0) or 0),
            )
        except Exception:
            pass
        try:
            audit_append(
                {
                    "event": "EXIT_INTEL_STATE_PATCH",
                    "trade_id": trade.trade_id,
                    "symbol": trade.symbol,
                    "phase_before": prev_phase,
                    "phase_after": next_phase,
                    "sl_before": prev_sl,
                    "sl_after": next_sl,
                    "tp_before": prev_tp,
                    "tp_after": next_tp,
                    "sl_changed": sl_changed,
                    "tp_changed": tp_changed,
                    "reason_codes": list(meta.get("reason_codes") or []),
                    "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                }
            )
        except Exception:
            pass
        return meta

    def _emit_exit_intent(self, trade, decision, market_data: dict, current_price: float):
        intent_payload = {
            "intent_type": "EXIT_INTELLIGENCE",
            "trade_id": trade.trade_id,
            "symbol": trade.symbol,
            "instrument": trade.instrument,
            "action": decision.action.value,
            "exit_qty_units": int(decision.exit_qty_units),
            "current_price": float(current_price),
            "reason_codes": list(decision.reason_codes),
            "before_plan": dict(decision.before_plan),
            "after_plan": dict(decision.after_plan),
            "safe_mode": bool(decision.safe_mode),
            "feed_state": market_data.get("feed_state")
            or ((market_data.get("feed_health") or {}).get("state") if isinstance(market_data.get("feed_health"), dict) else None),
            "ts_epoch": now_utc_epoch(),
        }
        preview_intent_id = self.execution_engine.build_exit_intent_id(intent_payload)
        existing_meta = self.trade_meta.get(trade.trade_id, {})
        if str(existing_meta.get("last_exit_intent_id") or "") == preview_intent_id:
            ack = {
                "accepted": True,
                "duplicate": True,
                "intent_id": preview_intent_id,
                "ts_epoch": now_utc_epoch(),
                "errors": [],
            }
            try:
                audit_append(
                    {
                        "event": "EXIT_INTEL_DUPLICATE_INTENT_SKIPPED",
                        "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                        "intent_id": preview_intent_id,
                        "trade_id": trade.trade_id,
                    }
                )
            except Exception:
                pass
            return ack, intent_payload
        ack = self.execution_engine.apply_exit_intent(intent_payload)
        try:
            audit_append(
                {
                    "event": "EXIT_INTEL_DECISION",
                    "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                    "intent": intent_payload,
                    "ack": ack,
                }
            )
        except Exception:
            pass
        return ack, intent_payload

    def _write_exit_intel_state(self, trade, meta: dict, current_price: float):
        try:
            path = logs_dir() / "exit_intel_state.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "ts_epoch": now_utc_epoch(),
                "trade_id": trade.trade_id,
                "symbol": trade.symbol,
                "instrument": trade.instrument,
                "status": getattr(trade, "status", None),
                "current_price": float(current_price),
                "best_price_seen": meta.get("best_price_seen"),
                "best_price_ts": meta.get("best_price_ts"),
                "current_sl": meta.get("current_sl"),
                "current_tp": meta.get("current_tp"),
                "exit_intel_phase": meta.get("exit_intel_phase"),
                "exit_intel_action": meta.get("exit_intel_action"),
                "stall_counter": meta.get("stall_counter"),
                "last_action_ts": meta.get("last_action_ts"),
                "reason_codes": list(meta.get("reason_codes") or []),
                "remaining_qty_units": int(meta.get("remaining_qty_units", 0) or 0),
            }
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
        except Exception:
            pass

    def _position_state_path(self, trade_id: str) -> Path:
        base = Path(str(getattr(cfg, "POSITION_STATE_STORE_PATH", "") or "").strip())
        if not str(base):
            base = logs_dir() / "position_state"
        return base / f"{str(trade_id)}.json"

    def _persist_position_state(self, state: PositionState) -> None:
        if not bool(getattr(cfg, "POSITION_STATE_ENGINE_ENABLE", True)):
            return
        if not bool(getattr(cfg, "POSITION_STATE_PERSIST_EVERY_CYCLE", True)):
            return
        if not state.trade_id:
            return
        try:
            save_position_state(self._position_state_path(state.trade_id), state)
        except Exception as exc:
            logger.warning("position_state_persist_failed trade_id=%s err=%s", state.trade_id, exc)

    def _load_position_state(self, trade_id: str) -> PositionState | None:
        if not bool(getattr(cfg, "POSITION_STATE_ENGINE_ENABLE", True)):
            return None
        key = str(trade_id or "")
        if not key:
            return None
        cached = self.position_states.get(key)
        if cached is not None:
            return cached
        loaded = load_position_state(self._position_state_path(key))
        if loaded is not None:
            self.position_states[key] = loaded
        return loaded

    def _initialize_position_state(self, trade, meta: dict, now_ts: float) -> PositionState | None:
        if not bool(getattr(cfg, "POSITION_STATE_ENGINE_ENABLE", True)):
            return None
        trade_id = str(getattr(trade, "trade_id", "") or "")
        if not trade_id:
            return None
        existing = self._load_position_state(trade_id)
        if existing is not None:
            return existing
        try:
            fill_payload = {
                "trade_id": trade_id,
                "fill_price": float(meta.get("entry_price", getattr(trade, "entry_price", 0.0)) or getattr(trade, "entry_price", 0.0)),
                "qty": int(meta.get("remaining_qty_units", getattr(trade, "qty_units", getattr(trade, "qty", 1))) or 1),
            }
            candidate_payload = {
                "trade_id": trade_id,
                "symbol": getattr(trade, "symbol", ""),
                "side": getattr(trade, "side", "BUY"),
                "selected_playbook": (
                    meta.get("selected_playbook")
                    or getattr(trade, "selected_playbook", None)
                    or getattr(trade, "decision_playbook", None)
                    or "none"
                ),
                "entry": getattr(trade, "entry_price", None),
                "execution_entry": getattr(trade, "entry_price", None),
                "stop_loss": getattr(trade, "stop_loss", None),
                "target": getattr(trade, "target", None),
                "setup_score": getattr(trade, "setup_score", None),
                "trigger_score": getattr(trade, "trigger_score", None),
                "entry_quality_score": getattr(trade, "entry_quality_score", None),
                "execution_quality_score": meta.get("execution_quality_score"),
                "qty": fill_payload["qty"],
            }
            state = initialize_position_state(fill_payload, candidate_payload, now_ts=now_ts)
            self.position_states[trade_id] = state
            self._persist_position_state(state)
            return state
        except Exception as exc:
            logger.warning("position_state_initialize_failed trade_id=%s err=%s", trade_id, exc)
            return None

    def _refresh_position_state(self, trade, meta: dict, market: dict, now_ts: float) -> PositionState | None:
        state = self._initialize_position_state(trade, meta, now_ts=now_ts)
        if state is None:
            return None
        try:
            state = update_position_state(state, market, now_ts=now_ts)
            state.telemetry.update(
                {
                    "playbook": state.playbook,
                    "status": state.status,
                    "tp1_done": bool(state.tp1_done),
                    "breakeven_done": bool(state.breakeven_done),
                    "trailing_active": bool(state.trailing_active),
                    "mfe_r": float(state.mfe_r),
                    "mae_r": float(state.mae_r),
                    "current_stop": float(state.current_stop),
                    "remaining_qty": int(state.remaining_qty),
                }
            )
            self.position_states[state.trade_id] = state
            if bool(getattr(cfg, "POSITION_STATE_EXIT_MANAGER_ENABLE", True)):
                exit_action = evaluate_exit_action(position_state_to_dict(state), market)
                state.telemetry["exit_manager_last_action"] = str(exit_action.action)
                state.telemetry["exit_manager_last_reason"] = str(exit_action.reason)
                state.telemetry["exit_manager_last_telemetry"] = dict(exit_action.telemetry or {})
                meta["position_state_advisory_action"] = str(exit_action.action)
                meta["position_state_advisory_reason"] = str(exit_action.reason)
                mode = str(getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM").strip().upper()
                allow_authoritative = mode in {"SIM", "PAPER", "BACKTEST"}
                if bool(getattr(cfg, "POSITION_STATE_EXIT_MANAGER_AUTHORITATIVE", False)) and allow_authoritative:
                    state = apply_position_exit_action(
                        state,
                        {
                            "action": str(exit_action.action),
                            "new_stop": exit_action.new_stop,
                            "exit_fraction": float(exit_action.exit_fraction),
                            "reason": str(exit_action.reason),
                        },
                        now_ts=now_ts,
                    )
                    self.position_states[state.trade_id] = state
                elif bool(getattr(cfg, "POSITION_STATE_EXIT_MANAGER_AUTHORITATIVE", False)) and not allow_authoritative:
                    state.telemetry["exit_manager_authoritative_blocked"] = "live_mode_not_allowed"
            self._persist_position_state(state)
            return state
        except Exception as exc:
            logger.warning("position_state_refresh_failed trade_id=%s err=%s", getattr(trade, "trade_id", None), exc)
            return state

    def _append_gate_status(self, market_data: dict, gate_allowed, gate_family, gate_reasons, stage: str):
        symbol = str((market_data or {}).get("symbol") or "")
        payload_min = {
            "event_type": str((market_data or {}).get("event_type") or "gate_status"),
            "symbol": symbol,
            "decision_stage": str((market_data or {}).get("decision_stage") or stage or ""),
            "cycle_id": (market_data or {}).get("cycle_id"),
            "ts_epoch": (market_data or {}).get("timestamp") or (market_data or {}).get("ts_epoch"),
        }
        try:
            seen = getattr(self, "_gate_status_cycle_seen", None)
            if isinstance(seen, set):
                key = (symbol, str(stage))
                if key in seen:
                    return
                seen.add(key)
            record = build_gate_status_record(
                market_data=market_data,
                gate_allowed=gate_allowed,
                gate_family=gate_family,
                gate_reasons=gate_reasons,
                stage=stage,
            )
            write_ok = append_gate_status(record, desk_id=getattr(cfg, "DESK_ID", "DEFAULT"))
            if write_ok is False:
                audit_append(
                    {
                        "event": "GATE_STATUS_WRITE_FAILED",
                        "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                        "symbol": symbol,
                        "stage": str(stage),
                        "gate_allowed": bool(gate_allowed),
                        "gate_family": gate_family,
                        "gate_reasons": list(gate_reasons or []),
                    }
                )
                append_decision_write_error(
                    desk_id=getattr(cfg, "DESK_ID", "DEFAULT"),
                    stream="gate_status",
                    exc=RuntimeError("append_gate_status_returned_false"),
                    payload=payload_min,
                    context={
                        "stage": str(stage),
                        "gate_allowed": bool(gate_allowed),
                        "gate_family": gate_family,
                    },
                )
        except Exception as exc:
            try:
                append_decision_write_error(
                    desk_id=getattr(cfg, "DESK_ID", "DEFAULT"),
                    stream="gate_status",
                    exc=exc,
                    payload=payload_min,
                    context={
                        "stage": str(stage),
                        "gate_allowed": bool(gate_allowed),
                        "gate_family": gate_family,
                    },
                )
            except Exception:
                pass
            logger.warning("gate_status_write_failed err=%s:%s", type(exc).__name__, exc)

    def _log_cycle_symbol_summary(
        self,
        *,
        symbol: str,
        snapshot_ok: bool,
        gate_allowed: bool,
        quote_age_gate_pass,
        trade_build_attempted: bool,
        trade_generated: bool,
        permission,
        final_action,
        reject_reason,
        top_gate_reasons,
    ) -> None:
        try:
            seen = getattr(self, "_decision_summary_cycle_seen", None)
            if isinstance(seen, set):
                key = (str(symbol or "").upper(), str(getattr(self, "_gate_status_cycle_id", "") or ""))
                if key in seen:
                    return
                seen.add(key)
            logger.info(
                "cycle_symbol_decision_summary symbol=%s cycle_id=%s snapshot_ok=%s gate_allowed=%s quote_age_gate_pass=%s trade_build_attempted=%s trade_generated=%s permission=%s final_action=%s reject_reason=%s top_gate_reasons=%s",
                symbol,
                str(getattr(self, "_gate_status_cycle_id", "") or ""),
                bool(snapshot_ok),
                bool(gate_allowed),
                quote_age_gate_pass,
                bool(trade_build_attempted),
                bool(trade_generated),
                permission,
                final_action,
                reject_reason,
                json.dumps(list(top_gate_reasons or [])[:5], separators=(",", ":")),
            )
        except Exception:
            pass

    def _emit_global_halt_events(self, reason: str):
        reason = str(reason or "UNKNOWN_HALT")
        if reason == str(getattr(self, "_last_global_halt_reason", "")):
            return
        self._last_global_halt_reason = reason
        veto_reason = reason.lower()
        try:
            event = self._build_decision_event(
                None,
                {"symbol": "GLOBAL"},
                gatekeeper_allowed=False,
                veto_reasons=[veto_reason],
            )
            self._log_decision_safe(event)
        except Exception:
            pass
        try:
            audit_append(
                {
                    "event": "GLOBAL_HALT",
                    "reason": reason,
                    "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                }
            )
        except Exception:
            pass
        if reason == "KILL_SWITCH":
            try:
                create_incident("SEV1", "KILL_SWITCH", {"desk_id": getattr(cfg, "DESK_ID", "DEFAULT")})
            except Exception:
                pass

    def _maybe_auto_clear_runtime_slo_failover_halt(self) -> None:
        if not bool(getattr(cfg, "AUTO_CLEAR_SLO_FAILOVER_RUNTIME_ENABLE", True)):
            self._slo_failover_runtime_clear_streak = 0
            return
        try:
            halt_state = risk_halt.load_halt() or {}
        except Exception:
            halt_state = {}
        halted = bool(halt_state.get("halted", False))
        reason = str(halt_state.get("reason") or "").strip().lower()
        if (not halted) or reason != "slo_failover":
            self._slo_failover_runtime_clear_streak = 0
            return
        max_open_positions = max(
            0,
            int(getattr(cfg, "AUTO_CLEAR_SLO_FAILOVER_RUNTIME_MAX_OPEN_POSITIONS", 0) or 0),
        )
        try:
            open_positions_count = len(fetch_open_positions_dict(limit=5000))
        except Exception:
            open_positions_count = 10_000
        if open_positions_count > max_open_positions:
            self._slo_failover_runtime_clear_streak = 0
            logger.warning(
                "slo_failover_runtime_clear_blocked_open_positions open_positions=%s max_allowed=%s",
                open_positions_count,
                max_open_positions,
            )
            return
        try:
            slo_status = evaluate_slo_status(enforce_failover=False)
        except Exception as exc:
            self._slo_failover_runtime_clear_streak = 0
            logger.warning("slo_failover_runtime_clear_eval_failed err=%s", exc)
            return
        reasons = [str(r or "").strip().upper() for r in list(slo_status.get("reasons") or []) if str(r or "").strip()]
        allowed_reasons = {
            str(code or "").strip().upper()
            for code in list(getattr(cfg, "AUTO_CLEAR_SLO_FAILOVER_RUNTIME_ALLOWED_REASONS", []) or [])
            if str(code or "").strip()
        }
        disallowed_reasons = [code for code in reasons if code not in allowed_reasons]
        auth_payload = slo_status.get("auth") if isinstance(slo_status.get("auth"), dict) else {}
        auth_ok = bool(auth_payload.get("ok", slo_status.get("ok", False)))
        healthy = bool(auth_ok) and (not disallowed_reasons)
        if not healthy:
            self._slo_failover_runtime_clear_streak = 0
            logger.warning(
                "slo_failover_runtime_clear_waiting status=%s reasons=%s warnings=%s",
                str(slo_status.get("status") or "UNKNOWN"),
                ",".join(reasons or ["none"]),
                ",".join(list(slo_status.get("warnings") or []) or ["none"]),
            )
            return
        self._slo_failover_runtime_clear_streak = int(self._slo_failover_runtime_clear_streak or 0) + 1
        required_streak = max(
            1,
            int(getattr(cfg, "AUTO_CLEAR_SLO_FAILOVER_RUNTIME_OK_STREAK", 2) or 2),
        )
        logger.warning(
            "slo_failover_runtime_clear_progress ok_streak=%s required=%s reasons=%s allowed_reasons=%s",
            self._slo_failover_runtime_clear_streak,
            required_streak,
            ",".join(reasons or ["none"]),
            ",".join(sorted(allowed_reasons) or ["none"]),
        )
        if self._slo_failover_runtime_clear_streak < required_streak:
            return
        try:
            risk_halt.clear_halt()
            self._slo_failover_runtime_clear_streak = 0
            logger.warning(
                "slo_failover_runtime_halt_cleared open_positions=%s status=%s",
                open_positions_count,
                str(slo_status.get("status") or "UNKNOWN"),
            )
            try:
                audit_append(
                    {
                        "event": "SLO_FAILOVER_RUNTIME_HALT_CLEARED",
                        "open_positions_count": int(open_positions_count),
                        "required_ok_streak": int(required_streak),
                        "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                    }
                )
            except Exception:
                pass
        except Exception as exc:
            logger.warning("slo_failover_runtime_halt_clear_failed err=%s", exc)

    def _latency_guard_action(self) -> str:
        state = getattr(self, "_latency_guard_state", {}) or {}
        return str(state.get("action") or ACTION_OK).upper()

    def _latency_blocks_entries(self) -> bool:
        return self._latency_guard_action() in {
            ACTION_COOLDOWN,
            ACTION_DEGRADE_EXIT_ONLY,
            ACTION_HALT_ALL,
        }

    def _latency_blocks_non_emergency_exits(self) -> bool:
        return self._latency_guard_action() == ACTION_HALT_ALL

    def _evaluate_latency_guard(self, *, market_open: bool, monitor_stats: dict) -> dict:
        result = self.latency_guard.evaluate(
            monitor_stats=monitor_stats or {},
            market_open=bool(market_open),
            now_ts=now_utc_epoch(),
        )
        now_epoch = now_utc_epoch()
        state = {
            "action": str(result.action),
            "reason": str(result.reason),
            "cooldown_until_ts": float(result.cooldown_until_ts or 0.0),
            "ts_epoch": now_epoch,
            "blocks_new_entries": bool(result.blocks_new_entries),
            "blocks_non_emergency_exits": bool(result.blocks_non_emergency_exits),
            "last_ok_at": now_epoch if str(result.action).upper() == ACTION_OK else getattr(self, "_latency_guard_state", {}).get("last_ok_at"),
            "last_bad_at": now_epoch if str(result.action).upper() != ACTION_OK else getattr(self, "_latency_guard_state", {}).get("last_bad_at"),
        }
        state.update(_latency_guard_metric_context(state, result.stats if isinstance(result.stats, dict) else {}))
        previous_action = str(getattr(self, "_latency_last_reported_action", ACTION_OK) or ACTION_OK).upper()
        next_action = str(state.get("action") or ACTION_OK).upper()
        self._latency_guard_state = state
        self._latency_last_reported_action = next_action
        if previous_action == next_action:
            return state
        payload = {
            "action": next_action,
            "previous_action": previous_action,
            "reason": state.get("reason"),
            "market_open": bool(market_open),
            "monitor_stats": monitor_stats or {},
            "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
        }
        try:
            append_runtime_event("latency_breach" if next_action != ACTION_OK else "latency_recovered", payload)
        except Exception:
            pass
        if next_action in {ACTION_DEGRADE_EXIT_ONLY, ACTION_HALT_ALL}:
            sev = "SEV1" if next_action == ACTION_HALT_ALL else "SEV2"
            try:
                create_incident(sev, "LATENCY_BREACH", payload)
            except Exception:
                pass
        if next_action == ACTION_HALT_ALL and bool(getattr(cfg, "HALT_ON_BREACH", True)):
            try:
                self._emit_global_halt_events("LATENCY_BREACH")
            except Exception:
                pass
        return state

    def _allocator_seed_date_iso(self, market_data: dict) -> str:
        ts_val = None
        if isinstance(market_data, dict):
            ts_val = market_data.get("timestamp")
        try:
            if ts_val is not None:
                return datetime.fromtimestamp(float(ts_val)).date().isoformat()
        except Exception:
            pass
        return now_ist().date().isoformat()

    def _allocator_context_seed(self, market_data: dict, symbol: str, strategy: str) -> str | None:
        ctx_payload = {}
        if isinstance(market_data, dict) and isinstance(market_data.get("market_context"), dict):
            ctx_payload.update(dict(market_data.get("market_context") or {}))
        if "execution_mode" not in ctx_payload:
            ctx_payload["execution_mode"] = getattr(cfg, "EXECUTION_MODE", "SIM")
        if "market_open" not in ctx_payload and isinstance(market_data, dict):
            if "market_open" in market_data:
                ctx_payload["market_open"] = market_data.get("market_open")
        if "segment" not in ctx_payload:
            if isinstance(market_data, dict) and market_data.get("segment"):
                ctx_payload["segment"] = market_data.get("segment")
            else:
                ctx_payload["segment"] = getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO")
        market_ctx = derive_market_context(ctx_payload)
        if market_ctx.mode not in {"PAPER", "SIM", "OFFHOURS"}:
            return None
        seed_day = self._allocator_seed_date_iso(market_data)
        return f"{seed_day}|{str(symbol)}|{str(strategy)}"

    def _build_cycle_market_data(self, market_data_list: list[dict] | None) -> list[dict]:
        """
        Build one canonical snapshot per symbol per cycle.
        Mutable snapshots are returned for execution flow.
        Immutable snapshots are cached for gatekeeper/logging.
        """
        if not isinstance(market_data_list, list):
            self._cycle_market_snapshot_by_symbol = {}
            return []
        feed_runtime_payload, _feed_runtime_path = _read_latest_feed_runtime_payload()
        feed_runtime_ts = _safe_float(
            feed_runtime_payload.get("ts_epoch")
            or feed_runtime_payload.get("last_ws_tick_epoch")
            or feed_runtime_payload.get("last_db_tick_epoch")
        )
        feed_runtime_ws_connected = feed_runtime_payload.get("ws_connected")
        feed_runtime_subscribed_total = int(
            feed_runtime_payload.get("subscribed_option_tokens_count")
            or feed_runtime_payload.get("subscribed_tokens_count")
            or 0
        )
        feed_runtime_last_tick_ts = _safe_float(
            feed_runtime_payload.get("last_ws_tick_epoch")
            or feed_runtime_payload.get("last_db_tick_epoch")
            or feed_runtime_payload.get("last_tick_epoch")
        )
        feed_runtime_last_tick_age = _safe_float(
            feed_runtime_payload.get("last_tick_age_sec")
            or feed_runtime_payload.get("last_db_tick_age_sec")
        )
        feed_runtime_state = str(feed_runtime_payload.get("runtime_state") or "").strip().upper()
        tick_ts_by_symbol = (
            dict(feed_runtime_payload.get("last_option_tick_ts_by_symbol") or {})
            if isinstance(feed_runtime_payload.get("last_option_tick_ts_by_symbol"), dict)
            else {}
        )
        tick_age_by_symbol = (
            dict(feed_runtime_payload.get("option_last_tick_age_by_symbol") or {})
            if isinstance(feed_runtime_payload.get("option_last_tick_age_by_symbol"), dict)
            else {}
        )
        block_reason_by_symbol = (
            dict(feed_runtime_payload.get("option_feed_block_reason_by_symbol") or {})
            if isinstance(feed_runtime_payload.get("option_feed_block_reason_by_symbol"), dict)
            else {}
        )
        subscribed_count_by_symbol = (
            dict(feed_runtime_payload.get("option_tokens_subscribed_count_by_symbol") or {})
            if isinstance(feed_runtime_payload.get("option_tokens_subscribed_count_by_symbol"), dict)
            else {}
        )
        per_symbol: dict[str, dict] = {}
        symbol_order: list[str] = []
        for raw in market_data_list:
            if not isinstance(raw, dict):
                continue
            if str(raw.get("instrument", "OPT")).upper() != "OPT":
                continue
            symbol = str(raw.get("symbol") or "").upper()
            if not symbol:
                continue
            try:
                snap = copy.deepcopy(raw)
            except Exception:
                snap = dict(raw)
            cycle_id = getattr(self, "_gate_status_cycle_id", None)
            if cycle_id is not None:
                snap["cycle_id"] = cycle_id
            if symbol:
                symbol_tick_ts = _safe_float(tick_ts_by_symbol.get(symbol))
                symbol_tick_age = _safe_float(tick_age_by_symbol.get(symbol))
                if symbol_tick_ts is None:
                    symbol_tick_ts = feed_runtime_last_tick_ts
                if symbol_tick_age is None and symbol_tick_ts is not None:
                    try:
                        symbol_tick_age = max(0.0, float(now_utc_epoch()) - float(symbol_tick_ts))
                    except Exception:
                        symbol_tick_age = None
                if symbol_tick_age is None:
                    symbol_tick_age = feed_runtime_last_tick_age
                symbol_subscribed = int(
                    subscribed_count_by_symbol.get(symbol)
                    or feed_runtime_subscribed_total
                    or 0
                )
                block_reason = str(block_reason_by_symbol.get(symbol) or "").strip().upper()
                if feed_runtime_ws_connected is not None:
                    snap["ws_connected"] = bool(feed_runtime_ws_connected)
                snap["subscribed_option_tokens_count"] = int(symbol_subscribed)
                if symbol_tick_ts is not None:
                    snap["latest_option_tick_ts"] = float(symbol_tick_ts)
                if symbol_tick_age is not None:
                    snap["latest_option_tick_age_sec"] = float(symbol_tick_age)
                if feed_runtime_ts is not None:
                    snap["feed_timestamp_epoch"] = float(feed_runtime_ts)
                    if _safe_float(snap.get("timestamp_epoch")) is None and symbol_tick_ts is not None:
                        snap["timestamp_epoch"] = float(symbol_tick_ts)
                if block_reason:
                    snap["option_feed_block_reason"] = block_reason
                feed_health = dict(snap.get("feed_health") or {}) if isinstance(snap.get("feed_health"), dict) else {}
                if feed_runtime_state:
                    feed_health["runtime_state"] = feed_runtime_state
                if feed_runtime_ws_connected is not None:
                    feed_health["ws_connected"] = bool(feed_runtime_ws_connected)
                feed_health["subscribed_option_tokens_count"] = int(symbol_subscribed)
                if symbol_tick_ts is not None:
                    feed_health["latest_option_tick_ts"] = float(symbol_tick_ts)
                if symbol_tick_age is not None:
                    feed_health["latest_option_tick_age_sec"] = float(symbol_tick_age)
                if feed_runtime_ts is not None:
                    feed_health["ts_epoch"] = float(feed_runtime_ts)
                if block_reason:
                    feed_health["option_feed_block_reason"] = block_reason
                    if block_reason != "OK":
                        feed_health["is_fresh"] = False
                snap["feed_health"] = feed_health
            # Keep the latest snapshot for this symbol in the cycle.
            try:
                ts_epoch = float(snap.get("timestamp") or 0.0)
            except Exception:
                ts_epoch = 0.0
            prev = per_symbol.get(symbol)
            if prev is None:
                per_symbol[symbol] = snap
                symbol_order.append(symbol)
                continue
            try:
                prev_ts = float(prev.get("timestamp") or 0.0)
            except Exception:
                prev_ts = 0.0
            if ts_epoch >= prev_ts:
                per_symbol[symbol] = snap
        cycle_rows = [per_symbol[sym] for sym in symbol_order if sym in per_symbol]
        immutable_map: dict[str, MappingProxyType] = {}
        for row in cycle_rows:
            sym = str(row.get("symbol") or "").upper()
            if not sym:
                continue
            try:
                immutable_map[sym] = MappingProxyType(copy.deepcopy(row))
            except Exception:
                immutable_map[sym] = MappingProxyType(dict(row))
        self._cycle_market_snapshot_by_symbol = immutable_map
        return cycle_rows

    def _apply_cycle_indicator_readiness_truth(
        self,
        market_data_list: list[dict] | None,
        indicator_report,
    ) -> None:
        if not isinstance(market_data_list, list):
            return
        decisions_by_symbol: dict[str, Any] = {}
        try:
            if indicator_report is not None:
                for decision in getattr(indicator_report, "decisions", ()) or ():
                    symbol = str(getattr(decision, "symbol", "") or "").strip().upper()
                    if symbol:
                        decisions_by_symbol[symbol] = decision
        except Exception:
            decisions_by_symbol = {}
        if not decisions_by_symbol:
            return

        refreshed_snapshots: dict[str, MappingProxyType] = {}
        for row in market_data_list:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            decision = decisions_by_symbol.get(symbol)
            if decision is None:
                continue
            try:
                row["indicator_source"] = getattr(decision, "source", None)
                row["indicator_readiness_source"] = getattr(decision, "source", None)
                row["indicator_last_update_epoch"] = getattr(decision, "indicator_last_update_epoch", None)
                row["indicators_age_sec"] = getattr(decision, "indicators_age_sec", None)
                row["indicator_age_sec"] = getattr(decision, "indicators_age_sec", None)
                row["indicator_missing_inputs"] = list(getattr(decision, "indicator_missing_inputs", ()) or ())
                row["compute_indicators_error"] = getattr(decision, "compute_indicators_error", "")
                row["indicators_ok"] = bool(getattr(decision, "indicators_ok", False))
                row["indicator_inputs_ok"] = bool(getattr(decision, "indicator_inputs_ok", False))
                row["indicator_readiness_ready"] = bool(getattr(decision, "ready", False))
                row["indicator_readiness_reason"] = (
                    "ready" if bool(getattr(decision, "ready", False)) else str(getattr(decision, "decision_gate_reason", "") or "unknown")
                )
                row["indicator_readiness_blockers"] = list(getattr(decision, "blockers", ()) or ())
            except Exception:
                pass
            try:
                refreshed_snapshots[symbol] = MappingProxyType(copy.deepcopy(row))
            except Exception:
                refreshed_snapshots[symbol] = MappingProxyType(dict(row))
        if refreshed_snapshots:
            current_snapshots = getattr(self, "_cycle_market_snapshot_by_symbol", None)
            if isinstance(current_snapshots, dict):
                current_snapshots.update(refreshed_snapshots)
            else:
                self._cycle_market_snapshot_by_symbol = refreshed_snapshots

    def _run_v2_shadow_pipeline(self, market_data_list: list[dict] | None) -> None:
        try:
            run_v2_pipeline(market_data_list, now_ts=time.time())
        except Exception as exc:
            logger.exception("v2_shadow_pipeline_failed err=%s", exc)

    def _run_pro_shadow_pipeline(self, market_data_list: list[dict] | None) -> None:
        if not bool(getattr(cfg, "ENABLE_PRO_STRATEGY_SHADOW", False)):
            return

        loop_id = str(getattr(self, "_gate_status_cycle_id", "") or "")
        try:
            existing = getattr(self, "_pro_shadow_process", None)
            if existing is not None:
                try:
                    alive = bool(existing.is_alive())
                except Exception:
                    alive = False
                started_at = float(getattr(self, "_pro_shadow_process_started_at", 0.0) or 0.0)
                ttl_sec = max(
                    0.0,
                    float(
                        getattr(
                            cfg,
                            "PRO_STRATEGY_SHADOW_WORKER_TTL_SEC",
                            getattr(cfg, "PRO_STRATEGY_SHADOW_THREAD_TTL_SEC", 30.0),
                        )
                    ),
                )
                age_sec = max(0.0, time.time() - started_at) if started_at > 0.0 else 0.0
                if alive:
                    if age_sec <= ttl_sec:
                        logger.info(
                            "pro_shadow_pipeline_skipped reason=worker_active loop_id=%s age_sec=%.3f ttl_sec=%.3f",
                            loop_id,
                            age_sec,
                            ttl_sec,
                        )
                        return
                    logger.warning(
                        "pro_shadow_pipeline_worker_stale loop_id=%s age_sec=%.3f ttl_sec=%.3f",
                        loop_id,
                        age_sec,
                        ttl_sec,
                    )
                    try:
                        existing.terminate()
                    except Exception as exc:
                        logger.warning("pro_shadow_pipeline_worker_terminate_failed err=%s", exc)
                    try:
                        existing.join(timeout=2.0)
                    except Exception as exc:
                        logger.warning("pro_shadow_pipeline_worker_join_failed err=%s", exc)
                else:
                    try:
                        existing.join(timeout=0.0)
                    except Exception:
                        pass
                exitcode = getattr(existing, "exitcode", None)
                if exitcode not in (None, 0):
                    logger.warning(
                        "pro_shadow_pipeline_worker_exitcode loop_id=%s exitcode=%s age_sec=%.3f",
                        loop_id,
                        exitcode,
                        age_sec,
                    )
                try:
                    self._pro_shadow_process = None
                    self._pro_shadow_process_started_at = 0.0
                except Exception:
                    pass
        except Exception:
            pass
        try:
            started_at = time.time()
            worker = _create_pro_shadow_process(_sanitize_pro_shadow_rows(market_data_list), loop_id, started_at)
            self._pro_shadow_process = worker
            self._pro_shadow_process_started_at = started_at
            worker.start()
        except Exception as exc:
            logger.exception("pro_shadow_pipeline_dispatch_failed err=%s", exc)
            try:
                self._pro_shadow_process = None
                self._pro_shadow_process_started_at = 0.0
            except Exception:
                pass

    def _immutable_cycle_snapshot(self, market_data: dict):
        symbol = str((market_data or {}).get("symbol") or "").upper()
        snap_map = getattr(self, "_cycle_market_snapshot_by_symbol", None)
        if isinstance(snap_map, dict) and symbol in snap_map:
            return snap_map[symbol]
        try:
            return MappingProxyType(copy.deepcopy(market_data or {}))
        except Exception:
            return MappingProxyType(dict(market_data or {}))

    def _regime_unstable_block_after(self, market_data: dict) -> int:
        ctx_payload = dict(market_data.get("market_context") or {}) if isinstance(market_data.get("market_context"), dict) else {}
        if "execution_mode" not in ctx_payload:
            ctx_payload["execution_mode"] = market_data.get("execution_mode")
        if "market_open" not in ctx_payload and ("market_open" in market_data):
            ctx_payload["market_open"] = market_data.get("market_open")
        if "segment" not in ctx_payload:
            ctx_payload["segment"] = market_data.get("segment")
        market_ctx = derive_market_context(ctx_payload)
        default_block_after = max(
            1,
            int(
                getattr(
                    cfg,
                    "LIVE_REGIME_UNSTABLE_CONSECUTIVE_BLOCK",
                    getattr(cfg, "REGIME_UNSTABLE_CONSECUTIVE_BLOCK", 1),
                )
            ),
        )
        if bool(market_ctx.allow_stale_quotes):
            return max(
                1,
                int(
                    getattr(
                        cfg,
                        "PAPER_REGIME_UNSTABLE_CONSECUTIVE_BLOCK",
                        default_block_after,
                    )
                ),
            )
        return default_block_after

    def _is_regime_unstable_hint(self, market_data: dict) -> bool:
        unstable_reasons = list(market_data.get("unstable_reasons") or [])
        if (not unstable_reasons) and bool(market_data.get("unstable_regime_flag", False)):
            unstable_reasons = ["legacy_unstable_flag"]

        ctx_payload = dict(market_data.get("market_context") or {}) if isinstance(market_data.get("market_context"), dict) else {}
        if "execution_mode" not in ctx_payload:
            ctx_payload["execution_mode"] = market_data.get("execution_mode")
        if "market_open" not in ctx_payload and ("market_open" in market_data):
            ctx_payload["market_open"] = market_data.get("market_open")
        if "segment" not in ctx_payload:
            ctx_payload["segment"] = market_data.get("segment")
        market_ctx = derive_market_context(ctx_payload)
        live_mode = str(market_ctx.mode).upper() == "LIVE"

        regime_prob_min = float(getattr(cfg, "REGIME_PROB_MIN", 0.45))
        if (not live_mode) and bool(getattr(cfg, "PAPER_RELAX_GATES", True)):
            regime_prob_min = float(getattr(cfg, "PAPER_REGIME_PROB_MIN", regime_prob_min))

        regime_prob_max = market_data.get("regime_prob_max")
        regime_probs = market_data.get("regime_probs") or {}
        if regime_prob_max is None:
            if isinstance(regime_probs, dict) and regime_probs:
                try:
                    regime_prob_max = max(float(v) for v in regime_probs.values())
                except Exception:
                    regime_prob_max = None
        if regime_prob_max is not None and float(regime_prob_max) < regime_prob_min:
            unstable_reasons.append("prob_too_low")

        regime_entropy = market_data.get("regime_entropy")
        from core.regime_entropy_gate import evaluate_regime_entropy_gate
        session_bucket = str(market_data.get("session_bucket") or "").strip().upper()
        if not session_bucket:
            session_bucket = resolve_canonical_session_context(
                market_data.get("timestamp_ist")
                or market_data.get("timestamp")
                or market_data.get("quote_ts")
                or market_data.get("quote_ts_epoch")
                or market_data.get("ltp_ts_epoch")
                or market_data.get("candle_ts_epoch"),
                segment=str(market_data.get("segment") or "NSE_FNO"),
                is_expiry_day=bool(market_data.get("is_expiry_day")),
                is_event_mode=bool(market_data.get("is_event_mode")),
            ).canonical_session_bucket
        entropy_gate = evaluate_regime_entropy_gate(
            raw_entropy=_safe_float(regime_entropy),
            probabilities=regime_probs if isinstance(regime_probs, dict) else None,
            session_bucket=session_bucket,
            market_data=market_data,
            primary_regime=market_data.get("primary_regime") or market_data.get("regime") or "",
            regime_prob_max=market_data.get("regime_prob_max") or market_data.get("regime_probs_max"),
        )
        if entropy_gate["uncertain"]:
            unstable_reasons.append("entropy_too_high")

        return bool(unstable_reasons)

    def _annotate_regime_unstable_debounce(self, market_data: dict) -> dict:
        row = dict(market_data or {})
        symbol = str(row.get("symbol") or "UNKNOWN").upper()
        streaks = getattr(self, "_regime_unstable_streak_by_symbol", None)
        if not isinstance(streaks, dict):
            streaks = {}
            self._regime_unstable_streak_by_symbol = streaks
        unstable_now = self._is_regime_unstable_hint(row)
        if unstable_now:
            streak = int(streaks.get(symbol, 0)) + 1
        else:
            streak = 0
        streaks[symbol] = streak
        block_after = self._regime_unstable_block_after(row)
        row["regime_unstable_streak"] = int(streak)
        row["regime_unstable_block_after"] = int(block_after)
        row["regime_unstable_debounced"] = bool(unstable_now and streak < block_after)
        return row

    def _maybe_run_suggestion_reliability_check(self) -> None:
        if not bool(getattr(cfg, "SUGGESTION_RELIABILITY_CHECK_ENABLE", True)):
            return
        now_ts = now_utc_epoch()
        interval_sec = float(getattr(cfg, "SUGGESTION_RELIABILITY_INTERVAL_SEC", 900.0))
        last_ts = float(getattr(self, "_last_suggestion_reliability_eval_ts", 0.0) or 0.0)
        if last_ts and (now_ts - last_ts) < interval_sec:
            return
        self._last_suggestion_reliability_eval_ts = now_ts
        payload = evaluate_suggestion_reliability(
            market_context={
                "execution_mode": str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper(),
                "market_open": bool(is_market_open_ist()),
            },
            now_epoch=now_ts,
        )
        persist_suggestion_reliability(payload)
        if str(payload.get("status") or "").upper() == "DEGRADED":
            logger.warning(
                "suggestion_slo_degraded ratio=%.3f allowed=%s candidates=%s top_reject_reasons=%s",
                float(payload.get("allowed_to_candidate_ratio") or 0.0),
                payload.get("allowed_count"),
                payload.get("candidate_count"),
                payload.get("top_reject_reasons"),
            )
            try:
                create_incident("SEV3", "SUGGESTION_RELIABILITY_DEGRADED", payload)
            except Exception:
                pass

    def _maybe_auto_repair_live_feed(self, market_data: dict, gate_reasons: list[str] | None = None) -> dict:
        result = {"action": "noop"}
        if not bool(getattr(cfg, "FEED_AUTO_REPAIR_ENABLE", True)):
            result["action"] = "disabled"
            return result
        ctx_payload = dict(market_data.get("market_context") or {}) if isinstance(market_data.get("market_context"), dict) else {}
        if "execution_mode" not in ctx_payload:
            ctx_payload["execution_mode"] = market_data.get("execution_mode")
        if "market_open" not in ctx_payload and ("market_open" in market_data):
            ctx_payload["market_open"] = market_data.get("market_open")
        if "segment" not in ctx_payload:
            ctx_payload["segment"] = market_data.get("segment")
        market_ctx = derive_market_context(ctx_payload)
        if not (str(market_ctx.mode).upper() == "LIVE" and bool(market_ctx.is_market_open)):
            result["action"] = "skipped_non_live"
            return result

        symbol = str(market_data.get("symbol") or "UNKNOWN").upper()
        reason_values = [str(x or "").strip().upper() for x in (gate_reasons or []) if str(x or "").strip()]
        for code in market_data.get("invalid_reason_codes") or []:
            reason_values.append(str(code or "").strip().upper())
        quote_health = market_data.get("quote_health") or {}
        for code in quote_health.get("stale_reasons") or []:
            reason_values.append(str(code or "").strip().upper())
        if market_data.get("quote_ok") is False:
            reason_values.append("QUOTE_INVALID")
        normalized = {r for r in reason_values if r}
        repair_triggers = {
            "FEED_STALE",
            "QUOTE_INVALID",
            "INDEX_BIDASK_MISSING",
            "LTP_STALE",
            "QUOTE_API_ISSUE",
            "MISSING_LIVE_BIDASK",
        }
        needs_repair = bool(normalized & repair_triggers)
        state = self._feed_auto_repair_state.setdefault(
            symbol,
            {"streak": 0, "retries": 0, "last_attempt_ts": 0.0, "last_auth_check_ts": 0.0},
        )
        if not needs_repair:
            state["streak"] = 0
            state["retries"] = 0
            result["action"] = "healthy"
            return result

        now_ts = now_utc_epoch()
        state["streak"] = int(state.get("streak", 0)) + 1
        result["reasons"] = sorted(list(normalized))
        result["streak"] = int(state["streak"])

        quote_refreshed = False
        try:
            quote_refreshed = bool(refresh_index_quote_from_rest(symbol, force=True))
        except Exception:
            quote_refreshed = False
        result["quote_refreshed"] = quote_refreshed

        trigger_strikes = max(1, int(getattr(cfg, "FEED_AUTO_REPAIR_TRIGGER_STRIKES", 2)))
        ltp_stale_trigger_strikes = max(
            trigger_strikes,
            int(getattr(cfg, "FEED_AUTO_REPAIR_LTP_STALE_TRIGGER_STRIKES", trigger_strikes)),
        )
        effective_trigger_strikes = (
            ltp_stale_trigger_strikes if "LTP_STALE" in normalized else trigger_strikes
        )
        result["trigger_strikes"] = int(effective_trigger_strikes)
        if "LTP_STALE" in normalized:
            result["ltp_stale_trigger_strikes"] = int(ltp_stale_trigger_strikes)
        if int(state["streak"]) < effective_trigger_strikes:
            result["action"] = "waiting_streak"
            return result

        cooldown_sec = float(getattr(cfg, "FEED_AUTO_REPAIR_COOLDOWN_SEC", 60.0))
        if (now_ts - float(state.get("last_attempt_ts") or 0.0)) < cooldown_sec:
            result["action"] = "cooldown"
            return result

        max_retries = max(1, int(getattr(cfg, "FEED_AUTO_REPAIR_MAX_RETRIES", 3)))
        if int(state.get("retries", 0)) >= max_retries:
            result["action"] = "max_retries_reached"
            return result

        auth_recheck_sec = float(getattr(cfg, "FEED_AUTO_REPAIR_AUTH_RECHECK_SEC", 90.0))
        auth_check_due = (now_ts - float(state.get("last_auth_check_ts") or 0.0)) >= auth_recheck_sec
        if auth_check_due:
            from core.auth_health import get_kite_auth_health

            auth_payload = dict(get_kite_auth_health(force=True) or {})
            state["last_auth_check_ts"] = now_ts
            auth_ok = bool(auth_payload.get("ok", False))
            auth_err = str(auth_payload.get("error") or auth_payload.get("auth_state") or "")
            if (not auth_ok) and is_auth_error(reason_text=auth_err):
                result["action"] = "auth_required"
                result["auth_error"] = auth_err
                logger.warning("feed_auto_repair_blocked symbol=%s auth_error=%s", symbol, auth_err)
                try:
                    create_incident(
                        "SEV2",
                        "AUTH_REQUIRED_AUTO_REPAIR_BLOCKED",
                        {"symbol": symbol, "error": auth_err, "reasons": sorted(list(normalized))},
                    )
                except Exception:
                    pass
                return result

        primary_reason = sorted(list(normalized))[0] if normalized else "unknown"
        restarted = bool(restart_depth_ws(reason=f"auto_repair:{symbol}:{primary_reason.lower()}"))
        state["last_attempt_ts"] = now_ts
        state["retries"] = int(state.get("retries", 0)) + 1
        result["action"] = "restart_attempted"
        result["restarted"] = restarted
        _log_freshness_debug(
            "feed_auto_repair symbol=%s restarted=%s streak=%s retries=%s reasons=%s quote_refreshed=%s",
            symbol,
            restarted,
            state["streak"],
            state["retries"],
            sorted(list(normalized)),
            quote_refreshed,
        )
        return result

    def _strategy_gate_for_symbol(self, market_data: dict):
        """
        Evaluate one pure decision DAG per symbol per cycle and log once.
        """
        snapshot = self._immutable_cycle_snapshot(market_data)
        snapshot_data = self._annotate_regime_unstable_debounce(dict(snapshot))
        candidate_id = compute_candidate_id(snapshot_data)
        symbol = str((snapshot_data or {}).get("symbol") or "").upper()
        cache = getattr(self, "_gatekeeper_cycle_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._gatekeeper_cycle_cache = cache
        if symbol in cache:
            decision = cache[symbol]
            return GateResult(
                bool(decision.allowed),
                decision.selected_strategy,
                list(decision.blockers),
                facts=dict(decision.facts or {}),
            )

        precondition_blocking_nodes = {
            NODE_N1_MARKET_OPEN,
            NODE_N2_FEED_FRESH,
            NODE_N3_WARMUP_DONE,
            NODE_N4_QUOTE_OK,
            NODE_N5_REGIME_OK,
            NODE_N6_RISK_OK,
            NODE_N7_GOVERNANCE_LOCKS_OK,
        }
        precheck = evaluate_decision(snapshot_data, strategy_candidates=())
        if (not precheck.allowed) and (precheck.stage in precondition_blocking_nodes):
            decision = precheck
        else:
            try:
                gate_input = MappingProxyType(copy.deepcopy(snapshot_data))
            except Exception:
                gate_input = MappingProxyType(dict(snapshot_data))
            gate = self.gatekeeper.evaluate(gate_input, mode="MAIN")
            strategy_candidates = [
                {
                    "family": getattr(gate, "family", None),
                    "allowed": bool(getattr(gate, "allowed", False)),
                    "reasons": list(getattr(gate, "reasons", []) or []),
                    "candidate_summary": {
                        "gate_family": getattr(gate, "family", None),
                        "gate_allowed": bool(getattr(gate, "allowed", False)),
                    },
                }
            ]
            decision = evaluate_decision(snapshot_data, strategy_candidates=strategy_candidates)

        try:
            handle_post_decision_side_effects(
                decision=decision,
                explain=decision.explain,
                snapshot=build_market_snapshot(snapshot_data),
            )
        except Exception:
            pass
        cache[symbol] = decision

        log_snapshot = dict(snapshot_data)
        log_snapshot["candidate_id"] = str(candidate_id)
        log_snapshot["decision_allowed"] = bool(decision.allowed)
        log_snapshot["decision_stage"] = decision.stage
        log_snapshot["decision_blockers"] = list(decision.blockers)
        log_snapshot["decision_explain"] = list(decision.explain)
        log_snapshot["feed_health_snapshot"] = dict(decision.facts.get("feed_health") or {})
        log_snapshot["node_call_counts"] = dict(decision.facts.get("node_call_counts") or {})
        log_snapshot["event_type"] = "decision_allowed" if bool(decision.allowed) else "decision_blocked"

        self._append_gate_status(
            log_snapshot,
            gate_allowed=bool(decision.allowed),
            gate_family=decision.selected_strategy,
            gate_reasons=list(decision.blockers),
            stage=str(decision.stage or "strategy_gate"),
        )
        decision_payload = {
            "event_type": "decision_evaluated",
            "candidate_id": str(candidate_id),
            "symbol": symbol,
            "allowed": bool(decision.allowed),
            "decision_stage": str(decision.stage or ""),
            "blockers": [str(x) for x in (decision.blockers or []) if str(x).strip()],
            "confidence": snapshot_data.get("global_conf", snapshot_data.get("regime_confidence")),
            "score_signal": snapshot_data.get("signal_score"),
            "score_global": snapshot_data.get("global_conf"),
            "score_regime_conf": snapshot_data.get("regime_confidence"),
            "orb_bias": snapshot_data.get("orb_bias"),
            "orb_factor": snapshot_data.get("orb_factor"),
            "reg_penalty": snapshot_data.get("reg_penalty"),
            "feed_state": (log_snapshot.get("feed_health_snapshot") or {}).get("state"),
            "gate_family": decision.selected_strategy,
            "ts_epoch": snapshot_data.get("timestamp") or now_utc_epoch(),
        }
        candidate_payload = {
            "event_type": "candidate_seen",
            "candidate_id": str(candidate_id),
            "symbol": symbol,
            "cycle_id": snapshot_data.get("cycle_id"),
            "instrument": snapshot_data.get("instrument", "OPT"),
            "strategy_id": decision.selected_strategy,
            "regime": snapshot_data.get("regime"),
            "regime_confidence": snapshot_data.get("regime_confidence"),
            "ts_epoch": snapshot_data.get("timestamp") or now_utc_epoch(),
        }
        try:
            append_candidate_stream_event(
                candidate_payload,
                desk_id=getattr(cfg, "DESK_ID", "DEFAULT"),
            )
        except Exception as exc:
            try:
                append_decision_write_error(
                    desk_id=getattr(cfg, "DESK_ID", "DEFAULT"),
                    stream="candidates_stream",
                    exc=exc,
                    payload=candidate_payload,
                    context={"phase": "candidate_seen"},
                )
            except Exception:
                pass
            logger.warning("candidate_stream_write_failed err=%s:%s", type(exc).__name__, exc)
        try:
            append_decision_stream_event(decision_payload, desk_id=getattr(cfg, "DESK_ID", "DEFAULT"))
            append_decision_stream_event(
                {
                    **decision_payload,
                    "event_type": "decision_allowed" if bool(decision.allowed) else "decision_blocked",
                },
                desk_id=getattr(cfg, "DESK_ID", "DEFAULT"),
            )
        except Exception as exc:
            try:
                append_decision_write_error(
                    desk_id=getattr(cfg, "DESK_ID", "DEFAULT"),
                    stream="decisions_stream",
                    exc=exc,
                    payload=decision_payload,
                    context={"phase": "decision_events"},
                )
            except Exception:
                pass
            try:
                audit_append(
                    {
                        "event": "DECISION_STREAM_WRITE_FAILED",
                        "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                        "symbol": symbol,
                        "decision_stage": str(decision.stage or ""),
                        "allowed": bool(decision.allowed),
                        "exception_type": type(exc).__name__,
                        "exception": str(exc),
                    }
                )
            except Exception:
                pass
            logger.warning("decision_stream_write_failed err=%s:%s", type(exc).__name__, exc)

        return GateResult(
            bool(decision.allowed),
            decision.selected_strategy,
            list(decision.blockers),
            facts=dict(decision.facts or {}),
        )

    def _is_live_mode(self):
        return str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper() == "LIVE"

    def _allow_planning_no_signal_fallback(self, market_data: dict) -> bool:
        if not bool(getattr(cfg, "PLANNING_NO_SIGNAL_FALLBACK_ENABLE", True)):
            return False
        ctx_payload = {}
        if isinstance(market_data, dict) and isinstance(market_data.get("market_context"), dict):
            ctx_payload.update(dict(market_data.get("market_context") or {}))
        if "execution_mode" not in ctx_payload:
            ctx_payload["execution_mode"] = getattr(cfg, "EXECUTION_MODE", "SIM")
        if "market_open" not in ctx_payload and isinstance(market_data, dict):
            if "market_open" in market_data:
                ctx_payload["market_open"] = market_data.get("market_open")
        if "segment" not in ctx_payload:
            if isinstance(market_data, dict) and market_data.get("segment"):
                ctx_payload["segment"] = market_data.get("segment")
            else:
                ctx_payload["segment"] = getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO")
        market_ctx = derive_market_context(ctx_payload)
        return bool(market_ctx.allow_stale_quotes)

    def _should_soften_nonlive_no_strategy_gate(self, market_data: dict, gate) -> bool:
        if gate is None or bool(getattr(gate, "allowed", False)):
            return False
        if self._is_live_mode():
            return False
        reasons = [str(reason) for reason in (getattr(gate, "reasons", None) or []) if str(reason)]
        if not reasons:
            return False
        if any(reason != "NO_STRATEGY_QUALIFIED" for reason in reasons):
            return False
        return bool(self._allow_planning_no_signal_fallback(market_data))

    def _latest_decision_rows(self, max_age_sec: float | None = None) -> dict:
        """
        Return latest Decision DAG row per symbol from gate_status.jsonl.
        This is used for governance/readiness-derived checks without recomputing feed health.
        """
        if max_age_sec is None:
            max_age_sec = float(getattr(cfg, "READINESS_DECISION_MAX_AGE_SEC", 240.0))
        path = logs_dir() / f"desks/{getattr(cfg, 'DESK_ID', 'DEFAULT')}/gate_status.jsonl"
        if not path.exists():
            return {}
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return {}
        now_epoch = now_utc_epoch()
        rows = {}
        for raw in reversed(lines[-500:]):
            line = raw.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            symbol = str(payload.get("symbol") or "").upper()
            if not symbol or symbol in rows:
                continue
            decision_stage = str(payload.get("decision_stage") or "").strip()
            if not decision_stage:
                continue
            try:
                ts_epoch = float(payload.get("ts_epoch"))
            except Exception:
                continue
            if (now_epoch - ts_epoch) > float(max_age_sec):
                continue
            rows[symbol] = payload
        return rows

    def _update_pilot_unlock_clean_cycles(self):
        """
        Count consecutive fresh-feed cycles for paper pilot unlock.
        """
        # Allow warmup cycles to increment in all modes, including LIVE.
        today = now_ist().date().isoformat()
        if today != self._pilot_unlock_day:
            self._pilot_unlock_day = today
            self._pilot_unlock_clean_cycles = 0
            self._pilot_unlock_used_day = None
        try:
            market_open = bool(is_market_open_ist())
            decision_rows = self._latest_decision_rows()
            if market_open and decision_rows:
                all_fresh = True
                for row in decision_rows.values():
                    fhs = row.get("feed_health_snapshot") or {}
                    if fhs.get("is_fresh") is not True:
                        all_fresh = False
                        break
                if all_fresh:
                    self._pilot_unlock_clean_cycles += 1
                    self._pilot_unlock_stale_tolerance = 0
                else:
                    self._pilot_unlock_stale_tolerance = getattr(self, "_pilot_unlock_stale_tolerance", 0) + 1
                    if self._pilot_unlock_stale_tolerance > 3:
                        self._pilot_unlock_clean_cycles = 0
            else:
                self._pilot_unlock_clean_cycles = 0
        except Exception:
            self._pilot_unlock_clean_cycles = 0

    def _pilot_feed_ok(self):
        decision_rows = self._latest_decision_rows()
        market_open = bool(is_market_open_ist())
        if not market_open:
            return True, []

        loaded_runtime = load_current_feed_runtime(logs_dir() / "feed_runtime_latest.json")
        if not loaded_runtime.get("valid"):
            return False, [f"feed_runtime:{loaded_runtime.get('reason_code') or 'INVALID_ARTIFACT'}"]
        feed_runtime_payload = dict(loaded_runtime.get("payload") or {})

        def _runtime_health_feed_reasons() -> tuple[bool, list[str], bool]:
            now_epoch = float(now_utc_epoch())
            stale_reasons: list[str] = []
            health_evidence_found = False
            runtime_health_path = logs_dir() / "runtime_health_latest.json"
            runtime_health_max_age_sec = float(getattr(cfg, "RUNTIME_HEALTH_MAX_AGE_SEC", 30.0))
            feed_runtime_max_age_sec = float(getattr(cfg, "FEED_RUNTIME_MAX_AGE_SEC", 15.0))

            def _safe_float(value):
                try:
                    if value is None:
                        return None
                    return float(value)
                except Exception:
                    return None

            runtime_payload = {}
            if runtime_health_path.exists():
                try:
                    runtime_payload = json.loads(runtime_health_path.read_text(encoding="utf-8"))
                except Exception:
                    runtime_payload = {}
            if runtime_payload:
                health_evidence_found = True

            snapshot_ts = _safe_float(runtime_payload.get("snapshot_ts_epoch") or runtime_payload.get("ts_epoch"))
            snapshot_age = (now_epoch - snapshot_ts) if snapshot_ts is not None else None

            execution_payload = runtime_payload.get("execution") if isinstance(runtime_payload.get("execution"), dict) else {}
            decision_breakers = execution_payload.get("decision_breakers") if isinstance(execution_payload.get("decision_breakers"), dict) else {}
            blocked_reasons = [str(x).strip().upper() for x in (decision_breakers.get("blocked_reasons") or []) if str(x).strip()]
            if bool(decision_breakers.get("blocked")) and any(reason in {"STALE_FEED", "FEED_STALE"} for reason in blocked_reasons):
                stale_reasons.append("feed_stale:DECISION_BREAKER_STALE_FEED")

            feed_payload = runtime_payload.get("feed") if isinstance(runtime_payload.get("feed"), dict) else {}
            if feed_payload:
                full_feed_proof_ready = bool(feed_payload.get("full_feed_proof_ready"))
                full_feed_proof_blockers = [str(x).strip().upper() for x in (feed_payload.get("full_feed_proof_blockers") or []) if str(x).strip()]
                if full_feed_proof_ready is False and full_feed_proof_blockers:
                    stale_reasons.extend([f"feed_stale:{reason}" for reason in full_feed_proof_blockers])
                ws_connected = feed_payload.get("ws_connected")
                ltp_required = bool(feed_payload.get("ltp_required", True))
                ltp_age = _safe_float(feed_payload.get("ltp_age_sec"))
                ltp_max_age = _safe_float(feed_payload.get("ltp_max_age_sec"))
                if ws_connected is False:
                    stale_reasons.append("feed_stale:WS_DISCONNECTED")
                if ltp_required and ltp_age is not None and ltp_max_age is not None and ltp_age > ltp_max_age:
                    stale_reasons.append("feed_stale:LTP_STALE")
                underlying_stale_symbols = [str(symbol).strip().upper() for symbol in (feed_payload.get("underlying_ltp_stale_symbols") or []) if str(symbol).strip()]
                if underlying_stale_symbols:
                    stale_reasons.append("feed_stale:UNDERLYING_LTP_STALE")
                sla_status = str(feed_payload.get("sla_status") or "").upper()
                if sla_status in {"FAIL", "STALE"}:
                    stale_reasons.append("feed_stale:SLA_FAIL")
                blockers = [str(x).strip() for x in (feed_payload.get("blockers") or []) if str(x).strip()]
                stale_reasons.extend([f"feed_stale:{reason}" for reason in blockers])

            feed_runtime_age = None
            if feed_runtime_payload:
                health_evidence_found = True
                feed_runtime_ts = _safe_float(feed_runtime_payload.get("ts_epoch"))
                feed_runtime_age = (now_epoch - feed_runtime_ts) if feed_runtime_ts is not None else None
                if snapshot_age is None or (feed_runtime_age is not None and feed_runtime_age < snapshot_age):
                    snapshot_age = feed_runtime_age
                if not stale_reasons:
                    feed_runtime_feed = feed_runtime_payload.get("feed_truth_state")
                    feed_runtime_reason = str(feed_runtime_payload.get("feed_truth_reason_code") or "").strip().upper()
                    feed_runtime_ok = bool(feed_runtime_payload.get("feed_ok"))
                    feed_runtime_blockers = [str(x).strip().upper() for x in (feed_runtime_payload.get("feed_reasons") or []) if str(x).strip()]
                    if feed_runtime_feed == "DEAD" or feed_runtime_reason == "FEED_UNHEALTHY":
                        stale_reasons.append("feed_stale:FEED_RUNTIME_DEAD")
                    elif feed_runtime_ok is False:
                        stale_reasons.extend([f"feed_stale:{reason}" for reason in feed_runtime_blockers or ["FEED_RUNTIME_NOT_OK"]])

            if runtime_payload:
                state_machine = runtime_payload.get("state_machine")
                if isinstance(state_machine, dict):
                    state = str(state_machine.get("state") or "").upper()
                    reason = str(state_machine.get("reason") or "").strip()
                    if state == "DOWN":
                        stale_reasons.append(f"feed_stale:STATE_{reason or 'DOWN'}")

            if snapshot_age is not None and snapshot_age > runtime_health_max_age_sec and not stale_reasons:
                if feed_runtime_age is None or feed_runtime_age > feed_runtime_max_age_sec:
                    stale_reasons.append("feed_stale:RUNTIME_HEALTH_STALE")

            return health_evidence_found, sorted(set(stale_reasons)), bool(stale_reasons)

        health_evidence_found, stale_reasons, runtime_health_stale = _runtime_health_feed_reasons()
        if runtime_health_stale:
            return False, stale_reasons

        if not decision_rows:
            runtime_health_path = logs_dir() / "runtime_health_latest.json"
            feed_tick_stale_sec = float(getattr(cfg, "FEED_TICK_STALE_RESTART_SEC", 5.0))

            if (not stale_reasons) and feed_runtime_payload:
                health_evidence_found = True
                ws_connected = feed_runtime_payload.get("ws_connected")
                db_tick_age = _safe_float(feed_runtime_payload.get("last_db_tick_age_sec"))
                if ws_connected is False:
                    stale_reasons.append("feed_stale:WS_DISCONNECTED")
                if db_tick_age is not None and db_tick_age > feed_tick_stale_sec:
                    stale_reasons.append("feed_stale:DB_TICK_STALE")

            if not health_evidence_found:
                stale_reasons.append("feed_stale:UNKNOWN")
            if not stale_reasons:
                return True, []
            return False, sorted(set(stale_reasons))
        stale_symbols = []
        for sym, row in decision_rows.items():
            blockers = [str(x).upper() for x in (row.get("decision_blockers") or [])]
            fhs = row.get("feed_health_snapshot") or {}
            if ("FEED_STALE" in blockers) or (fhs.get("is_fresh") is False):
                stale_symbols.append(sym)
        if stale_symbols:
            return False, [f"feed_stale:{','.join(sorted(set(stale_symbols)))}"]
        return True, []

    def _pilot_checks(self):
        if not getattr(cfg, "LIVE_PILOT_MODE", False):
            return True, []
        now = time.time()
        if now - self._pilot_check_cache.get("ts", 0) < 60:
            return self._pilot_check_cache["ok"], list(self._pilot_check_cache["reasons"])
        reasons = []
        if getattr(cfg, "RISK_PROFILE", "PILOT") != "PILOT":
            reasons.append("risk_profile_not_pilot")
        if not getattr(cfg, "LIVE_STRATEGY_WHITELIST", []):
            reasons.append("strategy_whitelist_empty")
        ok, r = self._pilot_audit_ok()
        if not ok:
            reasons.extend(r)
        ok, r = self._pilot_models_ok()
        if not ok:
            reasons.extend(r)
        ok, r = self._pilot_feed_ok()
        if not ok:
            reasons.extend(r)
        ok = len(reasons) == 0
        self._pilot_check_cache = {"ts": now, "ok": ok, "reasons": reasons}
        return ok, reasons

    def _pilot_exec_degradation(self):
        if not getattr(cfg, "LIVE_PILOT_MODE", False):
            return
        path = logs_dir() / "fill_quality_daily.json"
        if not path.exists():
            self.risk_state.set_mode("HARD_HALT", "pilot_fill_quality_missing")
            return
        try:
            data = json.loads(path.read_text())
        except Exception:
            self.risk_state.set_mode("HARD_HALT", "pilot_fill_quality_unreadable")
            return
        day = now_ist().date().isoformat()
        row = data.get(day)
        if not row:
            self.risk_state.set_mode("HARD_HALT", "pilot_fill_quality_empty")
            return
        fill_rate = row.get("fill_rate")
        max_miss = float(getattr(cfg, "EXEC_DEGRADATION_MAX_MISSED_FILL_RATE", 0.5))
        if fill_rate is not None:
            missed_rate = 1.0 - float(fill_rate)
            if missed_rate > max_miss:
                self.risk_state.set_mode("HARD_HALT", "pilot_missed_fill_rate")
                return
        baseline = float(getattr(cfg, "EXEC_BASELINE_SLIPPAGE", 0.0))
        if baseline <= 0:
            self.risk_state.set_mode("HARD_HALT", "pilot_slippage_baseline_missing")
            return
        slippage = row.get("avg_slippage_vs_mid")
        if slippage is not None:
            max_mult = float(getattr(cfg, "EXEC_DEGRADATION_MAX_SLIPPAGE_MULT", 2.0))
            if float(slippage) > baseline * max_mult:
                self.risk_state.set_mode("HARD_HALT", "pilot_slippage_degradation")
                return
        try:
            self.risk_state.set_mode("SOFT_HALT", "pilot_exec_ok")
        except Exception:
            pass

    def _maybe_queue_pilot_unlock(self, market_data: dict, gate_reasons: list[str] | None = None, debug_flag: bool = False):
        """
        Paper-only: queue one low-risk pilot idea per day after clean feed cycles.
        """
        try:
            if self._is_live_mode():
                return None
            if not bool(getattr(cfg, "PAPER_PILOT_UNLOCK_ENABLE", True)):
                return None
            today = now_ist().date().isoformat()
            if self._pilot_unlock_used_day == today:
                return None
            required_cycles = int(getattr(cfg, "PAPER_PILOT_UNLOCK_CLEAN_CYCLES", 3))
            if self._pilot_unlock_clean_cycles < required_cycles:
                return None
            indicators_ok = bool(market_data.get("indicators_ok", False))
            indicators_age = market_data.get("indicators_age_sec")
            indicators_stale = (
                indicators_age is None
                or float(indicators_age) > float(getattr(cfg, "INDICATOR_STALE_SEC", 120))
            )
            if (not indicators_ok) or indicators_stale:
                return None
            trade, _trace = self.trade_builder.build_with_trace(
                market_data,
                quick_mode=True,
                debug_reasons=debug_flag,
                force_family="DEFINED_RISK",
                allow_fallbacks=True,
                allow_baseline=True,
            )
            if not trade:
                return None
            max_risk = float(getattr(cfg, "PAPER_PILOT_UNLOCK_MAX_RISK", 150.0))
            tiny_lots = max(1, min(int(getattr(trade, "qty", 1) or 1), 1))
            pilot_trade = replace(
                trade,
                qty=tiny_lots,
                qty_lots=tiny_lots,
                capital_at_risk=min(float(getattr(trade, "capital_at_risk", max_risk) or max_risk), max_risk),
                tier="PILOT",
            )
            queued, pilot_trade = _queue_review_candidate(
                pilot_trade,
                extra={
                    "tier": "PILOT",
                    "category": "pilot_unlock",
                    "pilot_unlock": True,
                    "pilot_unlock_reason": "PILOT_UNLOCK",
                    "pilot_unlock_clean_cycles": self._pilot_unlock_clean_cycles,
                    "gate_reasons": list(gate_reasons or []),
                },
                reject_source="orchestrator_pilot_unlock",
            )
            if not queued:
                return None
            self._pilot_unlock_used_day = today
            try:
                audit_append(
                    {
                        "event": "PILOT_UNLOCK",
                        "symbol": market_data.get("symbol"),
                        "gate_reasons": list(gate_reasons or []),
                        "clean_cycles": self._pilot_unlock_clean_cycles,
                        "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                    }
                )
            except Exception:
                pass
            return pilot_trade
        except Exception:
            return None

    def _maybe_queue_target_points_idea(self, market_data: dict, debug_flag: bool = False, gate_reasons: list[str] | None = None):
        """
        Advisory-only queue for high-upside ideas.
        This never places orders and is disabled in LIVE mode by default.
        """
        try:
            if not bool(getattr(cfg, "ENABLE_TARGET_POINTS_SUGGESTIONS", True)):
                return None
            if self._is_live_mode() and not bool(getattr(cfg, "ALLOW_AUX_TRADES_LIVE", False)):
                return None
            reasons = set(gate_reasons or [])
            quality_blockers = {
                "indicators_missing_or_stale",
                "cross_asset_required_missing",
                "cross_asset_required_stale",
                "cross_asset_check_error",
                "news_shock_block",
            }
            if reasons & quality_blockers:
                return None
            trade, _trace = self.trade_builder.build_with_trace(
                market_data,
                quick_mode=True,
                debug_reasons=debug_flag,
                allow_fallbacks=True,
                allow_baseline=True,
            )
            if not trade:
                return None
            try:
                target_points = abs(float(getattr(trade, "target", 0.0) or 0.0) - float(getattr(trade, "entry_price", 0.0) or 0.0))
            except Exception:
                return None
            min_points = float(getattr(cfg, "TARGET_POINTS_MIN", 20.0))
            if target_points < min_points:
                return None
            queued, trade = _queue_review_candidate(
                trade,
                queue_path=TARGET_POINTS_QUEUE_PATH,
                extra={
                    "category": "target_points",
                    "tier": "OPPORTUNITY",
                    "target_points": round(target_points, 2),
                    "target_premium": round(target_points, 2),
                    "target_points_min": min_points,
                },
                reject_source="orchestrator_target_points",
            )
            if not queued:
                return None
            try:
                audit_append(
                    {
                        "event": "TARGET_POINTS_IDEA",
                        "symbol": getattr(trade, "symbol", market_data.get("symbol")),
                        "trade_id": getattr(trade, "trade_id", None),
                        "target_points": round(target_points, 2),
                        "target_points_min": min_points,
                        "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                    }
                )
            except Exception:
                pass
            return trade
        except Exception:
            return None

    def _calc_dte(self, expiry: str | None):
        if not expiry:
            return None
        try:
            exp = datetime.fromisoformat(expiry)
        except Exception:
            try:
                exp = datetime.strptime(expiry, "%Y-%m-%d")
            except Exception:
                return None
        return max((exp.date() - now_ist().date()).days, 0)

    def _open_risk(self):
        total = 0.0
        try:
            for lst in self.open_trades.values():
                for tr in lst:
                    total += float(getattr(tr, "capital_at_risk", 0.0) or 0.0)
        except Exception:
            pass
        return total

    def _refresh_exposure_snapshot(self):
        try:
            capital_base = self.portfolio.get("equity_high", self.portfolio.get("capital", self.total_capital))
            snap = self.exposure_ledger.snapshot_from_open_trades(
                self.open_trades,
                total_capital=capital_base,
            ).to_dict()
            self.portfolio["exposure_snapshot"] = snap
            self.portfolio["exposure_by_underlying"] = dict(snap.get("exposure_by_underlying") or {})
            self.portfolio["exposure_by_expiry"] = dict(snap.get("exposure_by_expiry") or {})
            self.portfolio["open_positions_count_by_underlying"] = dict(snap.get("open_positions_count_by_underlying") or {})
            self.portfolio["total_open_exposure"] = float(snap.get("total_open_exposure") or 0.0)
            return snap
        except Exception:
            return {}

    def _update_risk_pct_fields(self):
        return orchestrator_data.update_risk_pct_fields(self)

    def _quote_age_sec(self, quote_ts):
        return orchestrator_data.quote_age_sec(quote_ts)

    def _quote_ts_epoch(self, quote_ts):
        return orchestrator_data.quote_ts_epoch(quote_ts)

    def _pilot_audit_ok(self):
        if not getattr(cfg, "AUDIT_REQUIRED_TO_TRADE", True):
            return True, []
        day = (now_ist() - timedelta(days=1)).date().isoformat()
        audit_path = logs_dir() / f"daily_audit_{day}.json"
        exec_path = logs_dir() / f"execution_report_{day}.json"
        missing = []
        if not audit_path.exists():
            missing.append(audit_path.name)
        if not exec_path.exists():
            missing.append(exec_path.name)
        if missing:
            return False, [f"audit_missing:{','.join(missing)}"]
        return True, []

    def _pilot_models_ok(self):
        active = {
            "xgb": model_registry.get_active("xgb"),
            "deep": model_registry.get_active("deep"),
            "micro": model_registry.get_active("micro"),
            "ensemble": model_registry.get_active("ensemble"),
        }
        if not any(active.values()):
            return False, ["model_registry_empty"]
        return True, []

    def _load_truth_dataset_for_reports(self):
        return orchestrator_data.load_truth_dataset_for_reports()

    def _write_cycle_reports(
        self,
        cycle_reason: str | None = None,
        decision_traces: list[dict] | None = None,
        config_snapshot: dict | None = None,
    ):
        return orchestrator_data.write_cycle_reports(
            cycle_reason=cycle_reason,
            decision_traces=decision_traces,
            config_snapshot=config_snapshot,
        )

    def _feed_status_for_heartbeat(self) -> dict:
        loaded_runtime = load_current_feed_runtime(logs_dir() / "feed_runtime_latest.json")
        payload = dict(loaded_runtime.get("payload") or {}) if loaded_runtime.get("valid") else {}
        feed_ok = False
        try:
            feed_ok, _ = self._pilot_feed_ok()
        except Exception:
            feed_ok = False
        auth_snapshot = runtime_auth_snapshot()
        effective_ws_connected = payload.get("effective_ws_connected")
        if effective_ws_connected is None:
            effective_ws_connected = payload.get("ws_connected")
        return {
            "feed_ok": bool(feed_ok),
            "ws_connected": effective_ws_connected,
            "auth_ok": bool(auth_snapshot.get("auth_ok", True)),
            "auth_state": str(auth_snapshot.get("auth_state") or "UNKNOWN"),
            "auth_reason": str(auth_snapshot.get("auth_reason") or ""),
            "subscribed_option_tokens_count": int(payload.get("subscribed_option_tokens_count") or 0),
            "missing_option_tokens_count": int(payload.get("missing_option_tokens_count") or 0),
        }

    def _write_cycle_status_files(
        self,
        *,
        cycle_ok: bool,
        cycle_stage: str,
        cycle_reason: str,
        last_error: str,
        market_mode: str,
        market_open: bool,
        symbols_scanned: int,
        trade_build_attempts: int = 0,
        candidates_seen: int,
        candidates_blocked: int,
        candidates_enqueued: int,
        blocker_counts: Counter,
        suggestion_count: int,
    ) -> None:
        ts_epoch = float(now_utc_epoch())
        ts_local = datetime.now().astimezone().isoformat()
        feed_status = self._feed_status_for_heartbeat()
        visible_counts = _scan_visible_suggestions(canonical_suggestions_log_path())
        cycle_status = derive_cycle_semantics(
            market_mode=str(market_mode or "").strip().upper(),
            market_open=bool(market_open),
            suggestion_count=int(suggestion_count),
            blocker_counts=blocker_counts,
            last_error=last_error,
        )
        top_blockers = list(cycle_status.get("top_blockers") or [])
        normalized_market_mode = str(cycle_status.get("market_mode") or "").strip().upper()
        normalized_market_open = bool(cycle_status.get("market_open"))
        visible_suggestion_count = int(visible_counts.get("visible_suggestion_count") or 0)
        visible_advisory_count = int(visible_counts.get("visible_advisory_count") or 0)
        visible_queue_only_count = int(visible_counts.get("visible_queue_only_count") or 0)
        visible_executable_count = int(visible_counts.get("visible_executable_count") or 0)
        visible_primary_blocker = str(visible_counts.get("primary_blocker") or "").strip() or None
        if bool(getattr(cfg, "STATUS_ZERO_VISIBLE_COUNTS_WHEN_UNHEALTHY", True)):
            auth_ok = bool(feed_status.get("auth_ok", True))
            ws_connected = feed_status.get("ws_connected")
            if (not bool(feed_status.get("feed_ok"))) or (ws_connected is False) or (not auth_ok):
                visible_counts = _zero_visible_counts(visible_counts)
                visible_suggestion_count = 0
                visible_advisory_count = 0
                visible_queue_only_count = 0
                visible_executable_count = 0
                if not auth_ok:
                    visible_primary_blocker = str(feed_status.get("auth_state") or "AUTH_REQUIRED").strip() or "AUTH_REQUIRED"
        suggestions_status = str(cycle_status.get("semantic_state") or "no_candidates")
        suggestions_reason = cycle_status.get("dominant_reason")
        suggestions_subreason = cycle_status.get("subreason")
        suggestions_primary_blocker = cycle_status.get("primary_blocker")
        if bool(getattr(cfg, "STATUS_ZERO_VISIBLE_COUNTS_WHEN_UNHEALTHY", True)):
            auth_ok = bool(feed_status.get("auth_ok", True))
            ws_connected = feed_status.get("ws_connected")
            if suggestions_status != "error" and not auth_ok:
                suggestions_status = "blocked"
                suggestions_reason = "auth_blocked"
                suggestions_subreason = str(feed_status.get("auth_reason") or "")
                suggestions_primary_blocker = str(feed_status.get("auth_state") or "AUTH_REQUIRED").strip() or "AUTH_REQUIRED"
            elif suggestions_status != "error" and ((not bool(feed_status.get("feed_ok"))) or (ws_connected is False)):
                suggestions_status = "blocked"
                suggestions_reason = "feed_unhealthy"
                suggestions_subreason = str(cycle_status.get("primary_blocker") or "")
                suggestions_primary_blocker = cycle_status.get("primary_blocker") or visible_primary_blocker or "FEED_UNHEALTHY"
        if visible_suggestion_count > 0 and suggestions_status == "no_candidates":
            if visible_executable_count > 0 or visible_queue_only_count > 0 or visible_advisory_count > 0:
                suggestions_status = "ok"
                suggestions_reason = "visible_suggestions_present"
                suggestions_subreason = ""
            else:
                suggestions_status = "blocked"
                suggestions_reason = visible_primary_blocker or "visible_suggestions_blocked"
                suggestions_subreason = ""
            suggestions_primary_blocker = visible_primary_blocker

        suggestions_payload = {
            "ts_epoch": ts_epoch,
            "ts_local": ts_local,
            "status": suggestions_status,
            "suggestion_count": visible_suggestion_count,
            "market_mode": normalized_market_mode,
            "market_open": normalized_market_open,
            "reason": suggestions_reason,
            "subreason": suggestions_subreason,
            "primary_blocker": suggestions_primary_blocker,
            "current_cycle_candidates_seen": int(candidates_seen),
            "current_cycle_candidates_enqueued": int(candidates_enqueued),
            "current_cycle_suggestion_count": int(suggestion_count),
            "visible_suggestion_count": visible_suggestion_count,
            "visible_advisory_count": visible_advisory_count,
            "visible_queue_only_count": visible_queue_only_count,
            "visible_executable_count": visible_executable_count,
            "feed_ok": bool(feed_status.get("feed_ok")),
            "ws_connected": feed_status.get("ws_connected"),
            "auth_ok": bool(feed_status.get("auth_ok", True)),
            "auth_state": str(feed_status.get("auth_state") or "UNKNOWN"),
            "auth_reason": str(feed_status.get("auth_reason") or ""),
            "subscribed_option_tokens_count": int(feed_status.get("subscribed_option_tokens_count") or 0),
            "missing_option_tokens_count": int(feed_status.get("missing_option_tokens_count") or 0),
        }
        engine_payload = {
            "ts_epoch": ts_epoch,
            "cycle_ok": bool(cycle_ok),
            "cycle_stage": cycle_status.get("semantic_state"),
            "market_mode": normalized_market_mode,
            "market_open": normalized_market_open,
            "reason": cycle_status.get("dominant_reason"),
            "subreason": cycle_status.get("subreason"),
            "symbols_scanned": int(symbols_scanned),
            "candidates_seen": int(candidates_seen),
            "candidates_blocked": int(candidates_blocked),
            "candidates_enqueued": int(candidates_enqueued),
            "cycle_trade_build_attempts": int(trade_build_attempts),
            "current_cycle_candidates_seen": int(candidates_seen),
            "current_cycle_candidates_enqueued": int(candidates_enqueued),
            "current_cycle_suggestion_count": int(suggestion_count),
            "visible_suggestion_count": visible_suggestion_count,
            "visible_advisory_count": visible_advisory_count,
            "visible_queue_only_count": visible_queue_only_count,
            "visible_executable_count": visible_executable_count,
            "top_blockers": top_blockers,
            "primary_blocker": cycle_status.get("primary_blocker"),
            "feed_ok": bool(feed_status.get("feed_ok")),
            "ws_connected": feed_status.get("ws_connected"),
            "auth_ok": bool(feed_status.get("auth_ok", True)),
            "auth_state": str(feed_status.get("auth_state") or "UNKNOWN"),
            "auth_reason": str(feed_status.get("auth_reason") or ""),
            "subscribed_option_tokens_count": int(feed_status.get("subscribed_option_tokens_count") or 0),
            "missing_option_tokens_count": int(feed_status.get("missing_option_tokens_count") or 0),
            "last_error": str(last_error or ""),
        }
        write_json_atomic(
            logs_dir() / "suggestions_status.json",
            stamp_runtime_payload(
                suggestions_payload,
                writer="orchestrator.suggestions_status",
            ),
        )
        write_json_atomic(
            logs_dir() / "engine_cycle_status.json",
            stamp_runtime_payload(
                engine_payload,
                writer="orchestrator.engine_cycle_status",
            ),
        )

    def _validate_market_snapshot(self, market_data: dict):
        return orchestrator_finalize.validate_market_snapshot(self, market_data)

    def _pilot_trade_gate(self, trade, market_data):
        return orchestrator_finalize.pilot_trade_gate(self, trade, market_data)

    def _build_decision_event(self, trade, market_data: dict, gatekeeper_allowed: bool, veto_reasons=None, pilot_allowed=None, pilot_reasons=None):
        return orchestrator_decisions.build_decision_event(
            self,
            trade,
            market_data,
            gatekeeper_allowed,
            veto_reasons=veto_reasons,
            pilot_allowed=pilot_allowed,
            pilot_reasons=pilot_reasons,
        )

    def _log_identity_error(self, trade, extra: dict | None = None) -> None:
        return orchestrator_decisions.log_identity_error(self, trade, extra=extra)

    def _log_decision_safe(self, event: dict, trade=None):
        return orchestrator_decisions.log_decision_safe(self, event, trade=trade, log_decision_fn=log_decision)

    def _instrument_id(self, trade):
        return orchestrator_decisions.instrument_id(self, trade)

    def _build_trade_ticket(self, trade, market_data: dict) -> TradeTicket:
        return orchestrator_decisions.build_trade_ticket(self, trade, market_data)

    def _log_meta_shadow(self, trade, market_data):
        return orchestrator_decisions.log_meta_shadow(self, trade, market_data)

    def _refresh_decay_report(self):
        return orchestrator_finalize.refresh_decay_report(self)

    def _runtime_safety_snapshot(self):
        snapshot = {}
        try:
            snapshot["circuit_breaker"] = self.circuit_breaker.state_dict()
        except Exception as exc:
            snapshot["circuit_breaker"] = {"error": f"circuit_breaker_state_error:{type(exc).__name__}"}
        try:
            snapshot["decision_breakers"] = self.decision_breakers.snapshot(now_ts=now_utc_epoch())
        except Exception as exc:
            snapshot["decision_breakers"] = {"error": f"decision_breakers_state_error:{type(exc).__name__}"}
        try:
            snapshot["run_lock"] = self.run_lock.state_dict()
        except Exception as exc:
            snapshot["run_lock"] = {"error": f"run_lock_state_error:{type(exc).__name__}"}
        try:
            snapshot["regime_monitor"] = dict(getattr(self, "_regime_monitor_status", {}) or {})
        except Exception as exc:
            snapshot["regime_monitor"] = {"error": f"regime_monitor_state_error:{type(exc).__name__}"}
        try:
            snapshot["latency_guard"] = dict(getattr(self, "_latency_guard_state", {}) or {})
            snapshot["latency_monitor"] = dict(getattr(self, "_last_latency_stats", {}) or {})
        except Exception as exc:
            snapshot["latency_guard"] = {"error": f"latency_guard_state_error:{type(exc).__name__}"}
        return snapshot

    def _emit_decision_breaker_transitions(self, transitions: list[dict] | None) -> None:
        for transition in list(transitions or []):
            payload = dict(transition or {})
            payload["desk_id"] = str(getattr(cfg, "DESK_ID", "DEFAULT"))
            try:
                append_runtime_event("decision_breaker_state", payload)
            except Exception:
                pass
            try:
                action = str(payload.get("action") or "UNKNOWN")
                breaker = str(payload.get("breaker") or "UNKNOWN")
                reason = str(payload.get("reason") or payload.get("previous_reason") or "")
                logger.warning("decision_breaker action=%s breaker=%s reason=%s", action, breaker, reason)
            except Exception:
                pass

    def _observe_price_mismatch_breaker(self, gate_reasons: list[str] | None) -> None:
        try:
            reasons = [str(x).strip().upper() for x in (gate_reasons or []) if str(x).strip()]
            mismatch_markers = {"PRICE_MISMATCH", "STALE_PRICE", "STALE_OPTION_LTP"}
            unhealthy = any(any(marker in reason for marker in mismatch_markers) for reason in reasons)
            transitions = self.decision_breakers.observe_price_mismatch(
                unhealthy,
                now_ts=now_utc_epoch(),
                evidence={"gate_reasons": reasons},
            )
            self._emit_decision_breaker_transitions(transitions)
        except Exception:
            pass

    def _update_decision_breakers(self, market_data_list: list[dict]) -> None:
        try:
            now_ts = now_utc_epoch()
            option_rows = [
                row for row in (market_data_list or [])
                if str((row or {}).get("instrument", "OPT")).upper() == "OPT"
            ]
            transitions = []
            if option_rows:
                min_option_rows = max(1, int(getattr(cfg, "BREAKER_STALE_FEED_MIN_OPTION_ROWS", 8)))
                if len(option_rows) < min_option_rows:
                    logger.info(
                        "STALE_FEED_DECISION_SAMPLE_SKIPPED option_rows=%s min_option_rows=%s",
                        len(option_rows),
                        min_option_rows,
                    )
                else:
                    fresh_count = 0
                    max_tick_age = float(
                        getattr(
                            cfg,
                            "BREAKER_STALE_FEED_MAX_TICK_AGE_SEC",
                            getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5),
                        )
                    )
                    for row in option_rows:
                        feed_health = (row or {}).get("feed_health")
                        feed_is_fresh = (
                            feed_health.get("is_fresh")
                            if isinstance(feed_health, dict) and ("is_fresh" in feed_health)
                            else None
                        )
                        if feed_is_fresh is None:
                            quote_age = (row or {}).get("quote_age_sec")
                            if quote_age is None:
                                quote_age = self._quote_age_sec((row or {}).get("quote_ts"))
                            try:
                                feed_is_fresh = float(quote_age) <= float(max_tick_age)
                            except Exception:
                                feed_is_fresh = False
                        if bool(feed_is_fresh):
                            fresh_count += 1
                    fresh_ratio = float(fresh_count) / float(max(1, len(option_rows)))
                    min_fresh_ratio = float(getattr(cfg, "BREAKER_STALE_FEED_MIN_FRESH_RATIO", 0.5))
                    transitions.extend(
                        self.decision_breakers.observe_stale_feed(
                            fresh_ratio < min_fresh_ratio,
                            now_ts=now_ts,
                            evidence={
                                "option_rows": len(option_rows),
                                "fresh_count": fresh_count,
                                "fresh_ratio": fresh_ratio,
                                "min_fresh_ratio": min_fresh_ratio,
                                "min_option_rows": min_option_rows,
                            },
                        )
                    )
            failure_snapshot = self.execution_engine.get_failure_snapshot(now_epoch=now_ts)
            counters = dict((failure_snapshot or {}).get("counters") or {})
            broker_rejects = int(counters.get("BROKER_REJECT") or 0)
            network_errors = int(counters.get("NETWORK") or 0)
            prev = dict(getattr(self, "_decision_breaker_failure_counters", {}) or {})
            broker_reject_delta = max(0, broker_rejects - int(prev.get("BROKER_REJECT") or 0))
            network_error_delta = max(0, network_errors - int(prev.get("NETWORK") or 0))
            broker_unhealthy = bool(
                broker_reject_delta > 0
                or network_error_delta > 0
                or bool((failure_snapshot or {}).get("kill_switch_triggered"))
            )
            transitions.extend(
                self.decision_breakers.observe_broker_failure(
                    broker_unhealthy,
                    now_ts=now_ts,
                    evidence={
                        "broker_reject_delta": broker_reject_delta,
                        "network_error_delta": network_error_delta,
                        "kill_switch_triggered": bool((failure_snapshot or {}).get("kill_switch_triggered")),
                    },
                )
            )
            self._decision_breaker_failure_counters = {
                "BROKER_REJECT": broker_rejects,
                "NETWORK": network_errors,
            }
            self._emit_decision_breaker_transitions(transitions)
        except Exception as exc:
            logger.warning("decision_breaker_update_error err=%s:%s", type(exc).__name__, exc)

    def _decision_breakers_block_entries(self) -> tuple[bool, list[str]]:
        try:
            blocked, reasons = self.decision_breakers.should_block_decisions(now_ts=now_utc_epoch())
            if blocked:
                mapped = [f"decision_breaker_{str(r).lower()}" for r in list(reasons or [])]
                return True, mapped
            return False, []
        except Exception:
            return False, []

    def _record_regime_monitor(self, market_data: dict) -> None:
        if not bool(getattr(self, "_regime_monitor_enabled", True)):
            return
        try:
            symbol = str((market_data or {}).get("symbol") or "").upper()
            if not symbol:
                return
            regime = (
                (market_data or {}).get("primary_regime")
                or (market_data or {}).get("regime")
                or "NEUTRAL"
            )
            confidence = (market_data or {}).get("regime_prob_max")
            if confidence is None:
                probs = (market_data or {}).get("regime_probs") or {}
                if isinstance(probs, dict) and probs:
                    try:
                        confidence = max(float(v) for v in probs.values())
                    except Exception:
                        confidence = None
            ltp = (market_data or {}).get("ltp")
            ts_epoch = (market_data or {}).get("timestamp")
            status = self.regime_monitor.record_market_snapshot(
                symbol=symbol,
                predicted_regime=regime,
                confidence=confidence,
                ltp=ltp,
                ts_epoch=ts_epoch,
            )
            self._regime_monitor_status = dict(status or {})
        except Exception:
            pass

    def live_monitoring(self, run_once: bool = False):
        acquired, reason = self.run_lock.acquire()
        if not acquired:
            logger.warning("run_lock_blocked reason=%s", reason)
            try:
                audit_append(
                    {
                        "event": "RUN_LOCK_ACTIVE",
                        "reason": reason,
                        "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                    }
                )
            except Exception as exc:
                logger.warning("run_lock_audit_error err=%s", type(exc).__name__)
            try:
                snap = decision_config_snapshot()
                snap.update(self._runtime_safety_snapshot())
                self._write_cycle_reports(
                    cycle_reason=reason,
                    decision_traces=[],
                    config_snapshot=snap,
                )
            except Exception as exc:
                logger.warning("run_lock_report_error err=%s", type(exc).__name__)
            return {"ok": False, "reason": reason}
        try:
            return run_live_monitoring(self, run_once=run_once, time_module=time)
        finally:
            try:
                self.run_lock.release()
            except Exception as exc:
                logger.warning("run_lock_release_error err=%s", type(exc).__name__)

    def _legacy_live_monitoring(self, run_once: bool = False):
        """
        Phase E: Live trading loop
        from config import config as cfg
        Fetch market data, generate trades, risk-check, execute, log, alert
        """
        from config import config as cfg
        logger.info("orchestrator_live_monitoring_start")
        while True:
            cycle_reason = "cycle_complete"
            cycle_stage = "cycle_start"
            cycle_error = ""
            loop_start_time = time.perf_counter()
            cycle_perf_start = loop_start_time
            dashboard_market_snapshot = None
            dashboard_market_snapshot = None
            latency_critical_path_end_perf = None
            feature_build_ms = 0.0
            decision_build_ms = 0.0
            execution_route_ms = 0.0
            cycle_blockers: Counter = Counter()
            cycle_symbols_scanned: set[str] = set()
            cycle_trade_build_attempts = 0
            cycle_candidates_seen = 0
            cycle_candidate_pool_count = 0
            cycle_scored_candidate_count = 0
            cycle_candidates_blocked = 0
            cycle_candidates_enqueued = 0
            cycle_candidates_softened = 0
            cycle_candidates_fallback = 0
            cycle_ranked_candidates = []
            cycle_candidate_handoff_snapshots: list[dict] = []
            cycle_candidate_starvation_snapshots: list[dict] = []
            cycle_strategy_no_qualified_attempts: list[dict] = []
            candidate_starvation_last_payload = getattr(self, "_candidate_starvation_trace_last_payload", None)
            cycle_real_trade_symbols: set[str] = set()
            cycle_market_mode = str(getattr(globals().get("cfg"), "EXECUTION_MODE", "SIM")).upper()
            cycle_market_open = False
            suggestion_rows_before = 0
            visible_counts_before = {}
            self._decision_traces = []
            self._decision_summary_cycle_seen = set()
            self._gate_status_cycle_seen = set()
            self._gatekeeper_cycle_cache = {}
            self._gate_status_cycle_id = f"{int(now_utc_epoch() * 1000)}"
            market_data_list = []
            feature_timing: dict[str, float] = {}
            feed_truth_payload = _load_cycle_feed_truth_payload()
            feed_runtime_payload, _feed_runtime_path = _read_latest_feed_runtime_payload()
            try:
                if getattr(globals().get("cfg"), "FEED_USE_SUBPROCESS", False):
                    monitor_depth_ws_subprocess()
            except Exception as exc:
                logger.error("subprocess_monitor_error err=%s", exc, exc_info=True)

            # Defensive check: if feed is fatally dead, sleep to prevent high CPU spin.
            from core.recovery_state_machine import evaluate_feed_state, is_fatal_state

            recovery_state = evaluate_feed_state(feed_runtime_payload)
            is_fatal = is_fatal_state(recovery_state)

            if is_fatal:
                logger.warning("orchestrator_live_monitoring_feed_fatal_sleep state=%s", recovery_state.name)
                _pace_loop(max(2.0, self.poll_interval), loop_start_time)
                if run_once:
                    break
                continue

            feed_truth_cycle_gate = _feed_truth_cycle_gate(feed_runtime_payload)
            try:
                # Hot-reload config logic removed to prevent breaking monkeypatches.
                try:
                    self._maybe_auto_clear_runtime_slo_failover_halt()
                except Exception as exc:
                    logger.warning("slo_failover_runtime_clear_cycle_error err=%s", exc)
                global_halt_reason = resolve_global_halt_reason(self.circuit_breaker)
                if global_halt_reason:
                    cycle_reason = global_halt_reason
                    cycle_stage = "global_halt"
                    cycle_blockers[str(global_halt_reason)] += 1
                    self._emit_global_halt_events(global_halt_reason)
                    _pace_loop(self.poll_interval, loop_start_time)
                    if run_once:
                        break
                    continue
                self._last_global_halt_reason = None
                slo_guard = evaluate_slo_status(enforce_failover=True)
                if self._is_live_mode() and str(slo_guard.get("status") or "").upper() in {"BREACH", "FAILOVER"}:
                    cycle_reason = "slo_guard_blocked"
                    cycle_stage = "slo_guard"
                    for reason_code in list(slo_guard.get("reasons") or []) or ["slo_guard_blocked"]:
                        cycle_blockers[str(reason_code)] += 1
                    if bool(slo_guard.get("failover_triggered", False)):
                        self._emit_global_halt_events("SLO_FAILOVER")
                    else:
                        logger.warning(
                            "slo_guard_live_cycle_blocked reasons=%s",
                            ",".join(list(slo_guard.get("reasons") or []) or ["unknown"]),
                        )
                    _pace_loop(self.poll_interval, loop_start_time)
                    if run_once:
                        break
                    continue
                # Feed freshness is now evaluated only in the Decision DAG from the
                # immutable market snapshot. Do not recompute readiness here.
                feature_stage_start = time.perf_counter()
                cycle_stage = "fetch_market_data"

                feature_timing["GAP_top_of_loop_ms"] = (time.perf_counter() - loop_start_time) * 1000.0

                # Daily decay report / strategy gating
                t0 = time.perf_counter()
                self._refresh_decay_report()
                feature_timing["refresh_decay_report_ms"] = _perf_ms(t0)

                t0 = time.perf_counter()
                live_market_data = fetch_live_market_data()
                feature_timing["fetch_live_market_data_ms"] = _perf_ms(t0)

                # Readiness owns underlying/index indicator truth.  The cycle
                # snapshot below is intentionally narrowed to option rows for
                # candidate evaluation, so using it here loses OHLC/indicator
                # inputs and creates a false missing-warmup verdict.
                readiness_market_data = [
                    row for row in list(live_market_data or [])
                    if isinstance(row, dict) and row.get("ohlc_bars_count") is not None
                ] or live_market_data

                t0 = time.perf_counter()
                market_data_list = self._build_cycle_market_data(live_market_data)
                feature_timing["build_cycle_market_data_ms"] = _perf_ms(t0)

                t_gap = time.perf_counter()
                try:
                    indicator_report = build_live_indicator_readiness_report(
                        [row for row in list(readiness_market_data or []) if isinstance(row, dict)],
                        now_epoch=float(time.time()),
                        warmup_min_bars=int(getattr(cfg, "WARMUP_MIN_BARS", 50)),
                        source="orchestrator_live_indicator_readiness_v2",
                    )
                    self._apply_cycle_indicator_readiness_truth(market_data_list, indicator_report)
                    write_live_indicator_readiness_latest(indicator_report, now_epoch=float(time.time()))
                    try:
                        from core.candle_pipeline_diagnostics import emit_candle_pipeline_event
                        for row in list(market_data_list or []):
                            if not isinstance(row, dict):
                                continue
                            symbol = str(row.get("symbol") or "").strip().upper()
                            if not symbol:
                                continue
                            emit_candle_pipeline_event(
                                symbol=symbol, timeframe="1m", stage="T8_WARMUP_EVALUATED",
                                source_event_ts=time.time(), bar_ts=row.get("last_candle_ts"),
                                bar_state=str(row.get("warmup_status") or "UNKNOWN"),
                                bar_count=row.get("ohlc_bars_count"),
                                producer="core.live_indicator_readiness.build_live_indicator_readiness_report",
                                consumer="orchestrator.live_monitoring",
                                details={
                                    "warmup_status": row.get("warmup_status"),
                                    "required_bars": row.get("warmup_min_bars"),
                                    "available_bars": row.get("ohlc_bars_count"),
                                    "accepted_bars": row.get("ohlc_bars_count"),
                                    "rejected_bars": 0,
                                    "last_valid_bar_ts": row.get("last_candle_ts"),
                                    "indicator_last_update_epoch": row.get("indicator_last_update_epoch"),
                                    "warmup_watermark": row.get("indicator_last_update_epoch"),
                                    "warmup_reason_codes": row.get("warmup_reasons") or row.get("regime_reasons") or [],
                                },
                            )
                            emit_candle_pipeline_event(
                                symbol=symbol, timeframe="1m", stage="T9_READINESS_EVALUATED",
                                source_event_ts=time.time(), bar_ts=row.get("last_candle_ts"),
                                bar_state="ALLOWED" if bool(row.get("indicator_readiness_ready")) else "BLOCKED",
                                producer="core.live_indicator_readiness.build_live_indicator_readiness_report",
                                consumer="orchestrator.live_monitoring",
                                details={
                                    "readiness_state": row.get("indicator_readiness_state"),
                                    "allowed": bool(row.get("indicator_readiness_ready")),
                                    "blockers": row.get("indicator_readiness_blockers") or row.get("regime_reasons") or [],
                                    "feed_ok": row.get("feed_ok"),
                                    "execution_feed_ready": row.get("execution_feed_ready"),
                                    "truth_integrity_status": row.get("truth_integrity_status"),
                                    "option_feed_block_reason": row.get("option_feed_block_reason"),
                                    "latest_completed_bar_ts": row.get("last_candle_ts"),
                                    "indicator_last_update_epoch": row.get("indicator_last_update_epoch"),
                                    "warmup_status": row.get("warmup_status"),
                                },
                            )
                    except Exception:
                        pass
                except Exception as exc:
                    logger.warning("cycle_indicator_truth_refresh_failed err=%s", exc)
                cycle_market_open = bool(
                    any(bool((row or {}).get("market_open")) for row in (market_data_list or []))
                )
                dashboard_market_snapshot = None
                feature_timing["GAP_build_indicator_report_ms"] = _perf_ms(t_gap)
                try:
                    # Engine-owned compute: dashboard reads this compact artifact and must not recompute it.
                    t0 = time.perf_counter()
                    dashboard_market_snapshot = produce_and_store_market_snapshot(
                        market_data_list=market_data_list,
                        market_open=cycle_market_open,
                        compute_ms=(time.perf_counter() - feature_stage_start) * 1000.0,
                        loop_id=str(getattr(self, "_gate_status_cycle_id", "") or ""),
                    )
                    feature_timing["produce_market_snapshot_ms"] = _perf_ms(t0)
                except Exception as exc:
                    logger.error("[MARKET_SNAPSHOT_WRITE_ERROR] phase=cycle error=%s:%s", type(exc).__name__, exc)
                t0 = time.perf_counter()
                self._update_decision_breakers(market_data_list)
                feature_timing["update_decision_breakers_ms"] = _perf_ms(t0)

                t0 = time.perf_counter()
                self._update_pilot_unlock_clean_cycles()
                feature_timing["update_pilot_unlock_ms"] = _perf_ms(t0)

                t0 = time.perf_counter()
                self._evaluate_suggestions(market_data_list)
                feature_timing["evaluate_suggestions_ms"] = _perf_ms(t0)
                try:
                    t0 = time.perf_counter()
                    self._run_v2_shadow_pipeline(market_data_list)
                    feature_timing["v2_shadow_pipeline_ms"] = _perf_ms(t0)
                except Exception as exc:
                    logger.warning("v2_shadow_pipeline_cycle_error err=%s", exc)

                try:
                    t0 = time.perf_counter()
                    self._maybe_run_suggestion_reliability_check()
                    feature_timing["suggestion_reliability_check_ms"] = _perf_ms(t0)
                except Exception as exc:
                    logger.warning("suggestion_slo_check_failed err=%s", exc)
                try:
                    # Update consolidated loss streak (max across symbols)
                    try:
                        self.portfolio["loss_streak"] = max(self.loss_streak.values()) if self.loss_streak else 0
                    except Exception:
                        self.portfolio["loss_streak"] = self.portfolio.get("loss_streak", 0)
                    self.risk_state.update_portfolio(self.portfolio)
                except Exception:
                    pass
                t_auto_tune = time.perf_counter()
                try:
                    self._update_risk_pct_fields()
                except Exception:
                    pass
                try:
                    maybe_auto_tune()
                except Exception:
                    pass
                try:
                    self._pilot_exec_degradation()
                except Exception:
                    pass
                feature_timing["GAP_auto_tune_block_ms"] = _perf_ms(t_auto_tune)

                # Reset daily flags at new day
                try:
                    today = now_ist().date()
                    if not hasattr(self, "_last_day"):
                        self._last_day = today
                    if today != self._last_day:
                        self._last_day = today
                        self.best_trade_logged = False
                        self.best_trade_by_regime = {}
                        self.portfolio["daily_profit"] = 0.0
                        self.portfolio["daily_loss"] = 0.0
                        self.portfolio["trades_today"] = 0
                        self.portfolio["symbol_profit"] = {}
                        # reset expiry zero-hero trackers
                        if hasattr(self.trade_builder, "_expiry_zero_hero_loss_streak"):
                            self.trade_builder._expiry_zero_hero_loss_streak = {}
                        if hasattr(self.trade_builder, "_expiry_zero_hero_disabled_until"):
                            self.trade_builder._expiry_zero_hero_disabled_until = {}
                        if hasattr(self.trade_builder, "_expiry_zero_hero_pnl"):
                            self.trade_builder._expiry_zero_hero_pnl = {}
                except Exception:
                    pass

                max_trades_day = getattr(cfg, "MAX_TRADES_PER_DAY", 0)
                if getattr(cfg, "LIVE_PILOT_MODE", False):
                    max_trades_day = min(max_trades_day, int(getattr(cfg, "LIVE_MAX_TRADES_PER_DAY", 2)))
                feature_build_ms += (time.perf_counter() - feature_stage_start) * 1000.0

                t_audit = time.perf_counter()
                try:
                    total_ms = float(feature_build_ms)
                    # Only log when feature_build is unexpectedly slow to avoid noisy logs.
                    if bool(getattr(cfg, "FEATURE_BUILD_TIMING_LOG_ENABLE", True)) and (total_ms >= float(getattr(cfg, "FEATURE_BUILD_TIMING_LOG_SLOW_MS", 2500.0))):
                        audit_append(
                            {
                                "event": "FEATURE_BUILD_TIMING",
                                "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                                "total_ms": round(total_ms, 3),
                                "timing_ms": {k: round(float(v), 3) for k, v in (feature_timing or {}).items()},
                            }
                        )
                except Exception:
                    pass
                feature_timing["GAP_audit_append_ms"] = _perf_ms(t_audit)

                cycle_stage = "scan_symbols"
                t0_sym_loop = time.perf_counter()
                for market_data in market_data_list:
                    market_snapshot = self._immutable_cycle_snapshot(market_data)
                    snap_ok, halt_cycle = self._validate_market_snapshot(market_data)
                    symbol_key = str((market_data or {}).get("symbol") or "").strip().upper()
                    if symbol_key:
                        cycle_symbols_scanned.add(symbol_key)
                    if not snap_ok:
                        cycle_candidates_blocked += 1
                        try:
                            invalid_reasons = [str(x) for x in (market_data.get("invalid_reason_codes") or []) if str(x)]
                            invalid_reason = str(market_data.get("invalid_reason") or "").strip()
                            if invalid_reason:
                                invalid_reasons.append(invalid_reason)
                            for reason_code in list(invalid_reasons or []) or ["invalid_market_snapshot"]:
                                cycle_blockers[str(reason_code)] += 1
                            repair = self._maybe_auto_repair_live_feed(market_data, gate_reasons=invalid_reasons)
                            if str(repair.get("action") or "").upper() == "AUTH_REQUIRED":
                                cycle_reason = "auth_required"
                                cycle_stage = "auth_required"
                                self._emit_global_halt_events("AUTH_REQUIRED")
                                break
                        except Exception:
                            pass
                        try:
                            queued_invalid_snapshot, _ = _queue_invalid_snapshot_candidate_for_analytics(
                                market_data,
                                gate_reasons=list(invalid_reasons or []) or ["invalid_market_snapshot"],
                                reject_reason=invalid_reason or "invalid_market_snapshot",
                                reject_source="orchestrator_invalid_snapshot",
                            )
                            if queued_invalid_snapshot:
                                cycle_candidates_enqueued += 1
                                audit_append(
                                    {
                                        "event": "INVALID_SNAPSHOT_ANALYTICS_QUEUED",
                                        "symbol": market_data.get("symbol"),
                                        "reason": invalid_reason or "invalid_market_snapshot",
                                        "reason_codes": list(invalid_reasons or []),
                                        "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                                    }
                                )
                        except Exception:
                            pass
                        if halt_cycle:
                            break
                        continue
                    instrument = str(market_data.get("instrument", "OPT")).upper()
                    if instrument != "OPT":
                        # Execution suggestion pipeline is option-centric. Skip non-OPT snapshots.
                        continue
                    try:
                        if isinstance(market_data, dict):
                            market_data["allow_planning_no_signal_fallback"] = self._allow_planning_no_signal_fallback(market_data)
                    except Exception:
                        pass
                    try:
                        self.risk_state.update_market(market_data.get("symbol"), market_data)
                    except Exception:
                        pass
                    if self.risk_state.mode == "HARD_HALT":
                        try:
                            event = self._build_decision_event(None, market_data, gatekeeper_allowed=False, veto_reasons=["hard_halt"])
                            self._log_decision_safe(event)
                            audit_append({"event": "HARD_HALT", "symbol": market_data.get("symbol"), "desk_id": getattr(cfg, "DESK_ID", "DEFAULT")})
                            create_incident("SEV1", "HARD_HALT", {"symbol": market_data.get("symbol")})
                        except Exception:
                            pass
                        continue
                    if self.portfolio.get("trades_today", 0) >= max_trades_day:
                        try:
                            event = self._build_decision_event(None, market_data, gatekeeper_allowed=False, veto_reasons=["max_trades_per_day"])
                            self._log_decision_safe(event)
                        except Exception:
                            pass
                        continue
                    if getattr(cfg, "LIVE_PILOT_MODE", False):
                        ok, reasons = self._pilot_checks()
                        if not ok:
                            try:
                                event = self._build_decision_event(None, market_data, gatekeeper_allowed=False, veto_reasons=["pilot_precheck"], pilot_allowed=0, pilot_reasons=reasons)
                                self._log_decision_safe(event)
                            except Exception:
                                pass
                            continue
                    self._sync_trades()
                    sym = market_data.get("symbol")
                    if sym and sym.upper() in getattr(cfg, "HALT_SYMBOLS", []):
                        try:
                            event = self._build_decision_event(None, market_data, gatekeeper_allowed=False, veto_reasons=["halt_symbol"])
                            self._log_decision_safe(event)
                        except Exception:
                            pass
                        continue
                    if sym:
                        self.last_md_by_symbol[sym] = market_data
                    self._record_regime_monitor(market_data)
                    # Check exits for any open trades on this symbol/instrument
                    if self._latency_blocks_non_emergency_exits():
                        try:
                            self._log_decision_safe(
                                self._build_decision_event(
                                    None,
                                    market_data,
                                    gatekeeper_allowed=False,
                                    veto_reasons=["latency_guard_halt_all"],
                                )
                            )
                        except Exception:
                            pass
                        continue
                    self._check_open_trades(market_data)
                    latency_soften_active = False
                    latency_action = None
                    if self._latency_blocks_entries():
                        latency_action = self._latency_guard_action().lower()
                        try:
                            self._log_decision_safe(
                                self._build_decision_event(
                                    None,
                                    market_data,
                                    gatekeeper_allowed=False,
                                    veto_reasons=[f"latency_guard_{latency_action}"],
                                )
                            )
                        except Exception:
                            pass
                        execution_mode = str(
                            market_data.get("execution_mode")
                            or ((market_data.get("market_context") or {}).get("execution_mode") if isinstance(market_data.get("market_context"), dict) else "")
                            or getattr(cfg, "EXECUTION_MODE", "SIM")
                        ).strip().upper()
                        allow_advisory = bool(getattr(cfg, "LATENCY_GUARD_ALLOW_ADVISORY", False))
                        if execution_mode in {"SIM", "PAPER"}:
                            latency_soften_active = True
                            market_data["latency_soften"] = True
                            market_data["latency_guard_action"] = latency_action or "unknown"
                        elif allow_advisory:
                            latency_soften_active = True
                            latency_reason = f"latency_guard_{latency_action}" if latency_action else "latency_guard"
                            market_data["latency_soften"] = True
                            market_data["latency_guard_action"] = latency_action or "unknown"
                            market_data["execution_allowed"] = False
                            market_data["execution_ok"] = False
                            market_data["execution_status"] = "advisory_only"
                            market_data["execution_blocked"] = True
                            market_data["execution_block_reason"] = latency_reason
                            blockers = list(market_data.get("execution_blockers") or [])
                            if latency_reason not in blockers:
                                blockers.append(latency_reason)
                            market_data["execution_blockers"] = blockers
                        else:
                            continue
                    breaker_blocked, breaker_reasons = self._decision_breakers_block_entries()
                    if breaker_blocked:
                        try:
                            self._log_decision_safe(
                                self._build_decision_event(
                                    None,
                                    market_data,
                                    gatekeeper_allowed=False,
                                    veto_reasons=breaker_reasons,
                                )
                            )
                        except Exception:
                            pass
                        continue
                    cooldown = getattr(cfg, "MIN_COOLDOWN_SEC", 300)
                    last_t = self.last_trade_time.get(sym)
                    if last_t and time.time() - last_t < cooldown:
                        continue
                    execution_mode = str(
                        market_data.get("execution_mode")
                        or ((market_data.get("market_context") or {}).get("execution_mode") if isinstance(market_data.get("market_context"), dict) else "")
                        or getattr(cfg, "EXECUTION_MODE", "")
                    ).strip().upper()
                    if _should_skip_trade_builder_for_latency_guard(
                        latency_soften_active=latency_soften_active,
                        execution_mode=execution_mode,
                    ):
                        skip_reason = f"latency_guard_{latency_action}_prebuild_skip" if latency_action else "latency_guard_prebuild_skip"
                        cycle_candidates_blocked += 1
                        cycle_blockers[skip_reason] += 1
                        logger.warning(
                            "latency_guard_prebuild_skip symbol=%s action=%s execution_mode=%s",
                            sym,
                            latency_action or "unknown",
                            execution_mode,
                        )
                        try:
                            audit_append(
                                {
                                    "event": "LATENCY_GUARD_PREBUILD_SKIP",
                                    "symbol": sym,
                                    "action": latency_action or "unknown",
                                    "execution_mode": execution_mode,
                                    "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                                }
                            )
                        except Exception:
                            pass
                        self._log_cycle_symbol_summary(
                            symbol=sym,
                            snapshot_ok=bool(market_snapshot),
                            gate_allowed=False,
                            quote_age_gate_pass=True,
                            trade_build_attempted=False,
                            trade_generated=False,
                            permission="QUEUE_ONLY",
                            final_action="QUEUE_ONLY",
                            reject_reason=skip_reason,
                            top_gate_reasons=[skip_reason],
                        )
                        continue
                    # Phase C: Build trade suggestion
                    debug_flag = getattr(cfg, "DEBUG_TRADE_REASONS", False) or getattr(cfg, "DEBUG_TRADE_MODE", False)
                    gate = self._strategy_gate_for_symbol(market_snapshot)
                    phase1_raw_input_count = len(
                        market_data.get("option_chain")
                        if isinstance(market_data.get("option_chain"), (list, tuple))
                        else []
                    )
                    phase1_strategy_evaluation_count = int(gate is not None)
                    gate_softened_no_strategy = self._should_soften_nonlive_no_strategy_gate(market_data, gate)
                    if gate_softened_no_strategy:
                        cycle_candidates_softened += 1
                        market_data["allow_planning_no_signal_fallback"] = True
                        market_data["gate_softened_no_strategy"] = True
                        logger.info(
                            "gatekeeper_softened_nonlive_no_strategy symbol=%s reasons=%s",
                            sym,
                            ",".join(list(gate.reasons or [])),
                        )
                    if not gate.allowed and not gate_softened_no_strategy:
                        cycle_candidates_blocked += 1
                        for reason_code in list(gate.reasons or []) or ["gatekeeper_blocked"]:
                            cycle_blockers[str(reason_code)] += 1
                        regime_diag = _regime_unstable_diagnostic_payload(market_data, gate.reasons)
                        if regime_diag:
                            logger.warning(
                                "REGIME_UNSTABLE_DIAGNOSTIC %s",
                                json.dumps(regime_diag, sort_keys=True, separators=(",", ":")),
                            )
                            try:
                                audit_append(
                                    {
                                        "event": "REGIME_UNSTABLE_DIAGNOSTIC",
                                        "symbol": sym,
                                        "diagnostic": regime_diag,
                                        "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                                    }
                                )
                            except Exception:
                                pass

                        tele = {}
                        try:
                            if hasattr(gate, "facts") and isinstance(getattr(gate, "facts"), dict):
                                tele = (gate.facts or {}).get("strategy_telemetry") or {}
                            elif hasattr(gate, "decision") and getattr(gate, "decision") is not None:
                                d = gate.decision
                                if hasattr(d, "facts") and isinstance(getattr(d, "facts"), dict):
                                    tele = (d.facts or {}).get("strategy_telemetry") or {}
                        except Exception:
                            tele = {}
                        try:
                            if any(str(reason).strip().upper() == "NO_STRATEGY_QUALIFIED" for reason in list(gate.reasons or [])):
                                cycle_strategy_no_qualified_attempts.append(
                                    build_strategy_attempt_from_gate(
                                        symbol=sym,
                                        strategy_id=getattr(gate, "family", None),
                                        gate_reasons=list(gate.reasons or []),
                                        telemetry=tele if isinstance(tele, dict) else {},
                                    )
                                )
                        except Exception:
                            pass
                        tele_compact = {}
                        if debug_flag:
                            # --- Gatekeeper rejection telemetry (NO_STRATEGY_QUALIFIED debug) ---
                            if isinstance(tele, dict) and tele:
                                tele_compact = {
                                    "qual_fail_codes": tele.get("qual_fail_codes"),
                                    "picked_candidate": tele.get("picked_candidate"),
                                    "qual_fail_reasons_raw": (tele.get("qual_fail_reasons_raw") or [])[:3],
                                }

                            _log_advisory_debug(
                                "gatekeeper_blocked symbol=%s reasons=%s tele=%s",
                                sym,
                                ",".join(gate.reasons),
                                tele_compact if tele_compact else None,
                            )
                        try:
                            repair = self._maybe_auto_repair_live_feed(
                                market_data,
                                gate_reasons=list(gate.reasons or []),
                            )
                            if str(repair.get("action") or "").upper() == "AUTH_REQUIRED":
                                cycle_reason = "auth_required"
                                cycle_stage = "auth_required"
                                self._emit_global_halt_events("AUTH_REQUIRED")
                                break
                        except Exception:
                            pass

                        try:
                            event = self._build_decision_event(
                                None,
                                market_data,
                                gatekeeper_allowed=False,
                                veto_reasons=gate.reasons,
                            )
                            self._log_decision_safe(event)

                            audit_append({
                                "event": "GATEKEEPER_BLOCK",
                                "symbol": sym,
                                "reasons": gate.reasons,
                                "telemetry": tele_compact,
                                "regime_diagnostic": regime_diag,
                                "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                            })
                        except Exception:
                            pass
                        # Advisory-only fallback: queue higher-upside ideas for operator review.
                        self._maybe_queue_target_points_idea(
                            market_data,
                            debug_flag=debug_flag,
                            gate_reasons=gate.reasons,
                        )
                        try:
                            queued_prebuilder, _ = _queue_prebuilder_gate_candidate_for_analytics(
                                market_data,
                                gate_reasons=list(gate.reasons or []),
                                reject_reason="gatekeeper_blocked",
                                reject_source="orchestrator_gatekeeper_block",
                            )
                            if queued_prebuilder:
                                cycle_candidates_enqueued += 1
                        except Exception:
                            pass
                        self._maybe_queue_pilot_unlock(
                            market_data,
                            gate_reasons=gate.reasons,
                            debug_flag=debug_flag,
                        )
                        self._log_cycle_symbol_summary(
                            symbol=sym,
                            snapshot_ok=bool(market_snapshot),
                            gate_allowed=False,
                            quote_age_gate_pass=None,
                            trade_build_attempted=False,
                            trade_generated=False,
                            permission=None,
                            final_action=None,
                            reject_reason="gatekeeper_blocked",
                            top_gate_reasons=list(gate.reasons or []),
                        )
                        continue
                    quote_age_snapshot = self._build_decision_snapshot(
                        market_data=market_data,
                        trade=None,
                        ts_epoch=time.time(),
                    )
                    if quote_age_snapshot is not None:
                        quote_age_thresholds = {
                            "index_max_age_ms": float(getattr(cfg, "DECISION_SNAPSHOT_INDEX_MAX_AGE_MS", 1500.0)),
                            "option_max_age_ms": float(getattr(cfg, "DECISION_SNAPSHOT_OPTION_MAX_AGE_MS", 1500.0)),
                        }
                        quote_age_gate = validate_quote_age(quote_age_snapshot, quote_age_thresholds)
                        if not bool(quote_age_gate.get("pass", False)):
                            reason_code = str(quote_age_gate.get("reason_code") or "STALE_OPTION_LTP")
                            cycle_candidates_blocked += 1
                            cycle_blockers[reason_code] += 1
                            if reason_code == "STALE_INDEX":
                                self.quote_age_gate_metrics["stale_index_count"] = int(
                                    self.quote_age_gate_metrics.get("stale_index_count", 0)
                                ) + 1
                            elif reason_code == "STALE_OPTION_LTP":
                                self.quote_age_gate_metrics["stale_option_count"] = int(
                                    self.quote_age_gate_metrics.get("stale_option_count", 0)
                                ) + 1
                            try:
                                audit_append(
                                    {
                                        "event": "QUOTE_AGE_GATE_BLOCKED",
                                        "symbol": sym,
                                        "reason_code": reason_code,
                                        "quote_age_gate": quote_age_gate,
                                        "snapshot_id": str(getattr(quote_age_snapshot, "snapshot_id", "")),
                                        "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                                    }
                                )
                            except Exception:
                                pass
                            try:
                                event = self._build_decision_event(
                                    None,
                                    market_data,
                                    gatekeeper_allowed=False,
                                    veto_reasons=[reason_code],
                                )
                                self._log_decision_safe(event)
                            except Exception:
                                pass
                            try:
                                queued_prebuilder, _ = _queue_prebuilder_gate_candidate_for_analytics(
                                    market_data,
                                    gate_reasons=[reason_code],
                                    reject_reason=reason_code,
                                    reject_source="orchestrator_quote_age_gate",
                                )
                                if queued_prebuilder:
                                    cycle_candidates_enqueued += 1
                            except Exception:
                                pass
                            self._log_cycle_symbol_summary(
                                symbol=sym,
                                snapshot_ok=bool(market_snapshot),
                                gate_allowed=True,
                                quote_age_gate_pass=False,
                                trade_build_attempted=False,
                                trade_generated=False,
                                permission=None,
                                final_action=None,
                                reject_reason=reason_code,
                                top_gate_reasons=[reason_code],
                            )
                            continue
                    decision_stage_start = time.perf_counter()
                    cycle_trade_build_attempts += 1
                    allow_builder_fallbacks = execution_mode in {"SIM", "PAPER"}
                    allow_builder_baseline = execution_mode in {"SIM", "PAPER"}
                    if bool(feed_truth_cycle_gate.get("skip")):
                        cycle_candidates_blocked += 1
                        gate_reason = str(feed_truth_cycle_gate.get("reason") or "NO_TRADE_FEED_UNVERIFIED")
                        gate_state = str(feed_truth_cycle_gate.get("state") or "UNKNOWN")
                        cycle_strategy_no_qualified_attempts.append(
                            {
                                "symbol": sym,
                                "strategy_id": getattr(gate, "family", None),
                                "raw_candidate_count": 0,
                                "post_scan_survivor_count": 0,
                                "trade_generated": False,
                                "reject_reason": gate_reason,
                                "reject_gate_reasons": [gate_reason, gate_state] if gate_state else [gate_reason],
                                "feed_truth_state": gate_state,
                                "feed_truth_reason_code": str(feed_truth_cycle_gate.get("reason_code") or ""),
                            }
                        )
                        if bool(getattr(cfg, "TRADE_BUILDER_RESULT_TRACE_ENABLE", True)):
                            print(
                                "TB_RESULT",
                                {
                                    "symbol": sym,
                                    "trade_is_none": True,
                                    "decision_stage": "feed_truth_gate",
                                    "final_action": gate_reason,
                                    "reject_reason": gate_reason,
                                },
                            )
                        continue
                    logger.debug(
                        "trade_builder_build_with_trace symbol=%s execution_mode=%s allow_fallbacks=%s allow_baseline=%s gate_family=%s",
                        sym,
                        execution_mode,
                        allow_builder_fallbacks,
                        allow_builder_baseline,
                        getattr(gate, "family", None),
                    )
                    try:
                        trade, decision_trace = self.trade_builder.build_with_trace(
                            market_data,
                            quick_mode=False,
                            debug_reasons=debug_flag,
                            force_family=gate.family,
                            allow_fallbacks=allow_builder_fallbacks,
                            allow_baseline=allow_builder_baseline,
                        )
                    except Exception as phase1_exc:
                        phase1_exception_type = type(phase1_exc).__name__
                        try:
                            record_phase1_observation(build_phase1_observation(
                                cycle_id=str(getattr(self, "_gate_status_cycle_id", "")),
                                market_data=market_data,
                                scan_summary={},
                                survivor_count=0,
                                phase2_handoff_count=0,
                                raw_input_count=phase1_raw_input_count,
                                strategy_evaluation_count=phase1_strategy_evaluation_count,
                                exception_type=phase1_exception_type,
                            ))
                        except Exception:
                            pass
                        raise
                    if isinstance(trade, dict):
                        candidate_status = str(trade.get("candidate_status") or "").strip().lower()
                        execution_status = str(trade.get("execution_status") or "").strip().lower()
                        if candidate_status == "advisory_only" or execution_status == "advisory_only":
                            soft_trade = trade
                            trade = None
                            try:
                                ranked = list(getattr(self.trade_builder, "_last_ranked_candidates", []) or [])
                                if soft_trade not in ranked:
                                    ranked.append(soft_trade)
                                    self.trade_builder._set_last_ranked_candidates(ranked)
                                    logger.info(
                                        "candidate_pool_append source=softened_builder_path symbol=%s reason=%s",
                                        soft_trade.get("symbol"),
                                        soft_trade.get("reject_reason"),
                                    )
                            except Exception:
                                pass
                    trace_payload = {}
                    if decision_trace is not None:
                        try:
                            if hasattr(decision_trace, "to_dict"):
                                trace_payload = dict(decision_trace.to_dict() or {})
                            elif isinstance(decision_trace, dict):
                                trace_payload = dict(decision_trace or {})
                        except Exception:
                            trace_payload = {}
                    if bool(getattr(cfg, "TRADE_BUILDER_RESULT_TRACE_ENABLE", True)):
                        tb_reject_ctx = dict(getattr(self.trade_builder, "_reject_ctx", {}) or {})
                        tb_reject_reason = str(
                            trace_payload.get("reject_reason")
                            or tb_reject_ctx.get("reason")
                            or ""
                        ).strip() or None
                        print(
                            "TB_RESULT",
                            {
                                "symbol": sym,
                                "trade_is_none": trade is None,
                                "decision_stage": trace_payload.get("decision_stage"),
                                "final_action": trace_payload.get("final_action"),
                                "reject_reason": tb_reject_reason,
                            },
                        )
                    scan_summary = dict(getattr(self.trade_builder, "_last_scan_summary", {}) or {})
                    raw_candidate_count = int(scan_summary.get("total_candidates") or 0)
                    cycle_candidate_pool_count += raw_candidate_count
                    cycle_scored_candidate_count += int(scan_summary.get("accepted") or 0)
                    decision_build_ms += (time.perf_counter() - decision_stage_start) * 1000.0
                    if decision_trace is not None:
                        try:
                            self._decision_traces.append(decision_trace.to_dict())
                        except Exception:
                            pass
                    ranked_candidates = _consume_trade_builder_ranked_candidates(self.trade_builder)
                    post_scan_survivor_count = len(ranked_candidates or [])
                    reject_reason = None
                    reject_gate_reasons: list[str] = []
                    soft_reject_candidates: list[dict] = []
                    breadth_candidates: list[dict] = []
                    if trade is None:
                        cycle_candidates_blocked += 1
                        ranked_candidates, soft_reject_candidates, reject_reason, reject_gate_reasons = (
                            _augment_ranked_candidates_with_soft_reject(
                                trade_builder=self.trade_builder,
                                ranked_candidates=ranked_candidates,
                                market_data=market_data,
                                execution_mode=execution_mode,
                                symbol=sym,
                            )
                        )
                    post_soft_reject_count = len(ranked_candidates or [])
                    try:
                        cycle_strategy_no_qualified_attempts.append(
                            build_strategy_attempt_from_trade_builder(
                                symbol=sym,
                                strategy_id=getattr(gate, "family", None),
                                raw_candidate_count=raw_candidate_count,
                                post_scan_survivor_count=post_scan_survivor_count,
                                trade_generated=trade is not None,
                                reject_reason=reject_reason,
                                reject_gate_reasons=reject_gate_reasons,
                            )
                        )
                    except Exception:
                        pass
                    if latency_soften_active and ranked_candidates:
                        pre_latency_real = sum(
                            1 for cand in ranked_candidates if not _is_synthetic_candidate(cand)
                        )
                        logger.info(
                            "PRE_LATENCY_REAL_CANDIDATES symbol=%s count=%s",
                            sym,
                            pre_latency_real,
                        )
                        ranked_candidates, softened_count = _apply_latency_soften_to_candidates(
                            ranked_candidates,
                            latency_action=latency_action,
                            execution_mode=execution_mode,
                            symbol=sym,
                        )
                        cycle_candidates_softened += int(softened_count)
                        post_latency_real = sum(
                            1 for cand in ranked_candidates if not _is_synthetic_candidate(cand)
                        )
                        logger.info(
                            "POST_LATENCY_REAL_CANDIDATES symbol=%s count=%s action=%s",
                            sym,
                            post_latency_real,
                            latency_action,
                        )
                    all_candidates, _ = _filter_invalid_cycle_candidates(ranked_candidates, symbol=sym)
                    real_candidates = [cand for cand in all_candidates if not _is_synthetic_candidate(cand)]
                    synthetic_candidates = [cand for cand in all_candidates if _is_synthetic_candidate(cand)]
                    ranked_candidates = list(real_candidates)
                    fallback_candidates, min_breadth = _build_min_breadth_backfill(
                        ranked_candidates=ranked_candidates,
                        soft_reject_candidates=soft_reject_candidates,
                        market_data=market_data,
                        execution_mode=execution_mode,
                    )
                    if fallback_candidates:
                        logger.info(
                            "MIN_BREADTH_TRIGGERED symbol=%s existing=%s target=%s",
                            sym,
                            len(ranked_candidates or []),
                            min_breadth,
                        )
                        for fallback_candidate in fallback_candidates:
                            breadth_candidates.append(fallback_candidate)
                            cycle_candidates_fallback += 1
                        synthetic_candidates.extend(breadth_candidates)
                        logger.info(
                            "candidate_breadth_backfill symbol=%s count=%s min_required=%s",
                            sym,
                            len(breadth_candidates),
                            min_breadth,
                        )
                        logger.info(
                            "MIN_BREADTH_ADDED symbol=%s added=%s total=%s",
                            sym,
                            len(breadth_candidates),
                            len(real_candidates) + len(synthetic_candidates),
                        )
                        logger.info(
                            "candidate_pool_append source=fallback_min_breadth symbol=%s count=%s",
                            sym,
                            len(breadth_candidates),
                        )
                    if real_candidates or synthetic_candidates:
                        softened = sum(
                            1 for cand in real_candidates if bool(_trade_attr(cand, "latency_softened", False))
                        )
                        fallback = sum(
                            1
                            for cand in synthetic_candidates
                            if str(_trade_attr(cand, "candidate_origin", "") or "") == "fallback_min_breadth"
                        )
                        normal = max(0, len(real_candidates) - softened)
                        total_candidates = len(real_candidates) + len(synthetic_candidates)
                        logger.info("CANDIDATE_POOL symbol=%s size=%s", sym, total_candidates)
                        logger.info(
                            "CANDIDATE_POOL_SOURCES symbol=%s normal=%s softened=%s fallback_min_breadth=%s",
                            sym,
                            normal,
                            softened,
                            fallback,
                        )
                    execution_truth_context = build_execution_truth_context(
                        market_data=market_data,
                        feed_truth=dict(feed_truth_payload),
                        latency_guard=dict(getattr(self, "_latency_guard_state", {}) or {}),
                    )
                    truth_candidate_rows = [
                        _candidate_trace_payload(cand, execution_truth_context=execution_truth_context)
                        for cand in real_candidates
                    ]
                    ranked_executable_candidates = [
                        row for row in truth_candidate_rows if bool(row.get("reportable_executable"))
                    ]
                    ranked_advisory_candidates = [
                        row for row in truth_candidate_rows
                        if str(row.get("visibility_bucket") or "").strip().lower() == "advisory"
                    ]
                    ranked_blocked_candidates = [
                        row for row in truth_candidate_rows
                        if str(row.get("visibility_bucket") or "").strip().lower() == "blocked"
                    ]
                    post_real_filter_count = len(real_candidates)
                    post_executable_filter_count = len(ranked_executable_candidates)
                    regime_gate_reasons = {}
                    regime_unstable_reasons: list[str] = []
                    if isinstance(market_data, dict):
                        regime_unstable_reasons = list(market_data.get("unstable_reasons") or [])
                    try:
                        scan_reject_counts = dict(getattr(self.trade_builder, "_scan_reject_counts", {}) or {})
                    except Exception:
                        scan_reject_counts = {}
                    if isinstance(gate, object) and getattr(gate, "reasons", None):
                        try:
                            regime_gate_reasons = {
                                str(reason).strip().upper(): int(cycle_blockers.get(str(reason).strip().upper(), 0) or 0)
                                for reason in list(gate.reasons or [])
                                if str(reason).strip().upper().startswith("REGIME_")
                            }
                        except Exception:
                            regime_gate_reasons = {}
                    starvation_regime_diag = _regime_unstable_diagnostic_payload(
                        market_data,
                        list(regime_gate_reasons.keys()) if regime_gate_reasons else regime_unstable_reasons,
                    )
                    quote_health_row = market_data.get("quote_health") if isinstance(market_data.get("quote_health"), dict) else {}
                    feed_health_row = market_data.get("feed_health") if isinstance(market_data.get("feed_health"), dict) else {}
                    try:
                        starvation_candidate_reason = None
                        if isinstance(reject_reason, str) and reject_reason.strip():
                            starvation_candidate_reason = reject_reason
                        elif scan_reject_counts:
                            starvation_candidate_reason = max(
                                scan_reject_counts.items(),
                                key=lambda item: (int(item[1] or 0), str(item[0])),
                            )[0]
                        cycle_candidate_starvation_snapshots.append(
                            {
                                "symbol": sym,
                                "regime": starvation_regime_diag if starvation_regime_diag else {
                                    "primary_regime": market_data.get("primary_regime") or market_data.get("regime"),
                                    "regime_entropy": market_data.get("regime_entropy"),
                                    "regime_entropy_normalized": market_data.get("regime_entropy_normalized"),
                                    "regime_entropy_max": market_data.get("regime_entropy_threshold"),
                                    "regime_prob_max": market_data.get("regime_prob_max") or market_data.get("regime_probs_max"),
                                    "regime_prob_min": market_data.get("regime_prob_min") or float(getattr(cfg, "REGIME_PROB_MIN", 0.45)),
                                    "regime_unstable_streak": market_data.get("regime_unstable_streak") or 0,
                                    "regime_unstable_block_after": market_data.get("regime_unstable_block_after") or 0,
                                    "regime_unstable_debounced": bool(market_data.get("regime_unstable_debounced", False)),
                                    "unstable_reasons": list(market_data.get("unstable_reasons") or []),
                                    "regime_unstable": bool(list(market_data.get("unstable_reasons") or [])),
                                    "feed_health": feed_health_row,
                                    "quote_health": quote_health_row,
                                },
                                "raw_candidate_count": raw_candidate_count,
                                "post_scan_survivor_count": post_scan_survivor_count,
                                "post_soft_reject_count": post_soft_reject_count,
                                "post_real_filter_count": post_real_filter_count,
                                "post_executable_filter_count": post_executable_filter_count,
                                "reject_reason": starvation_candidate_reason,
                                "reject_gate_reasons": list(reject_gate_reasons or []),
                                "scan_reject_counts": scan_reject_counts,
                                "blocker_counts": dict(cycle_blockers),
                                "top_blockers": [
                                    {"reason": reason, "count": int(count)}
                                    for reason, count in sorted(
                                        ((str(k), int(v or 0)) for k, v in dict(cycle_blockers or {}).items() if str(k).strip()),
                                        key=lambda item: (-int(item[1]), str(item[0])),
                                    )[:10]
                                ],
                                "feed_runtime_state": feed_runtime_payload.get("runtime_state") if isinstance(feed_runtime_payload, dict) else None,
                                "ws_connected": feed_runtime_payload.get("ws_connected") if isinstance(feed_runtime_payload, dict) else None,
                                "option_feed_block_reason": feed_runtime_payload.get("option_feed_block_reason") if isinstance(feed_runtime_payload, dict) else None,
                                "quote_health_state": quote_health_row.get("state"),
                                "quote_health_stale_reasons": list(quote_health_row.get("stale_reasons") or []),
                                "ltp_age_sec": quote_health_row.get("ltp_age_sec"),
                            }
                        )
                    except Exception:
                        pass
                    eligible_real_candidates = []
                    if trade is not None and not _is_synthetic_candidate(trade):
                        cycle_real_trade_symbols.add(sym)
                        eligible_real_candidates.append(trade)
                    suppress_synthetic_emit = bool(eligible_real_candidates) or sym in cycle_real_trade_symbols
                    eligible_synthetic_candidates = []
                    if trade is None and not suppress_synthetic_emit:
                        eligible_synthetic_candidates = list(soft_reject_candidates) + list(breadth_candidates)
                    if bool(getattr(cfg, "TRADE_BUILDER_RESULT_TRACE_ENABLE", True)):
                        print(
                            "RAW_CANDIDATE_COUNT",
                            {"symbol": sym, "count": raw_candidate_count},
                        )
                        print(
                            "POST_SCAN_SURVIVOR_COUNT",
                            {"symbol": sym, "count": post_scan_survivor_count},
                        )
                        print(
                            "POST_SOFT_REJECT_COUNT",
                            {"symbol": sym, "count": post_soft_reject_count},
                        )
                        print(
                            "POST_REAL_FILTER_COUNT",
                            {"symbol": sym, "count": post_real_filter_count},
                        )
                        print(
                            "POST_EXECUTABLE_FILTER_COUNT",
                            {"symbol": sym, "count": post_executable_filter_count},
                        )
                        print(
                            "TB_RANKED_COUNT_REAL",
                            {"symbol": sym, "count": len(real_candidates)},
                        )
                        print(
                            "TB_RANKED_COUNT_SYNTH",
                            {"symbol": sym, "count": len(synthetic_candidates)},
                        )
                        print(
                            "TB_RANKED_COUNT_TOTAL",
                            {"symbol": sym, "count": len(real_candidates) + len(synthetic_candidates)},
                        )
                        print(
                            "TB_RANKED_COUNT_EXECUTABLE",
                            {"symbol": sym, "count": len(ranked_executable_candidates)},
                        )
                        print(
                            "TB_RANKED_COUNT_ADVISORY",
                            {"symbol": sym, "count": len(ranked_advisory_candidates)},
                        )
                        print(
                            "TB_RANKED_COUNT_BLOCKED",
                            {"symbol": sym, "count": len(ranked_blocked_candidates)},
                        )
                        if real_candidates:
                            top = truth_candidate_rows[0]
                            print(
                                "TB_TOP_REAL_CANDIDATE",
                                top,
                            )
                        if ranked_executable_candidates:
                            print(
                                "TB_TOP_EXECUTABLE_CANDIDATE",
                                ranked_executable_candidates[0],
                            )
                        if ranked_advisory_candidates:
                            print(
                                "TB_TOP_ADVISORY_CANDIDATE",
                                ranked_advisory_candidates[0],
                            )
                        if ranked_blocked_candidates:
                            print(
                                "TB_TOP_BLOCKED_CANDIDATE",
                                ranked_blocked_candidates[0],
                            )
                        if synthetic_candidates:
                            top_synth = synthetic_candidates[0]
                            print(
                                "TB_TOP_SYNTH_CANDIDATE",
                                _candidate_trace_payload(top_synth),
                            )
                    cycle_ranked_candidates_before_append = len(cycle_ranked_candidates)
                    if ranked_candidates:
                        cycle_ranked_candidates.extend(ranked_candidates)
                    cycle_ranked_candidates_after_append = len(cycle_ranked_candidates)
                    try:
                        record_phase1_observation(build_phase1_observation(
                            cycle_id=str(getattr(self, "_gate_status_cycle_id", "")),
                            market_data=market_data,
                            scan_summary=scan_summary,
                            survivor_count=post_scan_survivor_count,
                            phase2_handoff_count=(
                                cycle_ranked_candidates_after_append
                                - cycle_ranked_candidates_before_append
                            ),
                            raw_input_count=phase1_raw_input_count,
                            strategy_evaluation_count=phase1_strategy_evaluation_count,
                        ))
                    except Exception:
                        pass
                    if ranked_executable_candidates:
                        try:
                            cycle_candidate_handoff_snapshots.append(
                                {
                                    "symbol": sym,
                                    "trade_builder_raw_count": raw_candidate_count,
                                    "post_scan_survivor_count": post_scan_survivor_count,
                                    "post_soft_reject_count": post_soft_reject_count,
                                    "post_real_filter_count": post_real_filter_count,
                                    "post_executable_filter_count": post_executable_filter_count,
                                    "ranked_total_count": len(real_candidates),
                                    "ranked_executable_count": len(ranked_executable_candidates),
                                    "top_reportable_executable": ranked_executable_candidates[0],
                                    "cycle_ranked_candidates_count_before_append": cycle_ranked_candidates_before_append,
                                    "cycle_ranked_candidates_count_after_append": cycle_ranked_candidates_after_append,
                                }
                            )
                        except Exception as handoff_exc:
                            logger.warning(
                                "runtime_candidate_handoff_snapshot_build_failed symbol=%s err=%s",
                                sym,
                                handoff_exc,
                            )
                    if trade is None:
                        for reason_code in reject_gate_reasons:
                            cycle_blockers[str(reason_code)] += 1
                        self._observe_price_mismatch_breaker(reject_gate_reasons)
                        if reject_reason == "missing_live_bidask":
                            self._append_gate_status(
                                market_snapshot,
                                gate_allowed=False,
                                gate_family=None,
                                gate_reasons=reject_gate_reasons,
                                stage="trade_builder_gate",
                            )
                        try:
                            repair = self._maybe_auto_repair_live_feed(market_data, gate_reasons=reject_gate_reasons)
                            if str(repair.get("action") or "").upper() == "AUTH_REQUIRED":
                                cycle_reason = "auth_required"
                                self._emit_global_halt_events("AUTH_REQUIRED")
                                break
                        except Exception:
                            pass
                        try:
                            event = self._build_decision_event(
                                None,
                                market_data,
                                gatekeeper_allowed=True,
                                veto_reasons=reject_gate_reasons,
                            )
                            if isinstance(event, dict):
                                event["builder_reject_reason"] = reject_reason
                                event["builder_gate_reasons"] = list(reject_gate_reasons or [])
                            self._log_decision_safe(event)
                        except Exception:
                            pass
                        self._maybe_queue_target_points_idea(
                            market_data,
                            debug_flag=debug_flag,
                            gate_reasons=reject_gate_reasons,
                        )
                        enqueued_trade_ids: set[str] = set()
                        if suppress_synthetic_emit:
                            if soft_reject_candidates or breadth_candidates:
                                logger.info(
                                    "synthetic_emit_suppressed symbol=%s reason=real_candidate_present",
                                    sym,
                                )
                        else:
                            queue_synthetic_candidates = bool(
                                getattr(cfg, "QUEUE_SYNTHETIC_CANDIDATES_ENABLE", False)
                            )
                            if soft_reject_candidates:
                                for soft_candidate in soft_reject_candidates:
                                    try:
                                        trade_id = str(soft_candidate.get("trade_id") or "")
                                        if trade_id and trade_id in enqueued_trade_ids:
                                            continue
                                        if queue_synthetic_candidates:
                                            add_to_queue(soft_candidate)
                                        else:
                                            _queue_rejected_candidate_for_analytics(
                                                [soft_candidate],
                                                gate_reasons=reject_gate_reasons,
                                                reject_reason=reject_reason,
                                                reject_source="orchestrator_soft_reject_candidate",
                                                extra={
                                                    "symbol": sym,
                                                    "decision_stage": "trade_builder_gate",
                                                    "category": "synthetic_soft_reject",
                                                },
                                                exclude_trade_ids=enqueued_trade_ids,
                                            )
                                        if trade_id:
                                            enqueued_trade_ids.add(trade_id)
                                        cycle_candidates_enqueued += 1
                                        logger.info(
                                            "soft_reject_candidate_enqueued symbol=%s trade_id=%s reason=%s gate_reasons=%s queue_synthetic=%s",
                                            soft_candidate.get("symbol"),
                                            soft_candidate.get("trade_id"),
                                            reject_reason or "trade_builder_reject",
                                            ",".join(reject_gate_reasons),
                                            queue_synthetic_candidates,
                                        )
                                    except Exception:
                                        logger.exception("soft_reject_candidate_enqueue_failed symbol=%s", soft_candidate.get("symbol"))
                            if breadth_candidates:
                                for breadth_candidate in breadth_candidates:
                                    try:
                                        trade_id = str(breadth_candidate.get("trade_id") or "")
                                        if trade_id and trade_id in enqueued_trade_ids:
                                            continue
                                        if queue_synthetic_candidates:
                                            add_to_queue(breadth_candidate)
                                        else:
                                            _queue_rejected_candidate_for_analytics(
                                                [breadth_candidate],
                                                gate_reasons=["fallback_min_breadth"],
                                                reject_reason="fallback_min_breadth",
                                                reject_source="orchestrator_breadth_backfill_candidate",
                                                extra={
                                                    "symbol": sym,
                                                    "decision_stage": "trade_builder_gate",
                                                    "category": "synthetic_breadth_backfill",
                                                },
                                                exclude_trade_ids=enqueued_trade_ids,
                                            )
                                        if trade_id:
                                            enqueued_trade_ids.add(trade_id)
                                        cycle_candidates_enqueued += 1
                                        logger.info(
                                            "candidate_breadth_backfill_enqueued symbol=%s trade_id=%s queue_synthetic=%s",
                                            breadth_candidate.get("symbol"),
                                            breadth_candidate.get("trade_id"),
                                            queue_synthetic_candidates,
                                        )
                                    except Exception:
                                        logger.exception("candidate_breadth_backfill_enqueue_failed symbol=%s", sym)
                        try:
                            queued_rejected, _queued_trade = _queue_rejected_candidate_for_analytics(
                                ranked_candidates,
                                gate_reasons=reject_gate_reasons,
                                reject_reason=reject_reason,
                                reject_source="orchestrator_trade_builder_reject",
                                extra={
                                    "symbol": sym,
                                    "decision_stage": "trade_builder_gate",
                                },
                                exclude_trade_ids=enqueued_trade_ids,
                            )
                            if queued_rejected:
                                cycle_candidates_enqueued += 1
                        except Exception:
                            pass
                        if self.decision_store is not None:
                            try:
                                decision_snapshot = self._build_decision_snapshot(
                                    market_data=market_data,
                                    trade=None,
                                    ts_epoch=time.time(),
                                )
                                snapshot_payload = (
                                    decision_snapshot.to_dict()
                                    if isinstance(decision_snapshot, DecisionSnapshot)
                                    else {}
                                )
                                signal_result = evaluate_signal(
                                    snapshot_payload,
                                    {
                                        "direction": "",
                                        "confidence": None,
                                        "features": {
                                            "pattern_flags": [],
                                            "rank_score": None,
                                        },
                                    },
                                )
                                execution_decision = evaluate_execution_decision(snapshot_payload, signal_result)
                                decision = build_decision(
                                    meta={
                                        "ts_epoch": time.time(),
                                        "run_id": f"{sym}-NO_TRADE",
                                        "symbol": sym,
                                        "timeframe": str(market_data.get("timeframe", "")),
                                    },
                                    market={
                                        "spot": float(market_data.get("spot", market_data.get("ltp", 0.0)) or 0.0),
                                        "vwap": market_data.get("vwap"),
                                        "trend_state": str(market_data.get("trend_state", "")),
                                        "regime": str(market_data.get("regime", "")),
                                        "vol_state": str(market_data.get("vol_state", "")),
                                        "iv": market_data.get("iv"),
                                        "ivp": market_data.get("ivp"),
                                    },
                                    outcome={"status": "skipped", "reject_reasons": reject_gate_reasons},
                                    decision_snapshot=decision_snapshot,
                                    signal_result=signal_result,
                                    execution_decision=execution_decision,
                                )
                                self.decision_store.save_decision(decision)
                            except Exception as exc:
                                logger.warning("decision_store_save_skipped_failed err=%s", exc)
                        self._log_cycle_symbol_summary(
                            symbol=sym,
                            snapshot_ok=bool(market_snapshot),
                            gate_allowed=True,
                            quote_age_gate_pass=True,
                            trade_build_attempted=True,
                            trade_generated=False,
                            permission=None,
                            final_action=None,
                            reject_reason=reject_reason or "no_trade_generated",
                            top_gate_reasons=reject_gate_reasons,
                        )
                        continue
                    trade = _coerce_trade_dict_to_schema(trade, market_data=market_data)
                    if isinstance(trade, dict):
                        cycle_candidates_blocked += 1
                        cycle_blockers["trade_schema_coerce_failed"] += 1
                        logger.warning(
                            "trade_schema_coerce_failed symbol=%s trade_id=%s strategy_family=%s",
                            sym,
                            trade.get("trade_id"),
                            trade.get("strategy_family"),
                        )
                        continue
                    cycle_candidates_seen += 1
                    self._observe_price_mismatch_breaker([])
                    self._log_cycle_symbol_summary(
                        symbol=sym,
                        snapshot_ok=bool(market_snapshot),
                        gate_allowed=True,
                        quote_age_gate_pass=True,
                        trade_build_attempted=True,
                        trade_generated=True,
                        permission=_trade_attr(trade, "permission", None),
                        final_action=_trade_attr(trade, "final_action", None),
                        reject_reason=None,
                        top_gate_reasons=[],
                    )
                    if str(_trade_attr(trade, "strategy", "") or "").upper() in getattr(cfg, "HALT_STRATEGIES", []):
                        try:
                            trade_id_for_update = _trade_attr(trade, "trade_id", None)
                            if trade_id_for_update:
                                update_execution(trade_id_for_update, {"veto_reasons": ["halt_strategy"]})
                        except Exception:
                            pass
                        continue
                    # Optional cross-asset staleness: downsize but do not block.
                    try:
                        cross_q = market_data.get("cross_asset_quality", {}) or {}
                        optional = set(getattr(cfg, "CROSS_OPTIONAL_FEEDS", []) or [])
                        stale = set(cross_q.get("stale_feeds", []) or [])
                        missing = set((cross_q.get("missing") or {}).keys())
                        if (stale | missing) & optional:
                            mult = float(getattr(cfg, "CROSS_ASSET_OPTIONAL_SIZE_MULT", 0.85))
                            current = float(_trade_attr(trade, "size_mult", 1.0) or 1.0)
                            trade = _replace_trade_fields(trade, {"size_mult": min(current, mult)})
                    except Exception:
                        pass
                    # Spread suggestions (advisory only; defined-risk)
                    try:
                        if gate.allowed and gate.family in ("DEFINED_RISK",):
                            spreads = self.trade_builder.build_spread_suggestions(market_data)
                            for sp in spreads:
                                queued, _ = _queue_review_candidate(type("Obj", (), sp), reject_source="orchestrator_spread_suggestion")
                                if queued:
                                    cycle_candidates_enqueued += 1
                                else:
                                    cycle_candidates_blocked += 1
                                    cycle_blockers["unresolved_contract"] += 1
                    except Exception:
                        pass
                    if not trade:
                        try:
                            reason = None
                            try:
                                reason = (self.trade_builder._reject_ctx or {}).get("reason")
                            except Exception:
                                reason = None
                            veto = [reason] if reason else ["no_trade_generated"]
                            event = self._build_decision_event(None, market_data, gatekeeper_allowed=True, veto_reasons=veto)
                            self._log_decision_safe(event)
                        except Exception:
                            pass
                        # Track blocked candidates for paper outcome evaluation
                        try:
                            self.blocked_tracker.capture_from_log()
                        except Exception:
                            pass
                        # No quick/baseline fallback trades in live mode
                        # Keep only strategy-specific queues if allowed by gatekeeper
                        try:
                            if str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper() == "LIVE" and not getattr(cfg, "ALLOW_AUX_TRADES_LIVE", False):
                                continue
                            if gate.allowed and bool(getattr(cfg, "EXPIRY_LOTTO_MODE", False)):
                                lotto_trades = self.trade_builder.build_expiry_lotto_candidates(
                                    market_data,
                                    debug_reasons=debug_flag,
                                )
                                cycle_ranked_candidates.extend(_consume_trade_builder_ranked_candidates(self.trade_builder))
                                if lotto_trades:
                                    for lotto_trade in lotto_trades:
                                        queued, _ = _queue_review_candidate(
                                            lotto_trade,
                                            queue_path=TARGET_POINTS_QUEUE_PATH,
                                            extra={"category": "expiry_lotto", "tier": "EXPLORATION"},
                                            reject_source="orchestrator_expiry_lotto",
                                        )
                                        if queued:
                                            cycle_candidates_enqueued += 1
                                        else:
                                            cycle_candidates_blocked += 1
                                            cycle_blockers["unresolved_contract"] += 1
                                else:
                                    try:
                                        reason = (self.trade_builder._reject_ctx or {}).get("reason")
                                        if reason:
                                            self._log_decision_safe(
                                                self._build_decision_event(
                                                    None,
                                                    market_data,
                                                    gatekeeper_allowed=True,
                                                    veto_reasons=[f"expiry_lotto:{reason}"],
                                                )
                                            )
                                    except Exception:
                                        pass
                            if gate.allowed and gate.family in ("TREND", "EVENT"):
                                zero_trade = self.trade_builder.build_zero_hero(
                                    market_data,
                                    debug_reasons=debug_flag
                                )
                                cycle_ranked_candidates.extend(_consume_trade_builder_ranked_candidates(self.trade_builder))
                                if zero_trade:
                                    queued, _ = _queue_review_candidate(
                                        zero_trade,
                                        queue_path=ZERO_HERO_QUEUE_PATH,
                                        extra={"category": "zero_to_hero", "tier": "EXPLORATION"},
                                        reject_source="orchestrator_zero_to_hero",
                                    )
                                    if queued:
                                        cycle_candidates_enqueued += 1
                                    else:
                                        cycle_candidates_blocked += 1
                                        cycle_blockers["unresolved_contract"] += 1
                            if gate.allowed and gate.family == "MEAN_REVERT":
                                scalp_trade = self.trade_builder.build_scalp(
                                    market_data,
                                    debug_reasons=debug_flag
                                )
                                cycle_ranked_candidates.extend(_consume_trade_builder_ranked_candidates(self.trade_builder))
                                if scalp_trade:
                                    queued, _ = _queue_review_candidate(
                                        scalp_trade,
                                        queue_path=SCALP_QUEUE_PATH,
                                        extra={"category": "scalp", "tier": "EXPLORATION"},
                                        reject_source="orchestrator_scalp",
                                    )
                                    if queued:
                                        cycle_candidates_enqueued += 1
                                    else:
                                        cycle_candidates_blocked += 1
                                        cycle_blockers["unresolved_contract"] += 1
                        except Exception:
                            pass
                        continue
                    # RiskState: register attempt and approve
                    decision_id = None
                    decision_snapshot_obj = self._build_decision_snapshot(
                        market_data=market_data,
                        trade=trade,
                        ts_epoch=time.time(),
                    )
                    if decision_snapshot_obj is not None:
                        try:
                            source_flags = dict(_trade_attr(trade, "source_flags", {}) or {})
                            source_flags["decision_snapshot"] = decision_snapshot_obj.to_dict()
                            source_flags["decision_snapshot_id"] = str(decision_snapshot_obj.snapshot_id)
                            trade = _replace_trade_fields(
                                trade,
                                {
                                    "snapshot_id": str(decision_snapshot_obj.snapshot_id),
                                    "source_flags": source_flags,
                                },
                            )
                        except Exception:
                            pass
                    try:
                        event = self._build_decision_event(trade, market_data, gatekeeper_allowed=True, veto_reasons=[])
                        if event.get("instrument_id") is None:
                            veto = event.get("veto_reasons") or []
                            if "missing_contract_fields" not in veto:
                                veto.append("missing_contract_fields")
                            event["veto_reasons"] = veto
                            self._log_identity_error(trade, event)
                            try:
                                self._log_decision_safe(event, trade)
                            except Exception:
                                pass
                            try:
                                queued_missing_contract, _ = _queue_review_candidate(
                                    trade,
                                    extra={
                                        "decision_stage": "decision:gatekeeper",
                                        "execution_blocked": True,
                                        "execution_block_reason": "missing_contract_fields",
                                        "permission": "ADVISORY_ONLY",
                                        "readiness": "ADVISORY_ONLY",
                                        "final_action": "ADVISORY_ONLY",
                                        "execution_status": "advisory_only",
                                    },
                                    reject_source="orchestrator_missing_contract_review_queue",
                                    allow_unresolved_for_analytics=True,
                                )
                                if queued_missing_contract:
                                    cycle_candidates_enqueued += 1
                            except Exception:
                                pass
                            continue
                        decision_id = self._log_decision_safe(event, trade)
                        self._log_meta_shadow(trade, market_data)
                    except Exception:
                        decision_id = _trade_attr(trade, "trade_id")
                    if self.decision_store is not None:
                        try:
                            snapshot_payload = (
                                decision_snapshot_obj.to_dict()
                                if isinstance(decision_snapshot_obj, DecisionSnapshot)
                                else {}
                            )
                            signal_result = evaluate_signal(
                                snapshot_payload,
                                {
                                    "direction": str(getattr(trade, "side", "") or ""),
                                    "confidence": getattr(trade, "confidence", None),
                                    "features": {
                                        "pattern_flags": list(getattr(trade, "pattern_flags", []) or []),
                                        "rank_score": getattr(trade, "trade_score", None),
                                    },
                                },
                            )
                            execution_decision = evaluate_execution_decision(snapshot_payload, signal_result)
                            decision = build_decision(
                                meta={
                                    "ts_epoch": time.time(),
                                    "run_id": decision_id or _trade_attr(trade, "trade_id"),
                                    "symbol": sym,
                                    "timeframe": str(market_data.get("timeframe", "")),
                                },
                                market={
                                    "spot": float(market_data.get("spot", market_data.get("ltp", 0.0)) or 0.0),
                                    "vwap": market_data.get("vwap"),
                                    "trend_state": str(market_data.get("trend_state", "")),
                                    "regime": str(market_data.get("regime", "")),
                                    "vol_state": str(market_data.get("vol_state", "")),
                                    "iv": market_data.get("iv"),
                                    "ivp": market_data.get("ivp"),
                                },
                                signals={
                                    "pattern_flags": list(getattr(trade, "pattern_flags", []) or []),
                                    "rank_score": getattr(trade, "trade_score", None),
                                    "confidence": getattr(trade, "confidence", None),
                                },
                                strategy={
                                    "name": str(getattr(trade, "strategy", "")),
                                    "legs": list(getattr(trade, "legs", []) or []),
                                    "direction": str(getattr(trade, "side", "")),
                                    "entry_reason": str(getattr(trade, "entry_reason", "")),
                                    "stop": float(getattr(trade, "stop_loss", 0.0) or 0.0),
                                    "target": float(getattr(trade, "target", 0.0) or 0.0),
                                    "rr": float(getattr(trade, "rr", 0.0) or 0.0),
                                    "max_loss": float(getattr(trade, "max_loss", 0.0) or 0.0),
                                    "size": float(getattr(trade, "qty", 0.0) or 0.0),
                                },
                                risk={
                                    "daily_loss_limit": float(getattr(cfg, "MAX_DAILY_LOSS_PCT", 0.0)),
                                    "position_limit": float(getattr(cfg, "MAX_TRADES_PER_DAY", 0.0)),
                                    "slippage_bps_assumed": float(getattr(cfg, "SLIPPAGE_BPS", 0.0)),
                                },
                                outcome={"status": "planned", "reject_reasons": []},
                                decision_snapshot=decision_snapshot_obj,
                                signal_result=signal_result,
                                execution_decision=execution_decision,
                            )
                            self.decision_store.save_decision(decision)
                        except Exception as exc:
                            logger.warning("decision_store_save_failed err=%s", exc)
                    trade_id_for_update = _trade_attr(trade, "trade_id", None)
                    strategy_name = str(_trade_attr(trade, "strategy", "") or "")
                    try:
                        self.risk_state.record_trade_attempt(trade)
                        ok, reason = self.risk_state.approve(trade)
                        if not ok:
                            cycle_candidates_blocked += 1
                            cycle_blockers[str(reason or "risk_state_blocked")] += 1
                            if debug_flag:
                                _log_advisory_debug("risk_state_trade_blocked reason=%s", reason)
                            try:
                                if trade_id_for_update:
                                    update_execution(trade_id_for_update, {"risk_allowed": 0, "veto_reasons": [reason]})
                            except Exception:
                                pass
                            if self.decision_store is not None and decision_id:
                                try:
                                    self.decision_store.update_status(decision_id, "rejected", reject_reasons=[reason])
                                except Exception as exc:
                                    logger.warning("decision_store_update_rejected_failed err=%s", exc)
                            continue
                        try:
                            if trade_id_for_update:
                                update_execution(trade_id_for_update, {"risk_allowed": 1})
                        except Exception:
                            pass
                    except Exception:
                        pass
                    if self.strategy_tracker.is_disabled(
                        strategy_name,
                        min_trades=getattr(cfg, "STRATEGY_MIN_TRADES", 30),
                        threshold=getattr(cfg, "STRATEGY_DISABLE_THRESHOLD", 0.45)
                    ):
                        logger.info("strategy_tracker_disabled strategy=%s", strategy_name)
                        continue
                    # Decay-based gating
                    action, _prob = self.strategy_tracker.decay_action(strategy_name)
                    if action == "hard":
                        try:
                            if trade_id_for_update:
                                update_execution(trade_id_for_update, {"veto_reasons": ["decay_quarantine"]})
                        except Exception:
                            pass
                        continue
                    elif action == "soft":
                        try:
                            next_size_mult = float(_trade_attr(trade, "size_mult", 1.0) or 1.0) * float(
                                getattr(cfg, "DECAY_DOWNSIZE_MULT", 0.6)
                            )
                            trade = _replace_trade_fields(trade, {"size_mult": next_size_mult})
                            if trade_id_for_update:
                                update_execution(trade_id_for_update, {"action_size_multiplier": next_size_mult})
                        except Exception:
                            pass
                    # Best trade per day filter
                    if getattr(cfg, "BEST_TRADE_PER_DAY", True) and self.best_trade_logged:
                        try:
                            update_execution(trade.trade_id, {"veto_reasons": ["best_trade_per_day"]})
                        except Exception:
                            pass
                        continue
                    # Best trade per regime filter
                    if getattr(cfg, "BEST_TRADE_PER_REGIME", True):
                        rkey = trade.regime or "NEUTRAL"
                        if self.best_trade_by_regime.get(rkey):
                            try:
                                update_execution(trade.trade_id, {"veto_reasons": ["best_trade_per_regime"]})
                            except Exception:
                                pass
                            continue
                    # Adjust epsilon by regime (lower in choppy regimes) without mutating global config.
                    base_eps = float(self.symbol_epsilon.get(sym, cfg.STRATEGY_EPSILON))
                    regime = market_data.get("primary_regime") or market_data.get("regime") or "NEUTRAL"
                    adjusted_eps = base_eps
                    if regime == "CHOPPY":
                        adjusted_eps = max(0.02, base_eps * 0.5)
                    elif regime == "TREND":
                        adjusted_eps = min(0.2, base_eps * 1.2)
                    allocator_seed = self._allocator_context_seed(market_data, sym, trade.strategy)
                    if not self.strategy_allocator.should_trade(
                        trade.strategy,
                        epsilon=adjusted_eps,
                        context_seed=allocator_seed,
                    ):
                        try:
                            update_execution(trade.trade_id, {"veto_reasons": ["strategy_allocator"]})
                        except Exception:
                            pass
                        continue
                    self.symbol_epsilon[sym] = adjusted_eps
                    self._save_symbol_eps()

                    # A/B paper trading log (shadow model)
                    try:
                        if getattr(cfg, "ML_AB_ENABLE", False) and getattr(trade, "shadow_confidence", None) is not None:
                            mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
                            log_ab_trial(
                                trade.trade_id,
                                trade.symbol,
                                now_ist().isoformat(),
                                trade.confidence,
                                trade.shadow_confidence,
                                getattr(trade, "model_version", None),
                                getattr(trade, "shadow_model_version", None),
                                mode=mode,
                                extra={"strategy": trade.strategy, "regime": trade.regime},
                            )
                    except Exception:
                            pass

                    # Pilot gating (strategy whitelist + quote/spread strictness)
                    if getattr(cfg, "LIVE_PILOT_MODE", False):
                        pilot_allowed, pilot_reasons = self._pilot_trade_gate(trade, market_data)
                        if not pilot_allowed:
                            try:
                                update_execution(trade.trade_id, {"pilot_allowed": 0, "pilot_reasons": pilot_reasons, "veto_reasons": pilot_reasons})
                            except Exception:
                                pass
                            continue
                        try:
                            update_execution(trade.trade_id, {"pilot_allowed": 1})
                        except Exception:
                            pass

                    # Manual approval gate (strong trades)
                    approval_payload_hash = order_payload_hash(trade)
                    approved, approval_reason = approval_status(trade.trade_id, payload_hash=approval_payload_hash)
                    if cfg.MANUAL_APPROVAL and not approved:
                        # Pre-trade validation report
                        rr = None
                        try:
                            rr = abs(trade.target - trade.entry_price) / max(abs(trade.entry_price - trade.stop_loss), 1e-6)
                        except Exception:
                            rr = None
                        # Regime-aware confidence threshold
                        min_conf = getattr(cfg, "ML_MIN_PROBA", 0.6)
                        mult = getattr(cfg, "REGIME_PROBA_MULT", {}).get(trade.regime or "NEUTRAL", 1.0)
                        min_conf = min_conf * mult
                        validation = {
                            "pretrade_conf_ok": trade.confidence >= min_conf,
                            "pretrade_rr": round(rr, 2) if rr is not None else None,
                            "pretrade_rr_ok": rr is not None and rr >= 1.2,
                            "pretrade_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "approval_payload_hash": approval_payload_hash,
                            "approval_reason": approval_reason,
                        }
                        review_packet = build_review_packet(
                            trade,
                            market_data=market_data,
                            risk_policy={
                                "position_sizing_cap": getattr(cfg, "MAX_QTY", None),
                                "time_window_validity_sec": getattr(trade, "validity_sec", None),
                                "allow_reason": "manual_approval_required",
                            },
                        )
                        review_packet_text = format_review_packet(review_packet)
                        validation["review_packet"] = review_packet
                        validation["review_packet_text"] = review_packet_text
                        queued, trade = _queue_review_candidate(
                            trade,
                            extra=dict(validation, **{"tier": "MAIN"}),
                            reject_source="orchestrator_manual_review",
                        )
                        if not queued:
                            try:
                                update_execution(trade.trade_id, {"veto_reasons": ["unresolved_contract"]})
                            except Exception:
                                pass
                            continue
                        logger.info("review_queue_trade_queued trade_id=%s", trade.trade_id)
                        try:
                            send_telegram_message(review_packet_text)
                        except Exception:
                            pass
                        try:
                            audit_append(
                                {
                                    "event": "APPROVAL_REVIEW_PACKET",
                                    "trade_id": trade.trade_id,
                                    "symbol": trade.symbol,
                                    "strategy": trade.strategy,
                                    "review_packet": review_packet,
                                    "approval_payload_hash": approval_payload_hash,
                                    "approval_reason": approval_reason,
                                    "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                                }
                            )
                        except Exception:
                            pass
                        try:
                            update_execution(trade.trade_id, {"veto_reasons": [f"manual_approval_pending:{approval_reason}"]})
                        except Exception:
                            pass
                        continue

                    # Phase B: Risk validation
                    exposure_snapshot = self._refresh_exposure_snapshot()
                    risk_decision = self.risk_engine.evaluate_trade(
                        self.portfolio,
                        trade=trade,
                        exposure_state=exposure_snapshot,
                    )
                    allowed = bool(risk_decision.allowed)
                    reason = str(risk_decision.reason)
                    reason_code = str(risk_decision.reason_code)
                    if not allowed:
                        logger.warning("risk_engine_trade_blocked reason=%s", reason)
                        if reason.lower().startswith("daily loss"):
                            risk_halt.set_halt("Daily loss limit hit")
                            send_telegram_message("Auto-halt: daily loss limit hit.")
                        try:
                            self._decision_traces.append(
                                {
                                    "run_id": f"{trade.trade_id}-risk",
                                    "symbol": sym,
                                    "ts": now_utc_epoch(),
                                    "inputs_snapshot": {
                                        "symbol": sym,
                                        "instrument_id": self._instrument_id(trade),
                                    },
                                    "features_snapshot": {},
                                    "score_breakdown": {
                                        "confidence": getattr(trade, "confidence", None),
                                        "trade_score": getattr(trade, "trade_score", None),
                                    },
                                    "gate_results": {
                                        "risk_engine_allowed": False,
                                        "exposure_snapshot": exposure_snapshot,
                                    },
                                    "final_decision": "BLOCKED",
                                    "reasons": [str(reason)],
                                }
                            )
                        except Exception:
                            pass
                        try:
                            update_execution(
                                trade.trade_id,
                                {
                                    "risk_allowed": 0,
                                    "risk_reason": reason,
                                    "risk_reason_code": reason_code,
                                    "veto_reasons": [reason_code],
                                },
                            )
                        except Exception:
                            pass
                        continue
                    else:
                        try:
                            update_execution(
                                trade.trade_id,
                                {
                                    "risk_allowed": 1,
                                    "risk_reason": reason,
                                    "risk_reason_code": reason_code,
                                },
                            )
                        except Exception:
                            pass

                    # Phase B: Portfolio-level allocator (correlation + factor exposure + stress)
                    alloc = self.portfolio_allocator.allocate(trade, self.portfolio, market_data, self.last_md_by_symbol)
                    if not alloc.allowed:
                        logger.warning("portfolio_allocator_trade_blocked reason=%s", alloc.reason)
                        try:
                            update_execution(trade.trade_id, {"veto_reasons": [alloc.reason]})
                        except Exception:
                            pass
                        continue
                    try:
                        detail = trade.trade_score_detail or {}
                        detail = {**detail, "portfolio_alloc": alloc.report}
                        trade = replace(trade, trade_score_detail=detail)
                    except Exception:
                        pass
                    try:
                        current = alloc.report.get("current_exposure", {}) if isinstance(alloc.report, dict) else {}
                        update_execution(trade.trade_id, {
                            "delta_exposure": current.get("delta"),
                            "gamma_exposure": current.get("gamma"),
                            "vega_exposure": current.get("vega"),
                            "open_risk": self._open_risk(),
                        })
                    except Exception:
                        pass

                    # Risk-based sizing
                    lot_size = getattr(cfg, "LOT_SIZE", {}).get(trade.symbol, 1)
                    current_vol = (market_data.get("atr", 0) / market_data.get("ltp", 1)) if market_data.get("ltp") else None
                    streak = self.loss_streak.get(trade.symbol, 0)
                    sized_qty = self.risk_engine.size_trade(trade, self.portfolio["capital"], lot_size, current_vol=current_vol, loss_streak=streak)
                    final_qty = min(sized_qty, alloc.max_qty) if alloc.max_qty else sized_qty
                    if getattr(cfg, "LIVE_PILOT_MODE", False):
                        final_qty = min(final_qty, int(getattr(cfg, "LIVE_MAX_LOTS", 1)))
                    if final_qty <= 0:
                        logger.warning("portfolio_allocator_trade_blocked reason=qty_after_allocation_zero")
                        continue
                    # RL sizing agent (shadow or live)
                    if getattr(cfg, "RL_ENABLED", False):
                        mult = 1.0
                        feats = None
                        if self.rl_size_agent:
                            try:
                                feats = build_features(trade, market_data, self.risk_state, self.portfolio, self.last_md_by_symbol)
                                mult = self.rl_size_agent.select_multiplier(feats, explore=False)
                            except Exception:
                                mult = 1.0
                                feats = None
                        try:
                            update_execution(trade.trade_id, {"action_size_multiplier": mult})
                        except Exception:
                            pass
                        if getattr(cfg, "RL_SHADOW_ONLY", True):
                            # log shadow decision, no sizing change
                            try:
                                with open(str(logs_dir() / "rl_size_shadow.jsonl"), "a") as f:
                                    f.write(json.dumps({
                                        "timestamp": time.time(),
                                        "trade_id": trade.trade_id,
                                        "symbol": trade.symbol,
                                        "baseline_qty": final_qty,
                                        "suggested_qty": int(round(final_qty * mult)),
                                        "multiplier": mult,
                                        "features": feats
                                    }) + "\n")
                            except Exception:
                                pass
                        else:
                            final_qty = int(round(final_qty * mult))
                            if final_qty <= 0:
                                logger.warning("rl_size_trade_blocked reason=qty_after_rl_sizing_zero")
                                continue
                    trade = replace(trade, qty=final_qty, capital_at_risk=round((trade.entry_price - trade.stop_loss) * final_qty * lot_size, 2))
                    
                    # Phase B: Split Quote Freshness & Just-In-Time Revalidation
                    final_executable_quote_age = None
                    try:
                        from core.tick_store import get_last_tick
                        from core.market_data import get_token_for_symbol
                        token = get_token_for_symbol(trade.symbol)
                        if token:
                            tick = get_last_tick(token)
                            if tick and tick.get("ts_epoch"):
                                final_executable_quote_age = time.time() - float(tick.get("ts_epoch"))
                    except Exception as e:
                        logger.warning("jit_quote_revalidation_failed error=%s", e)
                        
                    if final_executable_quote_age is not None and final_executable_quote_age > 2.5:
                        logger.warning("execution_guard_trade_blocked reason=stale_final_executable_quote age=%.2f", final_executable_quote_age)
                        try:
                            blocked_reasons = list(getattr(trade, "tradable_reasons_blocking", []) or [])
                            blocked_reasons.append("stale_final_executable_quote")
                            source_flags = dict(getattr(trade, "source_flags", {}) or {})
                            source_flags["risk_guard_passed"] = False
                            blocked_trade = replace(
                                trade,
                                tradable=False,
                                tradable_reasons_blocking=blocked_reasons,
                                source_flags=source_flags,
                            )
                            ticket = self._build_trade_ticket(blocked_trade, market_data)
                            send_trade_ticket(ticket)
                        except Exception:
                            pass
                        try:
                            update_execution(
                                trade.trade_id,
                                {
                                    "exec_guard_allowed": 0,
                                    "exec_guard_reason": "stale_final_executable_quote",
                                    "exec_guard_reason_code": "stale_quote",
                                    "veto_reasons": ["stale_quote"],
                                },
                            )
                        except Exception:
                            pass
                        continue

                    # Phase B: Execution guard (after sizing)
                    guard_decision = self.execution_guard.evaluate(
                        trade,
                        self.portfolio,
                        trade.regime,
                        market_data=market_data,
                        mode=getattr(cfg, "EXECUTION_MODE", "SIM"),
                    )
                    approved = bool(guard_decision.allowed)
                    reason = str(guard_decision.reason)
                    reason_code = str(guard_decision.reason_code)
                    if not approved:
                        logger.warning("execution_guard_trade_blocked reason=%s", reason)
                        try:
                            blocked_reasons = list(getattr(trade, "tradable_reasons_blocking", []) or [])
                            blocked_reasons.append(f"risk_guard_failed:{reason_code}")
                            source_flags = dict(getattr(trade, "source_flags", {}) or {})
                            source_flags["risk_guard_passed"] = False
                            blocked_trade = replace(
                                trade,
                                tradable=False,
                                tradable_reasons_blocking=blocked_reasons,
                                source_flags=source_flags,
                            )
                            ticket = self._build_trade_ticket(blocked_trade, market_data)
                            send_trade_ticket(ticket)
                        except Exception:
                            pass
                        try:
                            update_execution(
                                trade.trade_id,
                                {
                                    "exec_guard_allowed": 0,
                                    "exec_guard_reason": reason,
                                    "exec_guard_reason_code": reason_code,
                                    "veto_reasons": [reason_code],
                                },
                            )
                        except Exception:
                            pass
                        continue
                    else:
                        try:
                            update_execution(
                                trade.trade_id,
                                {
                                    "exec_guard_allowed": 1,
                                    "exec_guard_reason": reason,
                                    "exec_guard_reason_code": reason_code,
                                    "planning_only": bool(guard_decision.planning_only),
                                    "cycle_processing_latency_ms": (time.perf_counter() - loop_start_time) * 1000.0 if 'loop_start_time' in locals() else None,
                                    "final_quote_revalidation_age_ms": final_executable_quote_age * 1000.0 if final_executable_quote_age else None,
                                },
                            )
                        except Exception:
                            pass
                        try:
                            source_flags = dict(getattr(trade, "source_flags", {}) or {})
                            source_flags["risk_guard_passed"] = True
                            source_flags["execution_guard_mode"] = guard_decision.mode
                            source_flags["execution_guard_planning_only"] = bool(guard_decision.planning_only)
                            trade = replace(trade, source_flags=source_flags)
                        except Exception:
                            pass
                        try:
                            size_mult = float((guard_decision.context or {}).get("size_multiplier", 1.0))
                        except Exception:
                            size_mult = 1.0
                        if size_mult < 1.0:
                            bounded_mult = max(0.0, min(1.0, float(size_mult)))
                            reduced_qty = int(round(float(trade.qty) * bounded_mult))
                            if reduced_qty <= 0:
                                logger.warning("execution_guard_trade_blocked reason=regime_monitor_qty_zero")
                                try:
                                    update_execution(
                                        trade.trade_id,
                                        {
                                            "exec_guard_allowed": 0,
                                            "exec_guard_reason": "regime_monitor_size_multiplier_zero_qty",
                                            "exec_guard_reason_code": "REGIME_MONITOR_SIZE_MULTIPLIER_ZERO_QTY",
                                            "veto_reasons": ["REGIME_MONITOR_SIZE_MULTIPLIER_ZERO_QTY"],
                                            "regime_size_multiplier": bounded_mult,
                                        },
                                    )
                                except Exception:
                                    pass
                                continue
                            if reduced_qty < int(trade.qty):
                                lot_size = getattr(cfg, "LOT_SIZE", {}).get(trade.symbol, 1)
                                try:
                                    trade = replace(
                                        trade,
                                        qty=int(reduced_qty),
                                        capital_at_risk=round(
                                            (trade.entry_price - trade.stop_loss) * int(reduced_qty) * lot_size, 2
                                        ),
                                    )
                                except Exception:
                                    pass
                                try:
                                    update_execution(
                                        trade.trade_id,
                                        {
                                            "regime_size_multiplier": bounded_mult,
                                            "qty_before_regime_multiplier": int(final_qty),
                                            "qty_after_regime_multiplier": int(reduced_qty),
                                        },
                                    )
                                except Exception:
                                    pass

                    slippage_decision = evaluate_slippage_budget(
                        trade,
                        market_data,
                        self.execution_engine,
                    )
                    if not bool(slippage_decision.allowed):
                        logger.warning("slippage_guard_trade_blocked reason=%s", slippage_decision.reason_code)
                        try:
                            append_reject_reasons(
                                symbol=trade.symbol,
                                strategy=trade.strategy,
                                reasons=[str(slippage_decision.reason_code)],
                                mode=getattr(cfg, "EXECUTION_MODE", "SIM"),
                                source="slippage_guard",
                                extra={
                                    "decision_stage": "execution:slippage_guard",
                                    "decision_explain": "Trade blocked due to slippage budget evaluation",
                                    "decision_blockers": [str(slippage_decision.reason_code)],
                                    "expected_slippage_bps": slippage_decision.expected_slippage_bps,
                                    "budget_bps": slippage_decision.budget_bps,
                                },
                            )
                        except Exception:
                            pass
                        try:
                            update_execution(
                                trade.trade_id,
                                {
                                    "slippage_budget_allowed": 0,
                                    "slippage_budget_reason": str(slippage_decision.reason_code),
                                    "veto_reasons": [str(slippage_decision.reason_code)],
                                },
                            )
                        except Exception:
                            pass
                        continue
                    try:
                        update_execution(
                            trade.trade_id,
                            {
                                "slippage_budget_allowed": 1,
                                "slippage_budget_reason": str(slippage_decision.reason_code),
                                "slippage_budget_bps": slippage_decision.budget_bps,
                                "slippage_expected_bps": slippage_decision.expected_slippage_bps,
                            },
                        )
                    except Exception:
                        pass

                    # Price confirmation entry (avoid false starts)
                    if getattr(cfg, "PRICE_CONFIRM_ENABLE", True):
                        if getattr(cfg, "PRICE_CONFIRM_VWAP", True):
                            vwap = market_data.get("vwap", trade.entry_price)
                            ltp = market_data.get("ltp", 0)
                            if trade.side == "BUY" and ltp < vwap:
                                continue
                            if trade.side == "SELL" and ltp > vwap:
                                continue
                        else:
                            confirm = getattr(cfg, "PRICE_CONFIRM_PCT", 0.001)
                            if trade.side == "BUY" and market_data.get("ltp", 0) < trade.entry_price * (1 + confirm):
                                continue
                            if trade.side == "SELL" and market_data.get("ltp", 0) > trade.entry_price * (1 - confirm):
                                continue

                    if bool(getattr(cfg, "EXECUTION_OPTIMIZER_ENABLE", True)):
                        playbook_name = (
                            str(
                                getattr(trade, "selected_playbook", None)
                                or getattr(trade, "decision_playbook", None)
                                or ""
                            )
                            .strip()
                            .lower()
                        )
                        execution_plan = build_execution_plan(
                            {
                                "trade_id": trade.trade_id,
                                "symbol": trade.symbol,
                                "selected_playbook": playbook_name,
                                "spread_pct": market_data.get("spread_pct"),
                                "liquidity_score": getattr(trade, "liquidity_score", None) or market_data.get("liquidity_score"),
                                "execution_quality_score": getattr(trade, "execution_quality_score", None),
                                "execution_entry": getattr(trade, "entry_price", None),
                                "entry": getattr(trade, "entry_price", None),
                                "stop_loss": getattr(trade, "stop_loss", None),
                                "target": getattr(trade, "target", None),
                            },
                            {
                                "urgency": 0.8 if playbook_name == "breakout_continuation" else 0.4,
                            },
                        )

                        if not bool(execution_plan.should_execute):
                            logger.warning(
                                "execution_optimizer_blocked trade_id=%s symbol=%s reason=%s effective_rr=%.3f",
                                trade.trade_id,
                                trade.symbol,
                                execution_plan.reason,
                                float(execution_plan.effective_rr),
                            )
                            try:
                                update_execution(
                                    trade.trade_id,
                                    {
                                        "execution_optimizer_allowed": 0,
                                        "execution_optimizer_reason": execution_plan.reason,
                                        "execution_optimizer_effective_rr": float(execution_plan.effective_rr),
                                        "veto_reasons": [f"execution_optimizer:{execution_plan.reason}"],
                                    },
                                )
                            except Exception:
                                pass
                            continue

                        try:
                            update_execution(
                                trade.trade_id,
                                {
                                    "execution_optimizer_allowed": 1,
                                    "execution_optimizer_reason": execution_plan.reason,
                                    "execution_optimizer_effective_rr": float(execution_plan.effective_rr),
                                    "execution_order_style": execution_plan.order_style,
                                    "execution_expected_slippage_bps": float(execution_plan.expected_slippage_bps),
                                },
                            )
                        except Exception:
                            pass
                        try:
                            source_flags = dict(getattr(trade, "source_flags", {}) or {})
                            source_flags["execution_plan"] = {
                                "should_execute": bool(execution_plan.should_execute),
                                "order_style": str(execution_plan.order_style),
                                "entry_limit": execution_plan.entry_limit,
                                "max_chase_pct": float(execution_plan.max_chase_pct),
                                "timeout_sec": float(execution_plan.timeout_sec),
                                "replace_limit": int(execution_plan.replace_limit),
                                "expected_slippage_bps": float(execution_plan.expected_slippage_bps),
                                "effective_rr": float(execution_plan.effective_rr),
                                "reason": str(execution_plan.reason),
                                "telemetry": dict(execution_plan.telemetry or {}),
                            }
                            trade = replace(trade, source_flags=source_flags)
                        except Exception:
                            pass

                    # Execute trade (simulation only)
                    # Require real quotes (no synthetic bid/ask)
                    if trade.instrument == "OPT":
                        bid = trade.opt_bid
                        ask = trade.opt_ask
                        if not bid or not ask or not getattr(trade, "quote_ok", True):
                            log_fill_quality({
                                "ts": time.time(),
                                "trade_id": getattr(trade, "trade_id", None),
                                "symbol": getattr(trade, "symbol", None),
                                "instrument": getattr(trade, "instrument", None),
                                "side": getattr(trade, "side", None),
                                "decision_bid": bid,
                                "decision_ask": ask,
                                "decision_mid": None,
                                "decision_spread": None,
                                "limit_price": getattr(trade, "entry_price", None),
                                "fill_price": None,
                                "not_filled_reason": "missing_option_quotes",
                                "time_to_fill": None,
                                "slippage_vs_mid": None,
                            })
                            logger.warning("execution_engine_skip reason=missing_invalid_option_quotes")
                            continue
                    else:
                        bid = market_data.get("bid")
                        ask = market_data.get("ask")
                        if not bid or not ask:
                            log_fill_quality({
                                "ts": time.time(),
                                "trade_id": getattr(trade, "trade_id", None),
                                "symbol": getattr(trade, "symbol", None),
                                "instrument": getattr(trade, "instrument", None),
                                "side": getattr(trade, "side", None),
                                "decision_bid": bid,
                                "decision_ask": ask,
                                "decision_mid": None,
                                "decision_spread": None,
                                "limit_price": getattr(trade, "entry_price", None),
                                "fill_price": None,
                                "not_filled_reason": "missing_index_quotes",
                                "time_to_fill": None,
                                "slippage_vs_mid": None,
                            })
                            logger.warning("execution_engine_skip reason=missing_live_quotes")
                            continue
                    volume = market_data.get("volume")
                    depth = None
                    if trade.instrument_token:
                        d = depth_store.get(trade.instrument_token)
                        depth = d.get("depth") if d else None
                    bid0 = bid
                    ask0 = ask
                    def _snapshot():
                        try:
                            if trade.instrument_token:
                                d = depth_store.get(trade.instrument_token)
                                if d and d.get("depth"):
                                    dep = d.get("depth")
                                    b = dep.get("buy", [{}])[0].get("price", bid0)
                                    a = dep.get("sell", [{}])[0].get("price", ask0)
                                    return {"bid": b, "ask": a, "ts": time.time(), "depth": dep}
                        except Exception:
                            pass
                        return {"bid": bid0, "ask": ask0, "ts": time.time(), "depth": depth}

                    execution_stage_start = time.perf_counter()
                    filled, fill_price, fill_report = self.execution_router.execute(
                        trade,
                        bid,
                        ask,
                        volume,
                        depth=depth,
                        snapshot_fn=_snapshot,
                        spread_pct=market_data.get("spread_pct"),
                        depth_imbalance=market_data.get("depth_imbalance"),
                        vol_z=market_data.get("vol_z"),
                    )
                    execution_route_ms += (time.perf_counter() - execution_stage_start) * 1000.0
                    try:
                        self.risk_state.record_fill(filled)
                    except Exception:
                        pass
                    if not filled:
                        if fill_report and fill_report.get("reason_if_aborted"):
                            logger.warning("execution_engine_fill_aborted reason=%s", fill_report.get("reason_if_aborted"))
                        else:
                            logger.info("execution_engine_limit_order_not_filled")
                        try:
                            update_execution(trade.trade_id, {
                                "filled_bool": 0,
                                "fill_price": None,
                                "time_to_fill": fill_report.get("time_to_fill") if fill_report else None,
                                "slippage_vs_mid": fill_report.get("slippage_vs_mid") if fill_report else None,
                                "veto_reasons": [fill_report.get("reason_if_aborted")] if fill_report else ["not_filled"],
                            })
                        except Exception:
                            pass
                        if self.decision_store is not None and decision_id:
                            try:
                                self.decision_store.update_status(
                                    decision_id,
                                    "rejected",
                                    reject_reasons=[fill_report.get("reason_if_aborted") if fill_report else "not_filled"],
                                )
                            except Exception as exc:
                                logger.warning("decision_store_update_not_filled_failed err=%s", exc)
                        continue
                    trade = replace(trade, entry_price=fill_price)
                    try:
                        update_execution(trade.trade_id, {
                            "filled_bool": 1,
                            "fill_price": fill_price,
                            "time_to_fill": fill_report.get("time_to_fill") if fill_report else None,
                            "slippage_vs_mid": fill_report.get("slippage_vs_mid") if fill_report else None,
                        })
                    except Exception:
                        pass
                    if self.decision_store is not None and decision_id:
                        try:
                            self.decision_store.update_status(decision_id, "filled")
                        except Exception as exc:
                            logger.warning("decision_store_update_filled_failed err=%s", exc)

                    self.portfolio["trades"].append(trade)
                    self.portfolio["capital"] -= getattr(trade, "capital_at_risk", 0)
                    self.portfolio["trades_today"] += 1
                    self.last_trade_time[sym] = time.time()
                    if getattr(cfg, "BEST_TRADE_PER_DAY", True):
                        self.best_trade_logged = True
                    if getattr(cfg, "BEST_TRADE_PER_REGIME", True):
                        rkey = trade.regime or "NEUTRAL"
                        self.best_trade_by_regime[rkey] = True

                    # Log trade
                    extra = {}
                    if market_data.get("option_chain"):
                        for opt in market_data["option_chain"]:
                            if opt.get("strike") == trade.strike and opt.get("type") in ("CE", "PE"):
                                if "micro_pred" in opt:
                                    extra["micro_pred"] = opt["micro_pred"]
                                break
                    if getattr(trade, "model_version", None):
                        extra["model_version"] = getattr(trade, "model_version", None)
                    if getattr(trade, "shadow_model_version", None):
                        extra["shadow_model_version"] = getattr(trade, "shadow_model_version", None)
                    if getattr(trade, "shadow_confidence", None) is not None:
                        extra["shadow_confidence"] = getattr(trade, "shadow_confidence", None)
                    if getattr(trade, "alpha_confidence", None) is not None:
                        extra["alpha_confidence"] = getattr(trade, "alpha_confidence", None)
                    if getattr(trade, "alpha_uncertainty", None) is not None:
                        extra["alpha_uncertainty"] = getattr(trade, "alpha_uncertainty", None)
                    if getattr(trade, "size_mult", None) is not None:
                        extra["size_mult"] = getattr(trade, "size_mult", None)
                    # Paper strict: mark aux/quick/scalp/zero-hero so they don't affect main perf stats
                    if str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper() == "PAPER" and getattr(cfg, "PAPER_STRICT_MODE", False):
                        if getattr(trade, "tier", "MAIN") != "MAIN" or trade.strategy in (
                            "SCALP",
                            "ZERO_HERO",
                            "ZERO_HERO_EXPIRY",
                            getattr(cfg, "STRATEGY_ZERO_TO_HERO", "ZERO_TO_HERO"),
                        ) or trade.strategy.startswith("QUICK"):
                            extra["paper_aux"] = True
                    if fill_report:
                        extra["fill_quality"] = fill_report
                        try:
                            score = fill_report.get("execution_quality_score")
                            if score is not None:
                                extra["execution_quality_score"] = score
                                self.strategy_tracker.record_execution_quality(trade.strategy, score)
                        except Exception:
                            pass
                    try:
                        ledger_hash = record_governance(trade, market_data, self.risk_state, fill_report, extra=extra)
                        extra["ledger_hash"] = ledger_hash
                    except Exception:
                        pass
                    log_trade(trade, extra=extra)
                    self._track_open_trade(trade, market_data)

                    # Telegram alert (actionable trades only)
                    try:
                        ticket = self._build_trade_ticket(trade, market_data)
                        actionable, reason = ticket.is_actionable()
                        if not actionable:
                            self._log_identity_error(trade, {"reason": reason})
                        else:
                            send_trade_ticket(ticket)
                    except Exception:
                        pass

                feature_timing["symbol_loop_ms"] = _perf_ms(t0_sym_loop)
                latency_critical_path_end_perf = time.perf_counter()

                # Phase F: Check and retrain model if needed
                execution_mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).strip().upper()
                try:
                    feed_ok, feed_reasons = self._pilot_feed_ok()
                except Exception:
                    feed_ok, feed_reasons = False, ["feed_status_unavailable"]
                latency_action = self._latency_guard_action()
                skip_background_maintenance = _should_skip_background_maintenance_for_latency_guard(
                    latency_action=latency_action,
                    execution_mode=execution_mode,
                    feed_ok=feed_ok,
                )
                if skip_background_maintenance:
                    skip_reason = {
                        "event": "LATENCY_GUARD_BACKGROUND_MAINTENANCE_SKIP",
                        "action": latency_action,
                        "execution_mode": execution_mode,
                        "feed_ok": bool(feed_ok),
                        "feed_reasons": list(feed_reasons or []),
                        "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                    }
                    logger.warning(
                        "latency_guard_background_maintenance_skip action=%s execution_mode=%s feed_ok=%s feed_reasons=%s",
                        latency_action or "unknown",
                        execution_mode,
                        bool(feed_ok),
                        ",".join(str(x) for x in (feed_reasons or [])[:5]),
                    )
                    try:
                        audit_append(skip_reason)
                    except Exception:
                        pass
                else:
                    self.retrainer.update_model()

                    # Evaluate blocked paper trades
                    try:
                        self.blocked_tracker.update(self.predictor)
                    except Exception:
                        pass
                cycle_stage = "cycle_complete"

            except Exception as e:
                cycle_reason = f"cycle_exception:{type(e).__name__}"
                cycle_stage = "cycle_exception"
                cycle_error = f"{type(e).__name__}:{e}"
                cycle_blockers[cycle_reason] += 1
                logger.exception("orchestrator_cycle_error err=%s", e)
                tripped, cb_reason = self.circuit_breaker.record_error("CYCLE_EXCEPTION")
                if tripped:
                    cycle_reason = cb_reason or "CB_ERROR_STORM"
                    cycle_blockers[cycle_reason] += 1
                    try:
                        audit_append(
                            {
                                "event": "CIRCUIT_BREAKER_TRIP",
                                "reason": cycle_reason,
                                "detail": str(e),
                                "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                            }
                        )
                    except Exception as exc:
                        logger.warning("circuit_breaker_audit_error err=%s", type(exc).__name__)
                    try:
                        create_incident(
                            "SEV1",
                            cycle_reason,
                            {"detail": str(e), "desk_id": getattr(cfg, "DESK_ID", "DEFAULT")},
                        )
                    except Exception as exc:
                        logger.warning("circuit_breaker_incident_error err=%s", type(exc).__name__)
            finally:
                try:
                    latency_stats = _build_cycle_latency_snapshot(
                        latency_monitor=self.latency_monitor,
                        cycle_perf_start=cycle_perf_start,
                        critical_path_end_perf=latency_critical_path_end_perf,
                        feature_build_ms=feature_build_ms,
                        decision_build_ms=decision_build_ms,
                        execution_route_ms=execution_route_ms,
                    )
                    self._last_latency_stats = latency_stats
                    cycle_latency = dict(latency_stats.get("cycle") or {})
                    background_overhead_ms = float(cycle_latency.get("background_overhead_ms") or 0.0)
                    background_warn_ms = max(
                        0.0, float(getattr(cfg, "LATENCY_GUARD_BACKGROUND_OVERHEAD_WARN_MS", 250.0))
                    )
                    if background_warn_ms > 0.0 and background_overhead_ms >= background_warn_ms:
                        logger.warning(
                            "latency_background_overhead critical_path_ms=%.1f full_cycle_ms=%.1f background_overhead_ms=%.1f guard_total_ms=%.1f use_critical_path_only=%s",
                            float(cycle_latency.get("critical_path_ms") or 0.0),
                            float(cycle_latency.get("full_cycle_ms") or 0.0),
                            background_overhead_ms,
                            float(cycle_latency.get("guard_total_ms") or 0.0),
                            bool(cycle_latency.get("guard_uses_critical_path")),
                        )
                    market_open = False
                    if isinstance(market_data_list, list) and market_data_list:
                        market_open = any(bool((row or {}).get("market_open")) for row in market_data_list)
                    if not market_open:
                        market_open = bool(is_market_open_ist())
                    self._evaluate_latency_guard(
                        market_open=market_open,
                        monitor_stats=latency_stats,
                    )
                except Exception as latency_exc:
                    logger.warning("latency_guard_cycle_evaluation_failed err=%s", latency_exc)
                if not cycle_market_open:
                    try:
                        cycle_market_open = bool(is_market_open_ist())
                    except Exception:
                        cycle_market_open = False
                if not cycle_market_open:
                    cycle_market_mode = "OFFHOURS"
                suggestion_rows_after = 0
                visible_counts_after = {}
                row_delta = max(0, int(suggestion_rows_after) - int(suggestion_rows_before))
                visible_delta = max(
                    0,
                    int(visible_counts_after.get("visible_suggestion_count") or 0)
                    - int(visible_counts_before.get("visible_suggestion_count") or 0),
                )
                cycle_suggestion_count = max(
                    0,
                    int(row_delta),
                    int(visible_delta),
                    int(cycle_candidates_enqueued),
                )
                cycle_candidates_enqueued = max(int(cycle_candidates_enqueued), int(cycle_suggestion_count))
                logger.debug(
                    "cycle_suggestion_accounting suggestion_rows_before=%s suggestion_rows_after=%s row_delta=%s visible_delta=%s cycle_suggestion_count=%s cycle_candidates_seen=%s cycle_candidates_enqueued=%s",
                    suggestion_rows_before,
                    suggestion_rows_after,
                    row_delta,
                    visible_delta,
                    cycle_suggestion_count,
                    cycle_candidates_seen,
                    cycle_candidates_enqueued,
                )
                try:
                    config_snapshot = decision_config_snapshot()
                    config_snapshot.update(self._runtime_safety_snapshot())
                    self._write_cycle_reports(
                        cycle_reason=cycle_reason,
                        decision_traces=list(self._decision_traces),
                        config_snapshot=config_snapshot,
                    )
                except Exception as report_exc:
                    logger.warning("orchestrator_report_error err=%s", report_exc)
                t_post_sym = time.perf_counter()
                try:
                    t_stat = time.perf_counter()
                    self._write_cycle_status_files(
                        cycle_ok=not bool(cycle_error),
                        cycle_stage=cycle_stage,
                        cycle_reason=cycle_reason,
                        last_error=cycle_error,
                        market_mode=cycle_market_mode,
                        market_open=cycle_market_open,
                        symbols_scanned=len(cycle_symbols_scanned),
                        trade_build_attempts=cycle_trade_build_attempts,
                        candidates_seen=cycle_candidates_seen,
                        candidates_blocked=cycle_candidates_blocked,
                        candidates_enqueued=cycle_candidates_enqueued,
                        blocker_counts=cycle_blockers,
                        suggestion_count=cycle_suggestion_count,
                    )
                    feature_timing["GAP_write_status_ms"] = _perf_ms(t_stat)
                except Exception as status_exc:
                    logger.warning("cycle_status_write_error err=%s", status_exc)
                try:
                    t_fun = time.perf_counter()
                    write_pipeline_funnel(
                        _build_pipeline_funnel_payload(
                            universe=len(cycle_symbols_scanned),
                            candidates=int(cycle_candidate_pool_count),
                            scored=int(cycle_scored_candidate_count),
                            visible_counts=visible_counts_after,
                            emitted=int(cycle_suggestion_count),
                            returned=int(cycle_candidates_seen),
                        )
                    )
                    feature_timing["GAP_write_funnel_ms"] = _perf_ms(t_fun)
                except Exception as funnel_exc:
                    logger.warning("pipeline_funnel_write_failed err=%s", funnel_exc)
                try:
                    t_truth = time.perf_counter()
                    feed_truth_payload_for_top = dict(feed_truth_payload)
                    for big_key in ("missing_option_symbols", "option_last_tick_age_by_symbol", "option_tokens_resolved_count_by_symbol", "option_tokens_subscribed_count_by_symbol", "option_ticks_received_count_by_symbol", "last_option_tick_ts_by_symbol", "option_feed_block_reason_by_symbol", "option_active_blockers_by_symbol", "missing_option_tokens_count_by_symbol", "subscribed_tokens_count_by_symbol"):
                        feed_truth_payload_for_top.pop(big_key, None)
                    feature_timing["GAP_feed_truth_copy_ms"] = _perf_ms(t_truth)

                    t_top = time.perf_counter()
                    top_payload = _build_top_opportunities_payload(
                        candidates=list(cycle_ranked_candidates),
                        executable_top_n=int(getattr(cfg, "TOP_EXECUTABLE_OPPORTUNITIES_N", 5)),
                        advisory_top_n=int(getattr(cfg, "TOP_ADVISORY_OPPORTUNITIES_N", 5)),
                        active_trade=self._phase2_active_trade if isinstance(self._phase2_active_trade, dict) else None,
                        execution_truth_context=build_execution_truth_context(
                            feed_truth=feed_truth_payload_for_top,
                            latency_guard=dict(getattr(self, "_latency_guard_state", {}) or {}),
                        ),
                    )
                    feature_timing["GAP_build_top_ms"] = _perf_ms(t_top)

                    t_root = time.perf_counter()
                    try:
                        root_cause_payload = build_candidate_handoff_root_cause_payload(
                            cycle_ts_epoch=float(time.time()),
                            strategy_generated_count=int(cycle_candidate_pool_count),
                            phase2_raw_candidates=[cand for cand in list(cycle_ranked_candidates or []) if isinstance(cand, dict)],
                            phase2_ranked_count=int(top_payload.get("phase2_ranked_count") or 0),
                        )
                        write_candidate_handoff_root_cause_latest(payload=root_cause_payload)
                    except Exception as handoff_exc:
                        logger.warning("candidate_handoff_root_cause_write_failed err=%s", handoff_exc)
                    feature_timing["GAP_build_root_cause_ms"] = _perf_ms(t_root)
                    feature_timing["GAP_post_symbol_loop_ms"] = _perf_ms(t_post_sym)
                    try:
                        t_heavy_io = time.perf_counter()
                        # Evidence-only: summarize why no-trade/no-executable is happening without mutating decisions.
                        phase2_rejection_payload = _read_json_dict(logs_dir() / "phase2_rejection_latest.json")
                        feed_truth_payload_for_notrade = dict(feed_truth_payload)
                        indicator_payload = _read_json_dict(runtime_dir() / "live_indicator_readiness_latest.json")
                        try:
                            # Refresh indicator readiness artifact from current cycle market snapshots so
                            # it cannot remain stale when the orchestrator is actively running.
                            indicator_report = build_live_indicator_readiness_report(
                                [row for row in list(readiness_market_data or []) if isinstance(row, dict)],
                                now_epoch=float(time.time()),
                                warmup_min_bars=int(getattr(cfg, "WARMUP_MIN_BARS", 50)),
                                source="orchestrator_live_indicator_readiness_v2",
                            )
                            write_live_indicator_readiness_latest(indicator_report, now_epoch=float(time.time()))
                            indicator_payload = _read_json_dict(runtime_dir() / "live_indicator_readiness_latest.json")
                        except Exception:
                            pass
                        regime_by_symbol = {}
                        regime_gate_reasons = {}
                        try:
                            for md in list(market_data_list or []):
                                if not isinstance(md, dict):
                                    continue
                                sym = str(md.get("symbol") or "").strip().upper()
                                if not sym:
                                    continue
                                unstable = md.get("unstable_reasons") if isinstance(md.get("unstable_reasons"), list) else []
                                if unstable:
                                    regime_by_symbol[sym] = {
                                        "primary_regime": md.get("primary_regime") or md.get("regime"),
                                        "regime_entropy": md.get("regime_entropy"),
                                        "regime_prob_max": md.get("regime_prob_max") or md.get("regime_probs_max"),
                                        "unstable_reasons": unstable,
                                    }
                            if regime_by_symbol:
                                regime_gate_reasons["REGIME_UNSTABLE"] = len(regime_by_symbol)
                        except Exception:
                            regime_by_symbol = {}
                            regime_gate_reasons = {}
                        notrade_payload = build_notrade_reason_truth_payload(
                            candidate_handoff=root_cause_payload if isinstance(root_cause_payload, dict) else {},
                            phase2_rejection=phase2_rejection_payload,
                            feed_truth=feed_truth_payload_for_notrade,
                            top_opportunities=top_payload,
                            cycle_blockers=dict(cycle_blockers),
                            indicator_readiness=indicator_payload,
                            regime_truth={"by_symbol": regime_by_symbol, "gate_reasons": regime_gate_reasons},
                            latency_guard=dict(getattr(self, "_latency_guard_state", {}) or {}),
                        )
                        write_notrade_reason_truth_latest(payload=notrade_payload)
                        feature_timing["heavy_io_telemetry_ms"] = _perf_ms(t_heavy_io)
                    except Exception as notrade_exc:
                        logger.warning("notrade_reason_truth_write_failed err=%s", notrade_exc)
                    t_rq = time.perf_counter()
                    try:
                        rq_payload = build_ranking_quality_evidence_payload(
                            candidates=[cand for cand in list(cycle_ranked_candidates or []) if isinstance(cand, dict)],
                            phase2_state=str(top_payload.get("phase2_state") or ""),
                            cycle_primary_reason=str(top_payload.get("cycle_primary_reason") or "") or None,
                            phase2_min_enter_score=float(getattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.70) or 0.70),
                        )
                        write_ranking_quality_latest(payload=rq_payload)
                    except Exception as rq_exc:
                        logger.warning("ranking_quality_write_failed err=%s", rq_exc)
                    feature_timing["GAP_ranking_quality_ms"] = _perf_ms(t_rq)
                    t_workload = time.perf_counter()
                    try:
                        pruned_md_list = []
                        for row in list(market_data_list or []):
                            if isinstance(row, dict):
                                p_row = dict(row)
                                for big_key in ("ohlc_bars", "candidate_tradingsymbols", "matched_tradingsymbols", "options", "chain_data", "call_chain", "put_chain", "candles"):
                                    p_row.pop(big_key, None)
                                pruned_md_list.append(p_row)

                        feed_runtime_payload = _read_json_dict(repo_logs_dir() / "feed_runtime_latest.json")
                        workload_payload = build_live_workload_payload(
                            execution_mode=str(getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM"),
                            market_open=bool(cycle_market_open),
                            market_data_list=pruned_md_list,
                            feed_runtime=feed_runtime_payload,
                            timing={
                                **(feature_timing if isinstance(feature_timing, dict) else {}),
                                "live_cycle_ms": float((time.perf_counter() - cycle_perf_start) * 1000.0),
                            },
                        )
                        write_live_workload_latest(payload=workload_payload)
                    except Exception as workload_exc:
                        logger.warning("live_workload_write_failed err=%s", workload_exc)
                    feature_timing["GAP_workload_payload_ms"] = _perf_ms(t_workload)
                    t0 = time.perf_counter()
                    try:
                        trace_payload = build_candidate_flow_trace_payload(
                            execution_mode=str(getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM"),
                            market_open=bool(cycle_market_open),
                            market_data_list=pruned_md_list,
                            cycle_blockers=dict(cycle_blockers),
                            indicator_readiness=indicator_payload,
                            regime_truth={"by_symbol": regime_by_symbol, "gate_reasons": regime_gate_reasons},
                            raw_candidate_count=int(cycle_candidate_pool_count),
                            phase2_input_candidate_count=int(len(cycle_ranked_candidates or [])),
                            latency_guard=dict(getattr(self, "_latency_guard_state", {}) or {}),
                            decision_gate_reason_by_symbol={
                                str(md.get("symbol") or "").strip().upper(): md.get("decision_gate_reason")
                                for md in list(market_data_list or [])
                                if isinstance(md, dict) and str(md.get("symbol") or "").strip()
                            },
                        )
                        write_candidate_flow_trace_latest(payload=trace_payload)
                    except Exception as trace_exc:
                        logger.warning("candidate_flow_trace_write_failed err=%s", trace_exc)
                    feature_timing["GAP_flow_trace_ms"] = _perf_ms(t0)

                    t0 = time.perf_counter()
                    try:
                        strategy_no_qualified_payload = build_strategy_no_qualified_reasons_payload(
                            execution_mode=str(getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM"),
                            market_open=bool(cycle_market_open),
                            market_data_list=pruned_md_list,
                            cycle_blockers=dict(cycle_blockers),
                            indicator_readiness=indicator_payload,
                            regime_truth={"by_symbol": regime_by_symbol, "gate_reasons": regime_gate_reasons},
                            strategy_attempts=[
                                row for row in list(cycle_strategy_no_qualified_attempts or []) if isinstance(row, dict)
                            ],
                            raw_candidate_count=int(cycle_candidate_pool_count),
                            phase2_input_candidate_count=int(len(cycle_ranked_candidates or [])),
                            latency_guard=dict(getattr(self, "_latency_guard_state", {}) or {}),
                        )
                        write_strategy_no_qualified_reasons_latest(payload=strategy_no_qualified_payload)
                    except Exception as strategy_no_qualified_exc:
                        logger.warning(
                            "strategy_no_qualified_reasons_write_failed err=%s",
                            strategy_no_qualified_exc,
                        )
                    feature_timing["GAP_strategy_no_qualified_ms"] = _perf_ms(t0)

                    t0 = time.perf_counter()
                    try:
                        starvation_payload = build_candidate_starvation_trace_payload(
                            execution_mode=str(getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM"),
                            market_open=bool(cycle_market_open),
                            market_data_list=pruned_md_list,
                            cycle_blockers=dict(cycle_blockers),
                            feed_runtime=feed_runtime_payload if isinstance(feed_runtime_payload, dict) else {},
                            candidate_starvation_snapshots=[
                                row for row in list(cycle_candidate_starvation_snapshots or []) if isinstance(row, dict)
                            ],
                            candidate_handoff_root_cause=root_cause_payload if isinstance(root_cause_payload, dict) else {},
                            phase2_rejection=phase2_rejection_payload if isinstance(phase2_rejection_payload, dict) else {},
                            previous_payload=candidate_starvation_last_payload if isinstance(candidate_starvation_last_payload, dict) else {},
                        )
                        write_candidate_starvation_trace_latest(payload=starvation_payload)
                        candidate_starvation_last_payload = dict(starvation_payload)
                        self._candidate_starvation_trace_last_payload = dict(starvation_payload)
                    except Exception as starvation_exc:
                        logger.warning("candidate_starvation_trace_write_failed err=%s", starvation_exc)
                    feature_timing["GAP_starvation_trace_ms"] = _perf_ms(t0)
                    self._phase2_active_trade = top_payload.pop("_phase2_next_active_trade", None)
                    t0 = time.perf_counter()
                    if cycle_candidate_handoff_snapshots:
                        for handoff_snapshot in cycle_candidate_handoff_snapshots:
                            try:
                                write_runtime_candidate_handoff_evidence(
                                    **handoff_snapshot,
                                    phase2_input_count=len(cycle_ranked_candidates),
                                    top_opportunities_payload=top_payload,
                                )
                            except Exception as handoff_exc:
                                logger.error("runtime_candidate_handoff_snapshot_write_failed symbol=%s err=%s", handoff_snapshot.get("symbol"), handoff_exc)
                    feature_timing["GAP_write_handoff_ms"] = _perf_ms(t0)

                    t0 = time.perf_counter()
                    try:
                        _write_ranked_pipeline_runtime_evidence(
                            top_payload=top_payload,
                            cycle_ranked_candidates=list(cycle_ranked_candidates or []),
                            market_open=bool(cycle_market_open),
                            feed_truth_payload=feed_truth_payload if isinstance(feed_truth_payload, dict) else {},
                            indicator_payload=indicator_payload if isinstance(indicator_payload, dict) else {},
                            cycle_blockers=dict(cycle_blockers),
                        )
                        try:
                            from core.candle_pipeline_diagnostics import emit_candle_pipeline_event
                            emit_candle_pipeline_event(
                                symbol="__CYCLE__", timeframe="cycle", stage="T10_CANDIDATE_EVALUATED",
                                source_event_ts=time.time(), bar_state="COMPLETED",
                                bar_count=int(cycle_candidate_pool_count),
                                producer="orchestrator.live_monitoring",
                                details={
                                    "evaluation_started": True,
                                    "evaluation_completed": True,
                                    "candidate_created": int(cycle_candidate_pool_count),
                                    "rankable": len(cycle_ranked_candidates),
                                    "executable": int(top_payload.get("top_executable_count") or 0),
                                    "blockers": dict(cycle_blockers),
                                    "readiness_state": top_payload.get("phase2_state"),
                                },
                            )
                            emit_candle_pipeline_event(
                                symbol="__CYCLE__", timeframe="cycle", stage="T11_RANKING_EVALUATED",
                                source_event_ts=time.time(), bar_state="COMPLETED",
                                bar_count=len(cycle_ranked_candidates),
                                producer="core.ranked_pipeline_evidence.write_ranked_pipeline_evidence",
                                details={
                                    "ranking_cycle_id": top_payload.get("cycle_id") or top_payload.get("generated_epoch"),
                                    "input_candidate_count": len(cycle_ranked_candidates),
                                    "rankable_count": int(top_payload.get("phase2_ranked_count") or 0),
                                    "executable_count": int(top_payload.get("top_executable_count") or 0),
                                    "ranked_count": len(cycle_ranked_candidates),
                                    "top_candidate_id": top_payload.get("phase2_selected_trade_id"),
                                    "ranking_completed": True,
                                    "blockers": dict(cycle_blockers),
                                },
                            )
                        except Exception:
                            pass
                    except Exception as ranked_pipeline_exc:
                        logger.error("[RANKED_PIPELINE_RUNTIME_ERROR] error=%s", ranked_pipeline_exc)
                    feature_timing["GAP_write_ranked_pipeline_ms"] = _perf_ms(t0)

                    t0 = time.perf_counter()
                    try:
                        lineage_cycle_id = str(
                            top_payload.get("cycle_id")
                            or top_payload.get("cycle_key")
                            or top_payload.get("session_id")
                            or top_payload.get("generated_epoch")
                            or ""
                        ).strip() or f"cycle_{int(cycle_perf_start)}"
                        lineage_rows: list[dict[str, Any]] = []
                        lineage_rows.extend(
                            {
                                **dict(row),
                                "stage": dict(row).get("stage") or "tradebuilder",
                                "stage_status": dict(row).get("stage_status") or ("blocked" if dict(row).get("reject_reason") else "passed"),
                                "source_stage": "tradebuilder",
                                "entry_path": dict(row).get("entry_path") or "strategy_to_tradebuilder",
                            }
                            for row in list(cycle_candidate_handoff_snapshots or [])
                            if isinstance(row, dict)
                        )
                        lineage_rows.extend(
                            {
                                **dict(row),
                                "stage": dict(row).get("stage") or "phase2",
                                "stage_status": dict(row).get("stage_status") or ("selected" if dict(row).get("top_opportunity") else "passed"),
                                "source_stage": "phase2",
                                "entry_path": dict(row).get("entry_path") or "phase2_direct",
                            }
                            for row in list(cycle_ranked_candidates or [])
                            if isinstance(row, dict)
                        )
                        if isinstance(top_payload, dict):
                            for key in ("top_executable_opportunities", "top_advisory_opportunities", "top_blocked_opportunities"):
                                for row in list(top_payload.get(key) or []):
                                    if isinstance(row, dict):
                                        candidate_row = dict(row)
                                        candidate_row.setdefault("stage", "top_opportunity")
                                        candidate_row.setdefault("stage_status", "selected" if key == "top_executable_opportunities" else "blocked")
                                        candidate_row.setdefault("top_opportunity", key == "top_executable_opportunities")
                                        candidate_row.setdefault("source_stage", "top_opportunity")
                                        candidate_row.setdefault("entry_path", "ranking_existing_candidate")
                                        lineage_rows.append(candidate_row)
                        summary_inputs = {
                            "generated_total": int(cycle_candidate_pool_count),
                            "tradebuilder_input_total": int(sum(1 for row in lineage_rows if str(row.get("source_stage") or "").strip().lower() == "tradebuilder")),
                            "tradebuilder_passed_total": int(sum(1 for row in lineage_rows if str(row.get("source_stage") or "").strip().lower() == "tradebuilder" and str(row.get("stage_status") or "").strip().lower() in {"passed", "ranked", "selected"})),
                            "phase2_input_total": int(sum(1 for row in lineage_rows if str(row.get("source_stage") or "").strip().lower() == "phase2")),
                            "phase2_passed_total": int(len(top_payload.get("top_executable_opportunities") or []) if isinstance(top_payload, dict) else 0),
                            "displayable_total": int(len((top_payload.get("top_executable_opportunities") or []) + (top_payload.get("top_advisory_opportunities") or [])) if isinstance(top_payload, dict) else 0),
                            "rankable_total": int(len(cycle_ranked_candidates or [])),
                            "executable_total": int(len(top_payload.get("top_executable_opportunities") or []) if isinstance(top_payload, dict) else 0),
                            "top_opportunity_total": int(len(top_payload.get("top_executable_opportunities") or []) if isinstance(top_payload, dict) else 0),
                            "blocked_total": int(sum(1 for row in lineage_rows if str(row.get("stage_status") or "").strip().lower() == "blocked")),
                        }
                        write_candidate_lineage_ledger(
                            cycle_id=lineage_cycle_id,
                            mode=str(getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM").lower(),
                            stage_rows=lineage_rows,
                            summary_inputs=summary_inputs,
                        )
                    except Exception as lineage_exc:
                        logger.warning("candidate_lineage_ledger_write_failed err=%s", lineage_exc)
                    feature_timing["GAP_candidate_lineage_ms"] = _perf_ms(t0)

                    t0 = time.perf_counter()
                    write_top_opportunities_snapshots(payload=top_payload, producer="orchestrator")
                    feature_timing["GAP_write_top_opportunities_ms"] = _perf_ms(t0)
                except Exception as top_exc:
                    logger.warning("top_opportunities_snapshot_write_failed err=%s", top_exc)
                try:
                    t_health = time.perf_counter()
                    write_runtime_health_snapshot(orchestrator=self)
                    feature_timing["write_runtime_health_ms"] = _perf_ms(t_health)
                except Exception as health_exc:
                    logger.warning("runtime_health_snapshot_error err=%s", health_exc)
                try:
                    t0 = time.perf_counter()
                    produce_and_store_runtime_snapshots(
                        market_snapshot=dashboard_market_snapshot,
                        producer="orchestrator_cycle",
                        loop_id=str(getattr(self, "_gate_status_cycle_id", "") or ""),
                        cycle_feed_truth_payload=feed_truth_payload,
                    )
                    feature_timing["produce_runtime_snapshots_ms"] = _perf_ms(t0)
                except Exception as exc:
                    logger.error("[RUNTIME_SNAPSHOT_WRITE_ERROR] phase=cycle error=%s:%s", type(exc).__name__, exc)
                t_end_gap = time.perf_counter()
                if (time.perf_counter() - loop_start_time) > 1.0:
                    logger.warning("LEGACY_CYCLE_END_TO_END_TIMING total_ms=%.1f timings=%s", (time.perf_counter() - loop_start_time) * 1000.0, feature_timing)
                if run_once:
                    break
                _pace_loop(self.poll_interval, loop_start_time)

    def _sync_trades(self):
        mode = str(getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM")) or "SIM").upper()
        dry_run_enabled = bool(
            getattr(cfg, "DRY_RUN", False)
            or str(os.getenv("DRY_RUN", "")).strip().lower() in {"1", "true", "yes", "on"}
        )
        if mode in {"SIM", "DRY_RUN"} or dry_run_enabled:
            return
        if not cfg.KITE_TRADES_SYNC or not kite_client.kite:
            return
        if time.time() - self.last_trade_sync < 10:
            return
        self.last_trade_sync = time.time()
        try:
            trades = kite_client.trades()
        except Exception:
            return

        for tr in trades:
            symbol = tr.get("tradingsymbol")
            token = tr.get("instrument_token")
            price = tr.get("average_price")
            ts = tr.get("exchange_timestamp")
            if not symbol or price is None:
                continue

            # Match by instrument_token when available, fallback to symbol
            for key, open_list in self.open_trades.items():
                for ot in open_list:
                    if ot.instrument_token and token and ot.instrument_token == token:
                        match = True
                    else:
                        match = ot.symbol in symbol
                    if match:
                        meta = self.trade_meta.get(ot.trade_id, {})
                        if meta.get("fill_price"):
                            continue
                        latency_ms = None
                        if ts:
                            latency_ms = int((time.time() - ts.timestamp()) * 1000)
                        slippage = price - ot.entry_price
                        meta["fill_price"] = price
                        meta["latency_ms"] = latency_ms
                        meta["slippage"] = slippage
                        self.trade_meta[ot.trade_id] = meta
                        update_trade_fill(ot.trade_id, price, latency_ms=latency_ms, slippage=slippage)
                        self.execution_engine.calibrate_slippage(slippage, instrument=ot.instrument)
                        try:
                            insert_execution_stat({
                                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "instrument": ot.instrument,
                                "slippage_bps": self.execution_engine.slippage_bps,
                                "latency_ms": latency_ms,
                                "fill_ratio": 1.0
                            })
                        except Exception:
                            pass

    def _load_symbol_eps(self):
        import json
        from pathlib import Path
        path = logs_dir() / "symbol_eps.json"
        if path.exists():
            try:
                self.symbol_epsilon = json.loads(path.read_text())
            except Exception:
                self.symbol_epsilon = {}

    def _save_symbol_eps(self):
        import json
        from pathlib import Path
        path = logs_dir() / "symbol_eps.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(self.symbol_epsilon))

        # append history
        hist_path = logs_dir() / "symbol_eps_history.json"
        self.eps_history.append({"ts": time.time(), "eps": self.symbol_epsilon})
        try:
            hist_path.write_text(json.dumps(self.eps_history[-500:]))
        except Exception:
            pass

    def _load_suggestion_eval(self):
        self.suggestion_eval_path = canonical_suggestion_eval_log_path()
        self.suggestion_evaluated = set()
        self._suggestion_log_offsets = {}
        self._last_suggestion_eval_ts = 0.0
        self._suggestion_strategy_tracker = None
        for path in suggestion_eval_log_paths():
            if not path.exists():
                continue
            try:
                with path.open("r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line)
                            tid = obj.get("trade_id")
                            if tid:
                                self.suggestion_evaluated.add(tid)
                        except Exception:
                            continue
            except Exception:
                continue

    def _suggestion_tracker(self) -> StrategyTracker:
        tracker = getattr(self, "_suggestion_strategy_tracker", None)
        if tracker is None:
            tracker = StrategyTracker()
            tracker.load(str(logs_dir() / "suggestion_strategy_perf.json"))
            self._suggestion_strategy_tracker = tracker
        return tracker

    def _read_pending_suggestions(self) -> list[dict]:
        suggestions: list[dict] = []
        incremental = bool(getattr(cfg, "SUGGESTION_EVAL_INCREMENTAL_READ_ENABLE", True))
        offsets = getattr(self, "_suggestion_log_offsets", None)
        if not isinstance(offsets, dict):
            offsets = {}
        files_seen = 0
        for sug_path in suggestion_log_paths():
            path = Path(sug_path)
            if not path.exists():
                offsets.pop(str(path), None)
                continue
            files_seen += 1
            start_offset = 0
            inode = None
            if incremental:
                try:
                    stat = path.stat()
                    inode = getattr(stat, "st_ino", None)
                    size = int(stat.st_size)
                    previous = dict(offsets.get(str(path)) or {})
                    previous_offset = max(0, int(previous.get("offset") or 0))
                    previous_inode = previous.get("inode")
                    if previous_inode == inode and previous_offset <= size:
                        start_offset = previous_offset
                except Exception:
                    start_offset = 0
            try:
                with path.open("r") as f:
                    if start_offset > 0:
                        f.seek(start_offset)
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            suggestions.append(json.loads(line))
                        except Exception:
                            continue
                    end_offset = f.tell()
            except Exception:
                continue
            if incremental:
                offsets[str(path)] = {"offset": end_offset, "inode": inode}
        self._suggestion_log_offsets = offsets
        if suggestions:
            logger.info(
                "suggestion_eval_scan files=%d pending=%d evaluated=%d incremental=%s",
                files_seen,
                len(suggestions),
                len(getattr(self, "suggestion_evaluated", set()) or []),
                incremental,
            )
        return suggestions

    def _evaluate_suggestions(self, market_data_list):
        """
        Evaluate suggested trades vs live option prices to see if targets/stops are hit.
        """
        if not bool(getattr(cfg, "SUGGESTION_EVAL_ENABLE", True)):
            return
        interval_sec = max(0.0, float(getattr(cfg, "SUGGESTION_EVAL_INTERVAL_SEC", 0.0) or 0.0))
        now_ts = float(now_utc_epoch())
        last_eval_ts = float(getattr(self, "_last_suggestion_eval_ts", 0.0) or 0.0)
        if interval_sec > 0 and last_eval_ts > 0 and (now_ts - last_eval_ts) < interval_sec:
            return
        self._last_suggestion_eval_ts = now_ts
        import re
        suggestions = self._read_pending_suggestions()
        if not suggestions:
            return
        # Build map for quick lookup
        md_map = {m.get("symbol"): m for m in market_data_list if m.get("instrument") == "OPT"}
        tracker = self._suggestion_tracker()
        updates = 0
        for s in suggestions:
            tid = s.get("trade_id")
            if not tid or tid in self.suggestion_evaluated:
                continue
            sym = s.get("symbol")
            md = md_map.get(sym)
            if not md:
                continue
            chain = md.get("option_chain", [])
            if not chain:
                continue
            # infer option type from trade_id
            opt_type = None
            m = re.search(r"-(CE|PE)(?:-|$)", tid)
            if m:
                opt_type = m.group(1)
            strike = s.get("strike")
            # find candidate option
            opt = None
            if strike in (None, "", 0, "ATM"):
                # pick closest strike of opt_type
                ltp = md.get("ltp", 0)
                if ltp:
                    step_map = getattr(cfg, "STRIKE_STEP_BY_SYMBOL", {})
                    step = step_map.get(sym, getattr(cfg, "STRIKE_STEP", 50))
                    atm = int(round(ltp / step) * step) if step else 0
                    candidates = [o for o in chain if (opt_type is None or o.get("type") == opt_type)]
                    if candidates:
                        opt = min(candidates, key=lambda o: abs(o.get("strike", 0) - atm))
            else:
                candidates = [o for o in chain if (opt_type is None or o.get("type") == opt_type) and o.get("strike") == strike]
                if candidates:
                    opt = candidates[0]
            if not opt:
                continue
            ltp_opt = opt.get("ltp")
            if ltp_opt is None:
                continue
            entry = s.get("entry")
            stop = s.get("stop")
            target = s.get("target")
            if entry is None or stop is None or target is None:
                continue
            outcome = None
            if ltp_opt >= target:
                outcome = "target"
            elif ltp_opt <= stop:
                outcome = "stop"
            if not outcome:
                continue
            # record evaluation
            payload = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "trade_id": tid,
                "symbol": sym,
                "strike": strike,
                "opt_type": opt_type,
                "ltp": ltp_opt,
                "outcome": outcome,
                "strategy": s.get("strategy"),
                "category": s.get("category"),
                "tier": s.get("tier"),
            }
            labeled_payload = attach_candidate_outcome_labels({**dict(s or {}), **payload})
            payload["candidate_outcome_label"] = labeled_payload.get("candidate_outcome_label")
            payload["candidate_outcome_label_provenance"] = labeled_payload.get("candidate_outcome_label_provenance")
            for eval_path in suggestion_eval_log_paths():
                try:
                    eval_path.parent.mkdir(parents=True, exist_ok=True)
                    with eval_path.open("a") as f:
                        f.write(json.dumps(payload) + "\n")
                except Exception:
                    continue
            self.suggestion_evaluated.add(tid)
            # update strategy evaluator (hit target = +1, stop = -1)
            pnl = 1 if outcome == "target" else -1
            strategy_name = s.get("strategy") or "UNKNOWN"
            tracker.record(strategy_name, pnl)
            category = str(s.get("category") or "").strip()
            if category:
                tracker.record(f"{category.upper()}::{strategy_name}", pnl)
            updates += 1
        if updates > 0:
            tracker.save(str(logs_dir() / "suggestion_strategy_perf.json"))
            logger.info(
                "suggestion_eval_processed pending=%d outcomes=%d",
                len(suggestions),
                updates,
            )

    def _start_depth_ws(self):
        if not cfg.KITE_USE_DEPTH:
            return
        logger.info("DEPTH_WS_START_TRIGGERED")
        kite_client.ensure()
        logger.info("WS: kite_client.ensure() done")
        ws_client = kite_client.kite
        if not ws_client:
            detail = getattr(kite_client, "last_init_error", None) or "kite_not_initialized"
            raise RuntimeError(f"kite_depth_ws_init_failed:{detail}")
        try:
            profile_payload = ws_client.profile()
        except Exception as exc:
            raise RuntimeError(
                f"kite_depth_ws_profile_failed:{exc} | "
                "Check: (1) cfg/env api_key present (2) token not expired (3) token generated using same api_key."
            ) from exc
        user_id_direct = str((profile_payload or {}).get("user_id", "") or "").strip()
        if not user_id_direct:
            raise RuntimeError(
                "kite_depth_ws_profile_failed:missing_user_id | "
                "Check: (1) cfg/env api_key present (2) token not expired (3) token generated using same api_key."
            )
        from core.auth_health import get_kite_auth_health
        auth_payload = get_kite_auth_health(force=True)
        if not auth_payload.get("ok"):
            raise RuntimeError(
                f"kite_depth_ws_profile_failed:{auth_payload.get('error')} | "
                "Check: (1) cfg/env api_key present (2) token not expired (3) token generated using same api_key."
            )
        user_id = str((auth_payload or {}).get("user_id", "") or user_id_direct)
        logger.info("WS: auth check passed")
        logger.info("kite_ws_profile_verified user_last4=%s", user_id[-4:] if user_id else "NONE")
        # Resolve a minimal depth subscription universe (index + ATM window).
        from core.kite_depth_ws import build_depth_subscription_tokens
        tokens, _resolution = build_depth_subscription_tokens(list(cfg.SYMBOLS))
        if not tokens:
            fallback = []
            for sym in cfg.SYMBOLS:
                tok = kite_client.resolve_index_token(sym)
                if tok:
                    fallback.append(tok)
            tokens = list(dict.fromkeys(fallback))
            if tokens:
                logger.info("kite_ws_fallback_index_tokens token_count=%d", len(tokens))
        if not tokens:
            raise RuntimeError("kite_depth_ws_init_failed:no_tokens_resolved")
        logger.info("WS: tokens_count=%d", len(tokens))
        if getattr(cfg, "FEED_USE_SUBPROCESS", False):
            start_depth_ws_subprocess(tokens, profile_verified=True)
        else:
            start_depth_ws(tokens, profile_verified=True)
        from core.feed.runtime_store import read_latest_runtime_snapshot

        snapshot = read_latest_runtime_snapshot() or {}
        runtime_state = str(snapshot.get("runtime_state") or "").strip().upper()
        runtime_source = str(snapshot.get("source") or "").strip()
        ws_connected = snapshot.get("ws_connected")
        snapshot_age_sec = None
        try:
            ts_epoch = float(snapshot.get("ts_epoch")) if snapshot.get("ts_epoch") is not None else None
            if ts_epoch is not None:
                snapshot_age_sec = max(0.0, float(time.time()) - float(ts_epoch))
        except Exception:
            snapshot_age_sec = None
        age_text = f"{snapshot_age_sec:.3f}" if snapshot_age_sec is not None else "none"
        logger.info(
            "WS: start_depth_ws dispatched runtime_state=%s source=%s ws_connected=%s snapshot_age_sec=%s",
            runtime_state or "UNKNOWN",
            runtime_source or "unknown",
            ws_connected,
            age_text,
        )
        if runtime_state in {"SUBSCRIBE_FAILED", "AUTH_BLOCKED", "IMPORT_MISSING"}:
            max_snapshot_age_sec = float(getattr(cfg, "DEPTH_WS_STARTUP_SNAPSHOT_MAX_AGE_SEC", 30.0))
            if snapshot_age_sec is not None and snapshot_age_sec <= max_snapshot_age_sec:
                detail = str(snapshot.get("last_error") or runtime_source or runtime_state).strip()
                raise RuntimeError(
                    f"kite_depth_ws_init_failed:runtime_state={runtime_state} detail={detail}"
                )

    def _run_preopen_auth_warm_check(self):
        try:
            from core.auth_health import run_preopen_auth_warm_check

            payload = run_preopen_auth_warm_check(force=True)
            if bool(payload.get("degrade_to_planning")):
                logger.warning(
                    "auth_guard_preopen_unhealthy degraded_to_planning=true reason=%s",
                    payload.get("reason"),
                )
            return payload
        except Exception as exc:
            logger.warning("auth_guard_preopen_warm_check_failed err=%s", exc)
            return {}

    def _run_startup_warmup_bootstrap(self):
        try:
            warmup_rows = ensure_startup_warmup_bootstrap(
                list(getattr(cfg, "SYMBOLS", []) or [])
            )
            for row in warmup_rows:
                logger.info(
                    "warmup_startup symbol=%s bars=%s last_candle_ts=%s indicator_last_update_ts=%s ok=%s reason=%s",
                    row.get("symbol"),
                    row.get("seeded_bars_count"),
                    row.get("last_candle_ts"),
                    row.get("indicator_last_update_ts"),
                    row.get("warmup_ok", row.get("indicators_ok_after_seed")),
                    row.get("warmup_reason") or row.get("seed_reason"),
                )
            return warmup_rows
        except Exception as exc:
            logger.warning("warmup_startup_failed err=%s", exc)
            return []

    def _track_open_trade(self, trade, market_data):
        key = f"{trade.symbol}:{trade.instrument}"
        if key not in self.open_trades:
            self.open_trades[key] = []
        self.open_trades[key].append(trade)
        trail_init = float(getattr(trade, "stop_loss", 0.0) or 0.0)
        meta = {
            "entry_time": time.time(),
            "trail_stop": trail_init,
            "current_sl": trail_init,
            "current_tp": float(getattr(trade, "target", 0.0) or 0.0),
            "instrument_token": trade.instrument_token,
            "entry_price": trade.entry_price,
            "mfe": 0.0,
            "mae": 0.0,
            "pnl_5m": None,
            "pnl_15m": None,
            "mfe_15m": None,
            "mae_15m": None,
            "trail_stop_init": trail_init,
            "trail_updates": 0,
            "trailing_enabled": True,
            "trailing_method": "ATR",
            "trailing_atr_mult": float(getattr(cfg, "TRAILING_STOP_ATR_MULT", 0.8)),
            "partial_enabled": bool(getattr(cfg, "PARTIAL_PROFIT_ENABLED", True)),
            "tp1_done": False,
            "remaining_qty_units": int(getattr(trade, "qty_units", 0) or 0),
            "realized_pnl_legs": 0.0,
            "legs_count": 0,
            "weighted_exit_sum": 0.0,
            "best_price_seen": float(getattr(trade, "entry_price", 0.0) or 0.0),
            "best_price_ts": time.time(),
            "exit_intel_phase": "INIT",
            "stall_counter": 0,
            "last_action_ts": 0.0,
            "reason_codes": [],
            "last_exit_intent_id": None,
            "selected_playbook": (
                getattr(trade, "selected_playbook", None)
                or getattr(trade, "decision_playbook", None)
                or "none"
            ),
        }
        if trade.strategy == "SCALP":
            meta["max_hold_sec"] = getattr(cfg, "SCALP_MAX_HOLD_MINUTES", 12) * 60
        if meta["remaining_qty_units"] <= 0:
            lot_size = int(getattr(cfg, "LOT_SIZE", {}).get(trade.symbol, 1))
            meta["remaining_qty_units"] = int(getattr(trade, "qty", 0) or 0) * (lot_size if trade.instrument == "OPT" else 1)
        self.trade_meta[trade.trade_id] = meta
        try:
            update_trailing_state(
                trade.trade_id,
                trailing_enabled=True,
                trailing_method=str(meta.get("trailing_method", "ATR")),
                trailing_atr_mult=float(meta.get("trailing_atr_mult", 0.8)),
                trail_stop_init=trail_init,
                trail_stop_last=trail_init,
                trail_updates=0,
            )
        except Exception:
            pass
        self._initialize_position_state(trade, meta, now_ts=time.time())

    def _check_open_trades(self, market_data):
        sym = market_data.get("symbol")
        instrument = market_data.get("instrument", "OPT")
        key = f"{sym}:{instrument}"
        if key not in self.open_trades:
            return

        remaining = []
        for tr in self.open_trades[key]:
            meta = self.trade_meta.get(tr.trade_id, {"trail_stop": tr.stop_loss, "entry_time": time.time()})
            meta.setdefault("current_sl", float(meta.get("trail_stop", tr.stop_loss) or tr.stop_loss))
            meta.setdefault("current_tp", float(meta.get("current_tp", tr.target) or tr.target))
            meta.setdefault("best_price_seen", float(meta.get("entry_price", tr.entry_price) or tr.entry_price))
            meta.setdefault("best_price_ts", float(meta.get("entry_time", time.time()) or time.time()))
            meta.setdefault("exit_intel_phase", "INIT")
            meta.setdefault("stall_counter", 0)
            meta.setdefault("last_action_ts", 0.0)
            meta.setdefault("reason_codes", [])
            if instrument == "OPT":
                option_snapshot = self._match_option_snapshot(tr, market_data)
                current_price = option_snapshot.get("ltp") if isinstance(option_snapshot, dict) else None
                if current_price is None:
                    remaining.append(tr)
                    continue
            else:
                option_snapshot = None
                current_price = market_data.get("ltp")
                if current_price is None:
                    remaining.append(tr)
                    continue

            position_state = self._refresh_position_state(
                tr,
                meta,
                {
                    "last_price": float(current_price),
                    "ltp": float(current_price),
                    "volatility": market_data.get("volatility"),
                    "quote_age_sec": (
                        option_snapshot.get("quote_age_sec")
                        if isinstance(option_snapshot, dict)
                        else market_data.get("quote_age_sec")
                    ),
                    "spread_pct": (
                        option_snapshot.get("spread_pct")
                        if isinstance(option_snapshot, dict)
                        else market_data.get("spread_pct")
                    ),
                },
                now_ts=time.time(),
            )
            if position_state is not None:
                meta["position_state_status"] = position_state.status
                meta["position_state_tp1_done"] = bool(position_state.tp1_done)
                meta["position_state_breakeven_done"] = bool(position_state.breakeven_done)
                meta["position_state_trailing_active"] = bool(position_state.trailing_active)
                meta["position_state_mfe_r"] = float(position_state.mfe_r)
                meta["position_state_mae_r"] = float(position_state.mae_r)
                meta["position_state_current_stop"] = float(position_state.current_stop)
                meta["position_state_remaining_qty"] = int(position_state.remaining_qty)
                meta["selected_playbook"] = str(position_state.playbook or meta.get("selected_playbook") or "none")

            # Store last price for unrealized PnL computation
            meta["last_price"] = current_price
            lot_size = int(getattr(cfg, "LOT_SIZE", {}).get(tr.symbol, 1))
            qty_total_units = int(meta.get("remaining_qty_units", 0) or 0)
            if qty_total_units <= 0:
                qty_total_units = int(getattr(tr, "qty_units", 0) or 0)
            if qty_total_units <= 0:
                qty_total_units = int(getattr(tr, "qty", 0) or 0) * (lot_size if tr.instrument == "OPT" else 1)
            if qty_total_units <= 0:
                remaining.append(tr)
                self.trade_meta[tr.trade_id] = meta
                continue
            # Track MFE/MAE and horizon PnL snapshots
            try:
                entry_px = meta.get("entry_price", tr.entry_price)
                pnl_now = (current_price - entry_px) if tr.side == "BUY" else (entry_px - current_price)
                meta["mfe"] = max(meta.get("mfe", 0.0), pnl_now)
                meta["mae"] = min(meta.get("mae", 0.0), pnl_now)
                elapsed = time.time() - meta.get("entry_time", time.time())
                if elapsed >= 300 and meta.get("pnl_5m") is None:
                    meta["pnl_5m"] = pnl_now
                if elapsed >= 900 and meta.get("pnl_15m") is None:
                    meta["pnl_15m"] = pnl_now
                    meta["mfe_15m"] = meta.get("mfe")
                    meta["mae_15m"] = meta.get("mae")
            except Exception:
                pass

            # Phase 3: Route live market quotes to AlphaDecayState in ExecutionEngine
            decay_state_dict = getattr(tr, "source_flags", {}).get("alpha_decay_state")
            if decay_state_dict:
                try:
                    from core.execution.alpha_decay import AlphaDecayState, monitor_alpha_decay
                    import time
                    decay_state = AlphaDecayState(**decay_state_dict)
                    l2_support_ratio = float(market_data.get("depth_imbalance", 0.5))
                    current_momentum_bps = float(market_data.get("momentum", 0.0))

                    should_force_exit = monitor_alpha_decay(
                        state=decay_state,
                        l2_support_ratio=l2_support_ratio,
                        current_momentum_bps=current_momentum_bps
                    )

                    if should_force_exit:
                        intent = {
                            "action": "FULL_EXIT",
                            "trade_id": str(tr.trade_id),
                            "reason_code": "decay_exhausted",
                            "exit_qty_units": qty_total_units,
                            "ts_epoch": time.time(),
                        }
                        self.execution_engine.apply_exit_intent(intent)

                    # Update state in trade source flags
                    tr.source_flags["alpha_decay_state"] = decay_state.__dict__

                    if should_force_exit:
                        codes = list(meta.get("reason_codes") or [])
                        codes.append("decay_exhausted")
                        meta["reason_codes"] = sorted(set(codes))
                        meta["exit_intel_action"] = "FULL_EXIT"
                        self.trade_meta[tr.trade_id] = meta

                        # Apply local full exit state updates since ExecutionEngine already generated the intent
                        try:
                            from core.exit_intelligence_evaluator import ExitDecision, ExitAction
                            decision = ExitDecision(
                                action=ExitAction.FULL_EXIT,
                                reason_codes=["decay_exhausted"],
                                state_patch={}
                            )
                            ack = {"accepted": True, "intent_id": f"exit_decay_{tr.trade_id}"}
                            position_state = self._load_position_state(tr.trade_id)
                            self._record_full_exit(tr, meta, position_state, decision, market_data, ack, now_ts=time.time())
                        except Exception:
                            pass

                        # Drop from open_trades as it is fully exited
                        continue
                except Exception as e:
                    pass

            feed_state = (
                market_data.get("feed_state")
                or (market_data.get("feed_health") or {}).get("state")
                or (market_data.get("quote_health") or {}).get("state")
            )
            decision = evaluate_exit(
                position={
                    "side": tr.side,
                    "entry_price": float(meta.get("entry_price", tr.entry_price)),
                    "current_sl": float(meta.get("current_sl", tr.stop_loss)),
                    "current_tp": float(meta.get("current_tp", tr.target)),
                    "best_price_seen": meta.get("best_price_seen"),
                    "best_price_ts": meta.get("best_price_ts"),
                    "exit_intel_phase": meta.get("exit_intel_phase"),
                    "stall_counter": meta.get("stall_counter"),
                    "last_action_ts": meta.get("last_action_ts"),
                    "remaining_qty_units": qty_total_units,
                    "qty_units": qty_total_units,
                    "entry_time": meta.get("entry_time"),
                    "max_hold_sec": meta.get("max_hold_sec"),
                    "reason_codes": list(meta.get("reason_codes") or []),
                    "last_price": meta.get("last_price"),
                },
                market_snapshot={
                    "ltp": current_price,
                    "atr": market_data.get("atr"),
                    "quote_age_sec": (
                        option_snapshot.get("quote_age_sec")
                        if isinstance(option_snapshot, dict)
                        else market_data.get("quote_age_sec")
                    ),
                    "spread_pct": (
                        option_snapshot.get("spread_pct")
                        if isinstance(option_snapshot, dict)
                        else market_data.get("spread_pct")
                    ),
                    "feed_state": feed_state,
                    "momentum": market_data.get("momentum"),
                    "momentum_break": market_data.get("momentum_break"),
                },
                now_ts=time.time(),
                cfg=cfg,
            )
            mode = str(getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM").strip().upper()
            if (
                mode in {"SIM", "PAPER"}
                and bool(getattr(cfg, "POSITION_STATE_EXIT_SHADOW_COMPARE_ENABLE", True))
                and position_state is not None
            ):
                try:
                    shadow_action = str(meta.get("position_state_advisory_action") or "UNKNOWN").upper()
                    shadow_reason = str(meta.get("position_state_advisory_reason") or "unknown")
                    live_action = str(decision.action.value or "UNKNOWN").upper()
                    live_reason = str((list(decision.reason_codes or []) or ["none"])[0])
                    logger.info(
                        "EXIT_SHADOW_COMPARE trade_id=%s symbol=%s live_action=%s live_reason=%s shadow_action=%s shadow_reason=%s playbook=%s",
                        tr.trade_id,
                        tr.symbol,
                        live_action,
                        live_reason,
                        shadow_action,
                        shadow_reason,
                        str(meta.get("selected_playbook") or "none"),
                    )
                except Exception:
                    pass
            meta = self._apply_exit_state_patch(tr, meta, decision.state_patch, float(current_price))
            reason_codes = list(decision.reason_codes or [])
            meta["exit_intel_action"] = decision.action.value
            self.trade_meta[tr.trade_id] = meta
            self._write_exit_intel_state(tr, meta, float(current_price))
            position_state = self._load_position_state(tr.trade_id)
            if decision.action == ExitAction.NOOP:
                if reason_codes:
                    meta["reason_codes"] = reason_codes
                    self.trade_meta[tr.trade_id] = meta
                remaining.append(tr)
                continue

            ack, _intent_payload = self._emit_exit_intent(tr, decision, market_data, float(current_price))
            if not bool(ack.get("accepted", False)):
                codes = list(meta.get("reason_codes") or [])
                codes.append("exit_intent_rejected")
                meta["reason_codes"] = sorted(set(codes))
                self.trade_meta[tr.trade_id] = meta
                remaining.append(tr)
                continue
            if bool(ack.get("duplicate", False)):
                remaining.append(tr)
                continue
            meta["last_exit_intent_id"] = ack.get("intent_id")
            self.trade_meta[tr.trade_id] = meta

            if decision.action == ExitAction.MODIFY_PLAN:
                if position_state is not None:
                    new_stop = meta.get("current_sl")
                    if new_stop is not None:
                        position_state = apply_position_exit_action(
                            position_state,
                            {
                                "action": "MOVE_STOP",
                                "new_stop": float(new_stop),
                                "reason": "exit_intel_modify_plan",
                            },
                            now_ts=time.time(),
                        )
                        self.position_states[position_state.trade_id] = position_state
                        self._persist_position_state(position_state)
                remaining.append(tr)
                continue

            if decision.action == ExitAction.PARTIAL_EXIT:
                remaining_units = int(meta.get("remaining_qty_units", qty_total_units) or qty_total_units)
                if remaining_units <= 1:
                    remaining.append(tr)
                    continue
                exit_qty = int(decision.exit_qty_units or 0)
                exit_qty = min(max(1, exit_qty), remaining_units - 1)
                if exit_qty <= 0:
                    remaining.append(tr)
                    continue
                entry_price_val = float(meta.get("entry_price", tr.entry_price))
                leg_pnl = (
                    (float(current_price) - entry_price_val) * exit_qty
                    if tr.side == "BUY"
                    else (entry_price_val - float(current_price)) * exit_qty
                )
                meta["remaining_qty_units"] = max(remaining_units - exit_qty, 0)
                meta["realized_pnl_legs"] = float(meta.get("realized_pnl_legs", 0.0)) + float(leg_pnl)
                meta["legs_count"] = int(meta.get("legs_count", 0)) + 1
                meta["weighted_exit_sum"] = float(meta.get("weighted_exit_sum", 0.0)) + (float(current_price) * exit_qty)
                meta["reason_codes"] = reason_codes
                self.trade_meta[tr.trade_id] = meta
                self._write_exit_intel_state(tr, meta, float(current_price))
                try:
                    insert_trade_leg(
                        tr.trade_id,
                        int(meta["legs_count"]),
                        int(exit_qty),
                        float(current_price),
                        "EXIT_INTEL_PARTIAL",
                    )
                except Exception:
                    pass
                if position_state is not None:
                    denom_qty = max(1, int(position_state.qty))
                    exit_fraction = max(0.0, min(1.0, float(exit_qty) / float(denom_qty)))
                    position_state = apply_position_exit_action(
                        position_state,
                        {
                            "action": "PARTIAL_EXIT",
                            "exit_fraction": exit_fraction,
                            "reason": "exit_intel_partial_exit",
                        },
                        now_ts=time.time(),
                    )
                    self.position_states[position_state.trade_id] = position_state
                    self._persist_position_state(position_state)
                remaining.append(tr)
                continue

            if decision.action != ExitAction.FULL_EXIT:
                remaining.append(tr)
                continue

            exit_reason_code = reason_codes[0] if reason_codes else "exit_intel_full_exit"
            if "TARGET" in exit_reason_code.upper():
                exit_reason = "TARGET"
                actual = 1
            elif "TIME" in exit_reason_code.upper():
                exit_reason = "TIME"
                actual = 0
            elif "STALL" in exit_reason_code.upper():
                exit_reason = "STALL_EXIT"
                actual = 0
            else:
                exit_reason = "STOP"
                actual = 0
            exit_price = float(current_price)

            remaining_units = int(meta.get("remaining_qty_units", 0) or 0)
            if remaining_units <= 0:
                remaining_units = qty_total_units
            final_leg_pnl = (
                (float(exit_price) - float(meta.get("entry_price", tr.entry_price))) * remaining_units
                if tr.side == "BUY"
                else (float(meta.get("entry_price", tr.entry_price)) - float(exit_price)) * remaining_units
            )
            total_realized_pnl = float(meta.get("realized_pnl_legs", 0.0)) + float(final_leg_pnl)
            total_units = max(1, int(getattr(tr, "qty_units", 0) or qty_total_units))
            total_risk = abs(float(meta.get("entry_price", tr.entry_price)) - float(tr.stop_loss)) * total_units
            r_multiple_realized = (total_realized_pnl / total_risk) if total_risk > 0 else 0.0
            outcome_label = "WIN" if total_realized_pnl > float(getattr(cfg, "OUTCOME_PNL_EPSILON", 1e-6)) else ("LOSS" if total_realized_pnl < -float(getattr(cfg, "OUTCOME_PNL_EPSILON", 1e-6)) else "BREAKEVEN")
            if r_multiple_realized >= 1.5:
                outcome_grade = "A"
            elif r_multiple_realized >= 1.0:
                outcome_grade = "B"
            elif r_multiple_realized >= 0.0:
                outcome_grade = "C"
            else:
                outcome_grade = "D"
            leg_count_final = int(meta.get("legs_count", 0)) + 1
            weighted_exit_sum = float(meta.get("weighted_exit_sum", 0.0)) + (float(exit_price) * remaining_units)
            avg_exit = weighted_exit_sum / max(1, total_units)
            try:
                insert_trade_leg(tr.trade_id, leg_count_final, remaining_units, float(exit_price), exit_reason)
            except Exception:
                pass

            # Update trade log
            updated = update_trade_outcome(
                tr.trade_id,
                exit_price,
                actual,
                exit_reason=exit_reason,
                realized_pnl_override=total_realized_pnl,
                r_multiple_realized_override=r_multiple_realized,
                outcome_label_override=outcome_label,
                outcome_grade_override=outcome_grade,
                legs_count=leg_count_final,
                avg_exit=avg_exit,
                exit_reason_final=exit_reason,
            )
            try:
                update_outcome(tr.trade_id, {
                    "pnl_horizon_5m": meta.get("pnl_5m"),
                    "pnl_horizon_15m": meta.get("pnl_15m"),
                    "mae_15m": meta.get("mae_15m"),
                    "mfe_15m": meta.get("mfe_15m"),
                })
            except Exception:
                pass

            # Update strategy performance
            pnl = total_realized_pnl
            # Update portfolio stats
            self.portfolio["capital"] += pnl
            self.portfolio["daily_loss"] += pnl
            if self.portfolio["capital"] > self.portfolio.get("equity_high", self.portfolio["capital"]):
                self.portfolio["equity_high"] = self.portfolio["capital"]
            dd = (self.portfolio["capital"] - self.portfolio["equity_high"]) / max(1.0, self.portfolio["equity_high"])
            if dd <= getattr(cfg, "MAX_DRAWDOWN_PCT", getattr(cfg, "PORTFOLIO_MAX_DRAWDOWN", -0.2)):
                risk_halt.set_halt("Max drawdown breach", {"drawdown": dd})
                send_telegram_message(f"Auto-halt: drawdown breach {dd:.2%}")
            # Skip aux trades in PAPER_STRICT_MODE from main perf stats
            if not (str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper() == "PAPER"
                    and getattr(cfg, "PAPER_STRICT_MODE", False)
                    and (getattr(tr, "tier", "MAIN") != "MAIN" or tr.strategy in (
                        "SCALP",
                        "ZERO_HERO",
                        "ZERO_HERO_EXPIRY",
                        getattr(cfg, "STRATEGY_ZERO_TO_HERO", "ZERO_TO_HERO"),
                    ) or tr.strategy.startswith("QUICK"))):
                self.strategy_tracker.record(tr.strategy, pnl)
                self.strategy_tracker.record_symbol(tr.symbol, pnl)
                self.strategy_tracker.save(str(logs_dir() / "strategy_perf.json"))
            # Expiry zero-hero: auto-disable after loss streak with cooldown
            try:
                if tr.strategy == "ZERO_HERO_EXPIRY":
                    streak = self.trade_builder._expiry_zero_hero_loss_streak.get(tr.symbol, 0)
                    if pnl <= 0:
                        streak += 1
                    else:
                        streak = 0
                    self.trade_builder._expiry_zero_hero_loss_streak[tr.symbol] = streak
                    max_streak = getattr(cfg, "ZERO_HERO_EXPIRY_DISABLE_AFTER_LOSS_STREAK", 2)
                    if tr.symbol == "NIFTY":
                        max_streak = getattr(cfg, "ZERO_HERO_EXPIRY_DISABLE_AFTER_LOSS_STREAK_NIFTY", max_streak)
                    if tr.symbol == "SENSEX":
                        max_streak = getattr(cfg, "ZERO_HERO_EXPIRY_DISABLE_AFTER_LOSS_STREAK_SENSEX", max_streak)
                    # Drawdown disable (net pnl)
                    pnl_sum = self.trade_builder._expiry_zero_hero_pnl.get(tr.symbol, 0.0) + pnl
                    self.trade_builder._expiry_zero_hero_pnl[tr.symbol] = pnl_sum
                    dd_limit = getattr(cfg, "ZERO_HERO_EXPIRY_DISABLE_DRAWDOWN", -0.5)
                    hit_drawdown = pnl_sum <= dd_limit
                    if streak >= max_streak or hit_drawdown:
                        cooldown = getattr(cfg, "ZERO_HERO_EXPIRY_DISABLE_COOLDOWN_MIN", 45) * 60
                        self.trade_builder._expiry_zero_hero_disabled_until[tr.symbol] = time.time() + cooldown
            except Exception:
                pass
            # update loss streak
            if pnl <= 0:
                self.loss_streak[tr.symbol] = self.loss_streak.get(tr.symbol, 0) + 1
            else:
                self.loss_streak[tr.symbol] = 0
            if pnl > 0:
                self.portfolio["daily_profit"] += pnl
                try:
                    self.portfolio["symbol_profit"][tr.symbol] = self.portfolio["symbol_profit"].get(tr.symbol, 0.0) + pnl
                except Exception:
                    pass
            try:
                self.risk_state.record_realized_pnl(tr.strategy, pnl)
            except Exception:
                pass
            meta["remaining_qty_units"] = 0
            self.trade_meta[tr.trade_id] = meta
            self._write_exit_intel_state(tr, meta, float(current_price))
            if position_state is not None:
                position_state = apply_position_exit_action(
                    position_state,
                    {
                        "action": "FULL_EXIT",
                        "exit_fraction": 1.0,
                        "reason": str(exit_reason_code or "exit_intel_full_exit"),
                    },
                    now_ts=time.time(),
                )
                self.position_states[position_state.trade_id] = position_state
                self._persist_position_state(position_state)

        self.open_trades[key] = remaining
        # Update unrealized PnL across all open trades using last known prices
        try:
            total_unrealized = 0.0
            for _, open_list in self.open_trades.items():
                for ot in open_list:
                    meta = self.trade_meta.get(ot.trade_id, {})
                    last_price = meta.get("last_price")
                    if last_price is None:
                        continue
                    lot_size = getattr(cfg, "LOT_SIZE", {}).get(ot.symbol, 1)
                    qty = ot.qty * (lot_size if ot.instrument == "OPT" else 1)
                    if ot.side == "BUY":
                        total_unrealized += (last_price - ot.entry_price) * qty
                    else:
                        total_unrealized += (ot.entry_price - last_price) * qty
            self.risk_state.update_unrealized(total_unrealized)
        except Exception:
            pass

    def backtest(self, historical_file: str, window_size: int = 50):
        """
        Phase D: Walk-forward backtest integration
        """
        logger.info("orchestrator_backtest_start file=%s", historical_file)
        historical = pd.read_csv(historical_file)

        # Use TradeBuilder + Phase B + Phase C logic for each window
        results = []
        for start in range(0, len(historical), window_size):
            end = start + window_size
            window_data = historical.iloc[start:end]
            for _, row in window_data.iterrows():
                market_data = row.to_dict()
                trade = self.trade_builder.build(market_data)
                allowed, _ = self.risk_engine.allow_trade(self.portfolio, trade=trade)
                if allowed:
                    results.append({
                        "symbol": trade.symbol,
                        "side": trade.side,
                        "entry": trade.entry_price,
                        "target": getattr(trade, "target", 0),
                        "pl": getattr(trade, "pl", 0),
                        "confidence": getattr(trade, "confidence", 0),
                        "regime": getattr(trade, "regime", "N/A"),
                        "capital": self.portfolio["capital"]
                    })
        df_results = pd.DataFrame(results)
        df_results.to_csv(str(logs_dir() / "backtest_results.csv"), index=False)
        logger.info("orchestrator_backtest_complete")
        return df_results


def _main():
    parser = argparse.ArgumentParser(description="Run orchestrator")
    parser.add_argument("--run-once", action="store_true", help="Run a single live-monitoring cycle and exit")
    parser.add_argument("--poll-interval", type=int, default=30, help="Polling interval in seconds")
    parser.add_argument("--capital", type=float, default=100000.0, help="Starting capital")
    args = parser.parse_args()
    if args.run_once:
        setattr(cfg, "KITE_USE_DEPTH", False)
    orch = Orchestrator(
        total_capital=args.capital,
        poll_interval=args.poll_interval,
        start_depth_ws_enabled=not args.run_once,
    )
    orch.live_monitoring(run_once=args.run_once)


if __name__ == "__main__":
    _main()
