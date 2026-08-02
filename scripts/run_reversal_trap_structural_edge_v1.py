#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, json, math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

STUDY_ID = "reversal_trap_structural_edge_v1"
EXCLUDE = {"synthetic","fixture","fixtures","testdata","tests","evidence","output","outputs","results","ledger","prediction","cache","node_modules",".git"}

@dataclass(frozen=True)
class Params:
    ema_len: int = 55
    atr_len: int = 14
    multiplier: float = 2.0
    trap_window: int = 10
    max_hold_bars: int = 30
    cost_bps: float = 5.0

def norm(x: object) -> str:
    return str(x).strip().lower().replace(" ", "_").replace("-", "_")

def col(df: pd.DataFrame, *names: str) -> str | None:
    m = {norm(x): str(x) for x in df.columns}
    return next((m[x] for x in names if x in m), None)

def canonicalise_frame(raw: pd.DataFrame, source: Path) -> pd.DataFrame | None:
    if raw is None or raw.empty: return None
    o,h,l,c = col(raw,"open","o"),col(raw,"high","h"),col(raw,"low","l"),col(raw,"close","c","ltp")
    ts,d,t,sym = col(raw,"timestamp","datetime","date_time","ts"),col(raw,"date","trading_date"),col(raw,"time","trading_time"),col(raw,"symbol","ticker","instrument","tradingsymbol")
    if not all((o,h,l,c)): return None
    if ts: x = raw[ts]
    elif d and t: x = raw[d].astype(str)+" "+raw[t].astype(str)
    elif d: x = raw[d]
    elif isinstance(raw.index,pd.DatetimeIndex): x = pd.Series(raw.index,index=raw.index)
    else: return None
    parsed = pd.to_datetime(x,errors="coerce")
    try:
        parsed = parsed.dt.tz_localize("Asia/Kolkata",ambiguous="NaT",nonexistent="shift_forward") if parsed.dt.tz is None else parsed.dt.tz_convert("Asia/Kolkata")
    except (AttributeError,TypeError,ValueError):
        parsed = pd.to_datetime(x,errors="coerce",utc=True).dt.tz_convert("Asia/Kolkata")
    df = pd.DataFrame({"timestamp":parsed,"open":pd.to_numeric(raw[o],errors="coerce"),"high":pd.to_numeric(raw[h],errors="coerce"),"low":pd.to_numeric(raw[l],errors="coerce"),"close":pd.to_numeric(raw[c],errors="coerce")})
    df["symbol"] = raw[sym].astype(str).values if sym else source.stem
    df = df.dropna().loc[lambda z:(z[["open","high","low","close"]]>0).all(axis=1)]
    df = df[(df.high>=df[["open","close","low"]].max(axis=1))&(df.low<=df[["open","close","high"]].min(axis=1))]
    if df.empty: return None
    df["timestamp"] = df.timestamp.dt.tz_localize(None)
    df = df.sort_values(["symbol","timestamp"]).drop_duplicates(["symbol","timestamp"],keep="last")
    df["session"] = df.timestamp.dt.date.astype(str)
    return df.reset_index(drop=True)

def load(path: Path) -> pd.DataFrame | None:
    try:
        raw = pd.read_parquet(path) if path.suffix.lower()==".parquet" else pd.read_feather(path) if path.suffix.lower() in {".feather",".ft"} else pd.read_csv(path,low_memory=False)
    except Exception: return None
    return canonicalise_frame(raw,path)

def discover(roots: Sequence[Path], limit: int) -> tuple[list[tuple[Path,pd.DataFrame]],list[dict[str,object]]]:
    files=[]
    for root in roots:
        if root.is_file(): files.append(root)
        elif root.exists():
            for pat in ("*.parquet","*.csv","*.feather","*.ft"): files += list(root.rglob(pat))
    out=[]; inv=[]
    for p in sorted(dict.fromkeys(x.resolve() for x in files))[:limit]:
        if {x.lower() for x in p.parts}&EXCLUDE: continue
        df=load(p)
        if df is None or len(df)<100 or df.session.nunique()<2: continue
        delta=df.groupby("symbol").timestamp.diff().dropna().dt.total_seconds()
        med=float(delta.median()) if len(delta) else math.nan
        if not math.isfinite(med) or not 0<med<=3600: continue
        out.append((p,df)); inv.append({"path":str(p),"rows":len(df),"symbols":df.symbol.nunique(),"sessions":df.session.nunique(),"start":df.timestamp.min().isoformat(),"end":df.timestamp.max().isoformat(),"median_bar_seconds":med})
    return out,inv

