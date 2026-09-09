#!/usr/bin/env python3
"""Research-only V5.1 frozen follow-up.

V5 showed that no simple monotone underlying-volatility state gate could both preserve all
77 development targets and remove all 7 frozen DX false positives. It did, however, find
six upper-bound ATR-family thresholds that can delay the anomalous 2026-04-06 session to
its observed bar while preserving all development targets. This script freezes those
interval-midpoint thresholds and tests them on the already frozen post-2026-01-30 period.

No P&L optimization. No broker calls. No live authority.
"""
from pathlib import Path
import urllib.request
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'research'/'evidence'/'reddit_fyers_volatility_v5_1'; OUT.mkdir(parents=True,exist_ok=True)
LABELS=ROOT/'research'/'external'/'reddit_fyers'/'public_fyers_labels_v1.csv'
SPOT=OUT/'NIFTY_50_5minute_public.csv'
URL='https://raw.githubusercontent.com/Aerysaint/TradingStrategyBacktester/main/datasets/NIFTY%2050_5minute.csv'
TRAIN_END=pd.Timestamp('2026-01-30 23:59:59')
DX_THR=25.0

CANDIDATES={
 'atr_14':(42.82129984748327+42.87678445113594)/2,
 'atrp_14':(0.0018883641075075086+0.0018914948893664226)/2,
 'atr_20':(44.49163660220157+44.617512212843835)/2,
 'atrp_20':(0.001962023804581043+0.0019682865076558276)/2,
 'atr_21':(44.653001244893744+44.780651307138506)/2,
 'atrp_21':(0.001969139777252727+0.001975483333795295)/2,
}

def prep():
    if not SPOT.exists():
        req=urllib.request.Request(URL,headers={'User-Agent':'tradebot-research/1.0'})
        with urllib.request.urlopen(req,timeout=180) as r: SPOT.write_bytes(r.read())
    s=pd.read_csv(SPOT); s['dt']=pd.to_datetime(s['date']); s=s.sort_values('dt').reset_index(drop=True)
    s['day']=s.dt.dt.date; s['hm']=s.dt.dt.hour*60+s.dt.dt.minute
    s=s[(s.hm>=555)&(s.hm<=930)].copy()
    pc=s.close.shift(1); tr=pd.concat([(s.high-s.low),(s.high-pc).abs(),(s.low-pc).abs()],axis=1).max(axis=1)
    up=s.high.diff(); down=-s.low.diff(); n=14
    atr14=tr.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    pdm=pd.Series(np.where((up>down)&(up>0),up,0.0),index=s.index); mdm=pd.Series(np.where((down>up)&(down>0),down,0.0),index=s.index)
    pdi=100*pdm.ewm(alpha=1/n,adjust=False,min_periods=n).mean()/atr14; mdi=100*mdm.ewm(alpha=1/n,adjust=False,min_periods=n).mean()/atr14
    s['dx14']=100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)
    for p in [14,20,21]:
        atr=tr.ewm(alpha=1/p,adjust=False,min_periods=p).mean(); s[f'atr_{p}']=atr; s[f'atrp_{p}']=atr/s.close
    lab=pd.read_csv(LABELS); lab['entry_dt']=pd.to_datetime(lab.entry_dt); lab['target_dt']=lab.entry_dt-pd.Timedelta(minutes=6); lab['day']=lab.target_dt.dt.date
    return s,lab

def dx_arms(s):
    out={}
    for d,g in s.groupby('day'):
        wd=pd.Timestamp(d).weekday()
        if wd>=5 or wd==1: continue
        g=g.reset_index(drop=True); idxs=np.flatnonzero(((g.hm>=650)&(g.hm<=900)).to_numpy())
        for j in idxs:
            if j==0: continue
            if pd.notna(g.iloc[j].dx14) and pd.notna(g.iloc[j-1].dx14) and g.iloc[j-1].dx14<DX_THR<=g.iloc[j].dx14:
                out[d]=pd.Timestamp(g.iloc[j]['dt']); break
    return out

