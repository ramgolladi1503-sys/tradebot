#!/usr/bin/env python3
"""Research-only V5: falsify simple underlying-volatility gates for the public FYERS reconstruction.

Starting point frozen from V4.1:
- public NIFTY 5-minute bars are bar-start stamped;
- entry target bar = FYERS order timestamp - 6 minutes;
- core timing candidate = first DX(14) cross above 25 in the post-10:50 window;
- Tuesday excluded.

This script does NOT search option P&L and does NOT grant live authority.
It asks a narrower question: can a single fixed monotone state/cross gate on standard
UNDERLYING volatility measures explain the seven frozen no-trade sessions and the
2026-04-06 delayed entry while preserving all development targets?
"""
from __future__ import annotations

import urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research" / "evidence" / "reddit_fyers_volatility_v5"
OUT.mkdir(parents=True, exist_ok=True)
LABELS = ROOT / "research" / "external" / "reddit_fyers" / "public_fyers_labels_v1.csv"
SPOT = OUT / "NIFTY_50_5minute_public.csv"
URL = "https://raw.githubusercontent.com/Aerysaint/TradingStrategyBacktester/main/datasets/NIFTY%2050_5minute.csv"
TRAIN_END = pd.Timestamp("2026-01-30 23:59:59")
DX_THR = 25.0
WINDOW_START = "10:50"
WINDOW_END = "15:00"


def download() -> None:
    if not SPOT.exists():
        req = urllib.request.Request(URL, headers={"User-Agent": "tradebot-research/1.0"})
        with urllib.request.urlopen(req, timeout=180) as r:
            SPOT.write_bytes(r.read())


def prep() -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    download()
    s = pd.read_csv(SPOT)
    s["dt"] = pd.to_datetime(s["date"])
    s = s.sort_values("dt").reset_index(drop=True)
    s["day"] = s.dt.dt.date
    s = s[(s.dt.dt.strftime("%H:%M") >= "09:15") & (s.dt.dt.strftime("%H:%M") <= "15:30")].copy()

    pc = s.close.shift(1)
    tr = pd.concat([(s.high - s.low), (s.high - pc).abs(), (s.low - pc).abs()], axis=1).max(axis=1)
    ret = s.close.pct_change()

    up = s.high.diff()
    down = -s.low.diff()
    n = 14
    atr14 = tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    pdm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=s.index)
    mdm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=s.index)
    pdi = 100 * pdm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr14
    mdi = 100 * mdm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr14
    s["dx14"] = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)

    metrics: list[str] = []
    for p in [5, 7, 10, 14, 20, 21]:
        atr = tr.ewm(alpha=1 / p, adjust=False, min_periods=p).mean()
        s[f"atr_{p}"] = atr
        s[f"atrp_{p}"] = atr / s.close
        s[f"std_{p}"] = ret.rolling(p).std()
        metrics += [f"atr_{p}", f"atrp_{p}", f"std_{p}"]
    for p in [10, 14, 20]:
        mid = s.close.rolling(p).mean()
        sd = s.close.rolling(p).std()
        s[f"bbw_{p}"] = 4 * sd / mid
        metrics.append(f"bbw_{p}")
    s["tr"] = tr
    s["trp"] = tr / s.close
    metrics += ["tr", "trp"]

    lab = pd.read_csv(LABELS)
    lab["entry_dt"] = pd.to_datetime(lab.entry_dt)
    lab["target_dt"] = lab.entry_dt - pd.Timedelta(minutes=6)
    lab["day"] = lab.target_dt.dt.date
    return s, lab, metrics


