#!/usr/bin/env python3
"""Fast minute-aware inverse reconstruction for the public Reddit/FYERS ledger.
Research only: no broker, order, paper/live, or promotion authority.
"""
from __future__ import annotations
import json, math, urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/evidence/reddit_fyers_inverse_v2_fast"
OUT.mkdir(parents=True, exist_ok=True)
LABELS = ROOT / "research/external/reddit_fyers/public_fyers_labels_v1.csv"
DATA_URL = "https://raw.githubusercontent.com/Aerysaint/TradingStrategyBacktester/main/datasets/NIFTY%2050_minute.csv"
DATA = OUT / "NIFTY_50_1minute_public.csv"
TRAIN_END = pd.Timestamp("2026-01-30")
TREND_NS = [5,6,7,8,9,10]
VOL_NS = [5,6,7,8,10,14]
VOL_METRICS = ["atr","tr","std","bbw"]
QS = [0.40,0.50,0.60,0.70,0.80,0.90]
SEMANTICS = ["CLOSED_BAR","LIVE_PARTIAL"]
SLOTS = np.arange(10*60+56, 15*60+6+1, 5, dtype=int)


def download():
    if DATA.exists() and DATA.stat().st_size > 5_000_000: return
    req=urllib.request.Request(DATA_URL,headers={"User-Agent":"tradebot-research/2.2"})
    with urllib.request.urlopen(req,timeout=180) as r: DATA.write_bytes(r.read())


def slope(c,n):
    if len(c)<n: return np.nan
    z=np.asarray(c[-n:],float); x=np.arange(n,dtype=float); x-=x.mean(); d=np.dot(x,x)
    return float(np.dot(x,z-z.mean())/d) if d else np.nan


def tr_array(h,l,c):
    if len(c)==0: return np.array([],float)
    a=np.empty(len(c),float); a[0]=h[0]-l[0]
    if len(c)>1:
        p=c[:-1]; a[1:]=np.maximum(h[1:]-l[1:],np.maximum(np.abs(h[1:]-p),np.abs(l[1:]-p)))
    return a


def wilder_last(a,n):
    if len(a)<n: return np.nan
    alpha=1.0/n; v=float(a[0])
    for x in a[1:]: v=alpha*float(x)+(1-alpha)*v
    return v


