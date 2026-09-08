#!/usr/bin/env python3
"""Diagnostic inverse reconstruction using public 1-minute ATM option candles.

Research only. No broker connectivity or live authority.

Purpose:
1. Verify whether an independent public option-premium dataset is close enough to the FYERS
   labelled entries to be useful (strike availability and entry-premium agreement).
2. Conditional on the OBSERVED option side/strike (timing diagnostic only), test whether
   option-price trend-strength x volatility events reproduce the labelled entry time.

Important: conditioning on observed side/strike means this is NOT a complete strategy
reconstruction. It only tests the hypothesis that the missing timing trigger is calculated
on option premium rather than NIFTY spot.
"""
from __future__ import annotations
import math, re, urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'research'/'evidence'/'reddit_fyers_option_v3'
OUT.mkdir(parents=True,exist_ok=True)
LABELS=ROOT/'research'/'external'/'reddit_fyers'/'public_fyers_labels_v1.csv'
XLSX=OUT/'nifty_1y_1min.xlsx'
URL='https://raw.githubusercontent.com/rajmaurya0904/bhav/562dc214416fd974eb41082b05e131c523e49023/sample_data/nifty_1y_1min.xlsx'
TRAIN_END=pd.Timestamp('2026-01-30')
WINDOW_START='10:55:00'; WINDOW_END='15:05:00'
TREND_PERIODS=[5,7,8,10,12,14]
VOL_PERIODS=[5,7,10,14,20]
QS=[.3,.4,.5,.6,.7,.8]
MODES=['state','trend_cross','vol_cross','joint_cross']


def download():
    if XLSX.exists() and XLSX.stat().st_size>1_000_000:return
    req=urllib.request.Request(URL,headers={'User-Agent':'tradebot-research/1.0'})
    with urllib.request.urlopen(req,timeout=180) as r:XLSX.write_bytes(r.read())

def parse_symbol(s:str):
    """Extract NIFTY strike + side robustly from legacy/current FYERS symbols.

    NIFTY strikes in this ledger are five digits; expiry encoding before the strike varies.
    Anchor only on the terminal 5-digit strike immediately before CE/PE.
    """
    m=re.search(r'(\d{5})(CE|PE)$',str(s).upper().strip())
    if not m: return np.nan,''
    return int(m.group(1)),m.group(2)

def lr_slope(x,n):
    xx=np.arange(n,dtype=float); xmean=xx.mean(); den=((xx-xmean)**2).sum()
    return x.rolling(n).apply(lambda a: float(((a-a.mean())*(xx-xmean)).sum()/den), raw=True)

def true_range(df):
    pc=df.close.shift(1)
    return pd.concat([(df.high-df.low),(df.high-pc).abs(),(df.low-pc).abs()],axis=1).max(axis=1)

def wilder(s,n):return s.ewm(alpha=1/n,adjust=False,min_periods=n).mean()

def adx(df,n):
    tr=true_range(df); atr=wilder(tr,n)
    up=df.high.diff(); down=-df.low.diff()
    pdm=pd.Series(np.where((up>down)&(up>0),up,0.0),index=df.index)
    mdm=pd.Series(np.where((down>up)&(down>0),down,0.0),index=df.index)
    pdi=100*wilder(pdm,n)/atr.replace(0,np.nan); mdi=100*wilder(mdm,n)/atr.replace(0,np.nan)
    dx=100*(pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)
    return wilder(dx,n)

def score(obs_times,pred_times):
    errs=[]; exact=[]; n1=[]; n5=[]; n10=[]
    for d,o in obs_times.items():
        p=pred_times.get(d)
        if p is None:continue
        e=abs((p-o).total_seconds()/60); errs.append(e)
        exact.append(e==0); n1.append(e<=1); n5.append(e<=5); n10.append(e<=10)
    tp=len(errs); fn=len(obs_times)-tp
    return {'obs':len(obs_times),'pred_on_obs_days':tp,'coverage':tp/len(obs_times) if obs_times else 0,
            'exact':float(np.mean(exact)) if exact else 0,'within1':float(np.mean(n1)) if n1 else 0,
            'within5':float(np.mean(n5)) if n5 else 0,'within10':float(np.mean(n10)) if n10 else 0,
            'median_err':float(np.median(errs)) if errs else math.inf,'fn':fn}

