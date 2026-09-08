#!/usr/bin/env python3
from __future__ import annotations
import math, urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'research'/'evidence'/'reddit_fyers_timing_v2'; OUT.mkdir(parents=True,exist_ok=True)
LABELS=ROOT/'research'/'external'/'reddit_fyers'/'public_fyers_labels_v1.csv'
URL='https://raw.githubusercontent.com/Aerysaint/TradingStrategyBacktester/main/datasets/NIFTY%2050_5minute.csv'
DATA=OUT/'NIFTY_50_5minute_public.csv'
TRAIN_END=pd.Timestamp('2026-01-30')
SLOPE_PERIODS=[5,6,7,8,9,10,12,14]
VOL_SPECS=[('atr_pct',5),('atr_pct',7),('atr_pct',10),('atr_pct',14),('tr_pct',1),('std_ret',5),('std_ret',7),('std_ret',10),('std_ret',14),('bb_width',10),('bb_width',14),('bb_width',20)]
QS=[.20,.30,.40,.50,.60,.70,.80]
MODES=['state','vol_cross','slope_cross','joint_cross']
START='10:55:00'; END='15:05:00'

def download():
    if DATA.exists() and DATA.stat().st_size>1_000_000:return
    req=urllib.request.Request(URL,headers={'User-Agent':'tradebot-research/2.0'})
    with urllib.request.urlopen(req,timeout=120) as r: DATA.write_bytes(r.read())

def add_features(raw,sp,vk,vp):
    f=raw.copy(); n=len(f)
    slope=np.full(n,np.nan); vol=np.full(n,np.nan)
    for _,idx in f.groupby('date',sort=False).groups.items():
        ii=np.asarray(list(idx),dtype=int); g=f.loc[ii]; c=g.close.to_numpy(float); h=g.high.to_numpy(float); l=g.low.to_numpy(float)
        x=np.arange(sp,dtype=float); xm=x.mean(); den=((x-xm)**2).sum()
        sl=np.full(len(ii),np.nan)
        for j in range(sp-1,len(ii)):
            y=c[j-sp+1:j+1]; sl[j]=((x-xm)*(y-y.mean())).sum()/den
        slope[ii]=sl/c
        prev=np.r_[np.nan,c[:-1]]
        tr=np.nanmax(np.c_[h-l,np.abs(h-prev),np.abs(l-prev)],axis=1)
        if vk=='tr_pct': vv=tr/c
        elif vk=='atr_pct': vv=pd.Series(tr).rolling(vp,min_periods=vp).mean().to_numpy()/c
        elif vk=='std_ret': vv=pd.Series(c).pct_change().rolling(vp,min_periods=vp).std().to_numpy()
        elif vk=='bb_width':
            s=pd.Series(c); ma=s.rolling(vp,min_periods=vp).mean(); sd=s.rolling(vp,min_periods=vp).std(); vv=(4*sd/ma).to_numpy()
        else: raise ValueError(vk)
        vol[ii]=vv
    f['slope']=slope; f['slope_abs']=np.abs(slope); f['vol']=vol
    return f

def metrics(days,labels,pred):
    tp=fp=fn=tn=0; exact=[]; n5=[]; n10=[]; dirs=[]; errs=[]
    for d in days:
        o=labels.get(d); p=pred.get(d)
        if o and p:
            tp+=1; e=abs((p[0]-o[0]).total_seconds()/60); errs.append(e); exact.append(e==0); n5.append(e<=5); n10.append(e<=10); dirs.append(p[1]==o[1])
        elif o: fn+=1
        elif p: fp+=1
        else: tn+=1
    pr=tp/(tp+fp) if tp+fp else 0; rc=tp/(tp+fn) if tp+fn else 0; f1=2*pr*rc/(pr+rc) if pr+rc else 0
    return dict(f1=f1,direction_accuracy=float(np.mean(dirs)) if dirs else 0,exact_time_rate=float(np.mean(exact)) if exact else 0,within_5m_rate=float(np.mean(n5)) if n5 else 0,within_10m_rate=float(np.mean(n10)) if n10 else 0,median_abs_timing_error_min=float(np.median(errs)) if errs else math.inf,tp=tp,fp=fp,fn=fn,tn=tn)

def score(m): return .40*m['exact_time_rate']+.25*m['within_5m_rate']+.10*m['within_10m_rate']+.15*m['direction_accuracy']+.10*m['f1']

