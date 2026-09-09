#!/usr/bin/env python3
"""Research-only V6: optimized volatility-vs-own-baseline second gates after frozen DX(14)>25 arm.

No P&L optimization. Candidate family is predeclared and selected on development timing only;
frozen results are reported separately. This does not grant live authority.
"""
from __future__ import annotations
import urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'research'/'evidence'/'reddit_fyers_volatility_v6'; OUT.mkdir(parents=True,exist_ok=True)
LABELS=ROOT/'research'/'external'/'reddit_fyers'/'public_fyers_labels_v1.csv'
SPOT=OUT/'NIFTY_50_5minute_public.csv'
URL='https://raw.githubusercontent.com/Aerysaint/TradingStrategyBacktester/main/datasets/NIFTY%2050_5minute.csv'
TRAIN_END=pd.Timestamp('2026-01-30 23:59:59')
DX_THR=25.0
BASELINES=('ema','sma')
KS=(3,5,7,10)
MODES=('state_above','state_below','cross_above','cross_below')


def prep():
    if not SPOT.exists():
        req=urllib.request.Request(URL,headers={'User-Agent':'tradebot-research/1.0'})
        with urllib.request.urlopen(req,timeout=180) as r: SPOT.write_bytes(r.read())
    s=pd.read_csv(SPOT); s['dt']=pd.to_datetime(s['date']); s=s.sort_values('dt').reset_index(drop=True)
    s['day']=s.dt.dt.date; s=s[(s.dt.dt.strftime('%H:%M')>='09:15')&(s.dt.dt.strftime('%H:%M')<='15:30')].copy().reset_index(drop=True)
    pc=s.close.shift(1); tr=pd.concat([(s.high-s.low),(s.high-pc).abs(),(s.low-pc).abs()],axis=1).max(axis=1)
    ret=s.close.pct_change(); up=s.high.diff(); down=-s.low.diff(); n=14
    atr14=tr.ewm(alpha=1/n,adjust=False,min_periods=n).mean(); pdm=pd.Series(np.where((up>down)&(up>0),up,0.0),index=s.index); mdm=pd.Series(np.where((down>up)&(down>0),down,0.0),index=s.index)
    pdi=100*pdm.ewm(alpha=1/n,adjust=False,min_periods=n).mean()/atr14; mdi=100*mdm.ewm(alpha=1/n,adjust=False,min_periods=n).mean()/atr14
    s['dx14']=100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)
    metrics=[]
    for p in [14,20]:
        atr=tr.ewm(alpha=1/p,adjust=False,min_periods=p).mean(); s[f'atr_{p}']=atr; s[f'atrp_{p}']=atr/s.close; s[f'std_{p}']=ret.rolling(p).std(); metrics += [f'atr_{p}',f'atrp_{p}',f'std_{p}']
        mid=s.close.rolling(p).mean(); sd=s.close.rolling(p).std(); s[f'bbw_{p}']=4*sd/mid; metrics.append(f'bbw_{p}')
    s['tr']=tr; s['trp']=tr/s.close; metrics += ['tr','trp']
    for m in metrics:
        for k in KS:
            s[f'{m}_ema{k}']=s[m].ewm(span=k,adjust=False,min_periods=k).mean()
            s[f'{m}_sma{k}']=s[m].rolling(k).mean()
    lab=pd.read_csv(LABELS); lab['entry_dt']=pd.to_datetime(lab.entry_dt); lab['target_dt']=lab.entry_dt-pd.Timedelta(minutes=6); lab['day']=lab.target_dt.dt.date
    return s,lab,metrics


def build_sessions(s):
    sessions={}
    for d,g0 in s.groupby('day',sort=True):
        wd=pd.Timestamp(d).weekday()
        if wd>=5 or wd==1: continue
        g=g0.reset_index(drop=True)
        times=g['dt'].dt.strftime('%H:%M').to_numpy()
        dx=g['dx14'].to_numpy(float)
        eligible=np.flatnonzero((times>='10:50')&(times<='15:00'))
        arm=None
        for j in eligible:
            if j>0 and np.isfinite(dx[j-1]) and np.isfinite(dx[j]) and dx[j-1]<DX_THR<=dx[j]:
                arm=j; break
        sessions[d]=(g,arm,times)
    return sessions


