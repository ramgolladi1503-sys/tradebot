from config import config as cfg
import logging
import hashlib
import os
import time
import threading
import json
import re
import atexit
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from core.auth import get_kite_ticker
from core.events import write_json_atomic
from core.kite_client import kite_client
from core.depth_store import depth_store
from core.tick_store import (
    get_last_tick,
    get_ltp,
    get_max_tick_epoch,
    insert_tick,
    record_tick_epoch,
    write_enqueue_count,
    write_flush_count,
    write_queue_depth,
)
from core.time_utils import is_market_open_ist, now_utc_epoch, now_ist
from core.runtime_boot_identity import stamp_runtime_payload
from core.feed_runtime import build_canonical_feed_truth_state
from core.feed_robustness_evidence import collector as feed_evidence
from core.feed_fd_trace import process_fd_count, record_trace as record_fd_trace, reset_trace as reset_fd_trace
from core.feed_recovery_coordinator import FeedRecoveryCoordinator, get_feed_recovery_coordinator
from core.auth_manager import (
    clear_auth_required_state,
    invalidate_cache,
    is_auth_error,
    set_auth_required_state,
)
from core.auth_health import get_kite_auth_health
from core.feed_restart_guard import feed_restart_guard
from core.feed_circuit_breaker import is_tripped as feed_breaker_tripped, trip as trip_feed_breaker
from core.market_data_monitor import get_feed_health_monitor, record_depth, record_tick
from core.market_event_graph_live_observation_registry import (
    BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET,
    load_observation_registry,
    build_observation_subscription_merge,
    observation_tokens,
)
from core.market_event_graph_live_ohlc_buffer import record_live_source_shadow_tick
from core.market_event_graph_live_launch_plan import load_launch_plan
from core.unified_live_validation_pr748_756.campaign_contract import EVIDENCE_ROOT_ENV
from core.feed.runtime_store import write_runtime_snapshot as write_feed_runtime_snapshot
from core.feed.runtime_store import canonicalize_feed_runtime_snapshot_truth
from core.feed_health_duration import build_feed_health_duration_artifact
from core.runtime_status_overlay import (
    derive_effective_ws_connected,
    derive_feed_ok,
    publish_feed_unhealthy_status_overlay,
)
from core.feed_truth_state import classify_feed_truth_state
from core import campaign_raw_diagnostics
from core.feed_execution_truth import attach_feed_execution_truth
from core import risk_halt
from core.paths import repo_root, logs_dir, runtime_dir
from core.log_writer import get_jsonl_writer, get_rotating_logger
from core.run_lock import RunLock
from core.runtime_lifecycle import lifecycle
from core.ws_handshake_credential_proof import (
    build_ws_auth_failure_proof_event,
    build_ws_handshake_attempt_event,
)
from core.blocker_lifecycle import (
    build_feed_owner_key,
    evaluate_feed_symbol_blockers,
    get_blocker_registry,
    top_active_code,
)

def get_latest_tick_rows_db(tokens: list[int] | None) -> dict[int, dict]:
    """
    Backward-compat shim for tests/legacy call sites.

    Contract check forbids importing tick-store DB helper APIs directly here; this
    implementation uses the per-token accessor which is memory-first and DB-fallback.
    """
    out: dict[int, dict] = {}
    for tok in list(tokens or []):
        try:
            tok_int = int(tok)
        except Exception:
            continue
        tick = get_last_tick(tok_int, allow_db=True)
        if not isinstance(tick, dict):
            continue
        if tick.get("ts_epoch") is None:
            continue
        out[tok_int] = {
            "ts_epoch": tick.get("ts_epoch"),
            "ltp": tick.get("ltp"),
        }
    return out

try:
    from kiteconnect import KiteTicker
except Exception:
    KiteTicker = None

_KITE_TICKER = None
_KITE_TICKER_LOCK = threading.Lock()
_WATCHDOG_THREAD = None
_WATCHDOG_STOP = None
_LAST_TOKENS = []
_PENDING_SUBSCRIBE_TOKENS = set()
_PENDING_UNSUBSCRIBE_TOKENS = set()
_PENDING_MODE_FULL_TOKENS = set()
_LAST_MUTATION_RESULT = None
_SOCKET_GENERATION = 0

_LAST_DESIRED_TOKENS: list[int] | None = None
_UNDERLYING_TOKENS: set[int] = set()
_UNDERLYING_TOKEN_TO_SYMBOL: dict[int, str] = {}
_TOKEN_TO_SYMBOL: dict[int, str] = {}
_UNDERLYING_LOGGED_MISSING = False
_SYMBOL_LAST_LTP_TS: dict[str, float] = {}
_SYMBOL_LAST_DEPTH_TS: dict[str, float] = {}
_SYMBOL_LAST_OPTION_TICK_TS: dict[str, float] = {}
# Token-level hysteresis for subscription pruning. This is intentionally in-memory only:
# if the process restarts, we will re-learn staleness from live ticks.
_STALE_PRUNE_STRIKES_BY_TOKEN: dict[int, int] = {}
_LAST_WS_TICK_EPOCH: float = 0.0
_LAST_MSG_TS_BY_TOKEN: dict[int, float] = {}
_LAST_PAYLOAD_TS_BY_TOKEN: dict[int, float] = {}
_FEED_SESSION_ID: str = ""
_FEED_RECONNECT_GENERATION = 0
_FEED_CONNECTION_START_EPOCH: float | None = None
_FEED_ON_TICKS_ROW_SEQ = 0
_RESTART_LOCK = threading.RLock()
_RESTART_ASYNC_LOCK = threading.Lock()
_RESTART_ASYNC_THREAD = None
_LAST_FULL_RESTART_EPOCH = 0.0
_FULL_RESTARTS = []
_STALE_STRIKES = 0
_WARMUP_PENDING = False
_LOG_PATH = logs_dir() / "depth_ws_watchdog.log"
_TICK_INGEST_ERROR_PATH = logs_dir() / "tick_ingest_errors.jsonl"
_TICK_INGEST_ERROR_WRITER = get_jsonl_writer(_TICK_INGEST_ERROR_PATH)
_TICK_INGEST_ERROR_LOCK = threading.Lock()
_LAST_TICK_INGEST_ERROR_TS = 0.0
_FEED_RUNTIME_SNAPSHOT_WRITE_COUNT = 0
_DEPTH_WS_LOCK: RunLock | None = None
_DEPTH_WS_LOCK_ACQUIRED = False
_STOP_REQUESTED = False
_SCHEMA_LOG_TS = 0.0
_INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "SENSEX"}
_AUTH_REQUIRED_LATCH = False
_SUBSCRIPTION_REQUESTED_TOKENS: set[int] = set()
_SUBSCRIPTION_REQUEST_SUCCEEDED_TOKENS: set[int] = set()
_MODE_REQUEST_SUCCEEDED_TOKENS: set[int] = set()
_FULL_PAYLOAD_OBSERVED_TOKENS: set[int] = set()
_MODE_COMMAND_LOCAL_SEND_SUCCEEDED_TOKENS: set[int] = set()
_MODE_COMMAND_FINAL_FULL_TOKENS: set[int] = set()
_SUBSCRIPTION_REQUESTED_EPOCH_BY_TOKEN: dict[int, float] = {}
_SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN: dict[int, float] = {}
_MODE_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN: dict[int, float] = {}
_MODE_COMMAND_LOCAL_SEND_SUCCEEDED_EPOCH_BY_TOKEN: dict[int, float] = {}
_LATEST_SUBSCRIBE_SEQUENCE_BY_TOKEN: dict[int, int] = {}
_LATEST_MODE_COMMAND_SEQUENCE_BY_TOKEN: dict[int, int] = {}
_LATEST_MODE_COMMAND_BY_TOKEN: dict[int, dict[str, object]] = {}
_NIFTY_MODE_LIFECYCLE_SEQUENCE = 0
_NIFTY_MODE_LIFECYCLE_LOCK = threading.Lock()
_FIRST_LIVE_TICK_EPOCH_BY_TOKEN: dict[int, float] = {}
_FIRST_SOURCE_TICK_EPOCH_BY_TOKEN: dict[int, float] = {}
_FIRST_FULL_PAYLOAD_EPOCH_BY_TOKEN: dict[int, float] = {}
_LATEST_FULL_PAYLOAD_EPOCH_BY_TOKEN: dict[int, float] = {}
_LATEST_OBSERVATION_PACKET_BY_TOKEN: dict[int, dict[str, object]] = {}
_OBSERVATION_CALLBACK_COUNT_BY_TOKEN: dict[int, int] = {}
_POST_MODE_CALLBACK_COUNT_BY_TOKEN: dict[int, int] = {}
_POST_MODE_QUOTE_COUNT_BY_TOKEN: dict[int, int] = {}
_POST_MODE_FULL_COUNT_BY_TOKEN: dict[int, int] = {}
_FIRST_POST_MODE_CALLBACK_EPOCH_BY_TOKEN: dict[int, float] = {}
_FIRST_POST_MODE_QUOTE_EPOCH_BY_TOKEN: dict[int, float] = {}
_FIRST_POST_MODE_FULL_EPOCH_BY_TOKEN: dict[int, float] = {}
_SUBSCRIPTION_REQUESTED_EPOCH: float | None = None
_SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH: float | None = None
_MODE_REQUEST_SUCCEEDED_EPOCH: float | None = None
_FULL_PAYLOAD_OBSERVED_EPOCH: float | None = None
_FEED_SESSION_ID: str = ""
_FEED_RECONNECT_GENERATION = 0
_FEED_CONNECTION_START_EPOCH: float | None = None
_FEED_ON_TICKS_ROW_SEQ = 0
_RESTART_LOCK = threading.RLock()
_RESTART_ASYNC_LOCK = threading.Lock()
_RESTART_ASYNC_THREAD = None
_LAST_FULL_RESTART_EPOCH = 0.0
_FULL_RESTARTS = []
_STALE_STRIKES = 0
_WARMUP_PENDING = False
_LOG_PATH = logs_dir() / "depth_ws_watchdog.log"
_TICK_INGEST_ERROR_PATH = logs_dir() / "tick_ingest_errors.jsonl"
_TICK_INGEST_ERROR_WRITER = get_jsonl_writer(_TICK_INGEST_ERROR_PATH)
_TICK_INGEST_ERROR_LOCK = threading.Lock()
_LAST_TICK_INGEST_ERROR_TS = 0.0
_FEED_RUNTIME_SNAPSHOT_WRITE_COUNT = 0
_DEPTH_WS_LOCK: RunLock | None = None
_DEPTH_WS_LOCK_ACQUIRED = False
_STOP_REQUESTED = False
_SCHEMA_LOG_TS = 0.0
_INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "SENSEX"}
_AUTH_REQUIRED_LATCH = False
_OBSERVATION_PLAN_STATE_LOCK = threading.RLock()
_OBSERVATION_PLAN_STATE: dict[str, Any] = {
    "enabled": False,
    "verdict": "DISABLED",
    "production_tokens": [],
    "observation_tokens": [],
    "overlap_tokens": [],
    "observation_exclusive_tokens": [],
    "final_union_tokens": [],
    "missing_observation_tokens": [],
    "configured_budget": None,
    "feed_session_id": "",
    "reconnect_generation": 0,
    "plan_sha": "",
    "decision_epoch": None,
}


def _observation_state_payload() -> dict[str, Any]:
    with _OBSERVATION_PLAN_STATE_LOCK:
        return dict(_OBSERVATION_PLAN_STATE)


def _set_observation_plan_state(
    *,
    enabled: bool,
    verdict: str,
    production_tokens: Sequence[int] = (),
    observation_tokens: Sequence[int] = (),
    final_union_tokens: Sequence[int] = (),
    missing_observation_tokens: Sequence[int] = (),
    configured_budget: int | None = None,
    plan_sha: str = "",
) -> dict[str, Any]:
    production = sorted({int(token) for token in production_tokens if int(token) > 0})
    observation = sorted({int(token) for token in observation_tokens if int(token) > 0})
    final_union = sorted({int(token) for token in final_union_tokens if int(token) > 0})
    overlap = sorted(set(production) & set(observation))
    exclusive = sorted(set(observation) - set(production))
    with _OBSERVATION_PLAN_STATE_LOCK:
        _OBSERVATION_PLAN_STATE.update(
            {
                "enabled": bool(enabled),
                "verdict": str(verdict),
                "production_tokens": production,
                "observation_tokens": observation,
                "overlap_tokens": overlap,
                "observation_exclusive_tokens": exclusive,
                "final_union_tokens": final_union,
                "missing_observation_tokens": sorted({int(token) for token in missing_observation_tokens if int(token) > 0}),
                "configured_budget": configured_budget,
                "feed_session_id": _ensure_feed_session_id() if bool(enabled) else "",
                "reconnect_generation": int(_FEED_RECONNECT_GENERATION),
                "plan_sha": str(plan_sha or ""),
                "decision_epoch": float(now_utc_epoch()),
            }
        )
        return dict(_OBSERVATION_PLAN_STATE)


def reset_market_event_graph_observation_plan_state() -> None:
    _set_observation_plan_state(enabled=False, verdict="DISABLED")


def activate_market_event_graph_launch_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    verdict = str(plan.get("verdict") or "")
    ok = bool(plan.get("ok")) and verdict == "PASS_LIVE_SOURCE_PRESESSION_READINESS"
    return _set_observation_plan_state(
        enabled=ok,
        verdict=verdict if verdict else "BLOCKED_BY_LAUNCH_PLAN_IDENTITY",
        production_tokens=plan.get("production_tokens") or (),
        observation_tokens=plan.get("observation_tokens") or (),
        final_union_tokens=plan.get("final_union_tokens") or (),
        missing_observation_tokens=plan.get("missing_observation_tokens") or (),
        configured_budget=plan.get("configured_budget"),
        plan_sha=str(plan.get("launch_plan_sha256") or ""),
    )


def _ensure_feed_session_id() -> str:
    global _FEED_SESSION_ID
    if not _FEED_SESSION_ID:
        configured = str(os.getenv("LIVE_FEED_SESSION_ID", "") or "").strip()
        _FEED_SESSION_ID = configured or f"kite-depth-{int(now_utc_epoch())}"
    return _FEED_SESSION_ID


def _nifty_mode_lifecycle_path() -> Path | None:
    root = str(os.getenv(EVIDENCE_ROOT_ENV, "") or "").strip()
    if not root:
        return None
    return Path(root) / "live" / "nifty_mode_lifecycle.jsonl"


def _client_mode_for_token(ws: Any, token: int) -> object:
    try:
        subscribed_tokens = getattr(ws, "subscribed_tokens", None)
        if isinstance(subscribed_tokens, Mapping):
            return subscribed_tokens.get(int(token)) or subscribed_tokens.get(str(int(token)))
    except Exception:
        return None
    return None


def _record_ws_subscription_operation(
    ws: Any,
    tokens: Sequence[int],
    *,
    callsite: str,
    operation: str,
    requested_mode: str | None = None,
    local_call_result: str = "not_attempted",
    exception_type: str | None = None,
    reason: str = "",
    client_mode_before: object = None,
    client_mode_after: object = None,
    socket_generation: int | None = None,
) -> dict[str, object] | None:
    global _NIFTY_MODE_LIFECYCLE_SEQUENCE
    normalized = sorted({int(token) for token in (tokens or []) if int(token) > 0})
    contains_nifty = 256265 in normalized
    if not contains_nifty:
        return None
    with _NIFTY_MODE_LIFECYCLE_LOCK:
        _NIFTY_MODE_LIFECYCLE_SEQUENCE += 1
        sequence_number = int(_NIFTY_MODE_LIFECYCLE_SEQUENCE)
    receipt_epoch = float(now_utc_epoch())
    payload = {
        "sequence_number": sequence_number,
        "receipt_epoch": receipt_epoch,
        "callsite": str(callsite),
        "operation": str(operation),
        "socket_generation": int(socket_generation if socket_generation is not None else _SOCKET_GENERATION),
        "feed_session_id": _ensure_feed_session_id(),
        "reconnect_generation": int(_FEED_RECONNECT_GENERATION),
        "thread_name": threading.current_thread().name,
        "token_count": len(normalized),
        "contains_nifty": True,
        "requested_mode": requested_mode,
        "client_mode_before": client_mode_before,
        "client_mode_after": client_mode_after,
        "local_call_result": str(local_call_result),
        "exception_type": exception_type,
        "reason": str(reason or ""),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    path = _nifty_mode_lifecycle_path()
    if path is not None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str) + "\n")
        except Exception:
            pass
    return payload


def _record_subscription_requested(tokens: Sequence[int]) -> None:
    global _SUBSCRIPTION_REQUESTED_TOKENS, _SUBSCRIPTION_REQUESTED_EPOCH
    normalized = {int(token) for token in (tokens or []) if int(token) > 0}
    if normalized:
        epoch = float(now_utc_epoch())
        _SUBSCRIPTION_REQUESTED_TOKENS.update(normalized)
        for token in normalized:
            _SUBSCRIPTION_REQUESTED_EPOCH_BY_TOKEN[token] = epoch
        _SUBSCRIPTION_REQUESTED_EPOCH = epoch


def _record_subscription_request_succeeded(tokens: Sequence[int]) -> None:
    global _SUBSCRIPTION_REQUEST_SUCCEEDED_TOKENS, _SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH
    normalized = {int(token) for token in (tokens or []) if int(token) > 0}
    if normalized:
        epoch = float(now_utc_epoch())
        _SUBSCRIPTION_REQUEST_SUCCEEDED_TOKENS.update(normalized)
        for token in normalized:
            _SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN[token] = epoch
            _LATEST_SUBSCRIBE_SEQUENCE_BY_TOKEN[token] = int(_NIFTY_MODE_LIFECYCLE_SEQUENCE)
            if token in _MODE_COMMAND_FINAL_FULL_TOKENS:
                _MODE_COMMAND_FINAL_FULL_TOKENS.discard(token)
        _SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH = epoch


def _record_mode_request_succeeded(tokens: Sequence[int]) -> None:
    global _MODE_REQUEST_SUCCEEDED_TOKENS, _MODE_REQUEST_SUCCEEDED_EPOCH
    normalized = {int(token) for token in (tokens or []) if int(token) > 0}
    if normalized:
        epoch = float(now_utc_epoch())
        _MODE_REQUEST_SUCCEEDED_TOKENS.update(normalized)
        _MODE_COMMAND_LOCAL_SEND_SUCCEEDED_TOKENS.update(normalized)
        for token in normalized:
            _MODE_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN[token] = epoch
            _MODE_COMMAND_LOCAL_SEND_SUCCEEDED_EPOCH_BY_TOKEN[token] = epoch
            mode_seq = int(_NIFTY_MODE_LIFECYCLE_SEQUENCE)
            _LATEST_MODE_COMMAND_SEQUENCE_BY_TOKEN[token] = mode_seq
            _MODE_COMMAND_FINAL_FULL_TOKENS.add(token)
            _LATEST_MODE_COMMAND_BY_TOKEN[token] = {
                "operation": "set_mode",
                "requested_mode": "full",
                "sequence_number": mode_seq,
                "receipt_epoch": epoch,
                "socket_generation": int(_SOCKET_GENERATION),
                "feed_session_id": _ensure_feed_session_id(),
                "reconnect_generation": int(_FEED_RECONNECT_GENERATION),
                "local_call_result": "succeeded",
                "broker_delivery_proven": False,
            }
        _MODE_REQUEST_SUCCEEDED_EPOCH = epoch


def _record_full_payload_observed(token: int) -> None:
    global _FULL_PAYLOAD_OBSERVED_TOKENS, _FULL_PAYLOAD_OBSERVED_EPOCH
    if int(token) > 0:
        token_int = int(token)
        epoch = float(now_utc_epoch())
        _FULL_PAYLOAD_OBSERVED_TOKENS.add(int(token))
        _FIRST_FULL_PAYLOAD_EPOCH_BY_TOKEN.setdefault(token_int, epoch)
        _LATEST_FULL_PAYLOAD_EPOCH_BY_TOKEN[token_int] = epoch
        _FULL_PAYLOAD_OBSERVED_EPOCH = epoch


def _observation_packet_detail(
    tick: dict,
    *,
    instrument_token: int,
    instrument_class: str,
    receipt_epoch: float,
    source_tick_epoch: float | None,
    mode_success_epoch: float | None,
    feed_session_id: str,
    reconnect_generation: int,
    has_depth: bool,
) -> dict[str, object]:
    parsed_mode = str(tick.get("mode") or "").strip().lower()
    has_exchange_timestamp = tick.get("exchange_timestamp") is not None
    has_ohlc = isinstance(tick.get("ohlc"), dict)
    has_change = tick.get("change") is not None
    detail = {
        "instrument_class": str(instrument_class or "UNKNOWN"),
        "instrument_token": int(instrument_token),
        "parsed_mode": parsed_mode or None,
        "has_ohlc": has_ohlc,
        "has_change": has_change,
        "has_exchange_timestamp": has_exchange_timestamp,
        "has_depth": bool(has_depth),
        "tradable": tick.get("tradable"),
        "callback_receipt_epoch": float(receipt_epoch),
        "source_tick_epoch": source_tick_epoch,
        "mode_request_succeeded_epoch": mode_success_epoch,
        "feed_session_id": str(feed_session_id or ""),
        "reconnect_generation": int(reconnect_generation),
    }
    if mode_success_epoch is None:
        detail["structured_reason"] = "MODE_REQUEST_FAILED"
    elif float(receipt_epoch) <= float(mode_success_epoch):
        detail["structured_reason"] = "POST_MODE_CALLBACK_NOT_OBSERVED"
    elif str(instrument_class or "").upper() == "INDEX":
        if parsed_mode == "full" or (not parsed_mode and has_exchange_timestamp):
            detail["structured_reason"] = "OK"
        elif parsed_mode:
            detail["structured_reason"] = "INDEX_FULL_PACKET_NOT_OBSERVED"
        else:
            detail["structured_reason"] = "INDEX_PACKET_MODE_UNPROVEN"
    elif parsed_mode == "full" or has_depth:
        detail["structured_reason"] = "OK"
    else:
        detail["structured_reason"] = "EQUITY_FULL_DEPTH_NOT_OBSERVED"
    return detail


def _observation_packet_full_status(
    tick: dict,
    *,
    instrument_token: int,
    instrument_class: str,
    receipt_epoch: float,
    source_tick_epoch: float | None,
    mode_success_epoch: float | None,
    feed_session_id: str,
    reconnect_generation: int,
    has_depth: bool,
) -> tuple[str, bool, dict[str, object]]:
    detail = _observation_packet_detail(
        tick,
        instrument_token=instrument_token,
        instrument_class=instrument_class,
        receipt_epoch=receipt_epoch,
        source_tick_epoch=source_tick_epoch,
        mode_success_epoch=mode_success_epoch,
        feed_session_id=feed_session_id,
        reconnect_generation=reconnect_generation,
        has_depth=has_depth,
    )
    is_index = str(instrument_class or "").upper() == "INDEX"
    is_full = detail["structured_reason"] == "OK"
    if is_index:
        packet_kind = "INDEX_FULL" if is_full else "INDEX_QUOTE"
    else:
        packet_kind = "NSE_EQUITY_FULL" if is_full else "NSE_EQUITY_QUOTE"
    return packet_kind, bool(is_full), detail


def _reset_market_event_graph_generation_evidence() -> None:
    global _SUBSCRIPTION_REQUESTED_TOKENS, _SUBSCRIPTION_REQUEST_SUCCEEDED_TOKENS, _MODE_REQUEST_SUCCEEDED_TOKENS, _FULL_PAYLOAD_OBSERVED_TOKENS
    global _SUBSCRIPTION_REQUESTED_EPOCH, _SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH, _MODE_REQUEST_SUCCEEDED_EPOCH, _FULL_PAYLOAD_OBSERVED_EPOCH
    _SUBSCRIPTION_REQUESTED_TOKENS = set()
    _SUBSCRIPTION_REQUEST_SUCCEEDED_TOKENS = set()
    _MODE_REQUEST_SUCCEEDED_TOKENS = set()
    _FULL_PAYLOAD_OBSERVED_TOKENS = set()
    _SUBSCRIPTION_REQUESTED_EPOCH_BY_TOKEN.clear()
    _SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN.clear()
    _MODE_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN.clear()
    _FIRST_LIVE_TICK_EPOCH_BY_TOKEN.clear()
    _FIRST_SOURCE_TICK_EPOCH_BY_TOKEN.clear()
    _FIRST_FULL_PAYLOAD_EPOCH_BY_TOKEN.clear()
    _LATEST_FULL_PAYLOAD_EPOCH_BY_TOKEN.clear()
    _LATEST_OBSERVATION_PACKET_BY_TOKEN.clear()
    _OBSERVATION_CALLBACK_COUNT_BY_TOKEN.clear()
    _SUBSCRIPTION_REQUESTED_EPOCH = None
    _SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH = None
    _MODE_REQUEST_SUCCEEDED_EPOCH = None
    _FULL_PAYLOAD_OBSERVED_EPOCH = None
    with _OBSERVATION_PLAN_STATE_LOCK:
        if _OBSERVATION_PLAN_STATE.get("enabled"):
            _OBSERVATION_PLAN_STATE["feed_session_id"] = _ensure_feed_session_id()
            _OBSERVATION_PLAN_STATE["reconnect_generation"] = int(_FEED_RECONNECT_GENERATION)


def get_current_feed_session_identity() -> dict[str, Any]:
    return {
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "feed_session_id": _ensure_feed_session_id(),
        "reconnect_generation": int(_FEED_RECONNECT_GENERATION),
        "connection_start_epoch": _FEED_CONNECTION_START_EPOCH,
    }


def market_event_graph_subscription_evidence_for_tokens(token_by_symbol: Mapping[str, int]) -> dict[str, Any]:
    expected = {str(symbol).upper(): int(token) for symbol, token in (token_by_symbol or {}).items() if token is not None}
    requested = {symbol for symbol, token in expected.items() if int(token) in _SUBSCRIPTION_REQUESTED_TOKENS}
    request_succeeded = {symbol for symbol, token in expected.items() if int(token) in _SUBSCRIPTION_REQUEST_SUCCEEDED_TOKENS}
    mode_requested = {symbol for symbol, token in expected.items() if int(token) in _MODE_REQUEST_SUCCEEDED_TOKENS}
    full_payload = {symbol for symbol, token in expected.items() if int(token) in _FULL_PAYLOAD_OBSERVED_TOKENS}
    live_tick = {symbol for symbol, token in expected.items() if _coerce_epoch(_LAST_MSG_TS_BY_TOKEN.get(int(token))) is not None}
    ordered = list(expected.keys())
    latest_live_tick_by_symbol = {
        symbol: _coerce_epoch(_LAST_MSG_TS_BY_TOKEN.get(int(token)))
        for symbol, token in expected.items()
        if _coerce_epoch(_LAST_MSG_TS_BY_TOKEN.get(int(token))) is not None
    }
    identity = get_current_feed_session_identity()
    lifecycle: dict[str, dict[str, Any]] = {}
    for symbol, token in expected.items():
        token_int = int(token)
        lifecycle[str(token_int)] = {
            "symbol": symbol,
            "instrument_token": token_int,
            "subscription_requested_epoch": _SUBSCRIPTION_REQUESTED_EPOCH_BY_TOKEN.get(token_int),
            "subscribe_call_succeeded_epoch": _SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN.get(token_int),
            "mode_command_dispatched_epoch": _MODE_COMMAND_LOCAL_SEND_SUCCEEDED_EPOCH_BY_TOKEN.get(token_int),
            "mode_command_local_send_succeeded_epoch": _MODE_COMMAND_LOCAL_SEND_SUCCEEDED_EPOCH_BY_TOKEN.get(token_int),
            "mode_delivery_observed_epoch": _FIRST_FULL_PAYLOAD_EPOCH_BY_TOKEN.get(token_int),
            "latest_subscribe_sequence_number": _LATEST_SUBSCRIBE_SEQUENCE_BY_TOKEN.get(token_int),
            "latest_mode_command_sequence_number": _LATEST_MODE_COMMAND_SEQUENCE_BY_TOKEN.get(token_int),
            "final_current_generation_local_mode": (
                "full" if token_int in _MODE_COMMAND_FINAL_FULL_TOKENS else None
            ),
            "final_current_generation_local_mode_is_full": token_int in _MODE_COMMAND_FINAL_FULL_TOKENS,
            "latest_mode_command": dict(_LATEST_MODE_COMMAND_BY_TOKEN.get(token_int) or {}),
            "post_mode_callback_count": int(_POST_MODE_CALLBACK_COUNT_BY_TOKEN.get(token_int) or 0),
            "registered_observation_callback_count": int(_OBSERVATION_CALLBACK_COUNT_BY_TOKEN.get(token_int) or 0),
            "post_mode_quote_count": int(_POST_MODE_QUOTE_COUNT_BY_TOKEN.get(token_int) or 0),
            "post_mode_full_count": int(_POST_MODE_FULL_COUNT_BY_TOKEN.get(token_int) or 0),
            "first_post_mode_callback_epoch": _FIRST_POST_MODE_CALLBACK_EPOCH_BY_TOKEN.get(token_int),
            "first_post_mode_quote_epoch": _FIRST_POST_MODE_QUOTE_EPOCH_BY_TOKEN.get(token_int),
            "first_post_mode_full_epoch": _FIRST_POST_MODE_FULL_EPOCH_BY_TOKEN.get(token_int),
            "mode_request_succeeded_epoch": _MODE_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN.get(token_int),
            "first_callback_receipt_epoch": _FIRST_LIVE_TICK_EPOCH_BY_TOKEN.get(token_int),
            "latest_callback_receipt_epoch": _coerce_epoch(_LAST_MSG_TS_BY_TOKEN.get(token_int)),
            "first_source_tick_epoch": _FIRST_SOURCE_TICK_EPOCH_BY_TOKEN.get(token_int),
            "latest_source_tick_epoch": _coerce_epoch(_LAST_PAYLOAD_TS_BY_TOKEN.get(token_int)),
            "first_post_mode_full_receipt_epoch": _FIRST_FULL_PAYLOAD_EPOCH_BY_TOKEN.get(token_int),
            "latest_post_mode_full_receipt_epoch": _LATEST_FULL_PAYLOAD_EPOCH_BY_TOKEN.get(token_int),
            # Compatibility aliases. These are receipt-time fields, not broker-source timestamps.
            "first_live_tick_epoch": _FIRST_LIVE_TICK_EPOCH_BY_TOKEN.get(token_int),
            "latest_live_tick_epoch": _coerce_epoch(_LAST_MSG_TS_BY_TOKEN.get(token_int)),
            "first_full_payload_epoch": _FIRST_FULL_PAYLOAD_EPOCH_BY_TOKEN.get(token_int),
            "latest_full_payload_epoch": _LATEST_FULL_PAYLOAD_EPOCH_BY_TOKEN.get(token_int),
            "latest_observation_packet": dict(_LATEST_OBSERVATION_PACKET_BY_TOKEN.get(token_int) or {}),
            "feed_session_id": identity["feed_session_id"],
            "reconnect_generation": identity["reconnect_generation"],
        }
    generation_basis = {
        "provider": identity["provider"],
        "token_domain": identity["token_domain"],
        "feed_session_id": identity["feed_session_id"],
        "reconnect_generation": identity["reconnect_generation"],
        "tokens": sorted(int(token) for token in expected.values()),
        "request_epochs": {
            str(token): lifecycle[str(token)].get("subscription_requested_epoch")
            for token in sorted(int(token) for token in expected.values())
        },
    }
    snapshot_basis = {
        **generation_basis,
        "token_lifecycle": lifecycle,
    }
    payload = {
        "provider": identity["provider"],
        "token_domain": identity["token_domain"],
        "feed_session_id": identity["feed_session_id"],
        "reconnect_generation": int(identity["reconnect_generation"]),
        "connection_start_epoch": identity["connection_start_epoch"],
        "token_by_symbol": dict(expected),
        "token_resolved_symbols": ordered,
        "subscription_requested_symbols": [symbol for symbol in ordered if symbol in requested],
        "subscription_request_succeeded_symbols": [symbol for symbol in ordered if symbol in request_succeeded],
        "mode_command_dispatched_symbols": [symbol for symbol in ordered if int(expected[symbol]) in _MODE_COMMAND_LOCAL_SEND_SUCCEEDED_TOKENS],
        "mode_command_local_send_succeeded_symbols": [symbol for symbol in ordered if int(expected[symbol]) in _MODE_COMMAND_LOCAL_SEND_SUCCEEDED_TOKENS],
        "mode_delivery_observed_symbols": [symbol for symbol in ordered if symbol in full_payload],
        "final_current_generation_full_mode_symbols": [symbol for symbol in ordered if int(expected[symbol]) in _MODE_COMMAND_FINAL_FULL_TOKENS],
        "mode_request_succeeded_symbols": [symbol for symbol in ordered if symbol in mode_requested],
        "live_tick_observed_symbols": [symbol for symbol in ordered if symbol in live_tick],
        "full_payload_observed_symbols": [symbol for symbol in ordered if symbol in full_payload],
        "completed_bar_available_symbols": [],
        "latest_live_tick_epoch_by_symbol": latest_live_tick_by_symbol,
        "subscription_requested_epoch": _SUBSCRIPTION_REQUESTED_EPOCH,
        "subscription_request_succeeded_epoch": _SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH,
        "mode_request_succeeded_epoch": _MODE_REQUEST_SUCCEEDED_EPOCH,
        "full_payload_observed_epoch": _FULL_PAYLOAD_OBSERVED_EPOCH,
        "token_lifecycle": lifecycle,
        "budget_status": {
            "requested_count": len(expected),
            "request_succeeded_count": len(request_succeeded),
            "mode_request_succeeded_count": len(mode_requested),
            "live_tick_count": len(live_tick),
            "full_payload_count": len(full_payload),
        },
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    observation_state = _observation_state_payload()
    payload["observation_plan_state"] = observation_state
    if observation_state.get("verdict") == BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET:
        payload["observation_blocker"] = {
            "verdict": BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET,
            "missing_observation_tokens": list(observation_state.get("missing_observation_tokens") or []),
            "generation_inactive": True,
        }
    payload["subscription_generation_id"] = hashlib.sha256(
        json.dumps(generation_basis, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    payload["evidence_snapshot_sha256"] = hashlib.sha256(
        json.dumps(snapshot_basis, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    payload["subscription_evidence_id"] = payload["subscription_generation_id"]
    return payload

_AUTH_REQUIRED_LOGGED = False
_LAST_FEED_TICK_LOG_MINUTE: int | None = None
_LAST_FEED_HEALTH_STATE: str | None = None
_RUNTIME_STATE: str = "STOPPED"
_LAST_RUNTIME_ERROR: str = ""
_INTENDED_TOKEN_COUNT: int = 0
_LAST_OPTION_TOKEN_INCIDENT_TS: dict[str, float] = {}
_LAST_ATM_BY_SYMBOL: dict[str, int] = {}
_LAST_OPTION_COUNTS_BY_SYMBOL: dict[str, int] = {}
_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL: dict[str, int] = {}
_STALE_OPTION_MUTATION_WINDOW_STATE: dict[str, dict[str, object]] = {}
_DEPTH_WS_START_EPOCH: float = 0.0
_RECONNECT_BLOCKED_REASON: str = ""
_RECONNECT_BLOCKED_SINCE_EPOCH: float = 0.0
_PARTIAL_RECOVERY_VERIFICATION: dict[str, object] = {}
_LAST_DISCONNECTED_CODE: int | None = None
_LAST_DISCONNECTED_REASON: str = ""
_LAST_INTERNAL_RETRY_SUPPRESSION_STATE: dict[str, object] = {}
_REACTOR_NOT_RESTARTABLE_DETECTED: bool = False
_RECOVERY_IN_PROGRESS: bool = False
_WS1006_RECOVERABLE_ATTEMPTS: int = 0
_WS1006_RECOVERABLE_LAST_ATTEMPT_EPOCH: float = 0.0
_WS1006_RECOVERABLE_LAST_REASON: str = ""
_FEED_RECOVERY_COORDINATOR = get_feed_recovery_coordinator()

_TOKEN_RECOVERY_MAX_ATTEMPTS = int(getattr(cfg, "TOKEN_RECOVERY_MAX_ATTEMPTS", 3) or 3)
_TOKEN_RECOVERY_COOLDOWN_SEC = float(getattr(cfg, "TOKEN_RECOVERY_COOLDOWN_SEC", 10.0) or 10.0)
_TOKEN_RECOVERY_VERIFY_TIMEOUT_SEC = float(getattr(cfg, "TOKEN_RECOVERY_VERIFY_TIMEOUT_SEC", 15.0) or 15.0)
_RECOVERY_STABLE_CYCLES = max(1, int(getattr(cfg, "RECOVERY_STABLE_CYCLES", 3) or 3))
_CORE_FEED_FRESH_QUORUM = float(getattr(cfg, "CORE_FEED_FRESH_QUORUM", 0.95) or 0.95)

# LIVE-TRUTH-23: Verified post-start feed recovery gate.
# Prevents treating a full restart as recovered unless connect + subscribe + fresh option ticks are observed.
_RESTART_VERIFY_LOCK = threading.Lock()
_FEED_RESTART_VERIFY_STATE: str = "IDLE"  # IDLE | PENDING | OK | FAILED
_FEED_RESTART_VERIFY_REASON: str = ""
_FEED_RESTART_VERIFY_START_EPOCH: float = 0.0
_FEED_RESTART_VERIFY_DEADLINE_EPOCH: float = 0.0
_FEED_RESTART_VERIFY_CONNECT_EPOCH: float | None = None
_FEED_RESTART_VERIFY_SUBSCRIBE_EPOCH: float | None = None
_FEED_RESTART_VERIFY_VERIFIED_EPOCH: float | None = None
_FEED_RESTART_VERIFY_FAILURE_DETAIL: str = ""
_FEED_RESTART_VERIFY_LAST_STAGE_EVENT: str = ""
_FEED_HEALTH_DURATION_STATE: dict[str, object] | None = None

_OPTION_FEED_VERIFY_STATE: str = "IDLE"  # IDLE | PENDING | OK | FAILED
_OPTION_FEED_VERIFY_REASON: str = ""
_OPTION_FEED_VERIFY_START_EPOCH: float = 0.0
_OPTION_FEED_VERIFY_DEADLINE_EPOCH: float = 0.0
_OPTION_FEED_VERIFY_REQUIRED_SYMBOLS: list[str] = []
_OPTION_FEED_VERIFY_REQUESTED_BY_SYMBOL: dict[str, int] = {}
_OPTION_FEED_VERIFY_SUBSCRIBED_BY_SYMBOL: dict[str, int] = {}
_OPTION_FEED_VERIFY_VERIFIED_SYMBOLS: list[str] = []
_OPTION_FEED_VERIFY_MISSING_SYMBOLS: list[str] = []
_OPTION_FEED_VERIFY_VERIFIED_EPOCH: float | None = None
_OPTION_FEED_VERIFY_FAILURE_DETAIL: str = ""
_OPTION_FEED_VERIFY_LAST_STAGE_EVENT: str = ""

_RESTART_VERIFY_OPTION_OK_CODES = {"", "OK", "NONE", "HEALTHY", "FRESH"}
logger = logging.getLogger(__name__)
_WS_LOGGER = get_rotating_logger("depth_ws_watchdog", _LOG_PATH)
_WS_LOG_THROTTLE_SEC = 5.0
_WS_LOG_THROTTLE_LOCK = threading.Lock()
_WS_LOG_LAST_EMIT: dict[str, float] = {}


def _use_native_reconnect() -> bool:
    if hasattr(cfg, "DEPTH_WS_USE_NATIVE_RECONNECT"):
        return bool(cfg.DEPTH_WS_USE_NATIVE_RECONNECT)
    # Fallback to old name for backward compatibility
    return bool(getattr(cfg, "DEPTH_WS_USE_INTERNAL_RECONNECT", True))


def _maybe_reset_restart_guard_on_market_open(
    *,
    market_open_now: bool,
    market_was_open: bool | None,
) -> bool:
    if bool(market_open_now) and (market_was_open is False or market_was_open is None):
        try:
            feed_restart_guard.reset(reason="market_open_transition")
        except Exception:
            pass
    return bool(market_open_now)


def _is_underlying_token(token: int | None) -> bool:
    if token is None:
        return False
    return (int(token) in _UNDERLYING_TOKENS) or (int(token) in _UNDERLYING_TOKEN_TO_SYMBOL)


def _normalize_positive_tokens(token_source) -> list[int]:
    out: set[int] = set()
    for tok in list(token_source or []):
        try:
            tok_int = int(tok)
        except Exception:
            continue
        if tok_int > 0:
            out.add(tok_int)
    return sorted(out)


def _use_desired_tokens_for_resubscribe() -> bool:
    return str(os.getenv("FEED_USE_DESIRED_TOKENS", "") or "").strip() == "1"


def _stale_option_subscription_prune_enabled() -> bool:
    return bool(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE", True))


def _stale_option_subscription_max_age_sec() -> float:
    try:
        return float(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", 12.0))
    except Exception:
        return 12.0


def _stale_option_subscription_consecutive_windows_required() -> int:
    try:
        n = int(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_CONSECUTIVE_STALE_WINDOWS", 3) or 3)
    except Exception:
        n = 3
    # Defensive clamp to keep behavior conservative and predictable.
    return max(1, min(10, n))


def _latest_feed_runtime_truth_snapshot() -> dict[str, object]:
    candidates = (
        logs_dir() / "feed_runtime_latest.json",
        repo_root() / "logs" / "feed_runtime_latest.json",
        repo_root() / ".runtime" / "feed_runtime_latest.json",
    )
    for path in candidates:
        try:
            if not path.exists() or not path.is_file():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _prune_stale_option_subscription_tokens(
    *,
    tokens: list[int],
    option_rank_by_token: dict[int, tuple[float, int, float, int, int]],
    token_to_symbol: dict[int, str],
    min_required_by_symbol: dict[str, int] | None = None,
) -> tuple[list[int], dict[str, object]]:
    global _DEPTH_WS_START_EPOCH
    if not _stale_option_subscription_prune_enabled():
        return list(tokens), {
            "enabled": False,
            "max_age_sec": _stale_option_subscription_max_age_sec(),
            "grace_sec": float(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_GRACE_SEC", 60.0)),
            "min_required_by_symbol": dict(min_required_by_symbol or {}),
            "min_required_blocked_by_symbol": {},
            "protected_stale_by_symbol": {},
            "pruned_count": 0,
            "kept_count": len(tokens),
            "pruned_tokens": [],
            "pruned_by_symbol": {},
            "consecutive_stale_windows_required": _stale_option_subscription_consecutive_windows_required(),
        }

    grace_sec = float(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_GRACE_SEC", 60.0))
    now_epoch = float(now_utc_epoch())
    start_epoch = float(_DEPTH_WS_START_EPOCH or 0.0)
    if start_epoch <= 0.0:
        _DEPTH_WS_START_EPOCH = now_epoch
        start_epoch = now_epoch
    if (now_epoch - start_epoch) < grace_sec:
        return list(tokens), {
            "enabled": True,
            "max_age_sec": _stale_option_subscription_max_age_sec(),
            "grace_sec": grace_sec,
            "min_required_by_symbol": dict(min_required_by_symbol or {}),
            "min_required_blocked_by_symbol": {},
            "protected_stale_by_symbol": {},
            "pruned_count": 0,
            "kept_count": len(tokens),
            "pruned_tokens": [],
            "pruned_by_symbol": {},
            "consecutive_stale_windows_required": _stale_option_subscription_consecutive_windows_required(),
        }

    option_tokens = [
        int(tok)
        for tok in list(tokens or [])
        if int(tok) > 0 and int(tok) in option_rank_by_token and not _is_underlying_token(int(tok))
    ]
    if not option_tokens:
        return list(tokens), {
            "enabled": True,
            "max_age_sec": _stale_option_subscription_max_age_sec(),
            "grace_sec": grace_sec,
            "require_session_tick": bool(
                getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_REQUIRE_SESSION_TICK", True)
            ),
            "min_required_by_symbol": dict(min_required_by_symbol or {}),
            "min_required_blocked_by_symbol": {},
            "protected_stale_by_symbol": {},
            "pruned_count": 0,
            "kept_count": len(tokens),
            "pruned_tokens": [],
            "pruned_by_symbol": {},
            "session_tick_skipped_by_symbol": {},
            "consecutive_stale_windows_required": _stale_option_subscription_consecutive_windows_required(),
        }

    max_age_sec = _stale_option_subscription_max_age_sec()
    stale_windows_required = _stale_option_subscription_consecutive_windows_required()
    require_session_tick = bool(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_REQUIRE_SESSION_TICK", True))
    db_rows = get_latest_tick_rows_db(option_tokens)
    pruned_tokens: list[int] = []
    kept_option_tokens: list[int] = []
    pruned_by_symbol: dict[str, int] = {}
    session_tick_skipped_by_symbol: dict[str, int] = {}
    min_required_blocked_by_symbol: dict[str, int] = {}
    protected_stale_by_symbol: dict[str, int] = {}
    stale_samples: list[dict[str, object]] = []
    symbol_rows: dict[str, list[dict[str, object]]] = {}

    # Track strikes only for the currently considered universe to avoid unbounded growth.
    option_token_set = set(int(t) for t in option_tokens)
    for old_tok in list(_STALE_PRUNE_STRIKES_BY_TOKEN.keys()):
        if int(old_tok) not in option_token_set:
            _STALE_PRUNE_STRIKES_BY_TOKEN.pop(int(old_tok), None)

    for token in option_tokens:
        symbol = str(token_to_symbol.get(int(token)) or "").upper() or "UNKNOWN"
        if require_session_tick:
            session_tick_epoch = _coerce_epoch(_SYMBOL_LAST_OPTION_TICK_TS.get(symbol))
            if session_tick_epoch is None or session_tick_epoch < float(start_epoch):
                kept_option_tokens.append(int(token))
                session_tick_skipped_by_symbol[symbol] = int(session_tick_skipped_by_symbol.get(symbol, 0)) + 1
                if len(stale_samples) < 10:
                    stale_samples.append(
                        {
                            "token": int(token),
                            "symbol": symbol,
                            "age_sec": None,
                            "db_epoch": None,
                            "memory_epoch": None,
                            "session_tick_epoch": session_tick_epoch,
                            "session_tick_required": True,
                        "session_tick_skipped": True,
                    }
                )
                continue
        db_row = db_rows.get(int(token)) or {}
        db_epoch = _coerce_epoch(db_row.get("ts_epoch"))
        memory_epoch = _coerce_epoch(_LAST_MSG_TS_BY_TOKEN.get(int(token)))
        effective_epoch = None
        if db_epoch is not None and memory_epoch is not None:
            effective_epoch = max(float(db_epoch), float(memory_epoch))
        elif db_epoch is not None:
            effective_epoch = float(db_epoch)
        elif memory_epoch is not None:
            effective_epoch = float(memory_epoch)
        age_sec = None if effective_epoch is None else max(0.0, float(now_epoch) - float(effective_epoch))
        is_stale = bool(age_sec is None or age_sec > max_age_sec)
        if is_stale:
            _STALE_PRUNE_STRIKES_BY_TOKEN[int(token)] = int(_STALE_PRUNE_STRIKES_BY_TOKEN.get(int(token), 0) or 0) + 1
        else:
            _STALE_PRUNE_STRIKES_BY_TOKEN[int(token)] = 0
        symbol_rows.setdefault(symbol, []).append(
            {
                "token": int(token),
                "age_sec": age_sec,
                "db_epoch": db_epoch,
                "memory_epoch": memory_epoch,
                "stale": is_stale,
                "stale_windows": int(_STALE_PRUNE_STRIKES_BY_TOKEN.get(int(token), 0) or 0),
                "rank": option_rank_by_token.get(int(token)),
            }
        )

    for symbol, rows in list(symbol_rows.items()):
        min_required = max(0, int((min_required_by_symbol or {}).get(symbol, 0) or 0))
        fresh_rows = [row for row in rows if not bool(row.get("stale"))]
        stale_rows = [row for row in rows if bool(row.get("stale"))]
        # Hysteresis: do not prune a stale token until it has been stale for N consecutive evaluations.
        keep_rows = list(fresh_rows) + [
            row for row in stale_rows if int(row.get("stale_windows") or 0) < int(stale_windows_required)
        ]
        candidate_prune_rows = [
            row for row in stale_rows if int(row.get("stale_windows") or 0) >= int(stale_windows_required)
        ]
        if len(keep_rows) < min_required:
            candidate_prune_rows.sort(
                key=lambda row: (
                    float(row.get("age_sec") if row.get("age_sec") is not None else float("inf")),
                    tuple(row.get("rank") or (float("inf"), 1, float("inf"), 2, int(row.get("token") or 0))),
                )
            )
            extra_needed = min_required - len(keep_rows)
            keep_rows.extend(candidate_prune_rows[:extra_needed])
            if extra_needed > 0:
                protected_stale_by_symbol[symbol] = int(min(extra_needed, len(candidate_prune_rows)))
            if len(keep_rows) < min_required:
                min_required_blocked_by_symbol[symbol] = int(min_required - len(keep_rows))
        prune_rows = [row for row in candidate_prune_rows if row not in keep_rows]
        for row in prune_rows:
            token = int(row.get("token") or 0)
            pruned_tokens.append(token)
            pruned_by_symbol[symbol] = int(pruned_by_symbol.get(symbol, 0)) + 1
            if len(stale_samples) < 10:
                stale_samples.append(
                    {
                        "token": token,
                        "symbol": symbol,
                        "age_sec": row.get("age_sec"),
                        "db_epoch": row.get("db_epoch"),
                        "memory_epoch": row.get("memory_epoch"),
                    }
                )
        for row in keep_rows:
            kept_option_tokens.append(int(row.get("token") or 0))

    if not pruned_tokens:
        return list(tokens), {
            "enabled": True,
            "max_age_sec": max_age_sec,
            "grace_sec": grace_sec,
            "require_session_tick": require_session_tick,
            "min_required_by_symbol": dict(min_required_by_symbol or {}),
            "min_required_blocked_by_symbol": {},
            "protected_stale_by_symbol": {},
            "pruned_count": 0,
            "kept_count": len(tokens),
            "pruned_tokens": [],
            "pruned_by_symbol": {},
            "session_tick_skipped_by_symbol": session_tick_skipped_by_symbol,
            "consecutive_stale_windows_required": stale_windows_required,
        }

    pruned_set = set(pruned_tokens)
    pruned_tokens_out = [int(tok) for tok in tokens if int(tok) in pruned_set]
    retained_tokens = [int(tok) for tok in tokens if int(tok) not in pruned_set]
    # Preserve order and avoid duplicates; underlyings and sticky tokens are never pruned here.
    retained_tokens = list(dict.fromkeys(retained_tokens + kept_option_tokens))
    return retained_tokens, {
        "enabled": True,
        "max_age_sec": max_age_sec,
        "grace_sec": grace_sec,
        "require_session_tick": require_session_tick,
        "min_required_by_symbol": dict(min_required_by_symbol or {}),
        "min_required_blocked_by_symbol": min_required_blocked_by_symbol,
        "protected_stale_by_symbol": protected_stale_by_symbol,
        "pruned_count": len(pruned_tokens_out),
        "kept_count": len(retained_tokens),
        "pruned_tokens": pruned_tokens_out,
        "pruned_by_symbol": pruned_by_symbol,
        "session_tick_skipped_by_symbol": session_tick_skipped_by_symbol,
        "stale_samples": stale_samples,
        "consecutive_stale_windows_required": stale_windows_required,
    }


def _option_subscription_freshness_stats(
    *,
    now_epoch: float,
    tokens: list[int],
) -> dict[str, object]:
    option_tokens = [
        int(tok)
        for tok in list(tokens or [])
        if int(tok) > 0 and not _is_underlying_token(int(tok))
    ]
    urgent_max_age_sec = float(getattr(cfg, "FEED_STALE_OPTION_SUBSCRIPTION_URGENT_MAX_AGE_SEC", 8.0))
    if not option_tokens:
        return {
            "option_count": 0,
            "fresh_count": 0,
            "stale_count": 0,
            "fresh_ratio": 1.0,
            "max_age_sec": 0.0,
            "urgent_max_age_sec": urgent_max_age_sec,
            "stale_samples": [],
        }

    fresh_count = 0
    stale_count = 0
    max_age_sec = 0.0
    stale_samples: list[dict[str, object]] = []
    db_rows = get_latest_tick_rows_db(option_tokens)
    for token in option_tokens:
        db_row = db_rows.get(int(token)) or {}
        db_epoch = _coerce_epoch(db_row.get("ts_epoch"))
        memory_epoch = _coerce_epoch(_LAST_MSG_TS_BY_TOKEN.get(int(token)))
        effective_epoch = None
        if db_epoch is not None and memory_epoch is not None:
            effective_epoch = max(float(db_epoch), float(memory_epoch))
        elif db_epoch is not None:
            effective_epoch = float(db_epoch)
        elif memory_epoch is not None:
            effective_epoch = float(memory_epoch)
        age_sec = None if effective_epoch is None else max(0.0, float(now_epoch) - float(effective_epoch))
        if age_sec is None or age_sec > urgent_max_age_sec:
            stale_count += 1
            if len(stale_samples) < 10:
                stale_samples.append(
                    {
                        "token": int(token),
                        "symbol": str(_TOKEN_TO_SYMBOL.get(int(token)) or "").upper() or "UNKNOWN",
                        "age_sec": age_sec,
                        "db_epoch": db_epoch,
                        "memory_epoch": memory_epoch,
                    }
                )
        else:
            fresh_count += 1
        if age_sec is not None and float(age_sec) > float(max_age_sec):
            max_age_sec = float(age_sec)
    option_count = int(len(option_tokens))
    fresh_ratio = float(fresh_count / option_count) if option_count > 0 else 1.0
    return {
        "option_count": option_count,
        "fresh_count": int(fresh_count),
        "stale_count": int(stale_count),
        "fresh_ratio": fresh_ratio,
        "max_age_sec": max_age_sec,
        "urgent_max_age_sec": urgent_max_age_sec,
        "stale_samples": stale_samples,
    }


def _option_subscription_freshness_by_symbol_stats(
    *,
    now_epoch: float,
    tokens: list[int],
) -> dict[str, dict[str, object]]:
    by_symbol: dict[str, dict[str, object]] = {}
    for tok in list(tokens or []):
        try:
            tok_int = int(tok)
        except Exception:
            continue
        if tok_int <= 0 or _is_underlying_token(tok_int):
            continue
        symbol = str(_TOKEN_TO_SYMBOL.get(tok_int) or "").upper()
        if not symbol or symbol == "STICKY":
            continue
        stats = by_symbol.setdefault(
            symbol,
            {
                "option_count": 0,
                "fresh_count": 0,
                "stale_count": 0,
                "fresh_ratio": 1.0,
                "max_age_sec": 0.0,
                "urgent_max_age_sec": float(getattr(cfg, "FEED_STALE_OPTION_SUBSCRIPTION_URGENT_MAX_AGE_SEC", 8.0)),
                "stale_samples": [],
            },
        )
        db_row = (get_latest_tick_rows_db([tok_int]) or {}).get(tok_int) or {}
        db_epoch = _coerce_epoch(db_row.get("ts_epoch"))
        memory_epoch = _coerce_epoch(_LAST_MSG_TS_BY_TOKEN.get(tok_int))
        effective_epoch = None
        if db_epoch is not None and memory_epoch is not None:
            effective_epoch = max(float(db_epoch), float(memory_epoch))
        elif db_epoch is not None:
            effective_epoch = float(db_epoch)
        elif memory_epoch is not None:
            effective_epoch = float(memory_epoch)
        age_sec = None if effective_epoch is None else max(0.0, float(now_epoch) - float(effective_epoch))
        stats["option_count"] = int(stats.get("option_count") or 0) + 1
        if age_sec is None or age_sec > float(stats.get("urgent_max_age_sec") or 0.0):
            stats["stale_count"] = int(stats.get("stale_count") or 0) + 1
            stale_samples = list(stats.get("stale_samples") or [])
            if len(stale_samples) < 10:
                stale_samples.append(
                    {
                        "token": tok_int,
                        "symbol": symbol,
                        "age_sec": age_sec,
                        "db_epoch": db_epoch,
                        "memory_epoch": memory_epoch,
                    }
                )
            stats["stale_samples"] = stale_samples
        else:
            stats["fresh_count"] = int(stats.get("fresh_count") or 0) + 1
        if age_sec is not None and float(age_sec) > float(stats.get("max_age_sec") or 0.0):
            stats["max_age_sec"] = float(age_sec)
        option_count = int(stats.get("option_count") or 0)
        fresh_count = int(stats.get("fresh_count") or 0)
        stats["fresh_ratio"] = float(fresh_count / option_count) if option_count > 0 else 1.0
    return by_symbol


def _maybe_refresh_stale_option_subscription_universe(
    *,
    now_epoch: float,
    refresh_state: dict[str, float],
) -> tuple[bool, dict[str, object]]:
    if not bool(is_market_open_ist()):
        return False, {"reason": "market_closed", "refresh_applied": False, "freshness_urgent": False}
    refresh_sec = float(getattr(cfg, "FEED_STALE_OPTION_SUBSCRIPTION_REFRESH_SEC", 20.0))
    drift_refresh_sec = float(getattr(cfg, "FEED_STALE_OPTION_SUBSCRIPTION_DRIFT_REFRESH_SEC", 45.0))
    min_fresh_ratio = float(getattr(cfg, "FEED_STALE_OPTION_SUBSCRIPTION_MIN_FRESH_RATIO", 0.8))
    min_stale_tokens_required = int(getattr(cfg, "FEED_STALE_OPTION_SUBSCRIPTION_MUTATION_MIN_STALE_COUNT", 5))
    mutation_max_fresh_ratio = float(getattr(cfg, "FEED_STALE_OPTION_SUBSCRIPTION_MUTATION_MAX_FRESH_RATIO", 0.7))
    consecutive_windows_required = int(getattr(cfg, "FEED_STALE_OPTION_SUBSCRIPTION_MUTATION_CONSECUTIVE_WINDOWS", 3))
    last_refresh = float(refresh_state.get("last_refresh_epoch") or 0.0)

    desired_tokens_raw, resolution = build_subscription_tokens(list(getattr(cfg, "SYMBOLS", []) or []))
    desired_tokens = _normalize_positive_tokens(desired_tokens_raw)
    current_tokens = _normalize_positive_tokens(_LAST_TOKENS)
    freshness = _option_subscription_freshness_stats(now_epoch=float(now_epoch), tokens=current_tokens)
    freshness_by_symbol = _option_subscription_freshness_by_symbol_stats(now_epoch=float(now_epoch), tokens=current_tokens)
    stale_symbols = [
        sym
        for sym, stats in sorted(freshness_by_symbol.items())
        if int(stats.get("option_count") or 0) > 0
        and (
            float(stats.get("fresh_ratio") or 1.0) < float(min_fresh_ratio)
            or float(stats.get("max_age_sec") or 0.0) > float(stats.get("urgent_max_age_sec") or 0.0)
        )
    ]
    freshness_urgent = bool(stale_symbols)
    freshness_cooldown_elapsed = (float(now_epoch) - float(refresh_state.get("last_freshness_refresh_epoch") or 0.0)) >= drift_refresh_sec
    mutation_eligible_symbols: list[str] = []
    mutation_skipped_symbols: list[str] = []
    mutation_skip_reason_by_symbol: dict[str, str] = {}
    mutation_window_count_by_symbol: dict[str, int] = {}
    mutation_state_snapshot: dict[str, dict[str, object]] = {}

    def _resolution_tokens_for_symbols(symbols: list[str], rows: list[dict] | None = None) -> list[int]:
        symbol_set = {str(sym or "").upper() for sym in list(symbols or []) if str(sym or "").strip()}
        selected: list[int] = []
        for row in list(rows or resolution or []):
            sym = str(row.get("symbol") or "").upper()
            if sym not in symbol_set:
                continue
            for tok in list(row.get("tokens") or []):
                try:
                    tok_int = int(tok)
                except Exception:
                    continue
                if tok_int > 0 and not _is_underlying_token(tok_int):
                    selected.append(tok_int)
        return _normalize_positive_tokens(selected)

    for symbol, stats in sorted(freshness_by_symbol.items()):
        symbol_text = str(symbol or "").upper()
        if not symbol_text:
            continue
        should_mutate_symbol, symbol_payload, next_state = _should_mutate_stale_option_symbol_subscription(
            symbol=symbol_text,
            option_count=int(stats.get("option_count") or 0),
            fresh_count=int(stats.get("fresh_count") or 0),
            stale_count=int(stats.get("stale_count") or 0),
            fresh_ratio=float(stats.get("fresh_ratio") or 0.0),
            max_age_sec=float(stats.get("max_age_sec") or 0.0),
            urgent_max_age_sec=float(stats.get("urgent_max_age_sec") or 0.0),
            min_fresh_ratio=min_fresh_ratio,
            min_stale_tokens_required=min_stale_tokens_required,
            mutation_max_fresh_ratio=mutation_max_fresh_ratio,
            consecutive_windows_required=consecutive_windows_required,
            stale_window_state=dict(_STALE_OPTION_MUTATION_WINDOW_STATE.get(symbol_text) or {}),
            now_epoch=float(now_epoch),
        )
        mutation_state_snapshot[symbol_text] = dict(next_state)
        _STALE_OPTION_MUTATION_WINDOW_STATE[symbol_text] = dict(next_state)
        mutation_window_count_by_symbol[symbol_text] = int(symbol_payload.get("mutation_window_count_by_symbol") or 0)
        if should_mutate_symbol:
            mutation_eligible_symbols.append(symbol_text)
        elif int(stats.get("option_count") or 0) > 0 and symbol_payload.get("diagnostic_urgent"):
            mutation_skipped_symbols.append(symbol_text)
            mutation_skip_reason_by_symbol[symbol_text] = str(symbol_payload.get("mutation_skip_reason") or "not_eligible")

    mutation_guard_ok, mutation_guard_reason, mutation_guard_payload = _can_mutate_ws_subscriptions(
        reason="stale_option_prune_refresh",
        now_epoch=float(now_epoch),
    )
    effective_mutation_symbols = list(mutation_eligible_symbols) if mutation_guard_ok else []
    if freshness_urgent and freshness_cooldown_elapsed and effective_mutation_symbols:
        desired_symbol_tokens = _resolution_tokens_for_symbols(effective_mutation_symbols)
        current_symbol_tokens = _normalize_positive_tokens(
            [
                tok
                for tok in current_tokens
                if str(_TOKEN_TO_SYMBOL.get(int(tok)) or "").upper() in set(effective_mutation_symbols)
                and not _is_underlying_token(int(tok))
            ]
        )
        desired_symbol_set = set(int(t) for t in desired_symbol_tokens)
        current_symbol_set = set(int(t) for t in current_symbol_tokens)
        subscribe_tokens = sorted(desired_symbol_set - current_symbol_set)
        unsubscribe_tokens = sorted(current_symbol_set - desired_symbol_set)
        refresh_tokens = sorted(desired_symbol_set) if not subscribe_tokens and not unsubscribe_tokens else []
        refresh_state["last_refresh_epoch"] = float(now_epoch)
        refresh_state["last_freshness_refresh_epoch"] = float(now_epoch)
        return bool(subscribe_tokens or unsubscribe_tokens or refresh_tokens), {
            "reason": "freshness_drift",
            "refresh_mode": "symbol_freshness_refresh" if refresh_tokens else "symbol_freshness",
            "refresh_sec": refresh_sec,
            "drift_refresh_sec": drift_refresh_sec,
            "previous_count": len(current_tokens),
            "desired_count": len(desired_tokens),
            "subscribe_count": len(subscribe_tokens),
            "unsubscribe_count": len(unsubscribe_tokens),
            "refresh_token_count": len(refresh_tokens),
            "subscribe_tokens": subscribe_tokens,
            "unsubscribe_tokens": unsubscribe_tokens,
            "refresh_tokens": refresh_tokens,
            "refresh_applied": False,
            "freshness_urgent": True,
            "freshness_urgent_symbols": list(stale_symbols),
            "mutation_eligible_symbols": list(effective_mutation_symbols),
            "mutation_skipped_symbols": list(mutation_skipped_symbols),
            "mutation_skip_reason_by_symbol": dict(mutation_skip_reason_by_symbol),
            "mutation_window_count_by_symbol": dict(mutation_window_count_by_symbol),
            "mutation_state_snapshot": mutation_state_snapshot,
            "freshness_by_symbol": freshness_by_symbol,
            "mutation_guard_ok": True,
            "mutation_guard_reason": "ok",
            "mutation_guard_payload": mutation_guard_payload,
            "min_stale_tokens_required": min_stale_tokens_required,
            "mutation_max_fresh_ratio": mutation_max_fresh_ratio,
            "mutation_consecutive_windows_required": consecutive_windows_required,
            **freshness,
            "pruned_stale_option_count_by_symbol": {
                str(row.get("symbol") or "").upper(): int(row.get("stale_option_pruned_count") or 0)
                for row in list(resolution or [])
                if str(row.get("symbol") or "").strip()
            },
        }

    skip_reason = "mutation_not_eligible" if freshness_urgent else "no_delta"
    if freshness_urgent and not mutation_eligible_symbols:
        skip_reason = "freshness_urgent_no_mutation_eligible"
    elif freshness_urgent and not freshness_cooldown_elapsed:
        skip_reason = "freshness_cooldown"
    elif not freshness_urgent and (float(now_epoch) - last_refresh) < refresh_sec:
        skip_reason = "refresh_cooldown"
    elif freshness_urgent and not mutation_guard_ok:
        skip_reason = f"mutation_guard:{mutation_guard_reason}"
    return False, {
        "reason": skip_reason,
        "refresh_mode": "symbol_freshness" if freshness_urgent else "delta",
        "refresh_sec": refresh_sec,
        "drift_refresh_sec": drift_refresh_sec,
        "previous_count": len(current_tokens),
        "desired_count": len(desired_tokens),
        "subscribe_count": 0,
        "unsubscribe_count": 0,
        "subscribe_tokens": [],
        "unsubscribe_tokens": [],
        "refresh_tokens": [],
        "refresh_applied": False,
        "freshness_urgent": freshness_urgent,
        "freshness_urgent_symbols": list(stale_symbols),
        "mutation_eligible_symbols": list(effective_mutation_symbols),
        "mutation_skipped_symbols": list(mutation_skipped_symbols),
        "mutation_skip_reason_by_symbol": dict(mutation_skip_reason_by_symbol),
        "mutation_window_count_by_symbol": dict(mutation_window_count_by_symbol),
        "mutation_state_snapshot": mutation_state_snapshot,
        "freshness_by_symbol": freshness_by_symbol,
        "mutation_guard_ok": bool(mutation_guard_ok),
        "mutation_guard_reason": mutation_guard_reason,
        "mutation_guard_payload": mutation_guard_payload,
        "min_stale_tokens_required": min_stale_tokens_required,
        "mutation_max_fresh_ratio": mutation_max_fresh_ratio,
        "mutation_consecutive_windows_required": consecutive_windows_required,
        **freshness,
        "pruned_stale_option_count_by_symbol": {
            str(row.get("symbol") or "").upper(): int(row.get("stale_option_pruned_count") or 0)
            for row in list(resolution or [])
            if str(row.get("symbol") or "").strip()
        },
    }


def _stale_option_mutation_guard_blocked(refresh_payload: dict[str, object] | None) -> tuple[bool, dict[str, object]]:
    payload = dict(refresh_payload or {})
    freshness_urgent = bool(payload.get("freshness_urgent"))
    mutation_guard_ok = bool(payload.get("mutation_guard_ok"))
    if not freshness_urgent or mutation_guard_ok:
        return False, {}
    skip_payload = {
        "reason": str(payload.get("reason") or "stale_option_prune_refresh_guard"),
        "refresh_mode": str(payload.get("refresh_mode") or "delta"),
        "freshness_urgent": freshness_urgent,
        "freshness_urgent_symbols": list(payload.get("freshness_urgent_symbols") or []),
        "mutation_eligible_symbols": list(payload.get("mutation_eligible_symbols") or []),
        "mutation_skipped_symbols": list(payload.get("mutation_skipped_symbols") or []),
        "mutation_skip_reason_by_symbol": dict(payload.get("mutation_skip_reason_by_symbol") or {}),
        "mutation_window_count_by_symbol": dict(payload.get("mutation_window_count_by_symbol") or {}),
        "mutation_guard_ok": False,
        "mutation_guard_reason": str(payload.get("mutation_guard_reason") or "mutation_guard_false"),
        "mutation_guard_payload": dict(payload.get("mutation_guard_payload") or {}),
        "fresh_count": int(payload.get("fresh_count") or 0),
        "stale_count": int(payload.get("stale_count") or 0),
        "fresh_ratio": float(payload.get("fresh_ratio") or 0.0),
        "max_age_sec": float(payload.get("max_age_sec") or 0.0),
        "min_stale_tokens_required": int(payload.get("min_stale_tokens_required") or 0),
        "mutation_max_fresh_ratio": float(payload.get("mutation_max_fresh_ratio") or 0.0),
        "mutation_consecutive_windows_required": int(payload.get("mutation_consecutive_windows_required") or 0),
        "subscribe_count": int(payload.get("subscribe_count") or 0),
        "unsubscribe_count": int(payload.get("unsubscribe_count") or 0),
        "refresh_token_count": int(payload.get("refresh_token_count") or 0),
        "refresh_applied": False,
        "guard_reason": str(payload.get("mutation_guard_reason") or "mutation_guard_false"),
    }
    return True, skip_payload


def _resubscribe_token_selection() -> tuple[list[int], dict[str, int | bool | str]]:
    desired_tokens = _normalize_positive_tokens(_LAST_DESIRED_TOKENS)
    fallback_tokens = _normalize_positive_tokens(_LAST_TOKENS)
    use_desired_tokens = _use_desired_tokens_for_resubscribe()
    desired_option_tokens_count = sum(1 for t in desired_tokens if not _is_underlying_token(t))
    fallback_option_tokens_count = sum(1 for t in fallback_tokens if not _is_underlying_token(t))
    auto_recover_missing_options = bool(
        desired_tokens
        and desired_option_tokens_count > 0
        and fallback_option_tokens_count <= 0
    )
    prefer_desired_tokens = bool((use_desired_tokens or auto_recover_missing_options) and desired_tokens)
    tokens = desired_tokens if prefer_desired_tokens else fallback_tokens
    return tokens, {
        "use_desired_tokens": use_desired_tokens,
        "desired_tokens_count": len(desired_tokens),
        "desired_option_tokens_count": desired_option_tokens_count,
        "fallback_tokens_count": len(fallback_tokens),
        "fallback_option_tokens_count": fallback_option_tokens_count,
        "auto_recover_missing_options": auto_recover_missing_options,
        "resubscribe_tokens_count": len(tokens),
        "token_source": (
            "desired"
            if use_desired_tokens and desired_tokens
            else ("desired_auto_recovery" if auto_recover_missing_options and desired_tokens else "last_tokens")
        ),
    }


def _soft_resubscribe_current(reason: str) -> bool:
    global _PENDING_SUBSCRIBE_TOKENS, _LAST_TOKENS
    can_mutate, guard_reason, guard_payload = _can_mutate_ws_subscriptions(reason=reason)
    if not can_mutate:
        _log_ws("FEED_SOFT_RESUBSCRIBE_SKIPPED", {**guard_payload, "guard_reason": guard_reason})
        return False
    with _KITE_TICKER_LOCK:
        ws_obj = _KITE_TICKER
        tokens, selection_payload = _resubscribe_token_selection()
        log_payload = {"reason": reason, **selection_payload}
        if ws_obj is None or not tokens:
            _PENDING_SUBSCRIBE_TOKENS = set(tokens)
            _log_ws("FEED_MUTATION_QUEUED", {**log_payload, "detail": "ws_missing_queued", "token_count": len(tokens)})
            return False

        from core.feed.ws_mutation_queue import _check_socket_health
        present, connected, fail_reason = _check_socket_health(ws_obj)
        if not present or connected is False:
            _PENDING_SUBSCRIBE_TOKENS = set(tokens)
            _log_ws("FEED_MUTATION_QUEUED", {**log_payload, "detail": "ws_disconnected_queued", "token_count": len(tokens)})
            return False

        try:
            from core.feed.ws_mutation_queue import safe_subscribe_full_mode
            now_epoch = now_utc_epoch()

            def on_applied():
                global _LAST_TOKENS
                _LAST_TOKENS = list(sorted(set(tokens)))
                _log_ws("FEED_MUTATION_APPLIED", log_payload)

            res_sub, res_mode = safe_subscribe_full_mode(ws_obj, tokens, reason, now_epoch, on_applied_callback=on_applied)

            if res_sub.applied and res_mode.applied:
                return True
            elif res_sub.queued or res_mode.queued:
                _PENDING_SUBSCRIBE_TOKENS = set(tokens)
                _log_ws("FEED_MUTATION_QUEUED", {**log_payload, "token_count": len(tokens)})
                return False
            else:
                _log_ws("FEED_MUTATION_FAILED", {**log_payload, "error": res_sub.failure_reason or res_mode.failure_reason})
                return False
        except Exception as exc:
            _log_ws("FEED_MUTATION_FAILED", {**log_payload, "error": str(exc)})
            return False
def _refresh_subscription_tokens(tokens: list[int], reason: str) -> bool:
    refresh_tokens = _normalize_positive_tokens(tokens)
    if not refresh_tokens:
        return False
    can_mutate, guard_reason, guard_payload = _can_mutate_ws_subscriptions(reason=reason)
    if not can_mutate:
        _log_ws("FEED_REFRESH_SKIPPED", {**guard_payload, "guard_reason": guard_reason, "token_count": len(refresh_tokens)})
        return False
    with _KITE_TICKER_LOCK:
        ws_obj = _KITE_TICKER
        if ws_obj is None:
            _log_ws(
                "FEED_REFRESH_SKIPPED",
                {"reason": reason, "detail": "ws_or_tokens_missing", "token_count": len(refresh_tokens)},
            )
            return False

        from core.feed.ws_mutation_queue import _check_socket_health
        present, connected, fail_reason = _check_socket_health(ws_obj)
        if not present or connected is False:
            _log_ws(
                "FEED_REFRESH_SKIPPED",
                {"reason": reason, "detail": "ws_disconnected", "token_count": len(refresh_tokens)},
            )
            return False

        try:
            from core.feed.ws_mutation_queue import safe_unsubscribe
            now_epoch = now_utc_epoch()
            res_unsub = safe_unsubscribe(ws_obj, refresh_tokens, reason, now_epoch)
            if not res_unsub.applied and res_unsub.failure_reason != "ws_method_missing":
                if res_unsub.queued:
                    # just log queued
                    _log_ws("FEED_REFRESH_UNSUBSCRIBE_QUEUED", {"reason": reason, "tokens": len(refresh_tokens)})
                else:
                    _log_ws("FEED_REFRESH_UNSUBSCRIBE_ERROR", {"reason": reason, "tokens": len(refresh_tokens), "error": res_unsub.failure_reason})
                    return False
        except Exception as exc:
            _log_ws("FEED_REFRESH_UNSUBSCRIBE_ERROR", {"reason": reason, "tokens": len(refresh_tokens), "error": str(exc)})
            return False

        try:
            from core.feed.ws_mutation_queue import safe_subscribe_full_mode
            now_epoch = now_utc_epoch()

            def on_refresh_applied():
                global _LAST_TOKENS
                _LAST_TOKENS = list(sorted(set(_LAST_TOKENS or []).union(set(refresh_tokens))))

            res_sub, res_mode = safe_subscribe_full_mode(ws_obj, refresh_tokens, reason, now_epoch, on_applied_callback=on_refresh_applied)

            if res_sub.queued or res_mode.queued:
                global _PENDING_SUBSCRIBE_TOKENS
                _PENDING_SUBSCRIBE_TOKENS.update(refresh_tokens)
                _log_ws("FEED_MUTATION_QUEUED", {"action": "refresh", "count": len(refresh_tokens), "reason": reason})
                return False
            elif not res_sub.applied or not res_mode.applied:
                _log_ws("FEED_REFRESH_SUBSCRIBE_ERROR", {"reason": reason, "count": len(refresh_tokens), "error": res_sub.failure_reason or res_mode.failure_reason})
                return False

            _log_ws("FEED_REFRESH_OK", {"reason": reason, "count": len(refresh_tokens)})
            _persist_runtime_snapshot_row(ws_connected=True, source=f"rebalance_refresh:{reason}", runtime_state="RUNNING", last_error="")
        except Exception as exc:
            global _RUNTIME_STATE, _LAST_RUNTIME_ERROR
            _RUNTIME_STATE = "SUBSCRIBE_FAILED"
            _LAST_RUNTIME_ERROR = f"refresh_error:{exc}"[:1000]
            _log_ws("FEED_REFRESH_SUBSCRIBE_ERROR", {"reason": reason, "count": len(refresh_tokens), "error": str(exc)})
            _persist_runtime_snapshot_row(ws_connected=False, source=f"rebalance_refresh_error:{reason}", runtime_state="SUBSCRIBE_FAILED", last_error=_LAST_RUNTIME_ERROR)
            return False

    return True
def _soft_resubscribe_hard_block_markers() -> tuple[str, ...]:
    raw = str(getattr(cfg, "FEED_SOFT_RESUBSCRIBE_HARD_BLOCK_MARKERS", "") or "")
    markers = tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    return markers


def _soft_resubscribe_eligibility(reason: str, now_epoch: float | None = None) -> tuple[bool, str]:
    reason_text = str(reason or "")
    reason_lower = reason_text.lower()
    for marker in _soft_resubscribe_hard_block_markers():
        if marker and marker in reason_lower:
            return False, f"hard_reason_marker:{marker}"

    ws_connected = _ws_connected_state()
    if ws_connected is not True:
        return False, "ws_disconnected"

    last_tick_epoch = float(_LAST_WS_TICK_EPOCH or 0.0)
    if last_tick_epoch <= 0.0:
        return False, "no_recent_ws_tick"

    now_ts = float(now_epoch if isinstance(now_epoch, (int, float)) else time.time())
    tick_age_sec = max(0.0, now_ts - last_tick_epoch)
    max_tick_age_sec = float(getattr(cfg, "FEED_SOFT_RESUBSCRIBE_MAX_TICK_AGE_SEC", 2.0))
    if tick_age_sec > max_tick_age_sec:
        return False, f"ws_tick_stale:{tick_age_sec:.2f}s"

    return True, "eligible"


def _auth_error_text(code, reason) -> str:
    parts = []
    if code is not None:
        parts.append(f"code={code}")
    if reason:
        parts.append(str(reason))
    return " ".join(parts).strip()


def _mark_auth_required(reason: str, code=None, *, source: str = "kite_depth_ws") -> None:
    global _AUTH_REQUIRED_LATCH, _AUTH_REQUIRED_LOGGED, _RUNTIME_STATE, _LAST_RUNTIME_ERROR
    if _AUTH_REQUIRED_LATCH:
        return
    _AUTH_REQUIRED_LATCH = True
    _RUNTIME_STATE = "AUTH_BLOCKED"
    _LAST_RUNTIME_ERROR = str(reason or "")[:1000]
    _persist_runtime_snapshot_row(
        ws_connected=False,
        source="mark_auth_required",
        runtime_state="AUTH_BLOCKED",
        last_error=_LAST_RUNTIME_ERROR,
    )
    invalidate_cache(reason=f"ws_auth_failure:{reason}")
    try:
        set_auth_required_state(reason=reason, source=source, code=code, repo_root_path=repo_root())
    except Exception:
        pass
    if not _AUTH_REQUIRED_LOGGED:
        _AUTH_REQUIRED_LOGGED = True
        _log_ws("FEED_AUTH_REQUIRED", {"code": code, "reason": reason})
    stop_depth_ws(reason="auth_required")


def _clear_auth_required_latch() -> None:
    global _AUTH_REQUIRED_LATCH, _AUTH_REQUIRED_LOGGED, _LAST_RUNTIME_ERROR
    _AUTH_REQUIRED_LATCH = False
_SUBSCRIPTION_REQUESTED_TOKENS: set[int] = set()
_SUBSCRIPTION_REQUEST_SUCCEEDED_TOKENS: set[int] = set()
_MODE_REQUEST_SUCCEEDED_TOKENS: set[int] = set()
_FULL_PAYLOAD_OBSERVED_TOKENS: set[int] = set()
_SUBSCRIPTION_REQUESTED_EPOCH_BY_TOKEN: dict[int, float] = {}
_SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN: dict[int, float] = {}
_MODE_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN: dict[int, float] = {}
_FIRST_LIVE_TICK_EPOCH_BY_TOKEN: dict[int, float] = {}
_FIRST_SOURCE_TICK_EPOCH_BY_TOKEN: dict[int, float] = {}
_FIRST_FULL_PAYLOAD_EPOCH_BY_TOKEN: dict[int, float] = {}
_LATEST_FULL_PAYLOAD_EPOCH_BY_TOKEN: dict[int, float] = {}
_SUBSCRIPTION_REQUESTED_EPOCH: float | None = None
_SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH: float | None = None
_MODE_REQUEST_SUCCEEDED_EPOCH: float | None = None
_FULL_PAYLOAD_OBSERVED_EPOCH: float | None = None
_FEED_SESSION_ID: str = ""
_FEED_RECONNECT_GENERATION = 0
_FEED_CONNECTION_START_EPOCH: float | None = None
_FEED_ON_TICKS_ROW_SEQ = 0
_RESTART_LOCK = threading.RLock()
_RESTART_ASYNC_LOCK = threading.Lock()
_RESTART_ASYNC_THREAD = None
_LAST_FULL_RESTART_EPOCH = 0.0
_FULL_RESTARTS = []
_STALE_STRIKES = 0
_WARMUP_PENDING = False
_LOG_PATH = logs_dir() / "depth_ws_watchdog.log"
_TICK_INGEST_ERROR_PATH = logs_dir() / "tick_ingest_errors.jsonl"
_TICK_INGEST_ERROR_WRITER = get_jsonl_writer(_TICK_INGEST_ERROR_PATH)
_TICK_INGEST_ERROR_LOCK = threading.Lock()
_LAST_TICK_INGEST_ERROR_TS = 0.0
_FEED_RUNTIME_SNAPSHOT_WRITE_COUNT = 0
_DEPTH_WS_LOCK: RunLock | None = None
_DEPTH_WS_LOCK_ACQUIRED = False
_STOP_REQUESTED = False
_SCHEMA_LOG_TS = 0.0
_INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "SENSEX"}
_AUTH_REQUIRED_LATCH = False
_OBSERVATION_PLAN_STATE_LOCK = threading.RLock()
_OBSERVATION_PLAN_STATE: dict[str, Any] = {
    "enabled": False,
    "verdict": "DISABLED",
    "production_tokens": [],
    "observation_tokens": [],
    "overlap_tokens": [],
    "observation_exclusive_tokens": [],
    "final_union_tokens": [],
    "missing_observation_tokens": [],
    "configured_budget": None,
    "feed_session_id": "",
    "reconnect_generation": 0,
    "plan_sha": "",
    "decision_epoch": None,
}


def _observation_state_payload() -> dict[str, Any]:
    with _OBSERVATION_PLAN_STATE_LOCK:
        return dict(_OBSERVATION_PLAN_STATE)


def _set_observation_plan_state(
    *,
    enabled: bool,
    verdict: str,
    production_tokens: Sequence[int] = (),
    observation_tokens: Sequence[int] = (),
    final_union_tokens: Sequence[int] = (),
    missing_observation_tokens: Sequence[int] = (),
    configured_budget: int | None = None,
    plan_sha: str = "",
) -> dict[str, Any]:
    production = sorted({int(token) for token in production_tokens if int(token) > 0})
    observation = sorted({int(token) for token in observation_tokens if int(token) > 0})
    final_union = sorted({int(token) for token in final_union_tokens if int(token) > 0})
    overlap = sorted(set(production) & set(observation))
    exclusive = sorted(set(observation) - set(production))
    with _OBSERVATION_PLAN_STATE_LOCK:
        _OBSERVATION_PLAN_STATE.update(
            {
                "enabled": bool(enabled),
                "verdict": str(verdict),
                "production_tokens": production,
                "observation_tokens": observation,
                "overlap_tokens": overlap,
                "observation_exclusive_tokens": exclusive,
                "final_union_tokens": final_union,
                "missing_observation_tokens": sorted({int(token) for token in missing_observation_tokens if int(token) > 0}),
                "configured_budget": configured_budget,
                "feed_session_id": _ensure_feed_session_id() if bool(enabled) else "",
                "reconnect_generation": int(_FEED_RECONNECT_GENERATION),
                "plan_sha": str(plan_sha or ""),
                "decision_epoch": float(now_utc_epoch()),
            }
        )
        return dict(_OBSERVATION_PLAN_STATE)


def reset_market_event_graph_observation_plan_state() -> None:
    _set_observation_plan_state(enabled=False, verdict="DISABLED")


def activate_market_event_graph_launch_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    verdict = str(plan.get("verdict") or "")
    ok = bool(plan.get("ok")) and verdict == "PASS_LIVE_SOURCE_PRESESSION_READINESS"
    return _set_observation_plan_state(
        enabled=ok,
        verdict=verdict if verdict else "BLOCKED_BY_LAUNCH_PLAN_IDENTITY",
        production_tokens=plan.get("production_tokens") or (),
        observation_tokens=plan.get("observation_tokens") or (),
        final_union_tokens=plan.get("final_union_tokens") or (),
        missing_observation_tokens=plan.get("missing_observation_tokens") or (),
        configured_budget=plan.get("configured_budget"),
        plan_sha=str(plan.get("launch_plan_sha256") or ""),
    )


def _ensure_feed_session_id() -> str:
    global _FEED_SESSION_ID
    if not _FEED_SESSION_ID:
        configured = str(os.getenv("LIVE_FEED_SESSION_ID", "") or "").strip()
        _FEED_SESSION_ID = configured or f"kite-depth-{int(now_utc_epoch())}"
    return _FEED_SESSION_ID


def _record_subscription_requested(tokens: Sequence[int]) -> None:
    global _SUBSCRIPTION_REQUESTED_TOKENS, _SUBSCRIPTION_REQUESTED_EPOCH
    normalized = {int(token) for token in (tokens or []) if int(token) > 0}
    if normalized:
        epoch = float(now_utc_epoch())
        _SUBSCRIPTION_REQUESTED_TOKENS.update(normalized)
        for token in normalized:
            _SUBSCRIPTION_REQUESTED_EPOCH_BY_TOKEN[token] = epoch
        _SUBSCRIPTION_REQUESTED_EPOCH = epoch


def _record_subscription_request_succeeded(tokens: Sequence[int]) -> None:
    global _SUBSCRIPTION_REQUEST_SUCCEEDED_TOKENS, _SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH
    normalized = {int(token) for token in (tokens or []) if int(token) > 0}
    if normalized:
        epoch = float(now_utc_epoch())
        _SUBSCRIPTION_REQUEST_SUCCEEDED_TOKENS.update(normalized)
        for token in normalized:
            _SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN[token] = epoch
            _LATEST_SUBSCRIBE_SEQUENCE_BY_TOKEN[token] = int(_NIFTY_MODE_LIFECYCLE_SEQUENCE)
            if token in _MODE_COMMAND_FINAL_FULL_TOKENS:
                _MODE_COMMAND_FINAL_FULL_TOKENS.discard(token)
        _SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH = epoch


def _record_mode_request_succeeded(tokens: Sequence[int]) -> None:
    global _MODE_REQUEST_SUCCEEDED_TOKENS, _MODE_REQUEST_SUCCEEDED_EPOCH
    normalized = {int(token) for token in (tokens or []) if int(token) > 0}
    if normalized:
        epoch = float(now_utc_epoch())
        _MODE_REQUEST_SUCCEEDED_TOKENS.update(normalized)
        _MODE_COMMAND_LOCAL_SEND_SUCCEEDED_TOKENS.update(normalized)
        for token in normalized:
            _MODE_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN[token] = epoch
            _MODE_COMMAND_LOCAL_SEND_SUCCEEDED_EPOCH_BY_TOKEN[token] = epoch
            mode_seq = int(_NIFTY_MODE_LIFECYCLE_SEQUENCE)
            _LATEST_MODE_COMMAND_SEQUENCE_BY_TOKEN[token] = mode_seq
            _MODE_COMMAND_FINAL_FULL_TOKENS.add(token)
            _LATEST_MODE_COMMAND_BY_TOKEN[token] = {
                "operation": "set_mode",
                "requested_mode": "full",
                "sequence_number": mode_seq,
                "receipt_epoch": epoch,
                "socket_generation": int(_SOCKET_GENERATION),
                "feed_session_id": _ensure_feed_session_id(),
                "reconnect_generation": int(_FEED_RECONNECT_GENERATION),
                "local_call_result": "succeeded",
                "broker_delivery_proven": False,
            }
        _MODE_REQUEST_SUCCEEDED_EPOCH = epoch


def _record_full_payload_observed(token: int) -> None:
    global _FULL_PAYLOAD_OBSERVED_TOKENS, _FULL_PAYLOAD_OBSERVED_EPOCH
    if int(token) > 0:
        token_int = int(token)
        epoch = float(now_utc_epoch())
        _FULL_PAYLOAD_OBSERVED_TOKENS.add(int(token))
        _FIRST_FULL_PAYLOAD_EPOCH_BY_TOKEN.setdefault(token_int, epoch)
        _LATEST_FULL_PAYLOAD_EPOCH_BY_TOKEN[token_int] = epoch
        _FULL_PAYLOAD_OBSERVED_EPOCH = epoch


def _reset_market_event_graph_generation_evidence() -> None:
    global _SUBSCRIPTION_REQUESTED_TOKENS, _SUBSCRIPTION_REQUEST_SUCCEEDED_TOKENS, _MODE_REQUEST_SUCCEEDED_TOKENS, _FULL_PAYLOAD_OBSERVED_TOKENS
    global _SUBSCRIPTION_REQUESTED_EPOCH, _SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH, _MODE_REQUEST_SUCCEEDED_EPOCH, _FULL_PAYLOAD_OBSERVED_EPOCH
    _SUBSCRIPTION_REQUESTED_TOKENS = set()
    _SUBSCRIPTION_REQUEST_SUCCEEDED_TOKENS = set()
    _MODE_REQUEST_SUCCEEDED_TOKENS = set()
    _FULL_PAYLOAD_OBSERVED_TOKENS = set()
    _MODE_COMMAND_LOCAL_SEND_SUCCEEDED_TOKENS.clear()
    _MODE_COMMAND_FINAL_FULL_TOKENS.clear()
    _SUBSCRIPTION_REQUESTED_EPOCH_BY_TOKEN.clear()
    _SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN.clear()
    _MODE_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN.clear()
    _MODE_COMMAND_LOCAL_SEND_SUCCEEDED_EPOCH_BY_TOKEN.clear()
    _LATEST_SUBSCRIBE_SEQUENCE_BY_TOKEN.clear()
    _LATEST_MODE_COMMAND_SEQUENCE_BY_TOKEN.clear()
    _LATEST_MODE_COMMAND_BY_TOKEN.clear()
    _FIRST_LIVE_TICK_EPOCH_BY_TOKEN.clear()
    _FIRST_SOURCE_TICK_EPOCH_BY_TOKEN.clear()
    _FIRST_FULL_PAYLOAD_EPOCH_BY_TOKEN.clear()
    _LATEST_FULL_PAYLOAD_EPOCH_BY_TOKEN.clear()
    _LATEST_OBSERVATION_PACKET_BY_TOKEN.clear()
    _OBSERVATION_CALLBACK_COUNT_BY_TOKEN.clear()
    _POST_MODE_CALLBACK_COUNT_BY_TOKEN.clear()
    _POST_MODE_QUOTE_COUNT_BY_TOKEN.clear()
    _POST_MODE_FULL_COUNT_BY_TOKEN.clear()
    _FIRST_POST_MODE_CALLBACK_EPOCH_BY_TOKEN.clear()
    _FIRST_POST_MODE_QUOTE_EPOCH_BY_TOKEN.clear()
    _FIRST_POST_MODE_FULL_EPOCH_BY_TOKEN.clear()
    _SUBSCRIPTION_REQUESTED_EPOCH = None
    _SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH = None
    _MODE_REQUEST_SUCCEEDED_EPOCH = None
    _FULL_PAYLOAD_OBSERVED_EPOCH = None
    with _OBSERVATION_PLAN_STATE_LOCK:
        if _OBSERVATION_PLAN_STATE.get("enabled"):
            _OBSERVATION_PLAN_STATE["feed_session_id"] = _ensure_feed_session_id()
            _OBSERVATION_PLAN_STATE["reconnect_generation"] = int(_FEED_RECONNECT_GENERATION)


def get_current_feed_session_identity() -> dict[str, Any]:
    return {
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "feed_session_id": _ensure_feed_session_id(),
        "reconnect_generation": int(_FEED_RECONNECT_GENERATION),
        "connection_start_epoch": _FEED_CONNECTION_START_EPOCH,
    }


def market_event_graph_subscription_evidence_for_tokens(token_by_symbol: Mapping[str, int]) -> dict[str, Any]:
    expected = {str(symbol).upper(): int(token) for symbol, token in (token_by_symbol or {}).items() if token is not None}
    requested = {symbol for symbol, token in expected.items() if int(token) in _SUBSCRIPTION_REQUESTED_TOKENS}
    request_succeeded = {symbol for symbol, token in expected.items() if int(token) in _SUBSCRIPTION_REQUEST_SUCCEEDED_TOKENS}
    mode_requested = {symbol for symbol, token in expected.items() if int(token) in _MODE_REQUEST_SUCCEEDED_TOKENS}
    full_payload = {symbol for symbol, token in expected.items() if int(token) in _FULL_PAYLOAD_OBSERVED_TOKENS}
    live_tick = {symbol for symbol, token in expected.items() if _coerce_epoch(_LAST_MSG_TS_BY_TOKEN.get(int(token))) is not None}
    ordered = list(expected.keys())
    latest_live_tick_by_symbol = {
        symbol: _coerce_epoch(_LAST_MSG_TS_BY_TOKEN.get(int(token)))
        for symbol, token in expected.items()
        if _coerce_epoch(_LAST_MSG_TS_BY_TOKEN.get(int(token))) is not None
    }
    identity = get_current_feed_session_identity()
    lifecycle: dict[str, dict[str, Any]] = {}
    for symbol, token in expected.items():
        token_int = int(token)
        lifecycle[str(token_int)] = {
            "symbol": symbol,
            "instrument_token": token_int,
            "subscription_requested_epoch": _SUBSCRIPTION_REQUESTED_EPOCH_BY_TOKEN.get(token_int),
            "subscribe_call_succeeded_epoch": _SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN.get(token_int),
            "mode_command_dispatched_epoch": _MODE_COMMAND_LOCAL_SEND_SUCCEEDED_EPOCH_BY_TOKEN.get(token_int),
            "mode_command_local_send_succeeded_epoch": _MODE_COMMAND_LOCAL_SEND_SUCCEEDED_EPOCH_BY_TOKEN.get(token_int),
            "mode_delivery_observed_epoch": _FIRST_FULL_PAYLOAD_EPOCH_BY_TOKEN.get(token_int),
            "latest_subscribe_sequence_number": _LATEST_SUBSCRIBE_SEQUENCE_BY_TOKEN.get(token_int),
            "latest_mode_command_sequence_number": _LATEST_MODE_COMMAND_SEQUENCE_BY_TOKEN.get(token_int),
            "final_current_generation_local_mode": (
                "full" if token_int in _MODE_COMMAND_FINAL_FULL_TOKENS else None
            ),
            "final_current_generation_local_mode_is_full": token_int in _MODE_COMMAND_FINAL_FULL_TOKENS,
            "latest_mode_command": dict(_LATEST_MODE_COMMAND_BY_TOKEN.get(token_int) or {}),
            "post_mode_callback_count": int(_POST_MODE_CALLBACK_COUNT_BY_TOKEN.get(token_int) or 0),
            "registered_observation_callback_count": int(_OBSERVATION_CALLBACK_COUNT_BY_TOKEN.get(token_int) or 0),
            "post_mode_quote_count": int(_POST_MODE_QUOTE_COUNT_BY_TOKEN.get(token_int) or 0),
            "post_mode_full_count": int(_POST_MODE_FULL_COUNT_BY_TOKEN.get(token_int) or 0),
            "first_post_mode_callback_epoch": _FIRST_POST_MODE_CALLBACK_EPOCH_BY_TOKEN.get(token_int),
            "first_post_mode_quote_epoch": _FIRST_POST_MODE_QUOTE_EPOCH_BY_TOKEN.get(token_int),
            "first_post_mode_full_epoch": _FIRST_POST_MODE_FULL_EPOCH_BY_TOKEN.get(token_int),
            "mode_request_succeeded_epoch": _MODE_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN.get(token_int),
            "first_callback_receipt_epoch": _FIRST_LIVE_TICK_EPOCH_BY_TOKEN.get(token_int),
            "latest_callback_receipt_epoch": _coerce_epoch(_LAST_MSG_TS_BY_TOKEN.get(token_int)),
            "first_source_tick_epoch": _FIRST_SOURCE_TICK_EPOCH_BY_TOKEN.get(token_int),
            "latest_source_tick_epoch": _coerce_epoch(_LAST_PAYLOAD_TS_BY_TOKEN.get(token_int)),
            "first_post_mode_full_receipt_epoch": _FIRST_FULL_PAYLOAD_EPOCH_BY_TOKEN.get(token_int),
            "latest_post_mode_full_receipt_epoch": _LATEST_FULL_PAYLOAD_EPOCH_BY_TOKEN.get(token_int),
            # Compatibility aliases. These are receipt-time fields, not broker-source timestamps.
            "first_live_tick_epoch": _FIRST_LIVE_TICK_EPOCH_BY_TOKEN.get(token_int),
            "latest_live_tick_epoch": _coerce_epoch(_LAST_MSG_TS_BY_TOKEN.get(token_int)),
            "first_full_payload_epoch": _FIRST_FULL_PAYLOAD_EPOCH_BY_TOKEN.get(token_int),
            "latest_full_payload_epoch": _LATEST_FULL_PAYLOAD_EPOCH_BY_TOKEN.get(token_int),
            "latest_observation_packet": dict(_LATEST_OBSERVATION_PACKET_BY_TOKEN.get(token_int) or {}),
            "feed_session_id": identity["feed_session_id"],
            "reconnect_generation": identity["reconnect_generation"],
        }
    generation_basis = {
        "provider": identity["provider"],
        "token_domain": identity["token_domain"],
        "feed_session_id": identity["feed_session_id"],
        "reconnect_generation": identity["reconnect_generation"],
        "tokens": sorted(int(token) for token in expected.values()),
        "request_epochs": {
            str(token): lifecycle[str(token)].get("subscription_requested_epoch")
            for token in sorted(int(token) for token in expected.values())
        },
    }
    snapshot_basis = {
        **generation_basis,
        "token_lifecycle": lifecycle,
    }
    payload = {
        "provider": identity["provider"],
        "token_domain": identity["token_domain"],
        "feed_session_id": identity["feed_session_id"],
        "reconnect_generation": int(identity["reconnect_generation"]),
        "connection_start_epoch": identity["connection_start_epoch"],
        "token_by_symbol": dict(expected),
        "token_resolved_symbols": ordered,
        "subscription_requested_symbols": [symbol for symbol in ordered if symbol in requested],
        "subscription_request_succeeded_symbols": [symbol for symbol in ordered if symbol in request_succeeded],
        "mode_command_dispatched_symbols": [symbol for symbol in ordered if int(expected[symbol]) in _MODE_COMMAND_LOCAL_SEND_SUCCEEDED_TOKENS],
        "mode_command_local_send_succeeded_symbols": [symbol for symbol in ordered if int(expected[symbol]) in _MODE_COMMAND_LOCAL_SEND_SUCCEEDED_TOKENS],
        "mode_delivery_observed_symbols": [symbol for symbol in ordered if symbol in full_payload],
        "final_current_generation_full_mode_symbols": [symbol for symbol in ordered if int(expected[symbol]) in _MODE_COMMAND_FINAL_FULL_TOKENS],
        "mode_request_succeeded_symbols": [symbol for symbol in ordered if symbol in mode_requested],
        "live_tick_observed_symbols": [symbol for symbol in ordered if symbol in live_tick],
        "full_payload_observed_symbols": [symbol for symbol in ordered if symbol in full_payload],
        "completed_bar_available_symbols": [],
        "latest_live_tick_epoch_by_symbol": latest_live_tick_by_symbol,
        "subscription_requested_epoch": _SUBSCRIPTION_REQUESTED_EPOCH,
        "subscription_request_succeeded_epoch": _SUBSCRIPTION_REQUEST_SUCCEEDED_EPOCH,
        "mode_request_succeeded_epoch": _MODE_REQUEST_SUCCEEDED_EPOCH,
        "full_payload_observed_epoch": _FULL_PAYLOAD_OBSERVED_EPOCH,
        "token_lifecycle": lifecycle,
        "budget_status": {
            "requested_count": len(expected),
            "request_succeeded_count": len(request_succeeded),
            "mode_request_succeeded_count": len(mode_requested),
            "live_tick_count": len(live_tick),
            "full_payload_count": len(full_payload),
        },
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    observation_state = _observation_state_payload()
    payload["observation_plan_state"] = observation_state
    if observation_state.get("verdict") == BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET:
        payload["observation_blocker"] = {
            "verdict": BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET,
            "missing_observation_tokens": list(observation_state.get("missing_observation_tokens") or []),
            "generation_inactive": True,
        }
    payload["subscription_generation_id"] = hashlib.sha256(
        json.dumps(generation_basis, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    payload["evidence_snapshot_sha256"] = hashlib.sha256(
        json.dumps(snapshot_basis, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    payload["subscription_evidence_id"] = payload["subscription_generation_id"]
    return payload

    _AUTH_REQUIRED_LOGGED = False
    _LAST_RUNTIME_ERROR = ""
    try:
        clear_auth_required_state(source="kite_depth_ws", repo_root_path=repo_root())
    except Exception:
        pass


def _extract_tick_epoch(tick: dict) -> float:
    ts = tick.get("exchange_timestamp") or tick.get("last_trade_time") or tick.get("timestamp")
    if ts is not None:
        try:
            if hasattr(ts, "timestamp"):
                out = float(ts.timestamp())
            else:
                out = float(ts)
            if out > 1e12:
                out = out / 1000.0
            return out
        except Exception:
            pass
    return float(time.time())


def _freshness_epoch_for_tick(token: int | None, payload_epoch: float | None, receipt_epoch: float) -> float:
    try:
        use_receipt_time = bool(getattr(cfg, "DEPTH_WS_OPTION_FRESHNESS_USE_RECEIPT_TIME", True))
    except Exception:
        use_receipt_time = True
    if use_receipt_time and token is not None and not _is_underlying_token(token):
        return float(receipt_epoch)
    return float(payload_epoch if payload_epoch is not None else receipt_epoch)


def _normalized_tick_epoch(
    token: int | None,
    *,
    payload_epoch: float | None,
    receipt_epoch: float,
) -> float:
    epoch = _freshness_epoch_for_tick(token, payload_epoch, receipt_epoch)
    previous_epoch = None
    if token is not None:
        previous_epoch = _coerce_epoch(_LAST_MSG_TS_BY_TOKEN.get(int(token)))
    if previous_epoch is None and _LAST_WS_TICK_EPOCH > 0:
        previous_epoch = float(_LAST_WS_TICK_EPOCH)
    try:
        max_payload_lag_sec = float(getattr(cfg, "FEED_TICK_MAX_PAYLOAD_LAG_SEC", 2.0))
    except Exception:
        max_payload_lag_sec = 2.0
    try:
        market_open_now = bool(is_market_open_ist())
    except Exception:
        market_open_now = False
    try:
        if payload_epoch is None:
            epoch = float(receipt_epoch)
        elif (
            market_open_now
            and previous_epoch is not None
            and (float(receipt_epoch) - float(epoch)) > max_payload_lag_sec
        ):
            epoch = float(receipt_epoch)
    except Exception:
        epoch = float(receipt_epoch)
    if previous_epoch is not None:
        epoch = max(float(epoch), float(previous_epoch))
    return float(epoch)


def _emit_feed_health(event: str, payload: dict | None = None) -> None:
    global _LAST_FEED_HEALTH_STATE
    state = str(event or "").strip().upper()
    if not state:
        return
    if _LAST_FEED_HEALTH_STATE == state:
        return
    _LAST_FEED_HEALTH_STATE = state
    _log_ws(state, dict(payload or {}))


def _reset_stale_on_fresh_ws_tick(*, now_epoch: float, tick_epoch: float, reason: str) -> None:
    global _STALE_STRIKES
    try:
        recover_sec = float(getattr(cfg, "FEED_TICK_RECOVER_SEC", 2.0))
    except Exception:
        recover_sec = 2.0
    tick_age_sec = max(0.0, float(now_epoch) - float(tick_epoch))
    if tick_age_sec > recover_sec:
        return
    strikes_before = int(_STALE_STRIKES)
    _STALE_STRIKES = 0
    _emit_feed_health(
        "FEED_HEALTH_OK",
        {
            "reason": str(reason or "fresh_tick"),
            "tick_age_sec": tick_age_sec,
            "last_ws_tick_epoch": float(tick_epoch),
            "stale_strikes_before": strikes_before,
            "stale_strikes_after": 0,
        },
    )


def _best_price(levels):
    try:
        if not levels:
            return None
        price = levels[0].get("price")
        return float(price) if price is not None else None
    except Exception:
        return None


def _depth_has_bid_ask(depth: dict | None) -> bool:
    if not isinstance(depth, dict):
        return False
    bid = _best_price(depth.get("buy", []))
    ask = _best_price(depth.get("sell", []))
    return bid is not None and ask is not None and bid > 0 and ask > 0


def _update_symbol_freshness(
    symbol: str | None,
    tick_epoch: float,
    has_ltp: bool,
    has_depth: bool,
    *,
    option_symbol: str | None = None,
) -> None:
    if not symbol:
        sym = ""
    else:
        sym = str(symbol).upper()
    if sym:
        if has_ltp:
            _SYMBOL_LAST_LTP_TS[sym] = float(tick_epoch)
        if has_depth:
            _SYMBOL_LAST_DEPTH_TS[sym] = float(tick_epoch)
    opt_sym = str(option_symbol or "").strip().upper()
    if opt_sym and has_ltp:
        _SYMBOL_LAST_OPTION_TICK_TS[opt_sym] = float(tick_epoch)


def _update_index_quote_cache(
    symbol: str,
    bid,
    ask,
    mid,
    ts_epoch: float,
    last_price,
    *,
    volume=None,
):
    try:
        from core.market_data import update_index_quote_snapshot

        update_index_quote_snapshot(
            symbol=symbol,
            bid=bid,
            ask=ask,
            mid=mid,
            ts_epoch=ts_epoch,
            source="ws",
            book_source="depth",
            ltp=last_price,
            volume=volume,
            last_price_source="ws_tick",
        )
    except Exception as exc:
        _log_ws("FEED_INDEX_CACHE_ERROR", {"symbol": symbol, "error": f"{type(exc).__name__}:{exc}"})


def _is_index_symbol(symbol: str | None) -> bool:
    return str(symbol or "").upper() in _INDEX_SYMBOLS


def build_depth_subscription_tokens(symbols=None, max_tokens=None):
    """Return instrument tokens to subscribe on WS. Compatibility shim."""
    # try to reuse related helpers
    for name in ("build_subscription_tokens", "build_tokens", "select_tokens"):
        fn = globals().get(name)
        if callable(fn):
            try:
                return fn(symbols=symbols, max_tokens=max_tokens)
            except TypeError:
                try:
                    return fn(symbols)
                except TypeError:
                    continue
    return []


def _should_throttle_ws_event(key: str, *, now_epoch: float, cooldown_sec: float = _WS_LOG_THROTTLE_SEC) -> bool:
    with _WS_LOG_THROTTLE_LOCK:
        last_emit = _WS_LOG_LAST_EMIT.get(key)
        if last_emit is not None and (float(now_epoch) - float(last_emit)) < float(cooldown_sec):
            return True
        _WS_LOG_LAST_EMIT[key] = float(now_epoch)
        if len(_WS_LOG_LAST_EMIT) > 2048:
            cutoff = float(now_epoch) - (float(cooldown_sec) * 2.0)
            for stale_key, stale_ts in list(_WS_LOG_LAST_EMIT.items()):
                if float(stale_ts) < cutoff:
                    _WS_LOG_LAST_EMIT.pop(stale_key, None)
        return False


def _log_ws(event: str, extra: dict | None = None, *, throttle_key: str | None = None):
    try:
        now_epoch = now_utc_epoch()
        payload = {
            "ts_epoch": now_epoch,
            "ts_ist": now_ist().isoformat(),
            "event": event,
        }
        if extra:
            payload.update(extra)
        if throttle_key:
            if _should_throttle_ws_event(str(throttle_key), now_epoch=float(now_epoch)):
                return
        _WS_LOGGER.info(json.dumps(payload, sort_keys=True, default=str))
    except Exception as exc:
        logger.error("depth_ws_log_error path=%s err=%s:%s", _LOG_PATH, type(exc).__name__, exc)


def _masked_secret_stats(label: str, secret: str | None) -> dict:
    value = str(secret or "")
    return {
        f"{label}_len": len(value),
        f"{label}_tail4": value[-4:] if len(value) >= 4 else value,
        f"{label}_has_whitespace": bool(re.search(r"\s", value)),
    }


def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _is_reactor_not_restartable_error(exc: Exception | None) -> bool:
    if exc is None:
        return False
    name = str(type(exc).__name__ or "").strip().lower()
    text = str(exc or "").strip().lower()
    return "reactornotrestartable" in name or "reactornotrestartable" in text


def _reactor_not_restartable_block_reason() -> str:
    return "reactor_not_restartable_process_restart_required"


def _reactor_terminal_restart_block_active() -> bool:
    global _REACTOR_NOT_RESTARTABLE_DETECTED
    if not _REACTOR_NOT_RESTARTABLE_DETECTED:
        try:
            from twisted.internet import reactor
            if getattr(reactor, "_started", False) and not getattr(reactor, "running", False):
                _REACTOR_NOT_RESTARTABLE_DETECTED = True
        except Exception:
            pass
    blocked_reason = str(_RECONNECT_BLOCKED_REASON or "").strip().lower()
    return bool(_REACTOR_NOT_RESTARTABLE_DETECTED or blocked_reason.startswith("reactor_not_restartable"))


def _is_terminal_ws_fault(*, code: int | None, reason_text: str | None) -> bool:
    reason_lower = str(reason_text or "").strip().lower()
    terminal_reason_markers = (
        "main loop terminated",
        "reactornotrestartable",
        "reactor not restartable",
    )
    return any(marker in reason_lower for marker in terminal_reason_markers)


def _should_require_process_restart_for_ws_fault(*, code: int | None, reason_text: str | None) -> bool:
    if _is_terminal_ws_fault(code=code, reason_text=reason_text):
        return True
    try:
        code_int = int(code) if code is not None else None
    except Exception:
        code_int = None
    if code_int != 1006:
        return False
    reason_lower = str(reason_text or "").strip().lower()
    return "main loop terminated" in reason_lower


def _ws1006_recoverable_max_attempts_per_session() -> int:
    try:
        return max(1, int(getattr(cfg, "DEPTH_WS_WS1006_RECOVERABLE_MAX_ATTEMPTS_PER_SESSION", 3)))
    except Exception:
        return 3


def _ws_recovery_timeout_sec() -> float:
    try:
        return max(0.0, float(getattr(cfg, "DEPTH_WS_RECOVERY_TIMEOUT_SEC", 90.0)))
    except Exception:
        return 90.0


def _ws_max_recoveries_per_window() -> int:
    try:
        return max(1, int(getattr(cfg, "DEPTH_WS_MAX_RECOVERIES_PER_WINDOW", 3)))
    except Exception:
        return 3


def _ws_recovery_window_sec() -> float:
    try:
        return max(0.0, float(getattr(cfg, "DEPTH_WS_RECOVERY_WINDOW_SEC", 600.0)))
    except Exception:
        return 600.0


def _ws1006_recoverable_retry_cooldown_sec() -> float:
    try:
        return max(0.0, float(getattr(cfg, "DEPTH_WS_WS1006_RECOVERABLE_RETRY_COOLDOWN_SEC", 10.0)))
    except Exception:
        return 10.0


def _clear_ws1006_recovery_state() -> None:
    global _RECOVERY_IN_PROGRESS, _WS1006_RECOVERABLE_ATTEMPTS, _WS1006_RECOVERABLE_LAST_ATTEMPT_EPOCH, _WS1006_RECOVERABLE_LAST_REASON
    _RECOVERY_IN_PROGRESS = False
    _WS1006_RECOVERABLE_ATTEMPTS = 0
    _WS1006_RECOVERABLE_LAST_ATTEMPT_EPOCH = 0.0
    _WS1006_RECOVERABLE_LAST_REASON = ""
    try:
        _FEED_RECOVERY_COORDINATOR.reset()
    except Exception:
        pass


def _sync_ws1006_recovery_state_from_coordinator() -> None:
    global _RECOVERY_IN_PROGRESS, _WS1006_RECOVERABLE_ATTEMPTS, _WS1006_RECOVERABLE_LAST_ATTEMPT_EPOCH, _WS1006_RECOVERABLE_LAST_REASON
    state = getattr(_FEED_RECOVERY_COORDINATOR, "state", None)
    if state is None:
        return
    _RECOVERY_IN_PROGRESS = bool(getattr(state, "recovery_in_progress", False))
    _WS1006_RECOVERABLE_ATTEMPTS = int(getattr(state, "recovery_attempt_count", 0) or 0)
    _WS1006_RECOVERABLE_LAST_ATTEMPT_EPOCH = float(
        getattr(state, "recovery_started_epoch", 0.0) or getattr(state, "last_recovery_action_epoch", 0.0) or 0.0
    )
    _WS1006_RECOVERABLE_LAST_REASON = str(getattr(state, "recovery_reason", "") or "")


def _emit_feed_recovery_events(events: list[str], *, source: str, code: int | None, reason: str | None) -> None:
    payload = {
        "source": source,
        "code": code,
        "reason": str(reason or ""),
        "recovery_in_progress": bool(_RECOVERY_IN_PROGRESS),
        "ws1006_recovery_attempt_count": int(_WS1006_RECOVERABLE_ATTEMPTS or 0),
    }
    for event in list(events or []):
        _log_ws(event, payload)
        if event == "FEED_WS_1006_RECOVERY_ATTEMPT":
            _log_ws("FEED_WS_RECOVERY_ATTEMPT", payload)


def _ws1006_fault_category(*, code: int | None, reason_text: str | None) -> str:
    try:
        code_int = int(code) if code is not None else None
    except Exception:
        code_int = None
    reason_lower = str(reason_text or "").strip().lower()
    if is_auth_error(code=code_int, reason_text=reason_text):
        return "AUTH_BLOCKED"
    if _is_terminal_ws_fault(code=code_int, reason_text=reason_text):
        return "TERMINAL_PROCESS_RESTART_REQUIRED"
    if code_int == 1006 and any(marker in reason_lower for marker in ("connection was closed uncleanly", "peer dropped")):
        return "RECOVERABLE_WS_DROP"
    return "UNKNOWN"


def _handle_ws1006_recoverable(*, source: str, ws, code: int | None, reason: str | None) -> bool:
    global _RUNTIME_STATE, _LAST_RUNTIME_ERROR
    category = _ws1006_fault_category(code=code, reason_text=reason)
    if category != "RECOVERABLE_WS_DROP":
        return False
    reason_text = str(reason or "")
    decision = _FEED_RECOVERY_COORDINATOR.request_recovery(
        source=source,
        code=code,
        reason=reason_text,
        max_recoverable_attempts_per_session=_ws1006_recoverable_max_attempts_per_session(),
    )
    _sync_ws1006_recovery_state_from_coordinator()
    _emit_feed_recovery_events(decision.events_emitted, source=source, code=code, reason=reason_text)
    if decision.action == "AUTH_REQUIRED":
        _mark_auth_required(_auth_error_text(code, reason_text), code=code, source="kite_depth_ws_recovery")
        return True
    if decision.action in {"RECOVERY_TIMEOUT", "RECOVERY_BLOCKED"}:
        _RUNTIME_STATE = "RECOVERY_BLOCKED"
        _LAST_RUNTIME_ERROR = f"{code}:{reason_text}"[:1000]
        _persist_runtime_snapshot_row(
            ws_connected=False,
            source=f"{source}:{decision.action.lower()}",
            runtime_state="RECOVERY_BLOCKED",
            last_error=_LAST_RUNTIME_ERROR,
            disconnected_code=code if code is None else int(code),
            disconnected_reason=reason_text,
            restart_attempt_allowed=False,
            restart_attempted=False,
            reconnect_blocked_reason=decision.action,
        )
        return True
    if decision.event == "FEED_RECOVERY_ALREADY_IN_PROGRESS":
        _persist_runtime_snapshot_row(
            ws_connected=False,
            source=f"{source}:recovery_already_in_progress",
            runtime_state="RECONNECTING" if _RECOVERY_IN_PROGRESS else "DEGRADED",
            last_error=f"{code}:{reason_text}"[:1000],
            disconnected_code=code if code is None else int(code),
            disconnected_reason=reason_text,
            restart_attempt_allowed=True,
            restart_attempted=False,
            reconnect_blocked_reason=None,
        )
        return True
    if decision.action == "TERMINAL":
        _RUNTIME_STATE = "RECOVERY_BLOCKED"
        _LAST_RUNTIME_ERROR = f"{code}:{reason_text}"[:1000]
        _block_reconnect_for_process_restart(source=source, code=code, reason=reason_text, ticker=ws)
        return True

    now_epoch = float(now_utc_epoch())
    max_attempts = _ws1006_recoverable_max_attempts_per_session()
    cooldown_sec = _ws1006_recoverable_retry_cooldown_sec()
    _RUNTIME_STATE = "RECONNECTING"
    _LAST_RUNTIME_ERROR = f"{code}:{reason_text}"[:1000]
    _persist_runtime_snapshot_row(
        ws_connected=False,
        source=f"{source}:ws1006_recoverable",
        runtime_state="RECONNECTING",
        last_error=_LAST_RUNTIME_ERROR,
        disconnected_code=code if code is None else int(code),
        disconnected_reason=reason_text,
        restart_attempt_allowed=True,
        restart_attempted=True,
        reconnect_blocked_reason=None,
    )
    if not getattr(cfg, "DEPTH_WS_ALLOW_SOFT_RECONNECTS", True):
        _log_ws(
            "FEED_WS_1006_RECOVERY_DELEGATED_TO_SUBPROCESS",
            {
                "source": source,
                "code": code,
                "reason": reason_text,
            },
        )
        _sync_ws1006_recovery_state_from_coordinator()
        _persist_runtime_snapshot_row(
            ws_connected=False,
            source=f"{source}:soft_reconnect_disabled",
            runtime_state="DEGRADED",
            last_error=_LAST_RUNTIME_ERROR,
            disconnected_code=code if code is None else int(code),
            disconnected_reason=reason_text,
            restart_attempt_allowed=True,
            restart_attempted=False,
            reconnect_blocked_reason=None,
        )
        if (not _reconnect_recovery_blocked_active()
                and not feed_breaker_tripped()
                and _restart_count_1h(now_epoch) < _ws_max_recoveries_per_window()):
            _schedule_restart_depth_ws(
                reason=f"ws1006_recovery_full:{source}",
                ignore_cooldown=True,
                force_full_restart=True,
                source="ws1006_recovery",
            )
        return True

    if _use_native_reconnect():
        soft_ok = _soft_resubscribe_current(reason=f"ws1006_recoverable:{source}")
        if not soft_ok:
            _log_ws(
                "FEED_WS_1006_RECOVERY_SOFT_RECONNECT_FAILED",
                {
                    "source": source,
                    "code": code,
                    "reason": reason_text,
                    "ws1006_recovery_attempt_count": int(_WS1006_RECOVERABLE_ATTEMPTS or 0),
                    "ws1006_max_recoverable_attempts": max_attempts,
                    "ws1006_recovery_cooldown_sec": cooldown_sec,
                    "ws1006_recovery_timeout_sec": _ws_recovery_timeout_sec(),
                    "ws1006_recovery_window_sec": _ws_recovery_window_sec(),
                },
            )
            _sync_ws1006_recovery_state_from_coordinator()
            _persist_runtime_snapshot_row(
                ws_connected=False,
                source=f"{source}:soft_reconnect_failed",
                runtime_state="DEGRADED",
                last_error=_LAST_RUNTIME_ERROR,
                disconnected_code=code if code is None else int(code),
                disconnected_reason=reason_text,
                restart_attempt_allowed=True,
                restart_attempted=False,
                reconnect_blocked_reason=None,
            )
            if (not _reconnect_recovery_blocked_active()
                    and not feed_breaker_tripped()
                    and _restart_count_1h(now_epoch) < _ws_max_recoveries_per_window()):
                _schedule_restart_depth_ws(
                    reason=f"ws1006_recovery_full:{source}",
                    ignore_cooldown=True,
                    force_full_restart=True,
                    source="ws1006_recovery",
                )
    else:
        _soft_resubscribe_current(reason=f"ws1006_recoverable:{source}")
    return True


def _set_reconnect_blocked_reason(reason: str) -> str:
    global _RECONNECT_BLOCKED_REASON, _RECONNECT_BLOCKED_SINCE_EPOCH, _RUNTIME_STATE, _LAST_RUNTIME_ERROR, _REACTOR_NOT_RESTARTABLE_DETECTED
    blocked = str(reason or "").strip().lower() or "unknown_reconnect_block"
    _RECONNECT_BLOCKED_REASON = blocked
    if not _RECONNECT_BLOCKED_SINCE_EPOCH:
        try:
            _RECONNECT_BLOCKED_SINCE_EPOCH = float(time.time())
        except Exception:
            _RECONNECT_BLOCKED_SINCE_EPOCH = 0.0
    if blocked.startswith("reactor_not_restartable") or blocked.startswith("ws1006_process_restart"):
        _RUNTIME_STATE = "FEED_LIFECYCLE_FATAL"
    else:
        _RUNTIME_STATE = "RECOVERY_BLOCKED"
    _LAST_RUNTIME_ERROR = blocked[:1000]
    if blocked.startswith("reactor_not_restartable"):
        _REACTOR_NOT_RESTARTABLE_DETECTED = True
    return blocked


def _set_last_disconnected_info(*, code: int | None = None, reason: str | None = None) -> None:
    global _LAST_DISCONNECTED_CODE, _LAST_DISCONNECTED_REASON
    _LAST_DISCONNECTED_CODE = int(code) if code is not None else None
    _LAST_DISCONNECTED_REASON = str(reason or "").strip()


def _clear_last_disconnected_info() -> None:
    global _LAST_DISCONNECTED_CODE, _LAST_DISCONNECTED_REASON
    _LAST_DISCONNECTED_CODE = None
    _LAST_DISCONNECTED_REASON = ""


def _block_reconnect_for_process_restart(
    *,
    source: str,
    code: int | None = None,
    reason: str | None = None,
    ticker=None,
) -> str:
    global _WATCHDOG_STOP
    internal_retry_state = _disable_kiteticker_internal_retry(reason=str(reason or ""), ticker=ticker)
    blocked_reason = _reactor_not_restartable_block_reason()
    reason_lower = str(reason or "").strip().lower()
    if "connection was closed uncleanly" in reason_lower or "peer dropped" in reason_lower or "main loop terminated" in reason_lower:
        blocked_reason = "ws1006_process_restart_required"
    _set_reconnect_blocked_reason(blocked_reason)
    _log_ws("ws_reactor_not_restartable", {"reason": str(reason or "")})
    _log_ws("ws_lifecycle_fatal", {"reason": str(reason or ""), "ws_lifecycle_state": "FATAL"})
    try:
        if _WATCHDOG_STOP is not None:
            _WATCHDOG_STOP.set()
    except Exception:
        pass
    _log_ws(
        "FEED_WS_PROCESS_RESTART_REQUIRED",
        {
            "source": source,
            "code": code,
            "reason": str(reason or ""),
            "reconnect_blocked_reason": blocked_reason,
            "recovery_action": "process_restart_required",
            **{k: v for k, v in internal_retry_state.items() if v is not None},
        },
    )
    _emit_reconnect_recovery_blocked_snapshot(
        source=f"{source}:process_restart_required",
        reason=blocked_reason,
        internal_retry_state=internal_retry_state,
    )
    return blocked_reason


def _disable_kiteticker_internal_retry(*, reason: str, ticker=None) -> dict[str, object]:
    global _LAST_INTERNAL_RETRY_SUPPRESSION_STATE
    current_ticker = ticker if ticker is not None else _KITE_TICKER
    evidence: dict[str, object] = {
        "reason": str(reason or "").strip(),
        "internal_retry_disabled": False,
        "stop_retry_called": False,
        "factory_stop_trying_called": False,
        "auto_reconnect_disabled": False,
        "error": None,
    }
    if current_ticker is None:
        return evidence
    error_parts: list[str] = []
    try:
        if hasattr(current_ticker, "stop_retry"):
            current_ticker.stop_retry()
            evidence["stop_retry_called"] = True
    except Exception as exc:
        error_parts.append(f"stop_retry:{type(exc).__name__}:{exc}")
    try:
        factory = getattr(current_ticker, "factory", None)
        if factory is not None and hasattr(factory, "stopTrying"):
            factory.stopTrying()
            evidence["factory_stop_trying_called"] = True
    except Exception as exc:
        error_parts.append(f"factory.stopTrying:{type(exc).__name__}:{exc}")
    try:
        if hasattr(current_ticker, "auto_reconnect"):
            setattr(current_ticker, "auto_reconnect", False)
            evidence["auto_reconnect_disabled"] = True
    except Exception as exc:
        error_parts.append(f"auto_reconnect:{type(exc).__name__}:{exc}")
    evidence["internal_retry_disabled"] = bool(
        evidence["stop_retry_called"] or evidence["factory_stop_trying_called"] or evidence["auto_reconnect_disabled"]
    )
    if error_parts:
        evidence["error"] = "; ".join(error_parts)
    _LAST_INTERNAL_RETRY_SUPPRESSION_STATE = dict(evidence)
    return evidence


def _reconnect_recovery_blocked_payload(
    *,
    reason: str,
    source: str,
    internal_retry_state: dict[str, object] | None = None,
) -> dict[str, object]:
    if internal_retry_state is None:
        internal_retry_state = dict(_LAST_INTERNAL_RETRY_SUPPRESSION_STATE or {})
    blocked_reason = str(reason or _RECONNECT_BLOCKED_REASON or "").strip().lower() or "unknown_reconnect_block"
    if blocked_reason == "reactor_not_restartable":
        blocked_reason = _reactor_not_restartable_block_reason()
    reactor_not_restartable = blocked_reason.startswith("reactor_not_restartable")
    payload = {
        "source": source,
        "reason": blocked_reason,
        "reconnect_blocked_reason": blocked_reason,
        "restart_blocked_reason": blocked_reason,
        "recovery_action": "process_restart_required",
        "process_restart_required": True,
        "recovery_blocked": True,
        "runtime_state": "RECOVERY_BLOCKED",
        "ws_connected": False,
        "last_error": blocked_reason,
        "restart_attempt_allowed": False,
        "restart_attempted": False,
        "ws_reconnect_allowed": False,
        "ws_reconnect_attempted": False,
        "restart_suppressed": True,
        "reactor_not_restartable_detected": reactor_not_restartable,
        "reconnect_blocked_since_epoch": float(_RECONNECT_BLOCKED_SINCE_EPOCH or 0.0) or None,
        "no_order_action": True,
        "order_safe": True,
    }
    if internal_retry_state is not None:
        payload.update(
            {
                "internal_retry_disabled": bool(internal_retry_state.get("internal_retry_disabled")),
                "stop_retry_called": bool(internal_retry_state.get("stop_retry_called")),
                "factory_stop_trying_called": bool(internal_retry_state.get("factory_stop_trying_called")),
                "auto_reconnect_disabled": bool(internal_retry_state.get("auto_reconnect_disabled")),
                "internal_retry_error": (
                    str(internal_retry_state.get("error") or "").strip() or None
                ),
                "internal_retry_reason": str(internal_retry_state.get("reason") or "").strip() or None,
            }
        )
    _log_ws("FEED_RECOVERY_BLOCKED", payload)
    _log_ws("FEED_RECONNECT_SUPPRESSED_RECOVERY_BLOCKED", payload)
    return payload


def _emit_reconnect_recovery_blocked_snapshot(
    *,
    source: str,
    reason: str,
    internal_retry_state: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = _reconnect_recovery_blocked_payload(
        reason=reason,
        source=source,
        internal_retry_state=internal_retry_state,
    )
    _persist_runtime_snapshot_row(
        ws_connected=False,
        source=source,
        runtime_state="RECOVERY_BLOCKED",
        last_error=str(payload["last_error"]),
        reconnect_blocked_reason=str(payload["reconnect_blocked_reason"]),
        internal_retry_disabled=bool(payload.get("internal_retry_disabled")) if "internal_retry_disabled" in payload else None,
        stop_retry_called=bool(payload.get("stop_retry_called")) if "stop_retry_called" in payload else None,
        factory_stop_trying_called=(
            bool(payload.get("factory_stop_trying_called")) if "factory_stop_trying_called" in payload else None
        ),
        auto_reconnect_disabled=bool(payload.get("auto_reconnect_disabled")) if "auto_reconnect_disabled" in payload else None,
        internal_retry_error=str(payload.get("internal_retry_error") or "").strip() or None if "internal_retry_error" in payload else None,
        internal_retry_reason=str(payload.get("internal_retry_reason") or "").strip() or None if "internal_retry_reason" in payload else None,
    )
    return payload


def _clear_reconnect_blocked_reason() -> None:
    global _RECONNECT_BLOCKED_REASON, _RECONNECT_BLOCKED_SINCE_EPOCH, _REACTOR_NOT_RESTARTABLE_DETECTED, _LAST_INTERNAL_RETRY_SUPPRESSION_STATE
    _RECONNECT_BLOCKED_REASON = ""
    _RECONNECT_BLOCKED_SINCE_EPOCH = 0.0
    _REACTOR_NOT_RESTARTABLE_DETECTED = False
    _LAST_INTERNAL_RETRY_SUPPRESSION_STATE = {}


def _reconnect_recovery_blocked_active() -> bool:
    blocked_reason = str(_RECONNECT_BLOCKED_REASON or "").strip().lower()
    if blocked_reason == "partial_recovery":
        return bool(_REACTOR_NOT_RESTARTABLE_DETECTED)
    return bool(blocked_reason or _REACTOR_NOT_RESTARTABLE_DETECTED)


def _token_priority_sets(current_tokens: set[int], underlying_tokens: set[int]) -> dict[str, set[int]]:
    current = {int(token) for token in set(current_tokens or set()) if int(token) > 0}
    critical = {int(token) for token in set(underlying_tokens or set()) if int(token) in current}
    core = set(current - critical)
    return {
        "critical": critical,
        "core": core,
        "watch": set(),
        "peripheral": set(),
    }


def _build_partial_recovery_verification(
    *,
    now_epoch: float,
    current_tokens: set[int],
    underlying_tokens: set[int],
    last_msg_by_token: dict[int, float] | None,
    index_threshold_sec: float,
    option_threshold_sec: float,
    previous_stable_cycles: int,
) -> dict[str, object]:
    priorities = _token_priority_sets(current_tokens, underlying_tokens)
    last_by_token = {int(token): float(epoch) for token, epoch in dict(last_msg_by_token or {}).items() if int(token) > 0}
    critical = priorities["critical"]
    core = priorities["core"]

    def _fresh_count(tokens: set[int], threshold: float) -> int:
        count = 0
        for token in tokens:
            last_epoch = float(last_by_token.get(int(token), 0.0) or 0.0)
            if last_epoch > 0 and max(0.0, float(now_epoch) - last_epoch) <= float(threshold):
                count += 1
        return count

    critical_fresh_count = _fresh_count(critical, float(index_threshold_sec))
    core_fresh_count = _fresh_count(core, float(option_threshold_sec))
    critical_required_count = len(critical)
    core_required_count = len(core)
    critical_feed_fresh = critical_fresh_count == critical_required_count
    core_fresh_ratio = 1.0 if core_required_count <= 0 else float(core_fresh_count) / float(core_required_count)
    critical_subscribe_applied_count = len(critical - set(_PENDING_SUBSCRIBE_TOKENS or set()))
    critical_mode_full_applied_count = len(critical - set(_PENDING_MODE_FULL_TOKENS or set()))
    pending_critical_mutations = len(
        critical
        & (set(_PENDING_SUBSCRIBE_TOKENS or set()) | set(_PENDING_UNSUBSCRIBE_TOKENS or set()) | set(_PENDING_MODE_FULL_TOKENS or set()))
    )
    pending_core_mutations = len(
        core
        & (set(_PENDING_SUBSCRIBE_TOKENS or set()) | set(_PENDING_UNSUBSCRIBE_TOKENS or set()) | set(_PENDING_MODE_FULL_TOKENS or set()))
    )
    transport_socket_connected = _ws_connected_state()
    last_transport_epoch = max(
        [float(_LAST_WS_TICK_EPOCH or 0.0)] + [float(epoch) for epoch in last_by_token.values()]
    )
    last_tick_age = None if last_transport_epoch <= 0 else max(0.0, float(now_epoch) - last_transport_epoch)
    registry_consistent = (
        pending_critical_mutations == 0
        and critical_subscribe_applied_count == critical_required_count
        and critical_mode_full_applied_count == critical_required_count
    )
    failure_reasons: list[str] = []
    if transport_socket_connected is not True:
        failure_reasons.append("transport_socket_disconnected")
    if not registry_consistent:
        failure_reasons.append("subscription_registry_inconsistent")
    if not critical_feed_fresh:
        failure_reasons.append("critical_feed_stale")
    if core_fresh_ratio < float(_CORE_FEED_FRESH_QUORUM):
        failure_reasons.append("core_quorum_below_threshold")
    if last_tick_age is None or last_tick_age > float(option_threshold_sec):
        failure_reasons.append("transport_callback_stale")
    stable = not failure_reasons
    stable_cycles = int(previous_stable_cycles or 0) + 1 if stable else 0
    return {
        "transport_socket_connected": transport_socket_connected,
        "active_socket_generation": int(_SOCKET_GENERATION or 0),
        "subscription_registry_consistent": bool(registry_consistent),
        "critical_required_count": critical_required_count,
        "critical_subscribe_applied_count": critical_subscribe_applied_count,
        "critical_mode_full_applied_count": critical_mode_full_applied_count,
        "critical_fresh_count": critical_fresh_count,
        "critical_feed_fresh": bool(critical_feed_fresh),
        "core_required_count": core_required_count,
        "core_fresh_count": core_fresh_count,
        "core_fresh_ratio": core_fresh_ratio,
        "depth_feed_fresh_ratio": core_fresh_ratio,
        "watch_stale_count": 0,
        "peripheral_stale_count": 0,
        "pending_critical_mutations": pending_critical_mutations,
        "pending_core_mutations": pending_core_mutations,
        "last_transport_callback_age_sec": last_tick_age,
        "last_tick_callback_age_sec": last_tick_age,
        "stable_cycles": stable_cycles,
        "stable_cycles_required": int(_RECOVERY_STABLE_CYCLES),
        "verified": bool(stable and stable_cycles >= int(_RECOVERY_STABLE_CYCLES)),
        "failure_reasons": failure_reasons,
        "bounded_recovery": {
            "token_recovery_max_attempts": int(_TOKEN_RECOVERY_MAX_ATTEMPTS),
            "token_recovery_cooldown_sec": float(_TOKEN_RECOVERY_COOLDOWN_SEC),
            "token_recovery_verify_timeout_sec": float(_TOKEN_RECOVERY_VERIFY_TIMEOUT_SEC),
            "recovery_stable_cycles": int(_RECOVERY_STABLE_CYCLES),
        },
    }


def _transition_partial_activity_recovery(
    *,
    now_epoch: float,
    current_tokens: set[int],
    underlying_tokens: set[int],
    last_msg_by_token: dict[int, float] | None,
    index_threshold_sec: float,
    option_threshold_sec: float,
) -> dict[str, object]:
    global _RUNTIME_STATE, _LAST_RUNTIME_ERROR, _PARTIAL_RECOVERY_VERIFICATION
    previous_cycles = int(dict(_PARTIAL_RECOVERY_VERIFICATION or {}).get("stable_cycles") or 0)
    verification = _build_partial_recovery_verification(
        now_epoch=now_epoch,
        current_tokens=current_tokens,
        underlying_tokens=underlying_tokens,
        last_msg_by_token=last_msg_by_token,
        index_threshold_sec=index_threshold_sec,
        option_threshold_sec=option_threshold_sec,
        previous_stable_cycles=previous_cycles,
    )
    _PARTIAL_RECOVERY_VERIFICATION = dict(verification)
    if bool(verification.get("verified")):
        _clear_reconnect_blocked_reason()
        _RUNTIME_STATE = "LIVE"
        _LAST_RUNTIME_ERROR = ""
    else:
        _RUNTIME_STATE = "VERIFYING_RECOVERY" if int(verification.get("stable_cycles") or 0) > 0 else "DEGRADED_LOCAL"
        _LAST_RUNTIME_ERROR = "partial_activity_verification_pending"
    _log_ws(
        "FEED_PARTIAL_RECOVERY_VERIFYING",
        {
            **verification,
            "runtime_state": _RUNTIME_STATE,
            "reconnect_blocked_reason": None,
            "process_restart_required": False,
            "restart_suppressed": False,
            "no_order_action": True,
            "order_safe": True,
        },
    )
    return verification


def _should_mutate_stale_option_symbol_subscription(
    *,
    symbol: str,
    option_count: int,
    fresh_count: int,
    stale_count: int,
    fresh_ratio: float,
    max_age_sec: float,
    urgent_max_age_sec: float,
    min_fresh_ratio: float,
    min_stale_tokens_required: int,
    mutation_max_fresh_ratio: float,
    consecutive_windows_required: int,
    stale_window_state: dict[str, object] | None,
    now_epoch: float,
) -> tuple[bool, dict[str, object], dict[str, object]]:
    symbol_text = str(symbol or "").strip().upper()
    previous_state = dict(stale_window_state or {})
    previous_window_count = int(previous_state.get("mutation_window_count") or 0)
    previous_breach_active = bool(previous_state.get("breach_active"))
    diagnostic_urgent = bool(option_count > 0 and (float(fresh_ratio) < float(min_fresh_ratio) or float(max_age_sec) > float(urgent_max_age_sec)))
    breadth_breach = bool(
        option_count > 0
        and int(stale_count) >= int(min_stale_tokens_required)
        and float(fresh_ratio) <= float(mutation_max_fresh_ratio)
        and float(max_age_sec) > float(urgent_max_age_sec)
    )
    if breadth_breach:
        mutation_window_count = previous_window_count + 1 if previous_breach_active else 1
    else:
        mutation_window_count = 0
    mutation_eligible = bool(breadth_breach and mutation_window_count >= int(consecutive_windows_required))
    skip_reason = ""
    if not diagnostic_urgent:
        skip_reason = "not_diagnostic_urgent"
    elif int(stale_count) < int(min_stale_tokens_required):
        skip_reason = "stale_count_below_threshold"
    elif float(fresh_ratio) > float(mutation_max_fresh_ratio):
        skip_reason = "fresh_ratio_above_mutation_threshold"
    elif float(max_age_sec) <= float(urgent_max_age_sec):
        skip_reason = "max_age_below_urgent_threshold"
    elif not breadth_breach:
        skip_reason = "mutation_breadth_not_met"
    elif mutation_window_count < int(consecutive_windows_required):
        skip_reason = "mutation_consecutive_windows_not_met"
    return mutation_eligible, {
        "symbol": symbol_text or None,
        "option_count": int(option_count),
        "fresh_count": int(fresh_count),
        "stale_count": int(stale_count),
        "fresh_ratio": float(fresh_ratio),
        "max_age_sec": float(max_age_sec),
        "urgent_max_age_sec": float(urgent_max_age_sec),
        "min_fresh_ratio": float(min_fresh_ratio),
        "min_stale_tokens_required": int(min_stale_tokens_required),
        "mutation_max_fresh_ratio": float(mutation_max_fresh_ratio),
        "mutation_consecutive_windows_required": int(consecutive_windows_required),
        "diagnostic_urgent": diagnostic_urgent,
        "breadth_breach": breadth_breach,
        "mutation_window_count_by_symbol": mutation_window_count,
        "mutation_allowed": mutation_eligible,
        "mutation_skip_reason": skip_reason,
        "breach_active": breadth_breach,
        "now_epoch": float(now_epoch),
    }, {
        "breach_active": breadth_breach,
        "mutation_window_count": mutation_window_count,
        "last_eval_epoch": float(now_epoch),
        "last_breach_epoch": float(now_epoch) if breadth_breach else float(previous_state.get("last_breach_epoch") or 0.0),
    }


def _can_mutate_ws_subscriptions(reason: str, now_epoch: float | None = None) -> tuple[bool, str, dict[str, object]]:
    current_runtime_state = str(_RUNTIME_STATE or "").strip().upper()
    reconnect_blocked_reason = str(_RECONNECT_BLOCKED_REASON or "").strip().lower()
    now_value = float(now_epoch) if now_epoch is not None else None
    ws_connected = _ws_connected_state()
    option_state = _option_runtime_state(
        now_epoch=float(now_value) if now_value is not None else float(now_epoch or 0.0),
        tokens=list(_LAST_TOKENS or []),
        expected_counts_by_symbol=dict(_LAST_OPTION_COUNTS_BY_SYMBOL or {}),
        min_required_by_symbol=dict(_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL or {}),
        ws_connected=ws_connected,
    )
    feed_block_reason_by_symbol = dict(option_state.get("feed_block_reason_by_symbol") or {})
    active_blockers_by_symbol = dict(option_state.get("active_blockers_by_symbol") or {})
    option_blockers = sorted(
        {
            str(reason_code).strip().upper()
            for reason_code in feed_block_reason_by_symbol.values()
            if str(reason_code or "").strip() and str(reason_code or "").strip().upper() != "OK"
        }
    )
    if not option_blockers:
        for blockers in active_blockers_by_symbol.values():
            for blocker in blockers or []:
                blocker_text = str(blocker or "").strip().upper()
                if blocker_text and blocker_text != "OK":
                    option_blockers.append(blocker_text)
        option_blockers = sorted(set(option_blockers))
    guard_payload: dict[str, object] = {
        "reason": str(reason or "").strip(),
        "runtime_state": current_runtime_state or "UNKNOWN",
        "ws_connected": ws_connected,
        "reconnect_blocked_reason": reconnect_blocked_reason or None,
        "stop_requested": bool(_STOP_REQUESTED),
        "reactor_terminal_restart_block_active": _reactor_terminal_restart_block_active(),
        "reconnect_recovery_blocked_active": _reconnect_recovery_blocked_active(),
        "now_epoch": now_value,
        "feed_block_reason_by_symbol": feed_block_reason_by_symbol,
        "active_blockers_by_symbol": active_blockers_by_symbol,
        "option_blockers": option_blockers,
    }
    if bool(_STOP_REQUESTED):
        return False, "stop_requested", guard_payload
    if _reconnect_recovery_blocked_active():
        return False, reconnect_blocked_reason or "reconnect_recovery_blocked", guard_payload
    if _reactor_terminal_restart_block_active():
        return False, reconnect_blocked_reason or "reactor_terminal_restart_block", guard_payload
    if current_runtime_state in {"RECOVERY_BLOCKED", "AUTH_BLOCKED", "IMPORT_MISSING", "STOPPED", "STOPPING", "DEGRADED"}:
        return False, current_runtime_state.lower(), guard_payload
    if _KITE_TICKER is None:
        return False, "ws_not_running", guard_payload
    if ws_connected is not True:
        return False, "ws_disconnected", guard_payload
    if _LAST_WS_TICK_EPOCH <= 0.0:
        return False, "no_ws_ticks", guard_payload
    if now_value is not None and now_value - float(_LAST_WS_TICK_EPOCH) > float(getattr(cfg, "MAX_DEPTH_AGE_SEC", getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0))) * 3.0:
        return False, "ws_tick_stale", guard_payload
    return True, "ok", guard_payload


def _apply_subscription_delta(ws, subscribe_tokens: list[int], unsubscribe_tokens: list[int], reason: str):
    global _LAST_TOKENS, _PENDING_SUBSCRIBE_TOKENS, _PENDING_UNSUBSCRIBE_TOKENS, _PENDING_MODE_FULL_TOKENS, _LAST_MUTATION_RESULT, _RUNTIME_STATE, _LAST_RUNTIME_ERROR
    to_subscribe = sorted(set(int(t) for t in (subscribe_tokens or []) if int(t) > 0))
    to_unsubscribe = sorted(set(int(t) for t in (unsubscribe_tokens or []) if int(t) > 0))

    can_mutate, guard_reason, guard_payload = _can_mutate_ws_subscriptions(reason=reason)
    if not can_mutate:
        _log_ws(
            "FEED_REBALANCE_SKIPPED",
            {**guard_payload, "guard_reason": guard_reason, "subscribe_count": len(to_subscribe), "unsubscribe_count": len(to_unsubscribe)},
        )
        return False

    from core.feed.ws_mutation_queue import _check_socket_health
    present, connected, fail_reason = _check_socket_health(ws)
    if not present or connected is False:
        _log_ws(
            "FEED_REBALANCE_SKIPPED",
            {"reason": reason, "detail": "ws_disconnected"},
        )
        return False

    all_applied = True

    try:
        from core.feed.ws_mutation_queue import safe_subscribe_full_mode, safe_unsubscribe
        now_epoch = now_utc_epoch()

        if to_subscribe:
            def on_sub_applied():
                global _LAST_TOKENS
                _LAST_TOKENS = list(sorted(set(_LAST_TOKENS or []).union(set(to_subscribe))))
                _log_ws("FEED_MUTATION_APPLIED", {"action": "subscribe", "count": len(to_subscribe), "reason": reason})

            res_sub, res_mode = safe_subscribe_full_mode(ws, to_subscribe, reason, now_epoch, on_applied_callback=on_sub_applied)

            if res_sub.queued or res_mode.queued:
                _PENDING_SUBSCRIBE_TOKENS.update(to_subscribe)
                _log_ws("FEED_MUTATION_QUEUED", {"action": "subscribe", "count": len(to_subscribe), "reason": reason})
                all_applied = False
            elif not res_sub.applied or not res_mode.applied:
                _log_ws("FEED_MUTATION_FAILED", {"action": "subscribe", "reason": res_sub.failure_reason or res_mode.failure_reason})
                all_applied = False

        if to_unsubscribe:
            def on_unsub_applied():
                global _LAST_TOKENS
                _LAST_TOKENS = list(sorted(set(_LAST_TOKENS or []) - set(to_unsubscribe)))
                _log_ws("FEED_MUTATION_APPLIED", {"action": "unsubscribe", "count": len(to_unsubscribe), "reason": reason})

            res_unsub = safe_unsubscribe(ws, to_unsubscribe, reason, now_epoch, on_applied_callback=on_unsub_applied)
            if res_unsub.queued:
                _PENDING_UNSUBSCRIBE_TOKENS.update(to_unsubscribe)
                _log_ws("FEED_MUTATION_QUEUED", {"action": "unsubscribe", "count": len(to_unsubscribe), "reason": reason})
                all_applied = False
            elif not res_unsub.applied:
                _log_ws("FEED_MUTATION_FAILED", {"action": "unsubscribe", "reason": res_unsub.failure_reason})
                all_applied = False

    except Exception as exc:
        _RUNTIME_STATE = "SUBSCRIBE_FAILED"
        _LAST_RUNTIME_ERROR = f"subscribe_delta:{exc}"[:1000]
        _log_ws(
            "FEED_MUTATION_FAILED",
            {"reason": reason, "error": str(exc)},
        )
        _persist_runtime_snapshot_row(
            ws_connected=False,
            source=f"rebalance_subscribe_error:{reason}",
            runtime_state="SUBSCRIBE_FAILED",
            last_error=_LAST_RUNTIME_ERROR,
        )
        return False

    return all_applied


def _normalize_recovery_blocked_snapshot_state(
    *,
    runtime_state: str | None,
    state_machine: dict | None,
    reconnect_blocked_reason: str | None,
    ws_connected: bool | None,
) -> tuple[str, dict[str, object], bool | None, str | None]:
    blocked_reason = str(
        reconnect_blocked_reason if reconnect_blocked_reason is not None else (_RECONNECT_BLOCKED_REASON or "")
    ).strip().lower() or None
    if blocked_reason == "reactor_not_restartable":
        blocked_reason = _reactor_not_restartable_block_reason()
    if blocked_reason == "partial_recovery":
        blocked_reason = None
    if not blocked_reason and _REACTOR_NOT_RESTARTABLE_DETECTED:
        blocked_reason = _reactor_not_restartable_block_reason()
    effective_state = str(runtime_state or _RUNTIME_STATE or "UNKNOWN").strip().upper() or "UNKNOWN"
    state_machine_row = dict(state_machine or {})
    effective_ws_connected = ws_connected
    if blocked_reason:
        effective_state = "RECOVERY_BLOCKED"
        effective_ws_connected = False
        machine_state = str(state_machine_row.get("state") or "").strip().upper()
        if machine_state in {"LIVE", "STARTING", "TICKS_FLOWING", "MARKET_OPEN", ""}:
            state_machine_row["state"] = "DOWN"
            state_machine_row["reason"] = (
                "ws1006_process_restart_required"
                if blocked_reason == "ws1006_process_restart_required"
                else (
                    "reactor_not_restartable_process_restart_required"
                    if blocked_reason.startswith("reactor_not_restartable")
                    else "reconnect_blocked"
                )
            )
        state_machine_row.setdefault("reason", blocked_reason)
    return effective_state, state_machine_row, effective_ws_connected, blocked_reason


def _runtime_transport_truth_fields(
    *,
    now_epoch: float,
    ws_connected: bool | None,
    runtime_state: str,
    last_ws_tick_epoch: float | None,
    last_tick_age_sec: float | None,
    last_depth_age_sec: float | None,
    reconnect_blocked_reason: str | None,
) -> dict[str, object]:
    verification = dict(_PARTIAL_RECOVERY_VERIFICATION or {})
    callback_epoch = None
    callback_candidates = [float(_LAST_WS_TICK_EPOCH or 0.0)]
    callback_candidates.extend(float(epoch) for epoch in dict(_LAST_MSG_TS_BY_TOKEN or {}).values())
    if callback_candidates:
        max_epoch = max(callback_candidates)
        callback_epoch = max_epoch if max_epoch > 0 else None
    tick_epoch = _coerce_epoch(last_ws_tick_epoch) or callback_epoch
    callback_age = None if callback_epoch is None else max(0.0, float(now_epoch) - float(callback_epoch))
    callback_activity_present = callback_age is not None and callback_age <= float(
        getattr(cfg, "MAX_DEPTH_AGE_SEC", getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0))
    ) * 3.0
    subscribed_count = len(set(int(token) for token in list(_LAST_TOKENS or []) if int(token) > 0))
    intended_count = int(_INTENDED_TOKEN_COUNT if _INTENDED_TOKEN_COUNT > 0 else subscribed_count)
    subscription_registry_consistent = (
        len(_PENDING_SUBSCRIBE_TOKENS or set()) == 0
        and len(_PENDING_UNSUBSCRIBE_TOKENS or set()) == 0
        and len(_PENDING_MODE_FULL_TOKENS or set()) == 0
    )
    subscription_truth_complete = subscription_registry_consistent and (intended_count <= 0 or subscribed_count >= intended_count)
    mode_full_truth_complete = subscription_registry_consistent and len(_PENDING_MODE_FULL_TOKENS or set()) == 0
    critical_feed_fresh = bool(verification.get("critical_feed_fresh", True))
    core_feed_fresh_ratio = float(verification.get("core_fresh_ratio", 1.0) or 0.0)
    depth_ratio = float(verification.get("depth_feed_fresh_ratio", 1.0 if last_depth_age_sec is not None else 0.0) or 0.0)
    state_text = str(runtime_state or "").strip().upper()
    blocked_reason = str(reconnect_blocked_reason or "").strip().lower()
    execution_feed_ready = bool(
        ws_connected is True
        and not blocked_reason
        and state_text in {"RUNNING", "LIVE", "HEALTHY", "OK"}
        and subscription_truth_complete
        and mode_full_truth_complete
        and critical_feed_fresh
        and core_feed_fresh_ratio >= float(_CORE_FEED_FRESH_QUORUM)
        and last_tick_age_sec is not None
    )
    canonical_state = state_text
    if state_text == "RUNNING" and execution_feed_ready:
        canonical_state = "LIVE"
    elif state_text == "RUNNING" and not execution_feed_ready:
        canonical_state = "DEGRADED_LOCAL"
    return {
        "transport_socket_connected": ws_connected,
        "transport_last_callback_epoch": callback_epoch,
        "transport_last_tick_epoch": tick_epoch,
        "transport_callback_activity_present": bool(callback_activity_present),
        "subscription_registry_consistent": bool(subscription_registry_consistent),
        "subscription_truth_complete": bool(subscription_truth_complete),
        "mode_full_truth_complete": bool(mode_full_truth_complete),
        "critical_feed_fresh": bool(critical_feed_fresh),
        "core_feed_fresh_ratio": core_feed_fresh_ratio,
        "depth_feed_fresh_ratio": depth_ratio,
        "execution_feed_ready": bool(execution_feed_ready),
        "canonical_feed_state": canonical_state,
        "recovery_verification": verification or None,
    }


def _log_tick_ingest_error(
    *,
    token: int | None,
    reason: str,
    error: str | None = None,
    keys: list[str] | None = None,
    tick_ts_present: bool | None = None,
) -> None:
    global _LAST_TICK_INGEST_ERROR_TS
    now_epoch = float(time.time())
    min_interval = 10.0
    with _TICK_INGEST_ERROR_LOCK:
        if (now_epoch - _LAST_TICK_INGEST_ERROR_TS) < min_interval:
            return
        _LAST_TICK_INGEST_ERROR_TS = now_epoch
    payload = {
        "ts_epoch": now_epoch,
        "event": "TICK_INGEST_ERROR",
        "instrument_token": token,
        "reason": reason,
    }
    if error:
        payload["error"] = str(error)
    if keys:
        payload["keys"] = list(keys)[:20]
    if tick_ts_present is not None:
        payload["tick_ts_present"] = bool(tick_ts_present)
    try:
        if not _TICK_INGEST_ERROR_WRITER.write(payload):
            logger.error("tick_ingest_error_log_write_failed path=%s", _TICK_INGEST_ERROR_PATH)
    except Exception:
        pass


def _coerce_epoch(value) -> float | None:
    try:
        if value is None:
            return None
        epoch = float(value)
        if epoch > 1e12:
            epoch = epoch / 1000.0
        return epoch
    except Exception:
        return None


def _latest_db_tick_epoch() -> float | None:
    db_path = Path(str(getattr(cfg, "TRADE_DB_PATH", "") or "")).expanduser()
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(str(db_path), timeout=30.0, check_same_thread=False) as conn:
            conn.execute("PRAGMA busy_timeout=30000")
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
            except Exception:
                pass
            return _coerce_epoch(get_max_tick_epoch(conn))
    except Exception:
        return None


def _ws_connected_state() -> bool | None:
    with _KITE_TICKER_LOCK:
        ticker = _KITE_TICKER
    if ticker is None:
        return None
    try:
        probe = getattr(ticker, "is_connected", None)
        if callable(probe):
            return bool(probe())
        if isinstance(probe, bool):
            return probe
    except Exception:
        return None
    return None


def _restart_count_1h(now_epoch: float) -> int:
    with _RESTART_LOCK:
        recent = [ts for ts in _FULL_RESTARTS if (float(now_epoch) - float(ts)) <= 3600.0]
    return len(recent)


def _restart_verification_enabled() -> bool:
    return bool(getattr(cfg, "FEED_RESTART_VERIFY_ENABLE", True))


def _restart_verification_require_market_open() -> bool:
    return bool(getattr(cfg, "FEED_RESTART_VERIFY_REQUIRE_MARKET_OPEN", True))


def _restart_verification_require_options() -> bool:
    return bool(getattr(cfg, "FEED_RESTART_VERIFY_REQUIRE_OPTIONS", True))


def _restart_verification_timeout_sec() -> float:
    try:
        return max(1.0, float(getattr(cfg, "FEED_RESTART_VERIFY_TIMEOUT_SEC", 45.0)))
    except Exception:
        return 45.0


def _restart_verification_min_option_ticks_per_symbol() -> int:
    try:
        return max(1, int(getattr(cfg, "FEED_RESTART_VERIFY_MIN_OPTION_TICKS_PER_SYMBOL", 1)))
    except Exception:
        return 1


def _option_feed_verification_enabled() -> bool:
    return bool(getattr(cfg, "FEED_OPTION_VERIFY_ENABLE", True))


def _option_feed_verification_timeout_sec() -> float:
    try:
        base = max(1.0, float(getattr(cfg, "FEED_OPTION_VERIFY_TIMEOUT_SEC", 45.0)))
        try:
            from core.time_utils import is_market_open_ist
            from datetime import datetime
            import pytz

            if is_market_open_ist():
                now_ist = datetime.now(pytz.timezone("Asia/Kolkata"))
                if now_ist.hour == 9 and now_ist.minute < 30:
                    return max(base, float(getattr(cfg, "FEED_OPTION_VERIFY_TIMEOUT_MARKET_OPEN_SEC", 90.0)))
        except Exception:
            pass
        return base
    except Exception:
        return 45.0


def _option_feed_verification_min_ticks_per_symbol() -> int:
    try:
        return max(1, int(getattr(cfg, "FEED_OPTION_VERIFY_MIN_OPTION_TICKS_PER_SYMBOL", 1)))
    except Exception:
        return 1


def _reset_feed_restart_verification(*, reason: str) -> None:
    global _FEED_RESTART_VERIFY_STATE
    global _FEED_RESTART_VERIFY_REASON
    global _FEED_RESTART_VERIFY_START_EPOCH
    global _FEED_RESTART_VERIFY_DEADLINE_EPOCH
    global _FEED_RESTART_VERIFY_CONNECT_EPOCH
    global _FEED_RESTART_VERIFY_SUBSCRIBE_EPOCH
    global _FEED_RESTART_VERIFY_VERIFIED_EPOCH
    global _FEED_RESTART_VERIFY_FAILURE_DETAIL
    global _FEED_RESTART_VERIFY_LAST_STAGE_EVENT
    if not _restart_verification_enabled():
        return
    with _RESTART_VERIFY_LOCK:
        _FEED_RESTART_VERIFY_STATE = "IDLE"
        _FEED_RESTART_VERIFY_REASON = str(reason or "")
        _FEED_RESTART_VERIFY_START_EPOCH = 0.0
        _FEED_RESTART_VERIFY_DEADLINE_EPOCH = 0.0
        _FEED_RESTART_VERIFY_CONNECT_EPOCH = None
        _FEED_RESTART_VERIFY_SUBSCRIBE_EPOCH = None
        _FEED_RESTART_VERIFY_VERIFIED_EPOCH = None
        _FEED_RESTART_VERIFY_FAILURE_DETAIL = ""
        _FEED_RESTART_VERIFY_LAST_STAGE_EVENT = ""
    _clear_last_disconnected_info()


def _reset_option_feed_verification(*, reason: str) -> None:
    global _OPTION_FEED_VERIFY_STATE
    global _OPTION_FEED_VERIFY_REASON
    global _OPTION_FEED_VERIFY_START_EPOCH
    global _OPTION_FEED_VERIFY_DEADLINE_EPOCH
    global _OPTION_FEED_VERIFY_REQUIRED_SYMBOLS
    global _OPTION_FEED_VERIFY_REQUESTED_BY_SYMBOL
    global _OPTION_FEED_VERIFY_SUBSCRIBED_BY_SYMBOL
    global _OPTION_FEED_VERIFY_VERIFIED_SYMBOLS
    global _OPTION_FEED_VERIFY_MISSING_SYMBOLS
    global _OPTION_FEED_VERIFY_VERIFIED_EPOCH
    global _OPTION_FEED_VERIFY_FAILURE_DETAIL
    global _OPTION_FEED_VERIFY_LAST_STAGE_EVENT
    if not _option_feed_verification_enabled():
        return
    with _RESTART_VERIFY_LOCK:
        _OPTION_FEED_VERIFY_STATE = "IDLE"
        _OPTION_FEED_VERIFY_REASON = str(reason or "")
        _OPTION_FEED_VERIFY_START_EPOCH = 0.0
        _OPTION_FEED_VERIFY_DEADLINE_EPOCH = 0.0
        _OPTION_FEED_VERIFY_REQUIRED_SYMBOLS = []
        _OPTION_FEED_VERIFY_REQUESTED_BY_SYMBOL = {}
        _OPTION_FEED_VERIFY_SUBSCRIBED_BY_SYMBOL = {}
        _OPTION_FEED_VERIFY_VERIFIED_SYMBOLS = []
        _OPTION_FEED_VERIFY_MISSING_SYMBOLS = []
        _OPTION_FEED_VERIFY_VERIFIED_EPOCH = None
        _OPTION_FEED_VERIFY_FAILURE_DETAIL = ""
        _OPTION_FEED_VERIFY_LAST_STAGE_EVENT = ""


def _begin_option_feed_verification(
    *,
    reason: str,
    start_epoch: float,
    requested_by_symbol: dict[str, int] | None,
    subscribed_by_symbol: dict[str, int] | None,
) -> None:
    global _OPTION_FEED_VERIFY_STATE
    global _OPTION_FEED_VERIFY_REASON
    global _OPTION_FEED_VERIFY_START_EPOCH
    global _OPTION_FEED_VERIFY_DEADLINE_EPOCH
    global _OPTION_FEED_VERIFY_REQUIRED_SYMBOLS
    global _OPTION_FEED_VERIFY_REQUESTED_BY_SYMBOL
    global _OPTION_FEED_VERIFY_SUBSCRIBED_BY_SYMBOL
    global _OPTION_FEED_VERIFY_VERIFIED_SYMBOLS
    global _OPTION_FEED_VERIFY_MISSING_SYMBOLS
    global _OPTION_FEED_VERIFY_VERIFIED_EPOCH
    global _OPTION_FEED_VERIFY_FAILURE_DETAIL
    global _OPTION_FEED_VERIFY_LAST_STAGE_EVENT
    if not _option_feed_verification_enabled():
        return
    start_epoch_f = float(start_epoch or 0.0)
    if start_epoch_f <= 0.0:
        start_epoch_f = float(now_utc_epoch())
    requested_map = {
        str(symbol or "").upper(): max(0, int(count or 0))
        for symbol, count in dict(requested_by_symbol or {}).items()
        if str(symbol or "").strip()
    }
    subscribed_map = {
        str(symbol or "").upper(): max(0, int(count or 0))
        for symbol, count in dict(subscribed_by_symbol or {}).items()
        if str(symbol or "").strip()
    }
    required_symbols = sorted({sym for sym, count in {**requested_map, **subscribed_map}.items() if int(count or 0) > 0})
    if not required_symbols:
        with _RESTART_VERIFY_LOCK:
            _OPTION_FEED_VERIFY_STATE = "OK"
            _OPTION_FEED_VERIFY_REASON = f"{reason}:auto_ok_empty"
            _OPTION_FEED_VERIFY_START_EPOCH = start_epoch_f
            _OPTION_FEED_VERIFY_DEADLINE_EPOCH = 0.0
            _OPTION_FEED_VERIFY_REQUIRED_SYMBOLS = []
            _OPTION_FEED_VERIFY_REQUESTED_BY_SYMBOL = dict(requested_map)
            _OPTION_FEED_VERIFY_SUBSCRIBED_BY_SYMBOL = dict(subscribed_map)
            _OPTION_FEED_VERIFY_VERIFIED_SYMBOLS = []
            _OPTION_FEED_VERIFY_MISSING_SYMBOLS = []
            _OPTION_FEED_VERIFY_VERIFIED_EPOCH = start_epoch_f
            _OPTION_FEED_VERIFY_FAILURE_DETAIL = ""
            _OPTION_FEED_VERIFY_LAST_STAGE_EVENT = "auto_ok_empty"
        _log_ws("FEED_OPTION_VERIFY_AUTO_OK", {"reason": str(reason or "")})
        return
    deadline = start_epoch_f + float(_option_feed_verification_timeout_sec())
    with _RESTART_VERIFY_LOCK:
        _OPTION_FEED_VERIFY_STATE = "PENDING"
        _OPTION_FEED_VERIFY_REASON = str(reason or "")
        _OPTION_FEED_VERIFY_START_EPOCH = start_epoch_f
        _OPTION_FEED_VERIFY_DEADLINE_EPOCH = float(deadline)
        _OPTION_FEED_VERIFY_REQUIRED_SYMBOLS = list(required_symbols)
        _OPTION_FEED_VERIFY_REQUESTED_BY_SYMBOL = dict(requested_map)
        _OPTION_FEED_VERIFY_SUBSCRIBED_BY_SYMBOL = dict(subscribed_map)
        _OPTION_FEED_VERIFY_VERIFIED_SYMBOLS = []
        _OPTION_FEED_VERIFY_MISSING_SYMBOLS = list(required_symbols)
        _OPTION_FEED_VERIFY_VERIFIED_EPOCH = None
        _OPTION_FEED_VERIFY_FAILURE_DETAIL = ""
        _OPTION_FEED_VERIFY_LAST_STAGE_EVENT = ""
    _log_ws(
        "FEED_OPTION_VERIFY_BEGIN",
        {
            "reason": str(reason or ""),
            "required_symbols": list(required_symbols),
            "subscription_requested_by_symbol": dict(requested_map),
            "subscribed_option_tokens_count_by_symbol": dict(subscribed_map),
            "verify_deadline_epoch": float(deadline),
            "start_epoch": start_epoch_f,
        },
    )


def _option_feed_verification_overlay_payload() -> dict[str, object]:
    if not _option_feed_verification_enabled():
        return {}
    with _RESTART_VERIFY_LOCK:
        return {
            "state": str(_OPTION_FEED_VERIFY_STATE or "IDLE").strip().upper(),
            "reason": str(_OPTION_FEED_VERIFY_REASON or ""),
            "start_epoch": float(_OPTION_FEED_VERIFY_START_EPOCH or 0.0),
            "deadline_epoch": float(_OPTION_FEED_VERIFY_DEADLINE_EPOCH or 0.0),
            "required_symbols": list(_OPTION_FEED_VERIFY_REQUIRED_SYMBOLS or []),
            "subscription_requested_by_symbol": dict(_OPTION_FEED_VERIFY_REQUESTED_BY_SYMBOL or {}),
            "subscribed_option_tokens_count_by_symbol": dict(_OPTION_FEED_VERIFY_SUBSCRIBED_BY_SYMBOL or {}),
            "verified_symbols": list(_OPTION_FEED_VERIFY_VERIFIED_SYMBOLS or []),
            "missing_symbols": list(_OPTION_FEED_VERIFY_MISSING_SYMBOLS or []),
            "verified_epoch": _coerce_epoch(_OPTION_FEED_VERIFY_VERIFIED_EPOCH),
            "failure_detail": str(_OPTION_FEED_VERIFY_FAILURE_DETAIL or ""),
        }


def _tick_option_feed_verification(*, now_epoch: float) -> None:
    global _OPTION_FEED_VERIFY_STATE
    global _OPTION_FEED_VERIFY_VERIFIED_SYMBOLS
    global _OPTION_FEED_VERIFY_MISSING_SYMBOLS
    global _OPTION_FEED_VERIFY_VERIFIED_EPOCH
    global _OPTION_FEED_VERIFY_FAILURE_DETAIL
    global _OPTION_FEED_VERIFY_LAST_STAGE_EVENT
    if not _option_feed_verification_enabled():
        return
    now_epoch_f = float(now_epoch or 0.0)
    if now_epoch_f <= 0.0:
        now_epoch_f = float(now_utc_epoch())
    with _RESTART_VERIFY_LOCK:
        state = str(_OPTION_FEED_VERIFY_STATE or "IDLE").strip().upper()
        if state != "PENDING":
            return
        start_epoch = float(_OPTION_FEED_VERIFY_START_EPOCH or 0.0)
        deadline = float(_OPTION_FEED_VERIFY_DEADLINE_EPOCH or 0.0)
        reason = str(_OPTION_FEED_VERIFY_REASON or "")
        required_symbols = list(_OPTION_FEED_VERIFY_REQUIRED_SYMBOLS or [])
        subscribed_by_symbol = dict(_OPTION_FEED_VERIFY_SUBSCRIBED_BY_SYMBOL or {})
        requested_by_symbol = dict(_OPTION_FEED_VERIFY_REQUESTED_BY_SYMBOL or {})

    min_ticks = int(_option_feed_verification_min_ticks_per_symbol())
    ticks_by_symbol: dict[str, int] = {}
    verified_symbols: list[str] = []
    missing_symbols: list[str] = []
    for symbol in required_symbols:
        sym = str(symbol or "").upper()
        if not sym:
            continue
        subscribed_count = int(subscribed_by_symbol.get(sym, 0) or 0)
        requested_count = int(requested_by_symbol.get(sym, 0) or 0)
        if subscribed_count <= 0 and requested_count <= 0:
            continue
        last_tick_ts = _coerce_epoch(_SYMBOL_LAST_OPTION_TICK_TS.get(sym))
        if last_tick_ts is not None and last_tick_ts >= start_epoch:
            verified_symbols.append(sym)
            ticks_by_symbol[sym] = int(ticks_by_symbol.get(sym, 0)) + 1
        else:
            missing_symbols.append(sym)

    verified = bool(required_symbols and not missing_symbols and len(verified_symbols) >= min_ticks)
    stage_event = "FEED_OPTION_VERIFY_OK" if verified else "FEED_OPTION_VERIFY_WAITING_TICKS"
    if _OPTION_FEED_VERIFY_LAST_STAGE_EVENT != stage_event:
        with _RESTART_VERIFY_LOCK:
            if _OPTION_FEED_VERIFY_LAST_STAGE_EVENT != stage_event:
                _OPTION_FEED_VERIFY_LAST_STAGE_EVENT = stage_event
                payload = {
                    "reason": reason,
                    "required_symbols": required_symbols,
                    "subscribed_option_tokens_count_by_symbol": subscribed_by_symbol,
                    "subscription_requested_by_symbol": requested_by_symbol,
                    "ticks_by_symbol": ticks_by_symbol,
                    "missing_symbols": missing_symbols,
                    "elapsed_sec": max(0.0, float(now_epoch_f) - float(start_epoch)),
                }
                if verified:
                    payload["verified_symbols"] = verified_symbols
                    _log_ws(
                        "FEED_OPTION_VERIFY_OK",
                        {
                            **payload,
                            "verify_elapsed_sec": max(0.0, float(now_epoch_f) - float(start_epoch)),
                        },
                    )
                else:
                    _log_ws("FEED_OPTION_VERIFY_WAITING_TICKS", payload)

        if verified:
            with _RESTART_VERIFY_LOCK:
                if _OPTION_FEED_VERIFY_STATE == "PENDING":
                    _OPTION_FEED_VERIFY_STATE = "OK"
                    _OPTION_FEED_VERIFY_VERIFIED_EPOCH = float(now_epoch_f)
                    _OPTION_FEED_VERIFY_FAILURE_DETAIL = ""
                    _OPTION_FEED_VERIFY_MISSING_SYMBOLS = []
                    _OPTION_FEED_VERIFY_VERIFIED_SYMBOLS = list(sorted(set(verified_symbols)))
            try:
                _FEED_RECOVERY_COORDINATOR.clear_recovery(
                    source="option_feed_verification_ok",
                    reason=reason,
                )
            except Exception:
                pass
            _sync_ws1006_recovery_state_from_coordinator()
            return

    if deadline > 0.0 and now_epoch_f >= deadline:
        failure_reason = "NO_LIVE_OPTION_FEED_AFTER_SUBSCRIBE" if missing_symbols else "OPTION_FEED_VERIFY_TIMEOUT"
        with _RESTART_VERIFY_LOCK:
            if _OPTION_FEED_VERIFY_STATE == "PENDING":
                _OPTION_FEED_VERIFY_STATE = "FAILED"
                _OPTION_FEED_VERIFY_FAILURE_DETAIL = failure_reason
                _OPTION_FEED_VERIFY_MISSING_SYMBOLS = list(sorted(set(missing_symbols or required_symbols)))
        _log_ws(
            "FEED_OPTION_VERIFY_FAILED",
            {
                "reason": failure_reason,
                "required_symbols": required_symbols,
                "missing_symbols": list(sorted(set(missing_symbols or required_symbols))),
                "ticks_by_symbol": ticks_by_symbol,
                "subscription_requested_by_symbol": requested_by_symbol,
                "subscribed_option_tokens_count_by_symbol": subscribed_by_symbol,
                "ws_connected": _ws_connected_state(),
                "runtime_state": str(_RUNTIME_STATE or "").strip().upper(),
                "verify_elapsed_sec": max(0.0, float(now_epoch_f) - float(start_epoch)),
            },
        )


def _begin_feed_restart_verification(*, reason: str, start_epoch: float, now_epoch: float) -> None:
    global _FEED_RESTART_VERIFY_STATE
    global _FEED_RESTART_VERIFY_REASON
    global _FEED_RESTART_VERIFY_START_EPOCH
    global _FEED_RESTART_VERIFY_DEADLINE_EPOCH
    global _FEED_RESTART_VERIFY_CONNECT_EPOCH
    global _FEED_RESTART_VERIFY_SUBSCRIBE_EPOCH
    global _FEED_RESTART_VERIFY_VERIFIED_EPOCH
    global _FEED_RESTART_VERIFY_FAILURE_DETAIL
    global _FEED_RESTART_VERIFY_LAST_STAGE_EVENT
    if not _restart_verification_enabled():
        return
    if _restart_verification_require_market_open() and not bool(is_market_open_ist()):
        return
    start_epoch_f = float(start_epoch or 0.0)
    now_epoch_f = float(now_epoch or 0.0)
    if start_epoch_f <= 0.0:
        start_epoch_f = now_epoch_f if now_epoch_f > 0.0 else float(now_utc_epoch())
    if now_epoch_f <= 0.0:
        now_epoch_f = float(now_utc_epoch())
    deadline = now_epoch_f + float(_restart_verification_timeout_sec())
    with _RESTART_VERIFY_LOCK:
        _FEED_RESTART_VERIFY_STATE = "PENDING"
        _FEED_RESTART_VERIFY_REASON = str(reason or "")
        _FEED_RESTART_VERIFY_START_EPOCH = start_epoch_f
        _FEED_RESTART_VERIFY_DEADLINE_EPOCH = float(deadline)
        _FEED_RESTART_VERIFY_CONNECT_EPOCH = None
        _FEED_RESTART_VERIFY_SUBSCRIBE_EPOCH = None
        _FEED_RESTART_VERIFY_VERIFIED_EPOCH = None
        _FEED_RESTART_VERIFY_FAILURE_DETAIL = ""
        _FEED_RESTART_VERIFY_LAST_STAGE_EVENT = ""
    _log_ws(
        "FEED_RESTART_VERIFY_BEGIN",
        {
            "reason": str(reason or ""),
            "start_epoch": start_epoch_f,
            "deadline_epoch": float(deadline),
            "timeout_sec": float(_restart_verification_timeout_sec()),
        },
    )


def _record_feed_restart_verify_connect(*, now_epoch: float) -> None:
    global _FEED_RESTART_VERIFY_CONNECT_EPOCH
    if not _restart_verification_enabled():
        return
    with _RESTART_VERIFY_LOCK:
        if _FEED_RESTART_VERIFY_STATE != "PENDING":
            return
        if _FEED_RESTART_VERIFY_CONNECT_EPOCH is not None:
            return
        _FEED_RESTART_VERIFY_CONNECT_EPOCH = float(now_epoch)


def _record_feed_restart_verify_subscribe(*, now_epoch: float) -> None:
    global _FEED_RESTART_VERIFY_SUBSCRIBE_EPOCH
    if not _restart_verification_enabled():
        return
    with _RESTART_VERIFY_LOCK:
        if _FEED_RESTART_VERIFY_STATE != "PENDING":
            return
        if _FEED_RESTART_VERIFY_SUBSCRIBE_EPOCH is not None:
            return
        _FEED_RESTART_VERIFY_SUBSCRIBE_EPOCH = float(now_epoch)


def _restart_verify_stage_event(stage: str) -> str:
    text = str(stage or "").strip().upper()
    return f"FEED_RESTART_VERIFY_{text}" if text else "FEED_RESTART_VERIFY"


def _restart_verify_should_block_runtime_state(state: str) -> bool:
    return str(state or "").strip().upper() in {"PENDING", "FAILED"}


def _restart_verification_proof(now_epoch: float) -> tuple[bool, str, dict[str, object]]:
    ws_connected = _ws_connected_state()
    option_state = _option_runtime_state(
        now_epoch=float(now_epoch),
        tokens=_LAST_TOKENS,
        expected_counts_by_symbol=_LAST_OPTION_COUNTS_BY_SYMBOL,
        min_required_by_symbol=_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL,
        ws_connected=ws_connected,
    )
    subscribed_by_symbol = dict(option_state.get("subscribed_count_by_symbol") or {})
    ticks_by_symbol = dict(option_state.get("ticks_received_count_by_symbol") or {})
    block_reason_by_symbol = dict(option_state.get("feed_block_reason_by_symbol") or {})
    total_option_tokens = int(option_state.get("option_count") or 0)

    required_symbols = [
        str(sym or "").upper()
        for sym, min_required in dict(_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL or {}).items()
        if str(sym or "").strip() and int(min_required or 0) > 0
    ]
    required_symbols = sorted(set(sym for sym in required_symbols if sym))
    if not required_symbols:
        required_symbols = sorted(set(str(sym or "").upper() for sym in subscribed_by_symbol.keys() if str(sym or "").strip()))

    min_ticks = int(_restart_verification_min_option_ticks_per_symbol())

    if _restart_verification_require_options() and total_option_tokens <= 0:
        return False, "no_subscribed_option_tokens", {
            "required_symbols": required_symbols,
            "subscribed_option_tokens_count": total_option_tokens,
        }

    for sym in required_symbols:
        subscribed_count = int(subscribed_by_symbol.get(sym, 0) or 0)
        if subscribed_count <= 0:
            return False, f"missing_option_subscriptions:{sym}", {
                "required_symbols": required_symbols,
                "subscribed_by_symbol": subscribed_by_symbol,
                "ticks_by_symbol": ticks_by_symbol,
                "block_reason_by_symbol": block_reason_by_symbol,
            }
        ticks_received = int(ticks_by_symbol.get(sym, 0) or 0)
        if ticks_received < min_ticks:
            return False, f"insufficient_option_ticks:{sym}", {
                "required_symbols": required_symbols,
                "min_ticks_per_symbol": min_ticks,
                "subscribed_by_symbol": subscribed_by_symbol,
                "ticks_by_symbol": ticks_by_symbol,
                "block_reason_by_symbol": block_reason_by_symbol,
            }
        block_reason = str(block_reason_by_symbol.get(sym, "OK") or "OK").strip().upper()
        if block_reason not in _RESTART_VERIFY_OPTION_OK_CODES:
            return False, f"feed_blocked:{sym}:{block_reason}", {
                "required_symbols": required_symbols,
                "min_ticks_per_symbol": min_ticks,
                "subscribed_by_symbol": subscribed_by_symbol,
                "ticks_by_symbol": ticks_by_symbol,
                "block_reason_by_symbol": block_reason_by_symbol,
            }

    return True, "ok", {
        "required_symbols": required_symbols,
        "min_ticks_per_symbol": min_ticks,
        "subscribed_by_symbol": subscribed_by_symbol,
        "ticks_by_symbol": ticks_by_symbol,
        "block_reason_by_symbol": block_reason_by_symbol,
        "ws_connected": ws_connected,
    }


def _restart_verification_live_recovery_proof(now_epoch: float) -> tuple[bool, str, dict[str, object]]:
    ws_connected = _ws_connected_state()
    option_state = _option_runtime_state(
        now_epoch=float(now_epoch),
        tokens=_LAST_TOKENS,
        expected_counts_by_symbol=_LAST_OPTION_COUNTS_BY_SYMBOL,
        min_required_by_symbol=_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL,
        ws_connected=ws_connected,
    )
    subscribed_by_symbol = dict(option_state.get("subscribed_count_by_symbol") or {})
    ticks_by_symbol = dict(option_state.get("ticks_received_count_by_symbol") or {})
    block_reason_by_symbol = dict(option_state.get("feed_block_reason_by_symbol") or {})
    total_option_tokens = int(option_state.get("option_count") or 0)
    last_ws_tick_epoch = float(_LAST_WS_TICK_EPOCH or 0.0)
    last_ws_tick_age_sec = max(0.0, float(now_epoch) - last_ws_tick_epoch) if last_ws_tick_epoch > 0.0 else None
    max_ws_tick_age_sec = float(getattr(cfg, "MAX_DEPTH_AGE_SEC", 5.0))

    required_symbols = [
        str(sym or "").upper()
        for sym, min_required in dict(_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL or {}).items()
        if str(sym or "").strip() and int(min_required or 0) > 0
    ]
    required_symbols = sorted(set(sym for sym in required_symbols if sym))
    if not required_symbols:
        required_symbols = sorted(set(str(sym or "").upper() for sym in subscribed_by_symbol.keys() if str(sym or "").strip()))

    if not ws_connected:
        return False, "ws_disconnected", {"required_symbols": required_symbols, "ws_connected": ws_connected}
    if total_option_tokens <= 0:
        return False, "no_subscribed_option_tokens", {
            "required_symbols": required_symbols,
            "subscribed_option_tokens_count": total_option_tokens,
        }
    if last_ws_tick_age_sec is None or last_ws_tick_age_sec > max_ws_tick_age_sec:
        return False, f"ws_tick_stale:{last_ws_tick_age_sec!s}", {
            "required_symbols": required_symbols,
            "last_ws_tick_age_sec": last_ws_tick_age_sec,
            "max_ws_tick_age_sec": max_ws_tick_age_sec,
        }

    min_ticks = int(_restart_verification_min_option_ticks_per_symbol())
    for sym in required_symbols:
        subscribed_count = int(subscribed_by_symbol.get(sym, 0) or 0)
        if subscribed_count <= 0:
            return False, f"missing_option_subscriptions:{sym}", {
                "required_symbols": required_symbols,
                "subscribed_by_symbol": subscribed_by_symbol,
                "ticks_by_symbol": ticks_by_symbol,
                "block_reason_by_symbol": block_reason_by_symbol,
            }
        ticks_received = int(ticks_by_symbol.get(sym, 0) or 0)
        if ticks_received < min_ticks:
            return False, f"insufficient_option_ticks:{sym}", {
                "required_symbols": required_symbols,
                "min_ticks_per_symbol": min_ticks,
                "subscribed_by_symbol": subscribed_by_symbol,
                "ticks_by_symbol": ticks_by_symbol,
                "block_reason_by_symbol": block_reason_by_symbol,
            }
        block_reason = str(block_reason_by_symbol.get(sym, "OK") or "OK").strip().upper()
        if block_reason not in _RESTART_VERIFY_OPTION_OK_CODES:
            return False, f"feed_blocked:{sym}:{block_reason}", {
                "required_symbols": required_symbols,
                "min_ticks_per_symbol": min_ticks,
                "subscribed_by_symbol": subscribed_by_symbol,
                "ticks_by_symbol": ticks_by_symbol,
                "block_reason_by_symbol": block_reason_by_symbol,
            }

    return True, "live_recovery_ok", {
        "required_symbols": required_symbols,
        "min_ticks_per_symbol": min_ticks,
        "subscribed_by_symbol": subscribed_by_symbol,
        "ticks_by_symbol": ticks_by_symbol,
        "block_reason_by_symbol": block_reason_by_symbol,
        "ws_connected": ws_connected,
        "last_ws_tick_age_sec": last_ws_tick_age_sec,
    }


def _tick_feed_restart_verification(*, now_epoch: float) -> None:
    global _FEED_RESTART_VERIFY_STATE
    global _FEED_RESTART_VERIFY_FAILURE_DETAIL
    global _FEED_RESTART_VERIFY_VERIFIED_EPOCH
    global _FEED_RESTART_VERIFY_LAST_STAGE_EVENT
    if not _restart_verification_enabled():
        return

    now_epoch_f = float(now_epoch or 0.0)
    if now_epoch_f <= 0.0:
        now_epoch_f = float(now_utc_epoch())

    with _RESTART_VERIFY_LOCK:
        state = str(_FEED_RESTART_VERIFY_STATE or "IDLE").strip().upper()
        if state not in {"PENDING", "FAILED"}:
            return
        start_epoch = float(_FEED_RESTART_VERIFY_START_EPOCH or 0.0)
        deadline = float(_FEED_RESTART_VERIFY_DEADLINE_EPOCH or 0.0)
        connect_epoch = _FEED_RESTART_VERIFY_CONNECT_EPOCH
        subscribe_epoch = _FEED_RESTART_VERIFY_SUBSCRIBE_EPOCH
        reason = str(_FEED_RESTART_VERIFY_REASON or "")

    stage = "WAITING_CONNECT"
    if connect_epoch is not None and float(connect_epoch) >= start_epoch:
        stage = "WAITING_SUBSCRIBE"
    if subscribe_epoch is not None and float(subscribe_epoch) >= start_epoch:
        stage = "WAITING_OPTION_TICKS"
    if state == "FAILED":
        stage = f"RECHECK_{stage}"

    stage_event = _restart_verify_stage_event(stage)
    with _RESTART_VERIFY_LOCK:
        if _FEED_RESTART_VERIFY_LAST_STAGE_EVENT != stage_event:
            _FEED_RESTART_VERIFY_LAST_STAGE_EVENT = stage_event
            _log_ws(
                stage_event,
                {
                    "reason": reason,
                    "start_epoch": start_epoch,
                    "deadline_epoch": deadline,
                    "now_epoch": now_epoch_f,
                    "connect_epoch": connect_epoch,
                    "subscribe_epoch": subscribe_epoch,
                },
            )

    verified = False
    verify_detail = "unknown"
    verify_meta: dict[str, object] = {}
    if state == "FAILED":
        try:
            verified, verify_detail, verify_meta = _restart_verification_live_recovery_proof(now_epoch_f)
        except Exception as exc:
            verified = False
            verify_detail = f"live_recovery_exception:{type(exc).__name__}:{exc}"
    elif subscribe_epoch is not None and float(subscribe_epoch) >= start_epoch:
        try:
            verified, verify_detail, verify_meta = _restart_verification_proof(now_epoch_f)
        except Exception as exc:
            verified = False
            verify_detail = f"proof_exception:{type(exc).__name__}:{exc}"

    if verified:
        with _RESTART_VERIFY_LOCK:
            if _FEED_RESTART_VERIFY_STATE in {"PENDING", "FAILED"}:
                _FEED_RESTART_VERIFY_STATE = "OK"
                _FEED_RESTART_VERIFY_VERIFIED_EPOCH = float(now_epoch_f)
                _FEED_RESTART_VERIFY_FAILURE_DETAIL = ""
        _log_ws("subscription_replay_verified", {"reason": "verified"})
        if _reconnect_recovery_blocked_active():
            cleared_reason = str(_RECONNECT_BLOCKED_REASON or "").strip().lower() or "recovery_blocked"
            _clear_reconnect_blocked_reason()
            _clear_last_disconnected_info()
            _log_ws(
                "FEED_RECONNECT_RECOVERY_CLEARED",
                {
                    "reason": reason,
                    "cleared_reason": cleared_reason,
                    "verified_epoch": float(now_epoch_f),
                },
            )
        _log_ws(
            "FEED_RESTART_VERIFIED_OK",
            {
                "reason": reason,
                "start_epoch": start_epoch,
                "verified_epoch": float(now_epoch_f),
                "connect_epoch": connect_epoch,
                "subscribe_epoch": subscribe_epoch,
                "meta": verify_meta,
            },
        )
        return

    if state == "FAILED":
        return

    if deadline > 0.0 and now_epoch_f >= deadline:
        with _RESTART_VERIFY_LOCK:
            if _FEED_RESTART_VERIFY_STATE == "PENDING":
                _FEED_RESTART_VERIFY_STATE = "FAILED"
                _FEED_RESTART_VERIFY_FAILURE_DETAIL = str(verify_detail or "timeout")
        _log_ws(
            "FEED_RESTART_VERIFY_FAILED",
            {
                "reason": reason,
                "start_epoch": start_epoch,
                "deadline_epoch": deadline,
                "now_epoch": now_epoch_f,
                "connect_epoch": connect_epoch,
                "subscribe_epoch": subscribe_epoch,
                "detail": str(verify_detail or "timeout"),
                "meta": verify_meta,
            },
        )


def _restart_verify_overlay_payload() -> dict[str, object]:
    if not _restart_verification_enabled():
        return {}
    with _RESTART_VERIFY_LOCK:
        return {
            "state": str(_FEED_RESTART_VERIFY_STATE or "IDLE").strip().upper(),
            "reason": str(_FEED_RESTART_VERIFY_REASON or ""),
            "start_epoch": float(_FEED_RESTART_VERIFY_START_EPOCH or 0.0),
            "deadline_epoch": float(_FEED_RESTART_VERIFY_DEADLINE_EPOCH or 0.0),
            "connect_epoch": _coerce_epoch(_FEED_RESTART_VERIFY_CONNECT_EPOCH),
            "subscribe_epoch": _coerce_epoch(_FEED_RESTART_VERIFY_SUBSCRIBE_EPOCH),
            "verified_epoch": _coerce_epoch(_FEED_RESTART_VERIFY_VERIFIED_EPOCH),
            "failure_detail": str(_FEED_RESTART_VERIFY_FAILURE_DETAIL or ""),
        }


def _effective_runtime_state_for_snapshot(runtime_state: str, *, now_epoch: float) -> tuple[str, str | None]:
    """Return (effective_runtime_state, failure_detail_override_or_none)."""
    global _FEED_RESTART_VERIFY_STATE
    global _FEED_RESTART_VERIFY_VERIFIED_EPOCH
    global _FEED_RESTART_VERIFY_FAILURE_DETAIL
    runtime_state_text = str(runtime_state or "").strip().upper()
    if runtime_state_text in {"RECOVERY_BLOCKED", "AUTH_BLOCKED", "IMPORT_MISSING"}:
        return runtime_state_text, None
    if not _restart_verification_enabled():
        return runtime_state, None
    _tick_feed_restart_verification(now_epoch=float(now_epoch))
    with _RESTART_VERIFY_LOCK:
        state = str(_FEED_RESTART_VERIFY_STATE or "IDLE").strip().upper()
        detail = str(_FEED_RESTART_VERIFY_FAILURE_DETAIL or "").strip()
    if state == "PENDING":
        return "RESTART_VERIFY_PENDING", None
    if state == "FAILED":
        try:
            recovered, recover_detail, recover_meta = _restart_verification_live_recovery_proof(float(now_epoch))
        except Exception as exc:
            recovered = False
            recover_detail = f"live_recovery_exception:{type(exc).__name__}:{exc}"
            recover_meta = {}
        if recovered:
            with _RESTART_VERIFY_LOCK:
                if _FEED_RESTART_VERIFY_STATE in {"PENDING", "FAILED"}:
                    _FEED_RESTART_VERIFY_STATE = "OK"
                    _FEED_RESTART_VERIFY_VERIFIED_EPOCH = float(now_epoch)
                    _FEED_RESTART_VERIFY_FAILURE_DETAIL = ""
            _log_ws(
                "FEED_RESTART_VERIFIED_OK",
                {
                    "reason": "failed_state_live_recovery",
                    "start_epoch": float(_FEED_RESTART_VERIFY_START_EPOCH or 0.0),
                    "verified_epoch": float(now_epoch),
                    "connect_epoch": _coerce_epoch(_FEED_RESTART_VERIFY_CONNECT_EPOCH),
                    "subscribe_epoch": _coerce_epoch(_FEED_RESTART_VERIFY_SUBSCRIBE_EPOCH),
                    "meta": recover_meta,
                },
            )
            return runtime_state, None
        return "RESTART_VERIFY_FAILED", (detail or "restart_verification_failed")
    return runtime_state, None


def _subscribed_tokens_count_by_symbol(tokens: list[int] | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tok in list(tokens or []):
        try:
            tok_int = int(tok)
        except Exception:
            continue
        symbol = str(_TOKEN_TO_SYMBOL.get(tok_int) or "").upper()
        if not symbol or symbol == "STICKY":
            continue
        counts[symbol] = int(counts.get(symbol, 0)) + 1
    return counts


def _missing_option_tokens_stats() -> tuple[int, dict[str, int]]:
    missing_by_symbol: dict[str, int] = {}
    total_missing = 0
    for symbol, min_required in dict(_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL).items():
        sym = str(symbol or "").upper()
        if not sym:
            continue
        try:
            required = max(0, int(min_required))
        except Exception:
            required = 0
        try:
            resolved = max(0, int((_LAST_OPTION_COUNTS_BY_SYMBOL or {}).get(sym, 0)))
        except Exception:
            resolved = 0
        missing = max(0, required - resolved)
        if missing <= 0:
            continue
        missing_by_symbol[sym] = int(missing)
        total_missing += int(missing)
    return int(total_missing), missing_by_symbol


def _subscribed_option_token_stats(
    *, now_epoch: float, tokens: list[int] | None, sample_limit: int = 10
) -> tuple[int, dict[str, float | None], list[dict[str, float | int | str | None]]]:
    option_count = 0
    latest_tick_ts_by_symbol: dict[str, float | None] = {}
    age_by_symbol: dict[str, float | None] = {}
    sample_rows: list[dict[str, float | int | str | None]] = []
    for tok in list(tokens or []):
        try:
            tok_int = int(tok)
        except Exception:
            continue
        if _is_underlying_token(tok_int):
            continue
        symbol = str(_TOKEN_TO_SYMBOL.get(tok_int) or "").upper()
        if not symbol or symbol == "STICKY":
            continue
        option_count += 1
        last_epoch = _coerce_epoch(_LAST_MSG_TS_BY_TOKEN.get(tok_int))
        age_sec = None if last_epoch is None else max(0.0, float(now_epoch) - float(last_epoch))
        prev_ts = latest_tick_ts_by_symbol.get(symbol)
        if prev_ts is None or (last_epoch is not None and float(last_epoch) > float(prev_ts)):
            latest_tick_ts_by_symbol[symbol] = last_epoch
        sample_rows.append(
            {
                "token": tok_int,
                "symbol": symbol,
                "last_tick_epoch": last_epoch,
                "tick_age_sec": age_sec,
            }
        )
    sample_rows.sort(key=lambda row: float(row.get("tick_age_sec") or -1.0), reverse=True)
    for symbol, last_tick_ts in dict(_SYMBOL_LAST_OPTION_TICK_TS or {}).items():
        sym = str(symbol or "").upper()
        if not sym:
            continue
        last_epoch = _coerce_epoch(last_tick_ts)
        prev_ts = latest_tick_ts_by_symbol.get(sym)
        if prev_ts is None or (last_epoch is not None and float(last_epoch) > float(prev_ts)):
            latest_tick_ts_by_symbol[sym] = last_epoch
    for symbol, last_tick_ts in list(latest_tick_ts_by_symbol.items()):
        last_epoch = _coerce_epoch(last_tick_ts)
        age_by_symbol[symbol] = None if last_epoch is None else max(0.0, float(now_epoch) - float(last_epoch))
    return int(option_count), dict(age_by_symbol), sample_rows[: max(1, int(sample_limit))]


def _option_runtime_state(
    *,
    now_epoch: float,
    tokens: list[int] | None,
    expected_counts_by_symbol: dict[str, int] | None = None,
    min_required_by_symbol: dict[str, int] | None = None,
    ws_connected: bool | None = None,
    sample_limit: int = 10,
) -> dict[str, object]:
    subscribed_count_by_symbol: dict[str, int] = {}
    ticks_received_count_by_symbol: dict[str, int] = {}
    last_tick_ts_by_symbol: dict[str, float | None] = {}
    option_age_by_symbol: dict[str, float | None] = {}
    sample_rows: list[dict[str, float | int | str | None]] = []
    option_count = 0
    for tok in list(tokens or []):
        try:
            tok_int = int(tok)
        except Exception:
            continue
        if _is_underlying_token(tok_int):
            continue
        symbol = str(_TOKEN_TO_SYMBOL.get(tok_int) or "").upper()
        if not symbol or symbol == "STICKY":
            continue
        option_count += 1
        subscribed_count_by_symbol[symbol] = int(subscribed_count_by_symbol.get(symbol, 0)) + 1
        last_epoch = _coerce_epoch(_LAST_MSG_TS_BY_TOKEN.get(tok_int))
        age_sec = None if last_epoch is None else max(0.0, float(now_epoch) - float(last_epoch))
        prev_ts = last_tick_ts_by_symbol.get(symbol)
        if prev_ts is None or (last_epoch is not None and float(last_epoch) > float(prev_ts)):
            last_tick_ts_by_symbol[symbol] = last_epoch
        if last_epoch is not None:
            ticks_received_count_by_symbol[symbol] = int(ticks_received_count_by_symbol.get(symbol, 0)) + 1
        sample_rows.append(
            {
                "token": tok_int,
                "symbol": symbol,
                "last_tick_epoch": last_epoch,
                "tick_age_sec": age_sec,
            }
        )
    sample_rows.sort(key=lambda row: float(row.get("tick_age_sec") or -1.0), reverse=True)
    for symbol, last_tick_ts in dict(_SYMBOL_LAST_OPTION_TICK_TS or {}).items():
        sym = str(symbol or "").upper()
        if not sym:
            continue
        last_epoch = _coerce_epoch(last_tick_ts)
        prev_ts = last_tick_ts_by_symbol.get(sym)
        if prev_ts is None or (last_epoch is not None and float(last_epoch) > float(prev_ts)):
            last_tick_ts_by_symbol[sym] = last_epoch
    for symbol, last_tick_ts in list(last_tick_ts_by_symbol.items()):
        last_epoch = _coerce_epoch(last_tick_ts)
        option_age_by_symbol[symbol] = (
            None if last_epoch is None else max(0.0, float(now_epoch) - float(last_epoch))
        )
    option_sla_sec = float(getattr(cfg, "OPTION_LTP_SLA_SEC", 2.0))
    feed_block_reason_by_symbol: dict[str, str] = {}
    active_blockers_by_symbol: dict[str, list[str]] = {}
    blocker_records_by_symbol: dict[str, list[dict[str, object]]] = {}
    tracked_symbols = (
        set(str(k).upper() for k in dict(expected_counts_by_symbol or {}).keys())
        | set(str(k).upper() for k in subscribed_count_by_symbol.keys())
    )
    registry = get_blocker_registry("feed")
    valid_owner_keys: set[str] = set()
    for symbol in sorted(sym for sym in tracked_symbols if sym):
        owner_key = build_feed_owner_key(symbol)
        valid_owner_keys.add(owner_key)
        expected_count = max(0, int((expected_counts_by_symbol or {}).get(symbol, 0) or 0))
        subscribed_count = max(0, int(subscribed_count_by_symbol.get(symbol, 0) or 0))
        last_tick_ts = _coerce_epoch(last_tick_ts_by_symbol.get(symbol))
        age_sec = option_age_by_symbol.get(symbol)
        min_required = max(0, int((min_required_by_symbol or {}).get(symbol, 0) or 0))
        if expected_count <= 0 and min_required <= 0 and subscribed_count <= 0:
            continue
        active_records = evaluate_feed_symbol_blockers(
            registry,
            now_ts=float(now_epoch),
            symbol=symbol,
            ws_connected=ws_connected,
            expected_option_count=expected_count,
            subscribed_option_count=subscribed_count,
            option_ticks_received_count=int(ticks_received_count_by_symbol.get(symbol, 0) or 0),
            latest_option_tick_ts=last_tick_ts,
            latest_option_tick_age_sec=age_sec,
            feed_freshness_sec=option_sla_sec,
            min_required_count=min_required,
        )
        active_codes = [str(record.code) for record in active_records]
        active_blockers_by_symbol[symbol] = active_codes
        blocker_records_by_symbol[symbol] = [record.to_payload() for record in active_records]
        top_code = top_active_code(active_records)
        if top_code:
            feed_block_reason_by_symbol[symbol] = top_code
        elif age_sec is None or float(age_sec) > float(option_sla_sec):
            feed_block_reason_by_symbol[symbol] = "NO_LIVE_OPTION_FEED"
            if "NO_LIVE_OPTION_FEED" not in active_blockers_by_symbol[symbol]:
                active_blockers_by_symbol[symbol].append("NO_LIVE_OPTION_FEED")
        else:
            feed_block_reason_by_symbol[symbol] = "OK"
        if age_sec is not None and float(age_sec) > float(option_sla_sec):
            if "STALE_OPTION_LTP" not in active_blockers_by_symbol[symbol]:
                active_blockers_by_symbol[symbol].append("STALE_OPTION_LTP")
            if feed_block_reason_by_symbol[symbol] == "OK":
                feed_block_reason_by_symbol[symbol] = "STALE_OPTION_LTP"
    registry.prune_invalid_owners(now_ts=float(now_epoch), scope="feed_symbol", valid_owner_keys=valid_owner_keys)
    registry.expire_stale(float(now_epoch), scope="feed_symbol")
    return {
        "option_count": int(option_count),
        "option_age_by_symbol": option_age_by_symbol,
        "sample_rows": sample_rows[: max(1, int(sample_limit))],
        "subscribed_count_by_symbol": subscribed_count_by_symbol,
        "ticks_received_count_by_symbol": ticks_received_count_by_symbol,
        "last_tick_ts_by_symbol": last_tick_ts_by_symbol,
        "feed_block_reason_by_symbol": feed_block_reason_by_symbol,
        "active_blockers_by_symbol": active_blockers_by_symbol,
        "blocker_records_by_symbol": blocker_records_by_symbol,
    }


def _feed_health_duration_artifact_path() -> Path:
    return logs_dir() / "feed_health_duration_latest.json"


def _write_feed_health_duration_artifact(snapshot: dict[str, object]) -> dict[str, object] | None:
    global _FEED_HEALTH_DURATION_STATE
    if not bool(getattr(cfg, "FEED_HEALTH_DURATION_ARTIFACT_ENABLE", True)):
        return None
    target = _feed_health_duration_artifact_path()
    previous = _FEED_HEALTH_DURATION_STATE
    if previous is None and target.exists():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
            previous = loaded if isinstance(loaded, dict) else None
        except Exception:
            previous = None
    artifact = build_feed_health_duration_artifact(
        dict(snapshot or {}),
        previous=previous,
        target_window_sec=float(getattr(cfg, "FEED_HEALTH_DURATION_TARGET_SEC", 3600.0)),
    )
    try:
        write_json_atomic(target, artifact)
        _FEED_HEALTH_DURATION_STATE = artifact
    except Exception as exc:
        _log_ws("FEED_HEALTH_DURATION_WRITE_ERROR", {"error": str(exc), "path": str(target)})
    return artifact


def _write_feed_runtime_snapshot(
    *,
    now_epoch: float,
    ws_connected: bool | None,
    subscribed_tokens_count: int,
    intended_tokens_count: int,
    subscribed_tokens_count_by_symbol: dict[str, int] | None = None,
    missing_option_tokens_count: int | None = None,
    missing_option_tokens_count_by_symbol: dict[str, int] | None = None,
    last_db_tick_epoch: float | None,
    last_db_tick_age_sec: float | None,
    last_ws_tick_epoch: float | None,
    last_tick_age_sec: float | None,
    last_depth_epoch: float | None,
    last_depth_age_sec: float | None,
    market_open: bool,
    state_machine: dict | None = None,
    subscribed_option_tokens_count: int | None = None,
    option_last_tick_age_by_symbol: dict[str, float | None] | None = None,
    option_last_tick_sample: list[dict] | None = None,
    option_tokens_resolved_count_by_symbol: dict[str, int] | None = None,
    option_tokens_subscribed_count_by_symbol: dict[str, int] | None = None,
    option_ticks_received_count_by_symbol: dict[str, int] | None = None,
    last_option_tick_ts_by_symbol: dict[str, float | None] | None = None,
    option_feed_block_reason_by_symbol: dict[str, str] | None = None,
    option_active_blockers_by_symbol: dict[str, list[str]] | None = None,
    restart_count_1h: int = 0,
    stale_strikes: int = 0,
    runtime_state: str | None = None,
    last_error: str | None = None,
    disconnected_code: int | None = None,
    disconnected_reason: str | None = None,
    reconnect_blocked_reason: str | None = None,
    restart_attempt_allowed: bool | None = None,
    restart_attempted: bool | None = None,
    restart_blocked_reason: str | None = None,
    internal_retry_disabled: bool | None = None,
    stop_retry_called: bool | None = None,
    factory_stop_trying_called: bool | None = None,
    auto_reconnect_disabled: bool | None = None,
    internal_retry_error: str | None = None,
    internal_retry_reason: str | None = None,
) -> None:
    global _FEED_RUNTIME_SNAPSHOT_WRITE_COUNT
    _FEED_RUNTIME_SNAPSHOT_WRITE_COUNT += 1
    stage_timing_enabled = bool(getattr(cfg, "FEED_RUNTIME_STAGE_TIMING_ENABLE", True))
    stage_total_start = time.perf_counter()
    stage_timing_ms: dict[str, float] = {}

    def _mark_stage(name: str, started_at: float) -> float:
        now_perf = time.perf_counter()
        if stage_timing_enabled:
            stage_timing_ms[name] = round(max(0.0, now_perf - float(started_at)) * 1000.0, 3)
        return now_perf

    path = logs_dir() / "feed_runtime_latest.json"
    stage_started = time.perf_counter()
    raw_state_text = str(runtime_state or _RUNTIME_STATE or "UNKNOWN").strip().upper()
    effective_state_text, restart_verify_failure = _effective_runtime_state_for_snapshot(
        raw_state_text,
        now_epoch=float(now_epoch),
    )
    restart_verify = _restart_verify_overlay_payload()
    stage_started = _mark_stage("restart_verification_ms", stage_started)
    effective_state_text, normalized_state_machine, ws_connected, normalized_blocked_reason = _normalize_recovery_blocked_snapshot_state(
        runtime_state=effective_state_text,
        state_machine=state_machine,
        reconnect_blocked_reason=reconnect_blocked_reason,
        ws_connected=ws_connected,
    )
    stage_started = _mark_stage("recovery_state_normalization_ms", stage_started)
    disconnected_code_value = disconnected_code if disconnected_code is not None else _LAST_DISCONNECTED_CODE
    disconnected_reason_value = disconnected_reason if disconnected_reason is not None else _LAST_DISCONNECTED_REASON
    if (
        not normalized_blocked_reason
        and effective_state_text == "RUNNING"
        and (disconnected_code_value is not None or str(disconnected_reason_value or "").strip())
    ):
        effective_state_text = "RESTARTING"
    if (
        not normalized_blocked_reason
        and effective_state_text == "RESTARTING"
        and (disconnected_code_value is not None or str(disconnected_reason_value or "").strip())
    ):
        ws_connected = False
    payload = {
        "ts_epoch": float(now_epoch),
        "ws_connected": ws_connected,
        "subscribed_tokens_count": int(subscribed_tokens_count),
        "intended_tokens_count": int(intended_tokens_count),
        "subscribed_tokens_count_by_symbol": dict(subscribed_tokens_count_by_symbol or {}),
        "missing_option_tokens_count": int(missing_option_tokens_count or 0),
        "missing_option_tokens_count_by_symbol": dict(missing_option_tokens_count_by_symbol or {}),
        "last_db_tick_epoch": _coerce_epoch(last_db_tick_epoch),
        "last_db_tick_age_sec": _safe_float(last_db_tick_age_sec),
        "last_ws_tick_epoch": _coerce_epoch(last_ws_tick_epoch),
        "last_tick_age_sec": _safe_float(last_tick_age_sec),
        "last_depth_epoch": _coerce_epoch(last_depth_epoch),
        "last_depth_age_sec": _safe_float(last_depth_age_sec),
        "market_open": bool(market_open),
        "state_machine": normalized_state_machine,
        "subscribed_option_tokens_count": int(subscribed_option_tokens_count or 0),
        "option_last_tick_age_by_symbol": dict(option_last_tick_age_by_symbol or {}),
        "option_last_tick_sample": list(option_last_tick_sample or []),
        "option_tokens_resolved_count_by_symbol": dict(option_tokens_resolved_count_by_symbol or {}),
        "option_tokens_subscribed_count_by_symbol": dict(option_tokens_subscribed_count_by_symbol or {}),
        "option_ticks_received_count_by_symbol": dict(option_ticks_received_count_by_symbol or {}),
        "last_option_tick_ts_by_symbol": dict(last_option_tick_ts_by_symbol or {}),
        "option_feed_block_reason_by_symbol": dict(option_feed_block_reason_by_symbol or {}),
        "option_active_blockers_by_symbol": dict(option_active_blockers_by_symbol or {}),
        "restart_count_1h": int(restart_count_1h),
        "stale_strikes": int(stale_strikes),
        "runtime_state": effective_state_text,
        "last_error": str(last_error if last_error is not None else _LAST_RUNTIME_ERROR or "")[:1000],
        "disconnected_code": int(disconnected_code_value) if disconnected_code_value is not None else None,
        "disconnected_reason": str(disconnected_reason_value or "").strip() or None,
        "reconnect_blocked_reason": normalized_blocked_reason,
        "restart_blocked_reason": str(restart_blocked_reason or normalized_blocked_reason or "").strip().lower() or None,
        "ws_error_code": disconnected_code_value,
        "ws_error_reason": str(disconnected_reason_value or "").strip() or None,
        "ws_recovery_state": "RECOVERING_WS_DROP" if _RECOVERY_IN_PROGRESS else (
            "RECOVERY_BLOCKED" if normalized_blocked_reason else ("RECONNECTING" if str(effective_state_text).strip().upper() == "RECONNECTING" else "IDLE")
        ),
        "ws1006_recovery_attempt_count": int(_WS1006_RECOVERABLE_ATTEMPTS or 0),
        "recovery_in_progress": bool(_RECOVERY_IN_PROGRESS),
        "reconnect_attempted": bool(restart_attempted) if restart_attempted is not None else bool(_RECOVERY_IN_PROGRESS or disconnected_code_value is not None or str(disconnected_reason_value or "").strip()),
        "resubscribe_attempted": bool(restart_attempted) if restart_attempted is not None else bool(_RECOVERY_IN_PROGRESS),
        "option_feed_verification_state": str(_option_feed_verification_overlay_payload().get("state") or "IDLE"),
    }
    payload.update(
        _runtime_transport_truth_fields(
            now_epoch=float(now_epoch),
            ws_connected=ws_connected,
            runtime_state=effective_state_text,
            last_ws_tick_epoch=last_ws_tick_epoch,
            last_tick_age_sec=last_tick_age_sec,
            last_depth_age_sec=last_depth_age_sec,
            reconnect_blocked_reason=normalized_blocked_reason,
        )
    )
    stage_started = _mark_stage("payload_assembly_ms", stage_started)
    if (
        internal_retry_disabled is not None
        or stop_retry_called is not None
        or factory_stop_trying_called is not None
        or auto_reconnect_disabled is not None
        or internal_retry_error is not None
        or internal_retry_reason is not None
    ):
        payload.update(
            {
                "internal_retry_disabled": bool(internal_retry_disabled) if internal_retry_disabled is not None else None,
                "stop_retry_called": bool(stop_retry_called) if stop_retry_called is not None else None,
                "factory_stop_trying_called": (
                    bool(factory_stop_trying_called) if factory_stop_trying_called is not None else None
                ),
                "auto_reconnect_disabled": bool(auto_reconnect_disabled) if auto_reconnect_disabled is not None else None,
                "internal_retry_error": str(internal_retry_error or "").strip() or None,
                "internal_retry_reason": str(internal_retry_reason or "").strip() or None,
            }
        )
    if payload["reconnect_blocked_reason"]:
        payload.update(
            {
                "recovery_action": "process_restart_required",
                "process_restart_required": True,
                "recovery_blocked": True,
                "restart_attempt_allowed": False if restart_attempt_allowed is None else bool(restart_attempt_allowed),
                "restart_attempted": False if restart_attempted is None else bool(restart_attempted),
                "ws_reconnect_allowed": False,
                "ws_reconnect_attempted": False,
                "restart_suppressed": True,
                "reactor_not_restartable_detected": payload["reconnect_blocked_reason"].startswith("reactor_not_restartable"),
                "reconnect_blocked_since_epoch": float(_RECONNECT_BLOCKED_SINCE_EPOCH or 0.0) or None,
                "no_order_action": True,
                "order_safe": True,
            }
        )
    else:
        payload.update(
            {
                "process_restart_required": False,
                "recovery_blocked": False,
                "restart_attempt_allowed": bool(restart_attempt_allowed) if restart_attempt_allowed is not None else (str(effective_state_text).strip().upper() not in {"STOPPED", "AUTH_BLOCKED", "IMPORT_MISSING"}),
                "restart_attempted": bool(restart_attempted) if restart_attempted is not None else bool(
                    disconnected_code_value is not None or str(disconnected_reason_value or "").strip()
                ),
                "restart_suppressed": False,
                "ws_reconnect_allowed": True if ws_connected is not False else False,
                "ws_reconnect_attempted": bool(restart_attempted) if restart_attempted is not None else bool(
                    disconnected_code_value is not None or str(disconnected_reason_value or "").strip()
                ),
                "restart_blocked_reason": None,
                "no_order_action": True,
                "order_safe": True,
            }
        )
    if restart_verify:
        payload["restart_verification"] = restart_verify
    if restart_verify_failure:
        payload["restart_verification_failure_detail"] = str(restart_verify_failure)
    stage_started = _mark_stage("restart_overlay_attach_ms", stage_started)
    option_feed_verification = _option_feed_verification_overlay_payload()
    if option_feed_verification:
        payload["option_feed_verification"] = option_feed_verification
        payload["option_ticks_verified"] = bool(str(option_feed_verification.get("state") or "").upper() == "OK")
        payload["verified_option_symbols"] = option_feed_verification.get("verified_symbols") or []
        payload["missing_option_symbols"] = option_feed_verification.get("missing_symbols") or []
    stage_started = _mark_stage("option_feed_verification_overlay_ms", stage_started)
    payload["effective_ws_connected"] = derive_effective_ws_connected(payload)
    payload["feed_ok"] = derive_feed_ok(payload)
    stage_started = _mark_stage("derive_feed_ok_ms", stage_started)
    feed_health_max_depth_age_sec = float(
        getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", 15.0)
    )
    feed_truth = classify_feed_truth_state(
        payload,
        now_epoch=float(now_epoch),
        max_option_tick_age_sec=float(getattr(cfg, "OPTION_LTP_SLA_SEC", 15.0)),
        max_ltp_age_sec=float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 15.0)),
        max_depth_age_sec=feed_health_max_depth_age_sec,
    )
    payload["feed_truth_state"] = str(feed_truth.state)
    payload["feed_truth_reason_code"] = str(feed_truth.reason_code)
    payload["feed_truth_reasons"] = list(feed_truth.reasons)
    payload["feed_truth_strict_live"] = bool(feed_truth.strict_live)
    stage_started = _mark_stage("classify_feed_truth_ms", stage_started)
    canonical_feed_truth = build_canonical_feed_truth_state(
        {
            "runtime_state": effective_state_text,
            "session_id": f"depth_ws:{int(_DEPTH_WS_START_EPOCH or float(now_epoch))}",
            "ws_connected": ws_connected,
            "underlying_tick_fresh": bool(last_tick_age_sec is not None and last_tick_age_sec <= 2.5),
            "depth_fresh": bool(last_depth_age_sec is not None and last_depth_age_sec <= 6.0),
            "option_ticks_verified": bool(str((option_feed_verification or {}).get("state") or "").upper() == "OK"),
            "latest_ltp_age_sec": last_tick_age_sec,
            "latest_depth_age_sec": last_depth_age_sec,
            "latest_option_tick_age_sec": None,
            "subscribed_option_tokens_count": int(subscribed_option_tokens_count or 0),
            "verified_option_symbols": list((option_feed_verification or {}).get("verified_option_symbols") or []),
            "missing_option_symbols": list((option_feed_verification or {}).get("missing_option_symbols") or []),
            "recovery_blocked": bool(payload.get("recovery_blocked")),
            "process_restart_required": bool(payload.get("process_restart_required")),
            "feed_error_code": disconnected_code_value,
            "reason_code": payload.get("feed_truth_reason_code"),
            "updated_at_epoch": float(now_epoch),
            "updated_at_ist": now_ist(),
        },
        restart_artifact_dir=runtime_dir(),
    )
    payload["canonical_feed_truth"] = canonical_feed_truth.to_payload()
    payload["recovery_state"] = canonical_feed_truth.recovery_state
    payload["recovery_generation_id"] = int(getattr(_FEED_RECOVERY_COORDINATOR.state, "recovery_generation_id", 0) or 0)
    payload["recovery_in_progress"] = bool(getattr(_FEED_RECOVERY_COORDINATOR.state, "recovery_in_progress", False))
    payload["ws_error_code"] = canonical_feed_truth.ws_error_code
    payload["ws_error_reason"] = canonical_feed_truth.ws_error_reason
    payload["ws_fault_class"] = canonical_feed_truth.ws_fault_class
    stage_started = _mark_stage("canonical_feed_truth_ms", stage_started)
    payload = canonicalize_feed_runtime_snapshot_truth(payload)
    payload = attach_feed_execution_truth(payload)
    payload = stamp_runtime_payload(
        payload,
        writer="kite_depth_ws.feed_runtime",
    )
    stage_started = _mark_stage("execution_truth_stamp_ms", stage_started)
    if stage_timing_enabled:
        stage_timing_ms["total_pre_write_ms"] = round(
            max(0.0, time.perf_counter() - float(stage_total_start)) * 1000.0,
            3,
        )
        payload["feed_runtime_stage_timing_ms"] = dict(stage_timing_ms)
    try:
        write_started = time.perf_counter()
        write_json_atomic(path, payload)
        write_ms = round(max(0.0, time.perf_counter() - float(write_started)) * 1000.0, 3)
        health_started = time.perf_counter()
        duration_artifact = _write_feed_health_duration_artifact(payload)
        health_ms = round(max(0.0, time.perf_counter() - float(health_started)) * 1000.0, 3)
        if stage_timing_enabled:
            timing_event = dict(stage_timing_ms)
            timing_event["write_feed_runtime_latest_ms"] = write_ms
            timing_event["health_duration_artifact_ms"] = health_ms
            if isinstance(duration_artifact, dict):
                timing_event["health_duration_target_met"] = bool(duration_artifact.get("target_met"))
                timing_event["current_healthy_duration_sec"] = duration_artifact.get("current_healthy_duration_sec")
            _log_ws("FEED_RUNTIME_STAGE_TIMING", timing_event, throttle_key="FEED_RUNTIME_STAGE_TIMING")
        publish_feed_unhealthy_status_overlay(
            feed_payload=payload,
            logs_root=logs_dir(),
            now_epoch=float(now_epoch),
        )
    except Exception as exc:
        _log_ws("FEED_RUNTIME_SNAPSHOT_ERROR", {"error": str(exc), "path": str(path)})


def _latest_depth_epoch_from_store() -> float | None:
    latest = None
    try:
        for book in depth_store.books.values():
            ts = book.get("ts_epoch") or book.get("ts")
            if ts is None:
                continue
            ts_val = _coerce_epoch(ts)
            if ts_val is None:
                continue
            if latest is None or ts_val > latest:
                latest = ts_val
    except Exception:
        return None
    return latest


def _persist_runtime_snapshot_row(
    *,
    ws_connected: bool | None,
    source: str,
    now_epoch: float | None = None,
    runtime_state: str | None = None,
    last_error: str | None = None,
    disconnected_code: int | None = None,
    disconnected_reason: str | None = None,
    intended_tokens_count: int | None = None,
    reconnect_blocked_reason: str | None = None,
    restart_attempt_allowed: bool | None = None,
    restart_attempted: bool | None = None,
    restart_blocked_reason: str | None = None,
    internal_retry_disabled: bool | None = None,
    stop_retry_called: bool | None = None,
    factory_stop_trying_called: bool | None = None,
    auto_reconnect_disabled: bool | None = None,
    internal_retry_error: str | None = None,
    internal_retry_reason: str | None = None,
    process_restart_required: bool | None = None,
) -> None:
    ts_epoch = float(now_epoch if now_epoch is not None else now_utc_epoch())
    state_text = str(runtime_state or _RUNTIME_STATE or "UNKNOWN").strip().upper()
    effective_state_text, restart_verify_failure = _effective_runtime_state_for_snapshot(
        state_text,
        now_epoch=ts_epoch,
    )
    state_machine: dict | None = None
    effective_state_text, state_machine, ws_connected, normalized_blocked_reason = _normalize_recovery_blocked_snapshot_state(
        runtime_state=effective_state_text,
        state_machine=state_machine,
        reconnect_blocked_reason=reconnect_blocked_reason,
        ws_connected=ws_connected,
    )
    err_text = str(last_error if last_error is not None else _LAST_RUNTIME_ERROR or "")[:1000]
    sub_counts = _subscribed_tokens_count_by_symbol(_LAST_TOKENS)
    missing_count, missing_counts_by_symbol = _missing_option_tokens_stats()
    market_open = bool(is_market_open_ist())
    last_db_tick_epoch = _latest_db_tick_epoch()
    last_db_tick_age_sec = None
    if last_db_tick_epoch is not None:
        last_db_tick_age_sec = max(0.0, float(ts_epoch) - float(last_db_tick_epoch))
    last_ws_tick_epoch = _LAST_WS_TICK_EPOCH if _LAST_WS_TICK_EPOCH > 0 else None
    last_tick_epoch = last_ws_tick_epoch or last_db_tick_epoch
    last_tick_age_sec = max(0.0, float(ts_epoch) - float(last_tick_epoch)) if last_tick_epoch is not None else None
    last_depth_epoch = _latest_depth_epoch_from_store()
    last_depth_age_sec = max(0.0, float(ts_epoch) - float(last_depth_epoch)) if last_depth_epoch is not None else None
    if normalized_blocked_reason:
        state_machine = state_machine or {
            "state": "DOWN",
            "reason": (
                "ws1006_process_restart_required"
                if normalized_blocked_reason == "ws1006_process_restart_required"
                else "reconnect_blocked"
            ),
        }
    elif not market_open:
        state_machine = {"state": "MARKET_CLOSED", "reason": "market_closed"}
    elif ws_connected is False:
        state_machine = {"state": "DOWN", "reason": "ws_disconnected"}
    elif last_tick_age_sec is None:
        state_machine = {"state": "STARTING", "reason": "awaiting_first_tick"}
    else:
        feed_health_live_tick_grace_sec = float(getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", 10.0))
        if last_tick_age_sec <= feed_health_live_tick_grace_sec:
            state_machine = {"state": "LIVE", "reason": "ticks_flowing"}
        else:
            state_machine = {"state": "DOWN", "reason": "no_ws_messages"}
    option_state = _option_runtime_state(
        now_epoch=ts_epoch,
        tokens=_LAST_TOKENS,
        expected_counts_by_symbol=_LAST_OPTION_COUNTS_BY_SYMBOL,
        min_required_by_symbol=_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL,
        ws_connected=ws_connected,
    )
    option_feed_block_reason_by_symbol = dict(option_state.get("feed_block_reason_by_symbol") or {})
    option_active_blockers_by_symbol = dict(option_state.get("active_blockers_by_symbol") or {})
    if effective_state_text == "RECOVERY_BLOCKED" or normalized_blocked_reason == "ws1006_process_restart_required":
        for symbol in list(option_feed_block_reason_by_symbol.keys()):
            option_feed_block_reason_by_symbol[symbol] = "NO_LIVE_OPTION_FEED"
            blockers = list(option_active_blockers_by_symbol.get(symbol) or [])
            if "NO_LIVE_OPTION_FEED" not in blockers:
                blockers.insert(0, "NO_LIVE_OPTION_FEED")
            option_active_blockers_by_symbol[symbol] = blockers
    restart_verify = _restart_verify_overlay_payload()
    disconnected_code_value = disconnected_code if disconnected_code is not None else _LAST_DISCONNECTED_CODE
    disconnected_reason_value = disconnected_reason if disconnected_reason is not None else _LAST_DISCONNECTED_REASON
    if (
        not normalized_blocked_reason
        and effective_state_text == "RESTARTING"
        and (disconnected_code_value is not None or str(disconnected_reason_value or "").strip())
    ):
        ws_connected = False
    payload = {
        "ts_epoch": ts_epoch,
        "ws_connected": ws_connected,
        "subscribed_tokens_count": len(_LAST_TOKENS or []),
        "intended_tokens_count": int(
            intended_tokens_count
            if intended_tokens_count is not None
            else (_INTENDED_TOKEN_COUNT if _INTENDED_TOKEN_COUNT > 0 else len(_LAST_TOKENS or []))
        ),
        "subscribed_tokens_sample": list(_LAST_TOKENS or [])[:25],
        "subscribed_tokens_count_by_symbol": sub_counts,
        "missing_option_tokens_count": int(missing_count),
        "missing_option_tokens_count_by_symbol": missing_counts_by_symbol,
        "subscribed_option_tokens_count": int(option_state.get("option_count") or 0),
        "option_last_tick_age_by_symbol": dict(option_state.get("option_age_by_symbol") or {}),
        "option_last_tick_sample": list(option_state.get("sample_rows") or []),
        "option_tokens_resolved_count_by_symbol": dict(_LAST_OPTION_COUNTS_BY_SYMBOL or {}),
        "option_tokens_subscribed_count_by_symbol": dict(option_state.get("subscribed_count_by_symbol") or {}),
        "option_ticks_received_count_by_symbol": dict(option_state.get("ticks_received_count_by_symbol") or {}),
        "last_option_tick_ts_by_symbol": dict(option_state.get("last_tick_ts_by_symbol") or {}),
        "option_feed_block_reason_by_symbol": option_feed_block_reason_by_symbol,
        "option_active_blockers_by_symbol": option_active_blockers_by_symbol,
        "market_open": market_open,
        "last_ws_tick_epoch": last_ws_tick_epoch,
        "last_tick_age_sec": last_tick_age_sec,
        "last_depth_epoch": last_depth_epoch,
        "last_depth_age_sec": last_depth_age_sec,
        "state_machine": state_machine,
        "source": source,
        "runtime_state": effective_state_text,
        "last_error": err_text,
        "disconnected_code": int(disconnected_code_value) if disconnected_code_value is not None else None,
        "disconnected_reason": str(disconnected_reason_value or "").strip() or None,
        "reconnect_blocked_reason": normalized_blocked_reason,
        "restart_blocked_reason": str(restart_blocked_reason or normalized_blocked_reason or "").strip().lower() or None,
    }
    payload.update(
        _runtime_transport_truth_fields(
            now_epoch=ts_epoch,
            ws_connected=ws_connected,
            runtime_state=effective_state_text,
            last_ws_tick_epoch=last_ws_tick_epoch,
            last_tick_age_sec=last_tick_age_sec,
            last_depth_age_sec=last_depth_age_sec,
            reconnect_blocked_reason=normalized_blocked_reason,
        )
    )
    if (
        internal_retry_disabled is not None
        or stop_retry_called is not None
        or factory_stop_trying_called is not None
        or auto_reconnect_disabled is not None
        or internal_retry_error is not None
        or internal_retry_reason is not None
    ):
        payload.update(
            {
                "internal_retry_disabled": bool(internal_retry_disabled) if internal_retry_disabled is not None else None,
                "stop_retry_called": bool(stop_retry_called) if stop_retry_called is not None else None,
                "factory_stop_trying_called": (
                    bool(factory_stop_trying_called) if factory_stop_trying_called is not None else None
                ),
                "auto_reconnect_disabled": bool(auto_reconnect_disabled) if auto_reconnect_disabled is not None else None,
                "internal_retry_error": str(internal_retry_error or "").strip() or None,
                "internal_retry_reason": str(internal_retry_reason or "").strip() or None,
            }
        )
    if payload["reconnect_blocked_reason"]:
        payload.update(
            {
                "recovery_action": "process_restart_required",
                "process_restart_required": True,
                "recovery_blocked": True,
                "restart_attempt_allowed": False if restart_attempt_allowed is None else bool(restart_attempt_allowed),
                "restart_attempted": False if restart_attempted is None else bool(restart_attempted),
                "ws_reconnect_allowed": False,
                "ws_reconnect_attempted": False,
                "restart_suppressed": True,
                "reactor_not_restartable_detected": payload["reconnect_blocked_reason"].startswith("reactor_not_restartable"),
                "reconnect_blocked_since_epoch": float(_RECONNECT_BLOCKED_SINCE_EPOCH or 0.0) or None,
                "no_order_action": True,
                "order_safe": True,
            }
        )
    else:
        payload.update(
            {
                "process_restart_required": bool(process_restart_required) if process_restart_required is not None else False,
                "recovery_blocked": False,
                "restart_attempt_allowed": bool(restart_attempt_allowed) if restart_attempt_allowed is not None else (state_text not in {"STOPPED", "AUTH_BLOCKED", "IMPORT_MISSING"}),
                "restart_attempted": bool(restart_attempted) if restart_attempted is not None else bool(
                    disconnected_code_value is not None or str(disconnected_reason_value or "").strip()
                ),
                "restart_suppressed": False,
                "ws_reconnect_allowed": True if ws_connected is not False else False,
                "ws_reconnect_attempted": bool(restart_attempted) if restart_attempted is not None else bool(
                    disconnected_code_value is not None or str(disconnected_reason_value or "").strip()
                ),
                "restart_blocked_reason": None,
                "no_order_action": True,
                "order_safe": True,
            }
        )
    if restart_verify:
        payload["restart_verification"] = restart_verify
    if restart_verify_failure:
        payload["restart_verification_failure_detail"] = str(restart_verify_failure)
    ok = write_feed_runtime_snapshot(payload)
    if not ok:
        _log_ws("FEED_RUNTIME_STORE_WRITE_ERROR", {"source": source})
    _write_feed_runtime_snapshot(
        now_epoch=ts_epoch,
        ws_connected=ws_connected,
        subscribed_tokens_count=len(_LAST_TOKENS or []),
        intended_tokens_count=int(payload["intended_tokens_count"] or 0),
        subscribed_tokens_count_by_symbol=sub_counts,
        missing_option_tokens_count=missing_count,
        missing_option_tokens_count_by_symbol=missing_counts_by_symbol,
        last_db_tick_epoch=last_db_tick_epoch,
        last_db_tick_age_sec=last_db_tick_age_sec,
        last_ws_tick_epoch=last_ws_tick_epoch,
        last_tick_age_sec=last_tick_age_sec,
        last_depth_epoch=last_depth_epoch,
        last_depth_age_sec=last_depth_age_sec,
        market_open=market_open,
        state_machine=state_machine,
        subscribed_option_tokens_count=int(option_state.get("option_count") or 0),
        option_last_tick_age_by_symbol=dict(option_state.get("option_age_by_symbol") or {}),
        option_last_tick_sample=list(option_state.get("sample_rows") or []),
        option_tokens_resolved_count_by_symbol=dict(_LAST_OPTION_COUNTS_BY_SYMBOL or {}),
        option_tokens_subscribed_count_by_symbol=dict(option_state.get("subscribed_count_by_symbol") or {}),
        option_ticks_received_count_by_symbol=dict(option_state.get("ticks_received_count_by_symbol") or {}),
        last_option_tick_ts_by_symbol=dict(option_state.get("last_tick_ts_by_symbol") or {}),
        option_feed_block_reason_by_symbol=option_feed_block_reason_by_symbol,
        option_active_blockers_by_symbol=option_active_blockers_by_symbol,
        restart_count_1h=_restart_count_1h(ts_epoch),
        stale_strikes=_STALE_STRIKES,
        runtime_state=effective_state_text,
        last_error=err_text,
        reconnect_blocked_reason=str(payload.get("reconnect_blocked_reason") or "").strip().lower() or None,
        internal_retry_disabled=internal_retry_disabled,
        stop_retry_called=stop_retry_called,
        factory_stop_trying_called=factory_stop_trying_called,
        auto_reconnect_disabled=auto_reconnect_disabled,
        internal_retry_error=internal_retry_error,
        internal_retry_reason=internal_retry_reason,
    )


def _run_db_tick_watchdog_cycle(
    *,
    now_epoch: float,
    market_open: bool,
    stale_restart_sec: float,
    reset_sec: float = 2.0,
    strikes_to_restart: int = 2,
    restart_cb=None,
) -> dict:
    global _STALE_STRIKES
    db_tick_epoch = _latest_db_tick_epoch()
    db_tick_age_sec = None
    if db_tick_epoch is not None:
        db_tick_age_sec = max(0.0, float(now_epoch) - float(db_tick_epoch))
    ws_tick_epoch = _LAST_WS_TICK_EPOCH if _LAST_WS_TICK_EPOCH > 0 else None
    ws_tick_age_sec = None
    if ws_tick_epoch is not None:
        ws_tick_age_sec = max(0.0, float(now_epoch) - float(ws_tick_epoch))
    restarted = False
    if not market_open:
        _STALE_STRIKES = 0
    elif ws_tick_age_sec is not None and ws_tick_age_sec <= float(reset_sec):
        if _STALE_STRIKES:
            _log_ws(
                "FEED_TICK_RECOVERED",
                {
                    "age_sec": ws_tick_age_sec,
                    "source": "ws",
                    "strikes": _STALE_STRIKES,
                },
            )
        _STALE_STRIKES = 0
        _emit_feed_health(
            "FEED_HEALTH_OK",
            {
                "reason": "ws_ticks_flowing",
                "last_ws_tick_epoch": ws_tick_epoch,
                "last_ws_tick_age_sec": ws_tick_age_sec,
                "last_db_tick_epoch": db_tick_epoch,
                "last_db_tick_age_sec": db_tick_age_sec,
                "stale_strikes": 0,
            },
        )
    else:
        ws_stale_limit = float(getattr(cfg, "MAX_DEPTH_AGE_SEC", 5.0))
        is_stale = False
        stale_source = "unknown"
        stale_age = 0.0

        if db_tick_age_sec is not None and db_tick_age_sec > float(stale_restart_sec):
            is_stale = True
            stale_source = "db"
            stale_age = db_tick_age_sec
        elif ws_tick_age_sec is not None and ws_tick_age_sec > float(ws_stale_limit):
            is_stale = True
            stale_source = "ws"
            stale_age = ws_tick_age_sec

        if is_stale:
            _STALE_STRIKES += 1
            _log_ws(
                "FEED_TICK_STALE",
                {"age_sec": stale_age, "source": stale_source, "strikes": _STALE_STRIKES},
                throttle_key="FEED_TICK_STALE",
            )
            _emit_feed_health(
                "FEED_STALE",
                {
                    "reason": f"{stale_source}_tick_stale",
                    "last_ws_tick_epoch": ws_tick_epoch,
                    "last_ws_tick_age_sec": ws_tick_age_sec,
                    "last_db_tick_epoch": db_tick_epoch,
                    "last_db_tick_age_sec": db_tick_age_sec,
                    "stale_strikes": int(_STALE_STRIKES),
                },
            )
            if _STALE_STRIKES >= max(1, int(strikes_to_restart)):
                cb = restart_cb or restart_depth_ws
                try:
                    restarted = bool(
                        cb(
                            reason="tick_stalled",
                            ignore_cooldown=True,
                            force_full_restart=True,
                        )
                    )
                except TypeError:
                    try:
                        restarted = bool(
                            cb(
                                reason="tick_stalled",
                                ignore_cooldown=True,
                            )
                        )
                    except TypeError:
                        restarted = bool(cb("tick_stalled"))
        elif not is_stale and ((db_tick_age_sec is not None and db_tick_age_sec <= float(reset_sec)) or (ws_tick_age_sec is not None and ws_tick_age_sec <= float(reset_sec))):
            if _STALE_STRIKES:
                _log_ws("FEED_TICK_RECOVERED", {"age_sec": db_tick_age_sec, "source": "db", "strikes": _STALE_STRIKES})
            _STALE_STRIKES = 0
            _emit_feed_health(
                "FEED_HEALTH_OK",
                {
                    "reason": "db_ticks_recovered",
                    "last_ws_tick_epoch": ws_tick_epoch,
                    "last_ws_tick_age_sec": ws_tick_age_sec,
                    "last_db_tick_epoch": db_tick_epoch,
                    "last_db_tick_age_sec": db_tick_age_sec,
                    "stale_strikes": 0,
                },
            )

    return {
        "last_db_tick_epoch": db_tick_epoch,
        "last_db_tick_age_sec": db_tick_age_sec,
        "last_ws_tick_epoch": ws_tick_epoch,
        "last_ws_tick_age_sec": ws_tick_age_sec,
        "stale_strikes": int(_STALE_STRIKES),
        "restarted": bool(restarted),
    }


def _infer_atm_strike(ltp: float | None, step: float | None) -> int | None:
    if ltp is None or step is None or step <= 0:
        return None
    try:
        return int(round(float(ltp) / float(step)) * float(step))
    except Exception:
        return None


def _underlying_ltp(symbol: str, index_token: int | None = None) -> tuple[float | None, str]:
    mapping = getattr(cfg, "PREMARKET_INDICES_LTP", {}) or {}
    ltp_symbol = mapping.get(symbol.upper())
    if not ltp_symbol:
        ltp_symbol = None
    try:
        if ltp_symbol:
            quotes = kite_client.ltp([ltp_symbol]) or {}
            val = quotes.get(ltp_symbol, {}).get("last_price")
            if val is not None:
                return float(val), "live_ltp"
    except Exception:
        pass
    if index_token is not None:
        try:
            ltp, _ts_epoch = get_ltp(int(index_token))
            if ltp is not None:
                return float(ltp), "tick_store"
        except Exception:
            pass
    return None, "missing"


def _expiry_key(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    try:
        text = str(value).strip()
        if not text:
            return None
        text = text.split("T", 1)[0]
        return datetime.fromisoformat(text).date().isoformat()
    except Exception:
        return None


def _load_option_token_meta(symbol: str, exchange: str, expiry) -> dict[int, dict]:
    seg = "NFO-OPT" if str(exchange).upper() == "NFO" else "BFO-OPT"
    expiry_norm = _expiry_key(expiry)
    out: dict[int, dict] = {}
    try:
        data = kite_client.instruments_cached(exchange, ttl_sec=getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600))
    except Exception:
        data = []
    for inst in data:
        if str(inst.get("segment") or "").upper() != seg:
            continue
        if str(inst.get("name") or "").upper() != str(symbol or "").upper():
            continue
        if expiry_norm is not None and _expiry_key(inst.get("expiry")) != expiry_norm:
            continue
        tok = inst.get("instrument_token")
        if tok is None:
            continue
        try:
            tok_int = int(tok)
        except Exception:
            continue
        strike = inst.get("strike")
        try:
            strike_val = float(strike) if strike is not None else None
        except Exception:
            strike_val = None
        out[tok_int] = {
            "strike": strike_val,
            "instrument_type": str(inst.get("instrument_type") or "").upper(),
        }
    return out


def _maybe_raise_option_token_incident(
    *,
    symbol: str,
    exchange: str,
    expiry,
    option_count: int,
    min_required: int,
    sample_tokens: list[int] | None = None,
    fail_reason: str = "option_tokens_under_min",
) -> None:
    cooldown_sec = float(getattr(cfg, "OPTION_TOKEN_INCIDENT_COOLDOWN_SEC", 300.0))
    now_epoch = float(now_utc_epoch())
    exp_key = _expiry_key(expiry) or "unknown"
    key = f"{str(symbol).upper()}|{str(exchange).upper()}|{exp_key}"
    last_ts = float(_LAST_OPTION_TOKEN_INCIDENT_TS.get(key, 0.0) or 0.0)
    if (now_epoch - last_ts) < cooldown_sec:
        return
    _LAST_OPTION_TOKEN_INCIDENT_TS[key] = now_epoch
    payload = {
        "symbol": str(symbol).upper(),
        "exchange": str(exchange).upper(),
        "expiry": exp_key,
        "option_count": int(option_count),
        "min_required": int(min_required),
        "fail_reason": str(fail_reason or "option_tokens_under_min"),
        "sample_tokens": list(sample_tokens or [])[:10],
    }
    _log_ws("FEED_OPTION_TOKENS_UNDER_MIN", payload)
    try:
        from core.incidents import SEV2, create_incident

        create_incident(SEV2, "OPTION_TOKENS_UNDER_MIN", payload)
    except Exception:
        pass


def _option_distance_rank(meta: dict | None, atm: int | None, step: float | None, token: int) -> tuple[float, int, float, int, int]:
    if not meta or atm is None or step is None or step <= 0:
        return (float("inf"), 1, float("inf"), 2, int(token))
    strike = meta.get("strike")
    if strike is None:
        return (float("inf"), 1, float("inf"), 2, int(token))
    try:
        strike_val = float(strike)
    except Exception:
        return (float("inf"), 1, float("inf"), 2, int(token))
    dist_abs = abs(strike_val - float(atm))
    dist_steps = dist_abs / float(step)
    opt_type = str(meta.get("instrument_type") or "").upper()
    # Prefer keeping non-OTM at a given distance; when pruning, far OTM tokens get dropped first.
    is_otm = (
        (opt_type == "CE" and strike_val > float(atm))
        or (opt_type == "PE" and strike_val < float(atm))
    )
    otm_rank = 1 if is_otm else 0
    type_rank = 0 if opt_type == "CE" else (1 if opt_type == "PE" else 2)
    return (dist_steps, otm_rank, dist_abs, type_rank, int(token))


def _enforce_subscription_budget(
    desired_tokens: list[int] | set[int],
    *,
    max_tokens: int | None,
    option_rank_by_token: dict[int, tuple] | None = None,
    underlying_tokens: set[int] | None = None,
    sticky_tokens: set[int] | None = None,
    active_trade_tokens: set[int] | None = None,
) -> tuple[list[int], bool, dict]:
    ordered = [int(t) for t in (desired_tokens or []) if t is not None and int(t) > 0]
    ordered = list(dict.fromkeys(ordered))
    budget = int(max_tokens or 0)
    preserve_tokens = set(int(t) for t in (underlying_tokens or set()) if t is not None)
    preserve_tokens.update(int(t) for t in (sticky_tokens or set()) if t is not None)
    preserve_tokens.update(int(t) for t in (active_trade_tokens or set()) if t is not None)
    if budget <= 0 or len(ordered) <= budget:
        return ordered, False, {
            "budget": budget,
            "dropped_count": 0,
            "dropped_tokens": [],
            "preserved_count": len([t for t in ordered if t in preserve_tokens]),
        }

    option_rank = dict(option_rank_by_token or {})
    preserved = [int(t) for t in ordered if int(t) in preserve_tokens]
    candidates = [int(t) for t in ordered if int(t) not in preserve_tokens]
    candidates.sort(
        key=lambda tok: option_rank.get(
            int(tok),
            (float("inf"), 1, float("inf"), 2, int(tok)),
        )
    )
    keep_budget = budget - len(preserved)
    if keep_budget >= 0:
        kept = preserved + candidates[:keep_budget]
    else:
        kept = list(preserved)
        _log_ws(
            "FEED_TOKEN_BUDGET_PRESERVE_EXCEEDED",
            {
                "max_tokens": budget,
                "preserved_tokens": len(preserved),
                "underlying_tokens": len(set(int(t) for t in (underlying_tokens or set()) if t is not None)),
                "sticky_tokens": len(set(int(t) for t in (sticky_tokens or set()) if t is not None)),
                "active_trade_tokens": len(set(int(t) for t in (active_trade_tokens or set()) if t is not None)),
            },
        )
    kept = list(dict.fromkeys(int(t) for t in kept if t is not None and int(t) > 0))
    kept_set = set(kept)
    dropped = [int(t) for t in ordered if int(t) not in kept_set]
    _log_ws(
        "FEED_SUBSCRIPTION_BUDGET_ENFORCED",
        {
            "max_tokens": budget,
            "desired_tokens": len(ordered),
            "kept_tokens": len(kept),
            "dropped_tokens": len(dropped),
            "underlying_tokens": len(set(int(t) for t in (underlying_tokens or set()) if t is not None)),
            "sticky_tokens": len(set(int(t) for t in (sticky_tokens or set()) if t is not None)),
            "active_trade_tokens": len(set(int(t) for t in (active_trade_tokens or set()) if t is not None)),
            "dropped_sample": dropped[:20],
        },
    )
    return kept, True, {
        "budget": budget,
        "dropped_count": len(dropped),
        "dropped_tokens": dropped,
        "preserved_count": len(preserved),
    }


def get_sticky_tokens() -> set[int]:
    """
    Optional sticky depth subscriptions for active trades.

    Falls back to an empty set when trade-state sources are unavailable.
    """
    out: set[int] = set()
    try:
        from core.trade_store import fetch_recent_trades

        cols, rows = fetch_recent_trades(limit=500)
    except Exception:
        return out
    if not cols or not rows:
        return out
    col_idx = {str(c): i for i, c in enumerate(cols)}
    tok_idx = col_idx.get("instrument_token")
    if tok_idx is None:
        return out
    status_idx = col_idx.get("status")
    exit_idx = col_idx.get("exit_time")
    for row in rows:
        try:
            tok_raw = row[tok_idx]
            tok = int(tok_raw)
        except Exception:
            continue
        if tok <= 0:
            continue
        is_active = False
        if status_idx is not None:
            try:
                status = str(row[status_idx] or "").strip().upper()
            except Exception:
                status = ""
            if status in {"ACTIVE", "OPEN", "LIVE", "ENTERED"}:
                is_active = True
        if not is_active and exit_idx is not None:
            try:
                exit_time = row[exit_idx]
            except Exception:
                exit_time = None
            if exit_time in (None, "", "None"):
                is_active = True
        if is_active:
            out.add(tok)
    return out


def build_subscription_tokens(symbols: list[str] | None, max_tokens: int | None = None) -> tuple[list[int], list[dict]]:
    global _UNDERLYING_TOKENS, _UNDERLYING_TOKEN_TO_SYMBOL, _UNDERLYING_LOGGED_MISSING, _TOKEN_TO_SYMBOL, _LAST_ATM_BY_SYMBOL
    global _LAST_DESIRED_TOKENS
    global _LAST_OPTION_COUNTS_BY_SYMBOL, _LAST_OPTION_MIN_REQUIRED_BY_SYMBOL
    symbols = list(symbols or list(getattr(cfg, "SYMBOLS", []) or []))
    tokens: list[int] = []
    resolution: list[dict] = []
    underlying_tokens: list[int] = []
    underlying_token_to_symbol: dict[int, str] = {}
    token_to_symbol: dict[int, str] = {}
    option_rank_by_token: dict[int, tuple[float, int, float, int, int]] = {}
    token_exchange_hint: dict[int, str] = {}
    if max_tokens is None:
        max_tokens = int(getattr(cfg, "DEPTH_SUBSCRIPTION_MAX_TOKENS", 150))
    strikes_around_default = int(getattr(cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND", 6))
    strikes_by_symbol = getattr(cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND_BY_SYMBOL", {}) or {}
    step_map = getattr(cfg, "STRIKE_STEP_BY_SYMBOL", {}) or {}
    validate_tokens = bool(getattr(cfg, "DEPTH_SUBSCRIPTION_VALIDATE_TOKENS", True))
    min_option_tokens = max(1, int(getattr(cfg, "MIN_OPTION_TOKENS", 12)))
    sticky_tokens = set(int(t) for t in get_sticky_tokens() if t is not None)
    active_trade_tokens = set(sticky_tokens)

    for sym in symbols:
        sym_upper = str(sym).upper()
        exchange = "BFO" if sym_upper == "SENSEX" else "NFO"
        index_token = kite_client.resolve_index_token(sym_upper)
        index_source = "instruments"
        if not index_token:
            mapping = getattr(cfg, "INDEX_TOKEN_BY_SYMBOL", {}) or {}
            fallback_token = int(mapping.get(sym_upper, 0) or 0)
            if fallback_token > 0:
                index_token = fallback_token
                index_source = "config"
        expiry = kite_client.next_available_expiry(sym, exchange=exchange)
        step = float(step_map.get(sym_upper, getattr(cfg, "STRIKE_STEP", 50)))
        strikes_around = int(strikes_by_symbol.get(sym_upper, strikes_around_default))
        try:
            ltp_result = _underlying_ltp(sym_upper, index_token)
        except TypeError:
            # Legacy tests may monkeypatch _underlying_ltp(symbol) only.
            ltp_result = _underlying_ltp(sym_upper)
        if isinstance(ltp_result, tuple):
            ltp, ltp_source = ltp_result
        else:
            ltp = ltp_result
            ltp_source = "live_ltp" if ltp is not None else "missing"
        if ltp is None:
            fallback = (getattr(cfg, "PREMARKET_INDICES_CLOSE", {}) or {}).get(sym_upper)
            if fallback:
                ltp = float(fallback)
                ltp_source = "fallback_close"
        atm = _infer_atm_strike(ltp, step)
        if atm is None:
            cached_atm = _LAST_ATM_BY_SYMBOL.get(sym_upper)
            if cached_atm is not None:
                atm = int(cached_atm)
                ltp_source = "fallback_last_atm"
        if atm is not None:
            _LAST_ATM_BY_SYMBOL[sym_upper] = int(atm)

        option_meta: dict[int, dict] = {}
        if expiry:
            option_meta = _load_option_token_meta(sym_upper, exchange, expiry)

        option_tokens_raw: list[int] = []
        if expiry and atm is not None:
            option_tokens_raw = kite_client.resolve_option_tokens_window(
                symbol=sym,
                expiry=expiry,
                strikes_around=strikes_around,
                exchange=exchange,
                spot=ltp,
            )
        option_tokens: list[int] = []
        seen_option_tokens: set[int] = set()
        for tok in option_tokens_raw or []:
            try:
                tok_int = int(tok)
            except Exception:
                continue
            if tok_int in seen_option_tokens:
                continue
            seen_option_tokens.add(tok_int)
            option_tokens.append(tok_int)
        option_tokens.sort(key=lambda t: _option_distance_rank(option_meta.get(int(t)), atm, step, int(t)))
        for tok in option_tokens:
            option_rank_by_token[int(tok)] = _option_distance_rank(option_meta.get(int(tok)), atm, step, int(tok))
        option_fail_reason = None
        option_coverage_status = "FULL"
        option_coverage_reason = "full_coverage"
        if expiry is None:
            option_fail_reason = "expiry_unavailable"
        elif atm is None:
            option_fail_reason = "atm_unavailable"
        elif len(option_tokens) <= 0:
            option_fail_reason = "option_tokens_zero"
        elif len(option_tokens) < min_option_tokens:
            option_fail_reason = "option_tokens_under_min"
        if option_fail_reason is not None:
            resolved_option_count = len(option_tokens)
            if option_fail_reason == "option_tokens_under_min" and resolved_option_count > 0:
                option_coverage_status = "DEGRADED"
                option_coverage_reason = "DEGRADED_OPTION_COVERAGE"
            elif resolved_option_count <= 0:
                option_coverage_status = "ZERO"
                option_coverage_reason = option_fail_reason
            else:
                option_coverage_status = "FULL"
                option_coverage_reason = "full_coverage"
            _maybe_raise_option_token_incident(
                symbol=sym_upper,
                exchange=exchange,
                expiry=expiry,
                option_count=len(option_tokens),
                min_required=min_option_tokens,
                sample_tokens=option_tokens[:10],
                fail_reason=option_fail_reason,
            )
        else:
            resolved_option_count = len(option_tokens)
            option_coverage_status = "FULL"
            option_coverage_reason = "full_coverage"

        per_tokens: list[int] = []
        if index_token:
            try:
                idx_int = int(index_token)
                per_tokens.append(idx_int)
                underlying_tokens.append(idx_int)
                underlying_token_to_symbol[idx_int] = sym_upper
                token_exchange_hint[idx_int] = "BSE" if sym_upper == "SENSEX" else "NSE"
            except Exception:
                index_token = None
        for tok in option_tokens:
            if tok not in per_tokens:
                per_tokens.append(int(tok))
            token_exchange_hint[int(tok)] = str(exchange).upper()
        if index_token:
            token_to_symbol[int(index_token)] = sym_upper
        selected_strikes: dict[float, set[str]] = {}
        for tok in per_tokens:
            meta = option_meta.get(int(tok)) or {}
            strike = meta.get("strike")
            opt_type = str(meta.get("instrument_type") or "").upper()
            if strike is not None and opt_type in {"CE", "PE"}:
                selected_strikes.setdefault(float(strike), set()).add(opt_type)
            try:
                token_to_symbol[int(tok)] = sym_upper
            except Exception:
                continue

        tokens.extend(per_tokens)
        resolution.append(
            {
                "symbol": sym_upper,
                "exchange": exchange,
                "expiry": expiry,
                "ltp": ltp,
                "ltp_source": ltp_source,
                "atm": atm,
                "strikes_around": strikes_around,
                "step": step,
                "tokens": list(per_tokens),
                "count": len(per_tokens),
                "resolved_count": len(per_tokens),
                "option_count": len(option_tokens),
                "resolved_option_count": len(option_tokens),
                "option_min_required": min_option_tokens,
                "option_fail_reason": option_fail_reason,
                "option_coverage_status": option_coverage_status,
                "option_coverage_reason": option_coverage_reason,
                "option_strikes_selected": sorted(selected_strikes.keys()),
                "option_strike_count": len(selected_strikes),
                "option_two_sided_strike_count": sum(1 for legs in selected_strikes.values() if {"CE", "PE"}.issubset(legs)),
                "index_token": index_token,
                "index_token_source": index_source if index_token else "missing",
            }
        )

    if sticky_tokens:
        sticky_list = sorted(int(t) for t in sticky_tokens if int(t) > 0)
        tokens.extend(sticky_list)
        for tok in sticky_list:
            token_to_symbol.setdefault(int(tok), "STICKY")

    tokens = list(dict.fromkeys(tokens))
    _UNDERLYING_TOKENS = set(int(t) for t in underlying_tokens if t is not None)
    _UNDERLYING_TOKEN_TO_SYMBOL = dict(underlying_token_to_symbol)
    _TOKEN_TO_SYMBOL = dict(token_to_symbol)
    _UNDERLYING_LOGGED_MISSING = False
    _LAST_OPTION_COUNTS_BY_SYMBOL = {
        str(row.get("symbol") or "").upper(): int(row.get("option_count") or 0)
        for row in resolution
        if str(row.get("symbol") or "").strip()
    }
    _LAST_OPTION_MIN_REQUIRED_BY_SYMBOL = {
        str(row.get("symbol") or "").upper(): int(row.get("option_min_required") or 0)
        for row in resolution
        if str(row.get("symbol") or "").strip()
    }

    preserve_tokens: set[int] = set(int(t) for t in _UNDERLYING_TOKENS)
    preserve_tokens.update(int(t) for t in sticky_tokens if t is not None)
    preserve_tokens.update(int(t) for t in option_rank_by_token.keys())

    min_required_by_symbol = dict(_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL or {})
    # Prevent prune starvation: enforce a per-symbol minimum floor, but still allow
    # pruning far/illiquid strikes so the band stays ATM-focused.
    try:
        floor_default = int(getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MIN_REQUIRED_FLOOR", 14) or 14)
    except Exception:
        floor_default = 14
    floor_by_symbol = getattr(cfg, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MIN_REQUIRED_FLOOR_BY_SYMBOL", {}) or {}
    for sym, resolved_count in dict(_LAST_OPTION_COUNTS_BY_SYMBOL or {}).items():
        sym_key = str(sym or "").upper()
        try:
            floor = int(floor_by_symbol.get(sym_key, floor_default) or floor_default)
        except Exception:
            floor = floor_default
        # Never demand more than the resolved window for this cycle.
        floor = max(0, min(int(floor), int(resolved_count or 0)))
        current = int(min_required_by_symbol.get(sym_key, 0) or 0)
        min_required_by_symbol[sym_key] = max(current, floor)

    tokens, prune_meta = _prune_stale_option_subscription_tokens(
        tokens=tokens,
        option_rank_by_token=option_rank_by_token,
        token_to_symbol=token_to_symbol,
        min_required_by_symbol=min_required_by_symbol,
    )
    pruned_tokens = [int(t) for t in list(prune_meta.get("pruned_tokens") or [])]
    if pruned_tokens:
        _log_ws(
            "FEED_OPTION_SUBSCRIPTIONS_PRUNED_STALE",
            {
                "pruned_count": int(prune_meta.get("pruned_count") or 0),
                "kept_count": int(prune_meta.get("kept_count") or 0),
                "max_age_sec": float(prune_meta.get("max_age_sec") or 0.0),
                "pruned_by_symbol": dict(prune_meta.get("pruned_by_symbol") or {}),
                "stale_samples": list(prune_meta.get("stale_samples") or [])[:10],
            },
        )
        for tok in pruned_tokens:
            option_rank_by_token.pop(int(tok), None)

    if validate_tokens:
        def _count_by_exchange(token_list: list[int]) -> dict[str, int]:
            counts: dict[str, int] = {}
            for token in token_list:
                exchange_key = str(token_exchange_hint.get(int(token), "UNKNOWN")).upper()
                counts[exchange_key] = int(counts.get(exchange_key, 0)) + 1
            return counts

        known_tokens: set[int] = set()
        try:
            for exch in ("NFO", "BFO", "NSE", "BSE"):
                for inst in kite_client.instruments_cached(exch, ttl_sec=getattr(cfg, "KITE_INSTRUMENTS_TTL", 3600)):
                    tok = inst.get("instrument_token")
                    if tok is not None:
                        try:
                            known_tokens.add(int(tok))
                        except Exception:
                            continue
        except Exception:
            known_tokens = set()
        if known_tokens:
            before_tokens = [int(t) for t in tokens]
            before = len(before_tokens)
            before_counts = _count_by_exchange(before_tokens)
            tokens = [t for t in before_tokens if int(t) in known_tokens or int(t) in preserve_tokens]
            kept_set = set(int(t) for t in tokens)
            dropped_tokens = [int(t) for t in before_tokens if int(t) not in kept_set]
            dropped = len(dropped_tokens)
            dropped_counts = _count_by_exchange(dropped_tokens)
            after_counts = _count_by_exchange([int(t) for t in tokens])
            _log_ws(
                "FEED_TOKEN_FILTER_COUNTS",
                {
                    "before_total": before,
                    "after_total": len(tokens),
                    "dropped_total": dropped,
                    "before_by_exchange": before_counts,
                    "after_by_exchange": after_counts,
                    "dropped_by_exchange": dropped_counts,
                    "kept_resolver_option_tokens": len(
                        [t for t in tokens if int(t) in option_rank_by_token]
                    ),
                },
            )
            if dropped > 0:
                _log_ws(
                    "FEED_TOKEN_FILTERED",
                    {
                        "dropped": dropped,
                        "kept": len(tokens),
                        "dropped_sample": dropped_tokens[:20],
                    },
                )
            dropped_bfo = [int(t) for t in dropped_tokens if str(token_exchange_hint.get(int(t), "")).upper() == "BFO"]
            if dropped_bfo:
                _log_ws(
                    "FEED_TOKEN_FILTERED_BFO_DROPPED",
                    {
                        "reason": "validate_tokens_not_in_known_universe",
                        "count": len(dropped_bfo),
                        "sample_tokens": dropped_bfo[:20],
                    },
                )

    tokens, truncated, budget_meta = _enforce_subscription_budget(
        tokens,
        max_tokens=max_tokens,
        option_rank_by_token=option_rank_by_token,
        underlying_tokens=_UNDERLYING_TOKENS,
        sticky_tokens=sticky_tokens,
        active_trade_tokens=active_trade_tokens,
    )
    try:
        observation_registry = load_observation_registry(force=False)
    except Exception as exc:
        reset_market_event_graph_observation_plan_state()
        _log_ws(
            "MARKET_EVENT_GRAPH_OBSERVATION_PLAN_BLOCKED",
            {"reason": f"registry_load_failed:{type(exc).__name__}:{exc}"},
        )
        observation_registry = None
    if observation_registry is not None:
        observation_token_list = [int(token) for token in observation_registry.all_tokens]
        merge = build_observation_subscription_merge(
            production_tokens=[int(token) for token in tokens],
            observation_tokens=observation_token_list,
            budget=max_tokens,
        )
        plan = {
            "ok": bool(merge.get("ok")),
            "verdict": (
                "PASS_LIVE_SOURCE_PRESESSION_READINESS"
                if bool(merge.get("ok"))
                else str(merge.get("reason") or BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET)
            ),
            "production_tokens": [int(token) for token in tokens],
            "observation_tokens": observation_token_list,
            "final_union_tokens": [int(token) for token in list(merge.get("tokens") or [])],
            "missing_observation_tokens": [int(token) for token in list(merge.get("missing_or_pruned_observation_tokens") or [])],
            "configured_budget": max_tokens,
            "launch_plan_sha256": str(getattr(observation_registry, "canonical_sha256", "") or ""),
        }
        activate_market_event_graph_launch_plan(plan)
        if bool(merge.get("ok")):
            tokens = [int(token) for token in list(merge.get("tokens") or [])]
            for symbol, token in dict(observation_registry.token_by_symbol).items():
                _TOKEN_TO_SYMBOL[int(token)] = str(symbol).upper()
        else:
            _log_ws(
                "MARKET_EVENT_GRAPH_OBSERVATION_PLAN_BLOCKED",
                {
                    "reason": str(merge.get("reason") or BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION_BUDGET),
                    "production_token_count": len(tokens),
                    "observation_token_count": len(observation_token_list),
                    "configured_budget": max_tokens,
                    "missing_observation_tokens": list(merge.get("missing_or_pruned_observation_tokens") or [])[:20],
                },
            )
    else:
        reset_market_event_graph_observation_plan_state()

    final_tokens_by_symbol: dict[str, list[int]] = {}
    final_option_counts_by_symbol: dict[str, int] = {}
    for tok in list(tokens or []):
        try:
            tok_int = int(tok)
        except Exception:
            continue
        symbol = str(_TOKEN_TO_SYMBOL.get(tok_int) or "").upper()
        if not symbol or symbol == "STICKY":
            continue
        final_tokens_by_symbol.setdefault(symbol, []).append(tok_int)
        if not _is_underlying_token(tok_int):
            final_option_counts_by_symbol[symbol] = int(final_option_counts_by_symbol.get(symbol, 0)) + 1

    for row in resolution:
        symbol = str(row.get("symbol") or "").upper()
        final_tokens_for_symbol = list(final_tokens_by_symbol.get(symbol, []))
        final_option_count = int(final_option_counts_by_symbol.get(symbol, 0))
        row["tokens"] = final_tokens_for_symbol
        row["count"] = len(final_tokens_for_symbol)
        row["final_count"] = len(final_tokens_for_symbol)
        row["option_count"] = final_option_count
        row["final_option_count"] = final_option_count
        row["stale_option_pruned_count"] = int((prune_meta.get("pruned_by_symbol") or {}).get(symbol, 0) or 0)
        row["stale_option_prune_enabled"] = bool(prune_meta.get("enabled"))
        row["stale_option_prune_max_age_sec"] = float(prune_meta.get("max_age_sec") or 0.0)
        row["stale_option_prune_require_session_tick"] = bool(prune_meta.get("require_session_tick"))
        row["stale_option_pruned_sample_tokens"] = [int(t) for t in list(prune_meta.get("pruned_tokens") or [])[:10]]
        row["stale_option_session_tick_skipped_count_by_symbol"] = dict(
            prune_meta.get("session_tick_skipped_by_symbol") or {}
        )
        row["option_drop_reason"] = row.get("option_fail_reason")
        if not row.get("option_drop_reason") and final_option_count < int(row.get("resolved_option_count") or 0):
            row["option_drop_reason"] = (
                "stale_option_subscription_pruned"
                if bool(prune_meta.get("pruned_count"))
                else (
                    "subscription_budget_truncated"
                    if bool(truncated)
                    else "option_tokens_filtered"
                )
            )
        min_required = int(row.get("option_min_required") or 0)
        if min_required > 0 and final_option_count < min_required and not row.get("option_fail_reason"):
            row["option_fail_reason"] = (
                "option_tokens_pruned_below_min"
                if bool(prune_meta.get("pruned_count"))
                else "option_tokens_under_min"
            )
            if not row.get("option_drop_reason"):
                row["option_drop_reason"] = (
                    "stale_option_subscription_pruned"
                    if bool(prune_meta.get("pruned_count"))
                    else "option_tokens_under_min"
                )
    _LAST_OPTION_COUNTS_BY_SYMBOL = {
        str(row.get("symbol") or "").upper(): int(row.get("option_count") or 0)
        for row in resolution
        if str(row.get("symbol") or "").strip()
    }

    try:
        out = logs_dir() / "token_resolution.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(resolution, indent=2, default=str))
    except Exception:
        pass

    _log_ws(
        "FEED_TOKEN_SELECTION",
        {
            "total_tokens": len(tokens),
            "max_tokens": max_tokens,
            "truncated": truncated,
            "per_symbol": {r["symbol"]: r.get("count", 0) for r in resolution},
            "option_tokens_resolved_count_by_symbol": {
                r["symbol"]: int(r.get("resolved_option_count") or 0) for r in resolution
            },
            "option_tokens_subscribed_count_by_symbol": {
                r["symbol"]: int(r.get("option_count") or 0) for r in resolution
            },
            "option_drop_reason_by_symbol": {
                r["symbol"]: str(r.get("option_drop_reason") or "")
                for r in resolution
                if str(r.get("option_drop_reason") or "").strip()
            },
            "underlying_tokens": list(_UNDERLYING_TOKENS),
            "sticky_tokens": sorted(int(t) for t in sticky_tokens if t is not None),
            "active_trade_tokens": sorted(int(t) for t in active_trade_tokens if t is not None),
            "underlying_token_to_symbol": dict(_UNDERLYING_TOKEN_TO_SYMBOL),
            "budget_dropped_tokens": int((budget_meta or {}).get("dropped_count", 0)),
            "sample_tokens": tokens[:10],
        },
    )
    desired_tokens = _normalize_positive_tokens(tokens)
    _LAST_DESIRED_TOKENS = desired_tokens or None
    return tokens, resolution


def _resolution_atm_step_and_underlyings(resolution: list[dict] | None) -> tuple[dict[str, int], dict[str, float], set[int]]:
    atm_by_symbol: dict[str, int] = {}
    step_by_symbol: dict[str, float] = {}
    underlying_tokens: set[int] = set()
    for row in list(resolution or []):
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        if symbol:
            atm_val = row.get("atm")
            step_val = row.get("step")
            try:
                if atm_val is not None:
                    atm_by_symbol[symbol] = int(float(atm_val))
            except Exception:
                pass
            try:
                if step_val is not None:
                    step_by_symbol[symbol] = float(step_val)
            except Exception:
                pass
        try:
            idx = int(row.get("index_token"))
        except Exception:
            idx = None
        if idx is not None and idx > 0:
            underlying_tokens.add(idx)
    return atm_by_symbol, step_by_symbol, underlying_tokens


def _max_atm_shift_steps(
    prev_atm_by_symbol: dict[str, int] | None,
    next_atm_by_symbol: dict[str, int] | None,
    step_by_symbol: dict[str, float] | None,
) -> float:
    prev = dict(prev_atm_by_symbol or {})
    nxt = dict(next_atm_by_symbol or {})
    step_map = dict(step_by_symbol or {})
    max_shift = 0.0
    for symbol in set(prev.keys()) | set(nxt.keys()):
        if symbol not in prev or symbol not in nxt:
            continue
        step = float(step_map.get(symbol, 0.0) or 0.0)
        if step <= 0.0:
            continue
        diff = abs(float(nxt[symbol]) - float(prev[symbol]))
        shift_steps = diff / step
        if shift_steps > max_shift:
            max_shift = shift_steps
    return float(max_shift)


def _compute_silent_reconnect_action(
    *,
    now_epoch: float,
    current_tokens: set[int],
    underlying_tokens: set[int],
    last_global_msg_epoch: float | None,
    last_msg_by_token: dict[int, float] | None,
    index_threshold_sec: float,
    option_threshold_sec: float,
    confirm_hits: int,
    confirm_needed: int,
    last_reconnect_epoch: float,
    backoff_min_sec: float,
    backoff_max_sec: float,
) -> dict:
    tracked_tokens = sorted(int(t) for t in (current_tokens or set()) if int(t) > 0)
    if not tracked_tokens:
        return {
            "silent_detected": False,
            "should_reconnect": False,
            "confirm_hits": 0,
            "reason": "no_tokens",
            "global_age_sec": None,
            "stale_tokens": 0,
            "tracked_tokens": 0,
            "backoff_sec": None,
        }
    if not isinstance(last_global_msg_epoch, (int, float)) or float(last_global_msg_epoch) <= 0.0:
        return {
            "silent_detected": False,
            "should_reconnect": False,
            "confirm_hits": 0,
            "reason": "no_messages_yet",
            "global_age_sec": None,
            "stale_tokens": 0,
            "tracked_tokens": len(tracked_tokens),
            "backoff_sec": None,
        }
    has_underlying = any(int(tok) in set(underlying_tokens or set()) for tok in tracked_tokens)
    global_threshold = float(index_threshold_sec if has_underlying else option_threshold_sec)
    global_age_sec = max(0.0, float(now_epoch) - float(last_global_msg_epoch))

    msg_map = dict(last_msg_by_token or {})
    underlying_set = set(int(t) for t in (underlying_tokens or set()) if int(t) > 0)
    stale_tokens = 0
    index_stale = 0
    option_stale = 0
    for tok in tracked_tokens:
        threshold = float(index_threshold_sec if tok in underlying_set else option_threshold_sec)
        token_last = msg_map.get(int(tok), float(last_reconnect_epoch))
        token_age = max(0.0, float(now_epoch) - float(token_last))
        if token_age > threshold:
            stale_tokens += 1
            if tok in underlying_set:
                index_stale += 1
            else:
                option_stale += 1

    if stale_tokens == 0:
        return {
            "silent_detected": False,
            "should_reconnect": False,
            "confirm_hits": 0,
            "reason": "global_age_within_threshold",
            "global_age_sec": global_age_sec,
            "stale_tokens": 0,
            "tracked_tokens": len(tracked_tokens),
            "backoff_sec": None,
        }

    if stale_tokens < len(tracked_tokens):
        return {
            "silent_detected": False,
            "should_reconnect": False,
            "confirm_hits": 0,
            "reason": "partial_activity_detected",
            "global_age_sec": global_age_sec,
            "stale_tokens": stale_tokens,
            "tracked_tokens": len(tracked_tokens),
            "backoff_sec": None,
        }

    new_hits = int(confirm_hits) + 1
    needed = max(1, int(confirm_needed))
    if new_hits < needed:
        return {
            "silent_detected": True,
            "should_reconnect": False,
            "confirm_hits": new_hits,
            "reason": "awaiting_confirmation",
            "global_age_sec": global_age_sec,
            "stale_tokens": stale_tokens,
            "tracked_tokens": len(tracked_tokens),
            "backoff_sec": None,
            "index_stale": index_stale,
            "option_stale": option_stale,
        }

    exponent = max(0, int(new_hits) - needed)
    backoff_sec = min(float(backoff_max_sec), float(backoff_min_sec) * (2 ** exponent))
    should_reconnect = (float(now_epoch) - float(last_reconnect_epoch)) >= float(backoff_sec)
    return {
        "silent_detected": True,
        "should_reconnect": bool(should_reconnect),
        "confirm_hits": new_hits,
        "reason": "silent_failure_confirmed",
        "global_age_sec": global_age_sec,
        "stale_tokens": stale_tokens,
        "tracked_tokens": len(tracked_tokens),
        "backoff_sec": float(backoff_sec),
        "index_stale": index_stale,
        "option_stale": option_stale,
    }


def _classify_silence_bucket(action: dict[str, object], *, feed_breaker_open: bool) -> str:
    index_stale = int(action.get("index_stale") or 0)
    option_stale = int(action.get("option_stale") or 0)
    stale_tokens = int(action.get("stale_tokens") or 0)
    tracked_tokens = int(action.get("tracked_tokens") or 0)
    if feed_breaker_open:
        return "breaker_blocked_recovery"
    if stale_tokens <= 0 or tracked_tokens <= 0:
        return "unknown"
    if index_stale > 0 and option_stale > 0:
        return "upstream_ws_silence"
    if index_stale > 0:
        return "index_only_silence"
    if option_stale > 0:
        return "option_only_silence"
    return "mixed_activity"


def _maybe_trigger_silent_reconnect(
    *,
    now_epoch: float,
    current_tokens: set[int],
    underlying_tokens: set[int],
    last_global_msg_epoch: float | None,
    last_msg_by_token: dict[int, float] | None,
    state: dict,
    index_threshold_sec: float,
    option_threshold_sec: float,
    confirm_needed: int,
    backoff_min_sec: float,
    backoff_max_sec: float,
    force_full_restart_after_sec: float | None,
    restart_cb,
) -> bool:
    action = _compute_silent_reconnect_action(
        now_epoch=now_epoch,
        current_tokens=current_tokens,
        underlying_tokens=underlying_tokens,
        last_global_msg_epoch=last_global_msg_epoch,
        last_msg_by_token=last_msg_by_token,
        index_threshold_sec=index_threshold_sec,
        option_threshold_sec=option_threshold_sec,
        confirm_hits=int(state.get("confirm_hits", 0)),
        confirm_needed=int(confirm_needed),
        last_reconnect_epoch=float(state.get("last_reconnect_epoch", 0.0) or 0.0),
        backoff_min_sec=float(backoff_min_sec),
        backoff_max_sec=float(backoff_max_sec),
    )
    if action.get("reason") == "partial_activity_detected":
        _transition_partial_activity_recovery(
            now_epoch=float(now_epoch),
            current_tokens=set(current_tokens or set()),
            underlying_tokens=set(underlying_tokens or set()),
            last_msg_by_token=last_msg_by_token,
            index_threshold_sec=float(index_threshold_sec),
            option_threshold_sec=float(option_threshold_sec),
        )
    elif action.get("stale_tokens") == 0 and str(_RUNTIME_STATE or "").strip().upper() in {"DEGRADED_LOCAL", "VERIFYING_RECOVERY"}:
        _clear_reconnect_blocked_reason()
        globals()["_RUNTIME_STATE"] = "LIVE"

    if not bool(action.get("silent_detected")):
        state["confirm_hits"] = 0
        return False

    state["confirm_hits"] = int(action.get("confirm_hits", 0))
    feed_breaker_open = bool(feed_breaker_tripped())
    silence_bucket = _classify_silence_bucket(action, feed_breaker_open=feed_breaker_open)
    _log_ws(
        "FEED_SILENT_WARNING",
        {
            "reason": action.get("reason"),
            "global_age_sec": action.get("global_age_sec"),
            "tracked_tokens": action.get("tracked_tokens"),
            "stale_tokens": action.get("stale_tokens"),
            "index_stale": action.get("index_stale"),
            "option_stale": action.get("option_stale"),
            "confirm_hits": state.get("confirm_hits", 0),
            "confirm_needed": int(confirm_needed),
            "backoff_sec": action.get("backoff_sec"),
        },
    )
    _log_ws(
        "FEED_SILENCE_RCA",
        {
            "silence_bucket": silence_bucket,
            "feed_breaker_open": feed_breaker_open,
            "reason": action.get("reason"),
            "global_age_sec": action.get("global_age_sec"),
            "tracked_tokens": action.get("tracked_tokens"),
            "stale_tokens": action.get("stale_tokens"),
            "index_stale": action.get("index_stale"),
            "option_stale": action.get("option_stale"),
            "confirm_hits": state.get("confirm_hits", 0),
            "confirm_needed": int(confirm_needed),
        },
    )
    if not bool(action.get("should_reconnect")):
        return False

    state["last_reconnect_epoch"] = float(now_epoch)
    reason = (
        f"silent_feed age={float(action.get('global_age_sec') or 0.0):.2f}s "
        f"stale={int(action.get('stale_tokens') or 0)}/{int(action.get('tracked_tokens') or 0)}"
    )
    force_full_restart = False
    if isinstance(force_full_restart_after_sec, (int, float)):
        force_full_restart = float(action.get("global_age_sec") or 0.0) >= float(force_full_restart_after_sec)
    if force_full_restart:
        _log_ws(
            "FEED_SILENT_FORCE_FULL_RESTART",
            {
                "reason": reason,
                "global_age_sec": action.get("global_age_sec"),
                "tracked_tokens": action.get("tracked_tokens"),
                "stale_tokens": action.get("stale_tokens"),
                "confirm_hits": state.get("confirm_hits", 0),
                "force_full_restart_after_sec": float(force_full_restart_after_sec),
            },
        )
    try:
        restart_cb(reason=reason, ignore_cooldown=True, force_full_restart=force_full_restart)
    except TypeError:
        restart_cb(reason=reason)
    return True


def _compute_rebalance_decision(
    *,
    current_tokens: set[int],
    desired_tokens: set[int],
    sticky_tokens: set[int],
    underlying_tokens: set[int],
    last_rebalance_ts: float | None,
    now_ts: float,
    cooldown_sec: float,
    threshold_steps: float,
    last_atm_by_symbol: dict[str, int] | None,
    next_atm_by_symbol: dict[str, int] | None,
    step_by_symbol: dict[str, float] | None,
) -> dict:
    current = set(int(t) for t in (current_tokens or set()) if int(t) > 0)
    sticky = set(int(t) for t in (sticky_tokens or set()) if int(t) > 0)
    underlying = set(int(t) for t in (underlying_tokens or set()) if int(t) > 0)
    desired = set(int(t) for t in (desired_tokens or set()) if int(t) > 0)
    preserve = set(underlying) | set(sticky)
    desired_full = set(desired) | set(preserve)
    shift_steps = _max_atm_shift_steps(last_atm_by_symbol, next_atm_by_symbol, step_by_symbol)
    has_shift = shift_steps >= float(threshold_steps)
    rebalance_age = None
    if isinstance(last_rebalance_ts, (int, float)):
        rebalance_age = max(0.0, float(now_ts) - float(last_rebalance_ts))
    cooldown_ok = rebalance_age is None or rebalance_age >= float(cooldown_sec)

    mandatory_missing = set(preserve) - set(current)
    first_run = not bool(current)
    should_rebalance = False
    reason = "rebalance_skipped"
    if first_run:
        should_rebalance = True
        reason = "initial_subscribe"
    elif mandatory_missing:
        should_rebalance = True
        reason = "preserve_tokens_missing"
    elif has_shift and cooldown_ok:
        should_rebalance = True
        reason = f"atm_shift_steps={shift_steps:.2f}"
    elif has_shift and (not cooldown_ok):
        reason = f"cooldown_blocked shift_steps={shift_steps:.2f}"
    else:
        reason = f"atm_shift_below_threshold shift_steps={shift_steps:.2f}"

    subscribe_tokens = sorted(int(t) for t in (desired_full - current))
    unsubscribe_tokens = sorted(int(t) for t in ((current - desired_full) - preserve))
    final_tokens = sorted((current | set(subscribe_tokens)) - set(unsubscribe_tokens))
    if should_rebalance and not subscribe_tokens and not unsubscribe_tokens:
        should_rebalance = False
        reason = "no_token_delta"

    return {
        "should_rebalance": bool(should_rebalance),
        "reason": str(reason),
        "shift_steps": float(shift_steps),
        "cooldown_ok": bool(cooldown_ok),
        "cooldown_age_sec": rebalance_age,
        "subscribe_tokens": subscribe_tokens,
        "unsubscribe_tokens": unsubscribe_tokens,
        "preserve_tokens": sorted(preserve),
        "final_tokens": final_tokens,
        "next_atm_by_symbol": dict(next_atm_by_symbol or {}),
    }


def ensure_subscribed_tokens(tokens: list[int], reason: str = "on_demand", symbol: str | None = None) -> bool:
    global _LAST_TOKENS, _TOKEN_TO_SYMBOL
    if not tokens:
        return False
    tokens = [int(t) for t in tokens if t is not None]
    if not tokens:
        return False
    can_mutate, guard_reason, guard_payload = _can_mutate_ws_subscriptions(reason=reason)
    if not can_mutate:
        _log_ws("FEED_SUBSCRIBE_SKIPPED", {**guard_payload, "guard_reason": guard_reason, "token_count": len(tokens)})
        return False
    with _KITE_TICKER_LOCK:
        if _KITE_TICKER is None:
            _log_ws("FEED_SUBSCRIBE_SKIPPED", {"reason": reason, "detail": "ws_not_running"})
            return False
        existing = set(int(t) for t in (_LAST_TOKENS or []))
        new_tokens = [t for t in tokens if t not in existing]
        if not new_tokens:
            return True
        try:
            client_mode_before = _client_mode_for_token(_KITE_TICKER, 256265)
            _record_ws_subscription_operation(
                _KITE_TICKER,
                new_tokens,
                callsite="ensure_subscribed_tokens",
                operation="subscribe",
                reason=reason,
                local_call_result="dispatched",
                client_mode_before=client_mode_before,
                socket_generation=int(_SOCKET_GENERATION),
            )
            _KITE_TICKER.subscribe(new_tokens)
            _record_subscription_request_succeeded(new_tokens)
            client_mode_after_subscribe = _client_mode_for_token(_KITE_TICKER, 256265)
            _record_ws_subscription_operation(
                _KITE_TICKER,
                new_tokens,
                callsite="ensure_subscribed_tokens",
                operation="subscribe",
                reason=reason,
                local_call_result="succeeded",
                client_mode_before=client_mode_before,
                client_mode_after=client_mode_after_subscribe,
                socket_generation=int(_SOCKET_GENERATION),
            )
            client_mode_before_mode = _client_mode_for_token(_KITE_TICKER, 256265)
            _record_ws_subscription_operation(
                _KITE_TICKER,
                new_tokens,
                callsite="ensure_subscribed_tokens",
                operation="set_mode",
                requested_mode="full",
                reason=reason,
                local_call_result="dispatched",
                client_mode_before=client_mode_before_mode,
                socket_generation=int(_SOCKET_GENERATION),
            )
            _KITE_TICKER.set_mode(_KITE_TICKER.MODE_FULL, new_tokens)
            _record_mode_request_succeeded(new_tokens)
            _record_ws_subscription_operation(
                _KITE_TICKER,
                new_tokens,
                callsite="ensure_subscribed_tokens",
                operation="set_mode",
                requested_mode="full",
                reason=reason,
                local_call_result="succeeded",
                client_mode_before=client_mode_before_mode,
                client_mode_after=_client_mode_for_token(_KITE_TICKER, 256265),
                socket_generation=int(_SOCKET_GENERATION),
            )
            _LAST_TOKENS = list(existing.union(set(new_tokens)))
            if symbol:
                for tok in new_tokens:
                    _TOKEN_TO_SYMBOL.setdefault(int(tok), str(symbol))
            _log_ws("FEED_SUBSCRIBE_OK", {"reason": reason, "tokens": len(new_tokens)})
            return True
        except Exception as exc:
            _record_ws_subscription_operation(
                _KITE_TICKER,
                new_tokens,
                callsite="ensure_subscribed_tokens",
                operation="subscribe_or_set_mode",
                requested_mode="full",
                reason=reason,
                local_call_result="exception",
                exception_type=type(exc).__name__,
                socket_generation=int(_SOCKET_GENERATION),
            )
            _log_ws("FEED_SUBSCRIBE_ERROR", {"reason": reason, "error": str(exc)})
            return False


def _ensure_depth_ws_lock() -> bool:
    global _DEPTH_WS_LOCK, _DEPTH_WS_LOCK_ACQUIRED
    if _DEPTH_WS_LOCK_ACQUIRED:
        return True
    _DEPTH_WS_LOCK = RunLock(
        name=getattr(cfg, "DEPTH_WS_LOCK_NAME", "depth_ws.lock"),
        max_age_sec=getattr(cfg, "DEPTH_WS_LOCK_MAX_AGE_SEC", 3600),
    )
    ok, reason = _DEPTH_WS_LOCK.acquire()
    if not ok:
        state = _DEPTH_WS_LOCK.state_dict()
        _log_ws("FEED_LOCK_BLOCKED", {"reason": reason, "state": state})
        logger.warning("depth_ws_lock_blocked reason=%s state=%s", reason, state)
        return False
    _DEPTH_WS_LOCK_ACQUIRED = True
    atexit.register(_DEPTH_WS_LOCK.release)
    lifecycle.register_resource("depth-ws-lock", _DEPTH_WS_LOCK.release)
    return True


def _close_ticker_instance(instance):
    if instance is None:
        return
    for method_name in ("close", "disconnect"):
        method = getattr(instance, method_name, None)
        if callable(method):
            try:
                method()
            except Exception as exc:
                _log_ws("FEED_CLOSE_ERROR", {"method": method_name, "error": str(exc)})


def _join_thread_safe(thread_obj, timeout_sec: float) -> None:
    if thread_obj is None:
        return
    try:
        if thread_obj.is_alive():
            thread_obj.join(max(0.0, float(timeout_sec)))
    except Exception:
        return


def _join_ticker_threads(instance, timeout_sec: float) -> None:
    if instance is None:
        return
    for attr_name in ("ws_thread", "_ws_thread", "thread", "_thread", "_run_thread"):
        thread_obj = getattr(instance, attr_name, None)
        _join_thread_safe(thread_obj, timeout_sec)
        ws_obj = getattr(thread_obj, "ws", None)
        ws_thread = getattr(ws_obj, "thread", None)
        _join_thread_safe(ws_thread, timeout_sec)


def _schedule_restart_depth_ws(
    *,
    reason: str,
    ignore_cooldown: bool = False,
    force_full_restart: bool = False,
    source: str,
) -> bool:
    global _RESTART_ASYNC_THREAD
    if bool(getattr(_FEED_RECOVERY_COORDINATOR.state, "recovery_in_progress", False)):
        _log_ws(
            "FEED_RECOVERY_ALREADY_IN_PROGRESS",
            {"reason": reason, "source": source, "force_full_restart": bool(force_full_restart)},
        )
        return False
    if _RECOVERY_IN_PROGRESS:
        _log_ws(
            "FEED_RECOVERY_ALREADY_IN_PROGRESS",
            {"reason": reason, "source": source, "force_full_restart": bool(force_full_restart)},
        )
        return False
    if _reconnect_recovery_blocked_active() or _reactor_terminal_restart_block_active():
        blocked_reason = str(_RECONNECT_BLOCKED_REASON or "").strip().lower() or _reactor_not_restartable_block_reason()
        _emit_reconnect_recovery_blocked_snapshot(source=f"_schedule_restart_depth_ws:{source}", reason=blocked_reason)
        return False

    with _RESTART_ASYNC_LOCK:
        existing = _RESTART_ASYNC_THREAD
        if existing is not None:
            try:
                if existing.is_alive():
                    _log_ws(
                        "FEED_RESTART_ASYNC_ALREADY_SCHEDULED",
                        {
                            "reason": reason,
                            "source": source,
                            "force_full_restart": bool(force_full_restart),
                        },
                    )
                    return True
            except Exception:
                pass

        thread_ref = {"thread": None}

        def _runner():
            try:
                restart_depth_ws(
                    reason=reason,
                    ignore_cooldown=ignore_cooldown,
                    force_full_restart=force_full_restart,
                )
            finally:
                global _RESTART_ASYNC_THREAD
                with _RESTART_ASYNC_LOCK:
                    if _RESTART_ASYNC_THREAD is thread_ref["thread"]:
                        _RESTART_ASYNC_THREAD = None

        thread_obj = threading.Thread(target=_runner, daemon=True)
        thread_ref["thread"] = thread_obj
        _RESTART_ASYNC_THREAD = thread_obj

    _log_ws(
        "FEED_RESTART_ASYNC_SCHEDULED",
        {
            "reason": reason,
            "source": source,
            "force_full_restart": bool(force_full_restart),
            "ignore_cooldown": bool(ignore_cooldown),
        },
    )
    thread_obj.start()
    return True


def _should_ignore_restart_cooldown_for_ws_fault(*, code: int | None, reason_text: str | None) -> bool:
    """
    Only bypass the full-restart cooldown for hard websocket faults that leave the feed dead in practice.

    This does NOT bypass:
    - hourly restart limits
    - restart-storm breaker
    - feed_restart_guard
    """
    try:
        code_int = int(code) if code is not None else None
    except Exception:
        code_int = None
    if code_int == 1006:
        return True
    _ = reason_text
    return False


def _state_identity_payload() -> dict[str, object]:
    import sys

    module = sys.modules.get("core.kite_depth_ws")
    return {
        "module_name": __name__,
        "module_file": __file__,
        "module_id": id(module),
        "last_msg_state_id": id(_LAST_MSG_TS_BY_TOKEN),
        "latest_observation_packet_state_id": id(_LATEST_OBSERVATION_PACKET_BY_TOKEN),
    }


def _coerce_generation(value: object, *, default: int = -1) -> int:
    if value is None:
        return int(default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _record_observation_callback_truth(
    *,
    tick: Mapping[str, Any],
    instrument_token: int,
    callback_receipt_epoch: float,
    source_tick_epoch: float | None,
) -> dict[str, object] | None:
    try:
        token_int = int(instrument_token)
    except Exception:
        return None
    try:
        observation_registry = load_observation_registry(force=False)
    except Exception:
        observation_registry = None
    if observation_registry is None:
        return None
    observation_identity = observation_registry.observation_identity(token_int)
    if observation_identity is None:
        return None
    observation_state = _observation_state_payload()
    feed_identity = get_current_feed_session_identity()
    symbol = str((observation_identity or {}).get("symbol") or "").upper()
    instrument_class = str((observation_identity or {}).get("instrument_class") or "UNKNOWN")
    depth = tick.get("depth") if isinstance(tick, Mapping) else None
    has_depth = _depth_has_bid_ask(depth)
    mode_epoch = _MODE_REQUEST_SUCCEEDED_EPOCH_BY_TOKEN.get(token_int)
    packet_kind, raw_full_payload, packet_detail = _observation_packet_full_status(
        dict(tick),
        instrument_token=token_int,
        instrument_class=instrument_class,
        receipt_epoch=float(callback_receipt_epoch),
        source_tick_epoch=source_tick_epoch,
        mode_success_epoch=mode_epoch,
        feed_session_id=str(feed_identity.get("feed_session_id") or ""),
        reconnect_generation=_coerce_generation(feed_identity.get("reconnect_generation"), default=-1),
        has_depth=has_depth,
    )
    active_plan_tokens = set(int(tok) for tok in (observation_state.get("observation_tokens") or []))
    token_in_active_plan = token_int in active_plan_tokens
    feed_session_matches = str(observation_state.get("feed_session_id") or "") == str(feed_identity.get("feed_session_id") or "")
    plan_generation = _coerce_generation(observation_state.get("reconnect_generation"), default=-1)
    feed_generation = _coerce_generation(feed_identity.get("reconnect_generation"), default=-1)
    reconnect_generation_matches = plan_generation == feed_generation
    subscription_send_recorded = token_int in _SUBSCRIPTION_REQUEST_SUCCEEDED_TOKENS
    mode_full_is_final = token_int in _MODE_COMMAND_FINAL_FULL_TOKENS
    post_mode_callback = bool(mode_epoch is not None and float(callback_receipt_epoch) > float(mode_epoch))
    plan_enabled = bool(observation_state.get("enabled")) and str(observation_state.get("verdict") or "") == "PASS_LIVE_SOURCE_PRESESSION_READINESS"
    accepted_context = bool(
        plan_enabled
        and token_in_active_plan
        and feed_session_matches
        and reconnect_generation_matches
        and subscription_send_recorded
        and mode_full_is_final
        and post_mode_callback
    )
    if not plan_enabled:
        rejection_reason = "CALLBACK_SEEN_PLAN_DISABLED"
    elif not feed_session_matches:
        rejection_reason = "CALLBACK_SEEN_SESSION_MISMATCH"
    elif not reconnect_generation_matches:
        rejection_reason = "CALLBACK_SEEN_GENERATION_MISMATCH"
    elif not subscription_send_recorded:
        rejection_reason = "CALLBACK_SEEN_SUBSCRIPTION_UNPROVEN"
    elif not mode_full_is_final:
        rejection_reason = "CALLBACK_SEEN_MODE_NOT_FINAL_FULL"
    elif not raw_full_payload:
        rejection_reason = "CALLBACK_SEEN_QUOTE_PACKET"
    else:
        rejection_reason = "CALLBACK_SEEN_FULL_PACKET"
    _OBSERVATION_CALLBACK_COUNT_BY_TOKEN[token_int] = int(_OBSERVATION_CALLBACK_COUNT_BY_TOKEN.get(token_int) or 0) + 1
    if post_mode_callback:
        _POST_MODE_CALLBACK_COUNT_BY_TOKEN[token_int] = int(_POST_MODE_CALLBACK_COUNT_BY_TOKEN.get(token_int) or 0) + 1
        _FIRST_POST_MODE_CALLBACK_EPOCH_BY_TOKEN.setdefault(token_int, float(callback_receipt_epoch))
        if raw_full_payload:
            _POST_MODE_FULL_COUNT_BY_TOKEN[token_int] = int(_POST_MODE_FULL_COUNT_BY_TOKEN.get(token_int) or 0) + 1
            _FIRST_POST_MODE_FULL_EPOCH_BY_TOKEN.setdefault(token_int, float(callback_receipt_epoch))
        else:
            _POST_MODE_QUOTE_COUNT_BY_TOKEN[token_int] = int(_POST_MODE_QUOTE_COUNT_BY_TOKEN.get(token_int) or 0) + 1
            _FIRST_POST_MODE_QUOTE_EPOCH_BY_TOKEN.setdefault(token_int, float(callback_receipt_epoch))
    packet_detail.update(
        {
            "callback_seen": True,
            "symbol": symbol,
            "tick_keys": sorted(str(key) for key in dict(tick).keys()),
            "has_last_price": tick.get("last_price") is not None,
            "raw_packet_kind": packet_kind,
            "raw_full_payload": bool(raw_full_payload),
            "socket_generation": int(_SOCKET_GENERATION),
            "plan_enabled": bool(plan_enabled),
            "plan_verdict": str(observation_state.get("verdict") or ""),
            "token_in_observation_registry": True,
            "token_in_active_plan": bool(token_in_active_plan),
            "feed_session_matches": bool(feed_session_matches),
            "reconnect_generation_matches": bool(reconnect_generation_matches),
            "subscription_send_recorded": bool(subscription_send_recorded),
            "mode_full_is_final_local_command": bool(mode_full_is_final),
            "post_mode_callback": bool(post_mode_callback),
            "accepted_for_shadow_bar": bool(accepted_context and tick.get("last_price") is not None),
            "rejection_reason": rejection_reason,
            "final_current_generation_local_mode_is_full": bool(mode_full_is_final),
            "latest_subscribe_sequence_number": _LATEST_SUBSCRIBE_SEQUENCE_BY_TOKEN.get(token_int),
            "latest_mode_command_sequence_number": _LATEST_MODE_COMMAND_SEQUENCE_BY_TOKEN.get(token_int),
            "state_identity": _state_identity_payload(),
        }
    )
    _LATEST_OBSERVATION_PACKET_BY_TOKEN[token_int] = dict(packet_detail)
    if accepted_context and raw_full_payload:
        _record_full_payload_observed(token_int)
    return packet_detail


def on_ticks(ws, ticks):
    global _UNDERLYING_LOGGED_MISSING, _SCHEMA_LOG_TS, _LAST_WS_TICK_EPOCH, _LAST_MSG_TS_BY_TOKEN, _LAST_PAYLOAD_TS_BY_TOKEN, _LAST_FEED_TICK_LOG_MINUTE, _RUNTIME_STATE, _LAST_RUNTIME_ERROR, _FEED_ON_TICKS_ROW_SEQ
    _ = ws
    if not ticks:
        return
    record_fd_trace(
        "on_ticks.callback_entry",
        row_index=_FEED_ON_TICKS_ROW_SEQ + 1,
        queue_depth=write_queue_depth(),
        pending_writes=max(0, write_enqueue_count() - write_flush_count()),
        runtime_store_writes=_FEED_RUNTIME_SNAPSHOT_WRITE_COUNT,
        extra={"tick_count": len(ticks or [])},
    )
    try:
        feed_evidence.callback(len(ticks or []), callback_epoch=float(time.time()), rows=ticks)
    except Exception:
        pass
    try:
        if not _should_throttle_ws_event("depth_ws_ticks", now_epoch=float(time.time()), cooldown_sec=5.0):
            logger.info(
                "depth_ws_ticks count=%d sample_tokens=%s",
                len(ticks or []),
                [
                    t.get("instrument_token")
                    for t in list(ticks or [])[:5]
                    if isinstance(t, dict)
                ],
            )
    except Exception:
        pass
    now_epoch = float(now_utc_epoch())
    max_tick_epoch = None
    try:
        get_feed_health_monitor().on_ws_message(now_epoch=now_epoch)
    except Exception:
        pass
    if ticks and (now_epoch - _SCHEMA_LOG_TS) >= 30.0:
        try:
            sample = ticks[0] if isinstance(ticks[0], dict) else {}
            sample_keys = sorted(list(sample.keys()))
            ts_fields = [k for k in ("exchange_timestamp", "last_trade_time", "timestamp") if k in sample]
            _log_ws(
                "TICK_PAYLOAD_SCHEMA",
                {
                    "sample_keys": sample_keys,
                    "has_last_price": sample.get("last_price") is not None,
                    "has_depth": sample.get("depth") is not None,
                    "instrument_token": sample.get("instrument_token"),
                    "ts_fields_present": ts_fields,
                },
            )
            _SCHEMA_LOG_TS = now_epoch
        except Exception:
            pass
    try:
        observation_registry = load_observation_registry(force=False)
    except Exception:
        observation_registry = None
    observation_token_set = set(int(token) for token in (getattr(observation_registry, "all_tokens", []) or []))
    for t in ticks:
        _FEED_ON_TICKS_ROW_SEQ += 1
        if not isinstance(t, dict):
            continue
        payload_tick_epoch = _extract_tick_epoch(t)
        token_int = None
        try:
            token_int = int(t.get("instrument_token"))
        except Exception:
            token_int = None

        if token_int is not None and payload_tick_epoch is not None:
            prev_payload = _coerce_epoch(_LAST_PAYLOAD_TS_BY_TOKEN.get(token_int))
            if prev_payload is not None and payload_tick_epoch < prev_payload:
                _log_ws("FEED_TICK_DROPPED_OUT_OF_ORDER", {"token": token_int, "payload_epoch": payload_tick_epoch, "prev_epoch": prev_payload})
                continue
            _LAST_PAYLOAD_TS_BY_TOKEN[token_int] = payload_tick_epoch
        freshness_tick_epoch = _normalized_tick_epoch(
            token_int,
            payload_epoch=payload_tick_epoch,
            receipt_epoch=now_epoch,
        )
        if max_tick_epoch is None or float(freshness_tick_epoch) > float(max_tick_epoch):
            max_tick_epoch = float(freshness_tick_epoch)
        depth = t.get("depth")
        last_price = t.get("last_price")
        if token_int is not None:
            _LAST_MSG_TS_BY_TOKEN[int(token_int)] = float(freshness_tick_epoch)
            _record_observation_callback_truth(
                tick=t,
                instrument_token=int(token_int),
                callback_receipt_epoch=float(now_epoch),
                source_tick_epoch=payload_tick_epoch,
            )
        if token_int is not None:
            _FIRST_LIVE_TICK_EPOCH_BY_TOKEN.setdefault(int(token_int), float(now_epoch))
            if payload_tick_epoch is not None:
                _FIRST_SOURCE_TICK_EPOCH_BY_TOKEN.setdefault(int(token_int), float(payload_tick_epoch))
        observation_identity = (
            observation_registry.observation_identity(token_int)
            if observation_registry is not None and token_int is not None
            else None
        )
        symbol = (observation_identity or {}).get("symbol") or (_TOKEN_TO_SYMBOL.get(token_int) if token_int is not None else None)
        underlying_tick = _is_underlying_token(token_int)
        has_depth = _depth_has_bid_ask(depth)
        tick_bid = _best_price(depth.get("buy", [])) if isinstance(depth, dict) else None
        tick_ask = _best_price(depth.get("sell", [])) if isinstance(depth, dict) else None
        observation_state = _observation_state_payload()
        plan_generation = _coerce_generation(observation_state.get("reconnect_generation"), default=-1)
        feed_generation = _coerce_generation(_FEED_RECONNECT_GENERATION, default=-1)
        observation_token_allowed = (
            token_int is not None
            and int(token_int) in observation_token_set
            and observation_registry is not None
            and bool(observation_state.get("enabled"))
            and str(observation_state.get("verdict") or "") == "PASS_LIVE_SOURCE_PRESESSION_READINESS"
            and int(token_int) in set(int(tok) for tok in (observation_state.get("observation_tokens") or []))
            and str(observation_state.get("feed_session_id") or "") == _ensure_feed_session_id()
            and plan_generation == feed_generation
            and int(token_int) in _SUBSCRIPTION_REQUEST_SUCCEEDED_TOKENS
        )
        if token_int is not None and isinstance(depth, dict) and depth:
            depth_store.update(token_int, depth)
        if token_int is not None and token_int in _UNDERLYING_TOKEN_TO_SYMBOL:
            symbol = _UNDERLYING_TOKEN_TO_SYMBOL.get(token_int) or symbol
        if underlying_tick and _is_index_symbol(symbol):
            if isinstance(depth, dict) and depth:
                buy_book = depth.get("buy", [])
                sell_book = depth.get("sell", [])
                bid = _best_price(buy_book)
                ask = _best_price(sell_book)
                mid = None
                if bid is not None and ask is not None and bid > 0 and ask > 0:
                    mid = (bid + ask) / 2.0
                _update_index_quote_cache(
                    symbol=symbol,
                    bid=bid,
                    ask=ask,
                    mid=mid,
                    ts_epoch=freshness_tick_epoch,
                    last_price=last_price,
                    volume=t.get("volume") if t.get("volume") is not None else t.get("volume_traded"),
                )
        if observation_token_allowed:
            feed_identity = get_current_feed_session_identity()
            instrument_class = str((observation_identity or {}).get("instrument_class") or "UNKNOWN")
            packet_detail = dict(_LATEST_OBSERVATION_PACKET_BY_TOKEN.get(int(token_int)) or {})
            packet_kind = str(packet_detail.get("raw_packet_kind") or "")
            if not packet_kind:
                packet_kind = "INDEX_QUOTE" if instrument_class.upper() == "INDEX" else "NSE_EQUITY_QUOTE"
            is_full_payload = bool(packet_detail.get("raw_full_payload"))
            final_local_full = int(token_int) in _MODE_COMMAND_FINAL_FULL_TOKENS
            packet_detail["final_current_generation_local_mode_is_full"] = bool(final_local_full)
            packet_detail["latest_subscribe_sequence_number"] = _LATEST_SUBSCRIBE_SEQUENCE_BY_TOKEN.get(int(token_int))
            packet_detail["latest_mode_command_sequence_number"] = _LATEST_MODE_COMMAND_SEQUENCE_BY_TOKEN.get(int(token_int))
            if is_full_payload and not final_local_full:
                is_full_payload = False
                packet_detail["structured_reason"] = "MODE_COMMAND_SUPERSEDED_BY_SUBSCRIBE"
                packet_kind = "INDEX_QUOTE" if instrument_class.upper() == "INDEX" else "NSE_EQUITY_QUOTE"
            _LATEST_OBSERVATION_PACKET_BY_TOKEN[int(token_int)] = dict(packet_detail)
        if observation_token_allowed and last_price is not None:
            try:
                record_live_source_shadow_tick(
                    symbol=str(symbol or "").upper(),
                    instrument_token=token_int,
                    price=last_price,
                    source_tick_epoch=payload_tick_epoch,
                    source_type="live_websocket",
                    payload_mode="full" if is_full_payload else "quote",
                    feed_identity=feed_identity,
                    provider="kite",
                    token_domain="kite_instrument_token",
                    universe_hash=str(getattr(observation_registry, "canonical_sha256", "") or ""),
                    packet_kind=packet_kind,
                    is_full_payload=is_full_payload,
                )
            except Exception:
                pass
            if last_price is not None and not is_full_payload:
                _update_index_quote_cache(
                    symbol=symbol,
                    bid=None,
                    ask=None,
                    mid=None,
                    ts_epoch=freshness_tick_epoch,
                    last_price=last_price,
                    volume=t.get("volume") if t.get("volume") is not None else t.get("volume_traded"),
                )
        freshness_symbol = symbol
        option_freshness_symbol = None
        if _is_index_symbol(symbol) and not underlying_tick:
            freshness_symbol = None
        if (not underlying_tick) and symbol and last_price is not None:
            option_freshness_symbol = symbol
        record_fd_trace(
            "on_ticks.pre_symbol_freshness",
            row_index=_FEED_ON_TICKS_ROW_SEQ,
            queue_depth=write_queue_depth(),
            pending_writes=max(0, write_enqueue_count() - write_flush_count()),
            runtime_store_writes=_FEED_RUNTIME_SNAPSHOT_WRITE_COUNT,
            extra={"token": token_int, "symbol": symbol, "has_depth": has_depth, "has_ltp": last_price is not None},
        )
        _update_symbol_freshness(
            freshness_symbol,
            freshness_tick_epoch,
            has_ltp=last_price is not None,
            has_depth=has_depth,
            option_symbol=option_freshness_symbol,
        )
        try:
            record_tick(
                token=token_int,
                symbol=symbol,
                ts_epoch=freshness_tick_epoch,
                has_depth=has_depth,
                is_index=bool(underlying_tick and _is_index_symbol(symbol)),
                bid=tick_bid,
                ask=tick_ask,
                ltp=last_price,
                depth_ok=has_depth,
                now_epoch=now_epoch,
            )
            if has_depth:
                record_depth(
                    token=token_int,
                    symbol=symbol,
                    ts_epoch=freshness_tick_epoch,
                    is_index=bool(underlying_tick and _is_index_symbol(symbol)),
                    now_epoch=now_epoch,
                )
        except Exception:
            pass
        record_fd_trace(
            "on_ticks.post_market_data_record",
            row_index=_FEED_ON_TICKS_ROW_SEQ,
            queue_depth=write_queue_depth(),
            pending_writes=max(0, write_enqueue_count() - write_flush_count()),
            runtime_store_writes=_FEED_RUNTIME_SNAPSHOT_WRITE_COUNT,
            extra={"token": token_int, "has_depth": has_depth},
        )
        if last_price is not None or has_depth:
            record_tick_epoch(freshness_tick_epoch)
            if not _UNDERLYING_TOKENS and not _UNDERLYING_LOGGED_MISSING:
                _log_ws("FEED_UNDERLYING_TOKENS_MISSING", {})
                _UNDERLYING_LOGGED_MISSING = True

        last_price_float = _safe_float(last_price)
        if token_int is None or last_price_float is None:
            feed_evidence.inc(
                "rejected",
                reason="invalid_token" if token_int is None else "missing_or_invalid_last_price",
            )
            record_fd_trace(
                "on_ticks.rejected",
                row_index=_FEED_ON_TICKS_ROW_SEQ,
                queue_depth=write_queue_depth(),
                pending_writes=max(0, write_enqueue_count() - write_flush_count()),
                runtime_store_writes=_FEED_RUNTIME_SNAPSHOT_WRITE_COUNT,
                extra={"reason": "missing_token_or_last_price", "token": token_int},
            )
            continue
        ts_value = freshness_tick_epoch
        volume = t.get("volume")
        if volume is None:
            volume = t.get("volume_traded")
        oi = t.get("oi")
        audit_source_row_index = t.get("_audit_source_row_index")
        if audit_source_row_index is not None:
            feed_evidence.normalized(
                audit_source_row_index,
                token_int,
                t.get("_audit_source_timestamp"),
                last_price_float,
                volume,
                oi,
            )
        else:
            feed_evidence.inc("normalized")
        try:
            if audit_source_row_index is not None:
                feed_evidence.published(audit_source_row_index, token_int, ts_value, last_price_float, volume, oi)
            record_fd_trace(
                "on_ticks.pre_insert_tick",
                row_index=_FEED_ON_TICKS_ROW_SEQ,
                queue_depth=write_queue_depth(),
                pending_writes=max(0, write_enqueue_count() - write_flush_count()),
                runtime_store_writes=_FEED_RUNTIME_SNAPSHOT_WRITE_COUNT,
                extra={"token": token_int, "ts_epoch": ts_value},
            )
            ok = insert_tick(
                ts=ts_value,
                token=token_int,
                last_price=last_price_float,
                volume=volume,
                oi=oi,
            )
            if not ok:
                if audit_source_row_index is not None:
                    feed_evidence.publication_failed(
                        audit_source_row_index,
                        token_int,
                        ts_value,
                        last_price_float,
                        volume,
                        oi,
                        "insert_tick_returned_false",
                    )
                else:
                    feed_evidence.inc("explicitly_dropped", reason="insert_tick_returned_false")
                _log_tick_ingest_error(
                    token=token_int,
                    reason="insert_tick_returned_false",
                    keys=list(t.keys()),
                    tick_ts_present=ts_value is not None,
                )
            else:
                if audit_source_row_index is None:
                    feed_evidence.inc("published")
        except Exception as exc:
            if audit_source_row_index is not None:
                feed_evidence.publication_failed(
                    audit_source_row_index,
                    token_int,
                    ts_value,
                    last_price_float,
                    volume,
                    oi,
                    f"{type(exc).__name__}:{exc}",
                )
            else:
                feed_evidence.inc("explicitly_dropped", reason="insert_tick_exception")
            _log_tick_ingest_error(
                token=token_int,
                reason="insert_tick_exception",
                error=f"{type(exc).__name__}:{exc}",
                keys=list(t.keys()),
                tick_ts_present=ts_value is not None,
            )
        record_fd_trace(
            "on_ticks.post_insert_tick",
            row_index=_FEED_ON_TICKS_ROW_SEQ,
            queue_depth=write_queue_depth(),
            pending_writes=max(0, write_enqueue_count() - write_flush_count()),
            runtime_store_writes=_FEED_RUNTIME_SNAPSHOT_WRITE_COUNT,
            extra={"token": token_int, "ts_epoch": ts_value},
        )
    if max_tick_epoch is not None:
        _LAST_WS_TICK_EPOCH = float(max_tick_epoch)
        _reset_stale_on_fresh_ws_tick(
            now_epoch=now_epoch,
            tick_epoch=_LAST_WS_TICK_EPOCH,
            reason="ws_ticks_flowing",
        )
    if _reconnect_recovery_blocked_active():
        _RUNTIME_STATE = "RECOVERY_BLOCKED"
        _LAST_RUNTIME_ERROR = str(_RECONNECT_BLOCKED_REASON or "").strip().lower() or "recovery_blocked"
    else:
        _RUNTIME_STATE = "RUNNING"
        _LAST_RUNTIME_ERROR = ""
    _tick_option_feed_verification(now_epoch=now_epoch)
    record_fd_trace(
        "on_ticks.pre_runtime_snapshot",
        row_index=_FEED_ON_TICKS_ROW_SEQ,
        queue_depth=write_queue_depth(),
        pending_writes=max(0, write_enqueue_count() - write_flush_count()),
        runtime_store_writes=_FEED_RUNTIME_SNAPSHOT_WRITE_COUNT,
        extra={"rows_in_callback": len(ticks or [])},
    )
    minute_bucket = int(_LAST_WS_TICK_EPOCH // 60.0)
    if _LAST_FEED_TICK_LOG_MINUTE != minute_bucket:
        _LAST_FEED_TICK_LOG_MINUTE = minute_bucket
        _log_ws("FEED_TICK", {"ticks": len(ticks), "last_ws_tick_epoch": _LAST_WS_TICK_EPOCH})
    _persist_runtime_snapshot_row(
        ws_connected=True,
        source="on_ticks",
        now_epoch=now_epoch,
        runtime_state=_RUNTIME_STATE,
        last_error=_LAST_RUNTIME_ERROR,
        reconnect_blocked_reason=_RECONNECT_BLOCKED_REASON if _reconnect_recovery_blocked_active() else None,
    )
    record_fd_trace(
        "on_ticks.post_runtime_snapshot",
        row_index=_FEED_ON_TICKS_ROW_SEQ,
        queue_depth=write_queue_depth(),
        pending_writes=max(0, write_enqueue_count() - write_flush_count()),
        runtime_store_writes=_FEED_RUNTIME_SNAPSHOT_WRITE_COUNT,
    )
    record_fd_trace(
        "on_ticks.callback_exit",
        row_index=_FEED_ON_TICKS_ROW_SEQ,
        queue_depth=write_queue_depth(),
        pending_writes=max(0, write_enqueue_count() - write_flush_count()),
        runtime_store_writes=_FEED_RUNTIME_SNAPSHOT_WRITE_COUNT,
    )


def _register_on_ticks_callback(kws, generation_is_current, delegate=None):
    """Install the exact registered callback wrapper used by the live ticker."""
    callback_delegate = delegate or on_ticks

    def on_ticks_current(ws, ticks):
        if not generation_is_current("on_ticks"):
            return
        diagnostic_start = campaign_raw_diagnostics.on_ticks_entry(len(ticks or []))
        try:
            callback_delegate(ws, ticks)
        except Exception:
            campaign_raw_diagnostics.on_ticks_exit(diagnostic_start, exception=True)
            raise
        campaign_raw_diagnostics.on_ticks_exit(diagnostic_start)

    kws.on_ticks = on_ticks_current
    return on_ticks_current


def stop_depth_ws(reason: str = "manual_stop"):
    """
    Stop watchdog and close existing KiteTicker instance.
    """
    global _KITE_TICKER, _WATCHDOG_STOP, _WATCHDOG_THREAD, _STALE_STRIKES, _STOP_REQUESTED, _LAST_WS_TICK_EPOCH, _LAST_MSG_TS_BY_TOKEN, _LAST_PAYLOAD_TS_BY_TOKEN, _LAST_FEED_TICK_LOG_MINUTE, _LAST_FEED_HEALTH_STATE, _RUNTIME_STATE, _SYMBOL_LAST_OPTION_TICK_TS
    campaign_raw_diagnostics.shutdown()
    _reset_feed_restart_verification(reason=f"stop_depth_ws:{reason}")
    _reset_option_feed_verification(reason=f"stop_depth_ws:{reason}")
    watchdog_thread = None
    ticker_instance = None
    stop_timeout_sec = float(getattr(cfg, "DEPTH_WATCHDOG_STOP_TIMEOUT_SEC", 3.0))
    with _KITE_TICKER_LOCK:
        has_active_ticker = _KITE_TICKER is not None
        has_active_watchdog = _WATCHDOG_THREAD is not None or _WATCHDOG_STOP is not None
        if not has_active_ticker and not has_active_watchdog:
            _STOP_REQUESTED = True
            _LAST_FEED_HEALTH_STATE = None
            _RUNTIME_STATE = "STOPPED"
            return
        _STOP_REQUESTED = True
        _log_ws("FEED_STOP", {"reason": reason})
        if _WATCHDOG_STOP is not None:
            _WATCHDOG_STOP.set()
        watchdog_thread = _WATCHDOG_THREAD
        _WATCHDOG_THREAD = None
        _STALE_STRIKES = 0
        _LAST_FEED_HEALTH_STATE = None
        _LAST_WS_TICK_EPOCH = 0.0
        _LAST_MSG_TS_BY_TOKEN = {}
        _LAST_PAYLOAD_TS_BY_TOKEN = {}
        _SYMBOL_LAST_OPTION_TICK_TS = {}
        _LAST_FEED_TICK_LOG_MINUTE = None
        _RUNTIME_STATE = "STOPPED"
        ticker_instance = _KITE_TICKER
        _close_ticker_instance(ticker_instance)
        _KITE_TICKER = None
    _join_thread_safe(watchdog_thread, stop_timeout_sec)
    _join_ticker_threads(ticker_instance, stop_timeout_sec)
    _persist_runtime_snapshot_row(
        ws_connected=False,
        source=f"stop_depth_ws:{reason}",
        runtime_state="STOPPED",
        last_error=str(reason),
    )


def restart_depth_ws(reason: str = "unknown", ignore_cooldown: bool = False, force_full_restart: bool = False):
    """
    Full restart: close existing ticker and recreate with last known tokens.
    Rate-limited to avoid restart storms.
    """
    global _LAST_FULL_RESTART_EPOCH, _FULL_RESTARTS, _STALE_STRIKES, _STOP_REQUESTED, _RUNTIME_STATE, _LAST_RUNTIME_ERROR

    _log_ws("feed_restart_required", {"reason": reason})
    if bool(getattr(_FEED_RECOVERY_COORDINATOR.state, "recovery_in_progress", False)):
        _log_ws("FEED_RECOVERY_ALREADY_IN_PROGRESS", {"reason": reason, "source": "restart_depth_ws"})
        return False
    if _AUTH_REQUIRED_LATCH:
        _log_ws("FEED_RESTART_BLOCKED_AUTH_REQUIRED", {"reason": reason})
        return False
    if _RECOVERY_IN_PROGRESS and not _reconnect_recovery_blocked_active():
        _log_ws("FEED_RECOVERY_ALREADY_IN_PROGRESS", {"reason": reason, "source": "restart_depth_ws"})
        return False
    if _reconnect_recovery_blocked_active() or _reactor_terminal_restart_block_active():
        blocked_reason = str(_RECONNECT_BLOCKED_REASON).strip().lower() or _reactor_not_restartable_block_reason()
        _log_ws(
            "FEED_RESTART_BLOCKED_RECOVERY_REQUIRED",
            {"reason": reason, "reconnect_blocked_reason": blocked_reason},
        )
        _emit_reconnect_recovery_blocked_snapshot(
            source=f"restart_depth_ws:blocked:{reason}",
            reason=blocked_reason,
        )
        return False

    tokens, selection_payload = _resubscribe_token_selection()
    tokens = _normalize_positive_tokens(tokens)
    if not tokens:
        _log_ws(
            "FEED_RESTART_SKIPPED",
            {"reason": reason, "detail": "no_tokens_cached", **selection_payload},
        )
        return False

    now = time.time()
    if _use_native_reconnect() and _KITE_TICKER is not None and not bool(force_full_restart):
        ws_connected = _ws_connected_state()
        soft_allowed, soft_reason = _soft_resubscribe_eligibility(reason=reason, now_epoch=now)
        if soft_allowed:
            _log_ws(
                "FEED_RESTART_SOFT_PATH",
                {"reason": reason, "detail": "internal_reconnect_enabled", "ws_connected": True},
            )
            soft_ok = _soft_resubscribe_current(reason=reason)
            if soft_ok:
                return True
            _log_ws(
                "FEED_RESTART_SOFT_PATH_FAILED",
                {"reason": reason, "detail": "soft_resubscribe_failed", "ws_connected": True},
            )
        else:
            _log_ws(
                "FEED_RESTART_FALLBACK_FULL_PATH",
                {
                    "reason": reason,
                    "detail": soft_reason if ws_connected is True else "ws_disconnected",
                    "ws_connected": ws_connected,
                },
            )
    elif bool(force_full_restart) and _KITE_TICKER is not None:
        ws_connected = _ws_connected_state()
        _log_ws(
            "FEED_RESTART_FORCE_FULL_PATH",
            {"reason": reason, "detail": "forced_full_restart", "ws_connected": ws_connected},
        )

    cooldown = float(getattr(cfg, "FEED_FULL_RESTART_COOLDOWN_SEC", 120))
    max_per_hour = int(getattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 6))
    storm_trip = int(getattr(cfg, "FEED_RESTART_STORM_TRIP", max_per_hour))

    if not _RESTART_LOCK.acquire(blocking=False):
        _log_ws("FEED_RESTART_CONCURRENT_BLOCKED", {"reason": reason})
        return False
    try:
        if feed_breaker_tripped():
            _log_ws("FEED_RESTART_BLOCKED_BY_BREAKER", {"reason": reason})
            return False
        if not feed_restart_guard.allow_restart(now=now, reason=reason):
            _log_ws("FEED_RESTART_BREAKER_BLOCK", {"reason": reason})
            return False
        _FULL_RESTARTS = [ts for ts in _FULL_RESTARTS if (now - ts) <= 3600.0]

        storm_window = float(getattr(cfg, "FEED_RESTART_STORM_WINDOW_SEC", 300.0))
        recent_storm = [ts for ts in _FULL_RESTARTS if (now - ts) <= storm_window]

        if len(recent_storm) >= storm_trip:
            try:
                trip_feed_breaker(
                    reason="feed_restart_storm",
                    meta={"count": len(recent_storm), "window_sec": storm_window, "reason": reason},
                )
            except Exception:
                pass
            try:
                risk_halt.set_halt(
                    "feed_restart_storm",
                    details={"count": len(recent_storm), "window_sec": storm_window, "reason": reason},
                )
            except Exception:
                pass
            _log_ws(
                "FEED_RESTART_STORM_TRIP",
                {"reason": reason, "count": len(recent_storm), "window_sec": storm_window},
            )
            return False

        if (not bool(ignore_cooldown)) and (now - _LAST_FULL_RESTART_EPOCH) < cooldown:
            next_allowed = _LAST_FULL_RESTART_EPOCH + cooldown
            remaining_sec = max(0.0, float(next_allowed) - float(now))
            _log_ws(
                "FEED_RESTART_RATE_LIMIT_COOLDOWN",
                {
                    "reason": reason,
                    "cooldown_sec": cooldown,
                    "next_allowed_epoch": next_allowed,
                    "cooldown_remaining_sec": remaining_sec,
                },
            )
            return False

        if len(_FULL_RESTARTS) >= max_per_hour:
            oldest = min(_FULL_RESTARTS)
            next_allowed = oldest + 3600.0
            _log_ws(
                "FEED_RESTART_RATE_LIMIT_HOURLY",
                {"reason": reason, "max_per_hour": max_per_hour, "next_allowed_epoch": next_allowed},
            )
            return False

        _log_ws("FEED_FULL_RESTART_BEGIN", {"reason": reason, "tokens": len(tokens), **selection_payload})
        _RUNTIME_STATE = "RESTARTING"
        _LAST_RUNTIME_ERROR = str(reason)
        import multiprocessing
        in_child_process = multiprocessing.current_process().name != "MainProcess"

        if getattr(cfg, "FEED_USE_SUBPROCESS", False) and in_child_process:
            _persist_runtime_snapshot_row(
                ws_connected=False,
                source=f"restart_depth_ws:begin:{reason}",
                runtime_state="RESTART_REQUIRED",
                last_error=str(reason),
                intended_tokens_count=len(tokens),
                restart_attempt_allowed=True,
                restart_attempted=True,
                process_restart_required=True,
            )
            import os
            _log_ws("feed_restart_subprocess_exit", {"reason": reason})
            os._exit(1)
        else:
            _persist_runtime_snapshot_row(
                ws_connected=False,
                source=f"restart_depth_ws:begin:{reason}",
                runtime_state="RESTARTING",
                last_error=str(reason),
                intended_tokens_count=len(tokens),
                restart_attempt_allowed=True,
                restart_attempted=True,
            )

            stop_depth_ws(reason=f"restart:{reason}")

            _STOP_REQUESTED = False

            try:
                _log_ws("feed_restart_attempt", {"reason": reason})
                started = start_depth_ws(tokens, profile_verified=False, skip_guard=True)
            except Exception as exc:
                _log_ws("feed_restart_failed", {"reason": reason, "error": str(exc)})
                _RUNTIME_STATE = "RESTART_FAILED"
                _LAST_RUNTIME_ERROR = f"start_exception:{type(exc).__name__}:{exc}"[:1000]
                _persist_runtime_snapshot_row(
                    ws_connected=False,
                    source=f"restart_depth_ws:start_exception:{reason}",
                    runtime_state="RESTART_FAILED",
                    last_error=_LAST_RUNTIME_ERROR,
                    intended_tokens_count=len(tokens),
                )
                _log_ws("FEED_FULL_RESTART_FAILED", {"reason": reason, "error": str(exc)})
                return False

            if started is False:
                _log_ws("feed_restart_failed", {"reason": reason, "error": "start_returned_false"})
                _RUNTIME_STATE = "RESTART_FAILED"
                _LAST_RUNTIME_ERROR = f"start_returned_false:{reason}"[:1000]
                _persist_runtime_snapshot_row(
                    ws_connected=False,
                    source=f"restart_depth_ws:start_failed:{reason}",
                    runtime_state="RESTART_FAILED",
                    last_error=_LAST_RUNTIME_ERROR,
                    intended_tokens_count=len(tokens),
                )
                _log_ws(
                    "FEED_FULL_RESTART_FAILED_AFTER_STOP",
                    {"reason": reason, "tokens": len(tokens), **selection_payload},
                )
                return False

            _log_ws("feed_restart_success", {"reason": reason})

            _persist_runtime_snapshot_row(
                ws_connected=None,
                source=f"restart_depth_ws:start_requested:{reason}",
                runtime_state="STARTING",
                last_error="",
                intended_tokens_count=len(tokens),
            )
            _LAST_FULL_RESTART_EPOCH = now
            _FULL_RESTARTS.append(now)
            _STALE_STRIKES = 0
            _log_ws("FEED_FULL_RESTART_OK", {"reason": reason, "tokens": len(tokens), **selection_payload})
            _begin_feed_restart_verification(
                reason=str(reason or ""),
                start_epoch=float(_DEPTH_WS_START_EPOCH or 0.0),
                now_epoch=float(now),
            )
            return True
    finally:
        _RESTART_LOCK.release()



def start_depth_ws(instrument_tokens, profile_verified=False, skip_lock: bool = False, skip_guard: bool = False) -> bool:
    global _DEPTH_WS_START_EPOCH, _KITE_TICKER, _WATCHDOG_THREAD, _WATCHDOG_STOP, _LAST_TOKENS, _STALE_STRIKES, _WARMUP_PENDING, _STOP_REQUESTED, _LAST_WS_TICK_EPOCH, _LAST_MSG_TS_BY_TOKEN, _LAST_PAYLOAD_TS_BY_TOKEN, _LAST_FEED_TICK_LOG_MINUTE, _LAST_FEED_HEALTH_STATE, _RUNTIME_STATE, _LAST_RUNTIME_ERROR, _INTENDED_TOKEN_COUNT, _SYMBOL_LAST_OPTION_TICK_TS, _SOCKET_GENERATION
    _log_ws("ws_start_requested", {"tokens_count": len(instrument_tokens), "ws_lifecycle_state": "STARTING"})
    if bool(getattr(cfg, "FEED_FD_TRACE_ENABLE", False)) or bool(str(os.environ.get("TRADEBOT_FEED_FD_TRACE", "")).strip()):
        try:
            reset_fd_trace(baseline_fd=process_fd_count())
        except Exception:
            pass
    if _reconnect_recovery_blocked_active() or _reactor_terminal_restart_block_active():
        blocked_reason = str(_RECONNECT_BLOCKED_REASON).strip().lower() or _reactor_not_restartable_block_reason()
        _emit_reconnect_recovery_blocked_snapshot(
            source="start_depth_ws:reconnect_blocked",
            reason=blocked_reason,
        )
        _log_ws(
            "FEED_START_BLOCKED_RECOVERY_REQUIRED",
            {"reconnect_blocked_reason": blocked_reason},
        )
        return False
    _DEPTH_WS_START_EPOCH = float(now_utc_epoch())
    _RUNTIME_STATE = "STARTING"
    _LAST_RUNTIME_ERROR = ""
    _INTENDED_TOKEN_COUNT = len(list(dict.fromkeys(instrument_tokens or [])))
    _persist_runtime_snapshot_row(
        ws_connected=None,
        source="start_depth_ws:starting",
        runtime_state="STARTING",
        last_error="",
        intended_tokens_count=_INTENDED_TOKEN_COUNT,
    )
    if not skip_lock:
        if not _ensure_depth_ws_lock():
            _RUNTIME_STATE = "SUBSCRIBE_FAILED"
            _LAST_RUNTIME_ERROR = "depth_ws_lock_blocked"
            _persist_runtime_snapshot_row(
                ws_connected=False,
                source="start_depth_ws:lock_blocked",
                runtime_state=_RUNTIME_STATE,
                last_error=_LAST_RUNTIME_ERROR,
                intended_tokens_count=_INTENDED_TOKEN_COUNT,
            )
            return False
    if not skip_guard and getattr(cfg, "DEPTH_WS_SINGLETON", True):
        with _KITE_TICKER_LOCK:
            if _KITE_TICKER is not None:
                _log_ws(
                    "FEED_START_SUPPRESSED",
                    {"reason": "already_running", "tokens": len(_LAST_TOKENS or [])},
                )
                _RUNTIME_STATE = "RUNNING"
                _LAST_RUNTIME_ERROR = ""
                _persist_runtime_snapshot_row(
                    ws_connected=True,
                    source="start_depth_ws:already_running",
                    runtime_state="RUNNING",
                    last_error="",
                    intended_tokens_count=_INTENDED_TOKEN_COUNT,
                )
                return True
    if not KiteTicker or not cfg.KITE_USE_DEPTH:
        _RUNTIME_STATE = "IMPORT_MISSING"
        _LAST_RUNTIME_ERROR = "kiteticker_unavailable_or_depth_disabled"
        _persist_runtime_snapshot_row(
            ws_connected=False,
            source="start_depth_ws:import_missing",
            runtime_state="IMPORT_MISSING",
            last_error=_LAST_RUNTIME_ERROR,
            intended_tokens_count=_INTENDED_TOKEN_COUNT,
        )
        logger.error("depth_ws_not_available")
        return False
    if not cfg.KITE_API_KEY:
        _RUNTIME_STATE = "AUTH_BLOCKED"
        _LAST_RUNTIME_ERROR = "missing_api_key"
        _persist_runtime_snapshot_row(
            ws_connected=False,
            source="start_depth_ws:auth_blocked",
            runtime_state="AUTH_BLOCKED",
            last_error=_LAST_RUNTIME_ERROR,
            intended_tokens_count=_INTENDED_TOKEN_COUNT,
        )
        logger.error("depth_ws_missing_api_key")
        return False
    try:
        cwd = Path.cwd()
        root = repo_root()
        log_dir = logs_dir()
        logger.debug("kite_ws_paths cwd=%s repo_root=%s logs_dir=%s log_path=%s", cwd, root, log_dir, _LOG_PATH)
        _log_ws(
            "FEED_PATHS",
            {"cwd": str(cwd), "repo_root": str(root), "logs_dir": str(log_dir), "log_path": str(_LOG_PATH)},
        )
    except Exception as exc:
        logger.debug("kite_ws_paths_error err=%s:%s", type(exc).__name__, exc)
    auth_payload = get_kite_auth_health(force=True)
    if not auth_payload.get("ok"):
        err = auth_payload.get("error") or "unknown_auth_error"
        _log_ws("FEED_AUTH_BLOCKED", {"error": err})
        _RUNTIME_STATE = "AUTH_BLOCKED"
        _LAST_RUNTIME_ERROR = str(err)
        _persist_runtime_snapshot_row(
            ws_connected=False,
            source="start_depth_ws:auth_blocked",
            runtime_state="AUTH_BLOCKED",
            last_error=_LAST_RUNTIME_ERROR,
            intended_tokens_count=_INTENDED_TOKEN_COUNT,
        )
        if is_auth_error(reason_text=str(err)):
            _mark_auth_required(str(err), source="kite_depth_ws_start")
        logger.error("depth_ws_invalid_access_token reason=%s", err)
        return False
    rest_client = None
    try:
        rest_client = kite_client.ensure()
        api_key = str(getattr(kite_client, "_active_api_key", "") or "").strip()
        access_token = str(getattr(kite_client, "_active_access_token", "") or "").strip()
    except Exception as exc:
        _log_ws("FEED_AUTH_BLOCKED", {"error": f"token_resolve_failed:{type(exc).__name__}:{exc}"})
        _RUNTIME_STATE = "AUTH_BLOCKED"
        _LAST_RUNTIME_ERROR = f"token_resolve_failed:{type(exc).__name__}:{exc}"
        _persist_runtime_snapshot_row(
            ws_connected=False,
            source="start_depth_ws:auth_blocked",
            runtime_state="AUTH_BLOCKED",
            last_error=_LAST_RUNTIME_ERROR,
            intended_tokens_count=_INTENDED_TOKEN_COUNT,
        )
        _mark_auth_required(f"token_resolve_failed:{type(exc).__name__}:{exc}", source="kite_depth_ws_start")
        logger.error("depth_ws_access_token_resolve_failed err=%s", exc)
        return False
    if not access_token:
        _log_ws("FEED_AUTH_BLOCKED", {"error": "missing_access_token:empty"})
        _RUNTIME_STATE = "AUTH_BLOCKED"
        _LAST_RUNTIME_ERROR = "missing_access_token:empty"
        _persist_runtime_snapshot_row(
            ws_connected=False,
            source="start_depth_ws:auth_blocked",
            runtime_state="AUTH_BLOCKED",
            last_error=_LAST_RUNTIME_ERROR,
            intended_tokens_count=_INTENDED_TOKEN_COUNT,
        )
        _mark_auth_required("missing_access_token:empty", source="kite_depth_ws_start")
        logger.error("depth_ws_access_token_empty")
        return False
    if not api_key:
        _log_ws("FEED_AUTH_BLOCKED", {"error": "missing_api_key:empty"})
        _RUNTIME_STATE = "AUTH_BLOCKED"
        _LAST_RUNTIME_ERROR = "missing_api_key:empty"
        _persist_runtime_snapshot_row(
            ws_connected=False,
            source="start_depth_ws:auth_blocked",
            runtime_state="AUTH_BLOCKED",
            last_error=_LAST_RUNTIME_ERROR,
            intended_tokens_count=_INTENDED_TOKEN_COUNT,
        )
        _mark_auth_required("missing_api_key:empty", source="kite_depth_ws_start")
        logger.error("depth_ws_api_key_empty")
        return False

    tokens = list(dict.fromkeys(instrument_tokens or []))
    if not tokens:
        _RUNTIME_STATE = "SUBSCRIBE_FAILED"
        _LAST_RUNTIME_ERROR = "no_instrument_tokens"
        _persist_runtime_snapshot_row(
            ws_connected=False,
            source="start_depth_ws:subscribe_failed",
            runtime_state="SUBSCRIBE_FAILED",
            last_error=_LAST_RUNTIME_ERROR,
            intended_tokens_count=_INTENDED_TOKEN_COUNT,
        )
        logger.error("depth_ws_no_instrument_tokens")
        return False
    _LAST_TOKENS = list(tokens)
    _STALE_STRIKES = 0
    _WARMUP_PENDING = True
    _STOP_REQUESTED = False
    _LAST_WS_TICK_EPOCH = 0.0
    _LAST_MSG_TS_BY_TOKEN = {}
    _LAST_PAYLOAD_TS_BY_TOKEN = {}
    _SYMBOL_LAST_OPTION_TICK_TS = {}
    _LAST_FEED_TICK_LOG_MINUTE = None
    _LAST_FEED_HEALTH_STATE = None
    _RUNTIME_STATE = "STARTING"
    try:
        get_feed_health_monitor().set_reconnect_handler(
            lambda reason: restart_depth_ws(reason=f"feed_health:{reason}")
        )
    except Exception:
        pass
    _clear_auth_required_latch()
    rebalance_cooldown_sec = float(getattr(cfg, "DEPTH_REBALANCE_COOLDOWN_SEC", 60.0))
    atm_shift_threshold_steps = float(getattr(cfg, "DEPTH_ATM_SHIFT_THRESHOLD_STEPS", 1))
    rebalance_state = {
        "last_rebalance_ts": None,
        "last_atm_by_symbol": {},
        "last_eval_ts": 0.0,
        "last_reason": "",
    }

    computed_profile_verified = False
    profile_error = ""
    try:
        if rest_client is not None:
            profile = rest_client.profile() or {}
            user_id = str(profile.get("user_id") or "").strip()
            if user_id:
                computed_profile_verified = True
                _log_ws("FEED_AUTH_PROFILE_OK", {"user_last4": user_id[-4:]})
            else:
                profile_error = "missing_user_id"
        else:
            profile_error = "kite_client_unavailable"
    except Exception as exc:
        profile_error = f"{type(exc).__name__}:{exc}"
    if not computed_profile_verified:
        _log_ws("FEED_AUTH_PROFILE_FAIL", {"error": profile_error or "unknown"})

    stats_api = _masked_secret_stats("api_key", api_key)
    stats_token = _masked_secret_stats("access_token", access_token)
    logger.info(
        "kite_ws_credential_stats api_key_len=%s api_key_tail4=%s api_key_has_whitespace=%s access_token_len=%s access_token_tail4=%s access_token_has_whitespace=%s",
        stats_api["api_key_len"],
        stats_api["api_key_tail4"],
        stats_api["api_key_has_whitespace"],
        stats_token["access_token_len"],
        stats_token["access_token_tail4"],
        stats_token["access_token_has_whitespace"],
    )
    _log_ws("FEED_CREDENTIAL_STATS", {**stats_api, **stats_token, "tokens": len(tokens)})

    handshake_proof = build_ws_handshake_attempt_event(
        public_key=api_key,
        access_token=access_token,
        token_count=len(tokens),
        profile_verified=bool(computed_profile_verified),
    )
    _log_ws(
        "FEED_WS_HANDSHAKE_CREDENTIAL_PROOF",
        {key: value for key, value in handshake_proof.items() if key != "event"},
    )
    logger.info(
        "feed_ws_handshake_credential_proof public_key_tail4=%s access_token_tail4=%s access_token_len=%s access_token_has_internal_whitespace=%s token_count=%s profile_verified=%s",
        handshake_proof.get("public_key_tail4"),
        handshake_proof.get("access_token_tail4"),
        handshake_proof.get("access_token_len"),
        handshake_proof.get("access_token_has_internal_whitespace"),
        handshake_proof.get("token_count"),
        handshake_proof.get("profile_verified"),
    )

    with _KITE_TICKER_LOCK:
        if _KITE_TICKER is not None:
            logger.info("kite_ws_existing_instance_detected_closing")
            _log_ws("FEED_RECREATE_CLOSE_OLD", {"tokens": len(tokens)})
            _close_ticker_instance(_KITE_TICKER)
            _KITE_TICKER = None
        if _WATCHDOG_STOP is not None:
            _WATCHDOG_STOP.set()
        _WATCHDOG_STOP = threading.Event()
        kws = get_kite_ticker(api_key=api_key, access_token=access_token, debug=False)
        _SOCKET_GENERATION += 1
        socket_generation = int(_SOCKET_GENERATION)
        _log_ws(
            "FEED_SOCKET_GENERATION_STARTED",
            {
                "socket_generation": socket_generation,
                "token_count": len(tokens),
                "timestamp": float(now_utc_epoch()),
                "result": "started",
            },
        )
        if hasattr(kws, "auto_reconnect"):
            try:
                kws.auto_reconnect = _use_native_reconnect()
            except Exception:
                pass
        logger.info(
            "kite_ws_created api_key_tail4=%s access_token_tail4=%s kite_id=%s",
            api_key[-4:] if len(str(api_key or "")) >= 4 else api_key,
            access_token[-4:] if len(str(access_token or "")) >= 4 else access_token,
            id(kws),
        )
        _KITE_TICKER = kws

    handshake_soft_reset_used = False

    def _generation_is_current(callback: str) -> bool:
        if socket_generation == int(_SOCKET_GENERATION):
            return True
        _log_ws(
            "FEED_OLD_GENERATION_CALLBACK_IGNORED",
            {
                "socket_generation": socket_generation,
                "active_generation": int(_SOCKET_GENERATION),
                "callback": callback,
                "callback_thread": threading.current_thread().name,
                "timestamp": float(now_utc_epoch()),
                "result": "ignored",
            },
        )
        return False

    def _apply_subscription_delta(ws, subscribe_tokens: list[int], unsubscribe_tokens: list[int], reason: str):
        global _LAST_TOKENS, _RUNTIME_STATE, _LAST_RUNTIME_ERROR
        to_subscribe = sorted(set(int(t) for t in (subscribe_tokens or []) if int(t) > 0))
        to_unsubscribe = sorted(set(int(t) for t in (unsubscribe_tokens or []) if int(t) > 0))
        can_mutate, guard_reason, guard_payload = _can_mutate_ws_subscriptions(reason=reason)
        if not can_mutate:
            _log_ws("FEED_REBALANCE_SKIPPED", {**guard_payload, "guard_reason": guard_reason, "subscribe_count": len(to_subscribe), "unsubscribe_count": len(to_unsubscribe)})
            return False
        try:
            if to_subscribe:
                _record_subscription_requested(to_subscribe)
                client_mode_before = _client_mode_for_token(ws, 256265)
                _record_ws_subscription_operation(
                    ws,
                    to_subscribe,
                    callsite="_apply_subscription_delta",
                    operation="subscribe",
                    reason=reason,
                    local_call_result="dispatched",
                    client_mode_before=client_mode_before,
                    socket_generation=socket_generation,
                )
                ws.subscribe(to_subscribe)
                _record_subscription_request_succeeded(to_subscribe)
                client_mode_after_subscribe = _client_mode_for_token(ws, 256265)
                _record_ws_subscription_operation(
                    ws,
                    to_subscribe,
                    callsite="_apply_subscription_delta",
                    operation="subscribe",
                    reason=reason,
                    local_call_result="succeeded",
                    client_mode_before=client_mode_before,
                    client_mode_after=client_mode_after_subscribe,
                    socket_generation=socket_generation,
                )
                client_mode_before_mode = _client_mode_for_token(ws, 256265)
                _record_ws_subscription_operation(
                    ws,
                    to_subscribe,
                    callsite="_apply_subscription_delta",
                    operation="set_mode",
                    requested_mode=str(getattr(ws, "MODE_FULL", "full")),
                    reason=reason,
                    local_call_result="dispatched",
                    client_mode_before=client_mode_before_mode,
                    socket_generation=socket_generation,
                )
                ws.set_mode(ws.MODE_FULL, to_subscribe)
                _record_mode_request_succeeded(to_subscribe)
                _record_ws_subscription_operation(
                    ws,
                    to_subscribe,
                    callsite="_apply_subscription_delta",
                    operation="set_mode",
                    requested_mode=str(getattr(ws, "MODE_FULL", "full")),
                    reason=reason,
                    local_call_result="succeeded",
                    client_mode_before=client_mode_before_mode,
                    client_mode_after=_client_mode_for_token(ws, 256265),
                    socket_generation=socket_generation,
                )
        except Exception as exc:
            _RUNTIME_STATE = "SUBSCRIBE_FAILED"
            _LAST_RUNTIME_ERROR = f"subscribe_delta:{exc}"[:1000]
            _log_ws(
                "FEED_REBALANCE_SUBSCRIBE_ERROR",
                {"reason": reason, "count": len(to_subscribe), "error": str(exc)},
            )
            _persist_runtime_snapshot_row(
                ws_connected=False,
                source=f"rebalance_subscribe_error:{reason}",
                runtime_state="SUBSCRIBE_FAILED",
                last_error=_LAST_RUNTIME_ERROR,
            )
            return False
        if to_unsubscribe:
            try:
                if hasattr(ws, "unsubscribe"):
                    ws.unsubscribe(to_unsubscribe)
            except Exception as exc:
                _RUNTIME_STATE = "SUBSCRIBE_FAILED"
                _LAST_RUNTIME_ERROR = f"unsubscribe_delta:{exc}"[:1000]
                _log_ws(
                    "FEED_REBALANCE_UNSUBSCRIBE_ERROR",
                    {"reason": reason, "count": len(to_unsubscribe), "error": str(exc)},
                )
                _persist_runtime_snapshot_row(
                    ws_connected=False,
                    source=f"rebalance_unsubscribe_error:{reason}",
                    runtime_state="SUBSCRIBE_FAILED",
                    last_error=_LAST_RUNTIME_ERROR,
                )
                return False
        final_set = set(int(t) for t in (_LAST_TOKENS or []))
        final_set.update(to_subscribe)
        final_set.difference_update(to_unsubscribe)
        _LAST_TOKENS = sorted(final_set)
        tokens[:] = list(_LAST_TOKENS)
        logger.info(
            "depth_ws_subscribe_apply subscribe_count=%d unsubscribe_count=%d final_count=%d",
            len(to_subscribe),
            len(to_unsubscribe),
            len(_LAST_TOKENS or []),
        )
        logger.info(
            "depth_ws_subscribe_tokens sample=%s",
            list((_LAST_TOKENS or [])[:10]),
        )
        if _LAST_TOKENS:
            try:
                client_mode_before_final = _client_mode_for_token(ws, 256265)
                _record_ws_subscription_operation(
                    ws,
                    _LAST_TOKENS,
                    callsite="_apply_subscription_delta:final_full",
                    operation="set_mode",
                    requested_mode=str(getattr(ws, "MODE_FULL", "full")),
                    reason=reason,
                    local_call_result="dispatched",
                    client_mode_before=client_mode_before_final,
                    socket_generation=socket_generation,
                )
                ws.set_mode(ws.MODE_FULL, _LAST_TOKENS)
                _record_mode_request_succeeded(_LAST_TOKENS)
                _record_ws_subscription_operation(
                    ws,
                    _LAST_TOKENS,
                    callsite="_apply_subscription_delta:final_full",
                    operation="set_mode",
                    requested_mode=str(getattr(ws, "MODE_FULL", "full")),
                    reason=reason,
                    local_call_result="succeeded",
                    client_mode_before=client_mode_before_final,
                    client_mode_after=_client_mode_for_token(ws, 256265),
                    socket_generation=socket_generation,
                )
            except Exception as exc:
                _record_ws_subscription_operation(
                    ws,
                    _LAST_TOKENS,
                    callsite="_apply_subscription_delta:final_full",
                    operation="set_mode",
                    requested_mode=str(getattr(ws, "MODE_FULL", "full")),
                    reason=reason,
                    local_call_result="exception",
                    exception_type=type(exc).__name__,
                    client_mode_before=client_mode_before_final,
                    socket_generation=socket_generation,
                )
        _log_ws(
            "FEED_REBALANCE_APPLIED",
            {
                "reason": reason,
                "subscribe_count": len(to_subscribe),
                "unsubscribe_count": len(to_unsubscribe),
                "total_tokens": len(_LAST_TOKENS),
            },
        )
        _RUNTIME_STATE = "RUNNING"
        _LAST_RUNTIME_ERROR = ""
        _persist_runtime_snapshot_row(
            ws_connected=True,
            source=f"rebalance_applied:{reason}",
            runtime_state="RUNNING",
            last_error="",
        )
        _reset_option_feed_verification(reason=f"rebalance_applied:{reason}")
        option_state = _option_runtime_state(
            now_epoch=float(time.time()),
            tokens=_LAST_TOKENS,
            expected_counts_by_symbol=_LAST_OPTION_COUNTS_BY_SYMBOL,
            min_required_by_symbol=_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL,
        )
        _begin_option_feed_verification(
            reason=f"rebalance:{reason}",
            start_epoch=float(now_utc_epoch()),
            requested_by_symbol=dict(_LAST_OPTION_COUNTS_BY_SYMBOL or {}),
            subscribed_by_symbol=dict(option_state.get("subscribed_count_by_symbol") or {}),
        )
        return True

    def _resubscribe_full(ws, reason: str):
        global _RUNTIME_STATE, _LAST_RUNTIME_ERROR
        _log_ws("subscription_replay_requested", {"reason": reason})
        desired, selection_payload = _resubscribe_token_selection()
        if not desired:
            desired = sorted(set(int(t) for t in (tokens or []) if int(t) > 0))
        if desired:
            event_base = {
                "socket_generation": socket_generation,
                "token_count": len(desired),
                "token_ids": list(desired),
                "desired_count": len(desired),
                "callback_thread": threading.current_thread().name,
                "timestamp": float(now_utc_epoch()),
                "reason": reason,
            }
            _log_ws("FEED_SUBSCRIBE_REQUESTED", {**event_base, "result": "requested"})
            _record_subscription_requested(desired)
            client_mode_before = _client_mode_for_token(ws, 256265)
            _record_ws_subscription_operation(
                ws,
                desired,
                callsite="_resubscribe_full",
                operation="subscribe",
                reason=reason,
                local_call_result="dispatched",
                client_mode_before=client_mode_before,
                socket_generation=socket_generation,
            )
            ws.subscribe(desired)
            _record_subscription_request_succeeded(desired)
            client_mode_after_subscribe = _client_mode_for_token(ws, 256265)
            _record_ws_subscription_operation(
                ws,
                desired,
                callsite="_resubscribe_full",
                operation="subscribe",
                reason=reason,
                local_call_result="succeeded",
                client_mode_before=client_mode_before,
                client_mode_after=client_mode_after_subscribe,
                socket_generation=socket_generation,
            )
            _log_ws("FEED_SUBSCRIBE_CALLBACK_APPLIED", {**event_base, "result": "applied"})
            _log_ws("FEED_MODE_FULL_REQUESTED", {**event_base, "result": "requested"})
            client_mode_before_mode = _client_mode_for_token(ws, 256265)
            _record_ws_subscription_operation(
                ws,
                desired,
                callsite="_resubscribe_full",
                operation="set_mode",
                requested_mode=str(getattr(ws, "MODE_FULL", "full")),
                reason=reason,
                local_call_result="dispatched",
                client_mode_before=client_mode_before_mode,
                socket_generation=socket_generation,
            )
            ws.set_mode(ws.MODE_FULL, desired)
            _record_mode_request_succeeded(desired)
            _record_ws_subscription_operation(
                ws,
                desired,
                callsite="_resubscribe_full",
                operation="set_mode",
                requested_mode=str(getattr(ws, "MODE_FULL", "full")),
                reason=reason,
                local_call_result="succeeded",
                client_mode_before=client_mode_before_mode,
                client_mode_after=_client_mode_for_token(ws, 256265),
                socket_generation=socket_generation,
            )
            _log_ws("FEED_MODE_FULL_CALLBACK_APPLIED", {**event_base, "result": "applied"})
        _record_feed_restart_verify_subscribe(now_epoch=float(now_utc_epoch()))
        _LAST_TOKENS[:] = desired
        tokens[:] = desired
        logger.info(
            "depth_ws_subscribe_apply subscribe_count=%d unsubscribe_count=%d final_count=%d",
            len(desired),
            0,
            len(desired),
        )
        logger.info(
            "depth_ws_subscribe_tokens sample=%s",
            list((desired or [])[:10]),
        )
        _RUNTIME_STATE = "RUNNING"
        _LAST_RUNTIME_ERROR = ""
        _reset_option_feed_verification(reason=f"resubscribe_full:{reason}")
        option_state = _option_runtime_state(
            now_epoch=float(time.time()),
            tokens=desired,
            expected_counts_by_symbol=_LAST_OPTION_COUNTS_BY_SYMBOL,
            min_required_by_symbol=_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL,
        )
        _begin_option_feed_verification(
            reason=f"resubscribe:{reason}",
            start_epoch=float(now_utc_epoch()),
            requested_by_symbol=dict(_LAST_OPTION_COUNTS_BY_SYMBOL or {}),
            subscribed_by_symbol=dict(option_state.get("subscribed_count_by_symbol") or {}),
        )
        _log_ws(
            "FEED_ON_CONNECT_SUBSCRIBE",
            {
                "reason": reason,
                "tokens": len(desired),
                "final_token_count_before_subscribe": len(desired),
                "subscription_requested_by_symbol": dict(_LAST_OPTION_COUNTS_BY_SYMBOL or {}),
                "resolved_option_tokens_count_by_symbol": dict(_LAST_OPTION_COUNTS_BY_SYMBOL or {}),
                "subscribed_option_tokens_count_by_symbol": dict(option_state.get("subscribed_count_by_symbol") or {}),
                "option_drop_reason_by_symbol": dict(option_state.get("feed_block_reason_by_symbol") or {}),
                **selection_payload,
            },
        )
        _log_ws(
            "FEED_RESUBSCRIBE",
            {
                "reason": reason,
                "tokens": len(tokens),
                "final_token_count_before_subscribe": len(tokens),
                "subscription_requested_by_symbol": dict(_LAST_OPTION_COUNTS_BY_SYMBOL or {}),
                "resolved_option_tokens_count_by_symbol": dict(_LAST_OPTION_COUNTS_BY_SYMBOL or {}),
                "subscribed_option_tokens_count_by_symbol": dict(option_state.get("subscribed_count_by_symbol") or {}),
                "option_drop_reason_by_symbol": dict(option_state.get("feed_block_reason_by_symbol") or {}),
                **selection_payload,
            },
        )
        _reset_option_feed_verification(reason=f"resubscribe_full:{reason}")
        _begin_option_feed_verification(
            reason=reason,
            start_epoch=float(now_utc_epoch()),
            requested_by_symbol=dict(_LAST_OPTION_COUNTS_BY_SYMBOL or {}),
            subscribed_by_symbol=dict(option_state.get("subscribed_count_by_symbol") or {}),
        )
        if rebalance_state.get("last_rebalance_ts") is None:
            rebalance_state["last_rebalance_ts"] = time.time()

    def on_connect(ws, response):
        global _STALE_STRIKES, _WARMUP_PENDING, _RUNTIME_STATE, _LAST_RUNTIME_ERROR
        try:
            campaign_raw_diagnostics.observe_protocol("open")
            campaign_raw_diagnostics.start_process_heartbeat()
            campaign_raw_diagnostics.start_reactor_heartbeat(getattr(getattr(ws, "factory", None), "reactor", None))
            if not _generation_is_current("on_connect"):
                return
            _clear_last_disconnected_info()
            _record_feed_restart_verify_connect(now_epoch=float(now_utc_epoch()))
            _log_ws("ws_connected", {"response": str(response), "ws_lifecycle_state": "CONNECTED"})
            _log_ws("FEED_CONNECT", {"tokens": len(tokens), "response": str(response)})
            logger.info(
                "depth_ws_connected token_count=%d first_tokens=%s",
                len(tokens or []),
                list((tokens or [])[:10]),
            )
            # Reset stale tracker and invalidate pre-existing depth timestamps so
            # watchdog waits for fresh post-connect ticks.
            _STALE_STRIKES = 0
            _WARMUP_PENDING = True
            global _LAST_WS_TICK_EPOCH
            _LAST_WS_TICK_EPOCH = 0.0
            for book in list(depth_store.books.values()):
                if isinstance(book, dict):
                    book["ts_epoch"] = None
                    book["ts"] = None
            _resubscribe_full(ws, reason="connect")
            _log_ws(
                "FEED_SUBSCRIPTION_REGISTRY_SNAPSHOT",
                {
                    "socket_generation": socket_generation,
                    "desired_count": len(_LAST_DESIRED_TOKENS or []),
                    "applied_count": len(_LAST_TOKENS or []),
                    "mode_full_applied_count": len(_LAST_TOKENS or []),
                    "queued_count": len(_PENDING_SUBSCRIBE_TOKENS),
                    "timestamp": float(now_utc_epoch()),
                    "result": "snapshot",
                },
            )
            _RUNTIME_STATE = "RUNNING"
            _LAST_RUNTIME_ERROR = ""
            _persist_runtime_snapshot_row(
                ws_connected=True,
                source="on_connect",
                runtime_state="RUNNING",
                last_error="",
            )
        except Exception as exc:
            _RUNTIME_STATE = "SUBSCRIBE_FAILED"
            _LAST_RUNTIME_ERROR = str(exc)
            _log_ws("FEED_CONNECT_ERROR", {"error": str(exc)})
            _persist_runtime_snapshot_row(
                ws_connected=False,
                source="on_connect:error",
                runtime_state="SUBSCRIBE_FAILED",
                last_error=_LAST_RUNTIME_ERROR,
            )

    def on_reconnect(ws, attempts):
        try:
            if not _generation_is_current("on_reconnect"):
                return
            _log_ws("ws_reconnect_attempt", {"attempts": attempts, "ws_lifecycle_state": "RECONNECTING"})
            _log_ws("FEED_RECONNECTING", {"attempts": attempts})
        except Exception as exc:
            _log_ws("FEED_RECONNECT_ERROR", {"error": str(exc), "attempts": attempts})

    ws_fault_seen = False

    def on_error(ws, code, reason):
        nonlocal handshake_soft_reset_used, ws_fault_seen
        global _RUNTIME_STATE, _LAST_RUNTIME_ERROR
        if not _generation_is_current("on_error"):
            return
        campaign_raw_diagnostics.observe_protocol("error", code=code, reason=reason)
        reason_text = str(reason)
        code_int = None
        try:
            code_int = int(code) if code is not None else None
        except Exception:
            code_int = None
        _set_last_disconnected_info(code=code_int, reason=reason_text)
        ws_fault_seen = True
        _log_ws("ws_reconnect_failed", {"code": code_int, "reason": reason_text, "ws_lifecycle_state": "DISCONNECTED"})
        _log_ws("FEED_ERROR", {"code": code, "reason": reason_text, "profile_verified": bool(computed_profile_verified)})
        _RUNTIME_STATE = "SUBSCRIBE_FAILED"
        _LAST_RUNTIME_ERROR = f"{code}:{reason_text}"[:1000]
        _persist_runtime_snapshot_row(
            ws_connected=False,
            source=f"on_error:{code}",
            runtime_state="SUBSCRIBE_FAILED",
            last_error=_LAST_RUNTIME_ERROR,
            disconnected_code=code_int,
            disconnected_reason=reason_text,
        )
        logger.warning("kite_ws_error code=%s reason=%s", code, reason)
        if is_auth_error(code=code_int, reason_text=reason_text):
            failure_proof = build_ws_auth_failure_proof_event(
                public_key=api_key,
                access_token=access_token,
                code=code_int,
                reason=reason_text,
                auth_required_latch=bool(_AUTH_REQUIRED_LATCH),
            )
            _log_ws(
                "FEED_WS_AUTH_FAILURE_PROOF",
                {key: value for key, value in failure_proof.items() if key != "event"},
            )
            _mark_auth_required(_auth_error_text(code, reason_text), code=code_int, source="kite_depth_ws_error")
            return
        reason_lower = reason_text.lower()
        handshake_error = (str(code) == "1006" or code == 1006) and "opening handshake" in reason_lower
        if handshake_error:
            if not handshake_soft_reset_used:
                handshake_soft_reset_used = True
                try:
                    _resubscribe_full(ws, reason="handshake_soft_reset")
                    _log_ws("FEED_HANDSHAKE_SOFT_RESET", {"code": code, "reason": reason_text})
                except Exception as exc:
                    _log_ws("FEED_HANDSHAKE_SOFT_RESET_ERROR", {"code": code, "reason": reason_text, "error": str(exc)})
            _log_ws("FEED_HANDSHAKE_SUPPRESS_RESTART", {"code": code, "reason": reason_text})
            return
        if _handle_ws1006_recoverable(source="on_error", ws=ws, code=code_int, reason=reason_text):
            return
        if _should_require_process_restart_for_ws_fault(code=code_int, reason_text=reason_text):
            decision = _FEED_RECOVERY_COORDINATOR.request_recovery(source="on_error", code=code_int, reason=reason_text)
            _sync_ws1006_recovery_state_from_coordinator()
            _emit_feed_recovery_events(decision.events_emitted, source="on_error", code=code_int, reason=reason_text)
            if decision.event == "FEED_RECOVERY_ALREADY_IN_PROGRESS":
                return
            _block_reconnect_for_process_restart(source="on_error", code=code_int, reason=reason_text, ticker=ws)
            return
        fatal = False
        if code in (1011, 1012):
            fatal = True
        stop_set = bool(_WATCHDOG_STOP is not None and _WATCHDOG_STOP.is_set())
        if fatal and is_market_open_ist() and not _STOP_REQUESTED and not stop_set:
            ignore_cooldown = _should_ignore_restart_cooldown_for_ws_fault(code=code_int, reason_text=reason_text)
            if _should_require_process_restart_for_ws_fault(code=code_int, reason_text=reason_text):
                _block_reconnect_for_process_restart(source="on_error", code=code_int, reason=reason_text, ticker=ws)
                return
            if _use_native_reconnect():
                if _reconnect_recovery_blocked_active():
                    blocked_reason = str(_RECONNECT_BLOCKED_REASON).strip().lower()
                    _emit_reconnect_recovery_blocked_snapshot(
                        source="on_error:reconnect_suppressed",
                        reason=blocked_reason,
                    )
                    return
                _persist_runtime_snapshot_row(
                    ws_connected=False,
                    source=f"on_error:restart_attempt:{code}",
                    runtime_state="RESTARTING",
                    last_error=_LAST_RUNTIME_ERROR,
                    disconnected_code=code_int,
                    disconnected_reason=reason_text,
                    restart_attempt_allowed=True,
                    restart_attempted=True,
                )
                _log_ws(
                    "FEED_INTERNAL_RECONNECT_FORCE_FULL",
                    {"source": "on_error", "code": code, "reason": reason_text},
                )
                _schedule_restart_depth_ws(
                    reason=f"ws_error:{code}",
                    ignore_cooldown=ignore_cooldown,
                    force_full_restart=True,
                    source="on_error",
                )
                return
            restart_depth_ws(reason=f"ws_error:{code}", ignore_cooldown=ignore_cooldown)

    def on_close(ws, code, reason):
        nonlocal ws_fault_seen
        global _RUNTIME_STATE, _LAST_RUNTIME_ERROR
        if not _generation_is_current("on_close"):
            return
        campaign_raw_diagnostics.observe_protocol("close", code=code, reason=reason)
        code_int = None
        try:
            code_int = int(code) if code is not None else None
        except Exception:
            code_int = None
        reason_text = str(reason)
        reason_lower = reason_text.lower()
        _set_last_disconnected_info(code=code_int, reason=reason_text)
        ws_fault_seen = True
        _log_ws("ws_disconnected", {"code": code_int, "reason": reason_text, "ws_lifecycle_state": "DISCONNECTED"})
        if _AUTH_REQUIRED_LATCH:
            close_failure_proof = build_ws_auth_failure_proof_event(
                public_key=api_key,
                access_token=access_token,
                code=code,
                reason=str(reason),
                auth_required_latch=True,
                source="kite_depth_ws_close_auth_required",
            )
            _log_ws(
                "FEED_WS_AUTH_FAILURE_PROOF",
                {key: value for key, value in close_failure_proof.items() if key != "event"},
            )
            _log_ws("FEED_CLOSE_AUTH_REQUIRED", {"code": code, "reason": str(reason)})
            _RUNTIME_STATE = "AUTH_BLOCKED"
            _LAST_RUNTIME_ERROR = f"{code}:{reason}"[:1000]
            _persist_runtime_snapshot_row(
                ws_connected=False,
                source=f"on_close_auth_required:{code}",
                runtime_state="AUTH_BLOCKED",
                last_error=_LAST_RUNTIME_ERROR,
            )
            return
        if (_WATCHDOG_STOP is not None and _WATCHDOG_STOP.is_set()) or _STOP_REQUESTED:
            _log_ws("FEED_CLOSE_STOP_REQUESTED", {"code": code, "reason": str(reason)})
            _RUNTIME_STATE = "STOPPED"
            _LAST_RUNTIME_ERROR = f"{code}:{reason}"[:1000]
            _persist_runtime_snapshot_row(
                ws_connected=False,
                source=f"on_close_stop_requested:{code}",
                runtime_state="STOPPED",
                last_error=_LAST_RUNTIME_ERROR,
            )
            return
        _log_ws("FEED_CLOSE", {"code": code, "reason": str(reason)})
        _RUNTIME_STATE = "SUBSCRIBE_FAILED"
        _LAST_RUNTIME_ERROR = f"{code}:{reason}"[:1000]
        _persist_runtime_snapshot_row(
            ws_connected=False,
            source=f"on_close:{code}",
            runtime_state="SUBSCRIBE_FAILED",
            last_error=_LAST_RUNTIME_ERROR,
            disconnected_code=code_int,
            disconnected_reason=reason_text,
        )
        logger.warning("kite_ws_close code=%s reason=%s", code, reason)
        if _handle_ws1006_recoverable(source="on_close", ws=ws, code=code_int, reason=reason_text):
            return
        if _should_require_process_restart_for_ws_fault(code=code_int, reason_text=reason_text):
            decision = _FEED_RECOVERY_COORDINATOR.request_recovery(source="on_close", code=code_int, reason=reason_text)
            _sync_ws1006_recovery_state_from_coordinator()
            _emit_feed_recovery_events(decision.events_emitted, source="on_close", code=code_int, reason=reason_text)
            if decision.event == "FEED_RECOVERY_ALREADY_IN_PROGRESS":
                return
            _block_reconnect_for_process_restart(source="on_close", code=code_int, reason=reason_text, ticker=ws)
            return
        fatal = False
        if code_int in (1011, 1012):
            fatal = True
        if is_market_open_ist():
            ignore_cooldown = _should_ignore_restart_cooldown_for_ws_fault(code=code_int, reason_text=reason_text)
            if _should_require_process_restart_for_ws_fault(code=code_int, reason_text=reason_text):
                _block_reconnect_for_process_restart(source="on_close", code=code_int, reason=reason_text, ticker=ws)
                return
            if _use_native_reconnect():
                if fatal:
                    if _reconnect_recovery_blocked_active():
                        blocked_reason = str(_RECONNECT_BLOCKED_REASON).strip().lower()
                        _emit_reconnect_recovery_blocked_snapshot(
                            source="on_close:reconnect_suppressed",
                            reason=blocked_reason,
                        )
                        return
                    _persist_runtime_snapshot_row(
                        ws_connected=False,
                        source=f"on_close:restart_attempt:{code}",
                        runtime_state="RESTARTING",
                        last_error=_LAST_RUNTIME_ERROR,
                        disconnected_code=code_int,
                        disconnected_reason=reason_text,
                        restart_attempt_allowed=True,
                        restart_attempted=True,
                    )
                    _log_ws(
                        "FEED_INTERNAL_RECONNECT_FORCE_FULL",
                        {"source": "on_close", "code": code, "reason": reason_text},
                    )
                    _schedule_restart_depth_ws(
                        reason=f"ws_close:{code}",
                        ignore_cooldown=ignore_cooldown,
                        force_full_restart=True,
                        source="on_close",
                    )
                    return
                _log_ws(
                    "FEED_INTERNAL_RECONNECT_WAIT",
                    {"source": "on_close", "code": code, "reason": reason_text},
                )
                _log_ws("ws_reconnect_attempt", {"attempts": 1, "source": "on_close", "ws_lifecycle_state": "RECONNECTING"})
                _soft_resubscribe_current(reason=f"on_close:{code}")
                return
            restart_depth_ws(reason=f"ws_close:{code}", ignore_cooldown=ignore_cooldown)

    def _watchdog():
        global _STALE_STRIKES, _WARMUP_PENDING
        max_age = float(getattr(cfg, "MAX_DEPTH_AGE_SEC", getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0)))
        soft_cooldown = float(getattr(cfg, "FEED_RECONNECT_COOLDOWN_SEC", 30))
        strikes_to_restart = int(getattr(cfg, "FEED_RESTART_STRIKES", 3))
        watchdog_poll_sec = float(getattr(cfg, "FEED_WATCHDOG_POLL_SEC", 1.0))
        tick_stale_restart_sec = float(getattr(cfg, "FEED_TICK_STALE_RESTART_SEC", 60.0))
        tick_stale_reset_sec = float(getattr(cfg, "FEED_TICK_RECOVER_SEC", 2.0))
        tick_stale_strikes_to_restart = int(getattr(cfg, "FEED_TICK_STALE_STRIKES", 2))
        tick_watchdog_poll_sec = float(getattr(cfg, "FEED_TICK_WATCHDOG_POLL_SEC", 2.0))
        silent_index_sec = float(getattr(cfg, "FEED_SILENT_INDEX_THRESHOLD_SEC", 1.5))
        silent_option_sec = float(getattr(cfg, "FEED_SILENT_OPTION_THRESHOLD_SEC", 3.0))
        silent_confirm_cycles = int(getattr(cfg, "FEED_SILENT_CONFIRM_CYCLES", 2))
        silent_backoff_min_sec = float(getattr(cfg, "FEED_SILENT_RECONNECT_BACKOFF_MIN_SEC", 1.0))
        silent_backoff_max_sec = float(getattr(cfg, "FEED_SILENT_RECONNECT_BACKOFF_MAX_SEC", 10.0))
        silent_force_full_restart_sec = float(getattr(cfg, "FEED_SILENT_FORCE_FULL_RESTART_SEC", 12.0))
        no_ticks_sec = float(getattr(cfg, "FEED_NO_TICKS_RECONNECT_SEC", 60.0))
        no_ticks_base_backoff = float(getattr(cfg, "FEED_NO_TICKS_RECONNECT_BACKOFF_SEC", 15.0))
        last_soft = 0.0
        last_warmup_log = 0.0
        no_tick_strikes = 0
        last_no_tick_restart = 0.0
        last_tick_watchdog_check = 0.0
        last_db_tick_epoch = None
        last_db_tick_age = None
        depth_stale_strikes = 0
        silent_state = {"confirm_hits": 0, "last_reconnect_epoch": 0.0}
        market_was_open: bool | None = None
        last_option_subscribe_retry = 0.0
        last_option_prune_refresh_state = {"last_refresh_epoch": 0.0}

        def _emit_snapshot(now_epoch: float) -> None:
            sub_counts = _subscribed_tokens_count_by_symbol(_LAST_TOKENS)
            missing_count, missing_counts_by_symbol = _missing_option_tokens_stats()
            market_open_now = bool(is_market_open_ist())
            last_ws_tick_epoch = _LAST_WS_TICK_EPOCH if _LAST_WS_TICK_EPOCH > 0 else None
            last_tick_epoch = last_ws_tick_epoch or last_db_tick_epoch
            last_tick_age_sec = max(0.0, float(now_epoch) - float(last_tick_epoch)) if last_tick_epoch is not None else None
            last_depth_epoch = _latest_depth_epoch_from_store()
            last_depth_age_sec = max(0.0, float(now_epoch) - float(last_depth_epoch)) if last_depth_epoch is not None else None
            feed_health_live_tick_grace_sec = float(getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", 10.0))
            ws_connected = _ws_connected_state()
            if not market_open_now:
                state_machine = {"state": "MARKET_CLOSED", "reason": "market_closed"}
            elif ws_connected is False:
                state_machine = {"state": "DOWN", "reason": "ws_disconnected"}
            elif last_tick_age_sec is None:
                state_machine = {"state": "STARTING", "reason": "awaiting_first_tick"}
            elif last_tick_age_sec <= feed_health_live_tick_grace_sec:
                state_machine = {"state": "LIVE", "reason": "ticks_flowing"}
            else:
                state_machine = {"state": "DOWN", "reason": "no_ws_messages"}
            option_state = _option_runtime_state(
                now_epoch=now_epoch,
                tokens=_LAST_TOKENS,
                expected_counts_by_symbol=_LAST_OPTION_COUNTS_BY_SYMBOL,
                min_required_by_symbol=_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL,
            )
            _tick_option_feed_verification(now_epoch=now_epoch)
            try:
                with _KITE_TICKER_LOCK:
                    ws_connected_runtime = bool(_KITE_TICKER is not None)
            except Exception:
                ws_connected_runtime = False
            logger.info(
                "depth_ws_runtime ws_connected=%s subscribed_option_tokens=%s option_block_reasons=%s latest_ws_tick=%s",
                ws_connected_runtime,
                int(option_state.get("option_count") or 0),
                dict(option_state.get("feed_block_reason_by_symbol") or {}),
                _LAST_WS_TICK_EPOCH if _LAST_WS_TICK_EPOCH > 0 else None,
            )
            _write_feed_runtime_snapshot(
                now_epoch=now_epoch,
                ws_connected=ws_connected,
                subscribed_tokens_count=len(_LAST_TOKENS or []),
                intended_tokens_count=int(_INTENDED_TOKEN_COUNT if _INTENDED_TOKEN_COUNT > 0 else len(_LAST_TOKENS or [])),
                subscribed_tokens_count_by_symbol=sub_counts,
                missing_option_tokens_count=missing_count,
                missing_option_tokens_count_by_symbol=missing_counts_by_symbol,
                last_db_tick_epoch=last_db_tick_epoch,
                last_db_tick_age_sec=last_db_tick_age,
                last_ws_tick_epoch=last_ws_tick_epoch,
                last_tick_age_sec=last_tick_age_sec,
                last_depth_epoch=last_depth_epoch,
                last_depth_age_sec=last_depth_age_sec,
                market_open=market_open_now,
                state_machine=state_machine,
                subscribed_option_tokens_count=int(option_state.get("option_count") or 0),
                option_last_tick_age_by_symbol=dict(option_state.get("option_age_by_symbol") or {}),
                option_last_tick_sample=list(option_state.get("sample_rows") or []),
                option_tokens_resolved_count_by_symbol=dict(_LAST_OPTION_COUNTS_BY_SYMBOL or {}),
                option_tokens_subscribed_count_by_symbol=dict(option_state.get("subscribed_count_by_symbol") or {}),
                option_ticks_received_count_by_symbol=dict(option_state.get("ticks_received_count_by_symbol") or {}),
                last_option_tick_ts_by_symbol=dict(option_state.get("last_tick_ts_by_symbol") or {}),
                option_feed_block_reason_by_symbol=dict(option_state.get("feed_block_reason_by_symbol") or {}),
                option_active_blockers_by_symbol=dict(option_state.get("active_blockers_by_symbol") or {}),
                restart_count_1h=_restart_count_1h(now_epoch),
                stale_strikes=_STALE_STRIKES,
                runtime_state=_RUNTIME_STATE,
                last_error=_LAST_RUNTIME_ERROR,
            )

        while True:
            if _WATCHDOG_STOP is None or _WATCHDOG_STOP.is_set():
                break
            if _reconnect_recovery_blocked_active():
                blocked_reason = str(_RECONNECT_BLOCKED_REASON or "").strip().lower() or "unknown_reconnect_block"
                _emit_reconnect_recovery_blocked_snapshot(
                    source="watchdog:recovery_blocked",
                    reason=blocked_reason,
                )
                while not (_WATCHDOG_STOP is None or _WATCHDOG_STOP.is_set()):
                    time.sleep(5.0)
                    _emit_reconnect_recovery_blocked_snapshot(
                        source="watchdog:monitoring_fatal",
                        reason=blocked_reason,
                    )
                    if not _reconnect_recovery_blocked_active():
                        break
                if _WATCHDOG_STOP is None or _WATCHDOG_STOP.is_set():
                    break
                continue
            time.sleep(max(0.5, watchdog_poll_sec))
            if _WATCHDOG_STOP is None or _WATCHDOG_STOP.is_set():
                break
            if _reconnect_recovery_blocked_active():
                blocked_reason = str(_RECONNECT_BLOCKED_REASON or "").strip().lower() or "unknown_reconnect_block"
                _emit_reconnect_recovery_blocked_snapshot(
                    source="watchdog:recovery_blocked_after_sleep",
                    reason=blocked_reason,
                )
                while not (_WATCHDOG_STOP is None or _WATCHDOG_STOP.is_set()):
                    time.sleep(5.0)
                    _emit_reconnect_recovery_blocked_snapshot(
                        source="watchdog:monitoring_fatal",
                        reason=blocked_reason,
                    )
                    if not _reconnect_recovery_blocked_active():
                        break
                if _WATCHDOG_STOP is None or _WATCHDOG_STOP.is_set():
                    break
                continue
            now_loop = float(time.time())
            if (now_loop - float(last_tick_watchdog_check)) >= max(0.5, tick_watchdog_poll_sec):
                last_tick_watchdog_check = now_loop
                hb = _run_db_tick_watchdog_cycle(
                    now_epoch=now_loop,
                    market_open=bool(is_market_open_ist()),
                    stale_restart_sec=tick_stale_restart_sec,
                    reset_sec=tick_stale_reset_sec,
                    strikes_to_restart=tick_stale_strikes_to_restart,
                    restart_cb=restart_depth_ws,
                )
                last_db_tick_epoch = hb.get("last_db_tick_epoch")
                last_db_tick_age = hb.get("last_db_tick_age_sec")
                if hb.get("restarted"):
                    _emit_snapshot(now_loop)
                    continue
            else:
                last_db_tick_age = (
                    max(0.0, now_loop - float(last_db_tick_epoch))
                    if last_db_tick_epoch is not None
                    else None
                )
            _emit_snapshot(now_loop)
            market_open_now = bool(is_market_open_ist())
            market_was_open = _maybe_reset_restart_guard_on_market_open(
                market_open_now=market_open_now,
                market_was_open=market_was_open,
            )
            if not market_open_now:
                _STALE_STRIKES = 0
                depth_stale_strikes = 0
                no_tick_strikes = 0
                silent_state["confirm_hits"] = 0
                _emit_snapshot(now_loop)
                # Keep watchdog/re-subscription paths active even when market is closed.
            expected_option_tokens = sum(
                max(0, int(v or 0)) for v in dict(_LAST_OPTION_COUNTS_BY_SYMBOL or {}).values()
            )
            option_state = _option_runtime_state(
                now_epoch=now_loop,
                tokens=_LAST_TOKENS,
                expected_counts_by_symbol=_LAST_OPTION_COUNTS_BY_SYMBOL,
                min_required_by_symbol=_LAST_OPTION_MIN_REQUIRED_BY_SYMBOL,
            )
            subscribed_option_tokens = int(option_state.get("option_count") or 0)
            refresh_payload: dict[str, object] = {}
            try:
                should_refresh, refresh_payload = _maybe_refresh_stale_option_subscription_universe(
                    now_epoch=now_loop,
                    refresh_state=last_option_prune_refresh_state,
                )
                last_option_prune_refresh_epoch = float(
                    last_option_prune_refresh_state.get("last_refresh_epoch") or 0.0
                )
                if should_refresh:
                    refresh_mode = str(refresh_payload.get("refresh_mode") or "delta")
                    refresh_reason = str(refresh_payload.get("reason") or "stale_option_prune_refresh")
                    refresh_ok = False
                    refresh_tokens = _normalize_positive_tokens(list(refresh_payload.get("refresh_tokens") or []))
                    if refresh_tokens:
                        refresh_ok = _refresh_subscription_tokens(
                            refresh_tokens,
                            reason="stale_option_symbol_freshness_refresh",
                        )
                    if list(refresh_payload.get("subscribe_tokens") or []) or list(
                        refresh_payload.get("unsubscribe_tokens") or []
                    ):
                        refresh_ok = globals()["_apply_subscription_delta"](
                            kws,
                            subscribe_tokens=list(refresh_payload.get("subscribe_tokens") or []),
                            unsubscribe_tokens=list(refresh_payload.get("unsubscribe_tokens") or []),
                            reason="stale_option_prune_refresh",
                        )
                    _log_ws(
                        "FEED_OPTION_PRUNE_REFRESH",
                        {
                            "reason": refresh_reason,
                            "refresh_mode": refresh_mode,
                            "refresh_sec": float(refresh_payload.get("refresh_sec") or 0.0),
                            "drift_refresh_sec": float(refresh_payload.get("drift_refresh_sec") or 0.0),
                            "previous_count": int(refresh_payload.get("previous_count") or 0),
                            "desired_count": int(refresh_payload.get("desired_count") or 0),
                            "subscribe_count": int(refresh_payload.get("subscribe_count") or 0),
                            "unsubscribe_count": int(refresh_payload.get("unsubscribe_count") or 0),
                            "refresh_token_count": int(refresh_payload.get("refresh_token_count") or len(refresh_tokens)),
                            "refresh_applied": bool(refresh_ok),
                            "force_resubscribe_current": bool(refresh_payload.get("force_resubscribe_current")),
                            "freshness_urgent": bool(refresh_payload.get("freshness_urgent")),
                            "fresh_count": int(refresh_payload.get("fresh_count") or 0),
                            "stale_count": int(refresh_payload.get("stale_count") or 0),
                            "fresh_ratio": float(refresh_payload.get("fresh_ratio") or 0.0),
                            "max_age_sec": float(refresh_payload.get("max_age_sec") or 0.0),
                            "mutation_eligible_symbols": list(refresh_payload.get("mutation_eligible_symbols") or []),
                            "mutation_skipped_symbols": list(refresh_payload.get("mutation_skipped_symbols") or []),
                            "mutation_skip_reason_by_symbol": dict(
                                refresh_payload.get("mutation_skip_reason_by_symbol") or {}
                            ),
                            "mutation_window_count_by_symbol": dict(
                                refresh_payload.get("mutation_window_count_by_symbol") or {}
                            ),
                            "mutation_guard_ok": bool(refresh_payload.get("mutation_guard_ok")),
                            "mutation_guard_reason": str(refresh_payload.get("mutation_guard_reason") or ""),
                            "mutation_guard_payload": dict(refresh_payload.get("mutation_guard_payload") or {}),
                            "min_stale_tokens_required": int(refresh_payload.get("min_stale_tokens_required") or 0),
                            "mutation_max_fresh_ratio": float(refresh_payload.get("mutation_max_fresh_ratio") or 0.0),
                            "mutation_consecutive_windows_required": int(
                                refresh_payload.get("mutation_consecutive_windows_required") or 0
                            ),
                            "pruned_stale_option_count_by_symbol": dict(
                                refresh_payload.get("pruned_stale_option_count_by_symbol") or {}
                            ),
                        },
                    )
                elif bool(refresh_payload.get("freshness_urgent")) or list(refresh_payload.get("mutation_skipped_symbols") or []):
                    _log_ws(
                        "FEED_OPTION_PRUNE_REFRESH_SKIPPED",
                        {
                            "reason": str(refresh_payload.get("reason") or "mutation_skipped"),
                            "refresh_mode": str(refresh_payload.get("refresh_mode") or "delta"),
                            "freshness_urgent": bool(refresh_payload.get("freshness_urgent")),
                            "freshness_urgent_symbols": list(refresh_payload.get("freshness_urgent_symbols") or []),
                            "mutation_eligible_symbols": list(refresh_payload.get("mutation_eligible_symbols") or []),
                            "mutation_skipped_symbols": list(refresh_payload.get("mutation_skipped_symbols") or []),
                            "mutation_skip_reason_by_symbol": dict(
                                refresh_payload.get("mutation_skip_reason_by_symbol") or {}
                            ),
                            "mutation_window_count_by_symbol": dict(
                                refresh_payload.get("mutation_window_count_by_symbol") or {}
                            ),
                            "mutation_guard_ok": bool(refresh_payload.get("mutation_guard_ok")),
                            "mutation_guard_reason": str(refresh_payload.get("mutation_guard_reason") or ""),
                        },
                    )
            except Exception:
                pass
            stale_option_mutation_guard_blocked, stale_option_mutation_guard_payload = _stale_option_mutation_guard_blocked(
                refresh_payload
            )
            if expected_option_tokens > 0 and subscribed_option_tokens <= 0:
                if (now_loop - float(last_option_subscribe_retry)) >= max(1.0, soft_cooldown):
                    last_option_subscribe_retry = now_loop
                    _log_ws(
                        "FEED_OPTION_SUBSCRIPTIONS_MISSING",
                        {
                            "expected_option_tokens": int(expected_option_tokens),
                            "subscribed_option_tokens": int(subscribed_option_tokens),
                            "subscribed_tokens_count_by_symbol": _subscribed_tokens_count_by_symbol(_LAST_TOKENS),
                            "reason": "market_open_option_subscriptions_missing",
                        },
                        throttle_key="FEED_OPTION_SUBSCRIPTIONS_MISSING",
                    )
                    restart_depth_ws(
                        reason="market_open_option_subscriptions_missing",
                        ignore_cooldown=True,
                        force_full_restart=True,
                    )
            try:
                get_feed_health_monitor().maybe_trigger_reconnect(
                    reason_prefix="watchdog_down",
                    now_epoch=now_loop,
                )
            except Exception:
                pass
            silent_triggered = _maybe_trigger_silent_reconnect(
                now_epoch=now_loop,
                current_tokens=set(int(t) for t in (_LAST_TOKENS or []) if int(t) > 0),
                underlying_tokens=set(int(t) for t in (_UNDERLYING_TOKENS or set()) if int(t) > 0),
                last_global_msg_epoch=_LAST_WS_TICK_EPOCH,
                last_msg_by_token=dict(_LAST_MSG_TS_BY_TOKEN),
                state=silent_state,
                index_threshold_sec=silent_index_sec,
                option_threshold_sec=silent_option_sec,
                confirm_needed=silent_confirm_cycles,
                backoff_min_sec=silent_backoff_min_sec,
                backoff_max_sec=silent_backoff_max_sec,
                force_full_restart_after_sec=silent_force_full_restart_sec,
                restart_cb=restart_depth_ws,
            )
            if silent_triggered:
                _emit_snapshot(now_loop)
                continue
            tick_age = None
            if _LAST_WS_TICK_EPOCH > 0:
                tick_age = now_loop - _LAST_WS_TICK_EPOCH
            if tick_age is not None and tick_age > no_ticks_sec:
                no_tick_strikes += 1
                backoff = no_ticks_base_backoff * (2 ** min(no_tick_strikes - 1, 3))
                _emit_feed_health(
                    "FEED_STALE",
                    {
                        "reason": "no_ws_ticks",
                        "tick_age_sec": tick_age,
                        "threshold_sec": no_ticks_sec,
                        "strikes": no_tick_strikes,
                        "last_ws_tick_epoch": _LAST_WS_TICK_EPOCH if _LAST_WS_TICK_EPOCH > 0 else None,
                        "last_db_tick_epoch": last_db_tick_epoch,
                        "last_db_tick_age_sec": last_db_tick_age,
                    },
                )
                _log_ws(
                    "FEED_NO_TICKS_DETECTED",
                    {
                        "tick_age_sec": tick_age,
                        "threshold_sec": no_ticks_sec,
                        "strikes": no_tick_strikes,
                        "backoff_sec": backoff,
                    },
                    throttle_key="FEED_NO_TICKS_DETECTED",
                )
                if (now_loop - last_no_tick_restart) >= backoff:
                    last_no_tick_restart = now_loop
                    restart_depth_ws(
                        reason=f"no_ticks_age={tick_age:.1f}s",
                        ignore_cooldown=True,
                        force_full_restart=True,
                    )
                _emit_snapshot(now_loop)
                continue
            no_tick_strikes = 0
            latest = None
            try:
                # find latest depth ts in store
                for v in depth_store.books.values():
                    ts = v.get("ts_epoch") or v.get("ts")
                    if ts is not None:
                        latest = max(latest or 0.0, float(ts))
            except Exception:
                latest = None
            if latest is None:
                now = time.time()
                # Warm-up wait until first fresh tick arrives after connect/reconnect.
                if now - last_warmup_log >= 30.0:
                    _log_ws("FEED_WARMUP_WAIT", {}, throttle_key="FEED_WARMUP_WAIT")
                    last_warmup_log = now
                _emit_snapshot(now_loop)
                continue
            age = time.time() - latest
            if _WARMUP_PENDING:
                _log_ws("FEED_WARMUP_DONE", {"first_age_sec": age})
                _WARMUP_PENDING = False
            if age <= max_age:
                if depth_stale_strikes:
                    _log_ws("FEED_RECOVERED", {"age_sec": age, "strikes": depth_stale_strikes})
                depth_stale_strikes = 0
            else:
                depth_stale_strikes += 1
                _log_ws(
                    "FEED_STALE_DETECTED",
                    {"age_sec": age, "strikes": depth_stale_strikes, "max_age": max_age},
                    throttle_key="FEED_STALE_DETECTED",
                )

                if depth_stale_strikes >= 2:
                    backoff = soft_cooldown * (2 ** min(depth_stale_strikes - 2, 3))
                    if time.time() - last_soft >= backoff:
                        last_soft = time.time()
                        try:
                            _resubscribe_full(kws, reason=f"soft_reset:strikes={depth_stale_strikes}")
                            _log_ws("FEED_SOFT_RESET_OK", {"tokens": len(tokens), "backoff_sec": backoff})
                        except Exception as exc:
                            _log_ws("FEED_SOFT_RESET_ERROR", {"error": str(exc), "backoff_sec": backoff})

                if depth_stale_strikes >= strikes_to_restart:
                    restart_depth_ws(
                        reason=f"depth_stale_age={age:.1f}s",
                        ignore_cooldown=True,
                        force_full_restart=True,
                    )
                    _emit_snapshot(now_loop)
                    continue

            if stale_option_mutation_guard_blocked:
                _log_ws(
                    "FEED_REBALANCE_SKIPPED",
                    {
                        **stale_option_mutation_guard_payload,
                        "guard_reason": "stale_option_mutation_guard",
                        "subscribe_count": 0,
                        "unsubscribe_count": 0,
                    },
                )
                _emit_snapshot(now_loop)
                continue
            now_reb = time.time()
            eval_interval = max(5.0, min(rebalance_cooldown_sec, 30.0))
            if (now_reb - float(rebalance_state.get("last_eval_ts") or 0.0)) < eval_interval:
                _emit_snapshot(now_loop)
                continue
            rebalance_state["last_eval_ts"] = now_reb
            try:
                desired_tokens_raw, resolution = build_subscription_tokens(
                    symbols=list(getattr(cfg, "SYMBOLS", []) or []),
                    max_tokens=int(getattr(cfg, "DEPTH_SUBSCRIPTION_MAX_TOKENS", 150)),
                )
            except Exception as exc:
                _log_ws("FEED_REBALANCE_BUILD_ERROR", {"error": str(exc)})
                _emit_snapshot(now_loop)
                continue

            sticky_tokens = set(int(t) for t in get_sticky_tokens() if t is not None)
            atm_by_symbol, step_by_symbol, underlying_tokens = _resolution_atm_step_and_underlyings(resolution)
            desired_tokens = set(int(t) for t in desired_tokens_raw if t is not None)
            desired_tokens.update(sticky_tokens)
            desired_tokens.update(underlying_tokens)

            decision = _compute_rebalance_decision(
                current_tokens=set(int(t) for t in (_LAST_TOKENS or [])),
                desired_tokens=desired_tokens,
                sticky_tokens=sticky_tokens,
                underlying_tokens=underlying_tokens,
                last_rebalance_ts=rebalance_state.get("last_rebalance_ts"),
                now_ts=now_reb,
                cooldown_sec=rebalance_cooldown_sec,
                threshold_steps=atm_shift_threshold_steps,
                last_atm_by_symbol=rebalance_state.get("last_atm_by_symbol"),
                next_atm_by_symbol=atm_by_symbol,
                step_by_symbol=step_by_symbol,
            )
            rebalance_state["last_atm_by_symbol"] = dict(atm_by_symbol)
            reason = str(decision.get("reason") or "rebalance")
            if bool(decision.get("should_rebalance")):
                ok_apply = globals()["_apply_subscription_delta"](
                    kws,
                    decision.get("subscribe_tokens") or [],
                    decision.get("unsubscribe_tokens") or [],
                    reason=reason,
                )
                if ok_apply:
                    rebalance_state["last_rebalance_ts"] = now_reb
            else:
                if reason != str(rebalance_state.get("last_reason") or ""):
                    _log_ws(
                        "FEED_REBALANCE_SKIPPED",
                        {
                            "reason": reason,
                            "shift_steps": decision.get("shift_steps"),
                            "cooldown_age_sec": decision.get("cooldown_age_sec"),
                            "current_tokens": len(_LAST_TOKENS or []),
                            "desired_tokens": len(desired_tokens),
                            "sticky_tokens": len(sticky_tokens),
                            "underlying_tokens": len(underlying_tokens),
                        },
                    )
                    rebalance_state["last_reason"] = reason
            _emit_snapshot(now_loop)

    kws.on_connect = on_connect
    kws.on_reconnect = on_reconnect
    kws.on_error = on_error
    kws.on_close = on_close
    previous_on_message = getattr(kws, "on_message", None)
    def on_message_current(ws, payload, is_binary):
        campaign_raw_diagnostics.observe_raw_message(payload, is_binary)
        if previous_on_message is not None:
            previous_on_message(ws, payload, is_binary)

    kws.on_message = on_message_current
    _register_on_ticks_callback(kws, _generation_is_current, on_ticks)
    watchdog_thread = threading.Thread(target=_watchdog)
    try:
        watchdog_thread.name = "kite-depth-watchdog"
    except Exception:
        pass
    try:
        watchdog_thread.daemon = False
    except Exception:
        pass
    _WATCHDOG_THREAD = watchdog_thread
    watchdog_thread.start()
    lifecycle.register(
        "kite-depth-watchdog",
        stop_fn=lambda: stop_depth_ws(reason="lifecycle_stop"),
        join_fn=lambda timeout_sec=3.0: _join_thread_safe(watchdog_thread, timeout_sec),
    )
    try:
        from twisted.internet import reactor
        if getattr(reactor, "_started", False) and not getattr(reactor, "running", False):
            raise RuntimeError("ReactorNotRestartable: Twisted reactor was started and stopped")
        kws.connect(threaded=True)
    except Exception as exc:
        reconnect_blocked_reason = None
        if _is_reactor_not_restartable_error(exc):
            internal_retry_state = _disable_kiteticker_internal_retry(reason=f"start_depth_ws:{type(exc).__name__}", ticker=kws)
            reconnect_blocked_reason = _set_reconnect_blocked_reason(_reactor_not_restartable_block_reason())
            _log_ws(
                "FEED_RESTART_PROCESS_RECOVERY_REQUIRED",
                {
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "reconnect_blocked_reason": reconnect_blocked_reason,
                    **{k: v for k, v in internal_retry_state.items() if v is not None},
                },
            )
        else:
            _RUNTIME_STATE = "SUBSCRIBE_FAILED"
            _LAST_RUNTIME_ERROR = f"connect_failed:{type(exc).__name__}:{exc}"[:1000]
        _persist_runtime_snapshot_row(
            ws_connected=False,
            source="start_depth_ws:connect_failed",
            runtime_state=_RUNTIME_STATE,
            last_error=_LAST_RUNTIME_ERROR if reconnect_blocked_reason is None else reconnect_blocked_reason,
            reconnect_blocked_reason=reconnect_blocked_reason,
            internal_retry_disabled=bool(internal_retry_state.get("internal_retry_disabled")) if reconnect_blocked_reason is not None else None,
            stop_retry_called=bool(internal_retry_state.get("stop_retry_called")) if reconnect_blocked_reason is not None else None,
            factory_stop_trying_called=(
                bool(internal_retry_state.get("factory_stop_trying_called")) if reconnect_blocked_reason is not None else None
            ),
            auto_reconnect_disabled=bool(internal_retry_state.get("auto_reconnect_disabled")) if reconnect_blocked_reason is not None else None,
            internal_retry_error=str(internal_retry_state.get("error") or "").strip() or None if reconnect_blocked_reason is not None else None,
            internal_retry_reason=str(internal_retry_state.get("reason") or "").strip() or None if reconnect_blocked_reason is not None else None,
        )
        return False
    if _LAST_DISCONNECTED_CODE is not None or _LAST_DISCONNECTED_REASON:
        ws_fault_seen = True

    if _reconnect_recovery_blocked_active():
        blocked_reason = str(_RECONNECT_BLOCKED_REASON or "").strip().lower() or "unknown_reconnect_block"
        _emit_reconnect_recovery_blocked_snapshot(
            source="start_depth_ws:post_connect_recovery_blocked",
            reason=blocked_reason,
        )
        return False

    if not ws_fault_seen:
        _log_ws("ws_started", {"tokens_count": len(instrument_tokens), "ws_lifecycle_state": "STARTED"})
    return not ws_fault_seen
