#!/usr/bin/env python3
"""Second-generation state-conditioned causal research screen.

Uses only current/prior bars and prior-session state. Research-only; no certification,
runtime authority, or broker actions. Screening keeps non-overlap, explicit time-stop
exits, fixed costs, and a minimum-trade threshold.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, math, statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def f(r: dict[str, Any], k: str, d: float = 0.0) -> float:
    try: return float(r.get(k, d) or d)
    except (TypeError, ValueError): return d


def ts(r: dict[str, Any]) -> str: return str(r.get("timestamp", ""))
def sk(r: dict[str, Any]) -> str: return ts(r)[:10]
def ret_bps(a: float, b: float) -> float: return 0.0 if a <= 0 else (b-a)/a*10000.0

def sid(parts: tuple[Any, ...]) -> str:
    return "SHYP-" + hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12].upper()


def load(path: Path, instrument: str) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as h:
        rows=[r for r in csv.DictReader(h) if str(r.get("instrument","")).upper()==instrument.upper()]
    rows.sort(key=lambda r:(sk(r),ts(r))); return rows


def session_stats(s: list[dict[str, Any]]) -> dict[str,float]:
    o=f(s[0],"open",f(s[0],"close")); c=f(s[-1],"close")
    hi=max(f(x,"high") for x in s); lo=min(f(x,"low") for x in s); mid=(hi+lo)/2
    return {"ret_bps":ret_bps(o,c),"range_bps":0.0 if mid<=0 else (hi-lo)/mid*10000.0,"close":c}


def prior_state(ordered: list[tuple[str,list[dict[str,Any]]]]) -> dict[str,dict[str,float]]:
    out={}; prev=None
    for day,s in ordered:
        cur=session_stats(s)
        if prev is not None:
            out[day]={"prior_ret_bps":prev["ret_bps"],"prior_range_bps":prev["range_bps"],"prior_close":prev["close"]}
        prev=cur
    return out


def generate(instrument:str)->list[dict[str,Any]]:
    out=[]
    regimes=("prior_up","prior_down","prior_high_vol","prior_low_vol")
    for family in ("gap_follow","gap_fade","opening_momentum","intraday_breakout","intraday_reversion"):
      for regime in regimes:
       for direction in (1,-1):
        for threshold in (10,20,35,50):
         for hold in (2,3,6,12):
          lookbacks=(3,6,12) if family in {"intraday_breakout","intraday_reversion"} else (3,)
          for lookback in lookbacks:
           p=(family,instrument,regime,direction,threshold,hold,lookback)
           out.append({"id":sid(p),"family":family,"regime":regime,"direction":direction,"threshold_bps":threshold,"hold_bars":hold,"lookback":lookback})
    return out


def regime_ok(h:dict[str,Any], state:dict[str,float], median_prior_range:float)->bool:
    if not state: return False
    r=state["prior_ret_bps"]; vr=state["prior_range_bps"]; reg=h["regime"]
    if reg=="prior_up": return r>0
    if reg=="prior_down": return r<0
    if reg=="prior_high_vol": return vr>=median_prior_range
    if reg=="prior_low_vol": return vr<median_prior_range
    return False


def signal(h:dict[str,Any], s:list[dict[str,Any]], i:int, state:dict[str,float])->bool:
    if not regime_ok(h,state,state.get("median_prior_range",0.0)): return False
    d=h["direction"]; fam=h["family"]; c=f(s[i],"close"); o=f(s[0],"open",f(s[0],"close")); pc=state.get("prior_close",0.0)
    if c<=0: return False
    if fam in {"gap_follow","gap_fade"}:
        if i!=1 or pc<=0: return False
        gap=ret_bps(pc,o)
        if abs(gap)<h["threshold_bps"]: return False
        desired=(1 if gap>0 else -1) * (1 if fam=="gap_follow" else -1)
        return d==desired
    if fam=="opening_momentum":
        if i<3: return False
        r=ret_bps(o,c)
        return d*r>=h["threshold_bps"]
    n=h["lookback"]
    if i<n: return False
    prev=s[i-n:i]; ph=max(f(x,"high") for x in prev); pl=min(f(x,"low") for x in prev)
    if fam=="intraday_breakout":
        if d==1: return c>ph and ret_bps(ph,c)>=h["threshold_bps"]
        return c<pl and ret_bps(c,pl)>=h["threshold_bps"]
    if fam=="intraday_reversion":
        hi=f(s[i],"high"); lo=f(s[i],"low")
        if d==1: return lo<pl and c>pl and ret_bps(lo,pl)>=h["threshold_bps"]
        return hi>ph and c<ph and ret_bps(ph,hi)>=h["threshold_bps"]
    return False


def mdd(xs:list[float])->float:
    e=p=dd=0.0
    for x in xs:
        e+=x; p=max(p,e); dd=min(dd,e-p)
    return dd


def evaluate(h:dict[str,Any], ordered:list[tuple[str,list[dict[str,Any]]]], state_map:dict[str,dict[str,float]], cost:float, min_trades:int)->dict[str,Any]:
    pnls=[]; by=defaultdict(list)
    prior_ranges=[v["prior_range_bps"] for v in state_map.values()]
    med=statistics.median(prior_ranges) if prior_ranges else 0.0
    for day,s in ordered:
        st=dict(state_map.get(day,{})); st["median_prior_range"]=med
        i=1
        while i<len(s)-1:
            if signal(h,s,i,st):
                j=min(len(s)-1,i+h["hold_bars"])
                if j>i:
                    entry=f(s[i],"close"); exit_=f(s[j],"close")
                    if entry>0:
                        pnl=h["direction"]*ret_bps(entry,exit_)-cost
                        pnls.append(pnl); by[day].append(pnl); i=j+1; continue
            i+=1
    n=len(pnls); wins=[x for x in pnls if x>0]; losses=[x for x in pnls if x<=0]
    exp=statistics.mean(pnls) if pnls else 0.0
    pf=sum(wins)/abs(sum(losses)) if losses and sum(losses)<0 else (math.inf if wins else 0.0)
    max_ts=max((len(v) for v in by.values()),default=0); abs_s=[abs(sum(v)) for v in by.values()]; total=sum(abs_s)
    return {**h,"hypothesis_id":h["id"],"direction":"BUY_CE" if h["direction"]==1 else "BUY_PE","trades":n,"sessions_traded":len(by),
            "win_rate":round(len(wins)/n,4) if n else 0.0,"net_expectancy_bps":round(exp,4),"profit_factor":"INF" if math.isinf(pf) else round(pf,4),
            "max_drawdown_bps":round(mdd(pnls),4),"top_session_trade_share":round(max_ts/n,6) if n else 0.0,
            "top_session_abs_pnl_share":round(max(abs_s)/total,6) if total else 0.0,
            "status":"PROMISING_NOT_CERTIFIED" if n>=min_trades and exp>0 else "REJECTED","certification":"NOT_CERTIFIED","runtime_authority":"NONE",
            "broker_actions_allowed":False,"overlapping_trades_allowed":False,"pnl_semantics":"UNDERLYING_DIRECTION_PROXY_BPS","option_pnl_claimed":False}


def write_csv(path:Path, rows:list[dict[str,Any]])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    if not rows: path.write_text("",encoding="utf-8"); return
    fields=sorted({k for r in rows for k in r})
    with path.open("w",newline="",encoding="utf-8") as h:
        w=csv.DictWriter(h,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(rows)


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--input",required=True); p.add_argument("--instrument",required=True); p.add_argument("--output-dir",required=True)
    p.add_argument("--min-trades",type=int,default=100); p.add_argument("--cost-bps",type=float,default=8.0); a=p.parse_args(argv)
    rows=load(Path(a.input),a.instrument); sessions=defaultdict(list)
    for r in rows: sessions[sk(r)].append(r)
    ordered=sorted(sessions.items()); sm=prior_state(ordered); hs=generate(a.instrument); results=[evaluate(h,ordered,sm,a.cost_bps,a.min_trades) for h in hs]
    results.sort(key=lambda x:(x["status"]=="PROMISING_NOT_CERTIFIED",x["net_expectancy_bps"],x["trades"]),reverse=True)
    run_id=datetime.now(timezone.utc).strftime("STATE-STRICT-%Y%m%dT%H%M%SZ"); out=Path(a.output_dir)/run_id; out.mkdir(parents=True,exist_ok=True)
    (out/"results.json").write_text(json.dumps(results,indent=2,sort_keys=True)+"\n",encoding="utf-8"); write_csv(out/"leaderboard.csv",results)
    manifest={"schema_version":"tradebot-state-conditioned-screen-v1","run_id":run_id,"instrument":a.instrument.upper(),"input":str(Path(a.input).resolve()),
              "input_sha256":hashlib.sha256(Path(a.input).read_bytes()).hexdigest(),"loaded_rows":len(rows),"sessions":len(sessions),"hypotheses":len(hs),
              "promising_not_certified":sum(r["status"]=="PROMISING_NOT_CERTIFIED" for r in results),"min_trades":a.min_trades,"cost_bps":a.cost_bps,
              "families":sorted({h["family"] for h in hs}),"regimes":sorted({h["regime"] for h in hs}),"certification":"NOT_CERTIFIED","runtime_authority":"NONE","broker_actions_allowed":False}
    (out/"run_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(json.dumps(manifest,indent=2)); return 0

if __name__=="__main__": raise SystemExit(main())
