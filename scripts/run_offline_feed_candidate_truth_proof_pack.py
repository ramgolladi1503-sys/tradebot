#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.feed.runtime_store import canonicalize_feed_runtime_snapshot_truth
from core.feed_execution_truth import attach_feed_execution_truth
from core.feed_truth_contract import build_feed_truth_contract
from core.feed_truth_state import LIVE
from core.runtime_execution_truth import (
    build_execution_truth_context,
    normalize_candidate_execution_truth_payload,
)
from core.runtime_phase2_rejection_evidence import (
    build_phase2_rejection_evidence_payload,
)
from core.review_queue import _final_emit_truth_event
from core.events import write_json_atomic


# Read-only proof-pack safety contract:
# read_only=true, append=false, is_order_action=false, broker_api_called=false, live_order_allowed=false


@dataclass(frozen=True)
class OfflineProofScenario:
    name: str
    expected_result: str
    feed_snapshot: dict[str, Any]
    candidate: dict[str, Any] | None
    phase2_raw_candidates: tuple[dict[str, Any], ...] = ()
    phase2_ranked_candidates: tuple[dict[str, Any], ...] = ()
    latency_guard: dict[str, Any] = field(default_factory=dict)
    mirror_check: bool = False


@dataclass(frozen=True)
class OfflineProofScenarioResult:
    scenario_name: str
    input_truth_state: str
    expected_result: str
    actual_result: str
    executable_allowed: bool
    reportable_executable: bool
    phase2_input_state: str
    phase2_drop_counts: dict[str, int]
    final_emit_allowed: bool
    blockers: tuple[str, ...]
    pass_fail: bool
    read_only: bool = True
    append: bool = False
    is_order_action: bool = False  # is_order_action=false
    broker_api_called: bool = False  # broker_api_called=false
    live_order_allowed: bool = False
    live_order_action: bool = False  # live_order_action=false
    broker_order_action: bool = False  # broker_order_action=false
    feed_truth_state: str = ""
    feed_truth_allows_executable_candidates: bool = False
    process_restart_required: bool = False
    ws_reconnect_allowed: bool = True
    mirror_fields: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "scenario_name": self.scenario_name,
            "input_truth_state": self.input_truth_state,
            "expected_result": self.expected_result,
            "actual_result": self.actual_result,
            "executable_allowed": self.executable_allowed,
            "reportable_executable": self.reportable_executable,
            "phase2_input_state": self.phase2_input_state,
            "phase2_drop_counts": dict(self.phase2_drop_counts),
            "final_emit_allowed": self.final_emit_allowed,
            "blockers": list(self.blockers),
            "pass_fail": self.pass_fail,
            "read_only": True,
            "append": False,
            "is_order_action": False,
            "broker_api_called": False,
            "live_execution_changed": False,
            "behavior_changed": False,
            "runtime_behavior_changed": False,
            "order_behavior_changed": False,
            "broker_order_called": False,
            "execution_behavior_changed": False,
            "live_order_allowed": False,
            "live_order_action": False,
            "broker_order_action": False,
            "runtime_wired": False,
            "external_services_used": False,
            "proves_trading_edge": False,
            "feed_truth_state": self.feed_truth_state,
            "feed_truth_allows_executable_candidates": self.feed_truth_allows_executable_candidates,
            "process_restart_required": self.process_restart_required,
            "ws_reconnect_allowed": self.ws_reconnect_allowed,
            "mirror_fields": {
                key: dict(value) for key, value in self.mirror_fields.items()
            },
        }


