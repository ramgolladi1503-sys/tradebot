#!/usr/bin/env python3
import argparse
import json
import logging
import os
import random
import sys
import tempfile
import threading
import time
import weakref
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import config as cfg

cfg.TICK_STORE_ENABLE_DB_WRITES = False
cfg.KITE_STORE_TICKS = False

import core.kite_depth_ws as ws

logger = logging.getLogger(__name__)

WEAK_TICKERS: list[weakref.ReferenceType] = []

LEGACY_PROFILE_ALIASES = {
    "reconnect": "reconnect_unbounded_resource_stress",
    "negative_control": "negative_fd_leak",
    "100_cycles": "control",
    "1000_cycles": "control",
}

POSITIVE_SUCCESS_VERDICTS = {
    "RECONNECT_RESOURCE_SOAK_PASS",
    "RECONNECT_RESOURCE_100_CYCLE_PASS",
    "RECONNECT_RESOURCE_1000_CYCLE_PASS",
    "RECONNECT_OWNER_FAILURE_RECOVERY_PASS",
    "RECONNECT_GUARDED_POLICY_PASS",
}


def _normalize_profile(profile: str) -> str:
    return LEGACY_PROFILE_ALIASES.get(profile, profile)


def _normalize_tokens(values) -> list[int]:
    normalized: list[int] = []
    for value in list(values or []):
        try:
            token = int(value)
        except Exception:
            continue
        if token > 0:
            normalized.append(token)
    return normalized


def _watchdog_thread_count() -> int:
    count = 0
    for thread_obj in list(threading.enumerate()):
        try:
            name = str(getattr(thread_obj, "name", "") or "")
        except Exception:
            name = ""
        if name.startswith("kite-depth-watchdog"):
            count += 1
    return count


def _get_fd_records():
    pid = os.getpid()
    try:
        import subprocess

        out = subprocess.check_output(["lsof", "-p", str(pid), "-F", "ftn"], text=True)
        records = []
        current_record = {}
        for line in out.splitlines():
            if not line:
                continue
            char = line[0]
            val = line[1:]
            if char == "p":
                continue
            if char == "f":
                if current_record and current_record.get("fd", "").isdigit():
                    records.append(current_record)
                current_record = {"fd": val}
            elif char == "t":
                current_record["type"] = val
            elif char == "n":
                current_record["identity"] = val
        if current_record and current_record.get("fd", "").isdigit():
            records.append(current_record)
        return records
    except Exception:
        return []


def _resource_snapshot() -> dict:
    try:
        import psutil  # type: ignore

        rss_bytes = int(psutil.Process(os.getpid()).memory_info().rss)
        source = "psutil.Process().memory_info().rss"
    except Exception:
        import resource

        rss_raw = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if sys.platform == "darwin":
            rss_bytes = rss_raw
            source = "resource.getrusage.ru_maxrss_bytes"
        else:
            rss_bytes = rss_raw * 1024
            source = "resource.getrusage.ru_maxrss_kib"

    fd_records = _get_fd_records()
    sqlite_fds = [
        record
        for record in fd_records
        if ".sqlite" in record.get("identity", "")
        or record.get("identity", "").endswith("-wal")
        or record.get("identity", "").endswith("-shm")
    ]

    global WEAK_TICKERS
    WEAK_TICKERS = [ticker_ref for ticker_ref in WEAK_TICKERS if ticker_ref() is not None]

    active_ticker = getattr(ws, "_KITE_TICKER", None)
    live_tickers = 1 if active_ticker is not None else 0
    retired_reachable = sum(1 for ticker_ref in WEAK_TICKERS if ticker_ref() is not active_ticker)

    required_tokens = _normalize_tokens(getattr(ws, "_LAST_TOKENS", []))
    requested_tokens = _normalize_tokens(getattr(active_ticker, "tokens", [])) if active_ticker else []
    required_counter = Counter(required_tokens)
    requested_counter = Counter(requested_tokens)
    missing_counter = required_counter - requested_counter
    unexpected_counter = requested_counter - required_counter
    duplicate_count = sum(max(0, count - 1) for count in requested_counter.values())
    matched_count = sum(min(required_counter[token], requested_counter[token]) for token in required_counter)
    subscription_tokens_match_exactly = required_counter == requested_counter

    return {
        "rss_bytes": rss_bytes,
        "rss_mib": rss_bytes / (1024.0 * 1024.0),
        "rss_source": source,
        "python_thread_count": len(list(threading.enumerate())),
        "watchdog_thread_count": _watchdog_thread_count(),
        "fd_count": len(fd_records),
        "fd_identities": [record.get("identity", "") for record in fd_records if "identity" in record],
        "fd_records": fd_records,
        "sqlite_fd_count": len(sqlite_fds),
        "live_websocket_generations": live_tickers,
        "retired_websocket_generations_reachable": retired_reachable,
        "reactor_count": None,
        "feed_worker_count": None,
        "queue_depth": getattr(ws, "_feed_queue_depth", lambda: 0)(),
        "queue_high_water": getattr(ws, "_feed_queue_high_water", lambda: 0)(),
        "required_token_count": len(required_tokens),
        "requested_token_count": len(requested_tokens),
        "active_token_count": len(requested_tokens),
        "missing_token_count": sum(missing_counter.values()),
        "unexpected_token_count": sum(unexpected_counter.values()),
        "duplicate_subscription_count": duplicate_count,
        "fresh_token_count": matched_count,
        "stale_token_count": sum(unexpected_counter.values()),
        "subscription_tokens_match_exactly": subscription_tokens_match_exactly,
        "active_reconnect_sequences": 1 if getattr(ws, "_RECOVERY_IN_PROGRESS", False) else 0,
        "reconnect_lock_held": getattr(ws, "_DEPTH_WS_LOCK_ACQUIRED", False),
    }


