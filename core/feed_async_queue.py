"""
Async feed ingestion layer to decouple Kite WebSocket from processing.
"""

import queue
import threading
import time

_tick_queue = queue.Queue(maxsize=10000)
_started = False


def enqueue_ticks(ticks):
    try:
        _tick_queue.put_nowait((time.time(), ticks))
    except queue.Full:
        try:
            _tick_queue.get_nowait()
            _tick_queue.put_nowait((time.time(), ticks))
        except Exception:
            pass


def _worker():
    from core.market_data_monitor import record_tick

    while True:
        ts, ticks = _tick_queue.get()
        for t in ticks:
            try:
                record_tick(
                    token=t.get("instrument_token"),
                    symbol=t.get("tradingsymbol"),
                    ts_epoch=ts,
                    ltp=t.get("last_price"),
                )
            except Exception:
                continue


def start_workers(n=2):
    global _started
    if _started:
        return
    _started = True

    for _ in range(n):
        threading.Thread(target=_worker, daemon=True).start()