def core_predictions(s: pd.DataFrame) -> dict:
    pred: dict = {}
    for d, g0 in s.groupby("day"):
        wd = pd.Timestamp(d).weekday()
        if wd >= 5 or wd == 1:
            continue
        g0 = g0.reset_index(drop=True)
        mask = (g0.dt.dt.strftime("%H:%M") >= WINDOW_START) & (g0.dt.dt.strftime("%H:%M") <= WINDOW_END)
        idxs = np.flatnonzero(mask.to_numpy())
        if not len(idxs):
            continue
        for j in idxs:
            if j == 0:
                continue
            cur = g0.iloc[j]
            prev = g0.iloc[j - 1]
            if pd.notna(cur.dx14) and pd.notna(prev.dx14) and prev.dx14 < DX_THR <= cur.dx14:
                pred[d] = pd.Timestamp(cur.dt)
                break
    return pred


def build_session_table(s: pd.DataFrame, lab: pd.DataFrame, pred: dict) -> pd.DataFrame:
    obs = {r.day: r for r in lab.itertuples() if r.target_dt <= s.dt.max()}
    days = sorted(
        d for d in s.day.unique()
        if min(obs) <= d <= max(obs)
        and pd.Timestamp(d).weekday() < 5
        and pd.Timestamp(d).weekday() != 1
    )
    rows = []
    for d in days:
        o = obs.get(d)
        p = pred.get(d)
        rows.append({
            "day": d,
            "has_trade": o is not None,
            "obs_dt": o.target_dt if o else pd.NaT,
            "has_core_pred": p is not None,
            "core_pred_dt": p if p is not None else pd.NaT,
            "timing_err_min": abs((p - o.target_dt).total_seconds() / 60) if p is not None and o else np.nan,
        })
    return pd.DataFrame(rows)


