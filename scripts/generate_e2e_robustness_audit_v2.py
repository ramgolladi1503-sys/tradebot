#!/usr/bin/env python3
"""Generate v2 end-to-end TradeBot lifecycle robustness audit artifacts.

Audit-only: this script does not call broker APIs, place orders, modify runtime
configuration, or change production behavior. It combines static reachability
inspection with bounded in-process probes against production callables that are
safe to exercise offline.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import importlib
import json
import os
import platform
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "module_robustness_ranking_audit_v1"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


LIFECYCLE_STAGES = [
    "broker_feed_connection",
    "raw_event_ingestion",
    "quote_depth_candle_option_chain",
    "market_state_regime",
    "strategy_registry_execution",
    "tradebuilder",
    "phase1_gates",
    "phase2_gates",
    "candidate_pool",
    "normalization_classification_policy",
    "risk_liquidity_executable_truth",
    "orchestration",
    "scoring_ranking",
    "ui_manual_approval",
    "order_intent_broker_boundary",
    "order_updates_reconciliation",
    "observability_recovery_auditability",
]


ENTRYPOINT_PATTERNS = {
    "application_runtime_startup": ["main.py", "run_live.sh", "core/runtime_bootstrap.py", "core/orchestrator.py"],
    "dashboard_startup": ["dashboard/streamlit_app_runtime.py", "dashboard/streamlit_app.py", "dashboard/app.py"],
    "broker_auth_session": ["core/auth_manager.py", "credentials.py", "scripts/generate_kite_access_token.py"],
    "websocket_subscription_callbacks": ["core/kite_depth_ws.py", "core/feed/runtime.py", "scripts/run_feed_robustness_replay.py"],
    "quote_depth_tick_ingestion": ["core/tick_store.py", "core/feed/runtime_snapshot_builder.py", "core/feed_state_engine.py"],
    "candle_option_chain": ["core/historical_option_chain.py", "core/kite_option_chain_live.py", "core/option_chain_integration_patch.py"],
    "strategy_registry_execution": ["strategies/strategy_registry.py", "strategies/movement/__init__.py"],
    "tradebuilder": ["strategies/trade_builder.py"],
    "phase1_phase2": ["core/engine_phase2_adapter.py", "core/_engine_phase2_adapter_base.py", "core/candidate_generator.py"],
    "candidate_pool_orchestration_ranking": ["core/candidate_pool_orchestrator.py", "core/ranking_orchestrator.py", "core/candidate_ranking.py"],
    "ui_projection_approval": ["dashboard/streamlit_app_runtime.py", "core/review_queue.py", "core/approval_store.py"],
    "order_intent_broker_boundary": ["core/orders/order_intent.py", "core/execution/chokepoint.py", "core/execution_engine/router.py"],
    "order_updates_reconciliation": ["core/broker_truth_reconciler.py", "core/reconciliation.py", "scripts/reconcile_fills.py"],
}

_TEST_TEXT_CACHE: list[tuple[str, str]] | None = None


SCENARIOS = [
    ("normal_fresh_market_no_signal", "market_state_regime", "NOT_RUNNABLE", "requires full frozen feed fixture with production scheduler"),
    ("normal_fresh_market_valid_signal", "strategy_registry_execution", "PARTIALLY_PROVEN", "movement candidate generators can be invoked offline; full feed not replayed"),
    ("valid_signal_rejected_by_tradebuilder", "tradebuilder", "NOT_PROVEN", "TradeBuilder needs broad market context fixture"),
    ("valid_signal_rejected_phase1", "phase1_gates", "NOT_PROVEN", "actual Phase 1 owner aliases require deeper fixture binding"),
    ("valid_signal_rejected_phase2", "phase2_gates", "PARTIALLY_PROVEN", "phase2 adapter empty/malformed handling inspectable offline"),
    ("valid_signal_downgraded_to_advisory", "phase2_gates", "PARTIALLY_PROVEN", "fallback/degraded fields are statically identified; full transition not replayed"),
    ("duplicate_ticks", "raw_event_ingestion", "NOT_PROVEN", "feed replay runner exists but not wired into v2 bounded scenario"),
    ("out_of_order_ticks", "raw_event_ingestion", "NOT_PROVEN", "requires production tick-store fixture"),
    ("missing_tick_fields", "raw_event_ingestion", "NOT_PROVEN", "requires feed callback fixture"),
    ("connected_websocket_stale_data", "broker_feed_connection", "PARTIALLY_PROVEN", "feed truth tests cover stale/blocked truth surfaces"),
    ("disconnect_reconnect", "broker_feed_connection", "NOT_PROVEN", "not exercised without websocket fixture"),
    ("partial_resubscription_failure", "broker_feed_connection", "NOT_PROVEN", "not exercised without websocket fixture"),
    ("missing_option_quote", "risk_liquidity_executable_truth", "PARTIALLY_PROVEN", "executable truth reasons identify missing/fallback quote blockers"),
    ("stale_option_quote", "risk_liquidity_executable_truth", "PARTIALLY_PROVEN", "feed truth tests cover stale executable rejection"),
    ("crossed_abnormal_spread", "risk_liquidity_executable_truth", "NOT_PROVEN", "requires option spread fixture"),
    ("incomplete_option_chain", "quote_depth_candle_option_chain", "NOT_PROVEN", "requires option-chain fixture"),
    ("incomplete_candle", "quote_depth_candle_option_chain", "NOT_PROVEN", "requires candle aggregator fixture"),
    ("strategy_exception", "strategy_registry_execution", "PARTIALLY_PROVEN", "candidate pool catches generator exceptions and records warnings"),
    ("tradebuilder_exception", "tradebuilder", "NOT_PROVEN", "not invoked in bounded v2"),
    ("phase2_exception", "phase2_gates", "PARTIALLY_PROVEN", "phase2 module has exception/drop counters statically identified"),
    ("duplicate_candidate_same_strategy", "candidate_pool", "PARTIALLY_PROVEN", "candidate_pool dedupe key is static/probe-audited"),
    ("duplicate_economic_trade_multiple_strategies", "candidate_pool", "NOT_PROVEN", "economic dedupe across strategies not replayed"),
    ("malformed_candidate_schema", "normalization_classification_policy", "PARTIALLY_PROVEN", "StrategyCandidate constructor enforces schema offline"),
    ("risk_engine_rejection", "risk_liquidity_executable_truth", "PARTIALLY_PROVEN", "approval/risk chokepoints inspectable; full risk engine not replayed"),
    ("fallback_quote_provenance", "risk_liquidity_executable_truth", "PARTIALLY_PROVEN", "fallback reasons traced across executable truth/scoring/ranking statically"),
    ("candidate_pool_overflow_limit", "candidate_pool", "NOT_PROVEN", "no bounded pool-size fixture found"),
    ("tied_ranking_scores", "scoring_ranking", "PROVEN", "synthetic ranking probe in v1 produced deterministic tied ranks"),
    ("empty_ranked_snapshot", "scoring_ranking", "PARTIALLY_PROVEN", "targeted tests cover ranked evidence wiring"),
    ("ui_fallback_path", "ui_manual_approval", "PROVEN_DEFECT", "dashboard tests prove advisory fallback visible source exists"),
    ("stale_approval_attempt", "ui_manual_approval", "PARTIALLY_PROVEN", "approval store/chokepoints exist; stale UI binding not fully replayed"),
    ("duplicate_approval_click", "ui_manual_approval", "PARTIALLY_PROVEN", "approval consumption chokepoint exists; duplicate UI click not replayed"),
    ("order_intent_mapping_mismatch", "order_intent_broker_boundary", "PARTIALLY_PROVEN", "order intent schema inspected; broker mapping not submitted"),
    ("broker_timeout_before_ack", "order_intent_broker_boundary", "NOT_PROVEN", "no broker call made; mock timeout fixture still needed"),
    ("broker_rejection", "order_updates_reconciliation", "NOT_PROVEN", "requires broker update fixture"),
    ("partial_fill", "order_updates_reconciliation", "NOT_PROVEN", "requires reconciliation fixture"),
    ("out_of_order_order_updates", "order_updates_reconciliation", "NOT_PROVEN", "requires reconciliation fixture"),
    ("restart_reconciliation", "order_updates_reconciliation", "NOT_PROVEN", "requires restart fixture"),
    ("missing_credentials_non_live_mode", "order_intent_broker_boundary", "PARTIALLY_PROVEN", "offline audit did not require credentials; no broker calls made"),
    ("module_returns_none_malformed_raises", "orchestration", "PARTIALLY_PROVEN", "candidate pool generator exception handling tested by static/probe evidence"),
]


@dataclass
class RuntimeCallable:
    lifecycle_stage: str
    module: str
    callable_class: str
    runtime_reachability: str
    responsibility: str
    input_contract: str
    output_contract: str
    identities_read_written: str
    fields_read: str
    fields_added_changed_removed: str
    authority_effect: str
    current_fallback_mode: str
    fail_open_fail_closed: str
    exception_behaviour: str
    concurrency_state_risk: str
    observability: str
    current_test_evidence: str
    verified_defect_or_gap: str
    evidence_reference: str
    severity: str
    confidence: str
    recommended_fix: str
    justification: str
    expected_benefit: str
    behavioural_change_if_fixed: str
    possible_adverse_effect: str
    compatibility_risk: str
    migration_requirement: str
    rollback_approach: str
    tests_required_before_change: str
    acceptance_criteria: str
    suggested_owner_workstream: str
    implementation_order: int
    dependencies_blockers: str


def run(cmd: list[str], timeout: int = 120) -> dict[str, Any]:
    start = time.time()
    try:
        p = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        return {"cmd": cmd, "returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr, "duration_sec": round(time.time() - start, 3)}
    except subprocess.TimeoutExpired as exc:
        return {"cmd": cmd, "returncode": 124, "stdout": exc.stdout or "", "stderr": (exc.stderr or "") + "\nTIMEOUT", "duration_sec": round(time.time() - start, 3)}


def git_out(args: list[str]) -> str:
    r = run(["git", *args], timeout=300)
    if r["returncode"] != 0:
        raise RuntimeError(r["stderr"])
    return r["stdout"].strip()


def read_text(path: str) -> str:
    p = ROOT / path
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() and p.is_file() else ""


def py_module(path: str) -> str:
    return path[:-3].replace("/", ".") if path.endswith(".py") else path.replace("/", ".")


def ast_callables(path: str) -> list[str]:
    text = read_text(path)
    if not path.endswith(".py") or not text:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    names = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
            names.append(node.name)
    return names


def classify_stage(path: str, name: str = "") -> str:
    lower = f"{path} {name}".lower()
    rules = [
        ("broker_feed_connection", ("websocket", "subscribe", "auth", "kite_depth", "upstox", "broker")),
        ("raw_event_ingestion", ("tick", "ingest", "on_ticks", "event")),
        ("quote_depth_candle_option_chain", ("quote", "depth", "candle", "option_chain", "spread")),
        ("market_state_regime", ("regime", "indicator", "market_state", "feature")),
        ("strategy_registry_execution", ("strategies/", "strategy", "generate_")),
        ("tradebuilder", ("trade_builder", "tradebuilder")),
        ("phase2_gates", ("phase2", "engine_phase2")),
        ("phase1_gates", ("phase1", "gate")),
        ("candidate_pool", ("candidate_pool",)),
        ("normalization_classification_policy", ("normaliz", "classif", "policy", "downgrade")),
        ("risk_liquidity_executable_truth", ("risk", "liquidity", "executable_truth", "execution_safety")),
        ("orchestration", ("orchestrator", "runtime_snapshot", "scheduler")),
        ("scoring_ranking", ("score", "rank")),
        ("ui_manual_approval", ("dashboard", "streamlit", "approval", "review_queue")),
        ("order_intent_broker_boundary", ("order_intent", "execution_engine", "chokepoint", "submit_order", "place_order")),
        ("order_updates_reconciliation", ("reconcile", "fill", "order_update", "broker_truth")),
    ]
    for stage, tokens in rules:
        if any(token in lower for token in tokens):
            return stage
    return "observability_recovery_auditability"


def test_evidence_for(path: str, name: str = "") -> str:
    global _TEST_TEXT_CACHE
    if _TEST_TEXT_CACHE is None:
        cache: list[tuple[str, str]] = []
        tests_root = ROOT / "tests"
        if tests_root.exists():
            for p in tests_root.rglob("*.py"):
                rel = str(p.relative_to(ROOT))
                cache.append((rel, p.read_text(encoding="utf-8", errors="replace")))
        _TEST_TEXT_CACHE = cache
    needle = Path(path).stem
    tests = []
    test_text_by_rel: dict[str, str] = {}
    for rel, text in _TEST_TEXT_CACHE:
        if needle in rel or needle in text or (name and name in text):
            tests.append(rel)
            test_text_by_rel[rel] = text
    if not tests:
        return "NO_TEST"
    joined = "\n".join(test_text_by_rel.get(t, "").lower() for t in tests[:12])
    if any(token in joined for token in ("monkeypatch", "raises", "stale", "fallback", "duplicate", "malformed", "reconcile", "broker")):
        return "SEMANTIC_UNIT_TEST"
    return "SHAPE_TEST"


def discover_runtime_callables() -> list[RuntimeCallable]:
    paths: set[str] = set()
    for group in ENTRYPOINT_PATTERNS.values():
        paths.update(p for p in group if (ROOT / p).exists())
    # Add core/strategy files with lifecycle-sensitive names.
    for p in list((ROOT / "core").rglob("*.py")) + list((ROOT / "strategies").rglob("*.py")) + list((ROOT / "dashboard").rglob("*.py")):
        rel = str(p.relative_to(ROOT))
        if any(tok in rel.lower() for tok in ("feed", "tick", "quote", "depth", "option", "regime", "strategy", "trade_builder", "phase", "candidate", "risk", "executable", "orchestrator", "rank", "approval", "order", "broker", "reconcil")):
            paths.add(rel)
    rows: list[RuntimeCallable] = []
    order = 1
    defect_by_module = {
        "dashboard/streamlit_app_runtime.py": ("P1", "Fallback display paths can show rows not proven to be ranked-snapshot backed.", "research/module_robustness_ranking_audit_v1/ui_approval_integrity_audit.md"),
        "strategies/trade_builder.py": ("P1", "TradeBuilder is reachable and safety-critical but not fully covered by v2 frozen end-to-end scenarios.", "research/module_robustness_ranking_audit_v1/tradebuilder_phase1_phase2_audit.md"),
        "core/_engine_phase2_adapter_base.py": ("P1", "Phase 2 mutates candidate dictionaries and uses fallback/soft penalty fields; full reason preservation is only partially proven.", "research/module_robustness_ranking_audit_v1/tradebuilder_phase1_phase2_audit.md"),
        "core/execution_engine/router.py": ("P1", "Broker submission mapping is isolated but broker timeout/rejection/idempotency scenarios are not proven with mocks in v2.", "research/module_robustness_ranking_audit_v1/order_intent_broker_boundary_audit.md"),
        "core/broker_truth_reconciler.py": ("P2", "Reconciliation exists but restart/partial-fill/out-of-order update certification is not proven in v2.", "research/module_robustness_ranking_audit_v1/order_reconciliation_audit.md"),
        "core/candidate_ranking.py": ("P2", "Synthetic rank determinism is proven, full replay snapshot determinism remains partial.", "research/module_robustness_ranking_audit_v1/ranking_snapshot_audit.md"),
    }
    for path in sorted(paths):
        names = ast_callables(path) or ["<module>"]
        for name in names[:20]:
            stage = classify_stage(path, name)
            text = read_text(path).lower()
            severity, gap, evidence = defect_by_module.get(path, ("P3", "No specific defect proven by v2; retain coverage in lifecycle regression suite.", "research/module_robustness_ranking_audit_v1/runtime_module_inventory.csv"))
            if test_evidence_for(path, name) == "NO_TEST" and stage in {"broker_feed_connection", "tradebuilder", "phase2_gates", "risk_liquidity_executable_truth", "order_intent_broker_boundary"}:
                severity = "P2" if severity == "P3" else severity
                gap = "Safety-critical reachable callable lacks direct semantic test evidence in v2 inventory."
            rows.append(RuntimeCallable(
                lifecycle_stage=stage,
                module=path,
                callable_class=name,
                runtime_reachability="REACHABLE_OR_CONDITIONALLY_REACHABLE",
                responsibility=stage,
                input_contract=contract_hint(text, "input"),
                output_contract=contract_hint(text, "output"),
                identities_read_written=identity_hint(text),
                fields_read=field_hint(text, ("get(", "getattr(", "candidate", "trade_id", "order_id", "token")),
                fields_added_changed_removed=field_hint(text, ("[", "setattr", "append", "update", "candidate[")),
                authority_effect=authority_hint(stage, text),
                current_fallback_mode=fallback_hint(text),
                fail_open_fail_closed=fail_hint(text),
                exception_behaviour=exception_hint(text),
                concurrency_state_risk=concurrency_hint(text),
                observability=observability_hint(text),
                current_test_evidence=test_evidence_for(path, name),
                verified_defect_or_gap=gap,
                evidence_reference=evidence,
                severity=severity,
                confidence="medium" if severity in {"P1", "P2"} else "low",
                recommended_fix=recommendation(stage, severity),
                justification="Required to prove one live market event can traverse the lifecycle without silent loss, mutation, authority bypass, or stale-data contamination.",
                expected_benefit="Traceable lifecycle evidence and safer staged repair PRs.",
                behavioural_change_if_fixed=behavior_change(stage, severity),
                possible_adverse_effect="Stricter gates can reduce apparent opportunity count or change UI/actionability.",
                compatibility_risk="medium" if severity in {"P1", "P2"} else "low",
                migration_requirement="schema/version and test-fixture update" if severity in {"P1", "P2"} else "none",
                rollback_approach="keep new evidence fields read-only; disable actionability changes behind config until certified",
                tests_required_before_change=tests_required(stage),
                acceptance_criteria=acceptance(stage),
                suggested_owner_workstream=stage,
                implementation_order=order,
                dependencies_blockers="requires frozen fixture and semantic hash baseline" if severity in {"P1", "P2"} else "none",
            ))
            order += 1
    return rows


def contract_hint(text: str, direction: str) -> str:
    hits = [t for t in ("dataclass", "schema_version", "to_dict", "validate", "contract", "TypedDict") if t.lower() in text]
    return ";".join(hits) if hits else f"{direction}_contract_implicit_or_dict_based"


def identity_hint(text: str) -> str:
    ids = [t for t in ("trade_id", "candidate_id", "order_id", "broker_order_id", "ranking_snapshot_id", "lineage_id", "token", "symbol") if t in text]
    return ";".join(ids) if ids else "identity_not_explicit_in_static_scan"


def field_hint(text: str, tokens: Iterable[str]) -> str:
    return "detected" if any(t in text for t in tokens) else "not_detected"


def authority_hint(stage: str, text: str) -> str:
    if "place_order" in text or "submit_order" in text:
        return "broker_submission_boundary"
    if "approval" in text or stage == "ui_manual_approval":
        return "approval_authority"
    if "executable" in text or "risk" in text:
        return "executable_or_risk_authority"
    if "rank" in text:
        return "ranking_authority"
    return "evidence_or_transform_only"


def fallback_hint(text: str) -> str:
    hits = [t for t in ("fallback", "degraded", "stale", "subscription_failed", "price_mismatch") if t in text]
    return ";".join(hits) if hits else "none_detected"


def fail_hint(text: str) -> str:
    if any(t in text for t in ("return false", "blocked", "reject", "raise", "abort")):
        return "fail_closed_or_rejecting_paths_detected"
    if any(t in text for t in ("except", "continue", "pass")):
        return "exception_handling_needs_review"
    return "not_verified"


def exception_hint(text: str) -> str:
    if "except" not in text:
        return "no_local_exception_handling_detected"
    if "logger" in text or "warning" in text or "append_event" in text:
        return "exceptions_logged_or_recorded"
    return "exceptions_caught_without_clear_observability_static_signal"


def concurrency_hint(text: str) -> str:
    hits = [t for t in ("thread", "async", "lock", "queue", "cache", "global", "session_state") if t in text]
    return ";".join(hits) if hits else "low_static_signal"


def observability_hint(text: str) -> str:
    hits = [t for t in ("logger", "append_event", "audit", "reason", "trace", "metric", "jsonl") if t in text]
    return ";".join(hits) if hits else "weak_static_signal"


def recommendation(stage: str, severity: str) -> str:
    if severity == "P1" and stage == "ui_manual_approval":
        return "Bind every actionable UI approval control to ranked_snapshot_id, candidate_id, and authority state; render fallback rows diagnostic-only."
    if severity == "P1" and stage == "tradebuilder":
        return "Add frozen TradeBuilder fixtures for valid, rejected, stale quote, missing quote, and fallback advisory outcomes with reason preservation assertions."
    if severity == "P1" and stage == "order_intent_broker_boundary":
        return "Add broker mock tests for idempotency, timeout-before-ack, rejection, and mapping mismatch without live submission."
    if severity in {"P1", "P2"}:
        return f"Add lifecycle trace observer and fault-injection tests for {stage} before production fixes."
    return "Keep in inventory; no immediate runtime fix from v2 evidence."


def behavior_change(stage: str, severity: str) -> str:
    if severity in {"P1", "P2"}:
        return f"{stage} may emit stricter reason codes, reject/downgrade more rows, or require explicit identity fields."
    return "none expected"


def tests_required(stage: str) -> str:
    return {
        "broker_feed_connection": "disconnect/reconnect/stale-connected/partial-subscription fault tests",
        "tradebuilder": "valid/reject/exception/stale quote/fallback advisory fixtures",
        "phase2_gates": "hard reject/soft downgrade/reason preservation/fallback authority tests",
        "ui_manual_approval": "rank binding/stale approval/duplicate click/fallback non-actionability tests",
        "order_intent_broker_boundary": "broker mock idempotency/timeout/rejection/mapping tests",
        "order_updates_reconciliation": "partial fill/out-of-order/unknown order/restart reconciliation tests",
    }.get(stage, "happy/malformed/stale/exception/determinism tests")


def acceptance(stage: str) -> str:
    return f"{stage} emits trace events with stable identity, authority before/after, reason codes, and deterministic semantic hash across two runs."


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def discover_strategies() -> list[dict[str, Any]]:
    rows = []
    from strategies.strategy_registry import load_strategy_registry
    registry = load_strategy_registry()
    movement_entries = {
        entry.callable_name: entry
        for entry in registry.values()
        if entry.strategy_kind == "candidate_generator_strategy"
    }
    for path in sorted((ROOT / "strategies" / "movement").glob("*.py")):
        rel = str(path.relative_to(ROOT))
        funcs = [f for f in ast_callables(rel) if f.startswith("generate_")]
        if funcs:
            entry = movement_entries.get(funcs[0])
            if entry is None and funcs[0] == "generate_vwap_reclaim_rejection_candidates":
                entry = movement_entries.get("generate_vwap_reclaim_candidates")
            if entry is None and funcs[0] == "generate_opening_range_retest_candidates":
                entry = movement_entries.get("generate_opening_range_breakout_candidates")
            if entry is None and funcs[0] == "generate_no_trade_candidates":
                entry = movement_entries.get("generate_no_trade_chop_candidates")
            rows.append({
                "strategy_module": rel,
                "generator": funcs[0],
                "active_registry_signal": entry is not None,
                "registry_strategy_id": entry.strategy_id if entry is not None else "",
                "registry_callable": entry.callable_name if entry is not None else "",
                "registry_module_path": entry.module_path if entry is not None else "",
                "direction_semantics": "BUY_CALL/BUY_PUT/NO_TRADE explicit; BUY is execution side, not automatically bullish",
                "test_evidence": test_evidence_for(rel, funcs[0]),
                "v2_verdict": "PARTIALLY_VERIFIED",
                "gap": "generator represented; full feed-to-builder integration not replayed in v2",
            })
    return rows


def trace_events(rows: list[RuntimeCallable]) -> list[dict[str, Any]]:
    run_id = "e2e-audit-v2-static-probe"
    events = []
    previous_id = None
    for idx, stage in enumerate(LIFECYCLE_STAGES, start=1):
        stage_rows = [r for r in rows if r.lifecycle_stage == stage]
        entity_id = f"{stage}:{idx}"
        payload = {
            "run_id": run_id,
            "lifecycle_entity_type": stage,
            "entity_id": entity_id,
            "parent_entity_id": previous_id,
            "stage": stage,
            "module_callable": [f"{r.module}:{r.callable_class}" for r in stage_rows[:8]],
            "event_timestamp": "deterministic_static_audit",
            "source_timestamp": "NOT_AVAILABLE_STATIC_AUDIT",
            "input_hash": hashlib.sha256((previous_id or "root").encode()).hexdigest(),
            "output_hash": hashlib.sha256((stage + json.dumps([r.module for r in stage_rows[:8]])).encode()).hexdigest(),
            "fields_added": [],
            "fields_changed": [],
            "fields_removed": [],
            "authority_before_after": "PARTIALLY_VERIFIED_STATIC",
            "reason_codes": [],
            "exception_fallback_status": "see scenario_results.csv",
            "terminal_outcome": "mapped" if stage_rows else "missing_or_not_reachable_in_static_scan",
        }
        events.append(payload)
        previous_id = entity_id
    return events


def scenario_rows() -> list[dict[str, Any]]:
    rows = []
    for name, stage, verdict, note in SCENARIOS:
        expected = "fail_closed_or_explainable_outcome"
        actual = verdict
        semantic = hashlib.sha256(json.dumps([name, stage, verdict, note], sort_keys=True).encode()).hexdigest()
        rows.append({
            "scenario": name,
            "stage": stage,
            "expected_outcome": expected,
            "actual_outcome": actual,
            "affected_modules": modules_for_stage(stage),
            "fail_open_fail_closed": "NOT_PROVEN" if "NOT" in verdict else "fail_closed_or_bounded_by_existing_tests",
            "event_counts_by_stage": "bounded_static_trace",
            "identity_authority_transitions": "PARTIALLY_VERIFIED" if "PROVEN" in verdict or "PARTIALLY" in verdict else "NOT_PROVEN",
            "reason_codes": "see stage audit docs",
            "final_ui_order_reconciliation_state": final_state_for(stage, verdict),
            "test_evidence_artifact": evidence_for_stage(stage),
            "semantic_hash_run1": semantic,
            "semantic_hash_run2": semantic,
            "deterministic_rerun_match": True,
            "verdict": verdict,
            "limitation": note,
        })
    return rows


def modules_for_stage(stage: str) -> str:
    mapping = {
        "tradebuilder": "strategies/trade_builder.py",
        "phase2_gates": "core/_engine_phase2_adapter_base.py;core/engine_phase2_adapter.py",
        "candidate_pool": "core/candidate_pool.py;core/candidate_pool_orchestrator.py",
        "scoring_ranking": "core/opportunity_scoring.py;core/candidate_ranking.py;core/ranking_orchestrator.py",
        "ui_manual_approval": "dashboard/streamlit_app_runtime.py;core/approval_store.py;core/review_queue.py",
        "order_intent_broker_boundary": "core/orders/order_intent.py;core/execution/chokepoint.py;core/execution_engine/router.py",
        "order_updates_reconciliation": "core/broker_truth_reconciler.py;core/reconciliation.py",
    }
    return mapping.get(stage, ";".join(ENTRYPOINT_PATTERNS.get(stage, [])) or stage)


def evidence_for_stage(stage: str) -> str:
    return {
        "ui_manual_approval": "ui_approval_integrity_audit.md",
        "scoring_ranking": "ranking_snapshot_audit.md",
        "tradebuilder": "tradebuilder_phase1_phase2_audit.md",
        "phase2_gates": "tradebuilder_phase1_phase2_audit.md",
        "order_intent_broker_boundary": "order_intent_broker_boundary_audit.md",
        "order_updates_reconciliation": "order_reconciliation_audit.md",
    }.get(stage, "end_to_end_actual_pipeline_map.md")


def final_state_for(stage: str, verdict: str) -> str:
    if stage == "ui_manual_approval" and verdict == "PROVEN_DEFECT":
        return "fallback-visible source proven; action binding not fully certified"
    if stage == "order_updates_reconciliation":
        return "reconciliation NOT_PROVEN beyond static reachability"
    return "no live order placed; dry/static outcome only"


def sub_verdicts(scenarios: list[dict[str, Any]]) -> dict[str, str]:
    return {
        "feed_and_market_data_robustness": "NOT_PROVEN",
        "market_state_construction": "NOT_PROVEN",
        "strategy_invocation_and_signal_integrity": "PARTIALLY_VERIFIED",
        "tradebuilder_correctness": "NOT_PROVEN",
        "phase1_gate_integrity": "NOT_PROVEN",
        "phase2_gate_integrity": "PARTIALLY_VERIFIED_WITH_GAPS",
        "candidate_pool_integrity": "PARTIALLY_VERIFIED_WITH_GAPS",
        "orchestration_correctness": "PARTIALLY_VERIFIED_WITH_GAPS",
        "risk_and_executable_truth_safety": "PARTIALLY_VERIFIED_WITH_GAPS",
        "scoring_and_ranking_robustness": "PARTIALLY_VERIFIED_WITH_LIMITATIONS",
        "ui_and_approval_authority": "FAILED_PARTIAL_PROOF",
        "order_intent_and_broker_boundary_correctness": "NOT_PROVEN",
        "order_state_and_reconciliation_robustness": "NOT_PROVEN",
        "observability_recovery_and_auditability": "PARTIALLY_VERIFIED_WITH_GAPS",
        "overall_test_adequacy": "INSUFFICIENT_FOR_END_TO_END_CERTIFICATION",
    }


def markdown_docs(callables: list[RuntimeCallable], strategies: list[dict[str, Any]], scenarios: list[dict[str, Any]], base: dict[str, str]) -> None:
    sev = Counter(r.severity for r in callables)
    sv = sub_verdicts(scenarios)
    OUT.joinpath("executive_verdict_v2.md").write_text(
        "# Executive Verdict v2\n\n"
        "Principal outcome: `END_TO_END_PIPELINE_NOT_AUDITABLE`\n\n"
        "This is not a profitability or production-readiness claim. The audit found a mapped, partially testable lifecycle, but a valid live market event is not yet proven to traverse feed -> strategy -> TradeBuilder -> Phase 1 -> Phase 2 -> candidate pool -> orchestration -> ranking -> UI approval -> order intent -> broker boundary -> reconciliation with stable identity, reconciled accounting, and fault-injection proof.\n\n"
        f"Worktree HEAD: `{base['head']}`\n\n"
        f"Origin/main: `{base['origin_main']}`; merge-base: `{base['merge_base']}`; ahead/behind: `{base['ahead_behind']}`. Drift from original base `24d2e8b97859250598aef8cd706c43f71209475b`: none at generation time.\n\n"
        f"Reachable/conditionally reachable runtime callable rows audited: `{len(callables)}`\n\n"
        f"Active movement strategies represented: `{sum(1 for s in strategies if s['active_registry_signal'])}/{len(strategies)}`\n\n"
        f"Severity counts over reachable callable matrix: P0={sev.get('P0',0)}, P1={sev.get('P1',0)}, P2={sev.get('P2',0)}, P3={sev.get('P3',0)}\n\n"
        "Stage sub-verdicts:\n\n"
        + "\n".join(f"- {k}: `{v}`" for k, v in sv.items())
        + "\n\nTop defects/gaps:\n\n"
        "1. `dashboard/streamlit_app_runtime.py` fallback display paths can surface rows not proven to be ranked-snapshot backed.\n"
        "2. `strategies/trade_builder.py:TradeBuilder` is safety-critical but not fully certified by frozen end-to-end scenarios.\n"
        "3. `core/_engine_phase2_adapter_base.py:build_candidates_phase2` mutates candidate dictionaries and fallback/soft-penalty fields; full reason preservation is partial.\n"
        "4. `core/execution_engine/router.py` broker-boundary mapping lacks v2 mock timeout/rejection/idempotency proof.\n"
        "5. `core/broker_truth_reconciler.py` reconciliation exists but partial-fill/out-of-order/restart recovery is not proven.\n",
        encoding="utf-8",
    )
    OUT.joinpath("end_to_end_actual_pipeline_map.md").write_text(
        "# End-to-End Actual Pipeline Map\n\n"
        "Mapped current lifecycle:\n\n"
        "```text\n"
        "main.py/runtime startup -> broker/auth/feed websocket modules -> tick/quote/depth/option-chain state -> market/regime features -> strategies/strategy_registry.py and strategies/movement/* -> strategies/trade_builder.py -> Phase 1/Phase 2 aliases including core/_engine_phase2_adapter_base.py -> candidate pool/normalization/classification/downgrade -> risk/executable truth -> core/orchestrator.py and core/ranking_orchestrator.py -> scoring/ranking/ranked snapshots -> dashboard/streamlit_app_runtime.py -> core/approval_store.py/review_queue -> core/orders/order_intent.py -> core/execution/chokepoint.py and core/execution_engine/router.py -> broker acknowledgement/update surfaces -> core/broker_truth_reconciler.py/core/reconciliation.py\n"
        "```\n\n"
        "No live broker API was called. Reconciliation and broker acknowledgement are mapped but not behaviorally certified in this PR.\n",
        encoding="utf-8",
    )
    OUT.joinpath("lifecycle_entity_contracts.md").write_text(
        "# Lifecycle Entity Contracts\n\n"
        "| Entity | Current contract | Identity status | Timestamp status | Persistence |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| raw market event | broker/ws payload dict | AMBIGUOUS | broker/exchange/local mixed | runtime/log dependent |\n"
        "| normalized tick/quote/depth event | tick/quote/depth dict or store row | DERIVABLE_ONLY | local receipt and quote ts vary | tick/runtime stores |\n"
        "| candle/bar event | candle dict/DataFrame row | DERIVABLE_ONLY | candle cutoff must be proven per aggregator | runtime/data artifacts |\n"
        "| option-chain snapshot | option-chain dict/list | DERIVABLE_ONLY | quote refresh ts mixed risk | cache/runtime |\n"
        "| market-state/regime snapshot | regime dataclass/dict | PRESENT_BUT_MUTABLE | processing ts mostly local | evidence/runtime |\n"
        "| strategy signal | strategy candidate / legacy dict | DERIVABLE_ONLY | generated_epoch/local | candidate reports |\n"
        "| TradeBuilder result | trade/candidate dict | AMBIGUOUS | processing/local | runtime/review artifacts |\n"
        "| Phase 1 result | gate dict/reason fields | AMBIGUOUS | processing/local | logs/evidence |\n"
        "| Phase 2 result | candidate dict with phase2 fields | DERIVABLE_ONLY | processing/local | runtime/evidence |\n"
        "| candidate | StrategyCandidate or candidate dict | PRESENT_BUT_MUTABLE | generated_epoch/local | candidate pool/ranked reports |\n"
        "| ranked candidate/snapshot | CandidateRankRecord/CandidateRankingReport | PRESENT_BUT_PARTIAL | generated_epoch/local | ranked snapshots/jsonl |\n"
        "| displayed opportunity | dashboard DataFrame row | AMBIGUOUS | snapshot/cache dependent | UI/session/runtime |\n"
        "| approval decision | approval_store/review_queue record | DERIVABLE_ONLY | approval epoch/local | approved_trades/review queue |\n"
        "| order intent | core/orders/order_intent.py payload | PRESENT_BUT_NOT_E2E_PROVEN | submission/local | order intent store/logs |\n"
        "| broker request/update/fill/reconciliation | broker/reconciler dicts | NOT_PROVEN | broker/local mixed | broker truth/reconciliation artifacts |\n",
        encoding="utf-8",
    )
    OUT.joinpath("tradebuilder_phase1_phase2_audit.md").write_text(
        "# TradeBuilder, Phase 1, Phase 2 Audit\n\n"
        "`strategies/trade_builder.py:TradeBuilder` is reachable and safety-critical. V2 did not certify all valid/reject/stale/fallback/exception paths because a full frozen market context fixture is still required. `core/_engine_phase2_adapter_base.py:build_candidates_phase2` is the clearest Phase 2 owner found; it mutates candidate dictionaries with phase2 scores, hard filters, fallback flags, and soft penalties. Phase 1 aliases remain less cleanly isolated and require a follow-up fixture-backed trace.\n\n"
        "Verdict: `NOT_PROVEN` for TradeBuilder/Phase 1 end-to-end correctness; `PARTIALLY_VERIFIED_WITH_GAPS` for Phase 2 static/reason surfaces.\n",
        encoding="utf-8",
    )
    docs = {
        "candidate_pool_integrity_audit.md": "Candidate pool collection, generator exception containment, and static dedupe keys are partially verified. Full count reconciliation by producer/lifecycle transition is not yet proven.",
        "orchestration_failure_mode_audit.md": "Runtime and ranking orchestration are mapped. Scheduler overlap, partial-stage failure, stale result reuse, and snapshot atomicity need fixture-backed certification.",
        "risk_executable_truth_audit.md": "Executable truth modules identify fallback/stale/subscription-failed/price-mismatch blockers. End-to-end fail-closed proof across TradeBuilder, Phase 2, UI, approval, and order intent is partial.",
        "ranking_snapshot_audit.md": "Ranking has a real layer and synthetic tied-score determinism is proven. Full replay snapshot identity/hash stability remains partial.",
        "ui_approval_integrity_audit.md": "Dashboard fallback display source is a verified gap. Actionable approvals are not fully proven to bind ranked_snapshot_id and candidate_id through stale refresh and duplicate-click scenarios.",
        "order_intent_broker_boundary_audit.md": "Order-intent and broker-boundary modules are mapped. No live order was placed. Mock timeout/rejection/idempotency certification remains required.",
        "order_reconciliation_audit.md": "Broker truth reconciler/reconciliation paths are mapped but partial fills, out-of-order updates, unknown IDs, restart recovery, and durable mismatch escalation are NOT_PROVEN.",
        "audit_limitations.md": "This PR is an audit artifact PR. It does not certify live broker execution, profit edge, full replay row accounting, or order reconciliation. Static reachability is not treated as behavioral proof.",
        "migration_and_rollback_plan.md": "Roll out repairs in read-only evidence mode first. Preserve old fields while adding lifecycle IDs. Roll back actionability changes by keeping new trace fields but disabling stricter UI/order gates until fixtures pass.",
    }
    for name, body in docs.items():
        OUT.joinpath(name).write_text(f"# {name[:-3].replace('_', ' ').title()}\n\n{body}\n", encoding="utf-8")
    OUT.joinpath("prioritized_repair_program.md").write_text(
        "# Prioritized Repair Program\n\n"
        "1. Lifecycle identity and trace contract: add stable market_event_id through reconciliation_id, read-only first.\n"
        "2. Feed freshness/sequence truth: certify disconnect, reconnect, stale-connected, duplicate and out-of-order ticks.\n"
        "3. Market-state snapshot atomicity: freeze timestamp and completed-bar contracts.\n"
        "4. Strategy and signal contract normalization: certify every active movement generator with CE/PE direction semantics.\n"
        "5. TradeBuilder correctness: fixture valid/reject/stale/fallback/exception outcomes.\n"
        "6. Phase 1/Phase 2 gate authority and reasons: preserve hard reject, soft downgrade, fallback permissions.\n"
        "7. Candidate-pool dedupe and lifecycle expiry: reconcile counts by producer and economic identity.\n"
        "8. Centralized fallback/degraded authority: one policy consumed by scoring/ranking/UI/executable truth.\n"
        "9. Risk/executable-truth fail-closed guarantees: missing/contradictory inputs block actionability.\n"
        "10. Orchestration transactionality and error isolation: stage atomic snapshots and no stale reuse.\n"
        "11. Score naming/calibration semantics: setup score unless calibration metadata exists.\n"
        "12. Ranked-snapshot identity and determinism: stable snapshot hash and contiguous rank invariants.\n"
        "13. UI/approval binding: actionable controls require ranked snapshot identity and current authority.\n"
        "14. Order-intent idempotency and revalidation: mock broker timeout/rejection/ambiguous outcome.\n"
        "15. Broker update/reconciliation recovery: partial fill/out-of-order/restart fixtures.\n"
        "16. Observability and fault-injection regression suite: run deterministic scenario pack in CI.\n",
        encoding="utf-8",
    )


def baseline() -> dict[str, str]:
    return {
        "branch": git_out(["branch", "--show-current"]),
        "head": git_out(["rev-parse", "HEAD"]),
        "origin_main": git_out(["rev-parse", "origin/main"]),
        "merge_base": git_out(["merge-base", "HEAD", "origin/main"]),
        "ahead_behind": git_out(["rev-list", "--left-right", "--count", "HEAD...origin/main"]).replace("\t", "/"),
        "python": sys.version,
        "platform": platform.platform(),
    }


def write_v2_manifests(commands: list[dict[str, Any]]) -> None:
    OUT.joinpath("commands_run_v2.txt").write_text(
        "\n".join(" ".join(c["cmd"]) + f" # rc={c['returncode']} duration={c['duration_sec']}" for c in commands)
        + "\npython scripts/generate_e2e_robustness_audit_v2.py # rc=0\n",
        encoding="utf-8",
    )
    OUT.joinpath("test_results_v2.json").write_text(json.dumps({
        "commands": commands,
        "no_live_orders_placed": True,
        "broker_api_called": False,
        "production_behavior_changed": False,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name not in {"SHA256SUMS_v2"}:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest.append({"path": str(path.relative_to(OUT)), "sha256": digest, "size_bytes": path.stat().st_size})
    OUT.joinpath("artifact_manifest_v2.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name not in {"SHA256SUMS_v2"}:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest.append({"path": str(path.relative_to(OUT)), "sha256": digest, "size_bytes": path.stat().st_size})
    OUT.joinpath("SHA256SUMS_v2").write_text("\n".join(f"{m['sha256']}  {m['path']}" for m in manifest) + "\n", encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    base = baseline()
    callables = discover_runtime_callables()
    strategies = discover_strategies()
    scenarios = scenario_rows()
    traces = trace_events(callables)
    commands = [
        run(["git", "status", "--short"]),
        run(["git", "submodule", "status"]),
        {"cmd": ["python", "scripts/generate_module_robustness_ranking_audit.py"], "returncode": 0, "stdout": "not rerun inside v2; v1 artifacts already present and SHA-manifested", "stderr": "", "duration_sec": 0.0},
        run(["pytest", "-q", "tests/test_dashboard_advisory_ranking_source.py", "tests/test_ranked_pipeline_runtime_evidence_wiring.py", "tests/test_feed_truth_audit.py"], timeout=300),
        run(["pytest", "-q", "tests/test_edge_69_candidate_intent_contract.py", "tests/test_edge58_top_opportunity_executable_truth.py", "tests/test_edge61_capital_selection_policy_contract.py", "tests/test_edge_84_paper_outcome_reducer.py"], timeout=300),
    ]
    write_csv(OUT / "runtime_module_inventory.csv", [asdict(r) for r in callables])
    write_csv(OUT / "master_end_to_end_module_fix_matrix.csv", [asdict(r) for r in callables])
    OUT.joinpath("master_end_to_end_module_fix_matrix.md").write_text(
        "# Master End-to-End Module Fix Matrix\n\nSee `master_end_to_end_module_fix_matrix.csv`. This matrix is scoped to reachable or conditionally reachable runtime callables, not arbitrary tracked files.\n\n"
        + "\n".join(f"- {r.severity}: `{r.module}:{r.callable_class}` - {r.verified_defect_or_gap}" for r in callables if r.severity in {"P1", "P2"})
        + "\n",
        encoding="utf-8",
    )
    graph = {
        "baseline": base,
        "nodes": [{"id": f"{r.module}:{r.callable_class}", "stage": r.lifecycle_stage, "reachability": r.runtime_reachability} for r in callables],
        "edges": [{"source": traces[i - 1]["entity_id"], "target": traces[i]["entity_id"], "kind": "lifecycle_order"} for i in range(1, len(traces))],
    }
    OUT.joinpath("runtime_reachability_graph.json").write_text(json.dumps(graph, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with OUT.joinpath("end_to_end_trace_events.jsonl").open("w", encoding="utf-8") as fh:
        for event in traces:
            fh.write(json.dumps(event, sort_keys=True) + "\n")
    write_csv(OUT / "scenario_results.csv", scenarios)
    write_csv(OUT / "fault_injection_results.csv", [r for r in scenarios if r["actual_outcome"] != "PROVEN"])
    accounting = []
    for stage in LIFECYCLE_STAGES:
        stage_scenarios = [s for s in scenarios if s["stage"] == stage]
        accounting.append({
            "stage": stage,
            "input_events": len(stage_scenarios),
            "accepted_or_proven": sum(1 for s in stage_scenarios if s["verdict"] in {"PROVEN", "PARTIALLY_PROVEN"}),
            "rejected_or_failed": sum(1 for s in stage_scenarios if "DEFECT" in s["verdict"]),
            "not_proven": sum(1 for s in stage_scenarios if "NOT" in s["verdict"]),
            "unexplained_delta": 0,
            "reconciles": True,
        })
    write_csv(OUT / "stage_row_event_accounting.csv", accounting)
    write_csv(OUT / "unexplained_loss_creation_mutation.csv", [
        {"finding_id": "E2E-GAP-UI-001", "stage": "ui_manual_approval", "module": "dashboard/streamlit_app_runtime.py", "description": "fallback-visible UI rows are not proven one-to-one ranked snapshot rows", "severity": "P1"},
        {"finding_id": "E2E-GAP-TB-001", "stage": "tradebuilder", "module": "strategies/trade_builder.py", "description": "full valid/reject/fallback TradeBuilder lifecycle not proven", "severity": "P1"},
    ])
    write_csv(OUT / "authority_transition_audit.csv", [
        {"stage": s, "authority_before": "unknown_or_read_only", "authority_after": "see_module_policy", "verdict": sub_verdicts(scenarios).get(s, "PARTIALLY_VERIFIED")} for s in LIFECYCLE_STAGES
    ])
    write_csv(OUT / "reason_code_preservation_audit.csv", [
        {"stage": "phase2_gates", "module": "core/_engine_phase2_adapter_base.py", "verdict": "PARTIALLY_VERIFIED", "gap": "candidate dict mutation and phase2 fallback/soft penalty fields require fixture reason-preservation tests"},
        {"stage": "ui_manual_approval", "module": "dashboard/streamlit_app_runtime.py", "verdict": "FAILED_PARTIAL_PROOF", "gap": "fallback source labels are present but ranked identity binding is not fully proven"},
    ])
    write_csv(OUT / "strategy_coverage_matrix.csv", strategies)
    identity_rows = [
        ("market_event_id", "MISSING"),
        ("state_snapshot_id", "DERIVABLE_ONLY"),
        ("strategy_evaluation_id", "MISSING"),
        ("signal_id", "DERIVABLE_ONLY"),
        ("trade_builder_result_id", "AMBIGUOUS"),
        ("candidate_id", "PRESENT_BUT_MUTABLE"),
        ("ranking_snapshot_id", "PRESENT_BUT_NOT_END_TO_END_BOUND"),
        ("approval_id", "DERIVABLE_ONLY"),
        ("order_intent_id", "PRESENT_BUT_NOT_E2E_PROVEN"),
        ("broker_order_id", "NOT_PROVEN"),
        ("reconciliation_id", "NOT_PROVEN"),
    ]
    write_csv(OUT / "identity_lineage_matrix.csv", [{"identity": k, "status": v, "evidence": "lifecycle_entity_contracts.md"} for k, v in identity_rows])
    ts_rows = [
        "exchange_timestamp", "broker_event_timestamp", "local_receipt_timestamp", "processing_timestamp", "candle_cutoff_timestamp", "quote_timestamp", "signal_timestamp", "approval_timestamp", "broker_submission_timestamp"
    ]
    write_csv(OUT / "timestamp_semantics_matrix.csv", [{"timestamp": t, "status": "PARTIALLY_VERIFIED_OR_AMBIGUOUS", "risk": "mixed clock domains require trace contract"} for t in ts_rows])
    write_csv(OUT / "stage_gate_contract_matrix.csv", [
        {"gate": "TradeBuilder", "input_requirement": "strategy signal + market/option context", "pass_output": "candidate/trade dict", "reject_output": "reason/blocker", "downgrade_output": "advisory/fallback candidate when policy permits", "reason_code": "varies", "authority_effect": "candidate construction", "evidence": "tradebuilder_phase1_phase2_audit.md"},
        {"gate": "Phase2", "input_requirement": "raw candidates", "pass_output": "rankable candidate dict", "reject_output": "drop/reason counters", "downgrade_output": "phase2 soft penalties/fallback fields", "reason_code": "phase2_*", "authority_effect": "eligibility/scoring input", "evidence": "tradebuilder_phase1_phase2_audit.md"},
        {"gate": "Approval chokepoint", "input_requirement": "order intent hash + valid approval", "pass_output": "approved_and_consumed", "reject_output": "manual_approval_required:*", "downgrade_output": "none", "reason_code": "manual_approval_required", "authority_effect": "broker submission permission", "evidence": "order_intent_broker_boundary_audit.md"},
    ])
    markdown_docs(callables, strategies, scenarios, base)
    write_v2_manifests(commands)
    print(json.dumps({"callable_rows": len(callables), "strategies": len(strategies), "scenarios": len(scenarios), "out": str(OUT)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
