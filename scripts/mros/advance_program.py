#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from pathlib import Path
from native_evidence import validate_native_evidence
from program_context import load_and_validate_context
from aggregate_reviews import aggregate_payloads as aggregate_reviews
from aggregate_audits import aggregate_payloads as aggregate_audits
from population_git_trust import validate_trusted_population,load_exact_receipts,canonical_manifest_path

ACCEPT={'PASS','PASS_WITH_MINOR_FINDINGS'}
ROOT=Path(__file__).resolve().parents[2]
SPRINT=re.compile(r'^S([0-9]{3})$')

def _nonneg_int(value):return isinstance(value,int) and not isinstance(value,bool) and value>=0
def _positive_int(value):return isinstance(value,int) and not isinstance(value,bool) and value>0

def _acceptance_ids(sprint:str)->tuple[list[str],list[str]]:
 p=ROOT/f'research/evidence/sprints/{sprint}/{sprint}_ACCEPTANCE_CONTRACT.json'
 if not p.is_file():return [],['ACCEPTANCE_CONTRACT_MISSING']
 try:d=json.loads(p.read_text(encoding='utf-8'))
 except Exception:return [],['ACCEPTANCE_CONTRACT_INVALID']
 if d.get('sprint')!=sprint or d.get('status')!='FROZEN':return [],['ACCEPTANCE_CONTRACT_NOT_FROZEN_FOR_SPRINT']
 ids=[c.get('id') for c in d.get('criteria',[]) if isinstance(c,dict) and isinstance(c.get('id'),str) and c.get('id')]
 return ids,([] if ids else ['ACCEPTANCE_CONTRACT_CRITERIA_MISSING'])

def _compare_recomputed(data:dict,recomputed:dict,*,kind:str)->list[str]:
 e=[];prefix=kind.upper();plural='reviews' if kind=='review' else 'audits'
 keys=(('minimum_valid_reviews','valid_reviews','invalid_reviews','expected_reviews','submitted_reviews','omitted_reviews','extra_reviews') if kind=='review' else ('minimum_valid_audits','valid_audits','invalid_audits','expected_audits','submitted_audits','omitted_audits','extra_audits'))
 detail_keys=('excluded_reviews','invalid','pass_or_minor') if kind=='review' else ('excluded_audits','invalid','pass_or_minor','required_acceptance_ids','covered_acceptance_ids','missing_acceptance_ids','unknown_acceptance_ids')
 keys=keys+('manifest_errors','critical','major','minor','unknown','decision',plural)+detail_keys
 for key in keys:
  if data.get(key)!=recomputed.get(key):e.append(f'{prefix}_RECOMPUTED_{key.upper()}_MISMATCH')
 return e

