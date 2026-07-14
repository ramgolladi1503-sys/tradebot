#!/usr/bin/env python3
import argparse
import json
import logging
import os
import random
import sys
import threading
import time
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
    return {
        "rss_bytes": rss_bytes,
        "rss_mib": rss_bytes / (1024.0 * 1024.0),
        "rss_source": source,
        "thread_count": len(getattr(threading, "_active", {})),
        "fd_count": process_fd_count(),
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
    # This acts as a mock injector if monkeypatch is not provided (when running standalone)
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
    
    # Patch external calls in kite_depth_ws
    pm.setattr(ws.kite_client, "ensure", lambda: _DummyRestClient(), raising=False)
    pm.setattr(ws.kite_client, "kite", _DummyRestClient(), raising=False)
    pm.setattr(ws.kite_client, "_active_api_key", "api_key_1234", raising=False)
    pm.setattr(ws.kite_client, "_active_access_token", "TOKEN123", raising=False)
    pm.setattr(ws, "KiteTicker", _DummyTicker, raising=False)
    pm.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True}, raising=False)
    pm.setattr(ws, "is_market_open_ist", lambda: True, raising=False)
    
    # Patch auth dependencies
    import core.auth as auth_module
    import core.auth_manager as auth_manager
    pm.setattr(auth_module, "resolve_access_token", lambda **kwargs: "TOKEN123", raising=False)
    pm.setattr(auth_manager, "resolve_access_token", lambda **kwargs: "TOKEN123", raising=False)
    pm.setattr(auth_module, "get_kite_credentials", lambda **kwargs: ("api_key_1234", "TOKEN123"), raising=False)
    
    # Override fast reconnect to avoid waiting 5-10s per test loop
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
        self.rng = random.Random(seed)
        self.timeline = []
        self.dummy_leak_fds = []
        
        self.tokens = list(range(100, 100 + self.req_tokens))
        
    def _run_control(self):
        # Profile A: start, let it sit, then stop
        ws.start_depth_ws(self.tokens, skip_lock=True, skip_guard=True)
        time.sleep(0.1)
        baseline = _resource_snapshot()
        self.timeline.append({"stage": "baseline", "snapshot": baseline})
        
        for i in range(self.cycles):
            self.timeline.append({
                "cycle": i,
                "snapshot": _resource_snapshot()
            })
            time.sleep(0.01)
            
        ws.stop_depth_ws(reason="soak_control_finish")
        time.sleep(2.0)
        final = _resource_snapshot()
        self.timeline.append({"stage": "final", "snapshot": final})
        
        return {
            "profile": self.profile,
            "cycles": self.cycles,
            "baseline": baseline,
            "final": final,
            "timeline": self.timeline,
            "fd_leaked": final["fd_count"] - baseline["fd_count"],
            "thread_leaked": final["thread_count"] - baseline["thread_count"],
        }

    def _run_reconnect_cycle(self, i):
        ticker = ws._KITE_TICKER
        if not ticker:
            return
            
        # Determine failure profile
        if self.profile == "owner_failure" and self.fail_every > 0 and i > 0 and i % self.fail_every == 0:
            # owner failure: lock can't be acquired or internal exception
            ws._log_ws("SOAK_SIMULATE_OWNER_FAILURE", {"cycle": i})
            # simulate a hard stop due to lock failure
            ws.stop_depth_ws(reason="simulate_owner_failure")
            time.sleep(0.05)
            # manually trigger a restart
            ws.restart_depth_ws(reason="soak_owner_recovery")
        else:
            # standard 1006 drop
            ticker.simulate_error(1006, "peer dropped")
            time.sleep(0.01) # give background threads a tiny bit of time to schedule restarts

    def _run_soak(self):
        ws.start_depth_ws(self.tokens, skip_lock=True, skip_guard=True)
        
        # Warmup baseline
        time.sleep(0.1)
        baseline = _resource_snapshot()
        self.timeline.append({"stage": "baseline", "snapshot": baseline})
        
        for i in range(self.cycles):
            if self.profile == "negative_control":
                # Intentionally leak an FD
                f = open("/dev/null", "r")
                self.dummy_leak_fds.append(f)
                
            self._run_reconnect_cycle(i)
            
            # Record occasionally to avoid giant JSONs for 1000+ cycles
            if i % max(1, self.cycles // 10) == 0 or i == self.cycles - 1:
                self.timeline.append({
                    "cycle": i,
                    "snapshot": _resource_snapshot()
                })
                
        ws.stop_depth_ws(reason="soak_finish")
        time.sleep(2.0) # let threads die off and FDs close
        final = _resource_snapshot()
        self.timeline.append({"stage": "final", "snapshot": final})
        
        return {
            "profile": self.profile,
            "cycles": self.cycles,
            "baseline": baseline,
            "final": final,
            "timeline": self.timeline,
            "fd_leaked": final["fd_count"] - baseline["fd_count"],
            "thread_leaked": final["thread_count"] - baseline["thread_count"],
        }
        
    def run(self):
        pm = patch_kite()
        try:
            if self.profile == "control":
                return self._run_control()
            else:
                return self._run_soak()
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
    parser.add_argument("--profile", required=True, choices=["control", "100_cycles", "1000_cycles", "owner_failure", "negative_control"])
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
        
    print(f"[{args.profile}] Cycles: {args.cycles}, FD Leak: {result['fd_leaked']}, Thread Leak: {result['thread_leaked']}")
    if result['fd_leaked'] > 0 and args.profile != "negative_control":
        print("FD LEAK DETECTED, DUMPING LSOF:")
        os.system(f"lsof -p {os.getpid()}")
        sys.exit(1)

if __name__ == "__main__":
    main()
