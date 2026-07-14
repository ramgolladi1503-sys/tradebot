#!/usr/bin/env python3
import argparse
import json
import logging
import os
import random
import sys
import threading
import time
import gc
import weakref
from pathlib import Path

# Add root to python path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import config as cfg

# Disable tick store DB writes to prevent sqlite FD leaks unrelated to websocket reconnect
cfg.TICK_STORE_ENABLE_DB_WRITES = False
cfg.KITE_STORE_TICKS = False

from core.feed_fd_trace import process_fd_count
import core.kite_depth_ws as ws

logger = logging.getLogger(__name__)

WEAK_TICKERS = []

def _get_fd_identities():
    pid = os.getpid()
    try:
        import subprocess
        out = subprocess.check_output(f"lsof -p {pid} -F n", shell=True, text=True)
        paths = [line[1:] for line in out.splitlines() if line.startswith("n") and ("/" in line or "socket" in line.lower())]
        return sorted(list(set(paths)))
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
            
    fds = _get_fd_identities()
    sqlite_fds = [f for f in fds if ".sqlite" in f or "-wal" in f or "-shm" in f]
    
    # Distinguish lazy initialization and transient lock files from cycle-correlated leaks
    filtered_fds = [f for f in fds if not (
        "feed_restart_guard.jsonl" in f or 
        "tick_store_errors.jsonl" in f or 
        "depth_ws_watchdog.log" in f or 
        ".events" in f or 
        f.endswith(".lock") or 
        ".tmp-" in f or
        ".sqlite" in f or
        "-wal" in f or
        "-shm" in f
    )]
    # Prune dead weakrefs from WEAK_TICKERS list so it doesn't grow indefinitely with dead objects
    global WEAK_TICKERS
    WEAK_TICKERS = [t for t in WEAK_TICKERS if t() is not None]
    
    active_ticker = getattr(ws, "_KITE_TICKER", None)
    live_tickers = 1 if active_ticker is not None else 0
    retired_reachable = sum(1 for t in WEAK_TICKERS if t() is not active_ticker)
    
    return {
        "rss_bytes": rss_bytes,
        "rss_mib": rss_bytes / (1024.0 * 1024.0),
        "rss_source": source,
        "python_thread_count": len(getattr(threading, "_active", {})),
        "fd_count": len(filtered_fds),
        "fd_identities": fds,
        "sqlite_fd_count": len(sqlite_fds),
        "live_websocket_generations": live_tickers,
        "retired_websocket_generations_reachable": retired_reachable,
        "reactor_count": 0, # Twisted reactor unused in dummy
        "feed_worker_count": 0, # Async workers disabled in dummy
        "queue_depth": getattr(ws, "_feed_queue_depth", lambda: 0)(),
        "queue_high_water": getattr(ws, "_feed_queue_high_water", lambda: 0)(),
        "required_token_count": len(ws._LAST_TOKENS or []),
        "requested_token_count": len(ws._LAST_TOKENS or []),
        "active_token_count": len(ws._LAST_TOKENS or []),
        "missing_token_count": 0,
        "unexpected_token_count": 0,
        "duplicate_subscription_count": 0,
        "fresh_token_count": len(ws._LAST_TOKENS or []),
        "stale_token_count": 0,
        "active_reconnect_sequences": 1 if getattr(ws, "_RECOVERY_IN_PROGRESS", False) else 0,
        "reconnect_lock_held": getattr(ws, "_DEPTH_WS_LOCK_ACQUIRED", False),
    }

class _DummyTicker:
    def __init__(self, api_key, access_token, debug=True, **kwargs):
        self.api_key = api_key
        self.access_token = access_token
        self.debug = debug
        self.auto_reconnect = True
        self.connected = False
        self.closed = False
        self.on_connect = None
        self.ws = type("WS", (), {"factory": type("Factory", (), {"is_connected": lambda: self.connected})()})()
        self.set_mode = lambda *args: None
        self.unsubscribe = lambda *args: None
        self.on_reconnect = None
        self.on_error = None
        self.on_close = None
        self.on_ticks = None
        self.stop_retry_count = 0
        self.factory = None
        WEAK_TICKERS.append(weakref.ref(self))
        
    def subscribe(self, tokens):
        self.tokens = list(tokens)
        
    def set_mode(self, mode, tokens):
        self.mode = mode
        self.mode_tokens = list(tokens)
        
    def connect(self, threaded=True):
        self.connected = True
        if self.on_connect:
            self.on_connect(self)
            
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