def main():
    download(); raw=pd.read_csv(DATA); raw['datetime']=pd.to_datetime(raw['date']); raw['date']=raw.datetime.dt.date; raw['time']=raw.datetime.dt.strftime('%H:%M:%S')
    for c in ['open','high','low','close']: raw[c]=pd.to_numeric(raw[c],errors='coerce')
    lab=pd.read_csv(LABELS); lab['signal_dt']=pd.to_datetime(lab.signal_dt); lab['date']=lab.signal_dt.dt.date
    lo=max(raw.datetime.min().normalize(),lab.signal_dt.min().normalize()); hi=min(raw.datetime.max().normalize(),lab.signal_dt.max().normalize())
    raw=raw[(raw.datetime>=lo)&(raw.datetime<hi+pd.Timedelta(days=1))].reset_index(drop=True); lab=lab[(lab.signal_dt>=lo)&(lab.signal_dt<hi+pd.Timedelta(days=1))]
    days=sorted(d for d in raw.date.unique() if pd.Timestamp(d).weekday()!=1); labels={r.date:(r.signal_dt,r.direction) for _,r in lab.iterrows() if r.date in days}
    train=[d for d in days if pd.Timestamp(d)<=TRAIN_END]; test=[d for d in days if pd.Timestamp(d)>TRAIN_END]
    inwin=(raw.time>=START)&(raw.time<=END); records=[]
    for sp in SLOPE_PERIODS:
      for vk,vp in VOL_SPECS:
        f=add_features(raw,sp,vk,vp); trainmask=f.date.isin(train)&inwin&f.slope_abs.notna()&f.vol.notna()
        if trainmask.sum()<100: continue
        sqvals={q:float(f.loc[trainmask,'slope_abs'].quantile(q)) for q in QS}; vqvals={q:float(f.loc[trainmask,'vol'].quantile(q)) for q in QS}
        prev_s=f.groupby('date').slope_abs.shift(1); prev_v=f.groupby('date').vol.shift(1)
        for sq,st in sqvals.items():
          for vq,vt in vqvals.items():
            state=inwin&(f.slope_abs>=st)&(f.vol>=vt)
            for mode in MODES:
              if mode=='state': trig=state
              elif mode=='vol_cross': trig=state&~(prev_v>=vt).fillna(False)
              elif mode=='slope_cross': trig=state&~(prev_s>=st).fillna(False)
              else: trig=state&~((prev_s>=st)&(prev_v>=vt)).fillna(False)
              x=f.loc[trig,['date','datetime','slope']].sort_values('datetime').groupby('date',sort=False).first().reset_index(); pred={r.date:(r.datetime,'CE' if r.slope>0 else 'PE') for _,r in x.iterrows()}
              tm=metrics(train,labels,pred); records.append(dict(sp=sp,vol_metric=vk,vol_period=vp,slope_q=sq,vol_q=vq,mode=mode,slope_threshold=st,vol_threshold=vt,train_score=score(tm),**{f'train_{k}':v for k,v in tm.items()}))
    res=pd.DataFrame(records).sort_values(['train_score','train_exact_time_rate','train_within_5m_rate'],ascending=False).reset_index(drop=True); res.to_csv(OUT/'train_candidates.csv',index=False)
    frozen=[]
    for _,r in res.head(100).iterrows():
      f=add_features(raw,int(r.sp),r.vol_metric,int(r.vol_period)); prev_s=f.groupby('date').slope_abs.shift(1); prev_v=f.groupby('date').vol.shift(1)
      state=inwin&(f.slope_abs>=r.slope_threshold)&(f.vol>=r.vol_threshold)
      if r.mode=='state': trig=state
      elif r.mode=='vol_cross': trig=state&~(prev_v>=r.vol_threshold).fillna(False)
      elif r.mode=='slope_cross': trig=state&~(prev_s>=r.slope_threshold).fillna(False)
      else: trig=state&~((prev_s>=r.slope_threshold)&(prev_v>=r.vol_threshold)).fillna(False)
      x=f.loc[trig,['date','datetime','slope']].sort_values('datetime').groupby('date',sort=False).first().reset_index(); pred={z.date:(z.datetime,'CE' if z.slope>0 else 'PE') for _,z in x.iterrows()}
      te=metrics(test,labels,pred); row=r.to_dict(); row.update({f'test_{k}':v for k,v in te.items()}); row['test_score']=score(te); frozen.append(row)
    fr=pd.DataFrame(frozen); fr.to_csv(OUT/'frozen_test_top100.csv',index=False)
    best=fr.iloc[0]
    report=f'''# Reddit/FYERS Timing Isolation V2\n\nVerdict: **{'TIMING_RULE_CANDIDATE' if best.test_exact_time_rate>=.30 and best.test_within_5m_rate>=.50 else 'NOT_RECONSTRUCTED'}**\n\nSelected on train only: LRS period {int(best.sp)} + {best.vol_metric}({int(best.vol_period)}), mode {best.mode}, slope q={best.slope_q}, vol q={best.vol_q}.\n\nTrain: exact {best.train_exact_time_rate:.1%}, ±5m {best.train_within_5m_rate:.1%}, direction {best.train_direction_accuracy:.1%}, median error {best.train_median_abs_timing_error_min:.1f}m.\n\nUnseen test: exact {best.test_exact_time_rate:.1%}, ±5m {best.test_within_5m_rate:.1%}, ±10m {best.test_within_10m_rate:.1%}, direction {best.test_direction_accuracy:.1%}, median error {best.test_median_abs_timing_error_min:.1f}m.\n\nThis run specifically tests whether a 5-minute Linear Regression Slope trend-strength proxy plus a volatility threshold/crossing event can explain the author's first daily post-11 entry. No option P&L was optimized.\n'''
    (OUT/'REPORT.md').write_text(report); print(report); print(fr.head(10).to_string(index=False))
if __name__=='__main__': main()
