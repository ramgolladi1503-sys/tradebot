#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('aggregate');p.add_argument('--sprint',required=True);p.add_argument('--round',required=True);a=p.parse_args();d=json.loads(Path(a.aggregate).read_text())
 findings=[]
 for r in d.get('reviews',[]):
  findings += [f for f in r.get('findings',[]) if f.get('severity') in {'CRITICAL','MAJOR','UNKNOWN'}]
 out={'sprint':a.sprint,'failed_head':d.get('candidate_head'),'review_round':a.round,'blocking_findings':findings,'repair_scope':{'allowed':['minimum changes required to resolve listed findings'],'forbidden':['weaken_fixture','change_acceptance_criteria','reuse_prior_head_reviews','begin_next_sprint','begin_M2','begin_M9','create_runtime_authority']}}
 print(json.dumps(out,indent=2,sort_keys=True))
if __name__=='__main__':main()