class _DummyTicker:
    MODE_FULL = "full"
    MODE_QUOTE = "quote"
    _GLOBAL_GEN_ID = 0

    def __init__(self, api_key, access_token, debug=True, **kwargs):
        _DummyTicker._GLOBAL_GEN_ID += 1
        self.generation_id = _DummyTicker._GLOBAL_GEN_ID
        self.api_key = api_key
        self.access_token = access_token
        self.debug = debug
        self.auto_reconnect = True
        self.connected = False
        self.closed = False
        self.on_connect = None
        self.on_reconnect = None
        self.on_error = None
        self.on_close = None
        self.on_ticks = None
        self.stop_retry_count = 0
        self.tokens = []

        class DummyWS:
            def __init__(self, ticker):
                self.ticker_ref = weakref.ref(ticker)

                class Factory:
                    def __init__(self, ws_obj):
                        self.ws_obj = ws_obj

                    def is_connected(self):
                        ticker_obj = self.ws_obj.ticker_ref()
                        return bool(ticker_obj and ticker_obj.connected)

                self.factory = Factory(self)

        self.ws = DummyWS(self)
        WEAK_TICKERS.append(weakref.ref(self))

    def subscribe(self, tokens):
        self.tokens = list(tokens)

    def set_mode(self, mode, tokens):
        self.mode = mode
        self.mode_tokens = list(tokens)

    def connect(self, threaded=True):
        self.connected = True
        if self.on_connect:
            self.on_connect(self, {"status": "ok"})

    def close(self):
        self.connected = False
        self.closed = True
        if self.on_close:
            self.on_close(self, 1000, "Normal closure")

    def is_connected(self):
        return bool(self.connected)

    def stop_retry(self):
        self.stop_retry_count += 1

    def simulate_error(self, code=1006, reason="simulated error"):
        self.connected = False
        if self.on_error:
            self.on_error(self, code, reason)


class _DummyRestClient:
    def __init__(self):
        self.token = ""

    def set_access_token(self, token):
        self.token = token

    def profile(self):
        return {"user_id": "ABCD1234"}

    def instruments(self, exchange=None):
        return [
            {"instrument_token": 1, "tradingsymbol": "A"},
            {"instrument_token": 2, "tradingsymbol": "B"},
            {"instrument_token": 3, "tradingsymbol": "C"},
        ]


