from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from research.autonomous_structural_edge_exhaustion_v1 import common as A

AERON_REPO = "https://github.com/aeron7/nifty-banknifty-intraday-data.git"
YEARS = set(range(2012, 2024))
SYMBOLS = ("NIFTY", "BANKNIFTY")
HORIZONS = (3, 6, 12)
GLOBAL_Q = 0.01
MAX_FINAL = 5

PRICE_FAMILIES = (
    "EMA_CROSS",
    "SMA_CROSS",
    "PRICE_EMA_TREND",
    "MACD_CROSS",
    "RSI_REVERSION",
    "RSI_50_MOMENTUM",
    "ADX_DI_TREND",
    "BOLLINGER_REENTRY",
    "BOLLINGER_BREAKOUT",
    "SUPERTREND_FLIP",
    "DONCHIAN_BREAKOUT",
    "STOCHASTIC_REVERSION",
    "CCI_REVERSION",
    "WILLIAMS_R_REVERSION",
    "ROC_CONTINUATION",
    "ZSCORE_REVERSION",
    "ZSCORE_CONTINUATION",
    "KELTNER_REENTRY",
    "KELTNER_BREAKOUT",
    "PSAR_FLIP",
    "ICHIMOKU_TREND",
    "OPENING_RANGE_BREAKOUT",
    "PREVIOUS_DAY_BREAKOUT",
    "ROLLING_RANGE_BREAKOUT",
    "ENGULFING_REVERSAL",
    "OUTSIDE_KEY_REVERSAL",
    "REGRESSION_REVERSION",
    "REGRESSION_SLOPE",
)

REVERSAL_WORDS = ("reversal", "revert", "reversion", "fade", "overbought", "oversold", "mean reversion")
BREAKOUT_WORDS = ("breakout", "breakdown", "continuation", "trend following", "trend-following", "momentum")


@dataclass(frozen=True)
class MechanismSpec:
    family: str
    params: tuple[tuple[str, float], ...]
    derivation: str

    @property
    def signature(self) -> str:
        args = ",".join(f"{k}={v:g}" for k, v in self.params)
        return f"{self.family}::{args}" if args else self.family

    def param_dict(self) -> dict[str, float]:
        return dict(self.params)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    completed = subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True)
    return completed.stdout


def clone_aeron(work_root: Path) -> tuple[Path, list[str]]:
    repo = work_root / "aeron7"
    if repo.exists():
        subprocess.run(["rm", "-rf", str(repo)], check=True)
    _run(["git", "clone", "--filter=blob:none", "--no-checkout", "--depth", "1", AERON_REPO, str(repo)])
    paths = _run(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=repo).splitlines()
    selected: list[str] = []
    for path in paths:
        parts = path.split("/")
        if not parts or not parts[0].isdigit() or int(parts[0]) not in YEARS:
            continue
        if Path(path).name.upper() not in {"NIFTY.TXT", "BANKNIFTY.TXT"}:
            continue
        selected.append(path)
    if not selected:
        raise RuntimeError("No Aeron7 NIFTY/BANKNIFTY files found")
    _run(["git", "config", "core.sparseCheckout", "true"], cwd=repo)
    sparse = repo / ".git" / "info" / "sparse-checkout"
    sparse.parent.mkdir(parents=True, exist_ok=True)
    sparse.write_text("".join(f"/{p}\n" for p in selected), encoding="utf-8")
    _run(["git", "read-tree", "-mu", "HEAD"], cwd=repo)
    return repo, selected


def _normalize_symbol(value: str) -> str | None:
    token = re.sub(r"[^A-Z0-9]", "", value.upper())
    if token in {"NIFTY", "NIFTY50", "NIFTYI"}:
        return "NIFTY"
    if token in {"BANKNIFTY", "NIFTYBANK", "BANKNIFTYI"}:
        return "BANKNIFTY"
    return None