def sessions(s,lab,arms):
    obs={r.day:r for r in lab.itertuples() if r.target_dt<=s.dt.max()}; days=sorted(d for d in s.day.unique() if min(obs)<=d<=max(obs) and pd.Timestamp(d).weekday()<5 and pd.Timestamp(d).weekday()!=1)
    rows=[]
    for d in days:
        o=obs.get(d); rows.append({'day':d,'has_trade':o is not None,'obs_dt':o.target_dt if o else pd.NaT,'arm_dt':arms.get(d,pd.NaT)})
    return pd.DataFrame(rows)

def evaluate_candidate(s,sess,metric,thr):
    groups={d:g for d,g in s.groupby('day')}; rec=[]
    for r in sess.itertuples(index=False):
        pred=pd.NaT
        if pd.notna(r.arm_dt):
            g=groups[r.day]; hit=g[(g.dt>=r.arm_dt)&(g.hm<=900)&(g[metric]<=thr)]
            if len(hit): pred=pd.Timestamp(hit.iloc[0]['dt'])
        err=abs((pred-r.obs_dt).total_seconds()/60) if r.has_trade and pd.notna(pred) else np.nan
        rec.append({'day':r.day,'has_trade':r.has_trade,'obs_dt':r.obs_dt,'pred_dt':pred,'err_min':err})
    df=pd.DataFrame(rec); test=df[pd.to_datetime(df.day)>TRAIN_END]
    return df,{
      'metric':metric,'threshold':thr,'tp':int((test.has_trade&test.pred_dt.notna()).sum()),'fp':int((~test.has_trade&test.pred_dt.notna()).sum()),'fn':int((test.has_trade&test.pred_dt.isna()).sum()),
      'exact':int((test.has_trade&(test.err_min==0)).sum()),'within5':int((test.has_trade&(test.err_min<=5)).sum()),
      'fp_dates':','.join(pd.to_datetime(test.loc[(~test.has_trade)&test.pred_dt.notna(),'day']).dt.strftime('%Y-%m-%d'))
    }

def main():
    s,lab=prep(); arms=dx_arms(s); sess=sessions(s,lab,arms); summaries=[]
    for m,t in CANDIDATES.items():
        df,sm=evaluate_candidate(s,sess,m,t); summaries.append(sm); df.to_csv(OUT/f'alignment_{m}.csv',index=False)
    summ=pd.DataFrame(summaries); summ.to_csv(OUT/'frozen_candidate_results.csv',index=False)
    core_test=sess[pd.to_datetime(sess.day)>TRAIN_END]; core_tp=int((core_test.has_trade&core_test.arm_dt.notna()).sum()); core_fp=int((~core_test.has_trade&core_test.arm_dt.notna()).sum())
    report=['# Reddit/FYERS volatility gate V5.1','',f'- frozen core DX trade-day detections: {core_tp}/51',f'- frozen core DX false positives: {core_fp}','', '## Frozen ATR-family follow-up']
    for r in summaries: report.append(f"- {r['metric']} <= {r['threshold']:.10g}: TP {r['tp']}/51, FP {r['fp']}/7, exact {r['exact']}/51, within5 {r['within5']}/51")
    improves=any(r['fp']<core_fp and r['tp']==51 and r['exact']>=48 for r in summaries)
    report += ['','## Verdict', 'UNDERLYING_MONOTONE_VOLATILITY_GATE_SURVIVES' if improves else 'UNDERLYING_MONOTONE_VOLATILITY_GATE_REJECTED_FOR_FROZEN_RECONSTRUCTION','',
               'The V5 April-06-compatible ATR thresholds are rejected unless they improve frozen no-trade specificity without sacrificing frozen timing. This is reconstruction evidence only, not a trading edge or live authorization.']
    (OUT/'REPORT.md').write_text('\n'.join(report)); print('\n'.join(report))

if __name__=='__main__': main()
