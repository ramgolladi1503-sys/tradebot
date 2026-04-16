from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

from kiteconnect import KiteConnect, KiteTicker

ROOT = Path(__file__).resolve().parents[1]
TOKEN_PATH = ROOT / ".runtime" / "kite_access_token"

API_KEY = os.getenv("KITE_API_KEY", "").strip()
ACCESS_TOKEN = os.getenv("KITE_ACCESS_TOKEN", "").strip()

if not ACCESS_TOKEN and TOKEN_PATH.exists():
    try:
        ACCESS_TOKEN = TOKEN_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        ACCESS_TOKEN = ""

if not API_KEY:
    raise SystemExit("Missing KITE_API_KEY")
if not ACCESS_TOKEN:
    raise SystemExit("Missing KITE_ACCESS_TOKEN")

# One guaranteed underlying token first, no option-chain dependencies.
TEST_TOKENS = [256265]

kws = KiteTicker(API_KEY, ACCESS_TOKEN)

state = {
    "connected": False,
    "ticks_seen": 0,
    "last_tick_ts": None,
    "last_error": None,
}


def shutdown(code: int = 0) -> None:
    print(json.dumps({"event": "FINAL_STATE", **state}, default=str))
    try:
        kws.close()
    except Exception:
        pass
    raise SystemExit(code)


def on_connect(ws, response):
    state["connected"] = True
    print(
        json.dumps(
            {
                "event": "WS_CONNECTED",
                "response": response,
                "token_count": len(TEST_TOKENS),
                "tokens": TEST_TOKENS,
            },
            default=str,
        )
    )
    ws.subscribe(TEST_TOKENS)
    ws.set_mode(ws.MODE_FULL, TEST_TOKENS)
    print(
        json.dumps(
            {
                "event": "WS_SUBSCRIBED",
                "mode": "full",
                "token_count": len(TEST_TOKENS),
            },
            default=str,
        )
    )


def on_ticks(ws, ticks):
    _ = ws
    state["ticks_seen"] += len(ticks or [])
    state["last_tick_ts"] = time.time()
    sample = ticks[0] if ticks else {}
    print(
        json.dumps(
            {
                "event": "WS_TICKS",
                "count": len(ticks or []),
                "sample_keys": sorted(sample.keys()) if isinstance(sample, dict) else [],
                "sample_token": sample.get("instrument_token") if isinstance(sample, dict) else None,
                "sample_ltp": sample.get("last_price") if isinstance(sample, dict) else None,
            },
            default=str,
        )
    )


def on_error(ws, code, reason):
    _ = ws
    state["last_error"] = f"{code}:{reason}"
    print(
        json.dumps(
            {
                "event": "WS_ERROR",
                "code": code,
                "reason": reason,
            },
            default=str,
        )
    )


def on_close(ws, code, reason):
    _ = ws
    print(
        json.dumps(
            {
                "event": "WS_CLOSED",
                "code": code,
                "reason": reason,
            },
            default=str,
        )
    )


def on_reconnect(ws, attempts_count):
    _ = ws
    print(
        json.dumps(
            {
                "event": "WS_RECONNECT",
                "attempts_count": attempts_count,
            },
            default=str,
        )
    )


def on_noreconnect(ws):
    _ = ws
    print(json.dumps({"event": "WS_NO_RECONNECT"}, default=str))
    shutdown(2)


kws.on_connect = on_connect
kws.on_ticks = on_ticks
kws.on_error = on_error
kws.on_close = on_close
kws.on_reconnect = on_reconnect
kws.on_noreconnect = on_noreconnect


def handle_sigint(signum, frame):
    _ = signum
    _ = frame
    shutdown(0)


signal.signal(signal.SIGINT, handle_sigint)

print(
    json.dumps(
        {
            "event": "WS_START",
            "api_key_tail": API_KEY[-4:],
            "token_count": len(TEST_TOKENS),
        },
        default=str,
    )
)

kws.connect(threaded=False)