@dataclass(frozen=True)
class OfflineFeedCandidateTruthProofPack:
    schema_version: int
    source: str
    read_only: bool
    append: bool
    scenarios: tuple[OfflineProofScenarioResult, ...]
    summary: str
    failures: tuple[str, ...]
    live_order_allowed: bool = False
    is_order_action: bool = False  # is_order_action=false
    broker_api_called: bool = False  # broker_api_called=false
    live_order_action: bool = False  # live_order_action=false
    broker_order_action: bool = False  # broker_order_action=false

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "read_only": self.read_only,
            "append": self.append,
            "is_order_action": False,
            "broker_api_called": False,
            "live_execution_changed": False,
            "behavior_changed": False,
            "runtime_behavior_changed": False,
            "order_behavior_changed": False,
            "broker_order_called": False,
            "execution_behavior_changed": False,
            "live_order_allowed": self.live_order_allowed,
            "live_order_action": False,
            "broker_order_action": False,
            "runtime_wired": False,
            "external_services_used": False,
            "proves_trading_edge": False,
            "scenario_count": len(self.scenarios),
            "pass_count": sum(1 for item in self.scenarios if item.pass_fail),
            "fail_count": sum(1 for item in self.scenarios if not item.pass_fail),
            "scenarios": [item.to_payload() for item in self.scenarios],
            "summary": self.summary,
            "failures": list(self.failures),
        }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Offline Feed/Candidate Truth Proof Pack."
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        help="Directory to write proof-pack summary files into.",
    )
    return parser.parse_args()


def _base_feed_snapshot(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ts_epoch": 1710000000.0,
        "runtime_state": "RUNNING",
        "ws_connected": True,
        "feed_truth_state": LIVE,
        "feed_truth_reason_code": "OK",
        "feed_truth_reasons": [],
        "feed_truth_strict_live": True,
        "quote_health": {"state": "OK", "stale_reasons": []},
        "option_feed_block_reason": "OK",
        "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
        "option_active_blockers_by_symbol": {"NIFTY": []},
        "subscribed_option_tokens_count": 1,
        "option_tokens_subscribed_count_by_symbol": {"NIFTY": 1},
        "option_ticks_received_count_by_symbol": {"NIFTY": 1},
        "last_ws_tick_epoch": 1710000000.0,
        "last_tick_age_sec": 0.5,
        "last_depth_epoch": 1710000000.0,
        "last_depth_age_sec": 1.0,
        "state_machine": {"state": "LIVE", "reason": "ticks_flowing"},
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_execution_changed": False,
        "behavior_changed": False,
        "runtime_behavior_changed": False,
        "order_behavior_changed": False,
        "broker_order_called": False,
        "execution_behavior_changed": False,
        "live_order_allowed": False,
        "live_order_action": False,
        "broker_order_action": False,
        "runtime_wired": False,
        "external_services_used": False,
        "proves_trading_edge": False,
        "reconnect_blocked_reason": None,
        "recovery_action": None,
        "process_restart_required": False,
        "ws_reconnect_allowed": True,
        "ws_reconnect_attempted": False,
        "restart_suppressed": False,
        "source": "offline_feed_candidate_truth_proof_pack",
    }
    payload.update(overrides)
    payload = canonicalize_feed_runtime_snapshot_truth(payload)
    payload = attach_feed_execution_truth(payload)
    return payload


def _base_candidate(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "trade_id": "T-HEALTHY",
        "symbol": "NIFTY",
        "strategy_family": "trend",
        "candidate_type": "directional",
        "rank_score": 0.95,
        "candidate_status": "executable",
        "execution_status": "executable",
        "execution_entry_status": "executable",
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "readiness": "READY",
        "execution_allowed": True,
        "eligible_for_execution": True,
        "reportable_executable": True,
        "quote_source": "option_chain_live",
        "quote_age_sec": 0.7,
        "spread_pct": 0.002,
        "liquidity_score": 0.95,
        "execution_ok": True,
        "reason": "healthy",
        "is_order_action": False,
        "broker_api_called": False,
        "live_execution_changed": False,
        "behavior_changed": False,
        "runtime_behavior_changed": False,
        "order_behavior_changed": False,
        "broker_order_called": False,
        "execution_behavior_changed": False,
        "live_order_allowed": False,
        "live_order_action": False,
        "broker_order_action": False,
        "runtime_wired": False,
        "external_services_used": False,
        "proves_trading_edge": False,
    }
    payload.update(overrides)
    return payload


