from collections import defaultdict, deque
from datetime import datetime
from config import config as cfg


class OhlcBuffer:
    def __init__(self):
        self._bars = defaultdict(lambda: deque(maxlen=getattr(cfg, "OHLC_BUFFER_MAX_BARS", 500)))

    def update_tick(self, symbol, price, volume=0, ts=None):
        if price is None:
            return
        try:
            ts = ts or datetime.now()
            if isinstance(ts, (int, float)):
                ts = datetime.fromtimestamp(ts)
            bucket = ts.replace(second=0, microsecond=0)
            bars = self._bars[symbol]
            if bars and bars[-1]["ts"] == bucket:
                bar = bars[-1]
                bar["high"] = max(bar["high"], price)
                bar["low"] = min(bar["low"], price)
                bar["close"] = price
                bar["volume"] += volume or 0
            else:
                bars.append({
                    "ts": bucket,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": volume or 0,
                })
        except Exception:
            return

    def get_bars(self, symbol):
        return list(self._bars.get(symbol, []))

    def last_ts(self, symbol):
        bars = self._bars.get(symbol)
        if not bars:
            return None
        return bars[-1]["ts"]

    def seed_bars(self, symbol, bars):
        try:
            q = self._bars[symbol]
            for b in bars:
                ts = b.get("date") or b.get("ts")
                if not ts:
                    continue
                if not hasattr(ts, "replace"):
                    from datetime import datetime
                    try:
                        ts = datetime.fromisoformat(str(ts))
                    except Exception:
                        continue
                q.append({
                    "ts": ts.replace(second=0, microsecond=0),
                    "open": b.get("open"),
                    "high": b.get("high"),
                    "low": b.get("low"),
                    "close": b.get("close"),
                    "volume": b.get("volume", 0) or 0,
                })
        except Exception:
            return


ohlc_buffer = OhlcBuffer()
