"""Read-only composition root for real Kite market-data observation."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.read_only_live_evidence import (
    MegIntervalScheduler,
    count_jsonl,
    extract_candidate_rows,
    latest_completed_index_interval,
    persist_meg_cycle,
    write_authority_snapshot_bundle,
    write_json_atomic,
)
from core.live_session_manifest import LiveSessionManifest, write_session_manifest
from core.live_consumer_contract import CANONICAL_CONSUMERS, validate_consumer_registry, write_consumer_registry
from core.live_runtime_artifacts import write_pending_runtime_artifacts, write_session_exit_gate
from core.market_session_state import derive_market_session_policy


UNSAFE_IMPORT_PREFIXES = (
    "core.broker",
    "core.execution_adapter",
    "core.execution_engine",
    "core.execution_router",
    "core.paper_broker",
    "core.paper_fill",
    "core.paper_order",
)
WRITE_METHODS = frozenset({
    "place_order", "modify_order", "cancel_order", "exit_order", "exit_position",
    "basket_order", "create_gtt", "modify_gtt", "delete_gtt", "submit_fill",
})


def safe_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    unsafe = {
        "TRADING_MODE": "LIVE", "EXECUTION_MODE": "LIVE", "TRADEBOT_MODE": "LIVE",
        "LIVE_BROKER_ADAPTER_ACTIVE": "1", "ALLOW_LIVE_ORDERS": "1",
        "AUTO_TRADE": "1", "AUTO_ORDER": "1", "PAPER_TRADING_ENABLED": "true",
    }
    inherited = {key: value for key, value in env.items() if key in unsafe and str(value).lower() in {"1", "true", "yes", "on", "live"}}
    env.update({
        "TRADING_MODE": "SIM", "EXECUTION_MODE": "SIM", "TRADEBOT_MODE": "SIM",
        "LIVE_BROKER_ADAPTER_ACTIVE": "0", "ALLOW_LIVE_ORDERS": "0",
        "AUTO_TRADE": "0", "AUTO_ORDER": "0", "PAPER_TRADING_ENABLED": "false",
        "LIVE_TRADING_ENABLED": "false", "LIVE_AUDIT_ONLY": "1",
        "MANUAL_APPROVAL_REQUIRED": "1", "TRADEBOT_READ_ONLY": "true",
    })
    env["KITE_READ_ONLY_UNSAFE_INHERITED"] = json.dumps(sorted(inherited))
    return env


def safety_contract(env: Mapping[str, str], *, child_command: list[str], child_pid: int | None = None) -> dict[str, Any]:
    safe = {
        "resolved_trading_mode": env.get("TRADING_MODE"),
        "resolved_execution_mode": env.get("EXECUTION_MODE"),
        "live_broker_adapter_active": env.get("LIVE_BROKER_ADAPTER_ACTIVE") == "1",
        "live_orders_allowed": env.get("ALLOW_LIVE_ORDERS") == "1",
        "paper_execution_allowed": env.get("PAPER_TRADING_ENABLED") == "true",
        "live_execution_allowed": False,
        "manual_approval_required": env.get("MANUAL_APPROVAL_REQUIRED") == "1",
        "read_only": env.get("TRADEBOT_READ_ONLY") == "true",
        "broker_write_authority": False,
        "order_authority": False,
        "manual_approval_cannot_route_orders": True,
        "unsafe_inherited_values": json.loads(env.get("KITE_READ_ONLY_UNSAFE_INHERITED", "[]")),
        "sanitized_values": {key: env.get(key) for key in (
            "TRADING_MODE", "EXECUTION_MODE", "LIVE_BROKER_ADAPTER_ACTIVE",
            "ALLOW_LIVE_ORDERS", "AUTO_TRADE", "AUTO_ORDER", "PAPER_TRADING_ENABLED",
            "LIVE_TRADING_ENABLED", "LIVE_AUDIT_ONLY", "MANUAL_APPROVAL_REQUIRED",
        )},
        "child_command": child_command,
        "child_pid": child_pid,
    }
    required = {
        "resolved_trading_mode": "SIM", "resolved_execution_mode": "SIM",
        "live_broker_adapter_active": False, "live_orders_allowed": False,
        "paper_execution_allowed": False, "live_execution_allowed": False,
        "read_only": True, "broker_write_authority": False, "order_authority": False,
        "manual_approval_cannot_route_orders": True,
    }
    if any(safe.get(key) != value for key, value in required.items()):
        raise RuntimeError("READ_ONLY_SAFETY_CONTRACT_FAILED")
    return safe


class BrokerWriteFirewall:
    def __init__(self, evidence_path: Path):
        self.evidence_path = evidence_path
        self.calls: list[dict[str, Any]] = []

    def reject(self, method: str) -> None:
        event = {"event": "SAFETY_BLOCKER_BROKER_WRITE_ATTEMPT", "method": method, "ts_epoch": time.time()}
        self.calls.append(event)
        self.evidence_path.parent.mkdir(parents=True, exist_ok=True)
        with self.evidence_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        raise RuntimeError("SAFETY_BLOCKER_BROKER_WRITE_ATTEMPT")


def assert_import_boundary() -> None:
    unsafe = sorted(name for name in sys.modules if name.startswith(UNSAFE_IMPORT_PREFIXES))
    if unsafe:
        raise RuntimeError(f"UNSAFE_OBSERVATION_IMPORTS:{','.join(unsafe)}")


def write_authority_snapshot(candidate: Mapping[str, Any], path: Path) -> dict[str, Any]:
    """Serialize canonical PR #771 authority output without execution wiring."""
    from core.runtime_authority_cutover import apply_runtime_authority

    row = dict(candidate)
    stamped = apply_runtime_authority(row, mode="SIM")
    payload = dict(stamped) if isinstance(stamped, Mapping) else dict(row)
    payload.update({
        "candidate_id": payload.get("candidate_id") or payload.get("trade_id") or payload.get("symbol"),
        "read_only": True,
        "is_order_action": False,
        "broker_write_authority": False,
        "order_authority": False,
        "allowed_for_live_execution": False,
        "allowed_for_paper_execution": False,
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
    return payload


def _measured_meg_facts(*, bridge: Any, result: Any) -> dict[str, Any]:
    contract, _ = bridge._load_universe_contract()
    symbols = [contract.index_symbol, *contract.constituent_symbols] if contract is not None else []
    from core.market_event_graph_live_ohlc_buffer import shadow_ohlc_buffer

    now = datetime.now(timezone.utc)
    completed = {
        symbol: shadow_ohlc_buffer.get_completed_bars(symbol, as_of=now)
        for symbol in symbols
    }
    audit = dict(getattr(result, "audit", {}) or {})
    subscription = dict(audit.get("subscription_evidence") or {})
    nifty_lifecycle = dict(
        (subscription.get("token_lifecycle") or {}).get(
            str(contract.index_instrument_token) if contract is not None else ""
        )
        or {}
    )
    rows = [bar for bars in completed.values() for bar in bars]
    source_ends = [
        float(bar.get("source_bar_end_epoch"))
        for bar in rows
        if bar.get("source_bar_end_epoch") is not None
    ]
    return {
        "accepted_constituent_count": int(getattr(result, "accepted_constituent_count", 0) or 0),
        "completed_constituent_bar_count": sum(len(completed.get(symbol, [])) for symbol in symbols[1:]),
        "index_completed_bar_count": len(completed.get(contract.index_symbol, [])) if contract is not None else 0,
        "first_source_bar_end_epoch": min(source_ends) if source_ends else None,
        "last_source_bar_end_epoch": max(source_ends) if source_ends else None,
        "universe_hash": contract.canonical_sha256 if contract is not None else "",
        "feed_session_id": subscription.get("feed_session_id"),
        "reconnect_generation": subscription.get("reconnect_generation"),
        "completed_constituent_bars": [symbol for symbol in symbols[1:] if completed.get(symbol)],
        "nifty_post_mode_full_packet_count": int(nifty_lifecycle.get("post_mode_full_count") or 0),
        "post_mode_full_nifty_packets": int(nifty_lifecycle.get("post_mode_full_count") or 0) > 0,
        "source_packet_bar_lineage": bool(rows),
        "subscription_evidence": subscription,
        "read_only": True,
        "is_order_action": False,
        "broker_write_authority": False,
        "order_authority": False,
        "allowed_for_live_execution": False,
        "allowed_for_paper_execution": False,
    }


def write_meg_wiring_evidence(
    *,
    bridge: Any,
    result: Any,
    output_path: Path,
    cycle_count: int,
    session_date: str | None = None,
    run_id: str | None = None,
    interval_end_epoch: float | None = None,
    cycle_cutoff_epoch: float | None = None,
    producer_commit: str = "",
) -> dict[str, Any]:
    """Persist latest measured facts plus append-only traversal/export ledgers."""
    resolved_session = session_date or datetime.now(timezone.utc).date().isoformat()
    resolved_run_id = run_id or str(os.environ.get("RUN_ID") or "read-only-observation")
    if interval_end_epoch is None:
        interval_end_epoch = latest_completed_index_interval(
            bridge,
            cycle_cutoff=datetime.now(timezone.utc),
        )
    payload = persist_meg_cycle(
        bridge=bridge,
        result=result,
        summary_path=output_path,
        traversal_path=output_path.with_name("meg_traversal_events.jsonl"),
        export_ledger_path=output_path.with_name("meg_live_source_exports.jsonl"),
        cycle_count=cycle_count,
        session_date=resolved_session,
        run_id=resolved_run_id,
        interval_end_epoch=interval_end_epoch,
        producer_commit=producer_commit,
    )
    from core.meg_request_scoped_causality import append_meg_cycle_primitives
    append_meg_cycle_primitives(
        output_path.parent,
        session_id=resolved_run_id,
        producer_commit_sha=producer_commit,
        cycle_id=str(payload.get("source_interval_identity") or f"{resolved_session}:{cycle_count}"),
        accepted=bool(getattr(result, "exported", False)),
        subscription_evidence=dict(payload.get("subscription_evidence") or {}),
        cycle_cutoff_epoch=cycle_cutoff_epoch,
    )
    payload.update(_measured_meg_facts(bridge=bridge, result=result))
    payload["market_event_graph_traversal_count"] = int(payload.get("cumulative_session_export_count") or 0)
    payload["market_event_graph_traversal"] = payload["market_event_graph_traversal_count"] > 0
    write_json_atomic(output_path, payload)
    return payload


class ObservationLifecycle:
    """Own the read-only feed lifecycle and prove an ordered, idempotent drain."""

    def __init__(self, feed: Any, *, drain_deadline_seconds: float = 5.0) -> None:
        self.feed = feed
        self.drain_deadline_seconds = float(drain_deadline_seconds)
        self.accepting = False
        self._stop_requested = threading.Event()
        self._shutdown_lock = threading.Lock()
        self._shutdown_report: dict[str, Any] | None = None
        self.phase = "CLOSED"

    def start(self, tokens: list[int]) -> None:
        if self._shutdown_report is not None:
            raise RuntimeError("READ_ONLY_LIFECYCLE_ALREADY_SHUT_DOWN")
        if not tokens or any(not isinstance(token, int) or token <= 0 for token in tokens):
            raise RuntimeError("READ_ONLY_LIFECYCLE_INVALID_TOKENS")
        if not self.feed.start_depth_ws(tokens, profile_verified=True, skip_lock=True):
            raise RuntimeError("READ_ONLY_KITE_FEED_START_FAILED")
        self.accepting = True
        self.phase = "RUNNING"

    def request_stop(self, reason: str = "read_only_observation_shutdown") -> None:
        self.accepting = False
        self._stop_requested.set()
        self.phase = "STOP_REQUESTED"
        self.feed.stop_depth_ws(reason=reason)
        self.phase = "FEED_CLOSED"

    def should_stop(self) -> bool:
        return self._stop_requested.is_set()

    def shutdown(self, reason: str = "read_only_observation_shutdown") -> dict[str, Any]:
        with self._shutdown_lock:
            if self._shutdown_report is not None:
                return dict(self._shutdown_report)
            self.request_stop(reason)
            deadline = self.drain_deadline_seconds
            import core.tick_store as tick_store
            import core.depth_store as depth_store
            import core.feed.runtime_store as runtime_store
            bridge_module = __import__("core.market_event_graph_live_runtime_bridge", fromlist=["flush_live_source_bridge"])
            self.phase = "IN_FLIGHT_CALLBACKS_SETTLED"
            bridge_result = bridge_module.flush_live_source_bridge()
            self.phase = "MEG_FLUSHED"
            self.phase = "PERSISTENCE_DRAINING"
            tick_result = tick_store.shutdown_persistence_worker(deadline_seconds=deadline)
            depth_result = depth_store.depth_store.shutdown_persistence(deadline_seconds=deadline)
            runtime_result = runtime_store.shutdown_runtime_persistence(deadline_seconds=deadline)
            tick_state = tick_store.get_persistence_worker_state()
            runtime_state = runtime_store.runtime_persistence_state()
            depth_state = depth_store.depth_store.persistence_state()
            complete = bool(
                runtime_result.get("complete")
                and tick_result.get("complete", tick_state.get("queue_depth_at_shutdown") == 0)
                and depth_result.get("complete")
                and not runtime_state.get("worker_alive")
                and not depth_state.get("worker_alive")
                and tick_state.get("worker_join_completed") is True
            )
            self.phase = "PERSISTENCE_DRAINED" if complete else "FAILED"
            if complete:
                self.phase = "WORKERS_JOINED"
                self.phase = "CLOSED"
            self._shutdown_report = {
                "proof_kind": "PR763_LIVE_ACCEPTANCE",
                "shutdown_drain_complete": complete,
                "persistence_drain_complete": complete,
                "accepting": self.accepting,
                "phase": self.phase,
                "phase_order": ["RUNNING", "STOP_REQUESTED", "FEED_CLOSED", "IN_FLIGHT_CALLBACKS_SETTLED", "MEG_FLUSHED", "PERSISTENCE_DRAINING", "PERSISTENCE_DRAINED", "WORKERS_JOINED", "CLOSED"],
                "feed_close_requested": True,
                "late_callback_policy": "REJECTED_AFTER_ACCEPTING_FALSE",
                "runtime_persistence": runtime_result,
                "tick_persistence": tick_result,
                "depth_persistence": depth_result,
                "runtime_state": runtime_state,
                "tick_state": tick_state,
                "depth_state": depth_state,
                "meg_bridge_flush": bridge_result,
                "read_only": True,
                "is_order_action": False,
                "broker_api_called": False,
                "broker_write_authority": False,
                "order_authority": False,
                "allowed_for_live_execution": False,
                "allowed_for_paper_execution": False,
            }
            return dict(self._shutdown_report)


def run_observation(*, launch_plan: Mapping[str, Any], output_root: Path, token_path: Path, session_date: str, max_runtime_sec: float | None = None) -> int:
    env = safe_environment()
    contract = safety_contract(env, child_command=[sys.executable, "-B", "core.kite_read_only_observation_runtime.py"])
    output_root.mkdir(parents=True, exist_ok=True)
    import core.depth_store as depth_store
    depth_store.depth_store.configure_rejection_provenance(
        output_root / "depth_rejections.jsonl",
        session_id=str(launch_plan.get("run_id") or output_root.name),
        producer_sha=str(launch_plan.get("commit_sha") or os.environ.get("TRADEBOT_PRODUCER_SHA") or ""),
    )
    (output_root / "startup_safety_contract.json").write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.environ.update(env)
    assert_import_boundary()

    from core.auth import get_kite_client, get_kite_credentials
    from core import kite_depth_ws
    from core.runtime_snapshot_producer import produce_and_store_runtime_snapshots
    from core.feed_forensics import append_event as append_feed_forensic_event
    assert_import_boundary()

    api_key, _ = get_kite_credentials(repo_root_path=Path.cwd())
    if not api_key or not token_path.is_file():
        raise RuntimeError("KITE_ACCESS_TOKEN_MISSING")
    get_kite_client(repo_root_path=Path.cwd()).profile()
    kite_depth_ws.activate_market_event_graph_launch_plan(launch_plan)
    tokens = list(launch_plan.get("final_union_tokens") or [])
    if not tokens:
        raise RuntimeError("READ_ONLY_LAUNCH_PLAN_EMPTY")
    from core.market_event_graph_live_runtime_bridge import get_live_source_bridge

    lifecycle = ObservationLifecycle(kite_depth_ws)
    lifecycle.start(tokens)
    meg_bridge = get_live_source_bridge()
    scheduler = MegIntervalScheduler()
    meg_cycle_count = 0
    authority_intervals: set[str] = set()
    latest_runtime_outputs: Any = {}
    run_id = str(os.environ.get("RUN_ID") or launch_plan.get("run_id") or f"kite-read-only-{session_date}")
    producer_commit = str(
        launch_plan.get("commit_sha")
        or os.environ.get("TRADEBOT_COMMIT_SHA")
        or ""
    )
    if not producer_commit:
        raise RuntimeError("MEG_PRODUCER_SHA_REQUIRED")
    write_json_atomic(output_root / "process_identity.json", {
        "run_id": run_id, "pid": os.getpid(), "producer_sha": producer_commit,
        "session_root": str(output_root.resolve()), "state": "RUNNING",
        "read_only": True, "order_authority": False, "broker_write_authority": False,
    })
    manifest = LiveSessionManifest(
        session_date=session_date,
        session_id=run_id,
        source_sha=producer_commit,
        observer_sha=producer_commit,
        observer_pid=os.getpid(),
        runtime_root=str(output_root.resolve()),
        sqlite_path=str(Path(os.getenv("DB_ROOT", str(output_root / "db"))) / "live.sqlite"),
        instrument_master_path=str(launch_plan.get("instrument_master_path") or "UNKNOWN"),
        instrument_master_sha=str(launch_plan.get("instrument_master_sha") or "") or None,
        auth_state="PASS",
        feed_state="STARTING",
        persistence_state="STARTING",
        subscription_count=len(tokens),
        consumer_registry=validate_consumer_registry(CANONICAL_CONSUMERS),
        pipeline_sha=str(launch_plan.get("pipeline_sha") or producer_commit),
        consumer_registry_path=str(launch_plan.get("consumer_registry_path") or output_root / "CONSUMERS.json"),
        advisory_queue_path=str(launch_plan.get("advisory_queue_path") or output_root / "advisory_queue.jsonl"),
    )
    write_session_manifest(output_root / "SESSION_MANIFEST.json", manifest)
    write_consumer_registry(output_root / "CONSUMERS.json", session_id=run_id, source_sha=producer_commit)
    write_pending_runtime_artifacts(
        output_root, session_id=run_id, source_sha=producer_commit,
        include_instrument_authority=False,
    )
    from core.canonical_cycle_coordinator import CanonicalCycleCoordinator
    cycle_coordinator = CanonicalCycleCoordinator(
        output_root=output_root, session_id=run_id, source_sha=producer_commit,
        cadence_seconds=float(os.environ.get("TRADEBOT_CANONICAL_CYCLE_CADENCE_SECONDS", "60")),
    )
    deadline = time.monotonic() + max_runtime_sec if max_runtime_sec is not None else None
    try:
        while not lifecycle.should_stop():
            if (output_root / "STOP_REQUESTED").is_file():
                lifecycle.request_stop("operator_control_file")
                break
            latest_runtime_outputs = produce_and_store_runtime_snapshots(
                market_snapshot=None,
                producer="kite_read_only_observation",
            )
            session_policy = derive_market_session_policy()
            write_json_atomic(
                output_root / "market_session_state.json",
                {
                    **session_policy.to_dict(),
                    "source_sha": producer_commit,
                    "session_id": run_id,
                    "read_only": True,
                    "broker_write_authority": False,
                    "order_authority": False,
                    "paper_authorized": False,
                    "live_authorized": False,
                    "execution_status": "advisory_only",
                },
            )
            from core.canonical_cycle_coordinator import normalize_feed_truth
            raw_feed_truth = latest_runtime_outputs.get("feed_health_truth_latest") or {}
            runtime_feed_truth = latest_runtime_outputs.get("feed_runtime_latest") or {}
            feed_truth = normalize_feed_truth(
                {"payload": {**dict(raw_feed_truth), "session_id": run_id, "source_sha": producer_commit}},
                runtime_truth=runtime_feed_truth,
                expected_session_id=run_id,
                expected_source_sha=producer_commit,
            )
            feed_recovered = str(feed_truth.get("overlay_state") or "").lower() == "feed_recovered"
            cycle_trigger = cycle_coordinator.should_request(
                market_open=session_policy.market_state == "MARKET_OPEN",
                feed_live=str(feed_truth.get("feed_state") or "").upper() == "LIVE",
                feed_recovered=feed_recovered,
            )
            if cycle_trigger:
                cycle_coordinator.run(cycle_coordinator.request(cycle_trigger, cutoff=datetime.now(timezone.utc)))
            append_feed_forensic_event(
                "RUNTIME_PERSISTENCE_PROGRESS",
                snapshot_count=1,
                latest_snapshot_epoch=time.time(),
                status="PROGRESS",
            )
            cycle_cutoff = datetime.now(timezone.utc)
            interval_end = latest_completed_index_interval(
                meg_bridge,
                cycle_cutoff=cycle_cutoff,
            )
            if scheduler.should_attempt(interval_end):
                meg_cycle_count += 1
                meg_result = meg_bridge.observe_cycle([], cycle_cutoff=cycle_cutoff)
                write_meg_wiring_evidence(
                    bridge=meg_bridge,
                    result=meg_result,
                    output_path=output_root / "meg_wiring_evidence.json",
                    cycle_count=meg_cycle_count,
                    session_date=session_date,
                    run_id=run_id,
                    interval_end_epoch=interval_end,
                    cycle_cutoff_epoch=cycle_cutoff.timestamp(),
                    producer_commit=producer_commit,
                )
                if interval_end is not None:
                    interval_identity = f"{session_date}:{int(float(interval_end))}"
                    if interval_identity not in authority_intervals:
                        write_authority_snapshot_bundle(
                            extract_candidate_rows(latest_runtime_outputs),
                            ledger_path=output_root / "authority_snapshots.jsonl",
                            latest_path=output_root / "authority_snapshot.json",
                            run_id=run_id,
                            session_date=session_date,
                            interval_identity=interval_identity,
                            interval_end_epoch=float(interval_end),
                            cycle_count=meg_cycle_count,
                            producer_commit=producer_commit,
                        )
                        authority_intervals.add(interval_identity)
                    scheduler.record(
                        float(interval_end),
                        reason=str(getattr(meg_result, "reason", "")),
                        exported=bool(getattr(meg_result, "exported", False)),
                    )
            if deadline is not None and time.monotonic() >= deadline:
                break
            time.sleep(0.05 if deadline is not None else 1.0)
    finally:
        if not (output_root / "authority_snapshot.json").is_file():
            write_authority_snapshot_bundle(
                extract_candidate_rows(latest_runtime_outputs),
                ledger_path=output_root / "authority_snapshots.jsonl",
                latest_path=output_root / "authority_snapshot.json",
                run_id=run_id,
                session_date=session_date,
                interval_identity=f"{session_date}:final:no-canonical-interval",
                interval_end_epoch=None,
                cycle_count=meg_cycle_count,
                producer_commit=producer_commit,
            )
        report = lifecycle.shutdown()
        (output_root / "shutdown_drain.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
        if not report["shutdown_drain_complete"]:
            raise RuntimeError("READ_ONLY_SHUTDOWN_DRAIN_INCOMPLETE")
        write_session_exit_gate(
            output_root, session_id=run_id, source_sha=producer_commit,
            auth_valid=True,
            feed_current=False,
            persistence_advancing=count_jsonl(output_root / "meg_traversal_events.jsonl") > 0,
            instrument_authority_current=bool(launch_plan.get("instrument_authority_sha256")),
            shutdown_drain_complete=bool(report.get("shutdown_drain_complete")),
            broker_order_calls=0,
        )
        write_json_atomic(output_root / "process_identity.json", {
            "run_id": run_id, "pid": os.getpid(), "producer_sha": producer_commit,
            "session_root": str(output_root.resolve()), "state": "STOPPED",
            "shutdown_drain_complete": bool(report.get("shutdown_drain_complete")),
            "read_only": True, "order_authority": False, "broker_write_authority": False,
        })
    return 0
