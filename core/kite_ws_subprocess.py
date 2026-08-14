from __future__ import annotations

import logging
import multiprocessing
import os
import signal
import time
from typing import Any

from core.kite_depth_ws import start_depth_ws, stop_depth_ws
from core.feed.artifact_loader import load_current_feed_runtime

logger = logging.getLogger(__name__)

_WS_PROCESS: multiprocessing.Process | None = None
_LAST_TOKENS: list[int] = []
_PROFILE_VERIFIED: bool = False
_LAST_RESTART_TIME = 0.0

def _run_in_child(tokens: list[int], profile_verified: bool) -> None:
    # Reset signal handlers in child to default so we can be terminated
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    
    try:
        logger.info(f"Subprocess [PID {os.getpid()}] starting feed.")
        start_depth_ws(tokens, profile_verified=profile_verified)
    except Exception as e:
        logger.error(f"Feed subprocess died with exception: {e}", exc_info=True)
    finally:
        logger.info(f"Subprocess [PID {os.getpid()}] feed stopped.")

def start_depth_ws_subprocess(tokens: list[int], profile_verified: bool = True) -> None:
    global _WS_PROCESS, _LAST_TOKENS, _PROFILE_VERIFIED, _LAST_RESTART_TIME
    
    _LAST_TOKENS = list(tokens)
    _PROFILE_VERIFIED = profile_verified
    
    if _WS_PROCESS is not None and _WS_PROCESS.is_alive():
        logger.warning("Subprocess is already alive. Stopping it first.")
        stop_depth_ws_subprocess()

    logger.info("Spawning new Kite depth WS subprocess...")
    _WS_PROCESS = multiprocessing.Process(
        target=_run_in_child,
        args=(tokens, profile_verified),
        name="kite_depth_ws_subprocess",
    )
    _WS_PROCESS.daemon = True # We want it to be killed if main exits unexpectedly
    _WS_PROCESS.start()
    _LAST_RESTART_TIME = time.time()
    logger.info(f"Subprocess spawned with PID {_WS_PROCESS.pid}")

def stop_depth_ws_subprocess() -> None:
    global _WS_PROCESS
    if _WS_PROCESS is not None:
        if _WS_PROCESS.is_alive():
            logger.info(f"Terminating Kite depth WS subprocess PID {_WS_PROCESS.pid}...")
            _WS_PROCESS.terminate()
            _WS_PROCESS.join(timeout=5.0)
            if _WS_PROCESS.is_alive():
                logger.warning(f"Subprocess PID {_WS_PROCESS.pid} did not terminate, killing it.")
                _WS_PROCESS.kill()
                _WS_PROCESS.join()
        _WS_PROCESS = None
        logger.info("Kite depth WS subprocess stopped.")

import atexit
atexit.register(stop_depth_ws_subprocess)

def monitor_depth_ws_subprocess() -> None:
    global _WS_PROCESS
    
    # Don't do anything if we never started
    if not _LAST_TOKENS:
        return
        
    now = time.time()
    needs_restart = False
    reason = ""

    if _WS_PROCESS is None or not _WS_PROCESS.is_alive():
        needs_restart = True
        reason = "process_died"
    else:
        # Check health via JSON file
        try:
            loaded = load_current_feed_runtime()
            if not loaded.get("valid"):
                needs_restart = True
                reason = f"invalid_runtime_artifact:{loaded.get('reason_code') or 'INVALID_ARTIFACT'}"
                snapshot = {}
            else:
                snapshot = dict(loaded.get("payload") or {})
            runtime_state = str(snapshot.get("runtime_state") or "").strip().upper()
            if not needs_restart and runtime_state in {"FEED_LIFECYCLE_FATAL", "RESTART_REQUIRED"}:
                needs_restart = True
                reason = f"fatal_state:{runtime_state}"
            elif snapshot.get("process_restart_required"):
                needs_restart = True
                reason = "process_restart_required_flag"
        except Exception as e:
            logger.error(f"Failed to read feed runtime snapshot: {e}")
            
    if needs_restart:
        # Prevent rapid restart loops
        if now - _LAST_RESTART_TIME < 15.0:
            logger.warning(f"Subprocess needs restart ({reason}), but skipping due to cooldown limit.")
            return

        logger.warning(f"Subprocess monitoring detected failure ({reason}). Restarting...")
        stop_depth_ws_subprocess()
        start_depth_ws_subprocess(_LAST_TOKENS, _PROFILE_VERIFIED)