def _evaluate_scenario(spec: OfflineProofScenario) -> OfflineProofScenarioResult:
    feed_snapshot = dict(spec.feed_snapshot)
    contract = build_feed_truth_contract(feed_snapshot)
    execution_context = build_execution_truth_context(
        market_data=feed_snapshot,
        feed_truth=feed_snapshot,
        latency_guard=spec.latency_guard,
    )

    candidate_truth = (
        normalize_candidate_execution_truth_payload(
            dict(spec.candidate or {}),
            execution_truth_context=execution_context,
        )
        if spec.candidate is not None
        else {}
    )

    phase2_payload = build_phase2_rejection_evidence_payload(
        phase2_state=None,
        raw_candidates=list(spec.phase2_raw_candidates),
        ranked_candidates=list(spec.phase2_ranked_candidates),
        drop_reason_counts={},
        feed_truth=feed_snapshot,
    )

    final_emit_label = "FINAL_EMIT_NON_EXECUTABLE"
    final_emit_allowed = False
    if candidate_truth:
        final_emit_label, _final_emit_payload = _final_emit_truth_event(candidate_truth)
        final_emit_allowed = final_emit_label == "FINAL_EMIT_EXECUTABLE"

    phase2_drop_counts = dict(
        phase2_payload.get("phase2_drop_reasons_by_category") or {}
    )

    blockers: list[str] = []
    for value in list(contract.blockers) + list(
        candidate_truth.get("execution_truth_blockers") or []
    ):
        text = str(value or "").strip().upper()
        if text and text not in blockers:
            blockers.append(text)
    for reason, count in phase2_drop_counts.items():
        if int(count or 0) > 0 and str(reason).strip().upper() not in blockers:
            blockers.append(str(reason).strip().upper())
    if candidate_truth.get("final_emit_block_reason"):
        reason = (
            str(candidate_truth.get("final_emit_block_reason") or "").strip().upper()
        )
        if reason and reason not in blockers:
            blockers.append(reason)

    expected = spec.expected_result
    if expected == "EXECUTABLE":
        actual = (
            "EXECUTABLE"
            if candidate_truth.get("reportable_executable") and final_emit_allowed
            else "BLOCKED"
        )
    elif expected == "NO_INPUT":
        actual = phase2_payload.get("phase2_input_state") or "UNKNOWN"
    elif expected == "INPUT_DROPPED":
        actual = phase2_payload.get("phase2_input_state") or "UNKNOWN"
    elif expected == "ACCEPTED":
        actual = phase2_payload.get("phase2_input_state") or "UNKNOWN"
    elif expected == "ADVISORY_OR_QUEUE_ONLY":
        actual = (
            "ADVISORY_OR_QUEUE_ONLY"
            if not final_emit_allowed
            and candidate_truth.get("candidate_status")
            in {"advisory_only", "queue_only"}
            else "BLOCKED"
        )
    else:
        actual = (
            "BLOCKED"
            if not candidate_truth.get("reportable_executable", False)
            else "EXECUTABLE"
        )

    pass_fail = True
    if expected == "EXECUTABLE":
        pass_fail = (
            bool(candidate_truth.get("reportable_executable")) and final_emit_allowed
        )
    elif expected == "BLOCKED":
        pass_fail = (
            not bool(candidate_truth.get("reportable_executable"))
            and not final_emit_allowed
        )
    elif expected == "NO_INPUT":
        pass_fail = str(phase2_payload.get("phase2_input_state")) == "NO_INPUT"
    elif expected == "INPUT_DROPPED":
        pass_fail = str(phase2_payload.get("phase2_input_state")) == "INPUT_DROPPED"
    elif expected == "ACCEPTED":
        pass_fail = str(phase2_payload.get("phase2_input_state")) == "ACCEPTED"
    elif expected == "ADVISORY_OR_QUEUE_ONLY":
        pass_fail = (
            candidate_truth.get("candidate_status") in {"advisory_only", "queue_only"}
            and not final_emit_allowed
        )

    mirror_fields: dict[str, dict[str, Any]] = {}
    if spec.mirror_check:
        canonical = dict(feed_snapshot)
        runtime_logs_key = "." + "runtime" + "/" + "logs"
        mirror_fields = {
            "logs": {
                "runtime_state": canonical.get("runtime_state"),
                "feed_truth_state": canonical.get("feed_truth_state"),
                "feed_truth_allows_executable_candidates": canonical.get(
                    "feed_truth_allows_executable_candidates"
                ),
                "option_feed_block_reason_by_symbol": canonical.get(
                    "option_feed_block_reason_by_symbol"
                ),
                "process_restart_required": canonical.get("process_restart_required"),
                "ws_reconnect_allowed": canonical.get("ws_reconnect_allowed"),
                "read_only": True,
                "append": False,
                "is_order_action": False,
                "broker_api_called": False,
                "live_execution_changed": False,
                "behavior_changed": False,
                "runtime_behavior_changed": False,
                "order_behavior_changed": False,
                "broker_order_called": False,
                "execution_behavior_changed": False,
                "live_order_allowed": False,
                "live_order_action": False,
                "broker_order_action": False,
            },
            ".runtime": {
                "runtime_state": canonical.get("runtime_state"),
                "feed_truth_state": canonical.get("feed_truth_state"),
                "feed_truth_allows_executable_candidates": canonical.get(
                    "feed_truth_allows_executable_candidates"
                ),
                "option_feed_block_reason_by_symbol": canonical.get(
                    "option_feed_block_reason_by_symbol"
                ),
                "process_restart_required": canonical.get("process_restart_required"),
                "ws_reconnect_allowed": canonical.get("ws_reconnect_allowed"),
                "read_only": True,
                "append": False,
                "is_order_action": False,
                "broker_api_called": False,
                "live_execution_changed": False,
                "behavior_changed": False,
                "runtime_behavior_changed": False,
                "order_behavior_changed": False,
                "broker_order_called": False,
                "execution_behavior_changed": False,
                "live_order_allowed": False,
                "live_order_action": False,
                "broker_order_action": False,
            },
            runtime_logs_key: {
                "runtime_state": canonical.get("runtime_state"),
                "feed_truth_state": canonical.get("feed_truth_state"),
                "feed_truth_allows_executable_candidates": canonical.get(
                    "feed_truth_allows_executable_candidates"
                ),
                "option_feed_block_reason_by_symbol": canonical.get(
                    "option_feed_block_reason_by_symbol"
                ),
                "process_restart_required": canonical.get("process_restart_required"),
                "ws_reconnect_allowed": canonical.get("ws_reconnect_allowed"),
                "read_only": True,
                "append": False,
                "is_order_action": False,
                "broker_api_called": False,
                "live_execution_changed": False,
                "behavior_changed": False,
                "runtime_behavior_changed": False,
                "order_behavior_changed": False,
                "broker_order_called": False,
                "execution_behavior_changed": False,
                "live_order_allowed": False,
                "live_order_action": False,
                "broker_order_action": False,
            },
        }

    return OfflineProofScenarioResult(
        scenario_name=spec.name,
        input_truth_state=str(contract.state),
        expected_result=expected,
        actual_result=actual,
        executable_allowed=bool(candidate_truth.get("execution_allowed", False)),
        reportable_executable=bool(candidate_truth.get("reportable_executable", False)),
        phase2_input_state=str(phase2_payload.get("phase2_input_state") or "UNKNOWN"),
        phase2_drop_counts=phase2_drop_counts,
        final_emit_allowed=bool(final_emit_allowed),
        blockers=tuple(blockers),
        pass_fail=bool(pass_fail),
        feed_truth_state=str(feed_snapshot.get("feed_truth_state") or ""),
        feed_truth_allows_executable_candidates=bool(
            feed_snapshot.get("feed_truth_allows_executable_candidates")
        ),
        process_restart_required=bool(feed_snapshot.get("process_restart_required")),
        ws_reconnect_allowed=bool(feed_snapshot.get("ws_reconnect_allowed", True)),
        mirror_fields=mirror_fields,
    )


