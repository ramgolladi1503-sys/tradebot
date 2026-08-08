#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from pathlib import Path
ROLES={'contract_compliance','negative_control','evidence_provenance','authority_promotion','causal_time','denominator_search_integrity','runtime_boundary','qa_verification','architecture_no_drift','adversarial_red_team','reproducibility','security_secrets','data_contract','statistical_semantics','adversarial_api','critical_adjudicator'}
VERDICTS={'PASS','PASS_WITH_MINOR_FINDINGS','REPAIR_REQUIRED','FAIL','UNKNOWN','INVALID_REVIEW'}
SEV={'CRITICAL','MAJOR','MINOR','UNKNOWN'}
SHA=re.compile(r'^[0-9a-f]{40}$');JOB=re.compile(r'^[0-9a-f]{32}$');ROLEID=re.compile(r'^R[0-9]{2,3}$')
REQ=['artifact_id','sprint','round','candidate_head','role','execution_role_id','execution_job_id','transport','packet_path','output_path','runtime_authority','broker_actions','independent_from_implementation','independent_from_review_aggregation','verdict','findings','critical','major','minor','unknown','evidence_refs']
ALLOWED=set(REQ)
FINDING_REQ=['finding_id','severity','requirement','evidence','falsifier','recommended_repair_scope']
FINDING_ALLOWED=set(FINDING_REQ)

def validate(d,head,expected_sprint=None,expected_round=None):
 e=[]
 if not isinstance(d,dict):return ['REVIEW_OBJECT_REQUIRED']
 for k in REQ:
  if k not in d:e.append('MISSING:'+k)
 extra=sorted(set(d)-ALLOWED)
 if extra:e.extend('UNKNOWN_FIELD:'+k for k in extra)
 if d.get('candidate_head')!=head:e.append('HEAD_MISMATCH')
 if not SHA.fullmatch(str(d.get('candidate_head',''))):e.append('INVALID_HEAD')
 if d.get('independent_from_implementation') is not True:e.append('REVIEWER_INVALID_NOT_INDEPENDENT_FROM_IMPLEMENTATION')
 if d.get('independent_from_review_aggregation') is not True:e.append('REVIEWER_INVALID_NOT_INDEPENDENT_FROM_AGGREGATION')
 if d.get('role') not in ROLES:e.append('INVALID_ROLE')
 if not ROLEID.fullmatch(str(d.get('execution_role_id',''))):e.append('INVALID_EXECUTION_ROLE_ID')
 if not JOB.fullmatch(str(d.get('execution_job_id',''))):e.append('INVALID_EXECUTION_JOB_ID')
 if d.get('transport')!='mac_git_mailbox':e.append('INVALID_TRANSPORT')
 if not isinstance(d.get('packet_path'),str) or not d.get('packet_path','').strip():e.append('INVALID_PACKET_PATH')
 if not isinstance(d.get('output_path'),str) or not d.get('output_path','').strip():e.append('INVALID_OUTPUT_PATH')
 if d.get('runtime_authority')!='NONE':e.append('INVALID_RUNTIME_AUTHORITY')
 if d.get('broker_actions')!='NONE':e.append('INVALID_BROKER_BOUNDARY')
 if d.get('verdict') not in VERDICTS:e.append('INVALID_VERDICT')
 if not re.fullmatch(r'S[0-9]{3}',str(d.get('sprint',''))):e.append('INVALID_SPRINT')
 if not re.fullmatch(r'R[0-9]{3}',str(d.get('round',''))):e.append('INVALID_ROUND')
 if expected_sprint is not None and d.get('sprint')!=expected_sprint:e.append('SPRINT_MISMATCH')
 if expected_round is not None and d.get('round')!=expected_round:e.append('ROUND_MISMATCH')
 refs=d.get('evidence_refs')
 if not isinstance(refs,list) or not refs or any(not isinstance(x,str) or not x.strip() for x in refs):e.append('INVALID_EVIDENCE_REFS')
 fs=d.get('findings',[])
 if not isinstance(fs,list):e.append('INVALID_FINDINGS');fs=[]
 counts={x:0 for x in SEV};ids=set()
 for i,f in enumerate(fs):
  if not isinstance(f,dict):e.append(f'INVALID_FINDING:{i}');continue
  for k in FINDING_REQ:
   if not isinstance(f.get(k),str) or not f.get(k,'').strip():e.append(f'FINDING_{i}_MISSING:{k}')
  extra_f=sorted(set(f)-FINDING_ALLOWED)
  if extra_f:e.extend(f'FINDING_{i}_UNKNOWN_FIELD:{k}' for k in extra_f)
  fid=f.get('finding_id')
  if fid in ids:e.append(f'FINDING_{i}_DUPLICATE_ID')
  ids.add(fid)
  if f.get('severity') not in SEV:e.append(f'FINDING_{i}_INVALID_SEVERITY')
  else:counts[f['severity']]+=1
 for sev,key in [('CRITICAL','critical'),('MAJOR','major'),('MINOR','minor'),('UNKNOWN','unknown')]:
  v=d.get(key)
  if isinstance(v,bool) or not isinstance(v,int) or v<0:e.append('INVALID_COUNT_TYPE:'+key)
  elif v!=counts[sev]:e.append('COUNT_MISMATCH:'+key)
 if isinstance(d.get('critical'),int) and not isinstance(d.get('critical'),bool) and d.get('critical',0)>0 and d.get('verdict') in {'PASS','PASS_WITH_MINOR_FINDINGS'}:e.append('CRITICAL_CANNOT_PASS')
 if isinstance(d.get('major'),int) and not isinstance(d.get('major'),bool) and d.get('major',0)>0 and d.get('verdict') in {'PASS','PASS_WITH_MINOR_FINDINGS'}:e.append('MAJOR_CANNOT_PASS')
 if isinstance(d.get('unknown'),int) and not isinstance(d.get('unknown'),bool) and d.get('unknown',0)>0 and d.get('verdict') in {'PASS','PASS_WITH_MINOR_FINDINGS'}:e.append('UNKNOWN_CANNOT_PASS')
 return e

def main():
 p=argparse.ArgumentParser();p.add_argument('review');p.add_argument('--candidate-head',required=True);p.add_argument('--sprint');p.add_argument('--round');a=p.parse_args()
 d=json.loads(Path(a.review).read_text());e=validate(d,a.candidate_head,a.sprint,a.round)
 print(json.dumps({'valid':not e,'errors':e},sort_keys=True));raise SystemExit(0 if not e else 1)
if __name__=='__main__':main()
