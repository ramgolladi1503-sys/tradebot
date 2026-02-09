from config import config as cfg
import time
import threading
import json
from core.kite_client import kite_client
from core.depth_store import depth_store
from core.tick_store import insert_tick
from core.time_utils import is_market_open_ist, now_utc_epoch, now_ist

try:
    from kiteconnect import KiteTicker
except Exception:
    KiteTicker = None

def start_depth_ws(instrument_tokens):
    if not KiteTicker or not cfg.KITE_USE_DEPTH:
        print("Depth websocket not available.")
        return
    if not cfg.KITE_API_KEY or not cfg.KITE_ACCESS_TOKEN:
        print("Missing Kite credentials.")
        return

    kws = KiteTicker(cfg.KITE_API_KEY, cfg.KITE_ACCESS_TOKEN)

    def _log_ws(event: str, extra: dict | None = None):
        try:
            payload = {
                "ts_epoch": now_utc_epoch(),
                "ts_ist": now_ist().isoformat(),
                "event": event,
            }
            if extra:
                payload.update(extra)
            with open("logs/depth_ws_watchdog.log", "a") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception:
            print("[DEPTH_WS_LOG_ERROR] failed to log")

    def on_connect(ws, response):
        try:
            ws.subscribe(instrument_tokens)
            ws.set_mode(ws.MODE_FULL, instrument_tokens)
            _log_ws("FEED_CONNECT", {"tokens": len(instrument_tokens)})
        except Exception as exc:
            _log_ws("FEED_CONNECT_ERROR", {"error": str(exc)})

    def on_reconnect(ws, attempts):
        try:
            ws.subscribe(instrument_tokens)
            ws.set_mode(ws.MODE_FULL, instrument_tokens)
            _log_ws("FEED_RECONNECT", {"attempts": attempts})
        except Exception as exc:
            _log_ws("FEED_RECONNECT_ERROR", {"error": str(exc), "attempts": attempts})

    def on_ticks(ws, ticks):
        for t in ticks:
            token = t.get("instrument_token")
            depth = t.get("depth")
            if token and depth:
                depth_store.update(token, depth)
            if cfg.KITE_STORE_TICKS:
                try:
                    ts = t.get("exchange_timestamp") or t.get("timestamp")
                    insert_tick(
                        ts,
                        token,
                        t.get("last_price"),
                        t.get("volume"),
                        t.get("oi")
                    )
                except Exception:
                    pass

    def _watchdog():
        max_age = float(getattr(cfg, "MAX_DEPTH_AGE_SEC", getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0)))
        cooldown = float(getattr(cfg, "FEED_RECONNECT_COOLDOWN_SEC", 30))
        last_reconnect = 0.0
        while True:
            time.sleep(5)
            if not is_market_open_ist():
                continue
            latest = None
            try:
                # find latest depth ts in store
                for v in depth_store.books.values():
                    ts = v.get("ts_epoch") or v.get("ts")
                    if ts is not None:
                        latest = max(latest or 0, float(ts))
            except Exception:
                latest = None
            if latest is None:
                continue
            age = time.time() - latest
            if age > max_age:
                if time.time() - last_reconnect < cooldown:
                    _log_ws("FEED_STALE_COOLDOWN", {"age_sec": age})
                    continue
                _log_ws("DEPTH_STALE_RECONNECT", {"age_sec": age})
                last_reconnect = time.time()
                try:
                    kws.subscribe(instrument_tokens)
                    kws.set_mode(kws.MODE_FULL, instrument_tokens)
                    _log_ws("FEED_MODE_RESET", {"tokens": len(instrument_tokens)})
                except Exception as exc:
                    _log_ws("FEED_MODE_RESET_ERROR", {"error": str(exc)})

    kws.on_connect = on_connect
    kws.on_reconnect = on_reconnect
    kws.on_ticks = on_ticks
    threading.Thread(target=_watchdog, daemon=True).start()
    kws.connect(threaded=True)