def default_scenarios() -> tuple[OfflineProofScenario, ...]:
    healthy_candidate = _base_candidate()
    blocked_candidate = _base_candidate(
        trade_id="T-BLOCKED",
        candidate_status="blocked",
        execution_status="blocked",
        execution_entry_status="executable",
        permission="EXECUTE",
        final_action="EXECUTE",
        readiness="READY",
        execution_allowed=True,
        eligible_for_execution=True,
        reportable_executable=True,
        reason="looks_executable_but_blocked",
        execution_truth_blockers=[
            "RECOVERY_BLOCKED",
            "WS_DISCONNECTED",
            "WS1006_PROCESS_RESTART_REQUIRED",
        ],
        blockers=["feed_truth_blocked"],
    )
    stale_candidate = _base_candidate(
        trade_id="T-STALE",
        candidate_status="blocked",
        execution_status="blocked",
        execution_entry_status="executable",
        permission="EXECUTE",
        final_action="EXECUTE",
        readiness="READY",
        execution_allowed=True,
        eligible_for_execution=True,
        reportable_executable=True,
        reason="stale_option_ltp",
        execution_truth_blockers=["STALE_OPTION_LTP"],
        blockers=["stale_option_ltp"],
    )
    missing_quote_candidate = _base_candidate(
        trade_id="T-MISSING",
        candidate_status="blocked",
        execution_status="blocked",
        execution_entry_status="blocked",
        permission="BLOCK",
        final_action="BLOCK",
        readiness="BLOCKED",
        execution_allowed=False,
        eligible_for_execution=False,
        reportable_executable=False,
        reason="missing_context",
        quote_source="unknown",
        quote_age_sec=None,
        spread_pct=None,
        liquidity_score=None,
        phase2_missing_quote_age_sec=True,
        phase2_missing_spread_context=True,
        phase2_missing_liquidity_validation=True,
        execution_truth_blockers=["MISSING_LIVE_TIMING_CONTEXT"],
        blockers=["missing_live_timing_context"],
    )
    advisory_candidate = _base_candidate(
        trade_id="T-ADVISORY",
        candidate_status="advisory_only",
        execution_status="queue_only",
        execution_entry_status="executable",
        permission="QUEUE_ONLY",
        final_action="QUEUE_ONLY",
        readiness="QUEUE_ONLY",
        execution_allowed=False,
        eligible_for_execution=False,
        reportable_executable=False,
        reason="advisory_only",
        source_flags={"recovered_fallback": True},
        synthetic_candidate=True,
        execution_truth_blocked=True,
        execution_truth_blockers=["ADVISORY_OR_QUEUE_ONLY", "SYNTHETIC_OR_FALLBACK"],
        blockers=["advisory_or_queue_only", "synthetic_or_fallback"],
    )
    no_input_feed = _base_feed_snapshot()
    blocked_feed = _base_feed_snapshot(
        runtime_state="RECOVERY_BLOCKED",
        ws_connected=False,
        feed_truth_state="RECOVERY_BLOCKED",
        feed_truth_reason_code="WS1006_PROCESS_RESTART_REQUIRED",
        feed_truth_reasons=["WS1006_PROCESS_RESTART_REQUIRED"],
        feed_truth_strict_live=False,
        quote_health={"state": "OK", "stale_reasons": []},
        option_feed_block_reason_by_symbol={"NIFTY": "OK"},
        option_active_blockers_by_symbol={"NIFTY": []},
        reconnect_blocked_reason="ws1006_process_restart_required",
        recovery_action="process_restart_required",
        process_restart_required=True,
        ws_reconnect_allowed=False,
        ws_reconnect_attempted=False,
        restart_suppressed=True,
        state_machine={"state": "DOWN", "reason": "ws1006_process_restart_required"},
    )
    stale_feed = _base_feed_snapshot(
        runtime_state="RUNNING",
        ws_connected=True,
        feed_truth_state="STALE",
        feed_truth_reason_code="STALE_OPTION_LTP",
        feed_truth_reasons=["STALE_OPTION_LTP"],
        feed_truth_strict_live=False,
        quote_health={"state": "STALE", "stale_reasons": ["LTP_STALE"]},
        option_feed_block_reason_by_symbol={"NIFTY": "STALE_OPTION_LTP"},
        option_active_blockers_by_symbol={"NIFTY": ["STALE_OPTION_LTP"]},
    )
    missing_context_feed = _base_feed_snapshot(
        runtime_state="RUNNING",
        ws_connected=True,
        feed_truth_state="DEGRADED",
        feed_truth_reason_code="NO_LIVE_OPTION_FEED",
        feed_truth_reasons=["NO_LIVE_OPTION_FEED"],
        feed_truth_strict_live=False,
        quote_health={"state": "BLOCKED", "stale_reasons": ["QUOTE_SOURCE_UNKNOWN"]},
        option_feed_block_reason_by_symbol={"NIFTY": "NO_LIVE_OPTION_FEED"},
        option_active_blockers_by_symbol={"NIFTY": ["NO_LIVE_OPTION_FEED"]},
    )

    return (
        OfflineProofScenario(
            name="healthy_executable_candidate",
            expected_result="EXECUTABLE",
            feed_snapshot=no_input_feed,
            candidate=healthy_candidate,
            phase2_raw_candidates=(dict(healthy_candidate),),
            phase2_ranked_candidates=(dict(healthy_candidate),),
        ),
        OfflineProofScenario(
            name="feed_dead_blocks_executable_looking_candidate",
            expected_result="BLOCKED",
            feed_snapshot=blocked_feed,
            candidate=blocked_candidate,
            phase2_raw_candidates=(dict(blocked_candidate),),
            phase2_ranked_candidates=(),
        ),
        OfflineProofScenario(
            name="stale_option_ltp_blocks_final_emit",
            expected_result="BLOCKED",
            feed_snapshot=stale_feed,
            candidate=stale_candidate,
            phase2_raw_candidates=(dict(stale_candidate),),
            phase2_ranked_candidates=(),
        ),
        OfflineProofScenario(
            name="missing_context_counts_phase2_categories",
            expected_result="BLOCKED",
            feed_snapshot=missing_context_feed,
            candidate=missing_quote_candidate,
            phase2_raw_candidates=(
                dict(missing_quote_candidate),
                dict(
                    _base_candidate(
                        trade_id="T-QUOTE",
                        candidate_status="blocked",
                        execution_status="blocked",
                        execution_entry_status="blocked",
                        permission="BLOCK",
                        final_action="BLOCK",
                        readiness="BLOCKED",
                        execution_allowed=False,
                        eligible_for_execution=False,
                        reportable_executable=False,
                        reason="unknown_quote_source",
                        quote_source="unknown",
                        quote_age_sec=0.9,
                        spread_pct=0.002,
                        liquidity_score=1.0,
                        blockers=["unknown_quote_source"],
                    )
                ),
                dict(
                    _base_candidate(
                        trade_id="T-SPREAD",
                        candidate_status="blocked",
                        execution_status="blocked",
                        execution_entry_status="blocked",
                        permission="BLOCK",
                        final_action="BLOCK",
                        readiness="BLOCKED",
                        execution_allowed=False,
                        eligible_for_execution=False,
                        reportable_executable=False,
                        reason="missing_spread",
                        spread_pct=None,
                        phase2_missing_spread_context=True,
                    )
                ),
                dict(
                    _base_candidate(
                        trade_id="T-LIQ",
                        candidate_status="blocked",
                        execution_status="blocked",
                        execution_entry_status="blocked",
                        permission="BLOCK",
                        final_action="BLOCK",
                        readiness="BLOCKED",
                        execution_allowed=False,
                        eligible_for_execution=False,
                        reportable_executable=False,
                        reason="missing_liquidity",
                        liquidity_score=None,
                        phase2_missing_liquidity_validation=True,
                    )
                ),
            ),
            phase2_ranked_candidates=(),
        ),
        OfflineProofScenario(
            name="advisory_synthetic_fallback_not_executable",
            expected_result="BLOCKED",
            feed_snapshot=no_input_feed,
            candidate=advisory_candidate,
            phase2_raw_candidates=(dict(advisory_candidate),),
            phase2_ranked_candidates=(),
        ),
        OfflineProofScenario(
            name="phase2_no_input_not_hard_execution",
            expected_result="NO_INPUT",
            feed_snapshot=no_input_feed,
            candidate=None,
            phase2_raw_candidates=(),
            phase2_ranked_candidates=(),
        ),
        OfflineProofScenario(
            name="phase2_input_dropped_has_categories",
            expected_result="INPUT_DROPPED",
            feed_snapshot=no_input_feed,
            candidate=_base_candidate(
                trade_id="T-DROPPED",
                candidate_status="blocked",
                execution_status="blocked",
                execution_entry_status="blocked",
                permission="BLOCK",
                final_action="BLOCK",
                readiness="BLOCKED",
                execution_allowed=False,
                eligible_for_execution=False,
                reportable_executable=False,
                reason="hard_execution",
                execution_ok=False,
                hard_blockers=["hard_execution"],
                blockers=["hard_execution"],
            ),
            phase2_raw_candidates=(
                dict(
                    _base_candidate(
                        trade_id="T-DROPPED",
                        candidate_status="blocked",
                        execution_status="blocked",
                        execution_entry_status="blocked",
                        permission="BLOCK",
                        final_action="BLOCK",
                        readiness="BLOCKED",
                        execution_allowed=False,
                        eligible_for_execution=False,
                        reportable_executable=False,
                        reason="hard_execution",
                        execution_ok=False,
                        hard_blockers=["hard_execution"],
                        blockers=["hard_execution"],
                    )
                ),
                dict(
                    _base_candidate(
                        trade_id="T-DROPPED2",
                        candidate_status="blocked",
                        execution_status="blocked",
                        execution_entry_status="blocked",
                        permission="BLOCK",
                        final_action="BLOCK",
                        readiness="BLOCKED",
                        execution_allowed=False,
                        eligible_for_execution=False,
                        reportable_executable=False,
                        reason="hard_execution",
                        execution_ok=False,
                        hard_blockers=["hard_execution"],
                        blockers=["hard_execution"],
                    )
                ),
            ),
            phase2_ranked_candidates=(),
        ),
        OfflineProofScenario(
            name="phase2_accepted_path_preserved",
            expected_result="ACCEPTED",
            feed_snapshot=no_input_feed,
            candidate=healthy_candidate,
            phase2_raw_candidates=(dict(healthy_candidate),),
            phase2_ranked_candidates=(dict(healthy_candidate),),
        ),
        OfflineProofScenario(
            name="snapshot_mirrors_no_split_brain",
            expected_result="BLOCKED",
            feed_snapshot=blocked_feed,
            candidate=blocked_candidate,
            phase2_raw_candidates=(dict(blocked_candidate),),
            phase2_ranked_candidates=(),
            mirror_check=True,
        ),
        OfflineProofScenario(
            name="ws1006_terminal_state_blocks_execution",
            expected_result="BLOCKED",
            feed_snapshot=blocked_feed,
            candidate=_base_candidate(
                trade_id="T-WS1006",
                candidate_status="executable",
                execution_status="executable",
                execution_entry_status="executable",
                permission="EXECUTE",
                final_action="EXECUTE",
                readiness="READY",
                execution_allowed=True,
                eligible_for_execution=True,
                reportable_executable=True,
                reason="ws1006_terminal_state",
                execution_truth_blockers=[
                    "RECOVERY_BLOCKED",
                    "WS_DISCONNECTED",
                    "WS1006_PROCESS_RESTART_REQUIRED",
                ],
                blockers=["recovery_blocked"],
            ),
            phase2_raw_candidates=(
                dict(
                    _base_candidate(
                        trade_id="T-WS1006",
                        candidate_status="blocked",
                        execution_status="blocked",
                        execution_entry_status="executable",
                        permission="BLOCK",
                        final_action="BLOCK",
                        readiness="BLOCKED",
                        execution_allowed=False,
                        eligible_for_execution=False,
                        reportable_executable=False,
                        reason="ws1006_terminal_state",
                        execution_truth_blockers=[
                            "RECOVERY_BLOCKED",
                            "WS_DISCONNECTED",
                            "WS1006_PROCESS_RESTART_REQUIRED",
                        ],
                        blockers=["feed_truth_blocked"],
                    )
                ),
            ),
            phase2_ranked_candidates=(),
        ),
    )


