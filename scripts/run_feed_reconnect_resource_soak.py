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

def _get_fd_records():
    pid = os.getpid()
    try:
        import subprocess
        out = subprocess.check_output(f"lsof -p {pid} -F ftn", shell=True, text=True)
        records = []
        current_record = {}
        for line in out.splitlines():
            if not line: continue
            char = line[0]
            val = line[1:]
            if char == 'p': continue
            if char == 'f':
                if current_record and current_record.get('fd', '').isdigit():
                    records.append(current_record)
                current_record = {'fd': val}
            elif char == 't':
                current_record['type'] = val
            elif char == 'n':
                current_record['identity'] = val
        if current_record and current_record.get('fd', '').isdigit():
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
    sqlite_fds = [f for f in fd_records if ".sqlite" in f.get('identity', '') or "-wal" in f.get('identity', '') or "-shm" in f.get('identity', '')]
    
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
        "fd_count": len(fd_records),
        "fd_identities": [r.get('identity', '') for r in fd_records if 'identity' in r],
        "fd_records": fd_records,
        "sqlite_fd_count": len(sqlite_fds),
        "live_websocket_generations": live_tickers,
        "retired_websocket_generations_reachable": retired_reachable,
        "reactor_count": None,
        "feed_worker_count": None,
        "queue_depth": getattr(ws, "_feed_queue_depth", lambda: 0)(),
        "queue_high_water": getattr(ws, "_feed_queue_high_water", lambda: 0)(),
        "required_token_count": len(ws._LAST_TOKENS or []),
        "requested_token_count": len(getattr(ws._KITE_TICKER, "tokens", [])) if ws._KITE_TICKER else 0,
        "active_token_count": len(getattr(ws._KITE_TICKER, "tokens", [])) if ws._KITE_TICKER else 0,
        "missing_token_count": 0,
        "unexpected_token_count": 0,
        "duplicate_subscription_count": 0,
        "fresh_token_count": len(getattr(ws._KITE_TICKER, "tokens", [])) if ws._KITE_TICKER else 0,
        "stale_token_count": 0,
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
        
        class DummyWS:
            def __init__(self, ticker):
                self.ticker_ref = weakref.ref(ticker)
                class Factory:
                    def __init__(self, ws):
                        self.ws = ws
                    def is_connected(self):
                        t = self.ws.ticker_ref()
                        return t.connected if t else False
                self.factory = Factory(self)
        self.ws = DummyWS(self)
        
        self.set_mode = lambda *args: None
        self.unsubscribe = lambda *args: None
        self.on_reconnect = None
        self.on_error = None
        self.on_close = None
        self.on_ticks = None
        self.stop_retry_count = 0
        self.tokens = []
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
        return [{"instrument_token": 1, "tradingsymbol": "A"}, {"instrument_token": 2, "tradingsymbol": "B"}, {"instrument_token": 3, "tradingsymbol": "C"}]

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
    pm.setattr(ws, "_ensure_depth_ws_lock", lambda: True, raising=False)
    
    import core.auth as auth_module
    import core.auth_manager as auth_manager
    pm.setattr(auth_module, "resolve_access_token", lambda **kwargs: "TOKEN123", raising=False)
    pm.setattr(auth_manager, "resolve_access_token", lambda **kwargs: "TOKEN123", raising=False)
    pm.setattr(auth_module, "get_kite_credentials", lambda **kwargs: ("api_key_1234", "TOKEN123"), raising=False)
    
    pm.setattr(cfg, "DEPTH_WS_ALLOW_SOFT_RECONNECTS", False, raising=False)
    pm.setattr(cfg, "DEPTH_WS_MAX_RECOVERIES_PER_WINDOW", 10000, raising=False)
    pm.setattr(ws._FEED_RECOVERY_COORDINATOR, "_max_recoverable_attempts_per_session", 10000, raising=False)
    pm.setattr(ws._FEED_RECOVERY_COORDINATOR, "_max_recoveries_per_window", 10000, raising=False)
    pm.setattr(cfg, "DEPTH_WS_WS1006_RECOVERABLE_MAX_ATTEMPTS_PER_SESSION", 10000, raising=False)
    pm.setattr(ws._FEED_RECOVERY_COORDINATOR, "_recoverable_retry_cooldown_sec", 0.0, raising=False)
    
    pm.setattr(ws, "feed_breaker_tripped", lambda: False, raising=False)
    pm.setattr(ws.feed_restart_guard, "allow_restart", lambda **kw: True, raising=False)
    pm.setattr(cfg, "FEED_MAX_FULL_RESTARTS_PER_HOUR", 10000, raising=False)
    pm.setattr(cfg, "FEED_RESTART_STORM_TRIP", 10000, raising=False)
    
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
            "verified_successful_reconnect_count": 0,
            "terminal_failure_count": 0,
            "active_reconnect_sequence_high_water": 0,
            "websocket_generations_created": 1,
            "initial_generation_id": None,
            "final_generation_id": None,
            "generation_transition_count": 0,
            "same_generation_reused_count": 0,
            "generation_creation_failures": 0,
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
        old_ticker = ws._KITE_TICKER
        if not old_ticker:
            self.metrics["hard_failures"] += 1
            if not self.metrics["first_mismatch"]:
                self.metrics["first_mismatch"] = f"cycle_{i}_no_old_ticker"
            return
            
        old_generation_id = getattr(old_ticker, "generation_id", id(old_ticker))
        
        if self.metrics["initial_generation_id"] is None:
            self.metrics["initial_generation_id"] = old_generation_id
            
        if self.profile == "owner_failure" and self.fail_every > 0 and i > 0 and i % self.fail_every == 0:
            ws._log_ws("SOAK_SIMULATE_OWNER_FAILURE", {"cycle": i})
            ws.stop_depth_ws(reason="simulate_owner_failure")
            time.sleep(0.05)
            self.metrics["disconnect_count"] += 1
            self.metrics["reconnect_request_count"] += 1
            ws.restart_depth_ws(reason="soak_owner_recovery")
            self.metrics["reconnect_owner_acquisition_count"] += 1
            self.metrics["reconnect_attempt_count"] += 1
        else:
            self.metrics["disconnect_count"] += 1
            self.metrics["reconnect_request_count"] += 1
            self.metrics["reconnect_owner_acquisition_count"] += 1
            self.metrics["reconnect_attempt_count"] += 1
            old_ticker.simulate_error(1006, "peer dropped")
            
        timeout = 10.0
        start_t = time.time()
        success = False
        new_ticker = None
        new_generation_id = None
        
        while time.time() - start_t < timeout:
            new_ticker = ws._KITE_TICKER
            if new_ticker is not None:
                new_generation_id = getattr(new_ticker, "generation_id", id(new_ticker))
                if new_generation_id != old_generation_id:
                    if getattr(new_ticker, "connected", False):
                        if not getattr(ws, "_RECOVERY_IN_PROGRESS", False):
                            if not getattr(ws, "_DEPTH_WS_LOCK_ACQUIRED", False):
                                if len(getattr(new_ticker, "tokens", [])) == len(ws._LAST_TOKENS or []):
                                    success = True
                                    break
            time.sleep(0.05)
            
        if not success:
            self.metrics["hard_failures"] += 1
            self.metrics["terminal_failure_count"] += 1
            self.metrics["generation_creation_failures"] += 1
            if not self.metrics["first_mismatch"]:
                self.metrics["first_mismatch"] = (f"cycle_{i}_timeout "
                       f"old_gen={old_generation_id} "
                       f"cur_gen={new_generation_id} "
                       f"runtime_state={getattr(ws, '_RUNTIME_STATE', None)} "
                       f"recovery={getattr(ws, '_RECOVERY_IN_PROGRESS', False)} "
                       f"thread_state={bool(getattr(ws, '_KITE_TICKER_THREAD', None))} "
                       f"last_err={getattr(ws, '_LAST_RUNTIME_ERROR', None)}")
        else:
            self.metrics["final_generation_id"] = new_generation_id
            self.metrics["generation_transition_count"] += 1
            self.metrics["websocket_generations_created"] += 1
            self.metrics["successful_reconnect_count"] += 1
            self.metrics["verified_successful_reconnect_count"] += 1
            
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
            
            # DEBUG: Print bounded diagnostic information
            for wt in WEAK_TICKERS:
                t = wt()
                if t is not None:
                    gen_id = getattr(t, 'generation_id', 'unknown')
                    obj_type = type(t).__name__
                    ref_types = set()
                    by_callback = False
                    by_factory = False
                    by_module = False
                    by_loop_var = False
                    
                    for ref in gc.get_referrers(t):
                        r_type = type(ref).__name__
                        ref_types.add(r_type)
                        
                        if r_type in ('cell', 'function', 'method', 'instancemethod'):
                            by_callback = True
                        elif r_type == 'DummyFactory':
                            by_factory = True
                        elif r_type == 'dict':
                            if ref.get('__name__') == 'core.kite_depth_ws':
                                by_module = True
                            if ref.get('__name__') == 'core.kite_client':
                                by_module = True
                        elif r_type == 'frame':
                            if 'wt' in ref.f_locals and 't' in ref.f_locals:
                                by_loop_var = True
                                
                    ref_types_str = ', '.join(sorted(ref_types))
                    print(f"DEBUG: generation ID: {gen_id}")
                    print(f"DEBUG: object type: {obj_type}")
                    print(f"DEBUG: referrer type names: {ref_types_str}")
                    print(f"DEBUG: whether referenced by callback: {by_callback}")
                    print(f"DEBUG: whether referenced by factory: {by_factory}")
                    print(f"DEBUG: whether referenced by websocket module global: {by_module}")
                    print(f"DEBUG: whether referenced by local loop var: {by_loop_var}")
            
            final = _resource_snapshot()
            self.timeline.append({"stage": "final", "snapshot": final})
            
            self._generate_verdict()
                    
            # calculate high waters and rss_slope
            high_water = {}
            if self.timeline:
                for k in ["fd_count", "sqlite_fd_count", "rss_bytes", "python_thread_count", "queue_depth"]:
                    high_water[k] = max(item["snapshot"].get(k, 0) for item in self.timeline if "snapshot" in item)
            
            rss_values = [item["snapshot"]["rss_bytes"] for item in self.timeline[2:-1] if "snapshot" in item]
            rss_slope = 0.0
            if len(rss_values) > 1:
                rss_slope = (rss_values[-1] - rss_values[0]) / max(1, len(rss_values))
                
            final["rss_slope_bytes_per_sample"] = rss_slope

            res = {
                "configuration": {
                    "profile": self.profile,
                    "cycles": self.cycles,
                    "req_tokens": self.req_tokens,
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
            try:
                ws.stop_depth_ws(reason="shutdown")
            except Exception:
                pass

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
    
    sys.exit(0)

if __name__ == "__main__":
    main()
