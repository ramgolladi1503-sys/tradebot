#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys
from pathlib import Path

def load_module(path):
    spec=importlib.util.spec_from_file_location("behavior_states_v1",path);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

def main():
    root=Path(__file__).resolve().parents[3];m=load_module(root/"scripts/research/hypothesis_factory/build_behavior_states_v1.py")
    cfg={"rolling_range_lookback":3,"rolling_return_lookback":3,"recent_extreme_lookback":3,"compression_ratio_max":0.70,"expansion_ratio_min":1.60,
         "strong_body_fraction_min":0.65,"rejection_wick_fraction_min":0.45,"escape_threshold_bps":8.0,"recovery_threshold_bps":6.0,
         "acceleration_ratio_min":1.50,"deceleration_ratio_max":0.60}
    def r(i,o,h,l,c,s="2026-01-01"):return {"timestamp":f"{s}T09:{15+i:02d}:00","session":s,"open":o,"high":h,"low":l,"close":c}
    rows=[r(0,100,100.1,99.9,100),r(1,100,100.2,99.9,100.1),r(2,100.1,100.25,100,100.2),r(3,100.2,100.7,100.15,100.65),r(4,100.65,100.8,100.2,100.3),r(5,100.3,100.35,99.7,100.15)]
    checks=[]
    def ck(n,v,d=None):checks.append({"check":n,"status":"PASS" if v else "FAIL","detail":d})
    full=m.build_states(rows,cfg)
    for t in range(len(rows)):
        pref=m.build_states(rows[:t+1],cfg)
        ck(f"PREFIX_REPRODUCIBLE_{t}",pref[-1]==full[t])
    extended=rows+[r(6,100.15,105,100,104.8),r(7,104.8,105,98,99)]
    ext=m.build_states(extended,cfg)
    ck("FUTURE_EXTENSION_INVARIANCE",ext[:len(rows)]==full)
    ck("CONFIRMATION_TIMESTAMP_IS_CURRENT_BAR",all(x["confirmation_timestamp"]==x["timestamp"] for x in full))
    second=[r(0,200,200.2,199.8,200,"2026-01-02"),r(1,200,200.4,199.9,200.3,"2026-01-02")]
    mixed=m.build_states(rows+second,cfg);first2=m.build_states(second,cfg)
    ck("SESSION_BOUNDARY_ISOLATION",mixed[-2:]==[{**x,"row_index":x["row_index"]+len(rows)} for x in first2])
    rerun=m.build_states(rows,cfg);ck("RERUN_DETERMINISM",rerun==full)
    forbidden={"forward_return","future_return","forward_excursion","pnl","profit","label","target","outcome"}
    keys=set()
    for x in full:keys.update(x.keys());keys.update(x["features"].keys())
    ck("NO_OUTCOME_FEATURE_NAMES",not any(any(f in k.lower() for f in forbidden) for k in keys),sorted(keys))
    ck("STATE_LIST_CANONICAL_ORDER",all(x["states"]==sorted(set(x["states"])) for x in full))
    failed=[x["check"] for x in checks if x["status"]!="PASS"]
    res={"schema_version":1,"status":"BEHAVIOR_STATE_ENGINE_V1_VALIDATION_PASS" if not failed else "BEHAVIOR_STATE_ENGINE_V1_VALIDATION_FAIL",
         "checks_total":len(checks),"checks_passed":len(checks)-len(failed),"checks_failed":len(failed),"failed_checks":failed,"checks":checks,
         "runtime_authority":"NONE","broker_actions_permitted":False,"edge_claimed":False,"forward_outcomes_computed":False}
    print(json.dumps(res,indent=2));return 0 if not failed else 2
if __name__=="__main__":raise SystemExit(main())
