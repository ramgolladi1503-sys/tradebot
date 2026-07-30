from collections import defaultdict, deque
from datetime import datetime, timedelta
from config import config as cfg
from core.time_utils import IST_TZ, now_ist


class OhlcBuffer:
    def __init__(self):
        self._bars = defaultdict(lambda: deque(maxlen=getattr(cfg, "OHLC_BUFFER_MAX_BARS", 500)))

    def update_tick(self, symbol, price, volume=None, ts=None, provenance=None):
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
                _merge_live_bar_provenance(bar, provenance, ts)
                return {
                    "accepted": True,
                    "status": "UPDATED_CURRENT_BAR",
                    "symbol": symbol,
                    "incoming_bucket": bucket,
                    "current_tail_bucket": tail_bucket,
                }
            else:
                row = {
                    "ts": bucket,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": volume if volume is not None else 0,
                }
                _merge_live_bar_provenance(row, provenance, ts)
                bars.append(row)
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
        try:
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
                if ts.tzinfo is None:
                    return []

                ts = ts.astimezone(IST_TZ)

                if last_ts is not None and ts <= last_ts:
                    return []
                if ts + interval_td <= as_of:
                    completed_bar = dict(bar)
                    completed_bar["ts"] = ts
                    completed_bars.append(completed_bar)
                last_ts = ts
            return completed_bars
        except Exception:
            return []
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
                    return {"accepted": False, "status": "INVALID_SEED_BATCH", "symbol": symbol, "seeded_bars": 0, "overlap_preserved": 0}
                if not isinstance(ts, datetime):
                    try:
                        ts = datetime.fromisoformat(str(ts))
                    except Exception:
                        return {"accepted": False, "status": "INVALID_SEED_BATCH", "symbol": symbol, "seeded_bars": 0, "overlap_preserved": 0}
                if isinstance(ts, datetime) and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=IST_TZ)
                elif isinstance(ts, datetime) and ts.tzinfo is not None:
                    ts = ts.astimezone(IST_TZ)

                bucket = ts.replace(second=0, microsecond=0)

                # validate required OHLC values
                try:
                    open_val = float(b.get("open"))
                    high_val = float(b.get("high"))
                    low_val = float(b.get("low"))
                    close_val = float(b.get("close"))
                    vol_val = float(b.get("volume", 0) or 0)
                except (TypeError, ValueError):
                    return {"accepted": False, "status": "INVALID_SEED_BATCH", "symbol": symbol, "seeded_bars": 0, "overlap_preserved": 0}

                normalized.append({
                    "ts": bucket,
                    "open": open_val,
                    "high": high_val,
                    "low": low_val,
                    "close": close_val,
                    "volume": vol_val,
                    "bar_provenance": {
                        "source_type": "historical_seed",
                        "live_feed_session_id": None,
                        "first_live_tick_epoch": None,
                        "last_live_tick_epoch": None,
                        "historical_seed": True,
                        "replay_fixture": False,
                        "non_live_fallback": False,
                        "recovered_synthetic": False,
                    },
                })

            if not normalized:
                return {"accepted": True, "status": "NO_CHANGE", "symbol": symbol, "seeded_bars": 0, "overlap_preserved": 0}

            normalized.sort(key=lambda x: x["ts"])

            deduped = {}
            for b in normalized:
                deduped[b["ts"]] = b

            q = self._bars[symbol]
            current_bars = list(q)
            existing_timestamps = {b["ts"] for b in current_bars}

            merged = {b["ts"]: dict(b) for b in current_bars}

            seeded_count = 0
            overlap_count = 0

            for ts, b in deduped.items():
                if ts in existing_timestamps:
                    overlap_count += 1
                else:
                    merged[ts] = b
                    seeded_count += 1

            if seeded_count == 0:
                return {"accepted": True, "status": "NO_CHANGE", "symbol": symbol, "seeded_bars": 0, "overlap_preserved": overlap_count}

            sorted_keys = sorted(merged.keys())
            final_bars = [merged[k] for k in sorted_keys]

            q.clear()
            for b in final_bars:
                q.append(b)

            return {"accepted": True, "status": "SEEDED", "symbol": symbol, "seeded_bars": seeded_count, "overlap_preserved": overlap_count}
        except Exception:
            return {"accepted": False, "status": "INVALID_SEED_BATCH", "symbol": symbol, "seeded_bars": 0, "overlap_preserved": 0}

ohlc_buffer = OhlcBuffer()


def _merge_live_bar_provenance(bar, provenance, tick_ts):
    payload = dict(provenance or {})
    if not payload:
        payload = {
            "source_type": "unknown",
            "live_feed_session_id": None,
            "historical_seed": False,
            "replay_fixture": False,
            "non_live_fallback": False,
            "recovered_synthetic": False,
        }
    try:
        tick_epoch = float(tick_ts.timestamp()) if hasattr(tick_ts, "timestamp") else float(tick_ts)
    except Exception:
        tick_epoch = None
    existing = dict(bar.get("bar_provenance") or {})
    first_epoch = existing.get("first_live_tick_epoch")
    last_epoch = existing.get("last_live_tick_epoch")
    source_type = str(payload.get("source_type") or existing.get("source_type") or "unknown")
    if tick_epoch is not None and source_type.lower() in {"live_websocket", "tick_store_live"}:
        first_epoch = tick_epoch if first_epoch is None else min(float(first_epoch), tick_epoch)
        last_epoch = tick_epoch if last_epoch is None else max(float(last_epoch), tick_epoch)
    bar["bar_provenance"] = {
        "source_type": source_type,
        "live_feed_session_id": payload.get("live_feed_session_id") or existing.get("live_feed_session_id"),
        "first_live_tick_epoch": first_epoch,
        "last_live_tick_epoch": last_epoch,
        "historical_seed": bool(payload.get("historical_seed", existing.get("historical_seed", False))),
        "replay_fixture": bool(payload.get("replay_fixture", existing.get("replay_fixture", False))),
        "non_live_fallback": bool(payload.get("non_live_fallback", existing.get("non_live_fallback", False))),
        "recovered_synthetic": bool(payload.get("recovered_synthetic", existing.get("recovered_synthetic", False))),
    }