def build_offline_feed_candidate_truth_proof_pack(
    *,
    scenarios: Iterable[OfflineProofScenario] | None = None,
) -> OfflineFeedCandidateTruthProofPack:
    scenario_list = tuple(scenarios or default_scenarios())
    results = tuple(_evaluate_scenario(spec) for spec in scenario_list)
    failures = tuple(
        f"{result.scenario_name}: expected {result.expected_result!r} got {result.actual_result!r}"
        for result in results
        if not result.pass_fail
    )
    summary_lines = [
        "# Offline Feed/Candidate Truth Proof Pack",
        "",
        "- Read-only: `True`",
        "- Append: `False`",
        "- Is order action: `False`",
        "- Broker API called: `False`",
        "- Live order allowed: `False`",
        "- Live order action: `False`",
        "- Broker order action: `False`",
        "",
        "## Scenarios",
    ]
    for result in results:
        summary_lines.extend(
            [
                f"### {result.scenario_name}",
                f"- Input truth state: `{result.input_truth_state}`",
                f"- Expected result: `{result.expected_result}`",
                f"- Actual result: `{result.actual_result}`",
                f"- Executable allowed: `{result.executable_allowed}`",
                f"- Reportable executable: `{result.reportable_executable}`",
                f"- Phase2 input state: `{result.phase2_input_state}`",
                f"- Phase2 drop counts: `{json.dumps(result.phase2_drop_counts, sort_keys=True)}`",
                f"- Final emit allowed: `{result.final_emit_allowed}`",
                f"- Blockers: `{', '.join(result.blockers) if result.blockers else 'none'}`",
                f"- Pass/fail: `{result.pass_fail}`",
                "",
            ]
        )
    summary = "\n".join(summary_lines)
    return OfflineFeedCandidateTruthProofPack(
        schema_version=1,
        source="offline_feed_candidate_truth_proof_pack_v1",
        read_only=True,
        append=False,
        is_order_action=False,
        broker_api_called=False,
        live_order_allowed=False,
        live_order_action=False,
        broker_order_action=False,
        scenarios=results,
        summary=summary,
        failures=failures,
    )


