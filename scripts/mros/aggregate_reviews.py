#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from validate_review import validate
from native_evidence import validate_native_evidence
from bridge_receipt import validate_bridge_receipt
from population_manifest import validate_population_manifest,reconcile_population
PASS={'PASS','PASS_WITH_MINOR_FINDINGS'}

def aggregate_payloads(payloads,*,candidate_head,receipts,manifest,expected_sprint=None,expected_round=None,minimum_required=None,require_receipt_path=False):
 manifest_errors=validate_population_manifest(manifest,candidate_head=candidate_head,job_type='reviewer',expected_sprint=expected_sprint,expected_round=expected_round,minimum_required=minimum_required)
 artifacts=[d for _,d in payloads if isinstance(d,dict)]
 recon=reconcile_population(manifest,artifacts) if not manifest_errors else {'expected':0,'submitted':len(artifacts),'omitted':[],'extra':[],'expected_members':{}}
 required=manifest.get('expected_count') if isinstance(manifest,dict) else None
 if isinstance(required,bool) or not isinstance(required,int):required=0
 expected_sprint=expected_sprint or (manifest.get('sprint') if isinstance(manifest,dict) else None);expected_round=expected_round or (manifest.get('round') if isinstance(manifest,dict) else None)
 reviews=[];invalid=[];seen_roles=set();seen_artifacts=set();seen_jobs=set()
 for name,d in payloads:
  errs=validate(d,candidate_head,expected_sprint,expected_round);member=recon['expected_members'].get(d.get('output_path')) if isinstance(d,dict) else None
  if not errs and member is None:errs.append('REVIEW_NOT_IN_FROZEN_POPULATION')
  if not errs:
   if d.get('execution_role_id')!=member.get('execution_role_id'):errs.append('POPULATION_EXECUTION_ROLE_MISMATCH')
   if d.get('role')!=member.get('semantic_role'):errs.append('POPULATION_SEMANTIC_ROLE_MISMATCH')
   if d.get('packet_path')!=member.get('packet_path'):errs.append('POPULATION_PACKET_PATH_MISMATCH')
  job_id=d.get('execution_job_id') if isinstance(d,dict) else None;receipt=receipts.get(job_id) if isinstance(receipts,dict) else None
  if not errs and require_receipt_path:
   frozen=receipt.get('_frozen_receipt_path') if isinstance(receipt,dict) else None
   if frozen!=member.get('receipt_path'):errs.append('POPULATION_RECEIPT_PATH_MISMATCH')
  if not errs:errs.extend(validate_bridge_receipt(receipt,d,candidate_head=candidate_head,job_type='reviewer'))
  role=d.get('role') if isinstance(d,dict) else None;artifact=d.get('artifact_id') if isinstance(d,dict) else None
  if not errs and role in seen_roles:errs.append('DUPLICATE_REVIEW_ROLE')
  if not errs and artifact in seen_artifacts:errs.append('DUPLICATE_REVIEW_ARTIFACT_ID')
  if not errs and job_id in seen_jobs:errs.append('DUPLICATE_REVIEW_JOB_ID')
  if errs:invalid.append({'file':str(name),'review':d,'errors':errs})
  else:reviews.append(d);seen_roles.add(role);seen_artifacts.add(artifact);seen_jobs.add(job_id)
 critical=sum(x['critical'] for x in reviews);major=sum(x['major'] for x in reviews);unknown=sum(x['unknown'] for x in reviews);minor=sum(x['minor'] for x in reviews)
 verdicts=[x['verdict'] for x in reviews];good=sum(v in PASS for v in verdicts);nonpass=[v for v in verdicts if v not in PASS]
 population_block=bool(manifest_errors or recon['omitted'] or recon['extra'])
 if manifest_errors:decision='INVALID_REVIEW_POPULATION_MANIFEST'
 elif population_block:decision='INCOMPLETE_OR_UNDECLARED_REVIEW_POPULATION'
 elif critical:decision='REVIEW_DISAGREEMENT_REQUIRES_ADJUDICATION'
 elif major:decision='REPAIR_REQUIRED'
 elif unknown or 'UNKNOWN' in verdicts:decision='UNKNOWN'
 elif len(reviews)<required:decision='INSUFFICIENT_VALID_INDEPENDENT_REVIEWS'
 elif nonpass:decision='REPAIR_REQUIRED' if set(nonpass)=={'REPAIR_REQUIRED'} else 'REVIEW_DISAGREEMENT_REQUIRES_ADJUDICATION'
 elif invalid:decision='INSUFFICIENT_VALID_INDEPENDENT_REVIEWS'
 elif minor:decision='PASS_WITH_MINOR_FINDINGS'
 else:decision='PASS'
 return {'candidate_head':candidate_head,'minimum_valid_reviews':required,'valid_reviews':len(reviews),'invalid_reviews':len(invalid),'expected_reviews':recon['expected'],'submitted_reviews':recon['submitted'],'omitted_reviews':recon['omitted'],'extra_reviews':recon['extra'],'excluded_reviews':0,'manifest_errors':manifest_errors,'pass_or_minor':good,'critical':critical,'major':major,'minor':minor,'unknown':unknown,'decision':decision,'reviews':reviews,'invalid':invalid,'transport':'mac_git_mailbox','runtime_authority':'NONE','authority':'Research / R'}

def load_receipts(directory:Path):
 out={}
 for f in sorted(directory.glob('*.json')):
  d=json.loads(f.read_text());job=d.get('job') if isinstance(d,dict) else None
  if isinstance(job,dict) and isinstance(job.get('job_id'),str):d=dict(d);d['_frozen_receipt_path']=f.as_posix();out[job['job_id']]=d
 return out

def main():
 p=argparse.ArgumentParser();p.add_argument('review_dir');p.add_argument('--receipt-dir',required=True);p.add_argument('--population-manifest',required=True);p.add_argument('--candidate-head',required=True);p.add_argument('--native-evidence',required=True);a=p.parse_args()
 n=json.loads(Path(a.native_evidence).read_text());errs=validate_native_evidence(n,a.candidate_head)
 if errs:print(json.dumps({'decision':'REVIEW_BLOCKED_NATIVE_VALIDATION_REQUIRED','native_errors':errs},sort_keys=True));raise SystemExit(2)
 payloads=[]
 for f in sorted(Path(a.review_dir).glob('*.json')):
  try:payloads.append((str(f),json.loads(f.read_text())))
  except Exception:payloads.append((str(f),None))
 manifest=json.loads(Path(a.population_manifest).read_text())
 out=aggregate_payloads(payloads,candidate_head=a.candidate_head,receipts=load_receipts(Path(a.receipt_dir)),manifest=manifest);out['native_validation']='PASS'
 print(json.dumps(out,indent=2,sort_keys=True));raise SystemExit(0 if out.get('decision') in PASS else 1)
if __name__=='__main__':main()
