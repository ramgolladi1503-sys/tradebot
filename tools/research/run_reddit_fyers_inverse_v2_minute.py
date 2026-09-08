#!/usr/bin/env python3
"""
Minute-aware inverse reconstruction of the public Reddit/FYERS NIFTY strategy.

Research-only: no broker connectivity, no order placement, no live authority.

Why V2 exists
-------------
Every public FYERS entry in the labelled ledger occurs at minute mod 5 == 1
(e.g. 11:36, 13:21, 11:01). V1 mapped those entries to a completed 5-minute
OHLC row by subtracting one minute. That is not sufficient to distinguish two
plausible FYERS Automate semantics:

1. CLOSED_BAR: at 11:36, evaluate indicators from the last completed 5-minute
   candle (11:30-11:34 when bars are start-labelled).
2. LIVE_PARTIAL: at 11:36, evaluate indicators using the currently forming
   11:35 bucket with 11:35 and 11:36 one-minute data included.

V2 therefore downloads independent public NIFTY 50 one-minute OHLC, reconstructs
both semantics, and freezes thresholds on the early period before scoring the
later period.

The predeclared family follows the author's public clue: one trend-strength
indicator plus one volatility indicator. Trend is Linear Regression Slope;
volatility candidates are ATR, True Range, Standard Deviation, and Bollinger
Band width. Direction is the sign of the regression slope.
"""
from __future__ import annotations

import json
import math
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research" / "evidence" / "reddit_fyers_inverse_v2_minute"
OUT.mkdir(parents=True, exist_ok=True)
LABELS = ROOT / "research" / "external" / "reddit_fyers" / "public_fyers_labels_v1.csv"
DATA_URL = "https://raw.githubusercontent.com/Aerysaint/TradingStrategyBacktester/main/datasets/NIFTY%2050_minute.csv"
LOCAL_DATA = OUT / "NIFTY_50_1minute_public.csv"
TRAIN_END = pd.Timestamp("2026-01-30")
PERIODS = [5, 6, 7, 8, 10, 14]
TREND_PERIODS = [5, 6, 7, 8, 9, 10]
QS = [0.40, 0.50, 0.60, 0.70, 0.80, 0.90]
SEMANTICS = ["CLOSED_BAR", "LIVE_PARTIAL"]
WINDOW_START_MIN = 10 * 60 + 56
WINDOW_END_MIN = 15 * 60 + 6


