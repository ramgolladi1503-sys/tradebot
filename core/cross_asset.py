from __future__ import annotations

import json
import math
import time
from collections import deque
from pathlib import Path
from typing import Dict, Optional

from config import config as cfg
from core.kite_client import kite_client


def _log_error(payload: dict) -> None:
    try:
        err_path = Path("logs/cross_asset_errors.jsonl")
        err_path.parent.mkdir(exist_ok=True)
        with err_path.open("a") as f:
            f.write(json.dumps(payload, default=str) + "\n")
    except Exception as exc:
        print(f"[CROSS_ASSET_LOG_ERROR] {exc}")


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

    def _fetch_prices(self, symbols_cfg):
        kite_symbols = [v for v in symbols_cfg.values() if v]
        if not kite_symbols or not kite_client.kite:
            reason = "kite_unavailable" if not kite_client.kite else "no_symbols_configured"
            _log_error({
                "ts": time.time(),
                "error": reason,
                "symbols": list(symbols_cfg.values()),
            })
            return {}, {"error": reason}
        data = {}
        errors = {}
        try:
            quotes = kite_client.ltp(kite_symbols) or {}
            for key, kite_sym in symbols_cfg.items():
                px = quotes.get(kite_sym, {}).get("last_price")
                if px is None:
                    errors[key] = "missing_last_price"
                data[key] = _safe_float(px)
        except Exception as e:
            _log_error({
                "ts": time.time(),
                "error": "fetch_exception",
                "detail": str(e),
                "symbols": list(symbols_cfg.values()),
            })
            return {}, {"error": "fetch_exception", "detail": str(e)}
        if errors:
            _log_error({
                "ts": time.time(),
                "error": "fetch_missing_prices",
                "missing": errors,
            })
        return data, errors

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

        symbols_cfg_all = getattr(cfg, "CROSS_ASSET_SYMBOLS", {}) or {}
        disabled_feeds = getattr(cfg, "CROSS_DISABLED_FEEDS", {}) or {}
        symbols_cfg = {k: v for k, v in symbols_cfg_all.items() if v and k not in disabled_feeds}
        valid_symbols = [v for v in symbols_cfg.values() if v]
        prices, fetch_errors = self._fetch_prices(symbols_cfg)
        stale_sec = float(getattr(cfg, "CROSS_ASSET_STALE_SEC", 120))
        required = set(getattr(cfg, "CROSS_REQUIRED_FEEDS", []) or [])
        optional = set(getattr(cfg, "CROSS_OPTIONAL_FEEDS", []) or [])
        feed_status = getattr(cfg, "CROSS_FEED_STATUS", {}) or {}
        data_quality = {
            "any_stale": False,
            "stale_feeds": [],
            "required_stale": [],
            "optional_stale": [],
            "age_sec": {},
            "last_ts": {},
            "disabled": False,
            "disabled_reason": None,
            "missing": {},
            "errors": fetch_errors or {},
            "disabled_feeds": disabled_feeds,
            "feed_status": feed_status,
        }

        if fetch_errors and fetch_errors.get("error"):
            data_quality["disabled"] = True
            data_quality["disabled_reason"] = "fetch_error"

        if not valid_symbols or not kite_client.kite:
            data_quality["disabled"] = True
            data_quality["disabled_reason"] = "no_symbols_configured" if not valid_symbols else "kite_unavailable"
            data_quality["any_stale"] = False
            if not valid_symbols:
                data_quality["errors"]["error"] = "no_symbols_configured"
            if not kite_client.kite:
                data_quality["errors"]["error"] = "kite_unavailable"
            _log_error({
                "ts": now,
                "error": "cross_asset_disabled",
                "reason": data_quality["disabled_reason"],
                "symbols": list(symbols_cfg_all.values()),
            })

        for key, price in prices.items():
            if price is None:
                data_quality["missing"][key] = "missing_last_price"
                continue
            h = self._hist(key)
            h.append((now, price))
            self.last_price_ts[key] = now

        # staleness check
        for key in symbols_cfg_all.keys():
            status_meta = feed_status.get(key) or {}
            status = status_meta.get("status")
            status_reason = status_meta.get("reason")
            last_ts = self.last_price_ts.get(key)
            age = (now - last_ts) if last_ts is not None else None
            if last_ts is not None:
                try:
                    age = max(0.0, float(age))
                except Exception:
                    age = 0.0
            data_quality["age_sec"][key] = age
            data_quality["last_ts"][key] = last_ts
            if status == "disabled" or key in disabled_feeds:
                reason = status_reason or disabled_feeds.get(key) or "disabled"
                data_quality["missing"][key] = f"disabled:{reason}"
                continue
            if data_quality["disabled"]:
                data_quality["missing"][key] = f"disabled:{data_quality['disabled_reason']}"
                continue
            if last_ts is None or (age is not None and age > stale_sec):
                data_quality["any_stale"] = True
                data_quality["stale_feeds"].append(key)
                data_quality["missing"].setdefault(key, "stale_or_missing")
            if key in (fetch_errors or {}):
                data_quality["missing"][key] = fetch_errors.get(key)
        # If a global fetch error occurred, mark all feeds missing explicitly
        try:
            if fetch_errors and fetch_errors.get("error"):
                for key in symbols_cfg.keys():
                    if key not in data_quality["missing"]:
                        data_quality["missing"][key] = fetch_errors.get("error")
        except Exception as e:
            _log_error({"ts": now, "error": "missing_map_error", "detail": str(e)})

        # classify required/optional staleness
        missing_keys = set(data_quality.get("missing", {}).keys())
        stale_keys = set(data_quality.get("stale_feeds", []) or [])
        if data_quality["disabled"]:
            # Fail closed for required feeds when cross-asset is unavailable.
            if data_quality.get("disabled_reason") in ("kite_unavailable", "fetch_error", "no_symbols_configured"):
                data_quality["required_stale"] = sorted(required)
                data_quality["optional_stale"] = sorted(optional)
                for key in symbols_cfg_all.keys():
                    data_quality["missing"].setdefault(key, data_quality.get("disabled_reason"))
            else:
                data_quality["required_stale"] = []
                data_quality["optional_stale"] = []
        else:
            data_quality["required_stale"] = sorted((missing_keys | stale_keys) & required)
            data_quality["optional_stale"] = sorted((missing_keys | stale_keys) & optional)

        # log fetch errors explicitly
        try:
            if fetch_errors or data_quality.get("missing"):
                _log_error({
                    "ts": now,
                    "error": "fetch_or_missing",
                    "errors": fetch_errors,
                    "missing": data_quality.get("missing", {}),
                })
        except Exception as e:
            _log_error({"ts": now, "error": "error_log_write_failed", "detail": str(e)})

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
                if key in disabled_feeds:
                    continue
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
            "prices": prices,
            "feed_status": {
                "required": list(getattr(cfg, "CROSS_REQUIRED_FEEDS", []) or []),
                "optional": list(getattr(cfg, "CROSS_OPTIONAL_FEEDS", []) or []),
                "disabled": getattr(cfg, "CROSS_DISABLED_FEEDS", {}) or {},
            },
        }
        self.cache = payload
        try:
            Path("data").mkdir(exist_ok=True)
            Path("data/cross_asset.json").write_text(json.dumps(payload, indent=2))
            Path("logs").mkdir(exist_ok=True)
            Path("logs/cross_asset_features.json").write_text(json.dumps(features, indent=2))
        except Exception as e:
            _log_error({"ts": now, "error": "write_failed", "detail": str(e)})
        return payload