def monotone_state_separation(s: pd.DataFrame, sess: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    lookup = s.set_index("dt")
    train = sess[pd.to_datetime(sess.day) <= TRAIN_END]
    test = sess[pd.to_datetime(sess.day) > TRAIN_END]
    train_dt = pd.to_datetime(train.loc[train.has_trade, "obs_dt"])
    fp_dt = pd.to_datetime(test.loc[(~test.has_trade) & test.has_core_pred, "core_pred_dt"])

    out = []
    for m in metrics:
        tv = lookup.reindex(train_dt)[m].dropna()
        fv = lookup.reindex(fp_dt)[m].dropna()
        if len(tv) != len(train_dt) or len(fv) != len(fp_dt):
            continue
        tmin, tmax = float(tv.min()), float(tv.max())
        # Any lower-bound gate v >= T preserving every train target must have T <= train_min.
        # Its strongest possible FP rejection occurs at T=train_min.
        lower_elim = int((fv < tmin).sum())
        # Any upper-bound gate v <= T preserving every train target must have T >= train_max.
        # Its strongest possible FP rejection occurs at T=train_max.
        upper_elim = int((fv > tmax).sum())
        out.append({
            "metric": m,
            "train_min": tmin,
            "train_max": tmax,
            "frozen_fp_count": int(len(fv)),
            "best_fp_elimination_lower_gate_preserve_all_train": lower_elim,
            "best_fp_elimination_upper_gate_preserve_all_train": upper_elim,
            "all_fps_eliminated_by_any_monotone_state_gate": bool(lower_elim == len(fv) or upper_elim == len(fv)),
            "fp_min": float(fv.min()),
            "fp_max": float(fv.max()),
        })
    return pd.DataFrame(out)


def fixed_cross_feasibility(s: pd.DataFrame, sess: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    idx = s.set_index("dt")
    train = sess[(pd.to_datetime(sess.day) <= TRAIN_END) & sess.has_trade]
    rows = []
    for m in metrics:
        ups = []
        downs = []
        all_up_direction = True
        all_down_direction = True
        for target in pd.to_datetime(train.obs_dt):
            loc = idx.index.get_loc(target)
            if not isinstance(loc, (int, np.integer)) or loc == 0:
                all_up_direction = all_down_direction = False
                break
            prev = float(idx.iloc[loc - 1][m])
            cur = float(idx.iloc[loc][m])
            if not (np.isfinite(prev) and np.isfinite(cur)):
                all_up_direction = all_down_direction = False
                break
            if prev < cur:
                ups.append((prev, cur))
            else:
                all_up_direction = False
            if cur < prev:
                downs.append((cur, prev))
            else:
                all_down_direction = False

        if all_up_direction and len(ups) == len(train):
            lo, hi = max(a for a, _ in ups), min(b for _, b in ups)
            up_feasible = bool(lo < hi)
        else:
            lo = hi = np.nan
            up_feasible = False
        if all_down_direction and len(downs) == len(train):
            dlo, dhi = max(a for a, _ in downs), min(b for _, b in downs)
            down_feasible = bool(dlo < dhi)
        else:
            dlo = dhi = np.nan
            down_feasible = False
        rows.append({
            "metric": m,
            "fixed_up_cross_all_train_feasible": up_feasible,
            "up_cross_interval_low_exclusive": lo,
            "up_cross_interval_high_inclusive": hi,
            "fixed_down_cross_all_train_feasible": down_feasible,
            "down_cross_interval_low_inclusive": dlo,
            "down_cross_interval_high_exclusive": dhi,
        })
    return pd.DataFrame(rows)


def april6_delay_compatibility(s: pd.DataFrame, sess: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    idx = s.set_index("dt")
    train = sess[(pd.to_datetime(sess.day) <= TRAIN_END) & sess.has_trade]
    train_dts = pd.to_datetime(train.obs_dt)
    row = sess[pd.to_datetime(sess.day) == pd.Timestamp("2026-04-06")].iloc[0]
    arm = pd.Timestamp(row.core_pred_dt)
    target = pd.Timestamp(row.obs_dt)
    path = s[(s.dt >= arm) & (s.dt <= target)].copy()
    out = []
    for m in metrics:
        tv = idx.reindex(train_dts)[m].dropna()
        if len(tv) != len(train_dts):
            continue
        vals = path[m].astype(float).to_numpy()
        if len(vals) < 2 or not np.isfinite(vals).all():
            continue
        before = vals[:-1]
        cur = vals[-1]
        # To make first v>=T pass occur exactly at target: max(before) < T <= cur.
        lower_delay_possible = bool(np.max(before) < cur)
        lower_lo = float(np.max(before)) if lower_delay_possible else np.nan
        lower_hi = float(cur) if lower_delay_possible else np.nan
        # Preserve all train targets too => T <= min(train values).
        lower_joint = bool(lower_delay_possible and lower_lo < min(lower_hi, float(tv.min())))

        # To make first v<=T pass occur exactly at target: cur <= T < min(before).
        upper_delay_possible = bool(cur < np.min(before))
        upper_lo = float(cur) if upper_delay_possible else np.nan
        upper_hi = float(np.min(before)) if upper_delay_possible else np.nan
        # Preserve all train targets too => T >= max(train values).
        upper_joint = bool(upper_delay_possible and max(upper_lo, float(tv.max())) < upper_hi)
        out.append({
            "metric": m,
            "april6_arm_dt": arm,
            "april6_obs_dt": target,
            "april6_value_at_arm": float(vals[0]),
            "april6_value_at_obs": float(cur),
            "lower_gate_delay_to_obs_possible": lower_delay_possible,
            "lower_gate_delay_interval_low_exclusive": lower_lo,
            "lower_gate_delay_interval_high_inclusive": lower_hi,
            "lower_gate_delay_and_preserve_all_train": lower_joint,
            "upper_gate_delay_to_obs_possible": upper_delay_possible,
            "upper_gate_delay_interval_low_inclusive": upper_lo,
            "upper_gate_delay_interval_high_exclusive": upper_hi,
            "upper_gate_delay_and_preserve_all_train": upper_joint,
        })
    return pd.DataFrame(out)


def main() -> None:
    s, lab, metrics = prep()
    pred = core_predictions(s)
    sess = build_session_table(s, lab, pred)
    sess.to_csv(OUT / "core_session_alignment.csv", index=False)

    state = monotone_state_separation(s, sess, metrics)
    state.to_csv(OUT / "monotone_state_gate_falsification.csv", index=False)

    cross = fixed_cross_feasibility(s, sess, metrics)
    cross.to_csv(OUT / "fixed_cross_gate_falsification.csv", index=False)

    apr = april6_delay_compatibility(s, sess, metrics)
    apr.to_csv(OUT / "april6_delay_compatibility.csv", index=False)

    test = sess[pd.to_datetime(sess.day) > TRAIN_END]
    fp = test[(~test.has_trade) & test.has_core_pred]
    mismatch = test[test.has_trade & (test.timing_err_min > 0)]

    any_state_full = bool(state.all_fps_eliminated_by_any_monotone_state_gate.any())
    any_cross = bool(cross.fixed_up_cross_all_train_feasible.any() or cross.fixed_down_cross_all_train_feasible.any())
    any_apr_joint = bool(apr.lower_gate_delay_and_preserve_all_train.any() or apr.upper_gate_delay_and_preserve_all_train.any())

    report = [
        "# Reddit/FYERS volatility gate V5",
        "",
        "## Frozen V4.1 core timing",
        f"- frozen observed trade days: {int(test.has_trade.sum())}",
        f"- frozen core predictions on trade days: {int((test.has_trade & test.has_core_pred).sum())}",
        f"- exact timing: {int((test.has_trade & (test.timing_err_min == 0)).sum())}/{int(test.has_trade.sum())}",
        f"- within 5 minutes: {int((test.has_trade & (test.timing_err_min <= 5)).sum())}/{int(test.has_trade.sum())}",
        f"- false-positive no-trade sessions: {len(fp)}",
        f"- false-positive dates: {', '.join(pd.to_datetime(fp.day).dt.strftime('%Y-%m-%d'))}",
        f"- residual timing mismatch dates: {', '.join(pd.to_datetime(mismatch.day).dt.strftime('%Y-%m-%d'))}",
        "",
        "## Predeclared underlying volatility families",
        "- ATR raw and ATR/price: periods 5, 7, 10, 14, 20, 21",
        "- rolling return standard deviation: periods 5, 7, 10, 14, 20, 21",
        "- Bollinger width: periods 10, 14, 20",
        "- True Range raw and TR/price",
        "",
        "## Monotone fixed state gate test",
        f"- any single lower/upper threshold preserving ALL train targets that eliminates all 7 frozen false positives: {any_state_full}",
        "",
        "## Fixed crossing gate test",
        f"- any volatility metric with one fixed up/down crossing threshold at ALL 77 train targets: {any_cross}",
        "",
        "## 2026-04-06 delay test",
        "- core DX(14)>25 crossing arms before the observed entry; a candidate second gate must delay first qualification to the observed bar.",
        f"- any tested monotone underlying-volatility state gate that both delays to the observed bar AND preserves all train targets: {any_apr_joint}",
        "",
        "## Verdict",
    ]
    if not any_state_full and not any_cross and not any_apr_joint:
        report.append("SIMPLE_UNDERLYING_VOLATILITY_GATE_REJECTED")
        report.append("")
        report.append("The tested standard NIFTY volatility measures cannot, with one fixed monotone state/cross threshold, explain the seven frozen no-trade sessions plus the April-06 delay while preserving every development target. The remaining second condition is therefore more likely to require different semantics (e.g. indicator-vs-indicator crossover, branch-specific logic) or to be evaluated on the option instrument rather than NIFTY spot. This is an inference, not a certification of option-based triggering.")
    else:
        report.append("UNDERLYING_VOLATILITY_GATE_NOT_REJECTED")
        report.append("")
        report.append("At least one simple tested gate remains compatible and requires frozen follow-up testing before moving to option-instrument hypotheses.")

    (OUT / "REPORT.md").write_text("\n".join(report))
    print("\n".join(report))


if __name__ == "__main__":
    main()