def _validate_aggregate(data:object,*,candidate_head:str,kind:str,manifest:dict,receipts:dict,expected_sprint:str,expected_round:str,minimum_required:int,required_acceptance_ids=None,expected_native_ref=None,review_job_ids=None)->list[str]:
 e=[];prefix=kind.upper()
 if not isinstance(data,dict):return [f'{prefix}_AGGREGATE_OBJECT_REQUIRED']
 if data.get('candidate_head')!=candidate_head:e.append(f'{prefix}_AGGREGATE_HEAD_MISMATCH')
 if data.get('decision') not in ACCEPT:e.append(f'{prefix}_BOARD_NOT_ACCEPTED')
 if data.get('runtime_authority')!='NONE':e.append(f'{prefix}_RUNTIME_AUTHORITY_INVALID')
 if data.get('authority')!='Research / R':e.append(f'{prefix}_AUTHORITY_INVALID')
 if data.get('transport')!='mac_git_mailbox':e.append(f'{prefix}_TRANSPORT_INVALID')
 expected_manifest=canonical_manifest_path(expected_sprint,expected_round,'reviewer' if kind=='review' else 'auditor')
 if data.get('population_manifest') is None:e.append(f'{prefix}_POPULATION_MANIFEST_REF_MISSING')
 elif Path(str(data.get('population_manifest'))).as_posix()!=expected_manifest:e.append(f'{prefix}_POPULATION_MANIFEST_REF_MISMATCH')
 plural='reviews' if kind=='review' else 'audits';valid_key='valid_reviews' if kind=='review' else 'valid_audits';invalid_key='invalid_reviews' if kind=='review' else 'invalid_audits';expected_key='expected_reviews' if kind=='review' else 'expected_audits';submitted_key='submitted_reviews' if kind=='review' else 'submitted_audits';omitted_key='omitted_reviews' if kind=='review' else 'omitted_audits';extra_key='extra_reviews' if kind=='review' else 'extra_audits';minimum_key='minimum_valid_reviews' if kind=='review' else 'minimum_valid_audits'
 items=data.get(plural)
 if not isinstance(items,list):e.append(f'{prefix}_ITEMS_INVALID');items=[]
 for key in (valid_key,invalid_key,expected_key,submitted_key,minimum_key,'critical','major','minor','unknown'):
  if not _nonneg_int(data.get(key)):e.append(f'{prefix}_{key.upper()}_INVALID')
 for key in (valid_key,expected_key,submitted_key,minimum_key):
  if not _positive_int(data.get(key)):e.append(f'{prefix}_{key.upper()}_NONPOSITIVE')
 if not items:e.append(f'{prefix}_EMPTY_POPULATION')
 if _nonneg_int(data.get(valid_key)) and data.get(valid_key)!=len(items):e.append(f'{prefix}_VALID_COUNT_MISMATCH')
 if _nonneg_int(data.get(invalid_key)) and data.get(invalid_key)!=0:e.append(f'{prefix}_INVALID_ARTIFACTS_PRESENT')
 if not isinstance(data.get(omitted_key),list) or data.get(omitted_key):e.append(f'{prefix}_OMITTED_ARTIFACTS_PRESENT')
 if not isinstance(data.get(extra_key),list) or data.get(extra_key):e.append(f'{prefix}_EXTRA_ARTIFACTS_PRESENT')
 if not isinstance(data.get('manifest_errors'),list) or data.get('manifest_errors'):e.append(f'{prefix}_MANIFEST_ERRORS_PRESENT')
 if all(_positive_int(data.get(k)) for k in (valid_key,expected_key,submitted_key,minimum_key)):
  if data[minimum_key]<minimum_required:e.append(f'{prefix}_POLICY_QUORUM_BELOW_REQUIRED')
  if data[valid_key]<minimum_required:e.append(f'{prefix}_POLICY_QUORUM_NOT_MET')
  if data[valid_key]<data[minimum_key]:e.append(f'{prefix}_QUORUM_NOT_MET')
  if data[expected_key]!=data[submitted_key] or data[expected_key]!=data[valid_key]:e.append(f'{prefix}_DENOMINATOR_MISMATCH')
 if any(data.get(k,0) for k in ('critical','major','unknown')):e.append(f'{prefix}_BLOCKING_FINDINGS_PRESENT')
 if kind=='audit':
  if not isinstance(data.get('missing_acceptance_ids'),list) or data.get('missing_acceptance_ids'):e.append('AUDIT_ACCEPTANCE_COVERAGE_INCOMPLETE')
  if data.get('unknown_acceptance_ids') not in (None,[]):e.append('AUDIT_ACCEPTANCE_COVERAGE_UNKNOWN_IDS')
  if sorted(data.get('required_acceptance_ids') or [])!=sorted(required_acceptance_ids or []):e.append('AUDIT_REQUIRED_ACCEPTANCE_IDS_MISMATCH')
  if expected_native_ref is None:e.append('AUDIT_EXPECTED_NATIVE_REF_REQUIRED')
 payloads=[(str(item.get('output_path') if isinstance(item,dict) else f'<invalid-{i}>'),item) for i,item in enumerate(items)]
 try:
  if kind=='review':
   recomputed=aggregate_reviews(payloads,candidate_head=candidate_head,receipts=receipts,manifest=manifest,expected_sprint=expected_sprint,expected_round=expected_round,minimum_required=minimum_required,require_receipt_path=True)
  else:
   review_round=data.get('review_round')
   if not isinstance(review_round,str) or not review_round:e.append('AUDIT_REVIEW_ROUND_INVALID');return e
   recomputed=aggregate_audits(payloads,candidate_head=candidate_head,review_round=review_round,receipts=receipts,manifest=manifest,review_job_ids=review_job_ids or [],required_acceptance_ids=required_acceptance_ids or [],expected_native_ref=expected_native_ref,expected_sprint=expected_sprint,expected_round=expected_round,minimum_required=minimum_required,require_receipt_path=True)
 except Exception:
  e.append(f'{prefix}_RECOMPUTATION_FAILED');return e
 e.extend(_compare_recomputed(data,recomputed,kind=kind))
 if recomputed.get('decision') not in ACCEPT:e.append(f'{prefix}_RECOMPUTED_BOARD_NOT_ACCEPTED')
 return e