def load_aeron_raw(repo: Path, selected: Sequence[str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[tuple[Any, ...]] = []
    failed: list[dict[str, str]] = []
    parsed_files = 0
    for rel in selected:
        path = repo / rel
        try:
            accepted = 0
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                parts = [x.strip() for x in line.split(",")]
                if len(parts) < 7:
                    continue
                symbol = _normalize_symbol(parts[0])
                if symbol is None or not re.fullmatch(r"\d{8}", parts[1]) or not re.fullmatch(r"\d{1,2}:\d{2}", parts[2]):
                    continue
                try:
                    o, h, l, c = (float(x) for x in parts[3:7])
                except ValueError:
                    continue
                rows.append((symbol, parts[1], parts[2], o, h, l, c, rel))
                accepted += 1
            parsed_files += int(accepted > 0)
        except Exception as exc:
            failed.append({"path": rel, "error": repr(exc)})
    raw = pd.DataFrame(rows, columns=["symbol", "date_text", "time_text", "open", "high", "low", "close", "source_file"])
    if raw.empty:
        raise RuntimeError("Aeron7 files produced no usable rows")
    raw["dt"] = pd.to_datetime(raw["date_text"] + " " + raw["time_text"], format="%Y%m%d %H:%M", errors="coerce")
    raw = raw.dropna(subset=["dt"])
    raw = raw[raw["dt"].dt.year.isin(YEARS)]
    raw = raw[(raw["dt"].dt.time >= pd.Timestamp("09:15").time()) & (raw["dt"].dt.time < pd.Timestamp("15:30").time())]
    valid = (
        (raw[["open", "high", "low", "close"]] > 0).all(axis=1)
        & (raw["low"] <= raw[["open", "close"]].min(axis=1))
        & (raw["high"] >= raw[["open", "close"]].max(axis=1))
        & (raw["low"] <= raw["high"])
    )
    invalid = int((~valid).sum())
    raw = raw[valid].copy()
    before = len(raw)
    raw = raw.sort_values(["symbol", "dt", "source_file"]).drop_duplicates(["symbol", "dt"], keep="last")
    return raw, {
        "repository": AERON_REPO,
        "selected_paths": len(selected),
        "parsed_files": parsed_files,
        "failed_files": failed,
        "raw_rows": int(len(raw)),
        "duplicates_removed": int(before - len(raw)),
        "invalid_ohlc_removed": invalid,
        "min_timestamp": str(raw["dt"].min()),
        "max_timestamp": str(raw["dt"].max()),
    }


def resample_5m(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    raw = raw.copy()
    raw["session_date"] = raw["dt"].dt.strftime("%Y-%m-%d")
    frames: list[pd.DataFrame] = []
    rejected = 0
    for (symbol, session), group in raw.groupby(["symbol", "session_date"], sort=True):
        g = group.sort_values("dt").set_index("dt")
        bars = g[["open", "high", "low", "close"]].resample(
            "5min", origin="start_day", offset="9h15min", label="left", closed="left"
        ).agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        bars = bars[(bars.index.time >= pd.Timestamp("09:15").time()) & (bars.index.time < pd.Timestamp("15:30").time())]
        if len(bars) < 70:
            rejected += 1
            continue
        deltas = pd.Series(bars.index).diff().dt.total_seconds().div(60).dropna()
        if deltas.empty or not (4.5 <= float(deltas.median()) <= 5.5):
            rejected += 1
            continue
        bars = bars.reset_index().rename(columns={"dt": "timestamp"})
        bars["symbol"] = symbol
        bars["session_date"] = session
        frames.append(bars)
    if not frames:
        raise RuntimeError("No complete 5-minute sessions")
    data = pd.concat(frames, ignore_index=True).sort_values(["symbol", "timestamp"], kind="mergesort").reset_index(drop=True)
    return data, {
        "accepted_symbol_sessions": int(data.groupby(["symbol", "session_date"]).ngroups),
        "accepted_dates": int(data["session_date"].nunique()),
        "rejected_symbol_sessions": rejected,
        "rows": int(len(data)),
        "min_session": str(data["session_date"].min()),
        "max_session": str(data["session_date"].max()),
    }


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0.0)
    down = -d.clip(upper=0.0)
    avg_up = up.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    avg_down = down.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = avg_up / avg_down.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift(1)
    return pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev).abs(),
        (df["low"] - prev).abs(),
    ], axis=1).max(axis=1)


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return _true_range(df).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def _adx(df: pd.DataFrame, n: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    atr = _atr(df, n)
    plus = 100.0 * plus_dm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr.replace(0.0, np.nan)
    minus = 100.0 * minus_dm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr.replace(0.0, np.nan)
    dx = 100.0 * (plus - minus).abs() / (plus + minus).replace(0.0, np.nan)
    adx = dx.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return adx, plus, minus


def _cross_up(a: pd.Series, b: pd.Series | float) -> pd.Series:
    b_series = pd.Series(float(b), index=a.index) if np.isscalar(b) else b
    return (a > b_series) & (a.shift(1) <= b_series.shift(1))


def _cross_down(a: pd.Series, b: pd.Series | float) -> pd.Series:
    b_series = pd.Series(float(b), index=a.index) if np.isscalar(b) else b
    return (a < b_series) & (a.shift(1) >= b_series.shift(1))


def _supertrend(df: pd.DataFrame, atr_n: int = 10, factor: float = 3.0) -> pd.Series:
    atr = _atr(df, atr_n)
    hl2 = (df["high"] + df["low"]) / 2.0
    upper_basic = hl2 + factor * atr
    lower_basic = hl2 - factor * atr
    upper = upper_basic.copy()
    lower = lower_basic.copy()
    direction = pd.Series(index=df.index, dtype=float)
    for i in range(len(df)):
        if i == 0 or not math.isfinite(float(atr.iloc[i])):
            direction.iloc[i] = np.nan
            continue
        pi = i - 1
        if math.isfinite(float(upper.iloc[pi])):
            upper.iloc[i] = upper_basic.iloc[i] if (upper_basic.iloc[i] < upper.iloc[pi] or df["close"].iloc[pi] > upper.iloc[pi]) else upper.iloc[pi]
        if math.isfinite(float(lower.iloc[pi])):
            lower.iloc[i] = lower_basic.iloc[i] if (lower_basic.iloc[i] > lower.iloc[pi] or df["close"].iloc[pi] < lower.iloc[pi]) else lower.iloc[pi]
        prev_dir = direction.iloc[pi]
        if not math.isfinite(float(prev_dir)):
            direction.iloc[i] = 1.0 if df["close"].iloc[i] >= hl2.iloc[i] else -1.0
        elif prev_dir > 0:
            direction.iloc[i] = -1.0 if df["close"].iloc[i] < lower.iloc[i] else 1.0
        else:
            direction.iloc[i] = 1.0 if df["close"].iloc[i] > upper.iloc[i] else -1.0
    return direction


def _psar(df: pd.DataFrame, step: float = 0.02, maximum: float = 0.2) -> pd.Series:
    n = len(df)
    out = np.full(n, np.nan)
    if n < 3:
        return pd.Series(out, index=df.index)
    bull = df["close"].iloc[1] >= df["close"].iloc[0]
    af = step
    ep = df["high"].iloc[0] if bull else df["low"].iloc[0]
    sar = df["low"].iloc[0] if bull else df["high"].iloc[0]
    direction = np.full(n, np.nan)
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if bull:
            sar = min(sar, df["low"].iloc[i - 1], df["low"].iloc[i - 2] if i > 1 else df["low"].iloc[i - 1])
            if df["low"].iloc[i] < sar:
                bull = False
                sar = ep
                ep = df["low"].iloc[i]
                af = step
            elif df["high"].iloc[i] > ep:
                ep = df["high"].iloc[i]
                af = min(maximum, af + step)
        else:
            sar = max(sar, df["high"].iloc[i - 1], df["high"].iloc[i - 2] if i > 1 else df["high"].iloc[i - 1])
            if df["high"].iloc[i] > sar:
                bull = True
                sar = ep
                ep = df["high"].iloc[i]
                af = step
            elif df["low"].iloc[i] < ep:
                ep = df["low"].iloc[i]
                af = min(maximum, af + step)
        out[i] = sar
        direction[i] = 1.0 if bull else -1.0
    return pd.Series(direction, index=df.index)


def _rolling_regression(close: pd.Series, n: int = 50) -> tuple[pd.Series, pd.Series]:
    values = close.to_numpy(float)
    slope = np.full(len(values), np.nan)
    resid_z = np.full(len(values), np.nan)
    x = np.arange(n, dtype=float)
    x_center = x - x.mean()
    denom = float(np.sum(x_center * x_center))
    for i in range(n - 1, len(values)):
        y = values[i - n + 1:i + 1]
        if not np.isfinite(y).all():
            continue
        y_mean = float(np.mean(y))
        b = float(np.sum(x_center * (y - y_mean)) / denom)
        a = y_mean - b * float(x.mean())
        fit = a + b * x
        resid = y - fit
        sd = float(np.std(resid, ddof=0))
        slope[i] = b / max(abs(y_mean), 1e-12)
        resid_z[i] = float(resid[-1] / sd) if sd > 1e-12 else 0.0
    return pd.Series(slope, index=close.index), pd.Series(resid_z, index=close.index)


def build_features(data: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for symbol, group in data.groupby("symbol", sort=True):
        g = group.sort_values("timestamp", kind="mergesort").reset_index(drop=True).copy()
        c = g["close"]
        for n in (9, 20, 26, 50, 100, 200):
            g[f"ema{n}"] = _ema(c, n)
        for n in (20, 50, 200):
            g[f"sma{n}"] = _sma(c, n)
        g["rsi14"] = _rsi(c, 14)
        ema12 = _ema(c, 12)
        ema26 = _ema(c, 26)
        g["macd"] = ema12 - ema26
        g["macd_signal"] = _ema(g["macd"], 9)
        g["atr14"] = _atr(g, 14)
        adx, plus, minus = _adx(g, 14)
        g["adx14"], g["plus_di14"], g["minus_di14"] = adx, plus, minus
        mid = _sma(c, 20)
        sd = c.rolling(20, min_periods=20).std(ddof=0)
        g["bb_mid"], g["bb_upper"], g["bb_lower"] = mid, mid + 2.0 * sd, mid - 2.0 * sd
        prior_high20 = g["high"].shift(1).rolling(20, min_periods=20).max()
        prior_low20 = g["low"].shift(1).rolling(20, min_periods=20).min()
        g["donchian_high20"], g["donchian_low20"] = prior_high20, prior_low20
        low14 = g["low"].rolling(14, min_periods=14).min()
        high14 = g["high"].rolling(14, min_periods=14).max()
        k = 100.0 * (c - low14) / (high14 - low14).replace(0.0, np.nan)
        g["stoch_k"] = k.rolling(3, min_periods=3).mean()
        g["stoch_d"] = g["stoch_k"].rolling(3, min_periods=3).mean()
        tp = (g["high"] + g["low"] + c) / 3.0
        tp_ma = tp.rolling(20, min_periods=20).mean()
        md = tp.rolling(20, min_periods=20).apply(lambda x: float(np.mean(np.abs(x - np.mean(x)))), raw=True)
        g["cci20"] = (tp - tp_ma) / (0.015 * md.replace(0.0, np.nan))
        g["williams14"] = -100.0 * (high14 - c) / (high14 - low14).replace(0.0, np.nan)
        g["roc12"] = c.pct_change(12)
        prior_mean = c.shift(1).rolling(20, min_periods=20).mean()
        prior_sd = c.shift(1).rolling(20, min_periods=20).std(ddof=0)
        g["z20"] = (c - prior_mean) / prior_sd.replace(0.0, np.nan)
        g["kelt_mid"] = _ema(c, 20)
        g["kelt_upper"] = g["kelt_mid"] + 2.0 * g["atr14"]
        g["kelt_lower"] = g["kelt_mid"] - 2.0 * g["atr14"]
        g["supertrend_dir"] = _supertrend(g, 10, 3.0)
        g["psar_dir"] = _psar(g)
        conv = (g["high"].rolling(9, min_periods=9).max() + g["low"].rolling(9, min_periods=9).min()) / 2.0
        base = (g["high"].rolling(26, min_periods=26).max() + g["low"].rolling(26, min_periods=26).min()) / 2.0
        span_a = ((conv + base) / 2.0).shift(26)
        span_b = ((g["high"].rolling(52, min_periods=52).max() + g["low"].rolling(52, min_periods=52).min()) / 2.0).shift(26)
        g["ichi_top"] = pd.concat([span_a, span_b], axis=1).max(axis=1)
        g["ichi_bottom"] = pd.concat([span_a, span_b], axis=1).min(axis=1)
        slope, rz = _rolling_regression(c, 50)
        g["reg_slope50"], g["reg_resid_z50"] = slope, rz
        g["index_ret3"] = np.log(c).diff().rolling(3, min_periods=3).sum()
        g["index_vol6"] = np.log(c).diff().rolling(6, min_periods=4).std(ddof=0)
        frames.append(g)
    out = pd.concat(frames, ignore_index=True)

    # Session-derived features must reset by day.
    parts: list[pd.DataFrame] = []
    prior_session_levels: dict[str, tuple[float, float]] = {}
    for symbol, sg in out.groupby("symbol", sort=True):
        prior_high = np.nan
        prior_low = np.nan
        for session, group in sg.groupby("session_date", sort=True):
            x = group.sort_values("timestamp", kind="mergesort").copy()
            x["bar_in_session"] = np.arange(len(x))
            x["session_progress"] = x["bar_in_session"] / max(1, len(x) - 1)
            opening = x.iloc[:3]
            orb_h = float(opening["high"].max()) if len(opening) == 3 else np.nan
            orb_l = float(opening["low"].min()) if len(opening) == 3 else np.nan
            x["orb_high15"] = orb_h
            x["orb_low15"] = orb_l
            x["prior_day_high"] = prior_high
            x["prior_day_low"] = prior_low
            prior_high = float(x["high"].max())
            prior_low = float(x["low"].min())
            parts.append(x)
    return pd.concat(parts, ignore_index=True).sort_values(["symbol", "timestamp"], kind="mergesort").reset_index(drop=True)


def _extract_lengths(text: str, label: str, defaults: tuple[int, int]) -> tuple[int, int]:
    pattern = re.compile(rf"{label}\s*\(?\s*(\d{{1,3}})(?:\s*[/,\-&]\s*(\d{{1,3}}))?", re.I)
    vals: list[int] = []
    for m in pattern.finditer(text):
        vals.append(int(m.group(1)))
        if m.group(2):
            vals.append(int(m.group(2)))
    vals = [v for v in vals if 2 <= v <= 300]
    uniq = []
    for v in vals:
        if v not in uniq:
            uniq.append(v)
    if len(uniq) >= 2:
        a, b = sorted(uniq[:2])
        return a, b
    return defaults


def map_record(record: Mapping[str, Any]) -> tuple[MechanismSpec | None, str]:
    text = f"{record.get('title','')} {record.get('description','')}".lower()
    primitives = set(map(str, record.get("primitives", [])))
    incompat = set(map(str, record.get("incompatibilities", [])))
    if record.get("fetch_status") != "OK":
        return None, "FETCH_FAILED"
    if incompat & {"OPTIONS_OR_GREEKS", "FUNDAMENTALS", "TRUE_INTRABAR_OR_LOWER_TF", "EXTERNAL_OR_MULTI_SYMBOL", "NON_STANDARD_CHART"}:
        return None, "INDEPENDENT_DATA_INCOMPATIBLE"
    if primitives & {"VOLUME", "VWAP", "VWMA"}:
        return None, "INDEPENDENT_DATA_MISSING_VOLUME"
    reversal = any(k in text for k in REVERSAL_WORDS)
    breakout = any(k in text for k in BREAKOUT_WORDS)

    if "SUPERTREND" in primitives:
        return MechanismSpec("SUPERTREND_FLIP", (), "recognized SuperTrend mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "BOLLINGER" in primitives:
        family = "BOLLINGER_REENTRY" if reversal or "crosses back" in text else "BOLLINGER_BREAKOUT"
        return MechanismSpec(family, (("length", 20), ("sigma", 2.0)), "recognized Bollinger mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "DONCHIAN" in primitives:
        return MechanismSpec("DONCHIAN_BREAKOUT", (("length", 20),), "recognized Donchian mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "KELTNER" in primitives:
        family = "KELTNER_REENTRY" if reversal else "KELTNER_BREAKOUT"
        return MechanismSpec(family, (("length", 20), ("atr_mult", 2.0)), "recognized Keltner mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "ICHIMOKU" in primitives:
        return MechanismSpec("ICHIMOKU_TREND", (), "recognized Ichimoku cloud mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "PSAR" in primitives:
        return MechanismSpec("PSAR_FLIP", (), "recognized Parabolic SAR mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "MACD" in primitives:
        return MechanismSpec("MACD_CROSS", (("fast", 12), ("slow", 26), ("signal", 9)), "recognized MACD crossover mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "ADX" in primitives or "DMI" in primitives:
        return MechanismSpec("ADX_DI_TREND", (("length", 14), ("threshold", 20)), "recognized ADX/DI trend mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "STOCHASTIC" in primitives:
        return MechanismSpec("STOCHASTIC_REVERSION", (("length", 14),), "recognized stochastic reversal mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "CCI" in primitives:
        return MechanismSpec("CCI_REVERSION", (("length", 20),), "recognized CCI reversal mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "WILLIAMS_R" in primitives:
        return MechanismSpec("WILLIAMS_R_REVERSION", (("length", 14),), "recognized Williams %R reversal mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "ZSCORE" in primitives:
        family = "ZSCORE_REVERSION" if reversal or not breakout else "ZSCORE_CONTINUATION"
        return MechanismSpec(family, (("length", 20), ("z", 2.0)), "recognized Z-score mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "REGRESSION" in primitives:
        family = "REGRESSION_REVERSION" if reversal or "channel" in text else "REGRESSION_SLOPE"
        return MechanismSpec(family, (("length", 50),), "recognized regression mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "OPENING_RANGE" in primitives:
        return MechanismSpec("OPENING_RANGE_BREAKOUT", (("minutes", 15),), "recognized opening-range mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "PREV_DAY_LEVEL" in primitives:
        return MechanismSpec("PREVIOUS_DAY_BREAKOUT", (), "recognized previous-day level mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "CANDLE_PATTERN" in primitives:
        family = "ENGULFING_REVERSAL" if "engulf" in text else "OUTSIDE_KEY_REVERSAL"
        return MechanismSpec(family, (), "recognized closed-bar reversal pattern"), "TESTABLE_CANONICAL_MECHANISM"
    if "EMA" in primitives:
        fast, slow = _extract_lengths(text, "ema", (20, 50))
        if "cross" in text or "crossover" in text or len(re.findall(r"\bema\b", text)) >= 2:
            return MechanismSpec("EMA_CROSS", (("fast", fast), ("slow", slow)), "recognized EMA crossover mechanism"), "TESTABLE_CANONICAL_MECHANISM"
        return MechanismSpec("PRICE_EMA_TREND", (("length", slow),), "recognized price/EMA trend mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "SMA" in primitives:
        fast, slow = _extract_lengths(text, "sma", (20, 50))
        return MechanismSpec("SMA_CROSS", (("fast", fast), ("slow", slow)), "recognized SMA crossover mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "RSI" in primitives:
        family = "RSI_REVERSION" if reversal or "30" in text or "70" in text else "RSI_50_MOMENTUM"
        return MechanismSpec(family, (("length", 14),), "recognized RSI mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "ROC" in primitives or "MOMENTUM" in primitives:
        return MechanismSpec("ROC_CONTINUATION", (("length", 12),), "recognized momentum/ROC mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "BREAKOUT" in primitives:
        return MechanismSpec("ROLLING_RANGE_BREAKOUT", (("length", 20),), "generic closed-bar breakout mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "MEAN_REVERSION" in primitives:
        return MechanismSpec("ZSCORE_REVERSION", (("length", 20), ("z", 2.0)), "generic standardized mean-reversion mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "TREND" in primitives:
        return MechanismSpec("PRICE_EMA_TREND", (("length", 50),), "generic trend mechanism"), "TESTABLE_CANONICAL_MECHANISM"
    if "PIVOT" in primitives:
        return MechanismSpec("OUTSIDE_KEY_REVERSAL", (), "conservative closed-bar pivot/reversal proxy"), "TESTABLE_CANONICAL_MECHANISM"
    return None, "OPAQUE_OR_NON_SIGNAL"


def _signal_for_family(g: pd.DataFrame, spec: MechanismSpec) -> pd.Series:
    p = spec.param_dict()
    fam = spec.family
    idx = g.index
    sig = pd.Series(0, index=idx, dtype=int)
    close = g["close"]
    if fam == "EMA_CROSS":
        fast = int(p.get("fast", 20)); slow = int(p.get("slow", 50))
        ef, es = _ema(close, fast), _ema(close, slow)
        sig[_cross_up(ef, es)] = 1; sig[_cross_down(ef, es)] = -1
    elif fam == "SMA_CROSS":
        fast = int(p.get("fast", 20)); slow = int(p.get("slow", 50))
        sf, ss = _sma(close, fast), _sma(close, slow)
        sig[_cross_up(sf, ss)] = 1; sig[_cross_down(sf, ss)] = -1
    elif fam == "PRICE_EMA_TREND":
        e = _ema(close, int(p.get("length", 50)))
        sig[_cross_up(close, e)] = 1; sig[_cross_down(close, e)] = -1
    elif fam == "MACD_CROSS":
        sig[_cross_up(g["macd"], g["macd_signal"])] = 1; sig[_cross_down(g["macd"], g["macd_signal"])] = -1
    elif fam == "RSI_REVERSION":
        r = g["rsi14"]
        sig[_cross_up(r, 30.0)] = 1; sig[_cross_down(r, 70.0)] = -1
    elif fam == "RSI_50_MOMENTUM":
        r = g["rsi14"]
        sig[_cross_up(r, 50.0)] = 1; sig[_cross_down(r, 50.0)] = -1
    elif fam == "ADX_DI_TREND":
        adx, plus, minus = g["adx14"], g["plus_di14"], g["minus_di14"]
        sig[(adx >= 20) & _cross_up(plus, minus)] = 1
        sig[(adx >= 20) & _cross_down(plus, minus)] = -1
    elif fam == "BOLLINGER_REENTRY":
        sig[(close > g["bb_lower"]) & (close.shift(1) <= g["bb_lower"].shift(1))] = 1
        sig[(close < g["bb_upper"]) & (close.shift(1) >= g["bb_upper"].shift(1))] = -1
    elif fam == "BOLLINGER_BREAKOUT":
        sig[_cross_up(close, g["bb_upper"])] = 1; sig[_cross_down(close, g["bb_lower"])] = -1
    elif fam == "SUPERTREND_FLIP":
        d = g["supertrend_dir"]
        sig[(d > 0) & (d.shift(1) < 0)] = 1; sig[(d < 0) & (d.shift(1) > 0)] = -1
    elif fam == "DONCHIAN_BREAKOUT":
        sig[close > g["donchian_high20"]] = 1; sig[close < g["donchian_low20"]] = -1
    elif fam == "STOCHASTIC_REVERSION":
        k, d = g["stoch_k"], g["stoch_d"]
        sig[(k.shift(1) < 20) & _cross_up(k, d)] = 1
        sig[(k.shift(1) > 80) & _cross_down(k, d)] = -1
    elif fam == "CCI_REVERSION":
        cci = g["cci20"]
        sig[_cross_up(cci, -100.0)] = 1; sig[_cross_down(cci, 100.0)] = -1
    elif fam == "WILLIAMS_R_REVERSION":
        w = g["williams14"]
        sig[_cross_up(w, -80.0)] = 1; sig[_cross_down(w, -20.0)] = -1
    elif fam == "ROC_CONTINUATION":
        r = g["roc12"]
        sig[_cross_up(r, 0.0)] = 1; sig[_cross_down(r, 0.0)] = -1
    elif fam == "ZSCORE_REVERSION":
        z = g["z20"]
        sig[_cross_up(z, -2.0)] = 1; sig[_cross_down(z, 2.0)] = -1
    elif fam == "ZSCORE_CONTINUATION":
        z = g["z20"]
        sig[_cross_up(z, 2.0)] = 1; sig[_cross_down(z, -2.0)] = -1
    elif fam == "KELTNER_REENTRY":
        sig[(close > g["kelt_lower"]) & (close.shift(1) <= g["kelt_lower"].shift(1))] = 1
        sig[(close < g["kelt_upper"]) & (close.shift(1) >= g["kelt_upper"].shift(1))] = -1
    elif fam == "KELTNER_BREAKOUT":
        sig[_cross_up(close, g["kelt_upper"])] = 1; sig[_cross_down(close, g["kelt_lower"])] = -1
    elif fam == "PSAR_FLIP":
        d = g["psar_dir"]
        sig[(d > 0) & (d.shift(1) < 0)] = 1; sig[(d < 0) & (d.shift(1) > 0)] = -1
    elif fam == "ICHIMOKU_TREND":
        sig[_cross_up(close, g["ichi_top"])] = 1; sig[_cross_down(close, g["ichi_bottom"])] = -1
    elif fam == "OPENING_RANGE_BREAKOUT":
        after = g["bar_in_session"] >= 3
        sig[after & _cross_up(close, g["orb_high15"])] = 1
        sig[after & _cross_down(close, g["orb_low15"])] = -1
    elif fam == "PREVIOUS_DAY_BREAKOUT":
        sig[_cross_up(close, g["prior_day_high"])] = 1; sig[_cross_down(close, g["prior_day_low"])] = -1
    elif fam == "ROLLING_RANGE_BREAKOUT":
        sig[close > g["donchian_high20"]] = 1; sig[close < g["donchian_low20"]] = -1
    elif fam == "ENGULFING_REVERSAL":
        po, pc = g["open"].shift(1), g["close"].shift(1)
        bull = (close > g["open"]) & (pc < po) & (g["open"] <= pc) & (close >= po)
        bear = (close < g["open"]) & (pc > po) & (g["open"] >= pc) & (close <= po)
        sig[bull] = 1; sig[bear] = -1
    elif fam == "OUTSIDE_KEY_REVERSAL":
        outside = (g["high"] > g["high"].shift(1)) & (g["low"] < g["low"].shift(1))
        sig[outside & (close > g["open"]) & (close > close.shift(1))] = 1
        sig[outside & (close < g["open"]) & (close < close.shift(1))] = -1
    elif fam == "REGRESSION_REVERSION":
        z = g["reg_resid_z50"]
        sig[_cross_up(z, -2.0)] = 1; sig[_cross_down(z, 2.0)] = -1
    elif fam == "REGRESSION_SLOPE":
        s = g["reg_slope50"]
        sig[_cross_up(s, 0.0)] = 1; sig[_cross_down(s, 0.0)] = -1
    else:
        raise KeyError(fam)
    return sig


def split_sessions(data: pd.DataFrame, symbol: str) -> dict[str, list[str]]:
    sessions = sorted(data.loc[data["symbol"].eq(symbol), "session_date"].astype(str).unique().tolist())
    n = len(sessions)
    a = int(n * 0.50); b = int(n * 0.20); c = int(n * 0.15)
    if min(a, b, c, n - a - b - c) < 50:
        raise ValueError(f"insufficient {symbol} sessions: {n}")
    return {
        "observation": sessions[:a],
        "replication": sessions[a:a+b],
        "validation": sessions[a+b:a+b+c],
        "holdout": sessions[a+b+c:],
    }


def add_split(data: pd.DataFrame, splits_by_symbol: Mapping[str, Mapping[str, Sequence[str]]]) -> pd.DataFrame:
    out = data.copy()
    labels = []
    for row in out[["symbol", "session_date"]].itertuples(index=False):
        label = "excluded"
        for split, dates in splits_by_symbol[str(row.symbol)].items():
            if str(row.session_date) in set(map(str, dates)):
                label = split
                break
        labels.append(label)
    out["split"] = labels
    return out


def context_cuts(frame: pd.DataFrame, symbol: str) -> dict[str, list[float]]:
    obs = frame[(frame["symbol"] == symbol) & (frame["split"] == "observation")]
    result = {}
    for col in ("index_ret3", "index_vol6"):
        vals = pd.to_numeric(obs[col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        result[col] = [float(vals.quantile(1/3)), float(vals.quantile(2/3))] if len(vals) >= 100 else [0.0, 0.0]
    return result


def _bin(v: float, cuts: Sequence[float]) -> int:
    if not math.isfinite(v):
        return 1
    return int(np.digitize([v], np.asarray(cuts, float), right=False)[0])


def outcome_lookup(frame: pd.DataFrame, symbol: str, allowed: set[str]) -> dict[tuple[str, int, int], dict[str, Any]]:
    lookup = {}
    source = frame[(frame["symbol"] == symbol) & (frame["split"].isin(sorted(allowed)))]
    for session, group in source.groupby("session_date", sort=True):
        g = group.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
        for i in range(len(g)):
            signal_ts = pd.Timestamp(g.loc[i, "timestamp"])
            for h in HORIZONS:
                entry = i + 1
                exit_i = entry + h
                if exit_i >= len(g):
                    continue
                if pd.Timestamp(g.loc[entry, "timestamp"]) != signal_ts + pd.Timedelta(minutes=5):
                    continue
                if pd.Timestamp(g.loc[exit_i, "timestamp"]) != signal_ts + pd.Timedelta(minutes=5 * (h + 1)):
                    continue
                ep = float(g.loc[entry, "open"]); xp = float(g.loc[exit_i, "open"])
                if not (ep > 0 and xp > 0):
                    continue
                raw = math.log(xp / ep) * 10000.0
                shorter_i = entry + max(1, h // 2)
                delayed_entry = i + 2; delayed_exit = delayed_entry + h
                longer_i = entry + h + max(1, h // 2)
                lookup[(str(session), int(signal_ts.value), h)] = {
                    "raw_return_bps": float(raw),
                    "shorter_raw_return_bps": float(math.log(float(g.loc[shorter_i, "open"]) / ep) * 10000.0) if shorter_i < len(g) else None,
                    "delayed_raw_return_bps": float(math.log(float(g.loc[delayed_exit, "open"]) / float(g.loc[delayed_entry, "open"])) * 10000.0) if delayed_exit < len(g) else None,
                    "longer_raw_return_bps": float(math.log(float(g.loc[longer_i, "open"]) / ep) * 10000.0) if longer_i < len(g) else None,
                    "session_progress": float(g.loc[i, "session_progress"]),
                    "index_ret3": float(g.loc[i, "index_ret3"]) if pd.notna(g.loc[i, "index_ret3"]) else float("nan"),
                    "index_vol6": float(g.loc[i, "index_vol6"]) if pd.notna(g.loc[i, "index_vol6"]) else float("nan"),
                }
    return lookup


def baseline_table(frame: pd.DataFrame, symbol: str, lookup: Mapping[tuple[str, int, int], Mapping[str, Any]], cuts: Mapping[str, Sequence[float]]) -> dict[tuple[int, int, int, int], float]:
    vals: dict[tuple[int, int, int, int], list[float]] = defaultdict(list)
    obs = frame[(frame["symbol"] == symbol) & (frame["split"] == "observation")]
    for row in obs.itertuples(index=False):
        progress_bin = int(np.clip(math.floor(float(row.session_progress) * 10), 0, 9))
        mom_bin = _bin(float(row.index_ret3) if pd.notna(row.index_ret3) else float("nan"), cuts["index_ret3"])
        vol_bin = _bin(float(row.index_vol6) if pd.notna(row.index_vol6) else float("nan"), cuts["index_vol6"])
        ts = pd.Timestamp(row.timestamp)
        for h in HORIZONS:
            out = lookup.get((str(row.session_date), int(ts.value), h))
            if out is not None:
                vals[(h, progress_bin, mom_bin, vol_bin)].append(float(out["raw_return_bps"]))
    table = {}
    fallback: dict[tuple[int, int], list[float]] = defaultdict(list)
    for key, arr in vals.items():
        if len(arr) >= 20:
            table[key] = float(np.median(arr))
        fallback[(key[0], key[1])].extend(arr)
    for (h, pb), arr in fallback.items():
        if len(arr) >= 30:
            med = float(np.median(arr))
            for mb in range(3):
                for vb in range(3):
                    table.setdefault((h, pb, mb, vb), med)
    return table


def summarize(values: Sequence[float]) -> dict[str, Any]:
    arr = np.asarray(values, float)
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        return {"n": 0, "mean_bps": None, "median_bps": None, "hit_rate": None, "ci90": [None, None], "sign_p": 1.0}
    hits = int(np.sum(arr > 0))
    ci = A.PA.bootstrap_mean_ci(arr, confidence=0.90)
    return {
        "n": int(len(arr)), "mean_bps": float(np.mean(arr)), "median_bps": float(np.median(arr)),
        "hit_rate": float(hits / len(arr)), "ci90": [float(ci[0]), float(ci[1])],
        "sign_p": float(binomtest(hits, len(arr), 0.5, alternative="greater").pvalue),
    }


def first_signals(frame: pd.DataFrame, symbol: str, spec: MechanismSpec) -> dict[str, tuple[pd.Timestamp, int]]:
    result = {}
    source = frame[frame["symbol"] == symbol]
    for session, group in source.groupby("session_date", sort=True):
        g = group.sort_values("timestamp", kind="mergesort")
        s = _signal_for_family(g, spec)
        hit = np.flatnonzero(s.to_numpy(int) != 0)
        if len(hit):
            pos = int(hit[0])
            result[str(session)] = (pd.Timestamp(g.iloc[pos]["timestamp"]), int(s.iloc[pos]))
    return result


def attach_outcomes(frame: pd.DataFrame, specs: Sequence[MechanismSpec], symbol: str, splits: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    allowed = {"observation", "replication", "validation"}
    lookup = outcome_lookup(frame, symbol, allowed)
    cuts = context_cuts(frame, symbol)
    baseline = baseline_table(frame, symbol, lookup, cuts)
    split_map = {str(d): split for split, dates in splits.items() for d in dates}
    records = []
    for spec in specs:
        signals = first_signals(frame, symbol, spec)
        for h in HORIZONS:
            events = []
            for session, (ts, direction) in signals.items():
                split = split_map.get(session, "excluded")
                if split not in allowed:
                    continue
                out = lookup.get((session, int(ts.value), h))
                if out is None:
                    continue
                pb = int(np.clip(math.floor(out["session_progress"] * 10), 0, 9))
                mb = _bin(out["index_ret3"], cuts["index_ret3"]); vb = _bin(out["index_vol6"], cuts["index_vol6"])
                base = baseline.get((h, pb, mb, vb))
                if base is None:
                    continue
                raw = float(out["raw_return_bps"])
                events.append({
                    "session_date": session, "split": split, "signal_timestamp": str(ts), "direction": direction,
                    "directional_excess_bps": direction * (raw - float(base)),
                    "directional_gross_bps": direction * raw,
                    "net_proxy_bps": direction * raw - A.COST_BPS,
                    "delayed_net_proxy_bps": direction * float(out["delayed_raw_return_bps"]) - A.COST_BPS if out["delayed_raw_return_bps"] is not None else None,
                    "shorter_net_proxy_bps": direction * float(out["shorter_raw_return_bps"]) - A.COST_BPS if out["shorter_raw_return_bps"] is not None else None,
                    "longer_net_proxy_bps": direction * float(out["longer_raw_return_bps"]) - A.COST_BPS if out["longer_raw_return_bps"] is not None else None,
                })
            stats = {}
            for split in ("observation", "replication", "validation"):
                subset = [e for e in events if e["split"] == split]
                stats[split] = {
                    "directional_excess": summarize([e["directional_excess_bps"] for e in subset]),
                    "net_proxy": summarize([e["net_proxy_bps"] for e in subset]),
                }
            records.append({
                "hypothesis_id": f"TV::{spec.signature}::H{h}",
                "mechanism_signature": spec.signature,
                "family": spec.family,
                "horizon_bars": h,
                "stats": stats,
                "events": events,
            })
    return {"symbol": symbol, "records": records, "context_thresholds": cuts, "baseline_cells": len(baseline)}


def structural_screen(outcomes: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    pvals = []
    for record in outcomes["records"]:
        obs = record["stats"]["observation"]["directional_excess"]
        rep = record["stats"]["replication"]["directional_excess"]
        pvals.append(float(rep["sign_p"]))
        rows.append({
            "hypothesis_id": record["hypothesis_id"], "mechanism_signature": record["mechanism_signature"], "family": record["family"],
            "observation": obs, "replication": rep,
        })
    qvals = A.PA.bh_qvalues(pvals)
    survivors = []
    for row, q in zip(rows, qvals):
        obs, rep = row["observation"], row["replication"]
        gates = {
            "observation_n_ge_30": obs["n"] >= 30,
            "observation_mean_excess_ge_2bps": float(obs["mean_bps"] or -1e9) >= 2.0,
            "replication_n_ge_15": rep["n"] >= 15,
            "replication_mean_excess_ge_2bps": float(rep["mean_bps"] or -1e9) >= 2.0,
            "replication_hit_rate_ge_55pct": float(rep["hit_rate"] or 0.0) >= 0.55,
            "replication_ci90_lower_positive": rep["ci90"][0] is not None and float(rep["ci90"][0]) > 0.0,
            "global_bh_q_le_1pct": float(q) <= GLOBAL_Q,
        }
        row["bh_q"] = float(q); row["gates"] = gates; row["passed"] = all(gates.values())
        if row["passed"]:
            survivors.append(row["hypothesis_id"])
    return {"survivor_hypothesis_ids": survivors, "results": rows, "global_q_threshold": GLOBAL_Q}


def validation_wfa(outcomes: Mapping[str, Any], screen: Mapping[str, Any]) -> dict[str, Any]:
    record_by_id = {r["hypothesis_id"]: r for r in outcomes["records"]}
    results = []; survivors = []
    for hid in screen["survivor_hypothesis_ids"]:
        record = record_by_id[hid]
        val = [e for e in record["events"] if e["split"] == "validation"]
        val_stats = summarize([e["net_proxy_bps"] for e in val])
        dev = [e for e in record["events"] if e["split"] in {"observation", "replication", "validation"}]
        dates = sorted({e["session_date"] for e in dev})
        folds = np.array_split(np.asarray(dates, object), 4) if dates else []
        positive = 0; usable = 0; fold_stats = []
        for i, fold in enumerate(folds):
            allowed = set(map(str, fold.tolist()))
            vals = [e["net_proxy_bps"] for e in dev if e["session_date"] in allowed]
            st = summarize(vals); fold_stats.append({"fold": i, **st})
            if st["n"] >= 5:
                usable += 1; positive += int(float(st["mean_bps"] or -1e9) > 0)
        worst = min((float(x["mean_bps"]) for x in fold_stats if x["n"] >= 5 and x["mean_bps"] is not None), default=-1e9)
        gates = {
            "validation_n_ge_10": val_stats["n"] >= 10,
            "validation_mean_net_positive": float(val_stats["mean_bps"] or -1e9) > 0,
            "validation_hit_rate_ge_50pct": float(val_stats["hit_rate"] or 0) >= 0.50,
            "wfa_usable_folds_ge_3": usable >= 3,
            "wfa_positive_fold_share_ge_75pct": usable >= 3 and positive / usable >= 0.75,
            "wfa_worst_fold_gt_minus5bps": worst > -5.0,
        }
        passed = all(gates.values())
        results.append({"hypothesis_id": hid, "validation": val_stats, "folds": fold_stats, "gates": gates, "passed": passed})
        if passed: survivors.append(hid)
    return {"survivor_hypothesis_ids": survivors, "results": results}


def robustness(outcomes: Mapping[str, Any], wfa: Mapping[str, Any], bank_outcomes: Mapping[str, Any] | None = None) -> dict[str, Any]:
    record_by_id = {r["hypothesis_id"]: r for r in outcomes["records"]}
    bank_by_signature_h = {}
    if bank_outcomes:
        for r in bank_outcomes["records"]:
            bank_by_signature_h[(r["mechanism_signature"], int(r["horizon_bars"]))] = r
    results = []; survivors = []
    for hid in wfa["survivor_hypothesis_ids"]:
        r = record_by_id[hid]
        events = [e for e in r["events"] if e["split"] in {"observation", "replication", "validation"}]
        gross = np.asarray([e["directional_gross_bps"] for e in events], float)
        if len(gross) < 30:
            results.append({"hypothesis_id": hid, "passed": False, "reason": "insufficient_events"}); continue
        base = gross - A.COST_BPS
        high_cost = gross - 10.0
        remove_n = max(1, int(math.ceil(len(base) * 0.10)))
        keep = np.ones(len(base), bool); keep[np.argsort(base)[-remove_n:]] = False
        stripped = base[keep]
        delayed = np.asarray([e["delayed_net_proxy_bps"] for e in events if e["delayed_net_proxy_bps"] is not None], float)
        shorter = np.asarray([e["shorter_net_proxy_bps"] for e in events if e["shorter_net_proxy_bps"] is not None], float)
        longer = np.asarray([e["longer_net_proxy_bps"] for e in events if e["longer_net_proxy_bps"] is not None], float)
        bank = bank_by_signature_h.get((r["mechanism_signature"], int(r["horizon_bars"])))
        bank_rep = bank["stats"]["replication"]["net_proxy"] if bank else {"n": 0, "mean_bps": None}
        gates = {
            "base_mean_positive": float(np.mean(base)) > 0,
            "ten_bps_cost_mean_positive": float(np.mean(high_cost)) > 0,
            "remove_best_10pct_mean_positive": len(stripped) > 0 and float(np.mean(stripped)) > 0,
            "delayed_entry_mean_positive": len(delayed) >= 15 and float(np.mean(delayed)) > 0,
            "shorter_horizon_not_catastrophic": len(shorter) >= 15 and float(np.mean(shorter)) > -5,
            "longer_horizon_not_catastrophic": len(longer) >= 15 and float(np.mean(longer)) > -5,
            "banknifty_replication_nonnegative_if_available": bank_rep["n"] < 15 or float(bank_rep["mean_bps"] or -1e9) >= 0,
        }
        passed = all(gates.values())
        results.append({
            "hypothesis_id": hid, "passed": passed, "gates": gates,
            "base_mean_bps": float(np.mean(base)), "ten_bps_cost_mean_bps": float(np.mean(high_cost)),
            "remove_best_10pct_mean_bps": float(np.mean(stripped)) if len(stripped) else None,
            "delayed_entry_mean_bps": float(np.mean(delayed)) if len(delayed) else None,
            "banknifty_replication": bank_rep,
        })
        if passed: survivors.append(hid)
    return {"survivor_hypothesis_ids": survivors, "results": results}


def holdout_test(frame: pd.DataFrame, specs: Sequence[MechanismSpec], outcomes: Mapping[str, Any], robust: Mapping[str, Any], symbol: str = "NIFTY") -> dict[str, Any]:
    candidates = robust["survivor_hypothesis_ids"][:MAX_FINAL]
    if not candidates:
        return {"holdout_scored": False, "tested": [], "survivors": [], "results": []}
    record_by_id = {r["hypothesis_id"]: r for r in outcomes["records"]}
    spec_by_sig = {s.signature: s for s in specs}
    lookup = outcome_lookup(frame, symbol, {"holdout"})
    results = []; survivors = []
    for hid in candidates:
        record = record_by_id[hid]
        spec = spec_by_sig[record["mechanism_signature"]]
        h = int(record["horizon_bars"])
        signals = first_signals(frame[frame["split"] == "holdout"], symbol, spec)
        vals = []
        for session, (ts, direction) in signals.items():
            out = lookup.get((session, int(ts.value), h))
            if out is not None:
                vals.append(direction * float(out["raw_return_bps"]) - A.COST_BPS)
        stats = summarize(vals)
        gates = {
            "n_ge_15": stats["n"] >= 15,
            "mean_net_ge_2bps": float(stats["mean_bps"] or -1e9) >= 2.0,
            "hit_rate_ge_55pct": float(stats["hit_rate"] or 0) >= 0.55,
            "ci90_lower_positive": stats["ci90"][0] is not None and float(stats["ci90"][0]) > 0,
        }
        passed = all(gates.values())
        results.append({"hypothesis_id": hid, "stats": stats, "gates": gates, "passed": passed})
        if passed: survivors.append(hid)
    return {"holdout_scored": True, "tested": candidates, "survivors": survivors, "results": results}


def prepare_specs(inventory: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    unique: dict[str, MechanismSpec] = {}
    counts = Counter()
    for record in inventory.get("records", []):
        spec, status = map_record(record)
        counts[status] += 1
        row = {
            "script_id": record.get("script_id"), "title": record.get("title"), "url": record.get("url"),
            "inventory_status": record.get("initial_status"), "benchmark_status": status,
            "mechanism_signature": spec.signature if spec else None,
            "family": spec.family if spec else None,
            "derivation": spec.derivation if spec else None,
        }
        rows.append(row)
        if spec:
            unique.setdefault(spec.signature, spec)
    payload = {
        "script_rows": rows,
        "benchmark_status_counts": dict(sorted(counts.items())),
        "unique_mechanism_count": len(unique),
        "mechanisms": [
            {"signature": s.signature, "family": s.family, "params": s.param_dict(), "derivation": s.derivation}
            for s in sorted(unique.values(), key=lambda x: x.signature)
        ],
        "policy": {
            "mapping_frozen_before_market_outcomes": True,
            "canonical_mechanism_is_not_exact_source_reproduction": True,
            "volume_required_scripts_excluded_from_independent_ohlc_lane": True,
            "protected_source_not_reverse_engineered": True,
        },
    }
    payload["semantic_sha256"] = digest(payload)
    return payload


def run_benchmark(inventory: Mapping[str, Any], work_root: Path) -> dict[str, Any]:
    mapping = prepare_specs(inventory)
    specs = [MechanismSpec(m["family"], tuple(sorted((k, float(v)) for k, v in m["params"].items())), m["derivation"]) for m in mapping["mechanisms"]]
    repo, selected = clone_aeron(work_root)
    raw, source_authority = load_aeron_raw(repo, selected)
    bars, bar_authority = resample_5m(raw)
    frame = build_features(bars)
    splits = {symbol: split_sessions(frame, symbol) for symbol in SYMBOLS}
    frame = add_split(frame, splits)

    nifty_outcomes = attach_outcomes(frame, specs, "NIFTY", splits["NIFTY"])
    bank_outcomes = attach_outcomes(frame, specs, "BANKNIFTY", splits["BANKNIFTY"])
    screen = structural_screen(nifty_outcomes)
    wfa = validation_wfa(nifty_outcomes, screen)
    robust = robustness(nifty_outcomes, wfa, bank_outcomes)
    final = holdout_test(frame, specs, nifty_outcomes, robust, "NIFTY")

    result = {
        "campaign": "tradingview_public_library_benchmark_v1",
        "mapping": mapping,
        "source_authority": source_authority,
        "bar_authority": bar_authority,
        "split_counts": {s: {k: len(v) for k, v in splits[s].items()} for s in SYMBOLS},
        "nifty_outcomes": nifty_outcomes,
        "banknifty_outcomes": bank_outcomes,
        "structural_screen": screen,
        "validation_wfa": wfa,
        "robustness": robust,
        "final_holdout": final,
        "final_authority": {
            "principal_verdict": (
                "TRADINGVIEW_EXTERNAL_HYPOTHESIS_HOLDOUT_SURVIVORS_REQUIRING_EXACT_SCRIPT_RECONSTRUCTION"
                if final["survivors"] else
                "NO_TRADINGVIEW_CANONICAL_PRICE_MECHANISM_SURVIVED_INDEPENDENT_CERTIFICATION"
            ),
            "inventory_scripts": int(inventory.get("unique_script_count", 0)),
            "mapped_scripts": sum(1 for r in mapping["script_rows"] if r["mechanism_signature"]),
            "unique_mechanisms": mapping["unique_mechanism_count"],
            "tested_hypotheses": len(nifty_outcomes["records"]),
            "structural_screen_survivors": len(screen["survivor_hypothesis_ids"]),
            "validation_wfa_survivors": len(wfa["survivor_hypothesis_ids"]),
            "robustness_survivors": len(robust["survivor_hypothesis_ids"]),
            "holdout_survivors": len(final["survivors"]),
            "exact_tradingview_script_certified": False,
            "options_edge_certified": False,
            "shadow_authorized": False,
            "paper_authorized": False,
            "live_authorized": False,
            "order_authorized": False,
            "next_gate_if_survivor": "RECONSTRUCT_ASSOCIATED_SCRIPT_RULE_EXACTLY_THEN_RETEST_WITHOUT_PARAMETER_TUNING",
        },
    }
    result["semantic_sha256"] = digest({k: v for k, v in result.items() if k not in {"nifty_outcomes", "banknifty_outcomes"}})
    return result
