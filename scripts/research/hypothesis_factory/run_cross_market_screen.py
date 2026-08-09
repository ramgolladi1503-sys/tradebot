#!/usr/bin/env python3
"""Cross-market causal research-only hypothesis screen.

Target: BANKNIFTY. Predictors: synchronized NIFTY and SENSEX features from the
exact-intersection cross-market matrix. Uses only current/prior information,
non-overlapping time-stop exits, explicit costs, and minimum-trade gating.

Never certifies edge and never grants runtime or broker authority.
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
def rbps(a: float, b: float) -> float: return 0.0 if a <= 0 else (b-a)/a*10000.0

def hid(parts: tuple[Any, ...]) -> str:
    return "CHYP-" + hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12].upper()


def load(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as h:
        rows=list(csv.DictReader(h))
    rows.sort(key=lambda r:(sk(r),ts(r))); return rows


def generate() -> list[dict[str, Any]]:
    out=[]
    families=("leader_consensus","nifty_lead","sensex_lead","relative_strength","cross_market_divergence")
    for fam in families:
      for direction in (1,-1):
       for threshold in (5,10,20,35,50):
        for hold in (2,3,6,12):
         for lookback in (1,2,3,6):
          p=(fam,direction,threshold,hold,lookback)
          out.append({"id":hid(p),"family":fam,"direction":direction,"threshold_bps":threshold,"hold_bars":hold,"lookback":lookback})
    return out


def _ret_over(s: list[dict[str, Any]], i: int, n: int, prefix: str) -> float:
    if i < n: return 0.0
    a=f(s[i-n],f"{prefix}_close"); b=f(s[i],f"{prefix}_close")
    return rbps(a,b)


def signal(h: dict[str, Any], s: list[dict[str, Any]], i: int) -> bool:
    n=h["lookback"]
    if i < n: return False
    d=h["direction"]; th=h["threshold_bps"]; fam=h["family"]
    br=_ret_over(s,i,n,"banknifty"); nr=_ret_over(s,i,n,"nifty"); sr=_ret_over(s,i,n,"sensex")
    if fam=="leader_consensus":
        return d*nr>=th and d*sr>=th and d*br>=0
    if fam=="nifty_lead":
        return d*nr>=th and d*br < d*nr
    if fam=="sensex_lead":
        return d*sr>=th and d*br < d*sr
    if fam=="relative_strength":
        # BANKNIFTY outruns the average leader in the same direction.
        leaders=(nr+sr)/2.0
        return d*br>=th and d*(br-leaders)>=th
    if fam=="cross_market_divergence":
        # leaders agree in one direction while BANKNIFTY is materially opposite/lagging.
        leader=(nr+sr)/2.0
        return d*leader>=th and d*br<=0
    return False


def mdd(xs:list[float])->float:
    e=p=dd=0.0
    for x in xs:
        e+=x; p=max(p,e); dd=min(dd,e-p)
    return dd


def evaluate(h:dict[str,Any], sessions:dict[str,list[dict[str,Any]]], cost:float, min_trades:int)->dict[str,Any]:
    pnls=[]; by=defaultdict(list)
    for day,s in sorted(sessions.items()):
        i=1
        while i<len(s)-1:
            if signal(h,s,i):
                j=min(len(s)-1,i+h["hold_bars"])
                if j>i:
                    entry=f(s[i],"banknifty_close"); exit_=f(s[j],"banknifty_close")
                    if entry>0:
                        pnl=h["direction"]*rbps(entry,exit_)-cost
                        pnls.append(pnl); by[day].append(pnl); i=j+1; continue
            i+=1
    n=len(pnls); wins=[x for x in pnls if x>0]; losses=[x for x in pnls if x<=0]
    exp=statistics.mean(pnls) if pnls else 0.0
    pf=sum(wins)/abs(sum(losses)) if losses and sum(losses)<0 else (math.inf if wins else 0.0)
    max_ts=max((len(v) for v in by.values()),default=0)
    abs_s=[abs(sum(v)) for v in by.values()]; total=sum(abs_s)
    return {**h,"hypothesis_id":h["id"],"direction":"BUY_CE" if h["direction"]==1 else "BUY_PE",
      "trades":n,"sessions_traded":len(by),"win_rate":round(len(wins)/n,4) if n else 0.0,
      "net_expectancy_bps":round(exp,4),"profit_factor":"INF" if math.isinf(pf) else round(pf,4),
      "max_drawdown_bps":round(mdd(pnls),4),"top_session_trade_share":round(max_ts/n,6) if n else 0.0,
      "top_session_abs_pnl_share":round(max(abs_s)/total,6) if total else 0.0,
      "status":"PROMISING_NOT_CERTIFIED" if n>=min_trades and exp>0 else "REJECTED",
      "certification":"NOT_CERTIFIED","runtime_authority":"NONE","broker_actions_allowed":False,
      "overlapping_trades_allowed":False,"pnl_semantics":"BANKNIFTY_UNDERLYING_DIRECTION_PROXY_BPS","option_pnl_claimed":False}


def write_csv(path:Path, rows:list[dict[str,Any]])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    if not rows: path.write_text("",encoding="utf-8"); return
    fields=sorted({k for r in rows for k in r})
    with path.open("w",newline="",encoding="utf-8") as h:
        w=csv.DictWriter(h,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(rows)


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True); p.add_argument("--output-dir",required=True)
    p.add_argument("--min-trades",type=int,default=100); p.add_argument("--cost-bps",type=float,default=8.0)
    a=p.parse_args(argv)
    rows=load(Path(a.input)); sessions=defaultdict(list)
    for r in rows: sessions[sk(r)].append(r)
    hs=generate(); results=[evaluate(h,sessions,a.cost_bps,a.min_trades) for h in hs]
    results.sort(key=lambda x:(x["status"]=="PROMISING_NOT_CERTIFIED",x["net_expectancy_bps"],x["trades"]),reverse=True)
    run_id=datetime.now(timezone.utc).strftime("CROSS-STRICT-%Y%m%dT%H%M%SZ"); out=Path(a.output_dir)/run_id; out.mkdir(parents=True,exist_ok=True)
    (out/"results.json").write_text(json.dumps(results,indent=2,sort_keys=True)+"\n",encoding="utf-8"); write_csv(out/"leaderboard.csv",results)
    manifest={"schema_version":"tradebot-cross-market-screen-v1","run_id":run_id,"input":str(Path(a.input).resolve()),
      "input_sha256":hashlib.sha256(Path(a.input).read_bytes()).hexdigest(),"loaded_rows":len(rows),"sessions":len(sessions),"hypotheses":len(hs),
      "promising_not_certified":sum(r["status"]=="PROMISING_NOT_CERTIFIED" for r in results),"min_trades":a.min_trades,"cost_bps":a.cost_bps,
      "families":sorted({h["family"] for h in hs}),"certification":"NOT_CERTIFIED","runtime_authority":"NONE","broker_actions_allowed":False}
    (out/"run_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(json.dumps(manifest,indent=2)); return 0

if __name__=="__main__": raise SystemExit(main())
