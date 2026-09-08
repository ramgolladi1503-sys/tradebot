#!/usr/bin/env python3
"""Research-only causal reconstruction of the public FYERS strategy.

The public 5-minute NIFTY file is bar-start stamped. A FYERS entry at HH:MM:01
maps to the public bar beginning 5 minutes earlier: target_bar = entry_dt - 6m.
No broker calls. No live authority.
"""
from __future__ import annotations
import urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'research'/'evidence'/'reddit_fyers_causal_v4'; OUT.mkdir(parents=True,exist_ok=True)
LABELS=ROOT/'research'/'external'/'reddit_fyers'/'public_fyers_labels_v1.csv'
SPOT=OUT/'NIFTY_50_5minute_public.csv'
URL='https://raw.githubusercontent.com/Aerysaint/TradingStrategyBacktester/main/datasets/NIFTY%2050_5minute.csv'
TRAIN_END=pd.Timestamp('2026-01-30 23:59:59')

def download():
    if not SPOT.exists():
        req=urllib.request.Request(URL,headers={'User-Agent':'tradebot-research/1.0'})
        with urllib.request.urlopen(req,timeout=180) as r: SPOT.write_bytes(r.read())

def lr_slope(x,n):
    xx=np.arange(n,dtype=float); xc=xx-xx.mean(); den=(xc*xc).sum()
    return x.rolling(n).apply(lambda a: float(np.dot(a-a.mean(),xc)/den),raw=True)

def prep():
    download()
    s=pd.read_csv(SPOT); s['dt']=pd.to_datetime(s['date']); s=s.sort_values('dt').copy(); s['day']=s.dt.dt.date
    s=s[(s.dt.dt.strftime('%H:%M')>='09:15')&(s.dt.dt.strftime('%H:%M')<='15:30')].copy()
    pc=s.close.shift(1); tr=pd.concat([(s.high-s.low),(s.high-pc).abs(),(s.low-pc).abs()],axis=1).max(axis=1)
    up=s.high.diff(); down=-s.low.diff()
    for n in [7,8,14,20]:
        atr=tr.ewm(alpha=1/n,adjust=False,min_periods=n).mean(); s[f'atr_{n}']=atr
        pdm=pd.Series(np.where((up>down)&(up>0),up,0.0),index=s.index)
        mdm=pd.Series(np.where((down>up)&(down>0),down,0.0),index=s.index)
        pdi=100*pdm.ewm(alpha=1/n,adjust=False,min_periods=n).mean()/atr
        mdi=100*mdm.ewm(alpha=1/n,adjust=False,min_periods=n).mean()/atr
        dx=100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)
        s[f'pdi_{n}']=pdi; s[f'mdi_{n}']=mdi; s[f'dx_{n}']=dx; s[f'adx_{n}']=dx.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    s['lrs_7']=lr_slope(s.close,7); s['lrs_8']=lr_slope(s.close,8)
    lab=pd.read_csv(LABELS); lab['entry_dt']=pd.to_datetime(lab.entry_dt)
    lab['target_dt']=lab.entry_dt-pd.Timedelta(minutes=6); lab['day']=lab.target_dt.dt.date
    return s,lab

def evaluate(s,lab,dx_thr=25.0,atr_thr=10.0):
    # Compute cross BEFORE windowing so a genuine 10:50 crossing can use 10:45 as prior bar.
    a=s.dx_14>=dx_thr; b=s.atr_20>=atr_thr
    x=s.copy(); x['trigger']=(a & b & ~a.shift(1,fill_value=False))
    win=x[(x.dt.dt.strftime('%H:%M')>='10:50')&(x.dt.dt.strftime('%H:%M')<='15:00')]
    groups={d:g.reset_index(drop=True) for d,g in win.groupby('day')}
    pred={}
    for d,g in groups.items():
        if pd.Timestamp(d).weekday()>=5 or pd.Timestamp(d).weekday()==1: continue
        h=g.index[g.trigger].to_numpy()
        if len(h):
            row=g.iloc[int(h[0])]
            pred[d]={'pred_dt':pd.Timestamp(row['dt']),'lrs7_dir':'CE' if row['lrs_7']>0 else 'PE','di14_dir':'CE' if row['pdi_14']>row['mdi_14'] else 'PE','dx14':row['dx_14'],'atr20':row['atr_20']}
    obs={r.day:r for r in lab.itertuples() if r.target_dt<=s.dt.max()}
    all_days=sorted(d for d in s.day.unique() if d in groups and min(obs)<=d<=max(obs) and pd.Timestamp(d).weekday()<5 and pd.Timestamp(d).weekday()!=1)
    rows=[]
    for d in all_days:
        o=obs.get(d); p=pred.get(d)
        rows.append({'day':d,'has_trade':o is not None,'has_pred':p is not None,'obs_dt':o.target_dt if o else pd.NaT,'pred_dt':p['pred_dt'] if p else pd.NaT,'timing_err_min':abs((p['pred_dt']-o.target_dt).total_seconds()/60) if p and o else np.nan,'obs_dir':o.direction if o else '','lrs7_dir':p['lrs7_dir'] if p else '','di14_dir':p['di14_dir'] if p else '','dx14':p['dx14'] if p else np.nan,'atr20':p['atr20'] if p else np.nan})
    return pd.DataFrame(rows)

