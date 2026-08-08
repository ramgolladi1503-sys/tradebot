#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from pathlib import Path
from native_evidence import validate_native_evidence
from program_context import load_and_validate_context
ACCEPT={'PASS','PASS_WITH_MINOR_FINDINGS'};ROOT=Path(__file__).resolve().parents[2];SPRINT=re.compile(r'^S([0-9]{3})$')

def _nonneg_int(value):return isinstance(value,int) and not isinstance(value,bool) and value>=0

def _validate_aggregate(data:object,*,candidate_head:str,kind:str)->list[str]:
 e=[];prefix=kind.upper()
 if not isinstance(data,dict):return [f'{prefix}_AGGREGATE_OBJECT_REQUIRED']
 if data.get('candidate_head')!=candidate_head:e.append(f'{prefix}_AGGREGATE_HEAD_MISMATCH')
 if data.get('decision') not in ACCEPT:e.append(f'{prefix}_BOARD_NOT_ACCEPTED')
 if data.get('runtime_authority')!='NONE':e.append(f'{prefix}_RUNTIME_AUTHORITY_INVALID')
 if data.get('authority')!='Research / R':e.append(f'{prefix}_AUTHORITY_INVALID')
 if data.get('transport')!='mac_git_mailbox':e.append(f'{prefix}_TRANSPORT_INVALID')
 plural='reviews' if kind=='review' else 'audits';valid_key='valid_reviews' if kind=='review' else 'valid_audits';invalid_key='invalid_reviews' if kind=='review' else 'invalid_audits';expected_key='expected_reviews' if kind=='review' else 'expected_audits';submitted_key='submitted_reviews' if kind=='review' else 'submitted_audits';omitted_key='omitted_reviews' if kind=='review' else 'omitted_audits';extra_key='extra_reviews' if kind=='review' else 'extra_audits';minimum_key='minimum_valid_reviews' if kind=='review' else 'minimum_valid_audits'
 items=data.get(plural)
 if not isinstance(items,list):e.append(f'{prefix}_ITEMS_INVALID');items=[]
 for key in (valid_key,invalid_key,expected_key,submitted_key,minimum_key,'critical','major','minor','unknown'):
  if not _nonneg_int(data.get(key)):e.append(f'{prefix}_{key.upper()}_INVALID')
 if _nonneg_int(data.get(valid_key)) and data.get(valid_key)!=len(items):e.append(f'{prefix}_VALID_COUNT_MISMATCH')
 if _nonneg_int(data.get(invalid_key)) and data.get(invalid_key)!=0:e.append(f'{prefix}_INVALID_ARTIFACTS_PRESENT')
 if not isinstance(data.get(omitted_key),list) or data.get(omitted_key):e.append(f'{prefix}_OMITTED_ARTIFACTS_PRESENT')
 if not isinstance(data.get(extra_key),list) or data.get(extra_key):e.append(f'{prefix}_EXTRA_ARTIFACTS_PRESENT')
 if not isinstance(data.get('manifest_errors'),list) or data.get('manifest_errors'):e.append(f'{prefix}_MANIFEST_ERRORS_PRESENT')
 if all(_nonneg_int(data.get(k)) for k in (valid_key,expected_key,submitted_key,minimum_key)):
  if data[valid_key]<data[minimum_key]:e.append(f'{prefix}_QUORUM_NOT_MET')
  if data[expected_key]!=data[submitted_key] or data[expected_key]!=data[valid_key]:e.append(f'{prefix}_DENOMINATOR_MISMATCH')
 if any(data.get(k,0) for k in ('critical','major','unknown')):e.append(f'{prefix}_BLOCKING_FINDINGS_PRESENT')
 seen_jobs=set();seen_roles=set()
 for i,item in enumerate(items):
  if not isinstance(item,dict):e.append(f'{prefix}_ITEM_{i}_INVALID');continue
  if item.get('candidate_head')!=candidate_head:e.append(f'{prefix}_ITEM_{i}_HEAD_MISMATCH')
  jid=item.get('execution_job_id');role=item.get('execution_role_id')
  if not isinstance(jid,str) or not jid:e.append(f'{prefix}_ITEM_{i}_JOB_ID_INVALID')
  elif jid in seen_jobs:e.append(f'{prefix}_DUPLICATE_JOB_ID')
  else:seen_jobs.add(jid)
  if not isinstance(role,str) or not role:e.append(f'{prefix}_ITEM_{i}_ROLE_INVALID')
  elif role in seen_roles:e.append(f'{prefix}_DUPLICATE_ROLE')
  else:seen_roles.add(role)
 if kind=='audit':
  if not isinstance(data.get('missing_acceptance_ids'),list) or data.get('missing_acceptance_ids'):e.append('AUDIT_ACCEPTANCE_COVERAGE_INCOMPLETE')
  if data.get('unknown_acceptance_ids') not in (None,[]):e.append('AUDIT_ACCEPTANCE_COVERAGE_UNKNOWN_IDS')
 return e

def authorize(*,sprint,next_sprint,candidate_head,review,audit,native,context_errors):
 errors=list(context_errors)
 errors.extend(_validate_aggregate(review,candidate_head=candidate_head,kind='review'))
 errors.extend(_validate_aggregate(audit,candidate_head=candidate_head,kind='audit'))
 if validate_native_evidence(native,candidate_head):errors.append('NATIVE_VALIDATION_NOT_PASS_FOR_HEAD')
 sm=SPRINT.fullmatch(str(sprint));nm=SPRINT.fullmatch(str(next_sprint))
 if not sm:errors.append('SPRINT_INVALID')
 if not nm:errors.append('NEXT_SPRINT_INVALID')
 if sm and int(sm.group(1))>=111:errors.append('M9_HARD_STOP')
 if nm and int(nm.group(1))>=111:errors.append('M9_HARD_STOP')
 if sm and nm and int(nm.group(1))!=int(sm.group(1))+1:errors.append('NON_SEQUENTIAL_SPRINT_TRANSITION')
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