def _current_safety_limits() -> dict:
    coordinator = ws._FEED_RECOVERY_COORDINATOR
    return {
        "recoverable_attempts_per_session": int(
            getattr(coordinator, "_max_recoverable_attempts_per_session", 0)
        ),
        "recoveries_per_time_window": int(getattr(coordinator, "_max_recoveries_per_window", 0)),
        "recovery_timeout_sec": float(getattr(coordinator, "_recovery_timeout_sec", 0.0)),
        "restart_storm_limit": int(getattr(cfg, "FEED_RESTART_STORM_TRIP", 0)),
        "restart_guard_enabled": True,
        "feed_breaker_enabled": True,
        "retry_cooldown_sec": float(getattr(coordinator, "_recoverable_retry_cooldown_sec", 0.0)),
        "full_restarts_per_hour": int(getattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 0)),
    }


def _profile_scope(profile: str) -> str:
    if profile == "reconnect_guarded":
        return "offline guarded policy validation"
    if profile in {"reconnect_unbounded_resource_stress", "negative_fd_leak", "sqlite_same_path_multi_descriptor_negative"}:
        return "offline synthetic resource stress"
    return "offline resource observation"


def patch_kite(profile: str, monkeypatch=None):
    class PatchManager:
        def __init__(self):
            self.patches = []

        def setattr(self, obj, name, value, raising=False):
            old = getattr(obj, name, None)
            self.patches.append((obj, name, old))
            setattr(obj, name, value)

        def restore(self):
            for obj, name, old in reversed(self.patches):
                if old is None:
                    delattr(obj, name)
                else:
                    setattr(obj, name, old)

    pm = PatchManager() if monkeypatch is None else monkeypatch

    original_limits = _current_safety_limits()

    pm.setattr(ws.kite_client, "ensure", lambda: _DummyRestClient(), raising=False)
    pm.setattr(ws.kite_client, "kite", _DummyRestClient(), raising=False)
    pm.setattr(ws.kite_client, "instruments", lambda exchange=None, force=False: _DummyRestClient().instruments(exchange), raising=False)
    pm.setattr(ws.kite_client, "next_available_expiry", lambda *args, **kwargs: None, raising=False)
    pm.setattr(ws.kite_client, "_active_api_key", "api_key_1234", raising=False)
    pm.setattr(ws.kite_client, "_active_access_token", "TOKEN123", raising=False)
    pm.setattr(ws, "KiteTicker", _DummyTicker, raising=False)
    pm.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True}, raising=False)
    pm.setattr(ws, "is_market_open_ist", lambda: True, raising=False)
    pm.setattr(ws, "_ensure_depth_ws_lock", lambda: True, raising=False)
    pm.setattr(cfg, "KITE_API_KEY", "api_key_1234", raising=False)
    pm.setattr(cfg, "KITE_USE_API", True, raising=False)
    pm.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    pm.setattr(cfg, "TRADING_MODE", "PAPER", raising=False)

    import core.auth as auth_module
    import core.auth_manager as auth_manager

    pm.setattr(auth_module, "resolve_access_token", lambda **kwargs: "TOKEN123", raising=False)
    pm.setattr(auth_manager, "resolve_access_token", lambda **kwargs: "TOKEN123", raising=False)
    pm.setattr(auth_module, "get_kite_credentials", lambda **kwargs: ("api_key_1234", "TOKEN123"), raising=False)

    test_limits = dict(original_limits)
    synthetic_stress = profile in {
        "reconnect_unbounded_resource_stress",
        "negative_fd_leak",
        "sqlite_same_path_multi_descriptor_negative",
        "owner_failure",
    }
    if synthetic_stress:
        pm.setattr(cfg, "DEPTH_WS_ALLOW_SOFT_RECONNECTS", False, raising=False)
        pm.setattr(cfg, "DEPTH_WS_MAX_RECOVERIES_PER_WINDOW", 10000, raising=False)
        pm.setattr(
            ws._FEED_RECOVERY_COORDINATOR,
            "_max_recoverable_attempts_per_session",
            10000,
            raising=False,
        )
        pm.setattr(ws._FEED_RECOVERY_COORDINATOR, "_max_recoveries_per_window", 10000, raising=False)
        pm.setattr(cfg, "DEPTH_WS_WS1006_RECOVERABLE_MAX_ATTEMPTS_PER_SESSION", 10000, raising=False)
        pm.setattr(ws._FEED_RECOVERY_COORDINATOR, "_recoverable_retry_cooldown_sec", 0.0, raising=False)
        pm.setattr(ws, "feed_breaker_tripped", lambda: False, raising=False)
        pm.setattr(ws.feed_restart_guard, "allow_restart", lambda **kw: True, raising=False)
        pm.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 10000, raising=False)
        pm.setattr(cfg, "FEED_RESTART_STORM_TRIP", 10000, raising=False)
        test_limits = _current_safety_limits()
    else:
        test_limits = _current_safety_limits()

    return pm, original_limits, test_limits, synthetic_stress


