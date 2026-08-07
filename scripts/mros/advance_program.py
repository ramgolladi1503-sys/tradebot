#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ACCEPT={'PASS','PASS_WITH_MINOR_FINDINGS'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--sprint',required=True);p.add_argument('--next-sprint',required=True);p.add_argument('--candidate-head',required=True);p.add_argument('--aggregate',required=True);p.add_argument('--native-evidence',required=True);p.add_argument('--acceptance-criteria-satisfied',action='store_true');a=p.parse_args()
 agg=json.loads(Path(a.aggregate).read_text());native=json.loads(Path(a.native_evidence).read_text())
 errors=[]
 if agg.get('candidate_head')!=a.candidate_head:errors.append('AGGREGATE_HEAD_MISMATCH')
 if native.get('head')!=a.candidate_head or native.get('failed')!=0 or native.get('exit_code')!=0:errors.append('NATIVE_VALIDATION_NOT_PASS_FOR_HEAD')
 if agg.get('decision') not in ACCEPT:errors.append('REVIEW_BOARD_NOT_ACCEPTED')
 if not a.acceptance_criteria_satisfied:errors.append('SPRINT_ACCEPTANCE_CRITERIA_NOT_SATISFIED')
 if a.next_sprint.startswith('S') and int(a.next_sprint[1:])>=111:errors.append('M9_HARD_STOP')
 if errors:
  print(json.dumps({'advance':False,'errors':errors},sort_keys=True));raise SystemExit(1)
 print(json.dumps({'advance':True,'accepted_sprint':a.sprint,'accepted_head':a.candidate_head,'next_sprint':a.next_sprint,'runtime_authority':'NONE'},sort_keys=True))
 print('ADVANCEMENT_AUTHORIZATION_ONLY: ledger/state mutation must be performed as a separate evidenced commit.')
if __name__=='__main__':main()
