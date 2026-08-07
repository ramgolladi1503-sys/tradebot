#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from pathlib import Path
ROLES={'evidence_chain','review_independence','acceptance_criteria','regression','program_state','scope_no_drift','scientific_integrity','reproducibility','authority','adversarial_acceptance','artifact_completeness','historical_supersession','ci_validation','calibration','runtime_contamination','critical_adjudicator'}
VERDICTS={'PASS','PASS_WITH_MINOR_FINDINGS','REPAIR_REQUIRED','FAIL','UNKNOWN','INVALID_AUDIT'}
SEV={'CRITICAL','MAJOR','MINOR','UNKNOWN'}
SHA=re.compile(r'^[0-9a-f]{40}$')
REQ=['artifact_id','sprint','round','candidate_head','role','independent_from_implementation','independent_from_review_aggregation','verdict','findings','critical','major','minor','unknown','evidence_refs','audited_review_round','audited_native_validation','audited_acceptance_criteria','audit_scope']
def validate(d,head,review_round=None):
 e=[]
 for k in REQ:
  if k not in d:e.append('MISSING:'+k)
 if d.get('candidate_head')!=head:e.append('HEAD_MISMATCH')
 if not SHA.match(str(d.get('candidate_head',''))):e.append('INVALID_HEAD')
 if d.get('independent_from_implementation') is not True:e.append('AUDITOR_INVALID_NOT_INDEPENDENT_FROM_IMPLEMENTATION')
 if d.get('independent_from_review_aggregation') is not True:e.append('AUDITOR_INVALID_NOT_INDEPENDENT_FROM_REVIEW_AGGREGATION')
 if d.get('role') not in ROLES:e.append('INVALID_ROLE')
 if d.get('verdict') not in VERDICTS:e.append('INVALID_VERDICT')
 if not re.match(r'^S[0-9]{3}$',str(d.get('sprint',''))):e.append('INVALID_SPRINT')
 if not re.match(r'^A[0-9]{3}$',str(d.get('round',''))):e.append('INVALID_AUDIT_ROUND')
 if review_round is not None and d.get('audited_review_round')!=review_round:e.append('REVIEW_ROUND_MISMATCH')
 if not isinstance(d.get('evidence_refs'),list):e.append('INVALID_EVIDENCE_REFS')
 if not isinstance(d.get('audited_acceptance_criteria'),list):e.append('INVALID_ACCEPTANCE_CRITERIA')
 if not isinstance(d.get('audit_scope'),list) or not d.get('audit_scope'):e.append('INVALID_AUDIT_SCOPE')
 fs=d.get('findings',[])
 if not isinstance(fs,list):e.append('INVALID_FINDINGS');fs=[]
 counts={x:0 for x in SEV}
 for i,f in enumerate(fs):
  if not isinstance(f,dict):e.append(f'INVALID_FINDING:{i}');continue
  for k in ['finding_id','severity','requirement','evidence','falsifier','recommended_repair_scope']:
   if not f.get(k):e.append(f'FINDING_{i}_MISSING:{k}')
  if f.get('severity') not in SEV:e.append(f'FINDING_{i}_INVALID_SEVERITY')
  else:counts[f['severity']]+=1
 for sev,key in [('CRITICAL','critical'),('MAJOR','major'),('MINOR','minor'),('UNKNOWN','unknown')]:
  if d.get(key)!=counts[sev]:e.append('COUNT_MISMATCH:'+key)
 if d.get('critical',0)>0 and d.get('verdict') in {'PASS','PASS_WITH_MINOR_FINDINGS'}:e.append('CRITICAL_CANNOT_PASS')
 if d.get('major',0)>0 and d.get('verdict') in {'PASS','PASS_WITH_MINOR_FINDINGS'}:e.append('MAJOR_CANNOT_PASS')
 return e
def main():
 p=argparse.ArgumentParser();p.add_argument('audit');p.add_argument('--candidate-head',required=True);p.add_argument('--review-round');a=p.parse_args()
 d=json.loads(Path(a.audit).read_text());e=validate(d,a.candidate_head,a.review_round)
 print(json.dumps({'valid':not e,'errors':e},sort_keys=True));raise SystemExit(0 if not e else 1)
if __name__=='__main__':main()
