#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,json,math
from collections import Counter,deque
from pathlib import Path

ENGINE_ID="BEHAVIOR_DISCOVERY_ENGINE_V2"
COMPONENT_ID="BEHAVIOR_STATE_ENGINE_V1"

def sha256(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def bps(a:float,b:float)->float|None:
    return (b/a-1.0)*10000.0 if math.isfinite(a) and math.isfinite(b) and a>0 else None

def load_rows(path:Path):
    with path.open(newline="",encoding="utf-8") as h: src=list(csv.DictReader(h))
    req={"timestamp","open","high","low","close"}
    if not src or not req.issubset(src[0]): raise ValueError("dataset_schema_mismatch")
    out=[]
    for r in src:
        try:o,h,l,c=(float(r[k]) for k in ("open","high","low","close"))
        except Exception:continue
        if min(o,h,l,c)<=0 or h<l:continue
        ts=r["timestamp"];out.append({"timestamp":ts,"session":r.get("session") or ts[:10],"open":o,"high":h,"low":l,"close":c})
    out.sort(key=lambda x:x["timestamp"]);return out

def _mean(xs):return sum(xs)/len(xs) if xs else None

def build_states(rows,cfg):
    rr_lb=int(cfg["rolling_range_lookback"]);ret_lb=int(cfg["rolling_return_lookback"]);ex_lb=int(cfg["recent_extreme_lookback"])
    out=[];session=None;ranges=deque(maxlen=rr_lb);absrets=deque(maxlen=ret_lb);recent=deque(maxlen=ex_lb)
    prior_close=None;prior_ret=None
    for idx,r in enumerate(rows):
        if r["session"]!=session:
            session=r["session"];ranges.clear();absrets.clear();recent.clear();prior_close=None;prior_ret=None
        o,h,l,c=r["open"],r["high"],r["low"],r["close"];rng=h-l;body=abs(c-o);upper=h-max(o,c);lower=min(o,c)-l
        bar_ret=bps(o,c);cc_ret=bps(prior_close,c) if prior_close is not None else None
        avg_range=_mean(list(ranges));avg_absret=_mean(list(absrets))
        range_ratio=rng/avg_range if avg_range and avg_range>0 else None
        body_fraction=body/rng if rng>0 else None;upper_frac=upper/rng if rng>0 else None;lower_frac=lower/rng if rng>0 else None
        prior_high=max((x["high"] for x in recent),default=None);prior_low=min((x["low"] for x in recent),default=None)
        up_escape=bps(prior_high,c) if prior_high is not None else None;down_escape=bps(prior_low,c) if prior_low is not None else None
        states=[]
        if range_ratio is not None and range_ratio<=float(cfg["compression_ratio_max"]):states.append("COMPRESSION")
        if range_ratio is not None and range_ratio>=float(cfg["expansion_ratio_min"]):states.append("EXPANSION")
        if body_fraction is not None and body_fraction>=float(cfg["strong_body_fraction_min"]):
            states.append("DIRECTIONAL_UP" if c>o else "DIRECTIONAL_DOWN" if c<o else "BALANCED_BODY")
        if upper_frac is not None and upper_frac>=float(cfg["rejection_wick_fraction_min"]):states.append("UPPER_REJECTION")
        if lower_frac is not None and lower_frac>=float(cfg["rejection_wick_fraction_min"]):states.append("LOWER_REJECTION")
        esc=float(cfg["escape_threshold_bps"])
        if up_escape is not None and up_escape>=esc:states.append("UPSIDE_ESCAPE")
        if down_escape is not None and down_escape<=-esc:states.append("DOWNSIDE_ESCAPE")
        if cc_ret is not None and prior_ret is not None and abs(prior_ret)>0:
            ratio=abs(cc_ret)/abs(prior_ret)
            if ratio>=float(cfg["acceleration_ratio_min"]) and cc_ret*prior_ret>0:states.append("DIRECTIONAL_ACCELERATION")
            if ratio<=float(cfg["deceleration_ratio_max"]) and cc_ret*prior_ret>0:states.append("DIRECTIONAL_DECELERATION")
        if prior_high is not None and h>prior_high and c<=prior_high:
            rej=bps(prior_high,c)
            if rej is not None and rej<=-float(cfg["recovery_threshold_bps"]):states.append("FAILED_UPSIDE_ESCAPE")
        if prior_low is not None and l<prior_low and c>=prior_low:
            rec=bps(prior_low,c)
            if rec is not None and rec>=float(cfg["recovery_threshold_bps"]):states.append("FAILED_DOWNSIDE_ESCAPE")
        if prior_high is not None and prior_low is not None and prior_high>prior_low:
            loc=(c-prior_low)/(prior_high-prior_low)
            if 0.40<=loc<=0.60:states.append("RANGE_BALANCE")
        out.append({"row_index":idx,"timestamp":r["timestamp"],"session":r["session"],"confirmation_timestamp":r["timestamp"],
                    "states":sorted(set(states)),"features":{"bar_return_bps":bar_ret,"close_to_close_return_bps":cc_ret,
                    "range":rng,"range_ratio":range_ratio,"body_fraction":body_fraction,"upper_wick_fraction":upper_frac,
                    "lower_wick_fraction":lower_frac,"prior_high":prior_high,"prior_low":prior_low,"up_escape_bps":up_escape,
                    "down_escape_bps":down_escape,"avg_abs_return_bps":avg_absret}})
        ranges.append(rng);recent.append(r)
        if cc_ret is not None:absrets.append(abs(cc_ret));prior_ret=cc_ret
        prior_close=c
    return out

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument("--repo-root",default=".");ap.add_argument("--input",default="research/hypotheses/historical_corpus/kite_nifty_cache_v2/canonical/NIFTY.csv")
    ap.add_argument("--contract",default="research/strategy_certification/BEHAVIOR_DISCOVERY_ENGINE_V2.json")
    ap.add_argument("--output",default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_states_v1.jsonl");a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve();ip=Path(a.input);ip=ip if ip.is_absolute() else root/ip;cp=root/a.contract;op=root/a.output
    res={"status":"FAIL_CLOSED","engine_id":ENGINE_ID,"component_id":COMPONENT_ID,"runtime_authority":"NONE","broker_actions_permitted":False,"edge_claimed":False,"forward_outcomes_computed":False,"locked_outcomes_accessed":False}
    try:
        cfg=json.loads(cp.read_text())
        if cfg.get("engine_id")!=ENGINE_ID or cfg.get("component_id")!=COMPONENT_ID:raise ValueError("contract_identity_mismatch")
        if cfg.get("forward_outcomes_permitted") or cfg.get("locked_outcomes_permitted"):raise ValueError("outcome_authority_must_be_false")
        if sha256(ip)!=cfg["dataset_sha256"]:raise ValueError("dataset_hash_mismatch")
        rows=load_rows(ip);states=build_states(rows,cfg);op.parent.mkdir(parents=True,exist_ok=True)
        op.write_text("".join(json.dumps(x,sort_keys=True,separators=(",",":"))+"\n" for x in states),encoding="utf-8")
        counts=Counter(s for x in states for s in x["states"])
        res.update({"status":"DISCOVERY_CORPUS_BUILT","input_path":str(ip),"input_sha256":sha256(ip),"contract_sha256":sha256(cp),
                    "rows":len(rows),"sessions":len({r["session"] for r in rows}),"state_rows":len(states),"state_counts":dict(sorted(counts.items())),
                    "output_path":str(op),"output_sha256":sha256(op),"interpretation":"Causal observable behavior-state corpus only. No forward returns, excursions, profitability labels, entry/exit rules, or edge claims are computed."})
    except Exception as e:res["error"]=f"{type(e).__name__}:{e}"
    sp=op.parent/"NIFTY_behavior_states_v1_summary.json";sp.parent.mkdir(parents=True,exist_ok=True);sp.write_text(json.dumps(res,indent=2,sort_keys=True)+"\n")
    print(json.dumps(res,indent=2));return 0 if res["status"]=="DISCOVERY_CORPUS_BUILT" else 2
if __name__=="__main__":raise SystemExit(main())