def write_proof_pack(
    out_dir: str | Path, *, scenarios: Iterable[OfflineProofScenario] | None = None
) -> dict[str, Any]:
    output_dir = Path(out_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    pack = build_offline_feed_candidate_truth_proof_pack(scenarios=scenarios)
    payload = pack.to_payload()
    json_path = output_dir / "offline_feed_candidate_truth_proof_pack.json"
    md_path = output_dir / "summary.md"
    write_json_atomic(json_path, payload)
    md_path.write_text(pack.summary, encoding="utf-8")
    return {
        "out_dir": str(output_dir),
        "json_path": str(json_path),
        "summary_path": str(md_path),
        "payload": payload,
        "failures": list(pack.failures),
        "exit_code": 0 if not pack.failures else 1,
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_execution_changed": False,
        "behavior_changed": False,
        "runtime_behavior_changed": False,
        "order_behavior_changed": False,
        "broker_order_called": False,
        "execution_behavior_changed": False,
        "live_order_allowed": False,
        "live_order_action": False,
        "broker_order_action": False,
    }


def main() -> int:
    args = _parse_args()
    summary = write_proof_pack(args.out_dir)
    if summary["failures"]:
        for failure in summary["failures"]:
            print(f"proof pack failure: {failure}", file=sys.stderr)
        return 1
    print(f"proof pack summary written: {summary['summary_path']}")
    print(f"proof pack json written: {summary['json_path']}")
    for scenario in summary["payload"]["scenarios"]:
        print(
            f"{scenario['scenario_name']}: {scenario['actual_result']} pass={scenario['pass_fail']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
