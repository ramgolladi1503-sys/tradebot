from __future__ import annotations

import json
import math
import time
from collections import deque
from pathlib import Path

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


class CrossAssetFeatures:
    def __init__(self):
        self.last_fetch_ts = 0.0
        self.history = {}
        self.index_history = {}
        self.cache = {}

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

    def _lead_lag(self, cross_ret, index_ret):
        if not cross_ret or not index_ret:
            return None
        if len(cross_ret) < 3 or len(index_ret) < 3:
            return None
        cross_shift = cross_ret[:-1]
        idx = index_ret[1:]
        return _corr(cross_shift, idx)

    def update(self, index_symbol: str, index_price: float | None):
        self.update_index(index_symbol, index_price)
        now = time.time()
        if now - self.last_fetch_ts < getattr(cfg, "CROSS_ASSET_REFRESH_SEC", 30):
            return self.cache
        self.last_fetch_ts = now

        prices = self._fetch_prices()
        for key, price in prices.items():
            if price is None:
                continue
            h = self._hist(key)
            h.append((now, price))

        features = {}
        index_hist = self._index_hist(index_symbol)
        index_ret_series = self._return_series(index_hist)
        index_ret_1 = self._returns_from_hist(index_hist, 60)
        index_ret_5 = self._returns_from_hist(index_hist, 300)
        index_std = None
        if index_ret_series:
            mean = sum(index_ret_series) / len(index_ret_series)
            var = sum((r - mean) ** 2 for r in index_ret_series) / max(len(index_ret_series), 1)
            index_std = math.sqrt(var)

        align_vals = []
        volspill_vals = []
        lead_vals = []

        risk_sign = getattr(cfg, "CROSS_ASSET_RISK_SIGN", {})

        for key, kite_sym in getattr(cfg, "CROSS_ASSET_SYMBOLS", {}).items():
            hist = self._hist(key)
            ret1 = self._returns_from_hist(hist, 60)
            ret5 = self._returns_from_hist(hist, 300)
            ret_series = self._return_series(hist)
            z = _zscore(ret1, ret_series) if ret1 is not None else None
            corr = _corr(index_ret_series, ret_series) if index_ret_series and ret_series else None
            lead = self._lead_lag(ret_series, index_ret_series) if ret_series and index_ret_series else None
            volspill = None
            if index_std and ret_series:
                mean = sum(ret_series) / len(ret_series)
                var = sum((r - mean) ** 2 for r in ret_series) / max(len(ret_series), 1)
                std = math.sqrt(var)
                if index_std > 0:
                    volspill = std / index_std

            align = None
            if ret1 is not None and index_ret_1 is not None:
                sign = float(risk_sign.get(key, -1))
                same_dir = (ret1 * index_ret_1) > 0
                if sign >= 0:
                    align = 1.0 if not same_dir else -1.0
                else:
                    align = 1.0 if same_dir else -1.0
                if z is not None:
                    align = align * min(1.0, abs(z) / 2.0)

            prefix = f"x_{key.lower()}"
            features[f"{prefix}_ret1"] = ret1
            features[f"{prefix}_ret5"] = ret5
            features[f"{prefix}_z"] = z
            features[f"{prefix}_corr"] = corr
            features[f"{prefix}_lead"] = lead
            features[f"{prefix}_volspill"] = volspill
            features[f"{prefix}_align"] = align

            if align is not None:
                align_vals.append(align)
            if volspill is not None:
                volspill_vals.append(volspill)
            if lead is not None:
                lead_vals.append(lead)

        features["x_regime_align"] = sum(align_vals) / len(align_vals) if align_vals else None
        features["x_vol_spillover"] = sum(volspill_vals) / len(volspill_vals) if volspill_vals else None
        features["x_lead_lag"] = sum(lead_vals) / len(lead_vals) if lead_vals else None
        features["x_index_ret1"] = index_ret_1
        features["x_index_ret5"] = index_ret_5

        self.cache = features
        try:
            Path("logs").mkdir(exist_ok=True)
            Path("logs/cross_asset_features.json").write_text(json.dumps(features, indent=2))
        except Exception:
            pass

        return features