def main():
    download()
    opt=pd.read_excel(XLSX,sheet_name='ATM_Options_1min')
    opt['timestamp']=pd.to_datetime(opt['Timestamp'],utc=True).dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)
    opt['day']=opt['timestamp'].dt.date
    opt=opt.rename(columns={'Strike':'strike','Type':'side','Open':'open','High':'high','Low':'low','Close':'close','Volume':'volume','OI':'oi'})
    for c in ['strike','open','high','low','close']:opt[c]=pd.to_numeric(opt[c],errors='coerce')
    opt=opt.dropna(subset=['timestamp','strike','side','open','high','low','close']).sort_values('timestamp')

    lab=pd.read_csv(LABELS); lab['entry_dt']=pd.to_datetime(lab.entry_dt); lab['signal_dt']=pd.to_datetime(lab.signal_dt); lab['day']=lab.signal_dt.dt.date
    parsed=lab.SYMBOL.apply(parse_symbol); lab['strike']=[x[0] for x in parsed]; lab['side']=[x[1] for x in parsed]
    parse_fail=lab['strike'].isna() | ~lab['side'].isin(['CE','PE'])
    if parse_fail.any():
        bad=lab.loc[parse_fail,['SYMBOL']].copy()
        bad.to_csv(OUT/'unparsed_symbols.csv',index=False)
        print(f'WARNING: dropping {int(parse_fail.sum())} unparsed symbols; see unparsed_symbols.csv')
    lab=lab.loc[~parse_fail].copy()
    lab['strike']=lab['strike'].astype(int)
    data_days=set(opt.day.unique()); lab=lab[lab.day.isin(data_days)].copy()

    # Data compatibility audit.
    audits=[]
    series_by_day={}
    for _,r in lab.iterrows():
        d=r.day; side=r.side; target=int(r.strike)
        z=opt[(opt.day==d)&(opt.side==side)]
        strikes=sorted(z.strike.astype(int).unique())
        if not strikes:continue
        chosen=min(strikes,key=lambda x:abs(x-target)); exact_strike=chosen==target
        s=z[z.strike.astype(int)==chosen].copy().sort_values('timestamp')
        series_by_day[d]=(s, chosen, target, side)
        cand=s.iloc[(s.timestamp-r.entry_dt).abs().argsort()[:1]]
        if len(cand):
            pub=float(cand.close.iloc[0]); fy=float(r.PRICE); rel=abs(pub-fy)/fy if fy else np.nan
            delta=abs((cand.timestamp.iloc[0]-r.entry_dt).total_seconds()/60)
        else: pub=rel=delta=np.nan
        audits.append({'date':d,'side':side,'target_strike':target,'chosen_strike':chosen,'exact_strike':exact_strike,
                       'fyers_entry_price':r.PRICE,'public_close_near_entry':pub,'price_abs_pct_error':rel,
                       'timestamp_delta_min':delta,'signal_dt':r.signal_dt,'entry_dt':r.entry_dt})
    aud=pd.DataFrame(audits); aud.to_csv(OUT/'option_data_compatibility.csv',index=False)

    dayfeat={}
    for d,(s,chosen,target,side) in series_by_day.items():
        x=s[['timestamp','open','high','low','close']].copy().reset_index(drop=True)
        x['time']=x.timestamp.dt.strftime('%H:%M:%S'); x['tr']=true_range(x)
        for n in TREND_PERIODS:
            x[f'slope_{n}']=lr_slope(x.close,n)
            x[f'slope_abs_{n}']=x[f'slope_{n}'].abs()/x.close
            x[f'adx_{n}']=adx(x,n)
        for n in VOL_PERIODS:
            x[f'atrpct_{n}']=wilder(x.tr,n)/x.close
            x[f'stdret_{n}']=x.close.pct_change().rolling(n).std()
            ma=x.close.rolling(n).mean(); sd=x.close.rolling(n).std()
            x[f'bbw_{n}']=(4*sd)/ma
            x[f'trpct_{n}']=x.tr/x.close
        dayfeat[d]=x

    train_lab=lab[lab.signal_dt<=TRAIN_END].copy(); test_lab=lab[lab.signal_dt>TRAIN_END].copy()
    train_obs={r.day:r.signal_dt for _,r in train_lab.iterrows() if r.day in dayfeat}
    test_obs={r.day:r.signal_dt for _,r in test_lab.iterrows() if r.day in dayfeat}

    trend_metrics=['slope_abs','adx']; vol_metrics=['atrpct','stdret','bbw','trpct']
    results=[]
    for tm in trend_metrics:
      for tp in TREND_PERIODS:
       for vm in vol_metrics:
        for vp in VOL_PERIODS:
          vals_t=[]; vals_v=[]
          for d in train_obs:
            x=dayfeat[d]; w=x[(x.time>=WINDOW_START)&(x.time<=WINDOW_END)]
            vals_t.extend(pd.to_numeric(w[f'{tm}_{tp}'],errors='coerce').dropna().tolist())
            vals_v.extend(pd.to_numeric(w[f'{vm}_{vp}'],errors='coerce').dropna().tolist())
          if len(vals_t)<100 or len(vals_v)<100: continue
          ta=np.array(vals_t); va=np.array(vals_v)
          for tq in QS:
            th_t=float(np.nanquantile(ta,tq))
            for vq in QS:
              th_v=float(np.nanquantile(va,vq))
              for mode in MODES:
                pred={}
                for d,x in dayfeat.items():
                  if d not in train_obs and d not in test_obs: continue
                  w=x[(x.time>=WINDOW_START)&(x.time<=WINDOW_END)].copy()
                  t=w[f'{tm}_{tp}']>=th_t; v=w[f'{vm}_{vp}']>=th_v; state=t&v
                  if mode=='state': trig=state
                  elif mode=='trend_cross': trig=state & ~t.shift(1,fill_value=False)
                  elif mode=='vol_cross': trig=state & ~v.shift(1,fill_value=False)
                  else: trig=state & ~state.shift(1,fill_value=False)
                  hit=w[trig]
                  if len(hit): pred[d]=hit.timestamp.iloc[0]
                tr=score(train_obs,pred)
                rank=.35*tr['exact']+.25*tr['within1']+.20*tr['within5']+.10*tr['within10']+.10*tr['coverage']
                results.append({'trend_metric':tm,'trend_period':tp,'vol_metric':vm,'vol_period':vp,'trend_q':tq,'vol_q':vq,
                                'trend_threshold':th_t,'vol_threshold':th_v,'mode':mode,'train_rank':rank,**{f'train_{k}':v for k,v in tr.items()}})
    res=pd.DataFrame(results).sort_values(['train_rank','train_exact','train_within5'],ascending=False).reset_index(drop=True)
    res.to_csv(OUT/'train_candidates.csv',index=False)

    frozen=[]
    for _,r in res.head(100).iterrows():
      pred={}
      for d,x in dayfeat.items():
        if d not in test_obs:continue
        w=x[(x.time>=WINDOW_START)&(x.time<=WINDOW_END)].copy()
        t=w[f"{r.trend_metric}_{int(r.trend_period)}"]>=r.trend_threshold
        v=w[f"{r.vol_metric}_{int(r.vol_period)}"]>=r.vol_threshold; state=t&v
        if r.mode=='state':trig=state
        elif r.mode=='trend_cross':trig=state & ~t.shift(1,fill_value=False)
        elif r.mode=='vol_cross':trig=state & ~v.shift(1,fill_value=False)
        else:trig=state & ~state.shift(1,fill_value=False)
        hit=w[trig]
        if len(hit):pred[d]=hit.timestamp.iloc[0]
      te=score(test_obs,pred); q=r.to_dict(); q.update({f'test_{k}':v for k,v in te.items()}); frozen.append(q)
    fr=pd.DataFrame(frozen); fr.to_csv(OUT/'frozen_test_top100.csv',index=False)
    b=fr.iloc[0]

    fingerprints=[]
    for _,r in lab.iterrows():
      if r.day not in dayfeat:continue
      x=dayfeat[r.day]; row=x.iloc[(x.timestamp-r.signal_dt).abs().argsort()[:1]]
      if not len(row):continue
      rr={'date':r.day,'signal_dt':r.signal_dt,'side':r.side,'strike':r.strike}
      for n in TREND_PERIODS:
        rr[f'slope_abs_{n}']=row[f'slope_abs_{n}'].iloc[0]; rr[f'adx_{n}']=row[f'adx_{n}'].iloc[0]
      for n in VOL_PERIODS:
        for m in ['atrpct','stdret','bbw','trpct']:rr[f'{m}_{n}']=row[f'{m}_{n}'].iloc[0]
      fingerprints.append(rr)
    pd.DataFrame(fingerprints).to_csv(OUT/'observed_entry_feature_fingerprint.csv',index=False)

    compat={
      'overlap_labels':int(len(lab)),
      'exact_strike_fraction':float(aud.exact_strike.mean()) if len(aud) else 0,
      'median_entry_price_abs_pct_error':float(aud.price_abs_pct_error.median()) if len(aud) else None,
      'p90_entry_price_abs_pct_error':float(aud.price_abs_pct_error.quantile(.9)) if len(aud) else None,
    }
    lines=['# Reddit/FYERS option-trigger reconstruction V3','',
           '## Scope','Conditional timing diagnostic using the observed option side/strike and an independent public 1-minute option-premium dataset. This is not a complete strategy reconstruction.','',
           '## Data compatibility',*(f'- {k}: {v}' for k,v in compat.items()),'',
           '## Frozen winner',
           f"- trend: {b.trend_metric} period {int(b.trend_period)}",
           f"- volatility: {b.vol_metric} period {int(b.vol_period)}",
           f"- mode: {b['mode']}",
           f"- train exact: {b.train_exact:.4f}",f"- train within 5m: {b.train_within5:.4f}",f"- train median error: {b.train_median_err:.2f} min",
           f"- TEST exact: {b.test_exact:.4f}",f"- TEST within 1m: {b.test_within1:.4f}",f"- TEST within 5m: {b.test_within5:.4f}",f"- TEST within 10m: {b.test_within10:.4f}",f"- TEST median error: {b.test_median_err:.2f} min",'',
           '## Interpretation']
    if b.test_within5>=.50 and b.test_exact>=.25:
      lines.append('OPTION_PREMIUM_TIMING_HYPOTHESIS=SUPPORTED_FOR_NEXT_STAGE')
    elif b.test_within5>=.30:
      lines.append('OPTION_PREMIUM_TIMING_HYPOTHESIS=PARTIAL')
    else:
      lines.append('OPTION_PREMIUM_TIMING_HYPOTHESIS=NOT_SUPPORTED_BY_THIS_FAMILY')
    lines += ['', 'Because the test conditions on the observed side/strike, even a strong result would only identify the timing mechanism; a separate causal direction/strike selector would still be required.']
    (OUT/'REPORT.md').write_text('\n'.join(lines))
    print('\n'.join(lines))

if __name__=='__main__':main()
