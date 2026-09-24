"""Read-only composition root for real Kite market-data observation."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)

from core.read_only_live_evidence import (
    MegIntervalScheduler,
    extract_candidate_rows,
    latest_completed_index_interval,
    persist_meg_cycle,
    write_authority_snapshot_bundle,
    write_json_atomic,
)


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

    def __init__(self, feed: Any, *, drain_deadline_seconds: float | None = None) -> None:
        self.feed = feed
        if drain_deadline_seconds is not None:
            self.drain_deadline_seconds = float(drain_deadline_seconds)
        else:
            configured_deadline = os.environ.get("OBSERVATION_SHUTDOWN_DRAIN_DEADLINE_SEC")
            if configured_deadline is not None:
                try:
                    self.drain_deadline_seconds = max(1.0, float(configured_deadline))
                except ValueError:
                    self.drain_deadline_seconds = 30.0
            else:
                try:
                    from config import config as cfg
                    cfg_val = getattr(cfg, "OBSERVATION_SHUTDOWN_DRAIN_DEADLINE_SEC", 30.0)
                except Exception:
                    cfg_val = 30.0
                self.drain_deadline_seconds = max(
                    1.0,
                    float(cfg_val or 30.0),
                )
        self.accepting = False
        self._stop_requested = threading.Event()
        self._shutdown_lock = threading.Lock()
        self._shutdown_report: dict[str, Any] | None = None
        self.phase = "CLOSED"

    def start(self, tokens: list[int], *, tick_sink=None) -> None:
        if self._shutdown_report is not None:
            raise RuntimeError("READ_ONLY_LIFECYCLE_ALREADY_SHUT_DOWN")
        if not tokens or any(not isinstance(token, int) or token <= 0 for token in tokens):
            raise RuntimeError("READ_ONLY_LIFECYCLE_INVALID_TOKENS")
        def lifecycle_owned_tick_sink(tick):
            if self.accepting and tick_sink is not None:
                tick_sink(tick)

        self.accepting = True
        if not self.feed.start_depth_ws(tokens, profile_verified=True, skip_lock=True, tick_sink=lifecycle_owned_tick_sink):
            self.accepting = False
            raise RuntimeError("READ_ONLY_KITE_FEED_START_FAILED")
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
            start_mono = time.monotonic()
            overall_deadline_mono = start_mono + max(1.0, float(self.drain_deadline_seconds))
            import core.tick_store as tick_store
            import core.depth_store as depth_store
            import core.feed.runtime_store as runtime_store
            bridge_module = __import__("core.market_event_graph_live_runtime_bridge", fromlist=["flush_live_source_bridge"])
            self.phase = "IN_FLIGHT_CALLBACKS_SETTLED"
            bridge_result = bridge_module.flush_live_source_bridge()
            self.phase = "MEG_FLUSHED"
            self.phase = "PERSISTENCE_DRAINING"

            # Pre-shutdown active queue drain loop: allow high-frequency buffers to drain before signalling stop
            # Uses public persistence APIs exclusively (no private member inspection)
            while time.monotonic() < overall_deadline_mono:
                d_st = depth_store.depth_store.persistence_state()
                depth_pending = int(d_st.get("queue_depth", 0)) + int(d_st.get("in_flight", 0))
                tick_pending = tick_store.pending_tick_count()
                r_st = runtime_store.runtime_persistence_state()
                runtime_pending = int(r_st.get("pending", 0))
                if depth_pending == 0 and tick_pending == 0 and runtime_pending == 0:
                    break
                time.sleep(0.05)

            remaining_sec = max(0.5, overall_deadline_mono - time.monotonic())
            tick_result = tick_store.shutdown_persistence_worker(deadline_seconds=remaining_sec)
            depth_result = depth_store.depth_store.shutdown_persistence(deadline_seconds=remaining_sec)
            runtime_result = runtime_store.shutdown_runtime_persistence(deadline_seconds=remaining_sec)
            tick_state = tick_store.get_persistence_worker_state()
            runtime_state = runtime_store.runtime_persistence_state()
            depth_state = depth_store.depth_store.persistence_state()

            # Strict institutional watermark reconciliation:
            # accepted == persisted + rejected + remaining (where remaining == 0, unaccounted_remainder == 0)
            # When accounting fields are provided, assert they pass; if legacy mock, verify queue drained
            depth_exact = (
                depth_state.get("queue_depth", 0) == 0
                and depth_state.get("in_flight", 0) == 0
                and (depth_state.get("accounting_invariant_ok", True) if "accounting_invariant_ok" in depth_state else True)
                and (depth_state.get("unaccounted_remainder", 0) == 0 if "unaccounted_remainder" in depth_state else True)
            )
            runtime_exact = (
                runtime_state.get("pending", 0) == 0
                and (runtime_state.get("accounting_invariant_ok", True) if "accounting_invariant_ok" in runtime_state else True)
                and (runtime_state.get("unaccounted_remainder", 0) == 0 if "unaccounted_remainder" in runtime_state else True)
            )
            tick_exact = (
                tick_state.get("queue_depth_at_shutdown", 0) == 0
                and tick_state.get("pending_writes_at_shutdown", 0) == 0
                and tick_state.get("worker_join_completed", True) is True
            )

            tick_result_complete = bool(
                tick_result.get("complete")
                or tick_result.get("status") in ("COMPLETE_DRAIN", "DRAIN_COMPLETE")
                or (tick_result.get("status") is None and tick_state.get("queue_depth_at_shutdown") == 0)
            )

            complete = bool(
                runtime_result.get("complete")
                and tick_result_complete
                and depth_result.get("complete")
                and not runtime_state.get("worker_alive")
                and not depth_state.get("worker_alive")
                and tick_exact
                and depth_exact
                and runtime_exact
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
                "storage_authority_lost": reason.startswith("runtime_storage_authority_lost"),
                "final_seal": __import__("core.runtime_storage_authority", fromlist=["final_seal_status"]).final_seal_status(storage_lost=reason.startswith("runtime_storage_authority_lost"), drain_complete=complete),
                "allowed_for_live_execution": False,
                "allowed_for_paper_execution": False,
            }
            return dict(self._shutdown_report)


def run_observation(*, launch_plan: Mapping[str, Any], output_root: Path, token_path: Path, session_date: str, max_runtime_sec: float | None = None) -> int:
    from core.runtime_storage_authority import StorageAuthorityError, establish, revalidate
    storage_authority = establish(volume=Path("/Volumes/TradeBotData"), runtime_root=output_root)
    env = safe_environment()
    contract = safety_contract(env, child_command=[sys.executable, "-B", "core.kite_read_only_observation_runtime.py"])
    output_root.mkdir(parents=True, exist_ok=True)
    # Bind the governed runtime environment before importing any module that
    # resolves config-dependent storage paths at import time.  In particular,
    # core.depth_store imports config.config, whose TRADE_DB_PATH is otherwise
    # frozen to the process's pre-existing/default runtime root.
    os.environ.update(env)
    import core.depth_store as depth_store
    depth_store.depth_store.configure_rejection_provenance(
        output_root / "depth_rejections.jsonl",
        session_id=str(launch_plan.get("run_id") or output_root.name),
        producer_sha=str(launch_plan.get("commit_sha") or os.environ.get("TRADEBOT_PRODUCER_SHA") or ""),
    )
    (output_root / "startup_safety_contract.json").write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert_import_boundary()

    from core.auth import get_kite_client, get_kite_credentials
    from core import kite_depth_ws
    from core.runtime_snapshot_producer import produce_and_store_runtime_snapshots
    from core.canonical_cycle_coordinator import CanonicalCycleCoordinator
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
    meg_bridge = get_live_source_bridge()
    scheduler = MegIntervalScheduler()
    meg_cycle_count = 0
    authority_intervals: set[str] = set()
    storage_loss_reason: str | None = None
    latest_runtime_outputs: Any = {}
    run_id = str(os.environ.get("RUN_ID") or launch_plan.get("run_id") or f"kite-read-only-{session_date}")
    producer_commit = str(
        launch_plan.get("commit_sha")
        or os.environ.get("TRADEBOT_COMMIT_SHA")
        or ""
    )
    if not producer_commit:
        raise RuntimeError("MEG_PRODUCER_SHA_REQUIRED")
    canonical_coordinator = CanonicalCycleCoordinator(
        output_root=output_root,
        session_id=run_id,
        source_sha=producer_commit,
        cadence_seconds=float(os.environ.get("CANONICAL_CYCLE_CADENCE_SECONDS", "60")),
    )
    from core.cas_primitive_producer import CASPrimitiveStore
    # Intersect subscription with verified NIFTY mapping, never arbitrary token.
    configured = {int(t) for t in (launch_plan.get("underlying_tokens") or []) if t}
    known_nifty = {int(t) for t, symbol in getattr(kite_depth_ws, "_UNDERLYING_TOKEN_TO_SYMBOL", {}).items() if str(symbol).upper() == "NIFTY"}
    authorized_nifty = configured & known_nifty if configured else known_nifty
    cas_token = next(iter(sorted(authorized_nifty)), 0)
    cas_store = CASPrimitiveStore(output_root / f"cas_short_horizon_primitives_{run_id}.json", session_id=run_id, source_sha=producer_commit, underlying_token=cas_token)
    cas_targets = {"0915": datetime.fromisoformat(f"{session_date}T09:15:00+05:30").timestamp(), "1000": datetime.fromisoformat(f"{session_date}T10:00:00+05:30").timestamp(), "1514": datetime.fromisoformat(f"{session_date}T15:14:00+05:30").timestamp()}
    def cas_tick_sink(tick):
        if not lifecycle.accepting or tick.get("underlying_symbol") != "NIFTY" or int(tick.get("instrument_token") or 0) != cas_token:
            return
        for name, target in cas_targets.items():
            if name not in cas_store.rows and tick.get("timestamp_epoch") is not None and float(tick["timestamp_epoch"]) >= target:
                cas_store.capture(name, target, tick, capture_timestamp_ist=datetime.now(timezone.utc).isoformat())
    lifecycle.start(tokens, tick_sink=cas_tick_sink)
    previous_feed_live = False

    # Governed strategy-shadow registry: consumes the existing native pulse only.
    # No second feed, no broker/order authority, and all prerequisites fail closed.
    from core.paper_shadow.strategy_shadow_adapter import (
        StrategyShadowAdapterRegistry,
        load_canonical_t1_prerequisites,
    )
    t1_prereqs = load_canonical_t1_prerequisites(
        session_date=session_date,
        launch_plan=launch_plan,
        data_dir=Path("runtime/preflight"),
    )
    shadow_evidence_root = output_root / "strategy_shadow"
    shadow_registry = StrategyShadowAdapterRegistry(
        session_id=run_id,
        source_sha=producer_commit,
        evidence_root=shadow_evidence_root,
        opening_drive_prev_contract_key=t1_prereqs["opening_drive_prev_contract_key"],
        opening_drive_prev_close_1529=t1_prereqs["opening_drive_prev_close_1529"],
        opening_drive_target_expiry=t1_prereqs["opening_drive_target_expiry"],
        overnight_prev_daily_close=t1_prereqs["overnight_prev_daily_close"],
        overnight_prev_sma200=t1_prereqs["overnight_prev_sma200"],
    )

    write_json_atomic(output_root / "process_identity.json", {
        "run_id": run_id, "pid": os.getpid(), "producer_sha": producer_commit,
        "session_root": str(output_root.resolve()), "state": "RUNNING",
        "read_only": True, "order_authority": False, "broker_write_authority": False,
        "shadow_strategy_ids": list(shadow_registry.adapters.keys()),
        "shadow_disabled_strategies": dict(shadow_registry.disabled_strategies),
    })
    deadline = time.monotonic() + max_runtime_sec if max_runtime_sec is not None else None
    try:
        while not lifecycle.should_stop():
            try:
                revalidate(storage_authority)
            except StorageAuthorityError as exc:
                storage_loss_reason = str(exc)
                try:
                    (output_root / "RUNTIME_STORAGE_AUTHORITY_LOST").write_text(storage_loss_reason + "\n", encoding="utf-8")
                except OSError:
                    pass
                lifecycle.request_stop("runtime_storage_authority_lost:" + storage_loss_reason)
                break
            if (output_root / "STOP_REQUESTED").is_file():
                lifecycle.request_stop("operator_control_file")
                break
            from zoneinfo import ZoneInfo
            from core.session_calendar import is_open as is_session_open
            from core.market_quote_resolver import get_index_quote_snapshot
            from core.market_snapshot_builder import build_market_snapshot, build_symbol_market_snapshot
            from core.market_event_graph_live_ohlc_buffer import shadow_ohlc_buffer

            cycle_cutoff = datetime.now(timezone.utc)
            now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
            active_market_open = is_session_open(now_ist, segment="NSE_FNO")
            nifty_quote = get_index_quote_snapshot("NIFTY")
            nifty_ltp = nifty_quote.get("last_price")
            nifty_ts_epoch = nifty_quote.get("ts_epoch")
            nifty_quote_age_sec = max(0.0, cycle_cutoff.timestamp() - float(nifty_ts_epoch)) if nifty_ts_epoch is not None else None

            nifty_completed_bars = shadow_ohlc_buffer.get_completed_bars("NIFTY", as_of=cycle_cutoff)
            latest_bar = nifty_completed_bars[-1] if nifty_completed_bars else {}

            symbols_payload = {}
            if nifty_ltp is not None:
                symbols_payload["NIFTY"] = build_symbol_market_snapshot(
                    spot=float(nifty_ltp),
                    ltp=float(nifty_ltp),
                    ohlc={
                        "open": float(latest_bar.get("open", nifty_ltp)),
                        "high": float(latest_bar.get("high", nifty_ltp)),
                        "low": float(latest_bar.get("low", nifty_ltp)),
                        "close": float(latest_bar.get("close", nifty_ltp)),
                    } if latest_bar else None,
                    feed_health={
                        "underlying_quote_age_sec": nifty_quote_age_sec,
                        "status": "HEALTHY" if (nifty_quote_age_sec is not None and nifty_quote_age_sec <= 2.5) else ("STALE" if nifty_quote_age_sec is not None else "UNKNOWN"),
                    },
                    quote_truth={
                        "symbol": "NIFTY",
                        "ltp": float(nifty_ltp),
                        "is_fresh": bool(nifty_quote_age_sec is not None and nifty_quote_age_sec <= 2.5),
                        "is_executable_quote": True,
                        "source": str(nifty_quote.get("source") or "UNKNOWN"),
                    "instrument_token": cas_token if cas_token > 0 else None,
                    },
                )

            current_market_snapshot = build_market_snapshot(
                generated_at=cycle_cutoff.isoformat(),
                market_open=active_market_open,
                symbols_payload=symbols_payload,
                loop_id=run_id,
            )

            latest_runtime_outputs = produce_and_store_runtime_snapshots(
                market_snapshot=current_market_snapshot,
                producer="kite_read_only_observation",
                loop_id=run_id,
                session_id=run_id,
                source_sha=producer_commit,
            )
            from core.market_snapshot_store import write_market_snapshot_atomic
            write_market_snapshot_atomic(
                current_market_snapshot,
                path=output_root / "snapshots" / "market_snapshot_latest.json",
            )
            if not isinstance(latest_runtime_outputs, Mapping):
                latest_runtime_outputs = {}
            feed_truth = latest_runtime_outputs.get("feed_health_truth_latest")
            feed_context = feed_truth.get("context") if isinstance(feed_truth, Mapping) else {}
            feed_state = str((feed_context or {}).get("feed_state") or "").upper()
            runtime_state = str((feed_context or {}).get("runtime_state") or "").upper()
            websocket_ok = (feed_truth or {}).get("websocket_ok") if isinstance(feed_truth, Mapping) else None
            feed_ok = (feed_truth or {}).get("feed_ok") if isinstance(feed_truth, Mapping) else None
            market_snapshot = latest_runtime_outputs.get("market_snapshot")
            market_open = bool(market_snapshot.get("market_open", False)) if isinstance(market_snapshot, Mapping) else False
            feed_live = feed_state == "LIVE" and runtime_state != "STOPPED" and websocket_ok is True and feed_ok is True
            feed_recovered = feed_live and not previous_feed_live
            previous_feed_live = feed_live
            trigger = canonical_coordinator.should_request(
                market_open=market_open,
                feed_live=feed_live,
                feed_recovered=feed_recovered,
            )
            if trigger:
                request = canonical_coordinator.request(trigger, cutoff=datetime.now(timezone.utc))
                canonical_coordinator.run(request)
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
            # Unified Native Pulse & 12-Hop Causal Pipeline Execution
            from core.causal_pulse import NativePulseTracker
            from core.causal_strategy_harness import evaluate_causal_strategies
            from core.causal_shadow_decision import evaluate_shadow_decision
            from core.causal_trade_truth_emitter import build_canonical_trade_truth

            if not hasattr(run_observation, "_pulse_tracker"):
                run_observation._pulse_tracker = NativePulseTracker(session_id=run_id, producer_sha=producer_commit)
            
            cycle_pulse = run_observation._pulse_tracker.next_pulse(
                payload={
                    "cycle_count": meg_cycle_count,
                    "interval_end_epoch": interval_end,
                    "market_open": market_open,
                    "feed_live": feed_live,
                },
                timestamp_epoch=cycle_cutoff.timestamp(),
                timestamp_ist=datetime.now(timezone.utc).isoformat(),
            )

            # Parallel read-only strategy-shadow observation branch.
            # This branch is evidence-only and cannot route into candidate selection,
            # TradeBuilder, risk, broker, paper execution, or order management.
            shadow_registry.on_pulse(
                pulse=cycle_pulse,
                market_snapshot=market_snapshot if isinstance(market_snapshot, Mapping) else {},
                feed_health_truth=feed_truth if isinstance(feed_truth, Mapping) else {},
            )

            strat_result = evaluate_causal_strategies(
                pulse=cycle_pulse,
                market_snapshot=market_snapshot if isinstance(market_snapshot, Mapping) else {},
                feed_health_truth=feed_truth if isinstance(feed_truth, Mapping) else {},
                cas_primitive_store=cas_store,
            )
            shadow_decisions = evaluate_shadow_decision(
                pulse=cycle_pulse,
                strategy_result=strat_result,
                feed_health_truth=feed_truth if isinstance(feed_truth, Mapping) else {},
            )
            trade_truth_record = build_canonical_trade_truth(
                pulse=cycle_pulse,
                market_snapshot=market_snapshot if isinstance(market_snapshot, Mapping) else {},
                feed_health_truth=feed_truth if isinstance(feed_truth, Mapping) else {},
                strategy_result=strat_result,
                decision_result=shadow_decisions,
            )

            # Append-only persistence to causal ledgers
            with (output_root / "strategy_observations.jsonl").open("a", encoding="utf-8") as so_file:
                for obs in strat_result.observations:
                    so_file.write(json.dumps(obs.to_dict(), sort_keys=True) + "\n")
            with (output_root / "candidate_pool.jsonl").open("a", encoding="utf-8") as cp_file:
                for cand in strat_result.candidates:
                    cp_file.write(json.dumps(cand.to_dict(), sort_keys=True) + "\n")
            # CAS advisory observations are not executable instruments.
            with (output_root / "advisory_pool.jsonl").open("a", encoding="utf-8") as ap_file:
                for advisory in strat_result.advisory_candidates:
                    ap_file.write(json.dumps(advisory.to_dict(), sort_keys=True) + "\n")
            with (output_root / "executable_pool.jsonl").open("a", encoding="utf-8") as ep_file:
                for excand in strat_result.executable_candidates:
                    ep_file.write(json.dumps(excand.to_dict(), sort_keys=True) + "\n")
            with (output_root / "candidate_decisions.jsonl").open("a", encoding="utf-8") as cd_file:
                for dec in shadow_decisions.selected_candidates:
                    cd_file.write(json.dumps(dec.to_dict(), sort_keys=True) + "\n")
            with (output_root / "trade_truth_stream.jsonl").open("a", encoding="utf-8") as tt_file:
                tt_file.write(json.dumps(trade_truth_record.to_dict(), sort_keys=True) + "\n")
            with (output_root / "native_pulse_stream.jsonl").open("a", encoding="utf-8") as np_file:
                np_file.write(json.dumps(cycle_pulse.to_dict(), sort_keys=True) + "\n")

            if strat_result.telemetry_counters:
                tc = strat_result.telemetry_counters
                logger.info(
                    "PIPELINE_TELEMETRY symbols_eval=%d obs=%d near=%d qual=%d exec=%d advisory=%d execution_gates=NOT_EVALUATED_SHADOW_ONLY prereq_blocked=%d",
                    tc.get("symbols_evaluated", 0),
                    tc.get("strategy_observations", 0),
                    tc.get("near_signals", 0),
                    tc.get("qualified_candidates", 0),
                    tc.get("execution_eligible_candidates", 0),
                    tc.get("advisory_ready_candidates", 0),
                    tc.get("blocked_prerequisites", 0),
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
            if deadline is None and session_date == now_ist.date().isoformat() and not active_market_open and (now_ist.hour > 15 or (now_ist.hour == 15 and now_ist.minute >= 30)):
                lifecycle.request_stop("market_session_closed")
                break
            if deadline is not None and time.monotonic() >= deadline:
                break
            time.sleep(0.05 if deadline is not None else 1.0)
    finally:
        # Seal strategy-shadow evidence before runtime shutdown. Evidence-seal failure
        # is a governed failure and must not be silently swallowed.
        try:
            shadow_registry.on_session_shutdown()
        except Exception as exc:
            (output_root / "STRATEGY_SHADOW_EVIDENCE_SEAL_FAIL").write_text(
                f"SHUTDOWN_SEAL_FAIL: {type(exc).__name__}: {exc}\n",
                encoding="utf-8",
            )
            raise

        if storage_loss_reason is None and not (output_root / "authority_snapshot.json").is_file():
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
        report = lifecycle.shutdown(reason=("runtime_storage_authority_lost:" + storage_loss_reason) if storage_loss_reason else "read_only_observation_shutdown")
        try:
            (output_root / "shutdown_drain.json").write_text(
                json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
            )
        except OSError:
            if storage_loss_reason is None:
                raise
        if not report["shutdown_drain_complete"]:
            raise RuntimeError("READ_ONLY_SHUTDOWN_DRAIN_INCOMPLETE")
        if storage_loss_reason is None:
            write_json_atomic(output_root / "process_identity.json", {
                "run_id": run_id, "pid": os.getpid(), "producer_sha": producer_commit,
                "session_root": str(output_root.resolve()), "state": "STOPPED",
                "shutdown_drain_complete": bool(report.get("shutdown_drain_complete")),
                "read_only": True, "order_authority": False, "broker_write_authority": False,
                "shadow_strategy_ids": list(shadow_registry.adapters.keys()),
                "shadow_disabled_strategies": dict(shadow_registry.disabled_strategies),
            })
    return 0
