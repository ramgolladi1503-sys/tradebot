#!/usr/bin/env python3
"""Expanded causal research-only hypothesis screen for canonical intraday OHLC data.

This is intentionally separate from the small baseline hypothesis factory. It explores
additional causal families and explicit parameter grids while preserving strict rules:
- no overlapping trades within a session;
- no future-bar features in entry rules;
- fixed, explicit time-stop exits only;
- cost applied to every trade;
- research-only outputs, no runtime/broker authority;
- screening is discovery, never certification.
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
def session_key(r: dict[str, Any]) -> str: return ts(r)[:10]
def stable_id(parts: tuple[Any, ...]) -> str:
    return "XHYP-" + hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12].upper()


def load_rows(path: Path, instrument: str) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as h:
        rows = [r for r in csv.DictReader(h) if str(r.get("instrument", "")).upper() == instrument.upper()]
    rows.sort(key=lambda r: (session_key(r), ts(r)))
    return rows


def ret_bps(a: float, b: float) -> float:
    return 0.0 if a <= 0 else (b-a)/a*10000.0


def rolling_range_bps(s: list[dict[str, Any]], start: int, end: int) -> float:
    q=s[max(0,start):end]
    if not q: return 1e9
    lo=min(f(x,"low") for x in q); hi=max(f(x,"high") for x in q); mid=(hi+lo)/2
    return 1e9 if mid<=0 else (hi-lo)/mid*10000.0


def generate(instrument: str) -> list[dict[str, Any]]:
    out=[]
    # opening drive continuation: strength of opening window then fresh break
    for direction in (1,-1):
      for open_bars in (2,3,6):
       for drive_bps in (15,25,40,60):
        for hold in (2,3,6,12):
         p=("opening_drive",instrument,direction,open_bars,drive_bps,hold)
         out.append({"id":stable_id(p),"family":"opening_drive","direction":direction,"open_bars":open_bars,"threshold_bps":drive_bps,"hold_bars":hold})
    # pullback after opening drive, followed by resumption
    for direction in (1,-1):
      for open_bars in (3,6):
       for drive_bps in (25,40,60):
        for retrace in (0.25,0.5,0.75):
         for hold in (3,6,12):
          p=("opening_pullback",instrument,direction,open_bars,drive_bps,retrace,hold)
          out.append({"id":stable_id(p),"family":"opening_pullback","direction":direction,"open_bars":open_bars,"threshold_bps":drive_bps,"retrace":retrace,"hold_bars":hold})
    # compression breakout using only previous bars
    for direction in (1,-1):
      for lookback in (3,6,12):
       for max_range in (20,35,50,75):
        for hold in (2,3,6,12):
         p=("compression_breakout",instrument,direction,lookback,max_range,hold)
         out.append({"id":stable_id(p),"family":"compression_breakout","direction":direction,"lookback":lookback,"threshold_bps":max_range,"hold_bars":hold})
    # k-bar momentum continuation
    for direction in (1,-1):
      for lookback in (2,3,6,12):
       for mom in (15,25,40,60):
        for hold in (2,3,6,12):
         p=("momentum_continuation",instrument,direction,lookback,mom,hold)
         out.append({"id":stable_id(p),"family":"momentum_continuation","direction":direction,"lookback":lookback,"threshold_bps":mom,"hold_bars":hold})
    # failed break of prior rolling range, then re-entry
    for direction in (1,-1):
      for lookback in (3,6,12):
       for min_excursion in (5,10,20):
        for hold in (2,3,6,12):
         p=("range_failure",instrument,direction,lookback,min_excursion,hold)
         out.append({"id":stable_id(p),"family":"range_failure","direction":direction,"lookback":lookback,"threshold_bps":min_excursion,"hold_bars":hold})
    return out


def signal(h: dict[str, Any], s: list[dict[str, Any]], i: int) -> bool:
    fam=h["family"]; d=h["direction"]; c=f(s[i],"close")
    if c<=0: return False
    if fam=="opening_drive":
        n=h["open_bars"]
        if i<n or len(s)<n+1: return False
        start=f(s[0],"open",f(s[0],"close")); end=f(s[n-1],"close")
        drive=d*ret_bps(start,end)
        if drive < h["threshold_bps"]: return False
        prior=s[:i]; ph=max(f(x,"high") for x in prior); pl=min(f(x,"low") for x in prior)
        return c>ph if d==1 else c<pl
    if fam=="opening_pullback":
        n=h["open_bars"]
        if i<=n: return False
        start=f(s[0],"open",f(s[0],"close")); drive_end=f(s[n-1],"close")
        drive=d*ret_bps(start,drive_end)
        if drive<h["threshold_bps"]: return False
        move=abs(drive_end-start)
        if move<=0: return False
        post=s[n:i]
        if not post: return False
        if d==1:
            pull=drive_end-min(f(x,"low") for x in post)
            return pull>=move*h["retrace"] and c>f(s[i-1],"high")
        pull=max(f(x,"high") for x in post)-drive_end
        return pull>=move*h["retrace"] and c<f(s[i-1],"low")
    if fam=="compression_breakout":
        n=h["lookback"]
        if i<n: return False
        prev=s[i-n:i]
        if rolling_range_bps(s,i-n,i)>h["threshold_bps"]: return False
        return c>max(f(x,"high") for x in prev) if d==1 else c<min(f(x,"low") for x in prev)
    if fam=="momentum_continuation":
        n=h["lookback"]
        if i<n: return False
        r=d*ret_bps(f(s[i-n],"close"),c)
        if r<h["threshold_bps"]: return False
        return c>f(s[i-1],"high") if d==1 else c<f(s[i-1],"low")
    if fam=="range_failure":
        n=h["lookback"]
        if i<n: return False
        prev=s[i-n:i]; ph=max(f(x,"high") for x in prev); pl=min(f(x,"low") for x in prev)
        hi=f(s[i],"high"); lo=f(s[i],"low")
        if d==1:
            excursion=ret_bps(lo,pl) if lo>0 and pl>lo else 0
            return lo<pl and c>pl and excursion>=h["threshold_bps"]
        excursion=ret_bps(ph,hi) if ph>0 and hi>ph else 0
        return hi>ph and c<ph and excursion>=h["threshold_bps"]
    return False


def max_dd(pnls:list[float])->float:
    e=p=dd=0.0
    for x in pnls:
        e+=x; p=max(p,e); dd=min(dd,e-p)
    return dd


def evaluate(h: dict[str, Any], sessions: dict[str,list[dict[str,Any]]], cost: float, min_trades: int) -> dict[str,Any]:
    pnls=[]; by=defaultdict(list)
    for sid,s in sorted(sessions.items()):
        i=1
        while i<len(s)-1:
            if signal(h,s,i):
                j=min(len(s)-1,i+int(h["hold_bars"]))
                if j>i:
                    entry=f(s[i],"close"); exit_=f(s[j],"close")
                    if entry>0:
                        pnl=h["direction"]*ret_bps(entry,exit_)-cost
                        pnls.append(pnl); by[sid].append(pnl); i=j+1; continue
            i+=1
    trades=len(pnls); wins=[x for x in pnls if x>0]; losses=[x for x in pnls if x<=0]
    exp=statistics.mean(pnls) if pnls else 0.0
    pf=sum(wins)/abs(sum(losses)) if losses and sum(losses)<0 else (math.inf if wins else 0.0)
    dd=max_dd(pnls); sessions_traded=len(by)
    max_ts=max((len(v) for v in by.values()),default=0); trade_share=max_ts/trades if trades else 0
    abs_s=[abs(sum(v)) for v in by.values()]; total=sum(abs_s); pnl_share=max(abs_s)/total if total else 0
    return {**h,"hypothesis_id":h["id"],"direction":"BUY_CE" if h["direction"]==1 else "BUY_PE","trades":trades,
      "sessions_traded":sessions_traded,"win_rate":round(len(wins)/trades,4) if trades else 0.0,
      "net_expectancy_bps":round(exp,4),"profit_factor":"INF" if math.isinf(pf) else round(pf,4),
      "max_drawdown_bps":round(dd,4),"top_session_trade_share":round(trade_share,6),
      "top_session_abs_pnl_share":round(pnl_share,6),"status":"PROMISING_NOT_CERTIFIED" if trades>=min_trades and exp>0 else "REJECTED",
      "certification":"NOT_CERTIFIED","runtime_authority":"NONE","broker_actions_allowed":False,"overlapping_trades_allowed":False,
      "pnl_semantics":"UNDERLYING_DIRECTION_PROXY_BPS","option_pnl_claimed":False}


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True); p.add_argument("--instrument",required=True)
    p.add_argument("--output-dir",required=True); p.add_argument("--min-trades",type=int,default=100); p.add_argument("--cost-bps",type=float,default=8.0)
    a=p.parse_args(argv)
    rows=load_rows(Path(a.input),a.instrument); sessions=defaultdict(list)
    for r in rows: sessions[session_key(r)].append(r)
    hs=generate(a.instrument); results=[evaluate(h,sessions,a.cost_bps,a.min_trades) for h in hs]
    results.sort(key=lambda x:(x["status"]=="PROMISING_NOT_CERTIFIED",x["net_expectancy_bps"],x["trades"]),reverse=True)
    run_id=datetime.now(timezone.utc).strftime("EXPANDED-STRICT-%Y%m%dT%H%M%SZ"); out=Path(a.output_dir)/run_id; out.mkdir(parents=True,exist_ok=True)
    (out/"results.json").write_text(json.dumps(results,indent=2,sort_keys=True)+"\n")
    with (out/"leaderboard.csv").open("w",newline="",encoding="utf-8") as h:
        w=csv.DictWriter(h,fieldnames=list(results[0].keys())); w.writeheader(); w.writerows(results)
    manifest={"schema_version":"tradebot-expanded-strict-screen-v1","run_id":run_id,"instrument":a.instrument.upper(),"input":str(Path(a.input).resolve()),
      "input_sha256":hashlib.sha256(Path(a.input).read_bytes()).hexdigest(),"loaded_rows":len(rows),"sessions":len(sessions),"hypotheses":len(hs),
      "promising_not_certified":sum(r["status"]=="PROMISING_NOT_CERTIFIED" for r in results),"min_trades":a.min_trades,"cost_bps":a.cost_bps,
      "families":sorted({h["family"] for h in hs}),"certification":"NOT_CERTIFIED","runtime_authority":"NONE","broker_actions_allowed":False}
    (out/"run_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    print(json.dumps(manifest,indent=2)); return 0

if __name__=="__main__": raise SystemExit(main())