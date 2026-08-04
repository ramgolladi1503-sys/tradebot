"""Read-only composition root for real Kite market-data observation."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
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


def run_observation(*, launch_plan: Mapping[str, Any], output_root: Path, token_path: Path, session_date: str) -> int:
    env = safe_environment()
    contract = safety_contract(env, child_command=[sys.executable, "-B", "core.kite_read_only_observation_runtime.py"])
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
    started = kite_depth_ws.start_depth_ws(tokens, profile_verified=True, skip_lock=True)
    if not started:
        raise RuntimeError("READ_ONLY_KITE_FEED_START_FAILED")
    stop = threading.Event()
    try:
        while not stop.wait(1.0):
            produce_and_store_runtime_snapshots(market_snapshot=None, producer="kite_read_only_observation")
    finally:
        kite_depth_ws.stop_depth_ws(reason="read_only_observation_shutdown")
    return 0