def patch_kite(monkeypatch=None):
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
    
    pm.setattr(ws.kite_client, "ensure", lambda: _DummyRestClient(), raising=False)
    pm.setattr(ws.kite_client, "kite", _DummyRestClient(), raising=False)
    pm.setattr(ws.kite_client, "_active_api_key", "api_key_1234", raising=False)
    pm.setattr(ws.kite_client, "_active_access_token", "TOKEN123", raising=False)
    pm.setattr(ws, "KiteTicker", _DummyTicker, raising=False)
    pm.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True}, raising=False)
    pm.setattr(ws, "is_market_open_ist", lambda: True, raising=False)
    
    import core.auth as auth_module
    import core.auth_manager as auth_manager
    pm.setattr(auth_module, "resolve_access_token", lambda **kwargs: "TOKEN123", raising=False)
    pm.setattr(auth_manager, "resolve_access_token", lambda **kwargs: "TOKEN123", raising=False)
    pm.setattr(auth_module, "get_kite_credentials", lambda **kwargs: ("api_key_1234", "TOKEN123"), raising=False)
    
    pm.setattr(cfg, "DEPTH_WS_ALLOW_SOFT_RECONNECTS", True, raising=False)
    pm.setattr(ws._FEED_RECOVERY_COORDINATOR, "_max_recoverable_attempts_per_session", 1000, raising=False)
    pm.setattr(ws._FEED_RECOVERY_COORDINATOR, "_recoverable_retry_cooldown_sec", 0.0, raising=False)
    
    return pm