def aggregate5(day):
    mins=day.datetime.dt.hour*60+day.datetime.dt.minute
    d=day.copy(); d["bucket"]=((mins-555)//5).astype(int)
    return d.groupby("bucket",sort=True).agg(open=("open","first"),high=("high","max"),low=("low","min"),close=("close","last"))


def snap(day,agg,m,sem):
    b=int((m-555)//5); prior=agg[agg.index<b][["open","high","low","close"]]
    if sem=="CLOSED_BAR": return prior
    mins=day.datetime.dt.hour*60+day.datetime.dt.minute
    cur=day[(mins>=555+b*5)&(mins<=m)]
    if cur.empty:return prior
    p=pd.DataFrame([{"open":float(cur.iloc[0].open),"high":float(cur.high.max()),"low":float(cur.low.min()),"close":float(cur.iloc[-1].close)}],index=[b])
    return pd.concat([prior,p])


def alloc(days): return np.full((len(days),len(SLOTS)),np.nan,float)


def build_features(raw,days):
    strength={(s,n):alloc(days) for s in SEMANTICS for n in TREND_NS}
    direction={(s,n):alloc(days) for s in SEMANTICS for n in TREND_NS}
    vol={(s,n,v):alloc(days) for s in SEMANTICS for n in VOL_NS for v in VOL_METRICS}
    for i,d in enumerate(days):
        day=raw[raw.date==d].sort_values("datetime").copy()
        if day.empty: continue
        available=set((day.datetime.dt.hour*60+day.datetime.dt.minute).astype(int).tolist()); agg=aggregate5(day)
        for j,m in enumerate(SLOTS):
            if int(m) not in available: continue
            for sem in SEMANTICS:
                z=snap(day,agg,int(m),sem)
                if len(z)<max(max(TREND_NS),max(VOL_NS)):continue
                h=z.high.to_numpy(float); l=z.low.to_numpy(float); c=z.close.to_numpy(float); tr=tr_array(h,l,c)
                for n in TREND_NS:
                    sl=slope(c,n); strength[(sem,n)][i,j]=abs(sl); direction[(sem,n)][i,j]=1 if sl>=0 else -1
                for n in VOL_NS:
                    x=c[-n:]; mu=float(x.mean()); sd=float(x.std(ddof=0))
                    vol[(sem,n,"atr")][i,j]=wilder_last(tr,n)
                    vol[(sem,n,"tr")][i,j]=float(tr[-1]); vol[(sem,n,"std")][i,j]=sd
                    vol[(sem,n,"bbw")][i,j]=4*sd/mu if mu else np.nan
    return strength,direction,vol


def label_arrays(days,labels):
    present=np.zeros(len(days),bool); minute=np.full(len(days),-1,int); dr=np.zeros(len(days),int)
    for i,d in enumerate(days):
        x=labels.get(d)
        if not x:continue
        dt,side=x; present[i]=True; minute[i]=dt.hour*60+dt.minute; dr[i]=1 if side=="CE" else -1
    return present,minute,dr


def mask_for(st,v,sth,vth,mode):
    state=np.isfinite(st)&np.isfinite(v)&(st>=sth)&(v>=vth)
    if mode=="state":return state
    prev=np.zeros_like(state); prev[:,1:]=state[:,:-1]
    return state&~prev


def score(mask,dm,inds,op,om,od):
    x=mask[inds]; pred=x.any(axis=1); first=np.argmax(x,axis=1); pm=np.where(pred,SLOTS[first],-1)
    ds=dm[inds]; pd=np.zeros(len(inds),int); rr=np.arange(len(inds)); pd[pred]=ds[rr[pred],first[pred]].astype(int)
    p=op[inds]; m=p&pred; tp=int(m.sum()); fp=int((~p&pred).sum()); fn=int((p&~pred).sum()); tn=int((~p&~pred).sum())
    precision=tp/(tp+fp) if tp+fp else 0.; recall=tp/(tp+fn) if tp+fn else 0.; f1=2*precision*recall/(precision+recall) if precision+recall else 0.
    spec=tn/(tn+fp) if tn+fp else 0.; exact=float(np.mean(pm[m]==om[inds][m])) if m.any() else 0.; dacc=float(np.mean(pd[m]==od[inds][m])) if m.any() else 0.
    err=np.abs(pm[m]-om[inds][m]) if m.any() else np.array([]); med=float(np.median(err)) if len(err) else math.inf
    w5=float(np.mean(err<=5)) if len(err) else 0.; w10=float(np.mean(err<=10)) if len(err) else 0.
    sc=.45*exact+.20*dacc+.15*f1+.20*spec
    return dict(tp=tp,fp=fp,fn=fn,tn=tn,precision=precision,recall=recall,f1=f1,specificity=spec,direction_accuracy=dacc,exact_time_rate=exact,within_5m_rate=w5,within_10m_rate=w10,median_abs_timing_error_min=med,score=sc)


def main():
    download(); raw=pd.read_csv(DATA); raw["datetime"]=pd.to_datetime(raw["date"],errors="coerce"); raw["date"]=raw.datetime.dt.date
    for c in ["open","high","low","close"]:raw[c]=pd.to_numeric(raw[c],errors="coerce")
    raw=raw.dropna(subset=["datetime","open","high","low","close"]).sort_values("datetime"); mins=raw.datetime.dt.hour*60+raw.datetime.dt.minute; raw=raw[(mins>=555)&(mins<=929)].copy()
    lab=pd.read_csv(LABELS); lab["entry_dt"]=pd.to_datetime(lab.entry_dt,errors="coerce"); lab=lab.dropna(subset=["entry_dt","direction"]); lab["date"]=lab.entry_dt.dt.date
    cadence=float(((lab.entry_dt.dt.minute%5)==1).mean()); lo=max(raw.datetime.min().normalize(),lab.entry_dt.min().normalize()); hi=min(raw.datetime.max().normalize(),lab.entry_dt.max().normalize())
    raw=raw[(raw.datetime>=lo)&(raw.datetime<hi+pd.Timedelta(days=1))].copy(); lab=lab[(lab.entry_dt>=lo)&(lab.entry_dt<hi+pd.Timedelta(days=1))].copy()
    days=sorted(d for d in raw.date.unique() if pd.Timestamp(d).weekday()!=1); ds=set(days); labels={r.date:(r.entry_dt,r.direction) for r in lab.itertuples(index=False) if r.date in ds}
    train=np.array([i for i,d in enumerate(days) if pd.Timestamp(d)<=TRAIN_END],int); test=np.array([i for i,d in enumerate(days) if pd.Timestamp(d)>TRAIN_END],int); allidx=np.arange(len(days)); op,om,od=label_arrays(days,labels)
    strength,direction,vol=build_features(raw,days)

    # Direction fingerprint at the actual public execution minute.
    slot={int(m):j for j,m in enumerate(SLOTS)}; fp=[]
    for sem in SEMANTICS:
        for n in TREND_NS:
            dm=direction[(sem,n)]
            for split,inds in [("TRAIN",train),("TEST",test),("ALL",allidx)]:
                hits=[]
                for i in inds:
                    if op[i] and int(om[i]) in slot and np.isfinite(dm[i,slot[int(om[i])]]):hits.append(int(int(dm[i,slot[int(om[i])]])==int(od[i])))
                fp.append(dict(semantic=sem,trend_n=n,split=split,direction_accuracy=float(np.mean(hits)) if hits else np.nan,n=len(hits)))
    fpdf=pd.DataFrame(fp); fpdf.to_csv(OUT/"direction_fingerprint.csv",index=False)

    rows=[]
    for sem in SEMANTICS:
        for tn in TREND_NS:
            st=strength[(sem,tn)]; ts=st[train].ravel(); ts=ts[np.isfinite(ts)]; sths={q:float(np.quantile(ts,q)) for q in QS}
            for vn in VOL_NS:
                for vm in VOL_METRICS:
                    vv=vol[(sem,vn,vm)]; tv=vv[train].ravel(); tv=tv[np.isfinite(tv)]; vths={q:float(np.quantile(tv,q)) for q in QS}
                    for sq,sth in sths.items():
                        for vq,vth in vths.items():
                            for mode in ["state","cross"]:
                                mk=mask_for(st,vv,sth,vth,mode); m=score(mk,direction[(sem,tn)],train,op,om,od)
                                rows.append(dict(semantic=sem,trend_n=tn,vol_n=vn,vol_metric=vm,strength_q=sq,vol_q=vq,strength_threshold=sth,vol_threshold=vth,mode=mode,**{f"train_{k}":x for k,x in m.items()}))
    cand=pd.DataFrame(rows).sort_values(["train_score","train_exact_time_rate","train_direction_accuracy","train_specificity"],ascending=False).reset_index(drop=True); cand.to_csv(OUT/"candidate_train_matrix.csv",index=False)
    frozen=[]
    for sem in SEMANTICS:
        for rank,r in enumerate(cand[cand.semantic==sem].head(100).itertuples(index=False),1):
            mk=mask_for(strength[(sem,int(r.trend_n))],vol[(sem,int(r.vol_n),r.vol_metric)],float(r.strength_threshold),float(r.vol_threshold),r.mode)
            tm=score(mk,direction[(sem,int(r.trend_n))],test,op,om,od); am=score(mk,direction[(sem,int(r.trend_n))],allidx,op,om,od); x=r._asdict(); x["train_rank_within_semantic"]=rank; x.update({f"test_{k}":v for k,v in tm.items()}); x.update({f"all_{k}":v for k,v in am.items()}); frozen.append(x)
    fr=pd.DataFrame(frozen); fr.to_csv(OUT/"top100_frozen_test_results.csv",index=False); best=[fr[(fr.semantic==s)&(fr.train_rank_within_semantic==1)].iloc[0].to_dict() for s in SEMANTICS]; pd.DataFrame(best).to_csv(OUT/"semantic_best_frozen_results.csv",index=False)
    promoted=[b for b in best if b["test_exact_time_rate"]>=.50 and b["test_direction_accuracy"]>=.85 and b["test_specificity"]>=.50]; verdict="RECONSTRUCTED_CANDIDATE" if promoted else "NOT_RECONSTRUCTED"
    lines=["# Reddit/FYERS inverse reconstruction V2 fast","",f"- entry cadence minute-mod-5==1: **{cadence:.1%}**",f"- overlap: **{lo.date()} to {hi.date()}**",f"- eligible non-Tuesday sessions: **{len(days)}**",f"- labelled sessions: **{int(op.sum())}**",f"- frozen train cutoff: **{TRAIN_END.date()}**",f"- candidates: **{len(cand):,}**","","## Direction fingerprint"]
    for sem in SEMANTICS:
        for split in ["TRAIN","TEST"]:
            z=fpdf[(fpdf.semantic==sem)&(fpdf.split==split)].sort_values("direction_accuracy",ascending=False).iloc[0]; lines.append(f"- {sem} {split}: best LRS({int(z.trend_n)}) = **{z.direction_accuracy:.1%}** (n={int(z.n)})")
    lines += ["","## Frozen semantic comparison"]
    for b in best:
        lines += ["",f"### {b['semantic']}",f"- rule: |LRS({int(b['trend_n'])})| q={b['strength_q']}, {b['vol_metric']}({int(b['vol_n'])}) q={b['vol_q']}, mode={b['mode']}",f"- TRAIN exact={b['train_exact_time_rate']:.1%}, direction={b['train_direction_accuracy']:.1%}, F1={b['train_f1']:.1%}, specificity={b['train_specificity']:.1%}",f"- TEST exact={b['test_exact_time_rate']:.1%}, within5={b['test_within_5m_rate']:.1%}, direction={b['test_direction_accuracy']:.1%}, F1={b['test_f1']:.1%}, specificity={b['test_specificity']:.1%}",f"- TEST median timing error={b['test_median_abs_timing_error_min']:.1f} min"]
    lines += ["","## Verdict","",f"**`{verdict}`**","","Hard gate: unseen exact-entry >=50%, direction >=85%, no-trade specificity >=50%. Direction alone is not accepted."]
    (OUT/"REPORT_V2_FAST.md").write_text("\n".join(lines)); (OUT/"run_manifest.json").write_text(json.dumps(dict(data_url=DATA_URL,cadence_rate=cadence,overlap_start=str(lo.date()),overlap_end=str(hi.date()),train_end=str(TRAIN_END.date()),candidate_count=len(cand),verdict=verdict),indent=2)); print("\n".join(lines))

if __name__=="__main__": main()
