#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys
from pathlib import Path
def load(path):
    s=importlib.util.spec_from_file_location("episode_graph_v1",path);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);return m
def main():
    root=Path(__file__).resolve().parents[3];m=load(root/"scripts/research/hypothesis_factory/build_behavior_episode_graph_v1.py")
    def x(i,states,s="2026-01-01"):return {"row_index":i,"timestamp":f"{s}T09:{15+i:02d}:00","session":s,"confirmation_timestamp":f"{s}T09:{15+i:02d}:00","states":states,"features":{}}
    rows=[x(0,["COMPRESSION"]),x(1,["COMPRESSION"]),x(2,["LOWER_REJECTION"]),x(3,[]),x(4,["EXPANSION"]),x(5,[]),x(6,[]),x(7,["DIRECTIONAL_UP"])]
    a=m.build_episodes(rows,1);b=m.build_episodes(rows,1);checks=[]
    def ck(n,v):checks.append({"check":n,"status":"PASS" if v else "FAIL"})
    ck("ADJACENT_DUPLICATES_COLLAPSED",a[0]["state_sequence"].count("COMPRESSION")==1)
    ck("ONE_BAR_GAP_BRIDGED",a[0]["end_row_index"]==4)
    ck("LARGER_GAP_SPLITS_EPISODE",len(a)==2 and a[1]["start_row_index"]==7)
    ck("FIRST_OBSERVABLE_CAUSAL",a[0]["first_observable_timestamp"]==rows[0]["confirmation_timestamp"])
    second=[x(0,["EXPANSION"],"2026-01-02")];mix=m.build_episodes(rows[:3]+second,1)
    ck("SESSION_BOUNDARY_ISOLATION",len(mix)==2 and mix[1]["session"]=="2026-01-02")
    ck("RERUN_DETERMINISM",a==b)
    prefix=m.build_episodes(rows[:5],1);ck("PREFIX_EPISODE_REPRODUCIBLE",prefix[0]==a[0])
    failed=[c["check"] for c in checks if c["status"]!="PASS"]
    res={"status":"BEHAVIOR_EPISODE_GRAPH_V1_VALIDATION_PASS" if not failed else "BEHAVIOR_EPISODE_GRAPH_V1_VALIDATION_FAIL","checks_total":len(checks),"checks_passed":len(checks)-len(failed),"checks_failed":len(failed),"failed_checks":failed,"checks":checks,"runtime_authority":"NONE","broker_actions_permitted":False,"edge_claimed":False}
    print(json.dumps(res,indent=2));return 0 if not failed else 2
if __name__=="__main__":raise SystemExit(main())