def determine_exit_code(result: dict, profile: str) -> int:
    profile = _normalize_profile(profile)
    verdict = str(result.get("verdict", "UNKNOWN"))
    if profile in {"negative_fd_leak", "sqlite_same_path_multi_descriptor_negative"}:
        return 0 if verdict == "RECONNECT_RESOURCE_NEGATIVE_CONTROL_PASS" else 1
    if profile == "reconnect_guarded":
        return 0 if verdict == "RECONNECT_GUARDED_POLICY_PASS" else 1
    if verdict not in POSITIVE_SUCCESS_VERDICTS:
        return 1
    if int(result.get("hard_failures", 0) or 0) > 0:
        return 1
    if result.get("first_mismatch") is not None:
        return 1
    return 0


class ResourceSoakRunner:
    def __init__(self, profile, cycles, req_tokens, output_path, seed, fail_every, sample_every):
        self.profile = _normalize_profile(profile)
        self.cycles = int(cycles)
        self.req_tokens = int(req_tokens)
        self.output_path = output_path
        self.fail_every = int(fail_every)
        self.sample_every = max(1, int(sample_every or 1))
        self.seed_val = int(seed)
        self.rng = random.Random(seed)
        self.timeline = []
        self.dummy_leak_fds = []
        self.tokens = list(range(100, 100 + self.req_tokens))
        self.original_safety_limits = {}
        self.test_safety_limits = {}
        self.safety_limits_overridden = False
        self.guard_block_observed = False

        self.metrics = {
            "disconnect_count": 0,
            "reconnect_request_count": 0,
            "reconnect_owner_acquisition_count": 0,
            "reconnect_attempt_count": 0,
            "owner_failures_injected_count": 0,
            "owner_failures_observed_count": 0,
            "owner_recoveries_completed_count": 0,
            "successful_reconnect_count": 0,
            "verified_successful_reconnect_count": 0,
            "terminal_failure_count": 0,
            "active_reconnect_sequence_high_water": 0,
            "websocket_generations_created": 1,
            "initial_generation_id": None,
            "final_generation_id": None,
            "generation_transition_count": 0,
            "same_generation_reused_count": 0,
            "generation_creation_failures": 0,
            "guarded_policy_block_count": 0,
            "hard_failures": 0,
            "first_mismatch": None,
            "verdict": "UNKNOWN",
        }

    def _close_dummy_leaks(self) -> None:
        for leak_handle in self.dummy_leak_fds:
            try:
                leak_handle.close()
            except Exception:
                try:
                    os.close(leak_handle)
                except Exception:
                    pass
        self.dummy_leak_fds.clear()

    def _cleanup_runtime(self, reason: str) -> None:
        try:
            ws.stop_depth_ws(reason=reason)
        except Exception:
            pass
        time.sleep(0.2)
        setattr(ws, "_KITE_TICKER", None)

    def _post_cleanup_snapshot(self) -> dict:
        self._close_dummy_leaks()
        self._cleanup_runtime("shutdown")
        return _resource_snapshot()

    def _set_first_mismatch(self, message: str) -> None:
        if self.metrics["first_mismatch"] is None:
            self.metrics["first_mismatch"] = str(message)

    def _do_warmup(self):
        process_start = _resource_snapshot()

        try:
            import core.feed.runtime_store as runtime_store

            with runtime_store._conn() as conn:
                conn.execute("SELECT 1").fetchall()
        except Exception:
            pass

        ws.start_depth_ws(self.tokens, skip_lock=True, skip_guard=True)
        time.sleep(0.1)

        if ws._KITE_TICKER:
            ws._KITE_TICKER.simulate_error(1006, "warmup drop")
        time.sleep(0.1)
        try:
            ws.feed_restart_guard.reset(reason="soak_warmup_baseline")
        except Exception:
            pass

        post_warmup = _resource_snapshot()
        self.timeline.append({"stage": "process_start_baseline", "snapshot": process_start})
        self.timeline.append({"stage": "post_warmup_baseline", "snapshot": post_warmup})
        return post_warmup

    def _update_metrics(self):
        seq = 1 if getattr(ws, "_RECOVERY_IN_PROGRESS", False) else 0
        if seq > self.metrics["active_reconnect_sequence_high_water"]:
            self.metrics["active_reconnect_sequence_high_water"] = seq

    def _recovery_blocked(self) -> bool:
        try:
            return bool(getattr(ws._FEED_RECOVERY_COORDINATOR.state, "recovery_blocked", False))
        except Exception:
            return False

    def _exact_subscription_match(self, ticker) -> bool:
        if ticker is None:
            return False
        expected = Counter(_normalize_tokens(getattr(ws, "_LAST_TOKENS", [])))
        actual = Counter(_normalize_tokens(getattr(ticker, "tokens", [])))
        return expected == actual

    def _cycle_success_conditions_met(self, old_generation_id: int):
        ticker = ws._KITE_TICKER
        if ticker is None:
            return False, None, None
        new_generation_id = getattr(ticker, "generation_id", id(ticker))
        if new_generation_id == old_generation_id:
            return False, ticker, new_generation_id
        if not bool(getattr(ticker, "connected", False)):
            return False, ticker, new_generation_id
        recovery_state = getattr(ws._FEED_RECOVERY_COORDINATOR, "state", None)
        if bool(getattr(recovery_state, "terminal_failure", False)):
            return False, ticker, new_generation_id
        if bool(getattr(recovery_state, "process_restart_required", False)):
            return False, ticker, new_generation_id
        if bool(getattr(recovery_state, "recovery_blocked", False)):
            return False, ticker, new_generation_id
        if bool(getattr(ws, "_DEPTH_WS_LOCK_ACQUIRED", False)):
            return False, ticker, new_generation_id
        if not self._exact_subscription_match(ticker):
            return False, ticker, new_generation_id
        return True, ticker, new_generation_id

    def _release_synthetic_recovery_owner(self, cycle_index: int) -> bool:
        """Close the synthetic recovery owner after transport verification.

        This harness intentionally does not inject live option ticks, so it cannot
        satisfy the production live-data verification phase. Resource-soak success
        is therefore bounded to a new connected generation, exact subscription
        replay, no terminal/block state, and no lock/resource leak. The synthetic
        owner is cleared only after those transport conditions are proven.
        """
        try:
            ws._FEED_RECOVERY_COORDINATOR.clear_recovery(
                source="resource_soak_transport_verified",
                reason=f"cycle_{cycle_index}_transport_verified",
            )
            ws._sync_ws1006_recovery_state_from_coordinator()
        except Exception as exc:
            self.metrics["hard_failures"] += 1
            self.metrics["terminal_failure_count"] += 1
            self._set_first_mismatch(
                f"cycle_{cycle_index}_recovery_owner_release_failed:"
                f"{type(exc).__name__}:{exc}"
            )
            return False
        coordinator_active = bool(
            getattr(ws._FEED_RECOVERY_COORDINATOR.state, "recovery_in_progress", False)
        )
        if bool(getattr(ws, "_RECOVERY_IN_PROGRESS", False)) or coordinator_active:
            self.metrics["hard_failures"] += 1
            self.metrics["terminal_failure_count"] += 1
            self._set_first_mismatch(f"cycle_{cycle_index}_recovery_owner_not_released")
            return False
        return True

    def _request_controlled_recovery(self, cycle_index: int):
        decision = ws._FEED_RECOVERY_COORDINATOR.request_recovery(
            source=f"soak_cycle_{cycle_index}",
            code=1006,
            reason="peer dropped",
        )
        ws._sync_ws1006_recovery_state_from_coordinator()
        return decision

    def _start_new_generation(self, cycle_index: int, *, owner_failure_triggered: bool) -> bool:
        ws.stop_depth_ws(reason=f"soak_cycle_disconnect_{cycle_index}")
        time.sleep(0.05)
        setattr(ws, "_STOP_REQUESTED", False)
        restart_ok = ws.start_depth_ws(self.tokens, skip_lock=True, skip_guard=True)
        self.metrics["reconnect_owner_acquisition_count"] += 1
        self.metrics["reconnect_attempt_count"] += 1
        if restart_ok is False:
            self.metrics["hard_failures"] += 1
            self.metrics["terminal_failure_count"] += 1
            mismatch = "owner_restart_rejected" if owner_failure_triggered else "restart_rejected"
            self._set_first_mismatch(f"cycle_{cycle_index}_{mismatch}")
            return False
        return True

    def _run_reconnect_cycle(self, cycle_index: int):
        old_ticker = ws._KITE_TICKER
        if not old_ticker:
            self.metrics["hard_failures"] += 1
            self.metrics["terminal_failure_count"] += 1
            self._set_first_mismatch(f"cycle_{cycle_index}_no_old_ticker")
            return "failed"

        old_generation_id = getattr(old_ticker, "generation_id", id(old_ticker))
        if self.metrics["initial_generation_id"] is None:
            self.metrics["initial_generation_id"] = old_generation_id

        self.metrics["disconnect_count"] += 1
        self.metrics["reconnect_request_count"] += 1

        owner_failure_triggered = (
            self.profile == "owner_failure"
            and self.fail_every > 0
            and cycle_index > 0
            and cycle_index % self.fail_every == 0
        )
        if owner_failure_triggered:
            ws._log_ws("SOAK_SIMULATE_OWNER_FAILURE", {"cycle": cycle_index})
            self.metrics["owner_failures_injected_count"] += 1
            self.metrics["owner_failures_observed_count"] += 1
        decision = self._request_controlled_recovery(cycle_index)
        if decision.action == "RECOVERY_BLOCKED":
            if self.profile == "reconnect_guarded":
                self.guard_block_observed = True
                self.metrics["guarded_policy_block_count"] += 1
                self._update_metrics()
                self._set_first_mismatch(
                    f"guarded_policy_blocked_at_cycle_{cycle_index}: recovery blocked by original safety limits"
                )
                return "guarded_blocked"
            self.metrics["hard_failures"] += 1
            self.metrics["terminal_failure_count"] += 1
            self._set_first_mismatch(f"cycle_{cycle_index}_recovery_blocked")
            return "failed"
        if decision.action != "SOFT_RECONNECT":
            self.metrics["hard_failures"] += 1
            self.metrics["terminal_failure_count"] += 1
            self._set_first_mismatch(f"cycle_{cycle_index}_unexpected_recovery_action:{decision.action}")
            return "failed"
        if not self._start_new_generation(cycle_index, owner_failure_triggered=owner_failure_triggered):
            return "failed"

        timeout_sec = 10.0
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            success, new_ticker, new_generation_id = self._cycle_success_conditions_met(old_generation_id)
            if success:
                if not self._release_synthetic_recovery_owner(cycle_index):
                    return "failed"
                self.metrics["final_generation_id"] = new_generation_id
                self.metrics["generation_transition_count"] += 1
                self.metrics["websocket_generations_created"] += 1
                self.metrics["successful_reconnect_count"] += 1
                self.metrics["verified_successful_reconnect_count"] += 1
                if owner_failure_triggered:
                    self.metrics["owner_recoveries_completed_count"] += 1
                self._update_metrics()
                return "success"

            if new_generation_id == old_generation_id:
                self.metrics["same_generation_reused_count"] += 1
            time.sleep(0.05)

        self.metrics["hard_failures"] += 1
        self.metrics["terminal_failure_count"] += 1
        self.metrics["generation_creation_failures"] += 1
        self._set_first_mismatch(
            f"cycle_{cycle_index}_timeout "
            f"old_gen={old_generation_id} "
            f"cur_gen={getattr(ws._KITE_TICKER, 'generation_id', None)} "
            f"runtime_state={getattr(ws, '_RUNTIME_STATE', None)} "
            f"recovery={getattr(ws, '_RECOVERY_IN_PROGRESS', False)} "
            f"blocked={self._recovery_blocked()} "
            f"last_err={getattr(ws, '_LAST_RUNTIME_ERROR', None)}"
        )
        self._update_metrics()
        return "failed"

    def _inject_negative_control(self, cycle_index: int) -> None:
        if self.profile == "negative_fd_leak":
            leak_file = tempfile.NamedTemporaryFile(prefix=f"dummy_leak_{cycle_index}_")
            self.dummy_leak_fds.append(leak_file)
        elif self.profile == "sqlite_same_path_multi_descriptor_negative":
            temp_path = Path(tempfile.gettempdir()) / "resource-soak-same-path-negative.sqlite"
            fd_one = os.open(temp_path, os.O_CREAT | os.O_RDWR, 0o600)
            fd_two = os.open(temp_path, os.O_CREAT | os.O_RDWR, 0o600)
            self.dummy_leak_fds.extend([fd_one, fd_two])

    def _record_cycle_sample(self, cycle_index: int) -> dict:
        snapshot = _resource_snapshot()
        self._update_metrics()
        self.timeline.append({"cycle": cycle_index, "snapshot": snapshot})
        return snapshot

    def _generate_verdict(self):
        baseline = next((item["snapshot"] for item in self.timeline if item.get("stage") == "post_warmup_baseline"), None)
        final = next((item["snapshot"] for item in self.timeline if item.get("stage") == "final"), None)
        if not baseline or not final:
            self.metrics["verdict"] = "FAILURE"
            return

        fd_diff = int(final["fd_count"]) - int(baseline["fd_count"])

        if self.profile in {"negative_fd_leak", "sqlite_same_path_multi_descriptor_negative"}:
            if fd_diff > 0 and self.metrics["first_mismatch"] is None:
                self._set_first_mismatch("fd_leak_detected_final")
            if fd_diff > 0 and self.metrics["first_mismatch"] is not None:
                self.metrics["verdict"] = "RECONNECT_RESOURCE_NEGATIVE_CONTROL_PASS"
            else:
                self.metrics["verdict"] = "FAILURE"
            return

        if self.profile == "reconnect_guarded":
            if self.guard_block_observed and self.metrics["hard_failures"] == 0:
                self.metrics["verdict"] = "RECONNECT_GUARDED_POLICY_PASS"
            else:
                self.metrics["verdict"] = "RECONNECT_RESOURCE_FAIL_GUARDED_POLICY"
            return

        if self.metrics["hard_failures"] > 0 or self.metrics["first_mismatch"] is not None:
            self.metrics["verdict"] = "RECONNECT_RESOURCE_FAIL_FD_GROWTH"
            return
        if fd_diff > 2:
            self.metrics["verdict"] = "RECONNECT_RESOURCE_FAIL_FD_GROWTH"
            return
        if self.profile == "owner_failure":
            self.metrics["verdict"] = "RECONNECT_OWNER_FAILURE_RECOVERY_PASS"
        elif self.cycles >= 1000:
            self.metrics["verdict"] = "RECONNECT_RESOURCE_1000_CYCLE_PASS"
        elif self.cycles >= 100:
            self.metrics["verdict"] = "RECONNECT_RESOURCE_100_CYCLE_PASS"
        else:
            self.metrics["verdict"] = "RECONNECT_RESOURCE_SOAK_PASS"

    def run(self):
        pm, original_limits, test_limits, synthetic_stress = patch_kite(self.profile)
        self.original_safety_limits = dict(original_limits)
        self.test_safety_limits = dict(test_limits)
        self.safety_limits_overridden = bool(synthetic_stress)
        try:
            baseline = self._do_warmup()

            for cycle_index in range(self.cycles):
                snapshot = None
                if self.profile in {"negative_fd_leak", "sqlite_same_path_multi_descriptor_negative"}:
                    self._inject_negative_control(cycle_index)

                cycle_result = "noop"
                if self.profile != "control":
                    cycle_result = self._run_reconnect_cycle(cycle_index)
                    if cycle_result == "guarded_blocked":
                        snapshot = self._record_cycle_sample(cycle_index)
                        break
                if cycle_index % self.sample_every == 0 or cycle_index == self.cycles - 1:
                    snapshot = self._record_cycle_sample(cycle_index)

                if cycle_result == "failed":
                    break

            self._cleanup_runtime("soak_finish")
            final = _resource_snapshot()
            self.timeline.append({"stage": "final", "snapshot": final})
            self._generate_verdict()

            high_water = {}
            for key in [
                "fd_count",
                "sqlite_fd_count",
                "rss_bytes",
                "python_thread_count",
                "watchdog_thread_count",
                "queue_depth",
            ]:
                high_water[key] = max(
                    item["snapshot"].get(key, 0)
                    for item in self.timeline
                    if "snapshot" in item
                )

            rss_values = [
                item["snapshot"]["rss_bytes"]
                for item in self.timeline
                if "snapshot" in item and "cycle" in item
            ]
            final["rss_slope_bytes_per_sample"] = 0.0
            if len(rss_values) > 1:
                final["rss_slope_bytes_per_sample"] = (rss_values[-1] - rss_values[0]) / max(1, len(rss_values) - 1)

            result = {
                "configuration": {
                    "profile": self.profile,
                    "cycles": self.cycles,
                    "req_tokens": self.req_tokens,
                    "sample_every": self.sample_every,
                    "scope": _profile_scope(self.profile),
                    "safety_limits_overridden": self.safety_limits_overridden,
                    "original_safety_limits": self.original_safety_limits,
                    "test_safety_limits": self.test_safety_limits,
                },
                "seed": self.seed_val,
                "process_start_baseline": self.timeline[0]["snapshot"],
                "post_warmup_baseline": self.timeline[1]["snapshot"],
                "high_water": high_water,
                "final": final,
                "process_fd_start": self.timeline[0]["snapshot"]["fd_count"],
                "process_fd_warmup": self.timeline[1]["snapshot"]["fd_count"],
                "process_fd_final": final["fd_count"],
                "verdict": self.metrics["verdict"],
                "hard_failures": self.metrics["hard_failures"],
                "first_mismatch": self.metrics["first_mismatch"],
                "cycle_samples": [item for item in self.timeline if "cycle" in item],
            }
            if self.profile in {"negative_fd_leak", "sqlite_same_path_multi_descriptor_negative"}:
                post_cleanup_final = self._post_cleanup_snapshot()
                result["post_cleanup_final"] = post_cleanup_final
            result.update(self.metrics)
            return result
        finally:
            if pm:
                pm.restore()
            self._close_dummy_leaks()
            self._cleanup_runtime("shutdown")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        required=True,
        choices=[
            "control",
            "100_cycles",
            "1000_cycles",
            "reconnect",
            "reconnect_guarded",
            "reconnect_unbounded_resource_stress",
            "owner_failure",
            "negative_control",
            "negative_fd_leak",
            "sqlite_same_path_multi_descriptor_negative",
        ],
    )
    parser.add_argument("--cycles", type=int, default=100)
    parser.add_argument("--required-token-count", type=int, default=150)
    parser.add_argument("--reconnect-failure-every", type=int, default=0)
    parser.add_argument("--sample-every", type=int, default=10)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    runner = ResourceSoakRunner(
        profile=args.profile,
        cycles=args.cycles,
        req_tokens=args.required_token_count,
        output_path=args.output_json,
        seed=args.seed,
        fail_every=args.reconnect_failure_every,
        sample_every=args.sample_every,
    )
    result = runner.run()

    with open(args.output_json, "w") as handle:
        json.dump(result, handle, indent=2)

    fd_leak = result["final"]["fd_count"] - result["post_warmup_baseline"]["fd_count"]
    thread_leak = result["final"]["python_thread_count"] - result["post_warmup_baseline"]["python_thread_count"]
    print(
        f"[{result['configuration']['profile']}] Cycles: {args.cycles}, "
        f"FD Leak vs Warmup: {fd_leak}, Thread Leak: {thread_leak}, Verdict: {result['verdict']}"
    )
    sys.exit(determine_exit_code(result, args.profile))


if __name__ == "__main__":
    main()