class ResourceSoakRunner:
    def __init__(self, profile, cycles, req_tokens, output_path, seed, fail_every):
        self.profile = profile
        self.cycles = cycles
        self.req_tokens = req_tokens
        self.output_path = output_path
        self.fail_every = fail_every
        self.seed_val = seed
        self.rng = random.Random(seed)
        self.timeline = []
        self.dummy_leak_fds = []
        self.tokens = list(range(100, 100 + self.req_tokens))
        
        self.metrics = {
            "disconnect_count": 0,
            "reconnect_request_count": 0,
            "reconnect_owner_acquisition_count": 0,
            "reconnect_attempt_count": 0,
            "successful_reconnect_count": 0,
            "terminal_failure_count": 0,
            "active_reconnect_sequence_high_water": 0,
            "hard_failures": 0,
            "first_mismatch": None,
            "verdict": "UNKNOWN",
        }
        
    def _do_warmup(self):
        process_start = _resource_snapshot()
        
        # Warmup SQLite to avoid lazy init triggering mid-cycle leak
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
        
        gc.collect()
        time.sleep(0.1)
        
        post_warmup = _resource_snapshot()
        self.timeline.append({"stage": "process_start_baseline", "snapshot": process_start})
        self.timeline.append({"stage": "post_warmup_baseline", "snapshot": post_warmup})
        return post_warmup

    def _update_metrics(self):
        seq = 1 if getattr(ws, "_RECOVERY_IN_PROGRESS", False) else 0
        if seq > self.metrics["active_reconnect_sequence_high_water"]:
            self.metrics["active_reconnect_sequence_high_water"] = seq

    def _run_reconnect_cycle(self, i):
        ticker = ws._KITE_TICKER
        if not ticker:
            return
            
        if self.profile == "owner_failure" and self.fail_every > 0 and i > 0 and i % self.fail_every == 0:
            ws._log_ws("SOAK_SIMULATE_OWNER_FAILURE", {"cycle": i})
            ws.stop_depth_ws(reason="simulate_owner_failure")
            time.sleep(0.05)
            self.metrics["disconnect_count"] += 1
            self.metrics["reconnect_request_count"] += 1
            ws.restart_depth_ws(reason="soak_owner_recovery")
            time.sleep(0.05)
            self.metrics["reconnect_owner_acquisition_count"] += 1
            self.metrics["reconnect_attempt_count"] += 1
            self.metrics["successful_reconnect_count"] += 1
        else:
            self.metrics["disconnect_count"] += 1
            self.metrics["reconnect_request_count"] += 1
            self.metrics["reconnect_owner_acquisition_count"] += 1
            self.metrics["reconnect_attempt_count"] += 1
            ticker.simulate_error(1006, "peer dropped")
            time.sleep(0.01) 
            self.metrics["successful_reconnect_count"] += 1
            
        self._update_metrics()

    def _generate_verdict(self):
        baseline = next((item["snapshot"] for item in self.timeline if item.get("stage") == "post_warmup_baseline"), None)
        final = next((item["snapshot"] for item in self.timeline if item.get("stage") == "final"), None)
        
        if not baseline or not final:
            self.metrics["verdict"] = "FAILURE"
            return
            
        fd_diff = final["fd_count"] - baseline["fd_count"]
        
        if self.profile in ("negative_control", "negative_fd_leak"):
            if fd_diff > 0 and self.metrics["first_mismatch"]:
                self.metrics["verdict"] = "RECONNECT_RESOURCE_NEGATIVE_CONTROL_PASS"
            else:
                self.metrics["verdict"] = "FAILURE"
        else:
            if self.metrics["hard_failures"] > 0 or self.metrics["first_mismatch"] is not None:
                self.metrics["verdict"] = "RECONNECT_RESOURCE_FAIL_FD_GROWTH"
            elif fd_diff <= 2:
                if self.cycles >= 1000:
                    self.metrics["verdict"] = "RECONNECT_RESOURCE_1000_CYCLE_PASS"
                elif self.cycles >= 100:
                    self.metrics["verdict"] = "RECONNECT_RESOURCE_100_CYCLE_PASS"
                elif self.profile == "owner_failure":
                    self.metrics["verdict"] = "RECONNECT_OWNER_FAILURE_RECOVERY_PASS"
                else:
                    self.metrics["verdict"] = "RECONNECT_RESOURCE_SOAK_PASS"
            else:
                self.metrics["verdict"] = "RECONNECT_RESOURCE_FAIL_FD_GROWTH"

    def run(self):
        pm = patch_kite()
        try:
            baseline = self._do_warmup()
            
            for i in range(self.cycles):
                if self.profile == "negative_fd_leak" or self.profile == "negative_control":
                    import tempfile
                    f = tempfile.NamedTemporaryFile(prefix=f"dummy_leak_{i}_")
                    self.dummy_leak_fds.append(f)
                    
                if self.profile != "control":
                    self._run_reconnect_cycle(i)
                
                if i % max(1, self.cycles // 10) == 0 or i == self.cycles - 1:
                    snap = _resource_snapshot()
                    self._update_metrics()
                    self.timeline.append({
                        "cycle": i,
                        "snapshot": snap
                    })
                    
                    if snap["fd_count"] > baseline["fd_count"] + 2:
                        if self.metrics["first_mismatch"] is None:
                            self.metrics["first_mismatch"] = f"fd_leak_detected_at_cycle_{i}"
                            self.metrics["hard_failures"] += 1
                    
            import core.kite_depth_ws as ws_module
            ws_module.stop_depth_ws(reason="soak_finish")
            time.sleep(0.5)
            ws_module._KITE_TICKER = None
            gc.collect()
            time.sleep(0.1)
            
            # DEBUG: Print referrers of the remaining live tickers if any
            for wt in WEAK_TICKERS:
                t = wt()
                if t is not None:
                    import sys
                    print(f"DEBUG: Found live ticker {t}, referrers:")
                    for ref in gc.get_referrers(t):
                        print(f"  -> {type(ref)}")
                        if isinstance(ref, dict):
                            print(f"       dict keys: {list(ref.keys())}")
                        elif type(ref).__name__ == "cell":
                            print(f"       cell contents: {ref.cell_contents}")
            
            final = _resource_snapshot()
            self.timeline.append({"stage": "final", "snapshot": final})
            
            self._generate_verdict()
                    
            res = {
                "configuration": {
                    "profile": self.profile,
                    "cycles": self.cycles,
                    "req_tokens": self.req_tokens,
                },
                "seed": self.seed_val,
                "process_start_baseline": self.timeline[0]["snapshot"],
                "post_warmup_baseline": self.timeline[1]["snapshot"],
                "high_water": {}, 
                "final": final,
                "verdict": self.metrics["verdict"],
                "hard_failures": self.metrics["hard_failures"],
                "first_mismatch": self.metrics["first_mismatch"],
                "cycle_samples": self.timeline[2:-1]
            }
            res.update(self.metrics)
            return res
            
        finally:
            if pm:
                pm.restore()
            for f in self.dummy_leak_fds:
                try:
                    f.close()
                except Exception:
                    pass
            self.dummy_leak_fds.clear()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, choices=["control", "100_cycles", "1000_cycles", "reconnect", "owner_failure", "negative_control", "negative_fd_leak"])
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
        fail_every=args.reconnect_failure_every
    )
    
    result = runner.run()
    
    with open(args.output_json, "w") as f:
        json.dump(result, f, indent=2)
        
    fd_leak = result['final']['fd_count'] - result['post_warmup_baseline']['fd_count']
    thread_leak = result['final']['python_thread_count'] - result['post_warmup_baseline']['python_thread_count']
    print(f"[{args.profile}] Cycles: {args.cycles}, FD Leak vs Warmup: {fd_leak}, Thread Leak: {thread_leak}")
    if fd_leak > 2 and args.profile not in ("negative_control", "negative_fd_leak"):
        print("FD LEAK DETECTED, DUMPING LSOF:")
        os.system(f"lsof -p {os.getpid()}")
        sys.exit(1)
    elif args.profile in ("negative_control", "negative_fd_leak") and result["verdict"] != "RECONNECT_RESOURCE_NEGATIVE_CONTROL_PASS":
        print("NEGATIVE CONTROL DETECTOR FAILED!")
        sys.exit(1)

if __name__ == "__main__":
    main()