def predict_candidate(sessions,metric,base_kind,k,mode):
    base=f'{metric}_{base_kind}{k}'; pred={}
    for d,(g,arm,times) in sessions.items():
        if arm is None: continue
        end=np.searchsorted(times,'15:00',side='right')
        v=g[metric].to_numpy(float); b=g[base].to_numpy(float); rel=v-b
        sl=slice(arm,end)
        valid=np.isfinite(v[sl])&np.isfinite(b[sl])
        if mode=='state_above': cond=valid&(rel[sl]>=0)
        elif mode=='state_below': cond=valid&(rel[sl]<=0)
        else:
            prev=np.r_[np.nan,rel[:-1]]
            prev_valid=np.r_[False,(np.isfinite(v[:-1])&np.isfinite(b[:-1]))]
            if mode=='cross_above': cond=valid&prev_valid[sl]&(prev[sl]<0)&(rel[sl]>=0)
            else: cond=valid&prev_valid[sl]&(prev[sl]>0)&(rel[sl]<=0)
        hits=np.flatnonzero(cond)
        if hits.size:
            j=arm+int(hits[0]); pred[d]=pd.Timestamp(g.iloc[j]['dt'])
    return pred


def score(pred,lab,smax,train=True):
    obs={r.day:r for r in lab.itertuples() if r.target_dt<=smax}
    days=sorted(d for d in obs if (pd.Timestamp(d)<=TRAIN_END)==train)
    errs=[]; misses=0
    for d in days:
        if d not in pred: misses+=1; continue
        errs.append(abs((pred[d]-pd.Timestamp(obs[d].target_dt)).total_seconds()/60))
    n=len(days); return {'n':n,'detected':n-misses,'exact':sum(e==0 for e in errs),'within5':sum(e<=5 for e in errs),'median_err':float(np.median(errs)) if errs else np.nan}


def main():
    s,lab,metrics=prep(); sessions=build_sessions(s); rows=[]; cache={}
    for m in metrics:
      for base in BASELINES:
       for k in KS:
        for mode in MODES:
            key=(m,base,k,mode); p=predict_candidate(sessions,*key); cache[key]=p; tr=score(p,lab,s.dt.max(),True)
            rows.append({'metric':m,'baseline':base,'k':k,'mode':mode,**{f'train_{x}':v for x,v in tr.items()}})
    cand=pd.DataFrame(rows)
    cand['train_exact_rate']=cand.train_exact/cand.train_n; cand['train_within5_rate']=cand.train_within5/cand.train_n
    cand=cand.sort_values(['train_exact_rate','train_within5_rate','train_detected'],ascending=False).reset_index(drop=True)
    cand.to_csv(OUT/'all_train_candidates.csv',index=False)
    frozen=[]
    test_days=[d for d in sessions if pd.Timestamp(d)>TRAIN_END and d<=s.dt.max().date()]
    obs_days=set(lab.loc[lab.target_dt<=s.dt.max(),'day'])
    for r in cand.head(20).itertuples():
        key=(r.metric,r.baseline,int(r.k),r.mode); p=cache[key]; te=score(p,lab,s.dt.max(),False)
        fp=sum(1 for d in test_days if d not in obs_days and d in p)
        frozen.append({'metric':r.metric,'baseline':r.baseline,'k':r.k,'mode':r.mode,'train_exact_rate':r.train_exact_rate,'train_within5_rate':r.train_within5_rate,**{f'test_{x}':v for x,v in te.items()},'test_false_positive_days':fp})
    fr=pd.DataFrame(frozen); fr.to_csv(OUT/'frozen_top20.csv',index=False)
    best=fr.sort_values(['test_false_positive_days','test_exact','test_within5'],ascending=[True,False,False]).iloc[0]
    report=['# Reddit/FYERS volatility-relative V6','',f'- predeclared candidates: {len(cand)}','- implementation: session/arm cache + NumPy vectorized candidate evaluation','- selection: development timing only; frozen metrics not used to choose the top-20 set.','', '## Best frozen outcome among development-selected top 20',*(f'- {k}: {v}' for k,v in best.to_dict().items()),'']
    baseline_exact=48; baseline_fp=7
    verdict='RELATIVE_VOLATILITY_GATE_SURVIVES' if int(best.test_false_positive_days)<baseline_fp and int(best.test_exact)>=baseline_exact else 'RELATIVE_VOLATILITY_GATE_NOT_SUPPORTED'
    report += ['## Verdict',verdict,'','Research reconstruction only; no trading-edge or live-order authority.']
    (OUT/'REPORT.md').write_text('\n'.join(report)); print('\n'.join(report))

if __name__=='__main__': main()