def metrics(df):
    obs=df.has_trade; pr=df.has_pred; both=obs&pr; err=df.loc[both,'timing_err_min']
    return {'sessions':len(df),'observed_trade_days':int(obs.sum()),'predicted_days':int(pr.sum()),'tp':int((obs&pr).sum()),'fp':int((~obs&pr).sum()),'fn':int((obs&~pr).sum()),'tn':int((~obs&~pr).sum()),'exact_over_obs':float((err==0).sum()/max(1,obs.sum())),'within5_over_obs':float((err<=5).sum()/max(1,obs.sum())),'lrs7_direction_on_tp':float((df.loc[both,'lrs7_dir']==df.loc[both,'obs_dir']).mean()) if both.any() else 0,'di14_direction_on_tp':float((df.loc[both,'di14_dir']==df.loc[both,'obs_dir']).mean()) if both.any() else 0}

def threshold_interval(s,lab):
    tr=lab[lab.target_dt<=TRAIN_END].copy(); idx=s.set_index('dt'); lows=[]; highs=[]; rows=[]
    for r in tr.itertuples():
        t=r.target_dt; p=t-pd.Timedelta(minutes=5)
        if t not in idx.index or p not in idx.index: continue
        pv=float(idx.loc[p,'dx_14']); cv=float(idx.loc[t,'dx_14']); ok=pv<cv
        rows.append({'day':r.day,'target_dt':t,'prev_dx14':pv,'target_dx14':cv,'up_cross_possible':ok})
        if ok: lows.append(pv); highs.append(cv)
    pd.DataFrame(rows).to_csv(OUT/'dx14_threshold_constraints_train.csv',index=False)
    return (max(lows),min(highs),len(lows)) if lows else (np.nan,np.nan,0)

def main():
    s,lab=prep(); df=evaluate(s,lab); train=df[pd.to_datetime(df.day)<=TRAIN_END]; test=df[pd.to_datetime(df.day)>TRAIN_END]
    df.to_csv(OUT/'alignment.csv',index=False); tm,te=metrics(train),metrics(test)
    lo,hi,n=threshold_interval(s,lab)
    controls=[]
    for shift in [-10,-5,5,10]:
        x=test.copy(); x.loc[x.has_trade,'obs_dt']=pd.to_datetime(x.loc[x.has_trade,'obs_dt'])+pd.Timedelta(minutes=shift)
        both=x.has_trade&x.has_pred; err=(pd.to_datetime(x.loc[both,'pred_dt'])-pd.to_datetime(x.loc[both,'obs_dt'])).abs().dt.total_seconds()/60
        controls.append({'label_shift_min':shift,'exact_over_obs':float((err==0).sum()/max(1,x.has_trade.sum()))})
    pd.DataFrame(controls).to_csv(OUT/'negative_controls.csv',index=False)
    report=['# Reddit/FYERS causal reconstruction V4.1','','## Candidate rule','- 5-minute NIFTY bars are bar-start stamped.','- Eligible days: Mon/Wed/Thu/Fri.','- Search window: 10:50 to 15:00 public bar timestamps.','- Timing: first DX(14) cross above 25 while ATR(20) >= 10.','- Direction diagnostic A: sign of Linear Regression Slope(7).','- Direction diagnostic B: +DI(14) vs -DI(14).','','## DX(14) train set-identification',f'- crossing constraints: {n}',f'- feasible fixed-threshold interval: ({lo}, {hi}]',f'- threshold 25 inside interval: {lo < 25 <= hi}','','## Train',*(f'- {k}: {v}' for k,v in tm.items()),'','## Frozen test',*(f'- {k}: {v}' for k,v in te.items()),'','## Verdict']
    report.append('TIMING_MECHANISM_STRONGLY_RECONSTRUCTED' if te['exact_over_obs']>=0.90 and te['lrs7_direction_on_tp']>=0.90 else 'NOT_RECONSTRUCTED')
    report += ['','The remaining false-positive no-trade sessions and residual timing/direction mismatches mean the exact hidden two-indicator strategy is not yet certified.']
    (OUT/'REPORT.md').write_text('\n'.join(report)); print('\n'.join(report))

if __name__=='__main__': main()
