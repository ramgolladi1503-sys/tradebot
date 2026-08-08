#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from native_evidence import validate_native_evidence
from program_context import load_and_validate_context
ACCEPT={'PASS','PASS_WITH_MINOR_FINDINGS'}
ROOT=Path(__file__).resolve().parents[2]

def authorize(*,sprint,next_sprint,candidate_head,review,audit,native,context_errors):
 errors=list(context_errors)
 if review.get('candidate_head')!=candidate_head:errors.append('REVIEW_AGGREGATE_HEAD_MISMATCH')
 if audit.get('candidate_head')!=candidate_head:errors.append('AUDIT_AGGREGATE_HEAD_MISMATCH')
 if validate_native_evidence(native,candidate_head):errors.append('NATIVE_VALIDATION_NOT_PASS_FOR_HEAD')
 if review.get('decision') not in ACCEPT:errors.append('REVIEW_BOARD_NOT_ACCEPTED')
 if audit.get('decision') not in ACCEPT:errors.append('AUDIT_BOARD_NOT_ACCEPTED')
 if review.get('critical',0) or review.get('major',0) or review.get('unknown',0):errors.append('REVIEW_BLOCKING_FINDINGS_PRESENT')
 if audit.get('critical',0) or audit.get('major',0) or audit.get('unknown',0):errors.append('AUDIT_BLOCKING_FINDINGS_PRESENT')
 if review.get('runtime_authority')!='NONE' or audit.get('runtime_authority')!='NONE':errors.append('BOARD_RUNTIME_AUTHORITY_INVALID')
 if review.get('authority')!='Research / R' or audit.get('authority')!='Research / R':errors.append('BOARD_AUTHORITY_INVALID')
 if not isinstance(next_sprint,str) or not next_sprint.startswith('S') or not next_sprint[1:].isdigit():errors.append('NEXT_SPRINT_INVALID')
 elif int(next_sprint[1:])>=111:errors.append('M9_HARD_STOP')
 if errors:return {'advance':False,'errors':sorted(set(errors)),'runtime_authority':'NONE','authority':'Research / R'}
 return {'advance':True,'accepted_sprint':sprint,'accepted_head':candidate_head,'next_sprint':next_sprint,'runtime_authority':'NONE','authority':'Research / R'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--sprint',required=True);p.add_argument('--next-sprint',required=True);p.add_argument('--candidate-head',required=True);p.add_argument('--review-aggregate',required=True);p.add_argument('--audit-aggregate',required=True);p.add_argument('--native-evidence',required=True);p.add_argument('--acceptance-trace',required=True);p.add_argument('--program-state',default=str(ROOT/'research/program/MROS_PROGRAM_STATE.yaml'));p.add_argument('--sprint-ledger',default=str(ROOT/'research/program/SPRINT_LEDGER.jsonl'));a=p.parse_args()
 review=json.loads(Path(a.review_aggregate).read_text());audit=json.loads(Path(a.audit_aggregate).read_text());native=json.loads(Path(a.native_evidence).read_text())
 context_errors=load_and_validate_context(state_path=Path(a.program_state),ledger_path=Path(a.sprint_ledger),acceptance_path=Path(a.acceptance_trace),sprint=a.sprint,next_sprint=a.next_sprint,candidate_head=a.candidate_head)
 out=authorize(sprint=a.sprint,next_sprint=a.next_sprint,candidate_head=a.candidate_head,review=review,audit=audit,native=native,context_errors=context_errors)
 print(json.dumps(out,sort_keys=True))
 if not out['advance']:raise SystemExit(1)
 print('ADVANCEMENT_AUTHORIZATION_ONLY: ledger/state mutation must be performed as a separate evidenced commit.')
if __name__=='__main__':main()
