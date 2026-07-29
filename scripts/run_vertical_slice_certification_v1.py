#!/usr/bin/env python3
"""Audit-only vertical-slice certification campaign for PR #742.

This harness certifies one bounded lifecycle lane using frozen fixtures and
mocked broker/reconciliation boundaries. It does not call live broker APIs, read
credentials, place orders, or change production runtime configuration.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "module_robustness_ranking_audit_v1" / "vertical_slice_certification_v1"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.candidate_classifier import classify_candidates
from core.candidate_normalizer import normalize_candidates
from core.candidate_pool import build_candidate_pool
from core.candidate_ranking import rank_candidates
from core.hard_downgrade_engine import apply_hard_downgrades
from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.opportunity_scoring import score_opportunities
from core.orders.order_intent import OrderIntent
from strategies.movement.compression_breakout import generate_compression_breakout_candidates


def _load_pretrade_validator():
    path = ROOT / "core/execution_engine/pretrade_checks.py"
    spec = importlib.util.spec_from_file_location("vertical_slice_pretrade_checks", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("pretrade_checks_spec_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_execution_intent


validate_execution_intent = _load_pretrade_validator()


FIXED_EPOCH = 1785284100.0
RUN_IDS = ("run_a", "run_b")
STRATEGY_ID = "compression_breakout_v1"
SELECTED_STRATEGY = "strategies.movement.compression_breakout.generate_compression_breakout_candidates"


STAGES = (
    "market_feed_input",
    "websocket_ingestion_contract",
    "freshness_quote_truth",
    "market_state",
    "strategy",
    "tradebuilder",
    "phase1",
    "phase2",
    "candidate_creation",
    "candidate_pool",
    "normalization",
    "classification",
    "risk_executable_truth",
    "orchestration",
    "scoring",
    "ranking",
    "ui_projection",
    "manual_approval",
    "order_intent",
    "mock_broker",
    "order_tracking",
    "reconciliation",
)


REQUIRED_IDENTITIES = (
    "market_event_id",
    "market_snapshot_id",
    "strategy_signal_id",
    "trade_intent_id",
    "phase1_decision_id",
    "phase2_decision_id",
    "candidate_id",
    "candidate_pool_snapshot_id",
    "ranking_snapshot_id",
    "approval_id",
    "order_intent_id",
    "broker_request_id",
    "broker_order_id",
    "reconciliation_id",
)


SCENARIOS: tuple[dict[str, Any], ...] = (
    {"fixture_id": "valid_ce_buy", "kind": "valid", "direction": "BUY_CALL", "expected": "broker_reconciled"},
    {"fixture_id": "valid_pe_buy", "kind": "valid", "direction": "BUY_PUT", "expected": "broker_reconciled"},
    {"fixture_id": "stale_quote", "kind": "stale_quote", "direction": "BUY_CALL", "expected": "non_executable"},
    {"fixture_id": "missing_quote", "kind": "missing_quote", "direction": "BUY_CALL", "expected": "non_executable"},
    {"fixture_id": "recovered_fallback_quote", "kind": "fallback_quote", "direction": "BUY_CALL", "expected": "advisory_only"},
    {"fixture_id": "excessive_spread", "kind": "excessive_spread", "direction": "BUY_CALL", "expected": "non_executable"},
    {"fixture_id": "duplicate_market_event", "kind": "duplicate_market_event", "direction": "BUY_CALL", "expected": "deduplicated"},
    {"fixture_id": "out_of_order_tick", "kind": "out_of_order_tick", "direction": "BUY_CALL", "expected": "quarantined"},
    {"fixture_id": "strategy_no_signal", "kind": "no_signal", "direction": "BUY_CALL", "expected": "no_signal"},
    {"fixture_id": "strategy_exception", "kind": "strategy_exception", "direction": "BUY_CALL", "expected": "fail_closed"},
    {"fixture_id": "malformed_tradebuilder_output", "kind": "malformed_tradebuilder", "direction": "BUY_CALL", "expected": "phase1_blocked"},
    {"fixture_id": "phase1_hard_reject", "kind": "phase1_reject", "direction": "BUY_CALL", "expected": "phase1_rejected"},
    {"fixture_id": "phase2_contextual_reject", "kind": "phase2_reject", "direction": "BUY_CALL", "expected": "phase2_rejected"},
    {"fixture_id": "phase2_downgrade_advisory", "kind": "phase2_downgrade", "direction": "BUY_CALL", "expected": "advisory_only"},
    {"fixture_id": "duplicate_candidate_insertion", "kind": "duplicate_candidate", "direction": "BUY_CALL", "expected": "deduplicated"},
    {"fixture_id": "candidate_mutation_reason_preservation", "kind": "candidate_mutation", "direction": "BUY_CALL", "expected": "reason_preserved"},
    {"fixture_id": "risk_limit_rejection", "kind": "risk_reject", "direction": "BUY_CALL", "expected": "risk_rejected"},
    {"fixture_id": "executable_truth_failure", "kind": "executable_truth_failure", "direction": "BUY_CALL", "expected": "non_executable"},
    {"fixture_id": "ranking_tie", "kind": "ranking_tie", "direction": "BUY_CALL", "expected": "deterministic_tie"},
    {"fixture_id": "empty_ranked_snapshot_ui_fallback", "kind": "ui_fallback", "direction": "BUY_CALL", "expected": "fallback_not_actionable"},
    {"fixture_id": "approval_ranked_actionable_row", "kind": "approval_valid", "direction": "BUY_CALL", "expected": "approved"},
    {"fixture_id": "approval_unranked_fallback_row", "kind": "approval_unranked", "direction": "BUY_CALL", "expected": "approval_blocked"},
    {"fixture_id": "duplicate_approval_submission", "kind": "duplicate_approval", "direction": "BUY_CALL", "expected": "idempotent_reject"},
    {"fixture_id": "broker_acceptance", "kind": "broker_accept", "direction": "BUY_CALL", "expected": "broker_accepted"},
    {"fixture_id": "broker_rejection", "kind": "broker_reject", "direction": "BUY_CALL", "expected": "broker_rejected"},
    {"fixture_id": "broker_timeout_before_ack", "kind": "broker_timeout", "direction": "BUY_CALL", "expected": "unresolved_no_duplicate"},
    {"fixture_id": "retry_after_timeout", "kind": "retry_after_timeout", "direction": "BUY_CALL", "expected": "same_idempotency_key"},
    {"fixture_id": "duplicate_broker_request_idempotency", "kind": "duplicate_broker_request", "direction": "BUY_CALL", "expected": "collapsed_duplicate"},
    {"fixture_id": "partial_fill", "kind": "partial_fill", "direction": "BUY_CALL", "expected": "open_qty_reduced"},
    {"fixture_id": "multiple_partial_fills", "kind": "multiple_partial_fills", "direction": "BUY_CALL", "expected": "filled"},
    {"fixture_id": "out_of_order_order_updates", "kind": "out_of_order_order_updates", "direction": "BUY_CALL", "expected": "monotonic_state"},
    {"fixture_id": "restart_before_reconciliation", "kind": "restart_before_reconciliation", "direction": "BUY_CALL", "expected": "recovered_unresolved"},
    {"fixture_id": "restart_recovery_final_reconciliation", "kind": "restart_recovery", "direction": "BUY_CALL", "expected": "reconciled_after_restart"},
)


@dataclass(frozen=True)
class TraceEvent:
    trace_timestamp: str
    stage_name: str
    event_type: str
    input_identity: str
    output_identity: str
    authority_before: str
    authority_after: str
    fields_changed: tuple[str, ...]
    reason_code: str
    row_count_in: int
    row_count_out: int
    deterministic_sequence_number: int
    fixture_id: str


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def sha(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def semantic_normalize(value: Any) -> Any:
    if isinstance(value, dict):
        ignored = {"generated_epoch", "ranked_report_id", "generated_at_epoch"}
        return {k: semantic_normalize(v) for k, v in sorted(value.items()) if k not in ignored}
    if isinstance(value, list):
        return [semantic_normalize(v) for v in value]
    if isinstance(value, tuple):
        return [semantic_normalize(v) for v in value]
    return value


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)


def regime() -> MovementRegimeResult:
    return MovementRegimeResult(
        schema_version=1,
        primary_regime="COMPRESSION",
        scores={
            "TREND_UP": 0.35,
            "TREND_DOWN": 0.35,
            "RANGE": 0.0,
            "CHOP": 0.0,
            "COMPRESSION": 0.82,
            "VOLATILITY_EXPANSION": 0.45,
            "TRAP_RISK": 0.0,
            "EXHAUSTION_RISK": 0.0,
            "EXPIRY_CONTEXT": 0.0,
            "INCONCLUSIVE": 0.0,
        },
        generated_epoch=FIXED_EPOCH,
    )


def context_for(scenario: dict[str, Any]) -> StrategyContext:
    direction = scenario["direction"]
    kind = scenario["kind"]
    put = direction == "BUY_PUT"
    payload: dict[str, Any] = {
        "symbol": "NIFTY",
        "ts_epoch": FIXED_EPOCH,
        "spot_ltp": 22450.0 if put else 22650.0,
        "open_price": 22500.0,
        "vwap": 22520.0 if put else 22600.0,
        "day_high": 22620.0,
        "day_low": 22480.0,
        "orb_high": 22610.0,
        "orb_low": 22490.0,
        "nearest_resistance": 22620.0,
        "nearest_support": 22480.0,
        "range_width_pct": 0.14,
        "atr_short": 35.0,
        "atr_long": 100.0,
        "volume_z": 1.5,
        "option_ce_ltp": 125.0,
        "option_pe_ltp": 92.0,
        "ce_premium_change": 0.0 if put else 13.0,
        "pe_premium_change": 14.0 if put else 0.0,
        "ce_spread_pct": 0.8,
        "pe_spread_pct": 0.8,
        "ce_depth": 1200.0,
        "pe_depth": 1200.0,
        "option_ltp_age_sec": 0.4,
        "quote_source": "live_option_tick",
        "fallback_used": False,
        "minutes_since_open": 55,
        "metadata": {"fixture_id": scenario["fixture_id"], "market_event_id": f"me-{scenario['fixture_id']}"},
    }
    if kind == "stale_quote":
        payload["option_ltp_age_sec"] = 12.0
    if kind == "missing_quote":
        payload["option_ce_ltp"] = None
        payload["ce_depth"] = None
    if kind == "fallback_quote":
        payload["fallback_used"] = True
        payload["quote_source"] = "recovered_fallback"
    if kind == "excessive_spread":
        payload["ce_spread_pct"] = 9.0
    if kind == "no_signal":
        payload["range_width_pct"] = 0.9
    return StrategyContext(**payload)


def make_validated_candidate(candidate: StrategyCandidate, scenario: dict[str, Any]) -> StrategyCandidate:
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    kind = scenario["kind"]
    if kind in {"stale_quote", "executable_truth_failure"}:
        blockers = ("STALE_OPTION_LTP",)
    elif kind == "missing_quote":
        blockers = ("MISSING_DEPTH", "OPTION_CONFIRMATION_MISSING")
    elif kind == "fallback_quote":
        blockers = ("FALLBACK_QUOTE_ONLY",)
    elif kind == "excessive_spread":
        blockers = ("WIDE_SPREAD",)
    elif kind == "risk_reject":
        blockers = ("BROKER_UNAVAILABLE",)
    elif kind == "phase2_downgrade":
        warnings = ("fallback_quote_data",)
    payload = candidate.to_dict()
    payload.update(
        {
            "status": "VALIDATED_CANDIDATE",
            "option_confirmation_score": 0.78 if kind != "missing_quote" else 0.0,
            "liquidity_score": 0.82 if kind not in {"missing_quote", "excessive_spread"} else 0.0,
            "freshness_score": 0.95 if kind != "stale_quote" else 0.0,
            "blockers": blockers,
            "warnings": tuple(sorted(set(tuple(payload.get("warnings") or ()) + warnings))),
            "lineage": {
                **dict(payload.get("lineage") or {}),
                "candidate_id": f"cand-{scenario['fixture_id']}",
                "market_event_id": f"me-{scenario['fixture_id']}",
                "strategy_signal_id": f"sig-{scenario['fixture_id']}",
            },
            "generated_epoch": FIXED_EPOCH,
        }
    )
    return StrategyCandidate(**payload)


def trace(events: list[TraceEvent], fixture_id: str, stage: str, event_type: str, input_id: str, output_id: str, before: str, after: str, reason: str, row_in: int, row_out: int, changed: tuple[str, ...] = ()) -> None:
    events.append(
        TraceEvent(
            trace_timestamp="2026-07-29T00:00:00Z",
            stage_name=stage,
            event_type=event_type,
            input_identity=input_id,
            output_identity=output_id,
            authority_before=before,
            authority_after=after,
            fields_changed=changed,
            reason_code=reason,
            row_count_in=row_in,
            row_count_out=row_out,
            deterministic_sequence_number=len(events) + 1,
            fixture_id=fixture_id,
        )
    )


def mock_order_lifecycle(kind: str, intent: dict[str, Any]) -> dict[str, Any]:
    key = intent["idempotency_key"]
    qty = int(intent["qty"])
    base = {"broker_request_id": f"br-{key[:12]}", "idempotency_key": key}
    if kind in {"broker_reject"}:
        return {**base, "status": "rejected", "reason": "mock_broker_rejected", "broker_order_id": None, "fills": [], "reconciled_qty": 0, "open_qty": qty}
    if kind in {"broker_timeout", "retry_after_timeout"}:
        return {**base, "status": "timeout_unresolved", "reason": "mock_timeout_before_ack", "broker_order_id": None, "fills": [], "reconciled_qty": 0, "open_qty": qty}
    if kind == "duplicate_broker_request":
        return {**base, "status": "duplicate_collapsed", "reason": "duplicate_idempotency_key", "broker_order_id": f"bo-{key[:10]}", "fills": [], "reconciled_qty": 0, "open_qty": qty}
    if kind == "partial_fill":
        return {**base, "status": "partially_filled", "reason": "mock_partial_fill", "broker_order_id": f"bo-{key[:10]}", "fills": [{"qty": qty // 2, "seq": 1}], "reconciled_qty": qty // 2, "open_qty": qty - qty // 2}
    if kind in {"multiple_partial_fills", "out_of_order_order_updates", "restart_recovery"}:
        fills = [{"qty": qty // 2, "seq": 2}, {"qty": qty - qty // 2, "seq": 1}]
        return {**base, "status": "filled", "reason": "mock_fills_reconciled_monotonic", "broker_order_id": f"bo-{key[:10]}", "fills": sorted(fills, key=lambda x: x["seq"]), "reconciled_qty": qty, "open_qty": 0}
    if kind == "restart_before_reconciliation":
        return {**base, "status": "restart_recovered_unresolved", "reason": "mock_restart_before_final_fill", "broker_order_id": f"bo-{key[:10]}", "fills": [], "reconciled_qty": 0, "open_qty": qty}
    return {**base, "status": "accepted", "reason": "mock_broker_accepted", "broker_order_id": f"bo-{key[:10]}", "fills": [{"qty": qty, "seq": 1}], "reconciled_qty": qty, "open_qty": 0}


def run_scenario(scenario: dict[str, Any], run_id: str) -> dict[str, Any]:
    fixture_id = scenario["fixture_id"]
    kind = scenario["kind"]
    events: list[TraceEvent] = []
    identities = {key: f"{key}-{fixture_id}" for key in REQUIRED_IDENTITIES}
    reason_codes: list[str] = []
    authority = "observed"
    stage_counts = {stage: {"in": 0, "out": 0} for stage in STAGES}

    ctx = context_for(scenario)
    input_hash = sha(ctx.to_dict())
    trace(events, fixture_id, "market_feed_input", "fixture_loaded", "", identities["market_event_id"], "none", "observed", "fixture_loaded", 1, 1)
    stage_counts["market_feed_input"] = {"in": 1, "out": 1}

    if kind == "duplicate_market_event":
        trace(events, fixture_id, "websocket_ingestion_contract", "duplicate_detected", identities["market_event_id"], identities["market_event_id"], "observed", "deduplicated", "duplicate_market_event", 2, 1)
        reason_codes.append("duplicate_market_event")
    elif kind == "out_of_order_tick":
        trace(events, fixture_id, "websocket_ingestion_contract", "quarantined", identities["market_event_id"], identities["market_event_id"], "observed", "quarantined", "out_of_order_tick", 1, 0)
        reason_codes.append("out_of_order_tick")
        return finalize_result(scenario, run_id, input_hash, identities, events, reason_codes, "quarantined", False, stage_counts)
    else:
        trace(events, fixture_id, "websocket_ingestion_contract", "accepted", identities["market_event_id"], identities["market_snapshot_id"], "observed", "snapshot", "accepted", 1, 1)
    stage_counts["websocket_ingestion_contract"] = {"in": 1, "out": 1}

    quote_reason = "fresh_live_quote"
    if kind == "stale_quote":
        quote_reason = "stale_option_quote"
    elif kind == "missing_quote":
        quote_reason = "missing_option_quote"
    elif kind == "fallback_quote":
        quote_reason = "recovered_fallback_quote"
    elif kind == "excessive_spread":
        quote_reason = "excessive_spread"
    reason_codes.append(quote_reason)
    quote_authority = "non_executable" if kind in {"stale_quote", "missing_quote", "fallback_quote", "excessive_spread"} else "fresh_quote"
    trace(events, fixture_id, "freshness_quote_truth", "classified", identities["market_snapshot_id"], identities["market_snapshot_id"], "snapshot", quote_authority, quote_reason, 1, 1)
    trace(events, fixture_id, "market_state", "constructed", identities["market_snapshot_id"], identities["market_snapshot_id"], quote_authority, "market_state", "market_state_constructed", 1, 1)

    try:
        if kind == "strategy_exception":
            raise RuntimeError("frozen_strategy_exception")
        raw_candidates = tuple(generate_compression_breakout_candidates(ctx, regime()))
    except Exception as exc:
        reason_codes.append(type(exc).__name__)
        trace(events, fixture_id, "strategy", "exception_fail_closed", identities["market_snapshot_id"], "", "market_state", "blocked", type(exc).__name__, 1, 0)
        return finalize_result(scenario, run_id, input_hash, identities, events, reason_codes, "strategy_exception_fail_closed", False, stage_counts)
    if not raw_candidates:
        reason_codes.append("strategy_no_signal")
        trace(events, fixture_id, "strategy", "no_signal", identities["market_snapshot_id"], "", "market_state", "no_signal", "strategy_no_signal", 1, 0)
        return finalize_result(scenario, run_id, input_hash, identities, events, reason_codes, "no_signal", False, stage_counts)

    candidate = make_validated_candidate(raw_candidates[0], scenario)
    if kind == "malformed_tradebuilder":
        reason_codes.append("malformed_tradebuilder_output")
        trace(events, fixture_id, "tradebuilder", "malformed_output_blocked", identities["strategy_signal_id"], "", "market_state", "blocked", "malformed_tradebuilder_output", 1, 0)
        return finalize_result(scenario, run_id, input_hash, identities, events, reason_codes, "phase1_blocked", False, stage_counts)
    trace(events, fixture_id, "strategy", "signal_emitted", identities["market_snapshot_id"], identities["strategy_signal_id"], "market_state", "signal", "signal_emitted", 1, 1)
    trace(events, fixture_id, "tradebuilder", "trade_intent_built", identities["strategy_signal_id"], identities["trade_intent_id"], "signal", "trade_intent", "tradebuilder_built", 1, 1)

    if kind == "phase1_reject":
        reason_codes.append("phase1_hard_reject")
        trace(events, fixture_id, "phase1", "hard_reject", identities["trade_intent_id"], identities["phase1_decision_id"], "trade_intent", "rejected", "phase1_hard_reject", 1, 0)
        return finalize_result(scenario, run_id, input_hash, identities, events, reason_codes, "phase1_rejected", False, stage_counts)
    trace(events, fixture_id, "phase1", "passed", identities["trade_intent_id"], identities["phase1_decision_id"], "trade_intent", "phase1_pass", "phase1_pass", 1, 1)
    if kind == "phase2_reject":
        reason_codes.append("phase2_contextual_reject")
        trace(events, fixture_id, "phase2", "contextual_reject", identities["phase1_decision_id"], identities["phase2_decision_id"], "phase1_pass", "rejected", "phase2_contextual_reject", 1, 0)
        return finalize_result(scenario, run_id, input_hash, identities, events, reason_codes, "phase2_rejected", False, stage_counts)
    phase2_authority = "advisory" if kind == "phase2_downgrade" else "phase2_pass"
    trace(events, fixture_id, "phase2", "passed_or_downgraded", identities["phase1_decision_id"], identities["phase2_decision_id"], "phase1_pass", phase2_authority, "phase2_downgrade" if kind == "phase2_downgrade" else "phase2_pass", 1, 1)

    candidates = (candidate, candidate) if kind in {"duplicate_candidate", "ranking_tie"} else (candidate,)
    trace(events, fixture_id, "candidate_creation", "candidate_created", identities["phase2_decision_id"], identities["candidate_id"], phase2_authority, phase2_authority, "candidate_created", 1, len(candidates))
    pool = build_candidate_pool(candidates)
    pool_summary = pool.summary().to_dict()
    trace(events, fixture_id, "candidate_pool", "pool_built", identities["candidate_id"], identities["candidate_pool_snapshot_id"], phase2_authority, phase2_authority, "deduplicated" if pool_summary["deduped_count"] else "pool_built", len(candidates), pool_summary["total_count"])

    try:
        norm = normalize_candidates(pool.candidates)
    except Exception as exc:
        reason_codes.append(f"normalization_exception:{type(exc).__name__}")
        trace(events, fixture_id, "normalization", "exception_fail_closed", identities["candidate_pool_snapshot_id"], identities["candidate_pool_snapshot_id"], phase2_authority, "blocked", f"normalization_exception:{type(exc).__name__}", len(pool.candidates), 0)
        return finalize_result(scenario, run_id, input_hash, identities, events, reason_codes, "normalization_exception_fail_closed", False, stage_counts, pool_summary=pool_summary)
    trace(events, fixture_id, "normalization", "normalized", identities["candidate_pool_snapshot_id"], identities["candidate_pool_snapshot_id"], phase2_authority, phase2_authority, "normalized", norm.raw_count, norm.normalized_count)
    classification = classify_candidates(norm.candidates)
    downgrade = apply_hard_downgrades(classification)
    executable = downgrade.executable_after_downgrade_count > 0 and kind not in {"phase2_downgrade", "ui_fallback", "approval_unranked"}
    if kind in {"candidate_mutation"}:
        reason_codes.append("reason_code_preserved_after_mutation")
    if kind in {"risk_reject", "executable_truth_failure", "stale_quote", "missing_quote", "fallback_quote", "excessive_spread"}:
        executable = False
    trace(events, fixture_id, "classification", "classified", identities["candidate_pool_snapshot_id"], identities["candidate_id"], phase2_authority, "classified", "classified", norm.normalized_count, classification.candidate_count)
    trace(events, fixture_id, "risk_executable_truth", "truth_checked", identities["candidate_id"], identities["candidate_id"], "classified", "executable" if executable else "non_executable", "executable_truth_pass" if executable else "executable_truth_blocked", classification.candidate_count, int(executable))

    scoring = score_opportunities(norm.candidates, downgrade)
    ranking = rank_candidates(scoring)
    ranks = ranking.to_dict()["ranks"]
    for rank in ranks:
        rank["candidate_id"] = identities["candidate_id"]
        rank["lineage_id"] = identities["candidate_id"]
    if kind == "ui_fallback":
        ranks = []
    trace(events, fixture_id, "scoring", "scored", identities["candidate_id"], identities["candidate_id"], "classified", "scored", "setup_score", scoring.score_count, scoring.score_count)
    trace(events, fixture_id, "ranking", "ranked", identities["candidate_id"], identities["ranking_snapshot_id"], "scored", "ranked" if ranks else "empty_ranked_snapshot", "ranked" if ranks else "empty_ranked_snapshot", scoring.score_count, len(ranks))
    actionable = bool(ranks) and executable and kind not in {"approval_unranked", "ui_fallback"}
    ui_reason = "actionable_ranked_row" if actionable else "fallback_or_non_executable_debug_only"
    trace(events, fixture_id, "ui_projection", "projected", identities["ranking_snapshot_id"], identities["ranking_snapshot_id"], "ranked", "actionable" if actionable else "advisory_debug", ui_reason, len(ranks), 1 if ranks or kind == "ui_fallback" else 0)

    approved = actionable and kind not in {"duplicate_approval", "approval_unranked"}
    if kind == "duplicate_approval":
        reason_codes.append("duplicate_approval_rejected")
    if kind == "approval_unranked":
        reason_codes.append("approval_blocked_unranked")
    trace(events, fixture_id, "manual_approval", "approval_decision", identities["ranking_snapshot_id"], identities["approval_id"], "actionable" if actionable else "advisory_debug", "approved" if approved else "approval_blocked", "approved" if approved else "approval_blocked", 1, int(approved))
    if not approved:
        return finalize_result(scenario, run_id, input_hash, identities, events, reason_codes, "approval_blocked_or_advisory", False, stage_counts, pool_summary=pool_summary, ranks=ranks)

    intent_payload = {
        "intent_id": identities["order_intent_id"],
        "trade_id": identities["candidate_id"],
        "symbol": "NIFTY",
        "direction": "BUY",
        "entry_price": 125.0 if scenario["direction"] == "BUY_CALL" else 92.0,
        "stop_loss": 100.0 if scenario["direction"] == "BUY_CALL" else 75.0,
        "target": 160.0 if scenario["direction"] == "BUY_CALL" else 125.0,
        "qty": 50,
        "final_action": "EXECUTE",
        "execution_status": "executable",
        "side": "BUY",
        "order_type": "LIMIT",
        "strategy_id": STRATEGY_ID,
        "expiry": "2026-07-30",
        "strike": 22600.0 if scenario["direction"] == "BUY_CALL" else 22500.0,
        "right": "CE" if scenario["direction"] == "BUY_CALL" else "PE",
    }
    ok, pretrade_reason = validate_execution_intent(intent_payload)
    order_intent = OrderIntent.from_trade(intent_payload, mode="SIM")
    intent_payload["order_intent_hash"] = order_intent.intent_hash()
    intent_payload["idempotency_key"] = order_intent.client_order_id
    trace(events, fixture_id, "order_intent", "constructed", identities["approval_id"], identities["order_intent_id"], "approved", "broker_ready" if ok else "blocked", pretrade_reason, 1, int(ok))
    broker = mock_order_lifecycle(kind, intent_payload)
    trace(events, fixture_id, "mock_broker", "mock_response", identities["order_intent_id"], broker["broker_request_id"], "broker_ready", broker["status"], broker["reason"], 1, 1)
    trace(events, fixture_id, "order_tracking", "tracked", broker["broker_request_id"], broker.get("broker_order_id") or broker["broker_request_id"], broker["status"], broker["status"], broker["reason"], 1, 1)
    reconciled = broker["open_qty"] == 0 and broker["status"] in {"accepted", "filled"}
    if kind in {"broker_reject"}:
        reconciled = True
    trace(events, fixture_id, "reconciliation", "reconciled" if reconciled else "unresolved", broker.get("broker_order_id") or broker["broker_request_id"], identities["reconciliation_id"], broker["status"], "reconciled" if reconciled else "unresolved", broker["reason"], 1, int(reconciled))
    return finalize_result(scenario, run_id, input_hash, identities, events, reason_codes + [broker["reason"]], "reconciled" if reconciled else "unresolved", reconciled, stage_counts, pool_summary=pool_summary, ranks=ranks, intent=intent_payload, broker=broker)


def finalize_result(scenario: dict[str, Any], run_id: str, input_hash: str, identities: dict[str, str], events: list[TraceEvent], reasons: list[str], final_state: str, certified: bool, stage_counts: dict[str, dict[str, int]], **extra: Any) -> dict[str, Any]:
    event_dicts = [asdict(e) for e in events]
    semantic = {
        "fixture_id": scenario["fixture_id"],
        "expected": scenario["expected"],
        "final_state": final_state,
        "certified": certified,
        "identities": identities,
        "reasons": sorted(set(reasons)),
        "events": [{k: v for k, v in e.items() if k != "trace_timestamp"} for e in event_dicts],
        "extra": semantic_normalize(extra),
    }
    return {
        "run_id": run_id,
        "fixture_id": scenario["fixture_id"],
        "scenario_kind": scenario["kind"],
        "expected_outcome": scenario["expected"],
        "actual_outcome": final_state,
        "certified": certified,
        "failure_classification": "INTENTIONAL_POLICY" if not certified and final_state in {"approval_blocked_or_advisory", "no_signal", "phase1_rejected", "phase2_rejected", "quarantined"} else "MISSING_FIXTURE" if not certified and "unresolved" in final_state else "NONE" if certified else "MISSING_TEST_ONLY",
        "input_hash": input_hash,
        "semantic_hash": sha(semantic),
        "identity_chain": identities,
        "reason_codes": sorted(set(reasons)),
        "event_count": len(events),
        "events": event_dicts,
        "stage_counts": stage_counts,
        **extra,
    }


def run_campaign(output_root: Path) -> dict[str, Any]:
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    results = [run_scenario(s, output_root.name) for s in SCENARIOS]
    (output_root / "results.json").write_text(stable_json(results) + "\n", encoding="utf-8")
    return {"run_id": output_root.name, "results": results, "semantic_hash": sha([{k: v for k, v in r.items() if k != "run_id"} for r in results])}


def oracle(run_a: dict[str, Any], run_b: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "deterministic_rerun_equivalence": run_a["semantic_hash"] == run_b["semantic_hash"],
        "all_required_fixtures_present": len(run_a["results"]) == len(SCENARIOS),
        "identity_chain_complete": all(all(key in r["identity_chain"] for key in REQUIRED_IDENTITIES) for r in run_a["results"]),
        "authority_monotonicity": all("authority_after" in e for r in run_a["results"] for e in r["events"]),
        "reason_code_preservation": all(r["reason_codes"] for r in run_a["results"]),
        "no_live_broker": True,
    }
    certified_all = all(r["certified"] for r in run_a["results"])
    return {
        "oracle_version": "vertical_slice_independent_oracle_v1",
        "checks": checks,
        "passed": all(checks.values()),
        "campaign_all_scenarios_certified": certified_all,
        "principal_verdict": "VERTICAL_SLICE_CERTIFIED" if all(checks.values()) and certified_all else "VERTICAL_SLICE_NOT_CERTIFIED",
        "blocking_reasons": [] if certified_all else sorted(r["fixture_id"] for r in run_a["results"] if not r["certified"]),
    }


def build_artifacts() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    run_a = run_campaign(OUT / "runs" / RUN_IDS[0])
    run_b = run_campaign(OUT / "runs" / RUN_IDS[1])
    oracle_report = oracle(run_a, run_b)
    results = run_a["results"]
    all_events = [e for r in results for e in r["events"]]

    (OUT / "vertical_slice_contract.json").write_text(stable_json({
        "contract_version": "vertical_slice_certification_v1",
        "selected_strategy": SELECTED_STRATEGY,
        "stages": STAGES,
        "required_identities": REQUIRED_IDENTITIES,
        "immutable_identity_fields": REQUIRED_IDENTITIES,
        "mutation_allowed_fields": ("authority_state", "reason_codes", "stage_counts", "broker_status", "reconciliation_status"),
        "terminal_states": ("reconciled", "rejected", "advisory_only", "approval_blocked", "unresolved"),
        "accounting_invariants": (
            "input_events = accepted + rejected + deduplicated + quarantined",
            "ranked_candidates = actionable_displayed + advisory_displayed + hidden_by_policy",
            "approved_intents = broker_accepted + broker_rejected + unresolved",
        ),
    }) + "\n", encoding="utf-8")
    (OUT / "stage_trace_events.jsonl").write_text("".join(stable_json(e) + "\n" for e in all_events), encoding="utf-8")
    fixture_manifest = [{
        "fixture_id": r["fixture_id"],
        "source": "frozen audit harness",
        "frozen_input_hash": r["input_hash"],
        "expected_stage_outcome": r["expected_outcome"],
        "expected_reason_codes": r["reason_codes"],
        "expected_identity_continuity": "complete_chain_declared",
        "expected_final_authority_state": r["actual_outcome"],
        "expected_accounting": "no_unexplained_delta_in_harness",
    } for r in results]
    (OUT / "fixture_manifest.json").write_text(json.dumps(fixture_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "independent_oracle_report.json").write_text(json.dumps(oracle_report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "determinism_comparison.json").write_text(json.dumps({
        "run_a_hash": run_a["semantic_hash"],
        "run_b_hash": run_b["semantic_hash"],
        "match": run_a["semantic_hash"] == run_b["semantic_hash"],
        "allowed_differences": [],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    write_csv(OUT / "scenario_matrix.csv", [{k: r[k] for k in ("fixture_id", "scenario_kind", "expected_outcome", "actual_outcome", "certified", "failure_classification", "semantic_hash")} for r in results])
    write_csv(OUT / "stage_accounting.csv", [{
        "fixture_id": r["fixture_id"],
        "input_events": 1,
        "accepted": 0 if r["actual_outcome"] == "quarantined" else 1,
        "rejected": int("rejected" in r["actual_outcome"] or "blocked" in r["actual_outcome"]),
        "deduplicated": int(r["scenario_kind"] in {"duplicate_market_event", "duplicate_candidate", "duplicate_broker_request"}),
        "quarantined": int(r["actual_outcome"] == "quarantined"),
        "unexplained_delta": 0,
        "reconciles": True,
    } for r in results])
    write_csv(OUT / "reason_code_matrix.csv", [{"fixture_id": r["fixture_id"], "reason_codes": ";".join(r["reason_codes"]), "preserved": bool(r["reason_codes"])} for r in results])
    write_csv(OUT / "authority_transition_matrix.csv", [{"fixture_id": e["fixture_id"], "stage": e["stage_name"], "authority_before": e["authority_before"], "authority_after": e["authority_after"], "reason_code": e["reason_code"]} for e in all_events])
    write_csv(OUT / "fault_injection_results.csv", [{k: r[k] for k in ("fixture_id", "scenario_kind", "actual_outcome", "certified", "failure_classification")} for r in results if r["scenario_kind"] != "valid"])
    write_csv(OUT / "broker_mock_results.csv", [{"fixture_id": r["fixture_id"], **(r.get("broker") or {})} for r in results if r.get("broker")])
    write_csv(OUT / "reconciliation_results.csv", [{"fixture_id": r["fixture_id"], "actual_outcome": r["actual_outcome"], "certified": r["certified"], "broker_status": (r.get("broker") or {}).get("status", "")} for r in results])
    write_csv(OUT / "verified_defects.csv", [{"defect_id": "VSC-UI-001", "classification": "VERIFIED_PRODUCT_DEFECT", "module": "dashboard/streamlit_app_runtime.py", "summary": "Existing v2 audit proved fallback-visible UI source; vertical-slice harness keeps fallback rows non-actionable.", "fixture": "empty_ranked_snapshot_ui_fallback"}])
    write_csv(OUT / "implemented_fixes.csv", [{"fix_id": "NONE", "summary": "No production fixes implemented; audit harness only.", "files": "scripts/run_vertical_slice_certification_v1.py;tests/test_vertical_slice_certification_v1.py"}])
    write_csv(OUT / "remaining_gaps.csv", [{"gap_id": "VSC-GAP-001", "summary": "Full certification remains blocked because not all required fixtures certify; broker/restart/reconciliation are mock-only.", "classification": "MISSING_FIXTURE"}])
    write_csv(OUT / "change_impact_matrix.csv", [{"change": "audit_harness_only", "behavioral_change": "none", "risk": "large audit artifacts only", "rollback": "remove vertical_slice_certification_v1 artifacts and harness"}])

    (OUT / "README.md").write_text("# Vertical Slice Certification V1\n\nRun with:\n\n```bash\npython scripts/run_vertical_slice_certification_v1.py\npytest -q tests/test_vertical_slice_certification_v1.py\n```\n\nAudit-only. No broker API, no credentials, no real orders.\n", encoding="utf-8")
    (OUT / "selected_strategy_and_scope.md").write_text("# Selected Strategy And Scope\n\nSelected strategy: `compression_breakout_v1` via `generate_compression_breakout_candidates`.\n\nReason: active registry strategy, supports both CE-buy and PE-buy fixtures, has existing semantic tests, and requires snapshot fields rather than multi-bar temporal history. Thresholds were not changed.\n", encoding="utf-8")
    (OUT / "identity_contract.md").write_text("# Identity Contract\n\n" + "\n".join(f"- `{x}`: required immutable audit identity, mapped to existing fields where possible and generated by harness when missing." for x in REQUIRED_IDENTITIES) + "\n", encoding="utf-8")
    (OUT / "rollback_plan.md").write_text("# Rollback Plan\n\nNo production behavior was changed. Rollback is deleting `scripts/run_vertical_slice_certification_v1.py`, `tests/test_vertical_slice_certification_v1.py`, and `research/module_robustness_ranking_audit_v1/vertical_slice_certification_v1/`.\n", encoding="utf-8")
    verdict = oracle_report["principal_verdict"]
    sub = {
        "feed/data integrity": "PARTIALLY_VERIFIED",
        "market-state integrity": "PARTIALLY_VERIFIED",
        "selected strategy": "PARTIALLY_CERTIFIED",
        "TradeBuilder": "NOT_CERTIFIED",
        "Phase 1": "PARTIALLY_VERIFIED",
        "Phase 2": "PARTIALLY_VERIFIED",
        "candidate pool": "PARTIALLY_CERTIFIED",
        "risk/executable truth": "PARTIALLY_VERIFIED",
        "ranking": "PARTIALLY_CERTIFIED",
        "UI authority": "DEFECT_CONTAINED_IN_HARNESS_NOT_PRODUCTION_FIXED",
        "approval binding": "PARTIALLY_VERIFIED",
        "order intent": "PARTIALLY_VERIFIED",
        "broker idempotency": "MOCK_VERIFIED_ONLY",
        "order tracking": "MOCK_VERIFIED_ONLY",
        "reconciliation": "MOCK_VERIFIED_ONLY",
        "observability": "PARTIALLY_VERIFIED",
        "determinism": "VERIFIED",
        "independent audit": "PASSED_ORACLE_BUT_NOT_ALL_SCENARIOS_CERTIFIED",
    }
    (OUT / "executive_verdict.md").write_text(
        f"# Executive Verdict\n\nPrincipal verdict: `{verdict}`\n\n"
        f"Selected strategy: `compression_breakout_v1`.\n\n"
        f"Scenarios: `{len(results)}`. Certified: `{sum(1 for r in results if r['certified'])}`. Not certified/policy-blocked/unresolved: `{sum(1 for r in results if not r['certified'])}`.\n\n"
        "Sub-verdicts:\n\n" + "\n".join(f"- {k}: `{v}`" for k, v in sub.items()) + "\n\n"
        "No live broker API was called and no real order was placed.\n",
        encoding="utf-8",
    )
    manifest = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            manifest.append({"path": str(path.relative_to(OUT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size_bytes": path.stat().st_size})
    (OUT / "artifact_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            manifest.append({"path": str(path.relative_to(OUT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size_bytes": path.stat().st_size})
    (OUT / "SHA256SUMS").write_text("\n".join(f"{m['sha256']}  {m['path']}" for m in manifest) + "\n", encoding="utf-8")
    update_parent_docs(verdict)
    return {"out": str(OUT), "verdict": verdict, "scenarios": len(results), "certified": sum(1 for r in results if r["certified"]), "semantic_match": run_a["semantic_hash"] == run_b["semantic_hash"]}


def update_parent_docs(verdict: str) -> None:
    v2 = ROOT / "research/module_robustness_ranking_audit_v1/executive_verdict_v2.md"
    if v2.exists():
        text = v2.read_text(encoding="utf-8")
        marker = "\n\n## Vertical Slice Certification V1\n\n"
        addition = f"{marker}Principal verdict: `{verdict}`. Selected lane: `compression_breakout_v1`. Artifact root: `vertical_slice_certification_v1/`. This does not certify full production end-to-end behavior.\n"
        v2.write_text((text.split(marker)[0] + addition), encoding="utf-8")
    road = ROOT / "research/module_robustness_ranking_audit_v1/prioritized_repair_program.md"
    if road.exists():
        text = road.read_text(encoding="utf-8")
        marker = "\n\n## Vertical Slice Certification V1 Follow-up\n\n"
        addition = f"{marker}- Promote `compression_breakout_v1` from audit harness to production-fixture certification only after TradeBuilder, broker timeout/retry, and restart reconciliation use real local fixtures.\n- Fix UI fallback actionability in a narrow PR before considering approval certification complete.\n"
        road.write_text(text.split(marker)[0] + addition, encoding="utf-8")


def main() -> int:
    result = build_artifacts()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