def download() -> None:
    if LOCAL_DATA.exists() and LOCAL_DATA.stat().st_size > 5_000_000:
        return
    req = urllib.request.Request(DATA_URL, headers={"User-Agent": "tradebot-research/2.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        LOCAL_DATA.write_bytes(r.read())


def linreg_slope(y: np.ndarray) -> float:
    n = len(y)
    x = np.arange(n, dtype=float)
    x0 = x - x.mean()
    den = float(np.dot(x0, x0))
    return float(np.dot(x0, y - y.mean()) / den) if den else np.nan


def true_range(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    out = np.full(len(c), np.nan)
    if len(c) == 0:
        return out
    out[0] = h[0] - l[0]
    if len(c) > 1:
        prev = c[:-1]
        out[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - prev), np.abs(l[1:] - prev)))
    return out


def indicator_snapshot(bars: pd.DataFrame, trend_n: int, vol_n: int, vol_metric: str) -> tuple[float, float]:
    if len(bars) < max(trend_n, vol_n) + 1:
        return np.nan, np.nan
    closes = bars["close"].to_numpy(float)
    slope = linreg_slope(closes[-trend_n:])
    h = bars["high"].to_numpy(float)
    l = bars["low"].to_numpy(float)
    tr = true_range(h, l, closes)
    if vol_metric == "tr":
        vol = float(tr[-1])
    elif vol_metric == "atr":
        vol = float(pd.Series(tr).ewm(alpha=1 / vol_n, adjust=False, min_periods=vol_n).mean().iloc[-1])
    elif vol_metric == "std":
        vol = float(np.std(closes[-vol_n:], ddof=0))
    elif vol_metric == "bbw":
        x = closes[-vol_n:]
        mu = float(np.mean(x))
        vol = float(4 * np.std(x, ddof=0) / mu) if mu else np.nan
    else:
        raise ValueError(vol_metric)
    return slope, vol


def build_completed_5m(day: pd.DataFrame) -> dict[int, pd.DataFrame]:
    """Return completed 5m bars available before each minute-of-day."""
    d = day.copy()
    minute = d["datetime"].dt.hour * 60 + d["datetime"].dt.minute
    bucket = ((minute - 555) // 5).astype(int)
    d["bucket"] = bucket
    grouped = d.groupby("bucket", sort=True).agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")
    )
    return grouped


def snapshot_for_time(day: pd.DataFrame, grouped: pd.DataFrame, minute_of_day: int, semantic: str) -> pd.DataFrame:
    bucket = int((minute_of_day - 555) // 5)
    if semantic == "CLOSED_BAR":
        return grouped[grouped.index < bucket][["open", "high", "low", "close"]].copy()
    # LIVE_PARTIAL: completed earlier buckets + currently forming bucket through this minute.
    prior = grouped[grouped.index < bucket][["open", "high", "low", "close"]].copy()
    m = day["datetime"].dt.hour * 60 + day["datetime"].dt.minute
    cur = day[(m >= 555 + bucket * 5) & (m <= minute_of_day)]
    if cur.empty:
        return prior
    partial = pd.DataFrame([{ "open": float(cur.iloc[0].open), "high": float(cur.high.max()),
                              "low": float(cur.low.min()), "close": float(cur.iloc[-1].close) }], index=[bucket])
    return pd.concat([prior, partial])


def compute_feature_table(raw: pd.DataFrame, eligible_days: list, labels: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for d in eligible_days:
        day = raw[raw["date"] == d].sort_values("datetime").copy()
        if day.empty:
            continue
        grouped = build_completed_5m(day)
        # Public executions only occur at minute mod 5 == 1. Evaluate the same cadence.
        candidate_minutes = sorted(set((day["datetime"].dt.hour * 60 + day["datetime"].dt.minute).tolist()))
        candidate_minutes = [m for m in candidate_minutes if WINDOW_START_MIN <= m <= WINDOW_END_MIN and (m % 5) == 1]
        for semantic in SEMANTICS:
            for m in candidate_minutes:
                snap = snapshot_for_time(day, grouped, m, semantic)
                for tn in TREND_PERIODS:
                    # Vol period/metric are filled in below so trend can be reused.
                    if len(snap) < tn:
                        continue
                    slope = linreg_slope(snap.close.to_numpy(float)[-tn:])
                    base = {"date": d, "minute": m, "semantic": semantic, "trend_n": tn, "slope": slope,
                            "direction": "CE" if slope >= 0 else "PE", "strength": abs(slope)}
                    h = snap.high.to_numpy(float); lo = snap.low.to_numpy(float); cl = snap.close.to_numpy(float)
                    tr = true_range(h, lo, cl)
                    for vn in PERIODS:
                        if len(snap) < vn + 1:
                            continue
                        vals = {
                            "tr": float(tr[-1]),
                            "atr": float(pd.Series(tr).ewm(alpha=1 / vn, adjust=False, min_periods=vn).mean().iloc[-1]),
                            "std": float(np.std(cl[-vn:], ddof=0)),
                            "bbw": float(4 * np.std(cl[-vn:], ddof=0) / np.mean(cl[-vn:])),
                        }
                        for vm, vv in vals.items():
                            r = dict(base); r.update({"vol_n": vn, "vol_metric": vm, "vol": vv}); rows.append(r)
    return pd.DataFrame(rows)


def score_predictions(days, labels_day, preds):
    tp = fp = fn = tn = 0
    exact = []; dmatch = []; errors = []
    for d in days:
        obs = labels_day.get(d)
        p = preds.get(d)
        if obs and p:
            tp += 1
            obs_dt, obs_dir = obs; pred_min, pred_dir = p
            obs_min = obs_dt.hour * 60 + obs_dt.minute
            err = abs(pred_min - obs_min); errors.append(err); exact.append(int(err == 0)); dmatch.append(int(pred_dir == obs_dir))
        elif obs and not p: fn += 1
        elif (not obs) and p: fp += 1
        else: tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    direction = float(np.mean(dmatch)) if dmatch else 0.0
    exact_rate = float(np.mean(exact)) if exact else 0.0
    med = float(np.median(errors)) if errors else math.inf
    # Timing is dominant because V1's main failure was timestamp reconstruction.
    score = 0.45 * exact_rate + 0.20 * direction + 0.15 * f1 + 0.20 * specificity
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": precision, "recall": recall, "f1": f1,
            "specificity": specificity, "direction_accuracy": direction, "exact_time_rate": exact_rate,
            "median_abs_timing_error_min": med, "score": score}


def predict_from_rule(ft: pd.DataFrame, semantic: str, tn: int, vn: int, vm: str, sth: float, vth: float, mode: str):
    x = ft[(ft.semantic == semantic) & (ft.trend_n == tn) & (ft.vol_n == vn) & (ft.vol_metric == vm)].copy()
    x = x.sort_values(["date", "minute"])
    state = x.strength.ge(sth) & x.vol.ge(vth)
    if mode == "cross":
        prev = state.groupby(x.date).shift(1, fill_value=False)
        state = state & ~prev
    x = x[state]
    first = x.groupby("date", sort=False).first().reset_index()
    return {r.date: (int(r.minute), r.direction) for r in first.itertuples(index=False)}


def main():
    download()
    raw = pd.read_csv(LOCAL_DATA)
    raw["datetime"] = pd.to_datetime(raw["date"])
    raw["date"] = raw.datetime.dt.date
    for col in ["open", "high", "low", "close"]:
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    raw = raw.dropna(subset=["datetime", "open", "high", "low", "close"]).sort_values("datetime")
    minute = raw.datetime.dt.hour * 60 + raw.datetime.dt.minute
    raw = raw[(minute >= 555) & (minute <= 929)].copy()

    lab = pd.read_csv(LABELS)
    lab["entry_dt"] = pd.to_datetime(lab.entry_dt)
    lab["date"] = lab.entry_dt.dt.date
    # Cadence forensic: this should be 100% minute-mod-5==1 if labels are intact.
    cadence_rate = float(((lab.entry_dt.dt.minute % 5) == 1).mean())

    overlap_start = max(raw.datetime.min().normalize(), lab.entry_dt.min().normalize())
    overlap_end = min(raw.datetime.max().normalize(), lab.entry_dt.max().normalize())
    raw = raw[(raw.datetime >= overlap_start) & (raw.datetime < overlap_end + pd.Timedelta(days=1))].copy()
    lab = lab[(lab.entry_dt >= overlap_start) & (lab.entry_dt < overlap_end + pd.Timedelta(days=1))].copy()

    eligible_days = sorted(d for d in raw.date.unique() if pd.Timestamp(d).weekday() != 1)
    labels_day = {r.date: (r.entry_dt, r.direction) for r in lab.itertuples(index=False) if r.date in eligible_days}
    train_days = [d for d in eligible_days if pd.Timestamp(d) <= TRAIN_END]
    test_days = [d for d in eligible_days if pd.Timestamp(d) > TRAIN_END]

    ft = compute_feature_table(raw, eligible_days, lab)
    ft.to_parquet(OUT / "minute_semantic_features.parquet", index=False)

    # Direction fingerprint at the actual entry minute, independent of thresholds.
    entry_keys = {(r.date, r.entry_dt.hour * 60 + r.entry_dt.minute): r.direction for r in lab.itertuples(index=False)}
    fp_rows = []
    for semantic in SEMANTICS:
        for tn in TREND_PERIODS:
            z = ft[(ft.semantic == semantic) & (ft.trend_n == tn)].drop_duplicates(["date", "minute"])
            hits = []
            for r in z.itertuples(index=False):
                key = (r.date, int(r.minute))
                if key in entry_keys:
                    hits.append(int(r.direction == entry_keys[key]))
            fp_rows.append({"semantic": semantic, "trend_n": tn, "entry_direction_accuracy": float(np.mean(hits)) if hits else np.nan,
                            "n": len(hits)})
    pd.DataFrame(fp_rows).to_csv(OUT / "direction_fingerprint.csv", index=False)

    # Thresholds are fitted only on TRAIN rows. Keep the family deliberately compact.
    candidates = []
    for semantic in SEMANTICS:
        for tn in TREND_PERIODS:
            for vn in PERIODS:
                for vm in ["atr", "tr", "std", "bbw"]:
                    z = ft[(ft.semantic == semantic) & (ft.trend_n == tn) & (ft.vol_n == vn) & (ft.vol_metric == vm)].copy()
                    tr = z[z.date.isin(train_days)].dropna(subset=["strength", "vol"])
                    if len(tr) < 100:
                        continue
                    svals = tr.strength; vvals = tr.vol
                    for sq in QS:
                        sth = float(svals.quantile(sq))
                        for vq in QS:
                            vth = float(vvals.quantile(vq))
                            for mode in ["state", "cross"]:
                                pred = predict_from_rule(ft, semantic, tn, vn, vm, sth, vth, mode)
                                m = score_predictions(train_days, labels_day, pred)
                                candidates.append({"semantic": semantic, "trend_n": tn, "vol_n": vn, "vol_metric": vm,
                                                   "strength_q": sq, "vol_q": vq, "strength_threshold": sth,
                                                   "vol_threshold": vth, "mode": mode, **{f"train_{k}": v for k, v in m.items()}})
    cand = pd.DataFrame(candidates).sort_values(["train_score", "train_exact_time_rate", "train_direction_accuracy"], ascending=False)
    cand.to_csv(OUT / "candidate_train_matrix.csv", index=False)

    frozen_rows = []
    for semantic in SEMANTICS:
        top = cand[cand.semantic == semantic].head(100)
        for rank, r in enumerate(top.itertuples(index=False), 1):
            pred = predict_from_rule(ft, r.semantic, r.trend_n, r.vol_n, r.vol_metric, r.strength_threshold, r.vol_threshold, r.mode)
            tm = score_predictions(test_days, labels_day, pred)
            row = r._asdict(); row["train_rank_within_semantic"] = rank
            row.update({f"test_{k}": v for k, v in tm.items()}); frozen_rows.append(row)
    frozen = pd.DataFrame(frozen_rows)
    frozen.to_csv(OUT / "top100_frozen_test_results.csv", index=False)

    best_rows = []
    for semantic in SEMANTICS:
        b = frozen[(frozen.semantic == semantic) & (frozen.train_rank_within_semantic == 1)].iloc[0].to_dict()
        best_rows.append(b)
    best_df = pd.DataFrame(best_rows)
    best_df.to_csv(OUT / "semantic_best_frozen_results.csv", index=False)

    lines = [
        "# Reddit/FYERS inverse reconstruction V2 — minute-aware semantics",
        "",
        f"- Public entry cadence minute-mod-5==1: **{cadence_rate:.1%}**",
        f"- Data overlap: **{overlap_start.date()} through {overlap_end.date()}**",
        f"- Eligible non-Tuesday sessions: **{len(eligible_days)}**",
        f"- Labelled trade sessions in overlap: **{sum(d in labels_day for d in eligible_days)}**",
        f"- Frozen train cutoff: **{TRAIN_END.date()}**",
        "",
        "## Frozen semantic comparison",
        "",
    ]
    for b in best_rows:
        lines += [
            f"### {b['semantic']}",
            f"- rule: LRS({int(b['trend_n'])}) strength q={b['strength_q']}, {b['vol_metric']}({int(b['vol_n'])}) q={b['vol_q']}, mode={b['mode']}",
            f"- TRAIN exact={b['train_exact_time_rate']:.1%}, direction={b['train_direction_accuracy']:.1%}, F1={b['train_f1']:.1%}, specificity={b['train_specificity']:.1%}",
            f"- TEST exact={b['test_exact_time_rate']:.1%}, direction={b['test_direction_accuracy']:.1%}, F1={b['test_f1']:.1%}, specificity={b['test_specificity']:.1%}",
            f"- TEST median timing error={b['test_median_abs_timing_error_min']:.1f} min",
            "",
        ]
    # Reconstruction gate is intentionally hard.
    promoted = [b for b in best_rows if b['test_exact_time_rate'] >= 0.50 and b['test_direction_accuracy'] >= 0.85 and b['test_specificity'] >= 0.50]
    verdict = "RECONSTRUCTED_CANDIDATE" if promoted else "NOT_RECONSTRUCTED"
    lines += ["## Verdict", "", f"**`{verdict}`**", "",
              "A candidate is not accepted merely because direction matches. It must reproduce actual entry minute, direction, and no-trade days on unseen sessions."]
    (OUT / "REPORT_V2.md").write_text("\n".join(lines))
    (OUT / "run_manifest.json").write_text(json.dumps({"data_url": DATA_URL, "cadence_rate": cadence_rate,
        "overlap_start": str(overlap_start.date()), "overlap_end": str(overlap_end.date()), "train_end": str(TRAIN_END.date()),
        "verdict": verdict}, indent=2))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
