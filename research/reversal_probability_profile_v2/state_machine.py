from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
import hashlib
import json
import math

import numpy as np
import pandas as pd

IST = "Asia/Kolkata"
CAMPAIGN_ID = "RPP_NIFTY_ZONE_INTERACTION_V2"
SPEC_VERSION = "2.0.0"

INTERACTION_STATES = ("NO_DECISION", "REJECTED", "BROKEN", "ACCEPTED", "RECLAIMED")
DIRECTIONS = ("NONE", "BULLISH", "BEARISH")


@dataclass(frozen=True)
class RPPV2Config:
    # Structural profile. These are research translations of the public concept,
    # not claimed to be the author's hidden/default Pine parameters.
    pivot_left: int = 5
    pivot_right: int = 5
    profile_bins: int = 64
    smoothing_radius_bins: int = 2
    min_profile_pivots: int = 20
    pivot_memory: int = 120
    lookback_sessions: int = 3

    # Causal price-interaction semantics.
    atr_window_minutes: int = 30
    approach_window_minutes: int = 10
    zone_search_distance_atr: float = 2.0
    touch_radius_atr: float = 0.20
    rejection_margin_atr: float = 0.05
    breakout_margin_atr: float = 0.10
    acceptance_bars: int = 2
    reclaim_touch_radius_atr: float = 0.20
    min_event_density: float = 0.65
    high_density_diagnostic: float = 0.80

    # Outcome contract.
    primary_horizon_minutes: int = 15
    secondary_horizons_minutes: tuple[int, ...] = (20, 30)
    negative_control_shift_minutes: int = 30
    round_trip_cost_bps: float = 5.0
    deoverlap_minutes: int = 15

    # Frozen evaluation geometry. No threshold/candidate search occurs in V2.
    reserve_tail_sessions: int = 63
    warmup_sessions: int = 126
    test_sessions: int = 63
    step_sessions: int = 63
    min_oos_folds: int = 3
    min_oos_events: int = 90
    min_oos_sessions: int = 45
    min_positive_fold_fraction: float = 0.60
    min_hit_rate: float = 0.52
    min_incremental_bps_vs_momentum: float = 0.50
    min_incremental_bps_vs_shifted_control: float = 0.50
    min_shifted_control_events: int = 45
    max_single_fold_positive_profit_share: float = 0.65
    bootstrap_repetitions: int = 2000
    bootstrap_seed: int = 20260906

    def digest(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


def sha256_path(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_table(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    if p.suffix.lower() == ".csv":
        return pd.read_csv(p)
    if p.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(p)
    raise ValueError(f"unsupported_table_format:{p.suffix}")


def _canonical_ts(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce")
    if ts.isna().any():
        raise ValueError("timestamp_parse_failure")
    if getattr(ts.dt, "tz", None) is None:
        ts = ts.dt.tz_localize(IST)
    else:
        ts = ts.dt.tz_convert(IST)
    return ts


def load_nifty_ohlc(path: str | Path, symbol: str = "NIFTY") -> pd.DataFrame:
    """Load NIFTY OHLC from either a single-instrument table or long symbol panel.

    The governed 5-minute constituent/index corpus is long-form. Filtering occurs
    before duplicate-timestamp validation so other symbols cannot contaminate the
    NIFTY stream.
    """
    raw = _read_table(path).copy()
    lower = {str(c).lower(): c for c in raw.columns}
    symbol_col = lower.get("symbol") or lower.get("instrument")
    if symbol_col is not None:
        vals = raw[symbol_col].astype(str).str.upper().str.strip()
        exact = vals == symbol.upper()
        if exact.any():
            raw = raw.loc[exact].copy()
        else:
            # Some canonical panels use decorated names. Admit only unambiguous
            # exact-prefix NIFTY rows; never silently mix BANKNIFTY/SENSEX.
            pref = vals.str.match(r"^NIFTY(?:$|\s|50|_)", na=False)
            raw = raw.loc[pref].copy()
        if raw.empty:
            raise ValueError(f"symbol_not_found:{symbol}")

    lower = {str(c).lower(): c for c in raw.columns}
    ts_col = next((lower[k] for k in ("timestamp", "datetime", "date", "ts") if k in lower), None)
    aliases = {
        "open": ("open", "spot_open", "o"),
        "high": ("high", "spot_high", "h"),
        "low": ("low", "spot_low", "l"),
        "close": ("close", "spot_close", "c"),
    }
    cols: dict[str, str | None] = {}
    for key, names in aliases.items():
        cols[key] = next((lower[n] for n in names if n in lower), None)
    if ts_col is None or any(v is None for v in cols.values()):
        raise ValueError("nifty_table_requires_timestamp_ohlc")

    out = pd.DataFrame({"timestamp": _canonical_ts(raw[ts_col])})
    for key, col in cols.items():
        out[key] = pd.to_numeric(raw[col], errors="coerce")
    out = out.dropna().sort_values("timestamp").reset_index(drop=True)
    if out.duplicated("timestamp").any():
        raise ValueError("duplicate_nifty_timestamps_after_symbol_filter")
    invalid = (
        (out["high"] < out[["open", "close", "low"]].max(axis=1))
        | (out["low"] > out[["open", "close", "high"]].min(axis=1))
    )
    if invalid.any():
        raise ValueError("invalid_ohlc")

    hhmm = out["timestamp"].dt.strftime("%H:%M")
    out = out.loc[(hhmm >= "09:15") & (hhmm <= "15:30")].copy()
    out["session"] = out["timestamp"].dt.date
    return out.reset_index(drop=True)


def infer_cadence_minutes(prices: pd.DataFrame) -> int:
    diffs: list[float] = []
    for _, day in prices.groupby("session", sort=True):
        d = day["timestamp"].sort_values().diff().dt.total_seconds().div(60).dropna()
        diffs.extend(d[d > 0].tolist())
    if not diffs:
        raise ValueError("cannot_infer_cadence")
    med = float(np.median(np.asarray(diffs, dtype=float)))
    cadence = int(round(med))
    if cadence <= 0 or abs(med - cadence) > 1e-6:
        raise ValueError(f"unsupported_noninteger_cadence:{med}")
    return cadence


def _bars_for_minutes(minutes: int, cadence_minutes: int) -> int:
    return max(1, int(math.ceil(minutes / cadence_minutes)))


def _causal_atr_and_approach(prices: pd.DataFrame, cfg: RPPV2Config, cadence: int) -> pd.DataFrame:
    out = prices.copy()
    out["prev_close"] = out.groupby("session", sort=False)["close"].shift(1)
    tr = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - out["prev_close"]).abs(),
            (out["low"] - out["prev_close"]).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_bars = _bars_for_minutes(cfg.atr_window_minutes, cadence)
    min_periods = max(2, min(atr_bars, max(3, atr_bars // 2)))
    out["atr"] = tr.groupby(out["session"]).transform(
        lambda s: s.rolling(atr_bars, min_periods=min_periods).mean()
    )
    approach_bars = _bars_for_minutes(cfg.approach_window_minutes, cadence)
    lag = out.groupby("session", sort=False)["close"].shift(approach_bars)
    out["approach_momentum_atr"] = (out["close"] - lag) / out["atr"]
    out["approach_direction"] = np.select(
        [out["approach_momentum_atr"] > 0, out["approach_momentum_atr"] < 0],
        ["UP", "DOWN"],
        default="FLAT",
    )
    return out


def _pivot_confirmations(df: pd.DataFrame, cfg: RPPV2Config) -> dict[int, list[tuple[str, float, int]]]:
    """Return pivots keyed by confirmation-bar index, never pivot-center index."""
    confirmations: dict[int, list[tuple[str, float, int]]] = {}
    left, right = cfg.pivot_left, cfg.pivot_right
    for _, day in df.groupby("session", sort=True):
        idx = day.index.to_numpy()
        highs = day["high"].to_numpy(float)
        lows = day["low"].to_numpy(float)
        for c in range(left, len(day) - right):
            hi_window = highs[c - left : c + right + 1]
            lo_window = lows[c - left : c + right + 1]
            confirm_idx = int(idx[c + right])
            pivot_idx = int(idx[c])
            if highs[c] == np.max(hi_window) and np.sum(hi_window == highs[c]) == 1:
                confirmations.setdefault(confirm_idx, []).append(("HIGH", float(highs[c]), pivot_idx))
            if lows[c] == np.min(lo_window) and np.sum(lo_window == lows[c]) == 1:
                confirmations.setdefault(confirm_idx, []).append(("LOW", float(lows[c]), pivot_idx))
    return confirmations


def _smooth(counts: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return counts.astype(float)
    offsets = np.arange(-radius, radius + 1)
    kernel = (radius + 1 - np.abs(offsets)).astype(float)
    return np.convolve(counts.astype(float), kernel, mode="same")


def _local_peaks(values: np.ndarray) -> np.ndarray:
    peaks: list[int] = []
    for i, value in enumerate(values):
        if value <= 0:
            continue
        left = values[i - 1] if i > 0 else -np.inf
        right = values[i + 1] if i + 1 < len(values) else -np.inf
        if value >= left and value >= right and (value > left or value > right):
            peaks.append(i)
    return np.asarray(peaks, dtype=int)


def _build_profile(pivots: Iterable[tuple[str, float, int, int]], cfg: RPPV2Config):
    piv = list(pivots)
    if len(piv) < cfg.min_profile_pivots:
        return None
    prices = np.asarray([p[1] for p in piv], dtype=float)
    lo, hi = float(np.min(prices)), float(np.max(prices))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return None
    edges = np.linspace(lo, hi, cfg.profile_bins + 1)
    bins = np.clip(np.searchsorted(edges, prices, side="right") - 1, 0, cfg.profile_bins - 1)
    highs = np.zeros(cfg.profile_bins, dtype=float)
    lows = np.zeros(cfg.profile_bins, dtype=float)
    for (kind, _, _, _), b in zip(piv, bins):
        (highs if kind == "HIGH" else lows)[b] += 1.0
    high_s = _smooth(highs, cfg.smoothing_radius_bins)
    low_s = _smooth(lows, cfg.smoothing_radius_bins)
    total = high_s + low_s
    tallest = float(np.max(total))
    if tallest <= 0:
        return None
    centers = (edges[:-1] + edges[1:]) / 2.0
    # This normalization is a relative historical density score. It is never
    # interpreted as a calibrated future reversal probability.
    relative_density = total / tallest
    return {
        "centers": centers,
        "high": high_s,
        "low": low_s,
        "total": total,
        "relative_density": relative_density,
        "support_peaks": _local_peaks(low_s),
        "resistance_peaks": _local_peaks(high_s),
        "max_idx": int(np.argmax(total)),
    }


def build_causal_location_map(
    prices: pd.DataFrame,
    cfg: RPPV2Config = RPPV2Config(),
) -> pd.DataFrame:
    """Build the market-memory/location layer from confirmed historical pivots only."""
    cadence = infer_cadence_minutes(prices)
    base = _causal_atr_and_approach(prices.reset_index(drop=True), cfg, cadence)
    confirmations = _pivot_confirmations(base, cfg)
    memory: deque[tuple[str, float, int, int]] = deque()
    profile = None
    bars_per_session = max(1, int(round(375 / cadence)))
    lookback_bars = cfg.lookback_sessions * bars_per_session
    rows: list[dict] = []

    for i, row in base.iterrows():
        changed = False
        for kind, price, pivot_idx in confirmations.get(i, []):
            memory.append((kind, price, pivot_idx, i))
            changed = True
        cutoff = i - lookback_bars
        while memory and memory[0][3] < cutoff:
            memory.popleft()
            changed = True
        while len(memory) > cfg.pivot_memory:
            memory.popleft()
            changed = True
        if changed:
            profile = _build_profile(memory, cfg)

        atr = float(row["atr"]) if pd.notna(row["atr"]) else np.nan
        if profile is None or not np.isfinite(atr) or atr <= 0:
            continue

        price = float(row["close"])
        centers = profile["centers"]
        density = profile["relative_density"]
        support_idx = profile["support_peaks"]
        resistance_idx = profile["resistance_peaks"]

        support = np.nan
        support_density = np.nan
        resistance = np.nan
        resistance_density = np.nan

        supports = support_idx[centers[support_idx] <= price]
        if len(supports):
            dist = price - centers[supports]
            valid = dist <= cfg.zone_search_distance_atr * atr
            if valid.any():
                k = int(supports[np.argmin(np.where(valid, dist, np.inf))])
                support = float(centers[k])
                support_density = float(density[k])

        resistances = resistance_idx[centers[resistance_idx] >= price]
        if len(resistances):
            dist = centers[resistances] - price
            valid = dist <= cfg.zone_search_distance_atr * atr
            if valid.any():
                k = int(resistances[np.argmin(np.where(valid, dist, np.inf))])
                resistance = float(centers[k])
                resistance_density = float(density[k])

        max_idx = profile["max_idx"]
        s_dist = (price - support) / atr if np.isfinite(support) else np.nan
        r_dist = (resistance - price) / atr if np.isfinite(resistance) else np.nan
        if np.isfinite(s_dist) and np.isfinite(r_dist):
            nearest_type = "SUPPORT" if s_dist <= r_dist else "RESISTANCE"
        elif np.isfinite(s_dist):
            nearest_type = "SUPPORT"
        elif np.isfinite(r_dist):
            nearest_type = "RESISTANCE"
        else:
            nearest_type = "NONE"

        rows.append(
            {
                "timestamp": row["timestamp"],
                "session": row["session"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": price,
                "prev_close": float(row["prev_close"]) if pd.notna(row["prev_close"]) else np.nan,
                "atr": atr,
                "cadence_minutes": cadence,
                "approach_momentum_atr": (
                    float(row["approach_momentum_atr"]) if pd.notna(row["approach_momentum_atr"]) else np.nan
                ),
                "approach_direction": str(row["approach_direction"]),
                "confirmed_pivot_count": len(memory),
                "support": support,
                "support_density": support_density,
                "support_distance_atr": s_dist,
                "resistance": resistance,
                "resistance_density": resistance_density,
                "resistance_distance_atr": r_dist,
                "nearest_zone_type": nearest_type,
                "max_reversal_zone": float(centers[max_idx]),
                "max_zone_distance_atr": (price - float(centers[max_idx])) / atr,
                "max_zone_relative_density": float(density[max_idx]),
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


def label_zone_interactions(
    location: pd.DataFrame,
    cfg: RPPV2Config = RPPV2Config(),
) -> pd.DataFrame:
    """Turn the location map into a causal interaction state machine.

    Critical rule: a new touch/break is always evaluated against the previous
    completed bar's already-known support/resistance zone. A same-bar zone
    re-selection can never create its own signal.
    """
    if location.empty:
        return location.copy()

    out = location.copy().sort_values("timestamp").reset_index(drop=True)
    records: list[dict] = []
    active: dict | None = None
    current_session = None

    for i, row in out.iterrows():
        if current_session != row["session"]:
            current_session = row["session"]
            active = None

        state = "NO_DECISION"
        direction = "NONE"
        zone_type = "NONE"
        zone = np.nan
        density = np.nan
        source_timestamp = pd.NaT

        atr = float(row["atr"])
        close = float(row["close"])
        high = float(row["high"])
        low = float(row["low"])

        # First evolve an already-broken zone. This is what distinguishes a
        # first break from later acceptance and reclaim confirmation.
        if active is not None:
            z = float(active["zone"])
            d = float(active["density"])
            if active["direction"] == "BULLISH":
                beyond = close >= z + cfg.breakout_margin_atr * atr
                retest = low <= z + cfg.reclaim_touch_radius_atr * atr
                reclaimed = retest and close >= z + cfg.rejection_margin_atr * atr
                invalidated = close < z - cfg.rejection_margin_atr * atr
                if reclaimed and i > active["break_index"]:
                    state, direction, zone_type = "RECLAIMED", "BULLISH", "RESISTANCE_TO_SUPPORT"
                    zone, density, source_timestamp = z, d, active["source_timestamp"]
                    active["reclaimed"] = True
                elif beyond:
                    active["consecutive_beyond"] += 1
                    if active["consecutive_beyond"] >= cfg.acceptance_bars and not active["accepted"]:
                        state, direction, zone_type = "ACCEPTED", "BULLISH", "RESISTANCE"
                        zone, density, source_timestamp = z, d, active["source_timestamp"]
                        active["accepted"] = True
                else:
                    active["consecutive_beyond"] = 0
                if invalidated:
                    active = None
            else:
                beyond = close <= z - cfg.breakout_margin_atr * atr
                retest = high >= z - cfg.reclaim_touch_radius_atr * atr
                reclaimed = retest and close <= z - cfg.rejection_margin_atr * atr
                invalidated = close > z + cfg.rejection_margin_atr * atr
                if reclaimed and i > active["break_index"]:
                    state, direction, zone_type = "RECLAIMED", "BEARISH", "SUPPORT_TO_RESISTANCE"
                    zone, density, source_timestamp = z, d, active["source_timestamp"]
                    active["reclaimed"] = True
                elif beyond:
                    active["consecutive_beyond"] += 1
                    if active["consecutive_beyond"] >= cfg.acceptance_bars and not active["accepted"]:
                        state, direction, zone_type = "ACCEPTED", "BEARISH", "SUPPORT"
                        zone, density, source_timestamp = z, d, active["source_timestamp"]
                        active["accepted"] = True
                else:
                    active["consecutive_beyond"] = 0
                if invalidated:
                    active = None

        # If an active context did not emit a confirmation on this bar, inspect
        # the prior completed bar's known zones for a new break or rejection.
        if state == "NO_DECISION" and i > 0:
            prev = out.iloc[i - 1]
            if prev["session"] == row["session"]:
                approach = float(row["approach_momentum_atr"]) if pd.notna(row["approach_momentum_atr"]) else 0.0

                pr = float(prev["resistance"]) if pd.notna(prev["resistance"]) else np.nan
                prd = float(prev["resistance_density"]) if pd.notna(prev["resistance_density"]) else np.nan
                ps = float(prev["support"]) if pd.notna(prev["support"]) else np.nan
                psd = float(prev["support_density"]) if pd.notna(prev["support_density"]) else np.nan
                prev_close = float(prev["close"])

                bull_break = (
                    np.isfinite(pr)
                    and np.isfinite(prd)
                    and prev_close <= pr + cfg.rejection_margin_atr * atr
                    and close >= pr + cfg.breakout_margin_atr * atr
                    and approach >= 0
                )
                bear_break = (
                    np.isfinite(ps)
                    and np.isfinite(psd)
                    and prev_close >= ps - cfg.rejection_margin_atr * atr
                    and close <= ps - cfg.breakout_margin_atr * atr
                    and approach <= 0
                )

                if bull_break:
                    state, direction, zone_type = "BROKEN", "BULLISH", "RESISTANCE"
                    zone, density, source_timestamp = pr, prd, prev["timestamp"]
                    active = {
                        "direction": "BULLISH",
                        "zone": pr,
                        "density": prd,
                        "source_timestamp": prev["timestamp"],
                        "break_index": i,
                        "consecutive_beyond": 1,
                        "accepted": False,
                        "reclaimed": False,
                    }
                elif bear_break:
                    state, direction, zone_type = "BROKEN", "BEARISH", "SUPPORT"
                    zone, density, source_timestamp = ps, psd, prev["timestamp"]
                    active = {
                        "direction": "BEARISH",
                        "zone": ps,
                        "density": psd,
                        "source_timestamp": prev["timestamp"],
                        "break_index": i,
                        "consecutive_beyond": 1,
                        "accepted": False,
                        "reclaimed": False,
                    }
                else:
                    support_reject = (
                        np.isfinite(ps)
                        and np.isfinite(psd)
                        and approach <= 0
                        and low <= ps + cfg.touch_radius_atr * atr
                        and close >= ps + cfg.rejection_margin_atr * atr
                        and prev_close >= ps - cfg.touch_radius_atr * atr
                    )
                    resistance_reject = (
                        np.isfinite(pr)
                        and np.isfinite(prd)
                        and approach >= 0
                        and high >= pr - cfg.touch_radius_atr * atr
                        and close <= pr - cfg.rejection_margin_atr * atr
                        and prev_close <= pr + cfg.touch_radius_atr * atr
                    )
                    if support_reject and resistance_reject:
                        # If a compressed bar interacts with both sides, select
                        # only the closer prior-known zone. Never emit two trades.
                        sd = abs(prev_close - ps)
                        rd = abs(pr - prev_close)
                        support_reject = sd <= rd
                        resistance_reject = not support_reject
                    if support_reject:
                        state, direction, zone_type = "REJECTED", "BULLISH", "SUPPORT"
                        zone, density, source_timestamp = ps, psd, prev["timestamp"]
                    elif resistance_reject:
                        state, direction, zone_type = "REJECTED", "BEARISH", "RESISTANCE"
                        zone, density, source_timestamp = pr, prd, prev["timestamp"]

        rec = row.to_dict()
        rec.update(
            {
                "interaction_state": state,
                "interaction_direction": direction,
                "interaction_zone_type": zone_type,
                "interaction_zone": zone,
                "interaction_density": density,
                "zone_source_timestamp": source_timestamp,
                "event_density_eligible": bool(np.isfinite(density) and density >= cfg.min_event_density),
                "high_density_diagnostic": bool(np.isfinite(density) and density >= cfg.high_density_diagnostic),
            }
        )
        records.append(rec)

    return pd.DataFrame(records)


def build_confirmed_events(states: pd.DataFrame, cfg: RPPV2Config = RPPV2Config()) -> pd.DataFrame:
    """Forecast only after confirmation, not on first break.

    REJECTED is itself close-confirmed rejection. ACCEPTED requires the frozen
    number of closes beyond the broken zone. RECLAIMED requires a post-break
    retest and close back in the breakout direction. BROKEN remains diagnostic.
    """
    if states.empty:
        return states.copy()
    mask = states["interaction_state"].isin(["REJECTED", "ACCEPTED", "RECLAIMED"])
    mask &= states["event_density_eligible"]
    ev = states.loc[mask].copy()
    ev["signal"] = np.where(ev["interaction_direction"] == "BULLISH", 1, -1)
    ev["event_type"] = ev["interaction_direction"] + "_" + ev["interaction_state"]
    return _deoverlap(ev, cfg.deoverlap_minutes)


def _deoverlap(events: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    keep: list[int] = []
    for _, day in events.sort_values("timestamp").groupby("session", sort=True):
        last = None
        for idx, row in day.iterrows():
            ts = row["timestamp"]
            if last is None or (ts - last) >= pd.Timedelta(minutes=minutes):
                keep.append(idx)
                last = ts
    return events.loc[keep].sort_values("timestamp").reset_index(drop=True)


def attach_forward_outcomes(
    events: pd.DataFrame,
    prices: pd.DataFrame,
    cfg: RPPV2Config = RPPV2Config(),
) -> pd.DataFrame:
    """Use the next actual bar open, so 1m and 5m corpora share one contract."""
    if events.empty:
        return events.copy()
    p = prices.sort_values("timestamp").reset_index(drop=True)
    lookup = {ts: i for i, ts in enumerate(p["timestamp"])}
    by_ts = p.set_index("timestamp", drop=False)
    horizons = (cfg.primary_horizon_minutes,) + tuple(cfg.secondary_horizons_minutes)
    rows: list[dict] = []

    for _, e in events.iterrows():
        decision = e["timestamp"]
        if decision not in lookup:
            continue
        pos = lookup[decision]
        if pos + 1 >= len(p):
            continue
        entry = p.iloc[pos + 1]
        if entry["session"] != e["session"]:
            continue
        item = e.to_dict()
        item["entry_timestamp"] = entry["timestamp"]
        item["entry_open"] = float(entry["open"])
        primary_ok = True
        for h in horizons:
            exit_ts = decision + pd.Timedelta(minutes=int(h))
            if exit_ts not in by_ts.index or by_ts.loc[exit_ts]["session"] != e["session"]:
                if h == cfg.primary_horizon_minutes:
                    primary_ok = False
                item[f"raw_{h}m_bps"] = np.nan
                item[f"signed_{h}m_gross_bps"] = np.nan
                item[f"signed_{h}m_net_bps"] = np.nan
                continue
            exit_close = float(by_ts.loc[exit_ts]["close"])
            raw_bps = float(np.log(exit_close / float(entry["open"])) * 10000.0)
            gross = float(int(e["signal"]) * raw_bps)
            item[f"raw_{h}m_bps"] = raw_bps
            item[f"signed_{h}m_gross_bps"] = gross
            item[f"signed_{h}m_net_bps"] = gross - cfg.round_trip_cost_bps
        if primary_ok:
            approach = float(e["approach_momentum_atr"]) if pd.notna(e["approach_momentum_atr"]) else 0.0
            momentum_signal = int(np.sign(approach))
            raw_primary = item[f"raw_{cfg.primary_horizon_minutes}m_bps"]
            item["momentum_baseline_net_bps"] = momentum_signal * raw_primary - cfg.round_trip_cost_bps
            rows.append(item)
    return pd.DataFrame(rows)


def attach_shifted_control(
    events: pd.DataFrame,
    prices: pd.DataFrame,
    cfg: RPPV2Config = RPPV2Config(),
) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    p = prices.sort_values("timestamp").reset_index(drop=True)
    lookup = {ts: i for i, ts in enumerate(p["timestamp"])}
    by_ts = p.set_index("timestamp", drop=False)
    rows: list[dict] = []
    for _, e in events.iterrows():
        item = e.to_dict()
        shifted_decision = e["timestamp"] + pd.Timedelta(minutes=cfg.negative_control_shift_minutes)
        item["shifted_control_decision_timestamp"] = shifted_decision
        item["shifted_control_net_bps"] = np.nan
        if shifted_decision in lookup:
            pos = lookup[shifted_decision]
            if pos + 1 < len(p):
                entry = p.iloc[pos + 1]
                exit_ts = shifted_decision + pd.Timedelta(minutes=cfg.primary_horizon_minutes)
                if (
                    entry["session"] == e["session"]
                    and exit_ts in by_ts.index
                    and by_ts.loc[exit_ts]["session"] == e["session"]
                ):
                    raw = float(np.log(float(by_ts.loc[exit_ts]["close"]) / float(entry["open"])) * 10000.0)
                    item["shifted_control_net_bps"] = int(e["signal"]) * raw - cfg.round_trip_cost_bps
        rows.append(item)
    return pd.DataFrame(rows)


def _session_bootstrap_ci(events: pd.DataFrame, metric: str, cfg: RPPV2Config) -> tuple[float, float]:
    if events.empty:
        return (np.nan, np.nan)
    means = events.groupby("session")[metric].mean().dropna().to_numpy(float)
    if len(means) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(cfg.bootstrap_seed)
    samples = rng.choice(means, size=(cfg.bootstrap_repetitions, len(means)), replace=True).mean(axis=1)
    lo, hi = np.quantile(samples, [0.025, 0.975])
    return float(lo), float(hi)


def evaluate_fixed_state_machine(
    outcomes: pd.DataFrame,
    usable_sessions: list,
    cfg: RPPV2Config = RPPV2Config(),
) -> dict:
    """Evaluate one frozen state machine. There is no train-time threshold search."""
    metric = f"signed_{cfg.primary_horizon_minutes}m_net_bps"
    gross_metric = f"signed_{cfg.primary_horizon_minutes}m_gross_bps"
    folds: list[dict] = []
    oos_parts: list[pd.DataFrame] = []

    start = cfg.warmup_sessions
    fold_id = 0
    while start + cfg.test_sessions <= len(usable_sessions):
        test = set(usable_sessions[start : start + cfg.test_sessions])
        part = outcomes[outcomes["session"].isin(test)].copy() if not outcomes.empty else pd.DataFrame()
        if not part.empty:
            part["fold_id"] = fold_id
            oos_parts.append(part)
        folds.append(
            {
                "fold_id": fold_id,
                "test_start": str(usable_sessions[start]),
                "test_end": str(usable_sessions[start + cfg.test_sessions - 1]),
                "events": int(len(part)),
                "sessions_with_events": int(part["session"].nunique()) if not part.empty else 0,
                "mean_net_bps": float(part[metric].mean()) if not part.empty else None,
                "gross_hit_rate": float((part[gross_metric] > 0).mean()) if not part.empty else None,
            }
        )
        fold_id += 1
        start += cfg.step_sessions

    oos = pd.concat(oos_parts, ignore_index=True) if oos_parts else pd.DataFrame()
    if oos.empty:
        return {
            "verdict": "NO_OOS_EVENTS",
            "blockers": ["NO_OOS_EVENTS"],
            "folds": folds,
        }

    ci_low, ci_high = _session_bootstrap_ci(oos, metric, cfg)
    fold_means = oos.groupby("fold_id")[metric].mean()
    positive_fold_fraction = float((fold_means > 0).mean()) if len(fold_means) else 0.0
    positive_pnl = oos.groupby("fold_id")[metric].sum().clip(lower=0)
    positive_total = float(positive_pnl.sum())
    max_profit_share = float(positive_pnl.max() / positive_total) if positive_total > 0 else 1.0
    mean_net = float(oos[metric].mean())
    mean_gross = float(oos[gross_metric].mean())
    hit_rate = float((oos[gross_metric] > 0).mean())
    baseline = float(oos["momentum_baseline_net_bps"].mean())
    incremental = mean_net - baseline
    shifted = oos["shifted_control_net_bps"].dropna()
    shifted_n = int(len(shifted))
    shifted_mean = float(shifted.mean()) if shifted_n else np.nan
    incremental_shift = mean_net - shifted_mean if np.isfinite(shifted_mean) else np.nan

    blockers: list[str] = []
    if len(fold_means) < cfg.min_oos_folds:
        blockers.append("INSUFFICIENT_OOS_FOLDS")
    if len(oos) < cfg.min_oos_events:
        blockers.append("INSUFFICIENT_OOS_EVENTS")
    if oos["session"].nunique() < cfg.min_oos_sessions:
        blockers.append("INSUFFICIENT_OOS_SESSIONS")
    if not np.isfinite(ci_low) or ci_low <= 0:
        blockers.append("SESSION_BOOTSTRAP_CI_NOT_POSITIVE")
    if positive_fold_fraction < cfg.min_positive_fold_fraction:
        blockers.append("FOLD_STABILITY_FAIL")
    if hit_rate < cfg.min_hit_rate:
        blockers.append("HIT_RATE_FAIL")
    if incremental < cfg.min_incremental_bps_vs_momentum:
        blockers.append("NO_INCREMENTAL_VALUE_VS_MOMENTUM")
    if shifted_n < cfg.min_shifted_control_events:
        blockers.append("INSUFFICIENT_SHIFTED_CONTROL_EVENTS")
    elif not np.isfinite(incremental_shift) or incremental_shift < cfg.min_incremental_bps_vs_shifted_control:
        blockers.append("NO_INCREMENTAL_VALUE_VS_SHIFTED_TIME_CONTROL")
    if max_profit_share > cfg.max_single_fold_positive_profit_share:
        blockers.append("FOLD_PROFIT_CONCENTRATION_FAIL")
    if mean_net <= 0:
        blockers.append("MEAN_AFTER_COST_PROXY_NOT_POSITIVE")

    by_state = {}
    for state, g in oos.groupby("event_type"):
        by_state[str(state)] = {
            "events": int(len(g)),
            "sessions": int(g["session"].nunique()),
            "mean_gross_bps": float(g[gross_metric].mean()),
            "mean_net_bps": float(g[metric].mean()),
            "gross_hit_rate": float((g[gross_metric] > 0).mean()),
            "mean_density": float(g["interaction_density"].mean()),
        }

    return {
        "verdict": "ROBUST_DIRECTIONAL_EDGE_AFTER_COST_PROXY" if not blockers else "NO_ROBUST_AFTER_COST_DIRECTIONAL_EDGE",
        "blockers": blockers,
        "oos_folds": int(len(fold_means)),
        "oos_events": int(len(oos)),
        "oos_sessions": int(oos["session"].nunique()),
        "mean_gross_bps": mean_gross,
        "mean_net_bps": mean_net,
        "gross_hit_rate": hit_rate,
        "session_bootstrap_95_ci_net_bps": [ci_low, ci_high],
        "positive_fold_fraction": positive_fold_fraction,
        "max_single_fold_positive_profit_share": max_profit_share,
        "momentum_baseline_mean_net_bps": baseline,
        "incremental_bps_vs_momentum": incremental,
        "shifted_control_events": shifted_n,
        "shifted_control_mean_net_bps": None if not np.isfinite(shifted_mean) else shifted_mean,
        "incremental_bps_vs_shifted_control": None if not np.isfinite(incremental_shift) else incremental_shift,
        "event_type_diagnostics": by_state,
        "folds": folds,
    }


def run_experiment(
    input_path: str | Path,
    output_dir: str | Path,
    cfg: RPPV2Config = RPPV2Config(),
) -> dict:
    prices_all = load_nifty_ohlc(input_path)
    sessions_all = sorted(prices_all["session"].unique())
    if len(sessions_all) <= cfg.reserve_tail_sessions + cfg.warmup_sessions + cfg.test_sessions:
        report = {
            "campaign_id": CAMPAIGN_ID,
            "spec_version": SPEC_VERSION,
            "config_sha256": cfg.digest(),
            "verdict": "INSUFFICIENT_SESSIONS_FOR_FROZEN_EVALUATION",
            "session_count": len(sessions_all),
            "holdout_evaluated": False,
            "option_pnl_claimed": False,
            "live_or_broker_authority": False,
        }
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        (Path(output_dir) / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return report

    # Seal the final tail BEFORE building pivots/features/outcomes. No values in
    # those sessions are passed into the location map or evaluation engine.
    usable_sessions = sessions_all[: -cfg.reserve_tail_sessions]
    sealed_sessions = sessions_all[-cfg.reserve_tail_sessions :]
    prices = prices_all[prices_all["session"].isin(set(usable_sessions))].copy().reset_index(drop=True)

    location = build_causal_location_map(prices, cfg)
    states = label_zone_interactions(location, cfg)
    events = build_confirmed_events(states, cfg)
    outcomes = attach_forward_outcomes(events, prices, cfg)
    outcomes = attach_shifted_control(outcomes, prices, cfg)
    evaluation = evaluate_fixed_state_machine(outcomes, usable_sessions, cfg)

    report = {
        "campaign_id": CAMPAIGN_ID,
        "spec_version": SPEC_VERSION,
        "config_sha256": cfg.digest(),
        "input_path": str(Path(input_path)),
        "input_sha256": sha256_path(input_path),
        "all_sessions_count": int(len(sessions_all)),
        "usable_sessions_count": int(len(usable_sessions)),
        "sealed_tail_sessions_count": int(len(sealed_sessions)),
        "sealed_tail_start": str(sealed_sessions[0]),
        "sealed_tail_end": str(sealed_sessions[-1]),
        "sealed_tail_feature_rows_processed": 0,
        "sealed_tail_outcomes_processed": 0,
        "price_rows_used": int(len(prices)),
        "location_rows": int(len(location)),
        "state_rows": int(len(states)),
        "confirmed_events": int(len(events)),
        "outcomes": int(len(outcomes)),
        "relative_density_is_calibrated_probability": False,
        "same_bar_zone_reselection_allowed": False,
        "first_break_is_trade_confirmation": False,
        "holdout_evaluated": False,
        "option_pnl_claimed": False,
        "live_or_broker_authority": False,
        **evaluation,
    }

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    states.to_csv(out / "zone_interaction_states.csv", index=False)
    outcomes.to_csv(out / "confirmed_event_outcomes.csv", index=False)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return report
