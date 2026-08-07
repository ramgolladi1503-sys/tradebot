#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
ACCEPT={'PASS','PASS_WITH_MINOR_FINDINGS'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--sprint',required=True);p.add_argument('--next-sprint',required=True);p.add_argument('--candidate-head',required=True);p.add_argument('--review-aggregate',required=True);p.add_argument('--audit-aggregate',required=True);p.add_argument('--native-evidence',required=True);p.add_argument('--acceptance-criteria-satisfied',action='store_true');p.add_argument('--state-consistent',action='store_true');a=p.parse_args()
 review=json.loads(Path(a.review_aggregate).read_text());audit=json.loads(Path(a.audit_aggregate).read_text());native=json.loads(Path(a.native_evidence).read_text())
 errors=[]
 if review.get('candidate_head')!=a.candidate_head:errors.append('REVIEW_AGGREGATE_HEAD_MISMATCH')
 if audit.get('candidate_head')!=a.candidate_head:errors.append('AUDIT_AGGREGATE_HEAD_MISMATCH')
 if native.get('head')!=a.candidate_head or native.get('failed')!=0 or native.get('exit_code')!=0 or native.get('passed')!=native.get('checks'):errors.append('NATIVE_VALIDATION_NOT_PASS_FOR_HEAD')
 if review.get('decision') not in ACCEPT:errors.append('REVIEW_BOARD_NOT_ACCEPTED')
 if audit.get('decision') not in ACCEPT:errors.append('AUDIT_BOARD_NOT_ACCEPTED')
 if review.get('critical',0) or review.get('major',0) or review.get('unknown',0):errors.append('REVIEW_BLOCKING_FINDINGS_PRESENT')
 if audit.get('critical',0) or audit.get('major',0) or audit.get('unknown',0):errors.append('AUDIT_BLOCKING_FINDINGS_PRESENT')
 if not a.acceptance_criteria_satisfied:errors.append('SPRINT_ACCEPTANCE_CRITERIA_NOT_SATISFIED')
 if not a.state_consistent:errors.append('PROGRAM_STATE_LEDGER_CONSISTENCY_NOT_PROVEN')
 if a.next_sprint.startswith('S') and int(a.next_sprint[1:])>=111:errors.append('M9_HARD_STOP')
 if errors:
  print(json.dumps({'advance':False,'errors':errors},sort_keys=True));raise SystemExit(1)
 print(json.dumps({'advance':True,'accepted_sprint':a.sprint,'accepted_head':a.candidate_head,'next_sprint':a.next_sprint,'runtime_authority':'NONE'},sort_keys=True))
 print('ADVANCEMENT_AUTHORIZATION_ONLY: ledger/state mutation must be performed as a separate evidenced commit.')
if __name__=='__main__':main()
