from __future__ import annotations

import json
import math
import time
from collections import deque
from pathlib import Path
from typing import Dict, Optional

from config import config as cfg
from core.kite_client import kite_client


def _safe_float(v):
    try:
        return float(v)
    except Exception:
        return None


def _corr(a, b):
    if not a or not b:
        return None
    n = min(len(a), len(b))
    if n < 3:
        return None
    a = a[-n:]
    b = b[-n:]
    ma = sum(a) / n
    mb = sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = math.sqrt(sum((a[i] - ma) ** 2 for i in range(n)))
    db = math.sqrt(sum((b[i] - mb) ** 2 for i in range(n)))
    if da == 0 or db == 0:
        return None
    return num / (da * db)


def _zscore(x, series):
    if not series:
        return None
    m = sum(series) / len(series)
    v = sum((s - m) ** 2 for s in series) / max(len(series), 1)
    s = math.sqrt(v)
    if s == 0:
        return 0.0
    return (x - m) / s


class CrossAsset:
    def __init__(self):
        self.last_fetch_ts = 0.0
        self.history = {}
        self.index_history = {}
        self.cache = {"features": {}, "data_quality": {"any_stale": True}}
        self.last_price_ts = {}

    def _hist(self, key):
        if key not in self.history:
            self.history[key] = deque(maxlen=getattr(cfg, "CROSS_ASSET_MAXLEN", 600))
        return self.history[key]

    def _index_hist(self, key):
        if key not in self.index_history:
            self.index_history[key] = deque(maxlen=getattr(cfg, "CROSS_ASSET_MAXLEN", 600))
        return self.index_history[key]

    def update_index(self, symbol: str, price: float | None):
        if price is None:
            return
        h = self._index_hist(symbol)
        h.append((time.time(), float(price)))

    def _fetch_prices(self):
        symbols = getattr(cfg, "CROSS_ASSET_SYMBOLS", {})
        kite_symbols = [v for v in symbols.values() if v]
        if not kite_symbols or not kite_client.kite:
            return {}
        data = {}
        try:
            quotes = kite_client.ltp(kite_symbols) or {}
            for key, kite_sym in symbols.items():
                px = quotes.get(kite_sym, {}).get("last_price")
                data[key] = _safe_float(px)
        except Exception:
            return {}
        return data

    def _returns_from_hist(self, hist, window_sec: int):
        if not hist or len(hist) < 2:
            return None
        now = hist[-1][0]
        latest = hist[-1][1]
        prev = None
        for ts, price in reversed(hist):
            if now - ts >= window_sec:
                prev = price
                break
        if prev is None or prev == 0:
            return None
        return (latest - prev) / prev

    def _return_series(self, hist):
        if not hist or len(hist) < 3:
            return []
        series = []
        for i in range(1, len(hist)):
            p0 = hist[i - 1][1]
            p1 = hist[i][1]
            if p0:
                series.append((p1 - p0) / p0)
        return series

    def _neutral_features(self):
        return {
            "x_regime_align": 0.0,
            "x_vol_spillover": 0.0,
            "x_lead_lag": 0.0,
            "x_index_ret1": 0.0,
            "x_index_ret5": 0.0,
        }

    def update(self, index_symbol: str, index_price: float | None):
        self.update_index(index_symbol, index_price)
        now = time.time()
        refresh = getattr(cfg, "CROSS_ASSET_REFRESH_SEC", 30)
        if now - self.last_fetch_ts < refresh:
            return self.cache
        self.last_fetch_ts = now

        prices = self._fetch_prices()
        stale_sec = float(getattr(cfg, "CROSS_ASSET_STALE_SEC", 120))
        data_quality = {"any_stale": False, "stale_feeds": [], "age_sec": {}, "last_ts": {}}

        for key, price in prices.items():
            if price is None:
                continue
            h = self._hist(key)
            h.append((now, price))
            self.last_price_ts[key] = now

        # staleness check
        for key in getattr(cfg, "CROSS_ASSET_SYMBOLS", {}).keys():
            last_ts = self.last_price_ts.get(key)
            age = (now - last_ts) if last_ts else None
            data_quality["age_sec"][key] = age
            data_quality["last_ts"][key] = last_ts
            if last_ts is None or (age is not None and age > stale_sec):
                data_quality["any_stale"] = True
                data_quality["stale_feeds"].append(key)

        if data_quality["any_stale"]:
            features = self._neutral_features()
        else:
            features = {}
            # index returns
            idx_hist_n = self._index_hist("NIFTY")
            idx_hist_s = self._index_hist("SENSEX")
            idx_ret_series = self._return_series(self._index_hist(index_symbol))
            idx_ret1 = self._returns_from_hist(self._index_hist(index_symbol), 60)
            idx_ret5 = self._returns_from_hist(self._index_hist(index_symbol), 300)
            idx_ret15 = self._returns_from_hist(self._index_hist(index_symbol), 900)
            idx_std = None
            if idx_ret_series:
                mean = sum(idx_ret_series) / len(idx_ret_series)
                var = sum((r - mean) ** 2 for r in idx_ret_series) / max(len(idx_ret_series), 1)
                idx_std = math.sqrt(var)

            volspill_vals = []
            for key in getattr(cfg, "CROSS_ASSET_SYMBOLS", {}).keys():
                hist = self._hist(key)
                ret1 = self._returns_from_hist(hist, 60)
                ret5 = self._returns_from_hist(hist, 300)
                ret15 = self._returns_from_hist(hist, 900)
                ret_series = self._return_series(hist)
                z = _zscore(ret1, ret_series) if ret1 is not None else None
                corr_n = _corr(self._return_series(idx_hist_n), ret_series) if idx_hist_n and ret_series else None
                corr_s = _corr(self._return_series(idx_hist_s), ret_series) if idx_hist_s and ret_series else None
                volspill = None
                if idx_std and ret_series:
                    mean = sum(ret_series) / len(ret_series)
                    var = sum((r - mean) ** 2 for r in ret_series) / max(len(ret_series), 1)
                    std = math.sqrt(var)
                    if idx_std > 0:
                        volspill = std / idx_std
                if volspill is not None:
                    volspill_vals.append(volspill)

                prefix = f"x_{key.lower()}"
                features[f"{prefix}_ret1"] = ret1
                features[f"{prefix}_ret5"] = ret5
                features[f"{prefix}_ret15"] = ret15
                features[f"{prefix}_z"] = z
                features[f"{prefix}_corr_nifty"] = corr_n
                features[f"{prefix}_corr_sensex"] = corr_s
                features[f"{prefix}_volspill"] = volspill

            features["x_vol_spillover"] = sum(volspill_vals) / len(volspill_vals) if volspill_vals else 0.0
            features["x_index_ret1"] = idx_ret1
            features["x_index_ret5"] = idx_ret5
            features["x_index_ret15"] = idx_ret15
            features["x_regime_align"] = 0.0
            features["x_lead_lag"] = 0.0

        payload = {
            "timestamp": now,
            "features": features,
            "data_quality": data_quality,
        }
        self.cache = payload
        try:
            Path("data").mkdir(exist_ok=True)
            Path("data/cross_asset.json").write_text(json.dumps(payload, indent=2))
            Path("logs").mkdir(exist_ok=True)
            Path("logs/cross_asset_features.json").write_text(json.dumps(features, indent=2))
        except Exception:
            pass
        return payload