def authorize(*,sprint,next_sprint,candidate_head,review,audit,native,context_errors,review_manifest=None,audit_manifest=None,review_receipts=None,audit_receipts=None,queue_repo=None,review_manifest_path=None,audit_manifest_path=None,review_round=None,audit_round=None,expected_native_ref=None):
 errors=list(context_errors);ids,ae=_acceptance_ids(str(sprint));errors.extend(ae)
 sm=SPRINT.fullmatch(str(sprint));nm=SPRINT.fullmatch(str(next_sprint))
 if not sm:errors.append('SPRINT_INVALID')
 if not nm:errors.append('NEXT_SPRINT_INVALID')
 if sm and int(sm.group(1))>=111:errors.append('M9_HARD_STOP')
 if nm and int(nm.group(1))>=111:errors.append('M9_HARD_STOP')
 if sm and nm and int(nm.group(1))!=int(sm.group(1))+1:errors.append('NON_SEQUENTIAL_SPRINT_TRANSITION')
 if not isinstance(review_manifest,dict):errors.append('REVIEW_POPULATION_MANIFEST_REQUIRED')
 if not isinstance(audit_manifest,dict):errors.append('AUDIT_POPULATION_MANIFEST_REQUIRED')
 if queue_repo is None:errors.append('CANONICAL_QUEUE_REPO_REQUIRED')
 review_round=review_round or (review.get('review_round') if isinstance(review,dict) else None);audit_round=audit_round or (audit.get('audit_round') if isinstance(audit,dict) else None)
 if not isinstance(review_round,str) or not re.fullmatch(r'R\d{3}',review_round):errors.append('REVIEW_ROUND_REQUIRED')
 if not isinstance(audit_round,str) or not re.fullmatch(r'A\d{3}',audit_round):errors.append('AUDIT_ROUND_REQUIRED')
 minimum=10 if sprint=='S003' else 1
 rr={};ar={}
 if queue_repo is not None and isinstance(review_manifest,dict) and isinstance(review_round,str):
  errors.extend(validate_trusted_population(queue_repo=Path(queue_repo),manifest_path=review_manifest_path or '',manifest=review_manifest,candidate_head=candidate_head,sprint=sprint,round_id=review_round,job_type='reviewer'))
  rr,receipt_errors=load_exact_receipts(queue_repo=Path(queue_repo),manifest=review_manifest);errors.extend('REVIEW_'+x for x in receipt_errors)
 if queue_repo is not None and isinstance(audit_manifest,dict) and isinstance(audit_round,str):
  errors.extend(validate_trusted_population(queue_repo=Path(queue_repo),manifest_path=audit_manifest_path or '',manifest=audit_manifest,candidate_head=candidate_head,sprint=sprint,round_id=audit_round,job_type='auditor'))
  ar,receipt_errors=load_exact_receipts(queue_repo=Path(queue_repo),manifest=audit_manifest);errors.extend('AUDIT_'+x for x in receipt_errors)
 review_jobs=[r.get('execution_job_id') for r in (review.get('reviews',[]) if isinstance(review,dict) else []) if isinstance(r,dict) and isinstance(r.get('execution_job_id'),str)]
 if isinstance(review_manifest,dict) and isinstance(review_round,str):errors.extend(_validate_aggregate(review,candidate_head=candidate_head,kind='review',manifest=review_manifest,receipts=rr,expected_sprint=sprint,expected_round=review_round,minimum_required=minimum))
 if isinstance(audit_manifest,dict) and isinstance(audit_round,str):errors.extend(_validate_aggregate(audit,candidate_head=candidate_head,kind='audit',manifest=audit_manifest,receipts=ar,expected_sprint=sprint,expected_round=audit_round,minimum_required=minimum,required_acceptance_ids=ids,expected_native_ref=expected_native_ref,review_job_ids=review_jobs))
 if validate_native_evidence(native,candidate_head):errors.append('NATIVE_VALIDATION_NOT_PASS_FOR_HEAD')
 if errors:return {'advance':False,'errors':sorted(set(errors)),'runtime_authority':'NONE','authority':'Research / R'}
 return {'advance':True,'accepted_sprint':sprint,'accepted_head':candidate_head,'next_sprint':next_sprint,'runtime_authority':'NONE','authority':'Research / R'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--sprint',required=True);p.add_argument('--next-sprint',required=True);p.add_argument('--candidate-head',required=True);p.add_argument('--review-aggregate',required=True);p.add_argument('--audit-aggregate',required=True);p.add_argument('--native-evidence',required=True);p.add_argument('--acceptance-trace',required=True);p.add_argument('--review-population-manifest',required=True);p.add_argument('--audit-population-manifest',required=True);p.add_argument('--queue-repo',required=True);p.add_argument('--program-state',default=str(ROOT/'research/program/MROS_PROGRAM_STATE.yaml'));p.add_argument('--sprint-ledger',default=str(ROOT/'research/program/SPRINT_LEDGER.jsonl'));a=p.parse_args()
 review=json.loads(Path(a.review_aggregate).read_text());audit=json.loads(Path(a.audit_aggregate).read_text());native=json.loads(Path(a.native_evidence).read_text());review_manifest=json.loads(Path(a.review_population_manifest).read_text());audit_manifest=json.loads(Path(a.audit_population_manifest).read_text())
 context_errors=load_and_validate_context(state_path=Path(a.program_state),ledger_path=Path(a.sprint_ledger),acceptance_path=Path(a.acceptance_trace),sprint=a.sprint,next_sprint=a.next_sprint,candidate_head=a.candidate_head)
 out=authorize(sprint=a.sprint,next_sprint=a.next_sprint,candidate_head=a.candidate_head,review=review,audit=audit,native=native,context_errors=context_errors,review_manifest=review_manifest,audit_manifest=audit_manifest,queue_repo=Path(a.queue_repo),review_manifest_path=Path(a.review_population_manifest),audit_manifest_path=Path(a.audit_population_manifest),review_round=review.get('review_round'),audit_round=audit.get('audit_round'),expected_native_ref=str(Path(a.native_evidence)))
 print(json.dumps(out,sort_keys=True))
 if not out['advance']:raise SystemExit(1)
 print('ADVANCEMENT_AUTHORIZATION_ONLY: ledger/state mutation must be performed as a separate evidenced commit.')
if __name__=='__main__':main()
