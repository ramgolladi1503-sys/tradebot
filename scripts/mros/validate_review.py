#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from pathlib import Path
ROLES={'contract_compliance','negative_control','evidence_provenance','authority_promotion','causal_time','denominator_search_integrity','runtime_boundary','qa_verification','architecture_no_drift','adversarial_red_team','critical_adjudicator'}
VERDICTS={'PASS','PASS_WITH_MINOR_FINDINGS','REPAIR_REQUIRED','FAIL','UNKNOWN','INVALID_REVIEW'}
SEV={'CRITICAL','MAJOR','MINOR','UNKNOWN'}
SHA=re.compile(r'^[0-9a-f]{40}$')
def validate(d,head):
 e=[]
 for k in ['review_id','sprint','review_round','reviewed_head','reviewer_role','independent_from_implementation','verdict','findings','critical','major','minor','unknown']:
  if k not in d:e.append('MISSING:'+k)
 if d.get('reviewed_head')!=head:e.append('HEAD_MISMATCH')
 if not SHA.match(str(d.get('reviewed_head',''))):e.append('INVALID_HEAD')
 if d.get('independent_from_implementation') is not True:e.append('REVIEWER_INVALID_NOT_INDEPENDENT')
 if d.get('reviewer_role') not in ROLES:e.append('INVALID_ROLE')
 if d.get('verdict') not in VERDICTS:e.append('INVALID_VERDICT')
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
 return e
def main():
 p=argparse.ArgumentParser();p.add_argument('review');p.add_argument('--candidate-head',required=True);a=p.parse_args()
 d=json.loads(Path(a.review).read_text());e=validate(d,a.candidate_head)
 print(json.dumps({'valid':not e,'errors':e},sort_keys=True));raise SystemExit(0 if not e else 1)
if __name__=='__main__':main()
