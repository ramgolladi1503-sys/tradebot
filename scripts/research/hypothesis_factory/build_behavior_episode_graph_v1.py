#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from collections import Counter
from pathlib import Path

COMPONENT_ID="BEHAVIOR_EPISODE_GRAPH_V1"

def sha256(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load_jsonl(p):
    return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]

def build_episodes(state_rows,max_gap_bars=1):
    episodes=[];cur=None;last_active_index=None
    for row in state_rows:
        active=bool(row.get("states"))
        if cur is not None and row["session"]!=cur["session"]:
            episodes.append(cur);cur=None;last_active_index=None
        if not active:
            if cur is not None and last_active_index is not None and row["row_index"]-last_active_index>max_gap_bars:
                episodes.append(cur);cur=None;last_active_index=None
            continue
        if cur is None:
            cur={"session":row["session"],"start_row_index":row["row_index"],"end_row_index":row["row_index"],
                 "start_timestamp":row["timestamp"],"end_timestamp":row["timestamp"],"first_observable_timestamp":row["confirmation_timestamp"],
                 "state_sequence":[],"state_sets":[],"duration_bars":1}
        elif last_active_index is not None and row["row_index"]-last_active_index>max_gap_bars+1:
            episodes.append(cur)
            cur={"session":row["session"],"start_row_index":row["row_index"],"end_row_index":row["row_index"],
                 "start_timestamp":row["timestamp"],"end_timestamp":row["timestamp"],"first_observable_timestamp":row["confirmation_timestamp"],
                 "state_sequence":[],"state_sets":[],"duration_bars":1}
        state_set=tuple(sorted(set(row["states"])))
        if not cur["state_sets"] or tuple(cur["state_sets"][-1])!=state_set:
            cur["state_sets"].append(list(state_set))
            for s in state_set:
                if not cur["state_sequence"] or cur["state_sequence"][-1]!=s:cur["state_sequence"].append(s)
        cur["end_row_index"]=row["row_index"];cur["end_timestamp"]=row["timestamp"];cur["duration_bars"]=cur["end_row_index"]-cur["start_row_index"]+1
        last_active_index=row["row_index"]
    if cur is not None:episodes.append(cur)
    for i,e in enumerate(episodes,1):
        e["episode_id"]=f"{e['session']}::E{i:05d}"
        e["transition_count"]=max(0,len(e["state_sets"])-1)
    return episodes

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument("--repo-root",default=".")
    ap.add_argument("--input",default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_states_v1.jsonl")
    ap.add_argument("--output",default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_episodes_v1.jsonl")
    ap.add_argument("--max-gap-bars",type=int,default=1);a=ap.parse_args(argv)
    root=Path(a.repo_root).resolve();ip=root/a.input;op=root/a.output
    res={"status":"FAIL_CLOSED","component_id":COMPONENT_ID,"runtime_authority":"NONE","broker_actions_permitted":False,"edge_claimed":False,"forward_outcomes_computed":False,"locked_outcomes_accessed":False}
    try:
        rows=load_jsonl(ip)
        forbidden={"forward_return","future_return","pnl","profit","outcome","target"}
        if any(any(f in json.dumps(x).lower() for f in forbidden) for x in rows):raise ValueError("outcome_like_input_rejected")
        episodes=build_episodes(rows,a.max_gap_bars);op.parent.mkdir(parents=True,exist_ok=True)
        op.write_text("".join(json.dumps(x,sort_keys=True,separators=(",",":"))+"\n" for x in episodes),encoding="utf-8")
        seq=Counter(">".join(e["state_sequence"]) for e in episodes)
        res.update({"status":"DISCOVERY_EPISODE_GRAPH_BUILT","input_sha256":sha256(ip),"input_rows":len(rows),"episodes":len(episodes),
                    "sessions":len({e["session"] for e in episodes}),"unique_state_sequences":len(seq),"output_sha256":sha256(op),
                    "interpretation":"Outcome-free causal episode graph. Adjacent state observations are collapsed into coherent session-local episodes."})
    except Exception as e:res["error"]=f"{type(e).__name__}:{e}"
    sp=op.parent/"NIFTY_behavior_episodes_v1_summary.json";sp.parent.mkdir(parents=True,exist_ok=True);sp.write_text(json.dumps(res,indent=2,sort_keys=True)+"\n")
    print(json.dumps(res,indent=2));return 0 if res["status"]=="DISCOVERY_EPISODE_GRAPH_BUILT" else 2
if __name__=="__main__":raise SystemExit(main())
