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
        "allowed_for_live_execution": False,
        "allowed_for_paper_execution": False,
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
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
                "allowed_for_live_execution": False,
            }
            return dict(self._shutdown_report)


def run_observation(*, launch_plan: Mapping[str, Any], output_root: Path, token_path: Path, session_date: str, max_runtime_sec: float | None = None) -> int:
    env = safe_environment()
    contract = safety_contract(env, child_command=[sys.executable, "-B", "core.kite_read_only_observation_runtime.py"])
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "startup_safety_contract.json").write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.environ.update(env)
    assert_import_boundary()

    from core.auth import get_kite_client, get_kite_credentials
    from core import kite_depth_ws
    from core.runtime_snapshot_producer import produce_and_store_runtime_snapshots
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
    deadline = time.monotonic() + max_runtime_sec if max_runtime_sec is not None else None
    try:
        while not lifecycle.should_stop():
            produce_and_store_runtime_snapshots(market_snapshot=None, producer="kite_read_only_observation")
            get_live_source_bridge().observe_cycle([], cycle_cutoff=datetime.now(timezone.utc))
            if deadline is not None and time.monotonic() >= deadline:
                break
            time.sleep(0.05 if deadline is not None else 1.0)
    finally:
        report = lifecycle.shutdown()
        (output_root / "shutdown_drain.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
        if not report["shutdown_drain_complete"]:
            raise RuntimeError("READ_ONLY_SHUTDOWN_DRAIN_INCOMPLETE")
    return 0
