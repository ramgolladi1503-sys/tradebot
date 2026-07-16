from collections import defaultdict, deque
from datetime import datetime, timedelta
from config import config as cfg
from core.time_utils import IST_TZ, now_ist


class OhlcBuffer:
    def __init__(self):
        self._bars = defaultdict(lambda: deque(maxlen=getattr(cfg, "OHLC_BUFFER_MAX_BARS", 500)))

    def update_tick(self, symbol, price, volume=None, ts=None):
        if price is None:
            return {
                "accepted": False,
                "status": "INVALID_TICK",
                "symbol": symbol,
                "incoming_bucket": None,
                "current_tail_bucket": None,
            }
        try:
            ts = ts or now_ist()
            if isinstance(ts, (int, float)):
                ts = datetime.fromtimestamp(ts, tz=IST_TZ)
            if isinstance(ts, datetime) and ts.tzinfo is None:
                ts = ts.replace(tzinfo=IST_TZ)
            bucket = ts.replace(second=0, microsecond=0)
            bars = self._bars[symbol]
            tail_bucket = bars[-1]["ts"] if bars else None

            if tail_bucket is not None and bucket < tail_bucket:
                return {
                    "accepted": False,
                    "status": "REJECTED_LATE_BUCKET",
                    "symbol": symbol,
                    "incoming_bucket": bucket,
                    "current_tail_bucket": tail_bucket,
                }

            if tail_bucket is not None and bucket == tail_bucket:
                bar = bars[-1]
                bar["high"] = max(bar["high"], price)
                bar["low"] = min(bar["low"], price)
                bar["close"] = price
                if volume is not None:
                    bar["volume"] += volume or 0
                return {
                    "accepted": True,
                    "status": "UPDATED_CURRENT_BAR",
                    "symbol": symbol,
                    "incoming_bucket": bucket,
                    "current_tail_bucket": tail_bucket,
                }
            else:
                bars.append({
                    "ts": bucket,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": volume if volume is not None else 0,
                })
                return {
                    "accepted": True,
                    "status": "NEW_BAR",
                    "symbol": symbol,
                    "incoming_bucket": bucket,
                    "current_tail_bucket": tail_bucket,
                }
        except Exception:
            return {
                "accepted": False,
                "status": "INVALID_TICK",
                "symbol": symbol,
                "incoming_bucket": None,
                "current_tail_bucket": None,
            }

    def get_bars(self, symbol):
        return list(self._bars.get(symbol, []))

    def get_completed_bars(self, symbol, *, as_of, interval_seconds=60):
        if not isinstance(interval_seconds, (int, float)) or interval_seconds <= 0:
            return []
        if not isinstance(as_of, datetime):
            return []

        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=IST_TZ)
        else:
            as_of = as_of.astimezone(IST_TZ)

        completed_bars = []
        interval_td = timedelta(seconds=interval_seconds)
        last_ts = None
        for bar in self._bars.get(symbol, []):
            ts = bar.get("ts")
            if not isinstance(ts, datetime):
                return []
            if last_ts is not None and ts <= last_ts:
                return []
            if ts + interval_td <= as_of:
                completed_bars.append(dict(bar))
            last_ts = ts
        return completed_bars

    def last_ts(self, symbol):
        bars = self._bars.get(symbol)
        if not bars:
            return None
        return bars[-1]["ts"]

    def seed_bars(self, symbol, bars):
        try:
            normalized = []
            for b in bars:
                ts = b.get("date") or b.get("ts")
                if not ts:
                    continue
                if not isinstance(ts, datetime):
                    try:
                        ts = datetime.fromisoformat(str(ts))
                    except Exception:
                        continue
                if isinstance(ts, datetime) and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=IST_TZ)
                elif isinstance(ts, datetime) and ts.tzinfo is not None:
                    ts = ts.astimezone(IST_TZ)

                bucket = ts.replace(second=0, microsecond=0)
                normalized.append({
                    "ts": bucket,
                    "open": b.get("open"),
                    "high": b.get("high"),
                    "low": b.get("low"),
                    "close": b.get("close"),
                    "volume": b.get("volume", 0) or 0,
                })

            if not normalized:
                return

            normalized.sort(key=lambda x: x["ts"])

            deduped = []
            for b in normalized:
                if deduped and deduped[-1]["ts"] == b["ts"]:
                    deduped[-1] = b
                else:
                    deduped.append(b)

            q = self._bars[symbol]
            current_bars = list(q)

            merged = {}
            for b in current_bars + deduped:
                merged[b["ts"]] = b

            sorted_keys = sorted(merged.keys())
            final_bars = [merged[k] for k in sorted_keys]

            q.clear()
            for b in final_bars:
                q.append(b)
        except Exception:
            return


ohlc_buffer = OhlcBuffer()
