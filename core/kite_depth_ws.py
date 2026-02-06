from config import config as cfg
from core.kite_client import kite_client
from core.depth_store import depth_store
from core.tick_store import insert_tick

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

    def on_connect(ws, response):
        ws.subscribe(instrument_tokens)
        ws.set_mode(ws.MODE_FULL, instrument_tokens)

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

    kws.on_connect = on_connect
    kws.on_ticks = on_ticks
    kws.connect(threaded=True)
