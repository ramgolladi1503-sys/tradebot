#!/usr/bin/env python3
"""
Inverse-reconstruct the public Reddit/FYERS NIFTY entry rule from 187 labelled trades.

Research-only. No broker connectivity, no order code, no live authority.

Method:
- Download a public NIFTY 50 5-minute OHLC file.
- Treat each FYERS ENTRY timestamp minus one minute as the signal-bar timestamp.
- Exclude Tuesdays, consistent with the observed 187-trade ledger.
- Search a deliberately small, predeclared family around the author's "ATR + ADX is close" clue:
    trend strength: ADX, absolute DMI gap, dominant DI
    volatility: ATR%, true-range%, ATR expansion ratio
    periods: 7, 10, 14, 20, 21
    condition: state or fresh-cross
- Fit thresholds ONLY on the early training period.
- Freeze the best training candidates and evaluate on later unseen dates.
- Include eligible no-trade days, so a rule cannot score well by firing every day.
"""

from __future__ import annotations
import json, math, urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research" / "evidence" / "reddit_fyers_inverse_v1"
OUT.mkdir(parents=True, exist_ok=True)
LABELS = ROOT / "research" / "external" / "reddit_fyers" / "public_fyers_labels_v1.csv"
DATA_URL = "https://raw.githubusercontent.com/Aerysaint/TradingStrategyBacktester/main/datasets/NIFTY%2050_5minute.csv"
DATA_SHA = "46574eaa9e4b3f758a082b766d68f1e23c5b3fb3"
LOCAL_DATA = OUT / "NIFTY_50_5minute_public.csv"
TRAIN_END = pd.Timestamp("2026-01-30")
PERIODS = [7, 10, 14, 20, 21]
QS = [0.40, 0.50, 0.60, 0.70, 0.80]
STRENGTH_METRICS = ["adx", "di_gap", "di_dom"]
VOL_METRICS = ["atr_pct", "tr_pct", "atr_ratio"]
MODES = ["state", "fresh_cross"]
WINDOW_START = "10:55:00"
WINDOW_END = "15:05:00"
RANDOM_SEED = 731921
PERMUTATIONS = 1000