def indicators(df: pd.DataFrame,p: Params) -> pd.DataFrame:
    z=df.sort_values("timestamp").reset_index(drop=True).copy(); prev=z.close.shift()
    tr=pd.concat([z.high-z.low,(z.high-prev).abs(),(z.low-prev).abs()],axis=1).max(axis=1)
    z["basis"]=z.close.ewm(span=p.ema_len,adjust=False,min_periods=p.ema_len).mean(); z["atr"]=tr.ewm(alpha=1/p.atr_len,adjust=False,min_periods=p.atr_len).mean()
    z["upper"]=z.basis+p.multiplier*z.atr; z["lower"]=z.basis-p.multiplier*z.atr
    d=z.close.diff(); g=d.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean(); q=(-d.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    z["rsi"]=(100-100/(1+g/q.replace(0,np.nan))).fillna(50); return z

def resolve(df: pd.DataFrame,i:int,side:str,stop:float,target:float,hold:int)->tuple[int,float,str]:
    end=min(len(df)-1,i+hold-1)
    for j in range(i,end+1):
        sh=(df.at[j,"low"]<=stop) if side=="LONG" else (df.at[j,"high"]>=stop); th=(df.at[j,"high"]>=target) if side=="LONG" else (df.at[j,"low"]<=target)
        if sh and th:return j,stop,"SAME_BAR_AMBIGUOUS_STOP_FIRST"
        if sh:return j,stop,"STOP"
        if th:return j,target,"TARGET"
    return end,float(df.at[end,"close"]),"TIME_OR_SESSION_EXIT"

def _resolve_exit(df: pd.DataFrame, i: int, side: str, entry: float, stop: float, target: float, hold: int) -> tuple[int,float,str]:
    return resolve(df, i, side, stop, target, hold)

def build(df:pd.DataFrame,source:str,symbol:str,setup:str,side:str,i:int,p:Params)->dict[str,object]|None:
    e=i+1
    if e>=len(df) or pd.Timestamp(df.at[e,"timestamp"]).date()!=pd.Timestamp(df.at[i,"timestamp"]).date(): return None
    atr,basis=float(df.at[i,"atr"]),float(df.at[i,"basis"]); entry=float(df.at[e,"open"]); prior=max(0,i-1)
    if not math.isfinite(atr) or atr<=0:return None
    if side=="LONG": stop=min(float(df.at[i,"low"]),float(df.at[prior,"low"]))-atr; target=basis; valid=stop<entry<target
    else: stop=max(float(df.at[i,"high"]),float(df.at[prior,"high"]))+atr; target=basis; valid=target<entry<stop
    if not valid:return None
    x,px,reason=resolve(df,e,side,stop,target,p.max_hold_bars); gross=(px-entry)/entry*10000*(1 if side=="LONG" else -1); rsi=float(df.at[i,"rsi"])
    return {"source":source,"symbol":symbol,"session":str(df.at[i,"session"]),"side":side,"setup":setup,"signal_index":i,"entry_index":e,"signal_time":pd.Timestamp(df.at[i,"timestamp"]).isoformat(),"entry_time":pd.Timestamp(df.at[e,"timestamp"]).isoformat(),"exit_time":pd.Timestamp(df.at[x,"timestamp"]).isoformat(),"entry":entry,"exit":px,"stop":stop,"target":target,"exit_reason":reason,"gross_bps":gross,"net_bps":gross-p.cost_bps,"rsi":rsi,"rsi_bucket":int(np.clip(np.rint(rsi/10),0,10)),"bars_held":x-e+1,**asdict(p)}

def generate(frame:pd.DataFrame,source:str,p:Params,setup:str="TRAP")->list[dict[str,object]]:
    trades=[]
    for symbol,sdf in frame.groupby("symbol",sort=True):
      for _,day in sdf.groupby("session",sort=True):
        df=indicators(day,p); until=-1; bull=None; bear=None
        for i in range(len(df)):
          if i<=until or pd.isna(df.at[i,"atr"]):continue
          close,upper,lower=float(df.at[i,"close"]),float(df.at[i,"upper"]),float(df.at[i,"lower"]); signal=None
          if setup=="DIRECT_BAND_FADE": signal=("LONG",i) if close<lower else ("SHORT",i) if close>upper else None
          else:
            if close<lower: bull=i if bull is None else bull
            elif bull is not None: signal=("LONG",i) if 1<=i-bull<=p.trap_window else None; bull=None
            if bull is not None and i-bull>p.trap_window:bull=None
            if close>upper: bear=i if bear is None else bear
            elif bear is not None: signal=signal or (("SHORT",i) if 1<=i-bear<=p.trap_window else None); bear=None
            if bear is not None and i-bear>p.trap_window:bear=None
          if signal:
            t=build(df,source,str(symbol),setup,*signal,p)
            if t: trades.append(t); until=int(t["entry_index"])+int(t["bars_held"])-1; bull=bear=None
    return trades

generate_trades = generate

def metric(df:pd.DataFrame)->dict[str,object]:
    if df.empty:return {"trade_count":0,"win_rate":0.0,"expectancy_bps":0.0,"median_bps":0.0,"profit_factor":None,"net_bps":0.0,"max_drawdown_bps":0.0,"long_count":0,"short_count":0}
    v=df.net_bps.astype(float).to_numpy(); w=v[v>0]; l=v[v<=0]; c=np.cumsum(v); peak=np.maximum.accumulate(np.r_[0,c])[1:]
    return {"trade_count":len(v),"win_rate":float((v>0).mean()),"expectancy_bps":float(v.mean()),"median_bps":float(np.median(v)),"profit_factor":float(w.sum()/abs(l.sum())) if len(w) and l.sum()<0 else None,"net_bps":float(v.sum()),"max_drawdown_bps":float((c-peak).min()),"long_count":int((df.side=="LONG").sum()),"short_count":int((df.side=="SHORT").sum())}

def split(df:pd.DataFrame,sessions:Sequence[str])->pd.DataFrame:
    s=sorted(dict.fromkeys(sessions)); a=max(1,int(.6*len(s))); b=max(a+1,int(.8*len(s))) if len(s)>=3 else len(s); m={x:("train" if i<a else "validation" if i<b else "test") for i,x in enumerate(s)}
    z=df.copy(); z["split"]=z.session.map(m).fillna("unknown"); return z

assign_splits = split

def boot(df:pd.DataFrame,n:int=2000)->tuple[float,float]:
    if df.empty:return 0.,0.
    x=df.groupby(["source","symbol","session"]).net_bps.mean().to_numpy(float)
    if len(x)<2:return float(x.mean()),float(x.mean())
    r=np.random.default_rng(20260802).choice(x,(n,len(x)),replace=True).mean(axis=1); return float(np.quantile(r,.025)),float(np.quantile(r,.975))

def prob_audit(df:pd.DataFrame)->dict[str,object]:
    a=df[df.split=="train"].copy(); b=df[df.split=="test"].copy()
    if a.empty or b.empty:return {"status":"INSUFFICIENT_SPLIT_DATA"}
    a["won"]=(a.net_bps>0).astype(int); b["won"]=(b.net_bps>0).astype(int); g=a.groupby("rsi_bucket").won.agg(["sum","count"]); p={int(i):float((r["sum"]+1)/(r["count"]+2)) for i,r in g.iterrows()}; base=float((a.won.sum()+1)/(len(a)+2)); pred=b.rsi_bucket.map(p).fillna(base).to_numpy(); y=b.won.to_numpy(); score=float(np.mean((pred-y)**2)); base_score=float(np.mean((base-y)**2))
    return {"status":"OK","test_rows":len(b),"bucket_probabilities":{str(k):v for k,v in p.items()},"test_brier":score,"constant_base_brier":base_score,"brier_improvement":base_score-score,"adds_out_of_sample_information":base_score-score>.002}

def run_study(frames:list[tuple[Path,pd.DataFrame]],inventory:list[dict[str,object]],out:Path)->dict[str,object]:
    p=Params(); sessions=sorted({s for _,df in frames for s in df.session.unique()}); trap=[]; base=[]
    for path,df in frames: trap+=generate(df,str(path),p,"TRAP"); base+=generate(df,str(path),p,"DIRECT_BAND_FADE")
    cols=["source","symbol","session","side","net_bps","rsi_bucket"]; t=split(pd.DataFrame(trap),sessions) if trap else pd.DataFrame(columns=cols+["split"]); d=split(pd.DataFrame(base),sessions) if base else pd.DataFrame(columns=cols+["split"])
    robust=[]
    for e in (34,55,89):
      for m in (1.5,2.,2.5):
       for w in (5,10):
        rows=[]; q=Params(ema_len=e,multiplier=m,trap_window=w)
        for path,df in frames:rows+=generate(df,str(path),q,"TRAP")
        z=split(pd.DataFrame(rows),sessions) if rows else pd.DataFrame(columns=cols+["split"]); robust.append({"ema_len":e,"multiplier":m,"trap_window":w,**metric(z[z.split=="test"])})
    r=pd.DataFrame(robust); tm={x:metric(t[t.split==x]) for x in ("train","validation","test")}; bm={x:metric(d[d.split==x]) for x in ("train","validation","test")}; test=t[t.split=="test"]; lo,hi=boot(test); exp=float(tm["test"]["expectancy_bps"]); uplift=exp-float(bm["test"]["expectancy_bps"]); rp=float((r.expectancy_bps>0).mean()); nchunks=min(5,test.session.nunique()); chunks=[x for x in np.array_split(sorted(test.session.unique()),nchunks) if len(x)] if nchunks else []; stable=float(np.mean([test[test.session.isin(x)].net_bps.mean()>0 for x in chunks])) if chunks else 0.
    blockers=[]
    if len(sessions)<30:blockers.append("FEWER_THAN_30_SESSIONS")
    if tm["test"]["trade_count"]<50:blockers.append("FEWER_THAN_50_TEST_TRADES")
    if metric(t)["trade_count"]<200:blockers.append("FEWER_THAN_200_TOTAL_TRADES")
    flags={"validation_expectancy_positive":tm["validation"]["expectancy_bps"]>0,"test_expectancy_positive_after_5bps":exp>0,"test_bootstrap_ci_lower_positive":lo>0,"trap_uplift_over_direct_fade_positive":uplift>1,"test_stability_at_least_60pct":stable>=.6,"neighbour_robustness_at_least_50pct":rp>=.5}
    verdict="DATA_BLOCKED" if blockers else "STRUCTURAL_EDGE_SUPPORTED" if all(flags.values()) else "FRAGILE_CANDIDATE_NOT_STRUCTURAL" if flags["validation_expectancy_positive"] and flags["test_expectancy_positive_after_5bps"] else "NO_STRUCTURAL_EDGE"
    result={"study_id":STUDY_ID,"verdict":verdict,"source_hypothesis":{"exact_pine_replication":False,"reason":"full Pine source and exact multiplier default were not exposed","canonical_assumption":asdict(p)},"data":{"files":len(frames),"sessions":len(sessions),"inventory":inventory},"trap_metrics":{"all":metric(t),**tm},"direct_band_fade_metrics":{"all":metric(d),**bm},"test_bootstrap_expectancy_95pct_bps":[lo,hi],"test_trap_uplift_over_direct_fade_bps":uplift,"test_positive_chunk_fraction":stable,"robustness_positive_fraction":rp,"rsi_probability_audit":prob_audit(t),"acceptance_flags":flags,"blockers":blockers}
    result["semantic_sha256"]=hashlib.sha256(json.dumps(result,sort_keys=True,default=str).encode()).hexdigest(); out.mkdir(parents=True,exist_ok=True); pd.DataFrame(inventory).to_csv(out/"dataset_inventory.csv",index=False); t.to_csv(out/"canonical_trap_trades.csv",index=False); d.to_csv(out/"canonical_direct_band_fade_trades.csv",index=False); r.to_csv(out/"robustness_matrix.csv",index=False); (out/"summary.json").write_text(json.dumps(result,indent=2,sort_keys=True)); (out/"report.md").write_text(f"# Reversal Trap Structural Edge V1\n**Verdict:** `{verdict}`\n\nData: {len(frames)} files, {len(sessions)} sessions. Test trades: {tm['test']['trade_count']}.\n\nTest expectancy after 5 bps: {exp:.4f} bps; 95% CI [{lo:.4f}, {hi:.4f}]. Direct-fade uplift: {uplift:.4f} bps.\n\nRobustness positive: {rp:.1%}. Positive test chunks: {stable:.1%}.\n\n"+"\n".join(f"- {k}: {v}" for k,v in flags.items())+("\n\nBlockers:\n"+"\n".join(f"- {x}" for x in blockers) if blockers else "")); return result

def main()->None:
    a=argparse.ArgumentParser(); a.add_argument("--root",action="append",default=[]); a.add_argument("--output-dir",default=f"research/{STUDY_ID}/evidence"); a.add_argument("--max-files",type=int,default=5000); x=a.parse_args(); roots=[Path(y) for y in x.root] if x.root else [Path("runtime"),Path(".runtime"),Path("data"),Path("research")]; frames,inv=discover(roots,x.max_files); result=run_study(frames,inv,Path(x.output_dir)); print(json.dumps({"verdict":result["verdict"],"semantic_sha256":result["semantic_sha256"],"data":result["data"]},indent=2))

if __name__=="__main__":main()
