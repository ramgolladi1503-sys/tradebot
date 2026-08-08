#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from validate_review import validate
from native_evidence import validate_native_evidence
from bridge_receipt import validate_bridge_receipt
PASS={'PASS','PASS_WITH_MINOR_FINDINGS'}
MIN_VALID=10

def aggregate_payloads(payloads, *, candidate_head, receipts):
 reviews=[];invalid=[];seen_roles=set();seen_artifacts=set();seen_jobs=set()
 for name,d in payloads:
  errs=validate(d,candidate_head)
  job_id=d.get('execution_job_id') if isinstance(d,dict) else None
  receipt=receipts.get(job_id) if isinstance(receipts,dict) else None
  if not errs:errs.extend(validate_bridge_receipt(receipt,d,candidate_head=candidate_head,job_type='reviewer'))
  role=d.get('role') if isinstance(d,dict) else None;artifact=d.get('artifact_id') if isinstance(d,dict) else None
  if not errs and role in seen_roles:errs.append('DUPLICATE_REVIEW_ROLE')
  if not errs and artifact in seen_artifacts:errs.append('DUPLICATE_REVIEW_ARTIFACT_ID')
  if not errs and job_id in seen_jobs:errs.append('DUPLICATE_REVIEW_JOB_ID')
  if errs:invalid.append({'file':str(name),'review':d,'errors':errs})
  else:reviews.append(d);seen_roles.add(role);seen_artifacts.add(artifact);seen_jobs.add(job_id)
 critical=sum(x['critical'] for x in reviews);major=sum(x['major'] for x in reviews);unknown=sum(x['unknown'] for x in reviews);minor=sum(x['minor'] for x in reviews)
 verdicts=[x['verdict'] for x in reviews];good=sum(v in PASS for v in verdicts);nonpass=[v for v in verdicts if v not in PASS]
 if critical:decision='REVIEW_DISAGREEMENT_REQUIRES_ADJUDICATION'
 elif major:decision='REPAIR_REQUIRED'
 elif unknown or 'UNKNOWN' in verdicts:decision='UNKNOWN'
 elif len(reviews)<MIN_VALID:decision='INSUFFICIENT_VALID_INDEPENDENT_REVIEWS'
 elif nonpass:decision='REPAIR_REQUIRED' if set(nonpass)=={'REPAIR_REQUIRED'} else 'REVIEW_DISAGREEMENT_REQUIRES_ADJUDICATION'
 elif minor:decision='PASS_WITH_MINOR_FINDINGS'
 else:decision='PASS'
 return {'candidate_head':candidate_head,'minimum_valid_reviews':MIN_VALID,'valid_reviews':len(reviews),'invalid_reviews':len(invalid),'pass_or_minor':good,'critical':critical,'major':major,'minor':minor,'unknown':unknown,'decision':decision,'reviews':reviews,'invalid':invalid,'transport':'mac_git_mailbox','runtime_authority':'NONE','authority':'Research / R'}

def load_receipts(directory:Path):
 out={}
 for f in sorted(directory.glob('*.json')):
  d=json.loads(f.read_text());job=d.get('job') if isinstance(d,dict) else None
  if isinstance(job,dict) and isinstance(job.get('job_id'),str):out[job['job_id']]=d
 return out

def main():
 p=argparse.ArgumentParser();p.add_argument('review_dir');p.add_argument('--receipt-dir',required=True);p.add_argument('--candidate-head',required=True);p.add_argument('--native-evidence',required=True);a=p.parse_args()
 n=json.loads(Path(a.native_evidence).read_text());native_errors=validate_native_evidence(n,a.candidate_head)
 if native_errors:
  print(json.dumps({'decision':'REVIEW_BLOCKED_NATIVE_VALIDATION_REQUIRED','native_errors':native_errors},sort_keys=True));raise SystemExit(2)
 payloads=[(str(f),json.loads(f.read_text())) for f in sorted(Path(a.review_dir).glob('reviewer-*.json'))]
 out=aggregate_payloads(payloads,candidate_head=a.candidate_head,receipts=load_receipts(Path(a.receipt_dir)));out['native_validation']='PASS'
 print(json.dumps(out,indent=2,sort_keys=True));raise SystemExit(0 if out.get('decision') in PASS else 1)
if __name__=='__main__':main()