def download():
    if LOCAL_DATA.exists() and LOCAL_DATA.stat().st_size > 1_000_000:
        return
    req = urllib.request.Request(DATA_URL, headers={"User-Agent":"tradebot-research/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        LOCAL_DATA.write_bytes(r.read())

def wilder(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(alpha=1/n, adjust=False, min_periods=n).mean()

def add_dmi(df: pd.DataFrame, n: int) -> pd.DataFrame:
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([(h-l), (h-prev_c).abs(), (l-prev_c).abs()], axis=1).max(axis=1)
    up = h.diff()
    down = -l.diff()
    pdm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    mdm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    atr = wilder(tr, n)
    pdi = 100 * wilder(pdm, n) / atr.replace(0, np.nan)
    mdi = 100 * wilder(mdm, n) / atr.replace(0, np.nan)
    dx = 100 * (pdi-mdi).abs() / (pdi+mdi).replace(0, np.nan)
    adx = wilder(dx, n)
    out = pd.DataFrame(index=df.index)
    out[f"tr_{n}"] = tr
    out[f"atr_{n}"] = atr
    out[f"pdi_{n}"] = pdi
    out[f"mdi_{n}"] = mdi
    out[f"adx_{n}"] = adx
    out[f"di_gap_{n}"] = (pdi-mdi).abs()
    out[f"di_dom_{n}"] = pd.concat([pdi, mdi], axis=1).max(axis=1)
    out[f"dir_{n}"] = np.where(pdi >= mdi, "CE", "PE")
    out[f"atr_pct_{n}"] = atr / c
    out[f"tr_pct_{n}"] = tr / c
    out[f"atr_ratio_{n}"] = atr / atr.rolling(max(20, n*2), min_periods=max(10, n)).median()
    return out

def metric_series(feat: pd.DataFrame, metric: str, n: int) -> pd.Series:
    return feat[f"{metric}_{n}"]

def metrics_from_predictions(days, labels_day, pred):
    tp=fp=fn=tn=0
    direction_hits=[]; exact=[]; near5=[]; near10=[]; abs_err=[]; rows=[]
    for d in days:
        obs = labels_day.get(d); p = pred.get(d)
        if obs is not None and p is not None:
            tp += 1
            obs_dt, obs_dir = obs; p_dt, p_dir = p
            delta = abs((p_dt-obs_dt).total_seconds()/60)
            abs_err.append(delta); direction_hits.append(int(p_dir==obs_dir))
            exact.append(int(delta==0)); near5.append(int(delta<=5)); near10.append(int(delta<=10))
            rows.append((d, obs_dt, obs_dir, p_dt, p_dir, delta))
        elif obs is not None: fn += 1
        elif p is not None: fp += 1
        else: tn += 1
    precision = tp/(tp+fp) if tp+fp else 0.0
    recall = tp/(tp+fn) if tp+fn else 0.0
    f1 = 2*precision*recall/(precision+recall) if precision+recall else 0.0
    specificity = tn/(tn+fp) if tn+fp else 0.0
    dacc = float(np.mean(direction_hits)) if direction_hits else 0.0
    ex = float(np.mean(exact)) if exact else 0.0
    n5 = float(np.mean(near5)) if near5 else 0.0
    n10 = float(np.mean(near10)) if near10 else 0.0
    med = float(np.median(abs_err)) if abs_err else math.inf
    score = .25*f1 + .20*specificity + .20*dacc + .20*ex + .15*n5
    return {"eligible_days":len(days),"observed_trade_days":sum(labels_day.get(d) is not None for d in days),
            "tp":tp,"fp":fp,"fn":fn,"tn":tn,"precision":precision,"recall":recall,"f1":f1,
            "specificity":specificity,"direction_accuracy":dacc,"exact_time_rate":ex,
            "within_5m_rate":n5,"within_10m_rate":n10,"median_abs_timing_error_min":med,"score":score}, rows

def predictions_for(mask: pd.Series, feat: pd.DataFrame, n: int):
    x = feat.loc[mask, ["date","datetime",f"dir_{n}"]].copy()
    if x.empty: return {}
    first = x.sort_values("datetime").groupby("date", sort=False).first().reset_index()
    return {r["date"]:(r["datetime"],r[f"dir_{n}"]) for _,r in first.iterrows()}

def main():
    download()
    raw = pd.read_csv(LOCAL_DATA)
    raw["datetime"] = pd.to_datetime(raw["date"])
    raw["date"] = raw["datetime"].dt.date
    for c in ["open","high","low","close"]: raw[c] = pd.to_numeric(raw[c], errors="coerce")
    raw = raw.dropna(subset=["datetime","open","high","low","close"]).sort_values("datetime").reset_index(drop=True)
    raw["time"] = raw["datetime"].dt.strftime("%H:%M:%S")

    lab = pd.read_csv(LABELS)
    lab["entry_dt"] = pd.to_datetime(lab["entry_dt"]); lab["signal_dt"] = pd.to_datetime(lab["signal_dt"])
    lab["date"] = lab["signal_dt"].dt.date
    overlap_start = max(raw["datetime"].min().normalize(), lab["signal_dt"].min().normalize())
    overlap_end = min(raw["datetime"].max().normalize(), lab["signal_dt"].max().normalize())
    raw = raw[(raw["datetime"] >= overlap_start) & (raw["datetime"] < overlap_end + pd.Timedelta(days=1))].copy()
    lab = lab[(lab["signal_dt"] >= overlap_start) & (lab["signal_dt"] < overlap_end + pd.Timedelta(days=1))].copy()

    eligible_days = sorted(d for d in raw["date"].unique() if pd.Timestamp(d).weekday() != 1)
    labels_day = {r["date"]:(r["signal_dt"], r["direction"]) for _,r in lab.iterrows() if r["date"] in eligible_days}
    train_days = [d for d in eligible_days if pd.Timestamp(d) <= TRAIN_END]
    test_days = [d for d in eligible_days if pd.Timestamp(d) > TRAIN_END]
    in_window = (raw["time"] >= WINDOW_START) & (raw["time"] <= WINDOW_END)
    train_rows = raw["date"].isin(train_days) & in_window

    feature_blocks=[]
    for n in PERIODS:
        b=add_dmi(raw,n); b["date"]=raw["date"].values; b["datetime"]=raw["datetime"].values; b["time"]=raw["time"].values
        feature_blocks.append((n,b))

    results=[]
    for n, feat in feature_blocks:
        for sm in STRENGTH_METRICS:
            s=metric_series(feat,sm,n)
            for vm in VOL_METRICS:
                v=metric_series(feat,vm,n)
                valid_train=train_rows & s.notna() & v.notna()
                if valid_train.sum()<100: continue
                svals=s[valid_train]; vvals=v[valid_train]
                for sq in QS:
                    sth=float(svals.quantile(sq))
                    for vq in QS:
                        vth=float(vvals.quantile(vq))
                        state=(in_window & s.notna() & v.notna() & (s>=sth) & (v>=vth))
                        for mode in MODES:
                            trig=state if mode=="state" else state & ~state.groupby(raw["date"]).shift(1, fill_value=False)
                            pred=predictions_for(trig,feat,n)
                            trm,_=metrics_from_predictions(train_days,labels_day,pred)
                            results.append({"period":n,"strength_metric":sm,"vol_metric":vm,"strength_q":sq,"vol_q":vq,
                                "strength_threshold":sth,"vol_threshold":vth,"mode":mode,
                                **{f"train_{k}":val for k,val in trm.items()}})
    res=pd.DataFrame(results).sort_values(["train_score","train_exact_time_rate","train_f1"],ascending=False).reset_index(drop=True)
    res.to_csv(OUT/"candidate_train_matrix.csv",index=False)

    top=res.head(100).copy(); test_rows=[]; detailed_best=None
    blocks=dict(feature_blocks)
    for rank,r in top.iterrows():
        n=int(r.period); feat=blocks[n]
        s=metric_series(feat,r.strength_metric,n); v=metric_series(feat,r.vol_metric,n)
        state=(in_window & s.notna() & v.notna() & (s>=r.strength_threshold) & (v>=r.vol_threshold))
        trig=state if r.mode=="state" else state & ~state.groupby(raw["date"]).shift(1, fill_value=False)
        pred=predictions_for(trig,feat,n)
        tm, rows=metrics_from_predictions(test_days,labels_day,pred); allm, allrows=metrics_from_predictions(eligible_days,labels_day,pred)
        row=r.to_dict(); row["train_rank"]=rank+1
        row.update({f"test_{k}":val for k,val in tm.items()}); row.update({f"all_{k}":val for k,val in allm.items()})
        test_rows.append(row)
        if rank==0: detailed_best=(pred,rows,allrows)
    test=pd.DataFrame(test_rows); test.to_csv(OUT/"top100_frozen_test_results.csv",index=False)
    best=test.iloc[0].to_dict(); pred,_,_=detailed_best

    daily=[]
    for d in eligible_days:
        obs=labels_day.get(d); p=pred.get(d)
        daily.append({"date":str(d),"observed_trade":obs is not None,
            "observed_signal_dt":obs[0].isoformat(sep=" ") if obs else "","observed_direction":obs[1] if obs else "",
            "predicted_trade":p is not None,"predicted_signal_dt":p[0].isoformat(sep=" ") if p else "",
            "predicted_direction":p[1] if p else "","timing_error_min":abs((p[0]-obs[0]).total_seconds()/60) if p and obs else np.nan,
            "direction_match":bool(p[1]==obs[1]) if p and obs else False,"split":"TRAIN" if pd.Timestamp(d)<=TRAIN_END else "TEST"})
    pd.DataFrame(daily).to_csv(OUT/"selected_candidate_daily_alignment.csv",index=False)

    fam=test.sort_values(["train_score","train_exact_time_rate"],ascending=False).groupby(["strength_metric","vol_metric","mode"],as_index=False).first()
    fam=fam.sort_values("train_score",ascending=False); fam.to_csv(OUT/"family_best_frozen_results.csv",index=False)

    rng=np.random.default_rng(RANDOM_SEED); actual=float(best["test_score"])
    obs_test=[d for d in test_days if labels_day.get(d) is not None]; obs_records=[labels_day[d] for d in obs_test]
    perm_scores=[]
    if obs_records and len(test_days)>=len(obs_records):
        for _ in range(PERMUTATIONS):
            chosen=rng.choice(len(test_days),size=len(obs_records),replace=False); perm_days=[test_days[i] for i in chosen]
            order=rng.permutation(len(obs_records)); perm_labels={d:obs_records[i] for d,i in zip(perm_days,order)}
            pm,_=metrics_from_predictions(test_days,perm_labels,pred); perm_scores.append(pm["score"])
    perm_p=(1+sum(x>=actual for x in perm_scores))/(1+len(perm_scores)) if perm_scores else np.nan

    summary={"data_url":DATA_URL,"data_blob_sha":DATA_SHA,"data_start":str(raw.datetime.min()),"data_end":str(raw.datetime.max()),
        "overlap_start":str(overlap_start.date()),"overlap_end":str(overlap_end.date()),"eligible_days":len(eligible_days),
        "observed_trade_days_in_overlap":len(labels_day),"train_end":str(TRAIN_END.date()),"train_days":len(train_days),"test_days":len(test_days),
        "train_observed_trades":sum(labels_day.get(d) is not None for d in train_days),"test_observed_trades":sum(labels_day.get(d) is not None for d in test_days),
        "candidate_count":int(len(res)),"selected_candidate":best,"test_permutation_count":len(perm_scores),
        "test_permutation_p_ge_score":float(perm_p) if not pd.isna(perm_p) else None}
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2,default=str))

    def pct(x): return f"{100*float(x):.1f}%"
    verdict="NOT_RECONSTRUCTED"
    if best["test_exact_time_rate"]>=.50 and best["test_direction_accuracy"]>=.75 and best["test_f1"]>=.70: verdict="STRONG_RECONSTRUCTION_CANDIDATE"
    elif best["test_within_5m_rate"]>=.50 and best["test_direction_accuracy"]>=.65 and best["test_f1"]>=.60: verdict="PARTIAL_RECONSTRUCTION_CANDIDATE"
    lines=["# Reddit/FYERS inverse reconstruction V1","",f"**Verdict: `{verdict}`**","","## Data",
        f"- Public NIFTY 50 5-minute OHLC: `{DATA_URL}`",f"- Git blob SHA: `{DATA_SHA}`",f"- Overlap: {overlap_start.date()} through {overlap_end.date()}",
        f"- Eligible non-Tuesday sessions: {len(eligible_days)}",f"- Observed FYERS trade days in overlap: {len(labels_day)}",f"- Train cutoff: {TRAIN_END.date()} (frozen before test scoring)","",
        "## Selected candidate (chosen on train only)",f"- period: {int(best['period'])}",f"- trend strength: {best['strength_metric']} at train quantile {best['strength_q']}",
        f"- volatility: {best['vol_metric']} at train quantile {best['vol_q']}",f"- condition mode: {best['mode']}",f"- frozen strength threshold: {best['strength_threshold']:.8g}",
        f"- frozen volatility threshold: {best['vol_threshold']:.8g}","","### Train",f"- F1 trade/no-trade: {pct(best['train_f1'])}",
        f"- specificity on no-trade days: {pct(best['train_specificity'])}",f"- direction accuracy: {pct(best['train_direction_accuracy'])}",
        f"- exact timestamp rate: {pct(best['train_exact_time_rate'])}",f"- within ±5m: {pct(best['train_within_5m_rate'])}",f"- median timing error: {best['train_median_abs_timing_error_min']:.1f} min","",
        "### Unseen test",f"- F1 trade/no-trade: {pct(best['test_f1'])}",f"- specificity on no-trade days: {pct(best['test_specificity'])}",
        f"- direction accuracy: {pct(best['test_direction_accuracy'])}",f"- exact timestamp rate: {pct(best['test_exact_time_rate'])}",
        f"- within ±5m: {pct(best['test_within_5m_rate'])}",f"- within ±10m: {pct(best['test_within_10m_rate'])}",
        f"- median timing error: {best['test_median_abs_timing_error_min']:.1f} min",
        f"- permutation p(score >= observed): {perm_p:.4f}" if not pd.isna(perm_p) else "- permutation test unavailable","",
        "## Interpretation","A high P&L in the author's ledger is not enough. The hidden rule is considered reconstructed only if",
        "the same two-indicator family reproduces trade/no-trade days, CE/PE direction, and entry timing on unseen dates.",
        "The test period was not used to choose the candidate or thresholds.","","See `family_best_frozen_results.csv`, `top100_frozen_test_results.csv`, and",
        "`selected_candidate_daily_alignment.csv` for the full evidence."]
    (OUT/"REPORT.md").write_text("\n".join(lines)+"\n"); print("\n".join(lines))

if __name__=="__main__": main()
