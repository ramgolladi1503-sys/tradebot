#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from validate_audit import validate
from native_evidence import validate_native_evidence
from bridge_receipt import validate_bridge_receipt
from population_manifest import validate_population_manifest,reconcile_population
PASS={'PASS','PASS_WITH_MINOR_FINDINGS'};MIN_VALID=10

def aggregate_payloads(payloads,*,candidate_head,review_round,receipts,manifest,review_job_ids=None,required_acceptance_ids=None,expected_native_ref=None):
 manifest_errors=validate_population_manifest(manifest,candidate_head=candidate_head,job_type='auditor');artifacts=[d for _,d in payloads if isinstance(d,dict)];recon=reconcile_population(manifest,artifacts) if not manifest_errors else {'expected':0,'submitted':len(artifacts),'omitted':[],'extra':[],'expected_members':{}}
 audits=[];invalid=[];seen_roles=set();seen_artifacts=set();seen_jobs=set();review_job_ids=set(review_job_ids or []);coverage=set()
 for name,d in payloads:
  errs=validate(d,candidate_head,review_round);member=recon['expected_members'].get(d.get('output_path')) if isinstance(d,dict) else None
  if not errs and member is None:errs.append('AUDIT_NOT_IN_FROZEN_POPULATION')
  if not errs:
   if d.get('execution_role_id')!=member.get('execution_role_id'):errs.append('POPULATION_EXECUTION_ROLE_MISMATCH')
   if d.get('role')!=member.get('semantic_role'):errs.append('POPULATION_SEMANTIC_ROLE_MISMATCH')
   if d.get('packet_path')!=member.get('packet_path'):errs.append('POPULATION_PACKET_PATH_MISMATCH')
  job_id=d.get('execution_job_id') if isinstance(d,dict) else None;receipt=receipts.get(job_id) if isinstance(receipts,dict) else None
  if not errs:errs.extend(validate_bridge_receipt(receipt,d,candidate_head=candidate_head,job_type='auditor'))
  if not errs and job_id in review_job_ids:errs.append('CROSS_BOARD_EXECUTION_JOB_REUSE')
  if not errs and expected_native_ref is not None and d.get('audited_native_validation')!=expected_native_ref:errs.append('AUDITED_NATIVE_REFERENCE_MISMATCH')
  role=d.get('role') if isinstance(d,dict) else None;artifact=d.get('artifact_id') if isinstance(d,dict) else None
  if not errs and role in seen_roles:errs.append('DUPLICATE_AUDIT_ROLE')
  if not errs and artifact in seen_artifacts:errs.append('DUPLICATE_AUDIT_ARTIFACT_ID')
  if not errs and job_id in seen_jobs:errs.append('DUPLICATE_AUDIT_JOB_ID')
  if errs:invalid.append({'file':str(name),'audit':d,'errors':errs})
  else:
   audits.append(d);seen_roles.add(role);seen_artifacts.add(artifact);seen_jobs.add(job_id);coverage.update(d.get('audited_acceptance_criteria',[]))
 critical=sum(x['critical'] for x in audits);major=sum(x['major'] for x in audits);unknown=sum(x['unknown'] for x in audits);minor=sum(x['minor'] for x in audits);verdicts=[x['verdict'] for x in audits];good=sum(v in PASS for v in verdicts);nonpass=[v for v in verdicts if v not in PASS]
 missing_criteria=sorted(set(required_acceptance_ids or [])-coverage);population_block=bool(manifest_errors or recon['omitted'] or recon['extra'])
 if manifest_errors:decision='INVALID_AUDIT_POPULATION_MANIFEST'
 elif population_block:decision='INCOMPLETE_OR_UNDECLARED_AUDIT_POPULATION'
 elif missing_criteria:decision='INCOMPLETE_AUDIT_ACCEPTANCE_COVERAGE'
 elif critical:decision='AUDIT_DISAGREEMENT_REQUIRES_ADJUDICATION'
 elif major:decision='REPAIR_REQUIRED'
 elif unknown or 'UNKNOWN' in verdicts:decision='UNKNOWN'
 elif len(audits)<MIN_VALID:decision='INSUFFICIENT_VALID_INDEPENDENT_AUDITS'
 elif nonpass:decision='REPAIR_REQUIRED' if set(nonpass)=={'REPAIR_REQUIRED'} else 'AUDIT_DISAGREEMENT_REQUIRES_ADJUDICATION'
 elif invalid:decision='INSUFFICIENT_VALID_INDEPENDENT_AUDITS'
 elif minor:decision='PASS_WITH_MINOR_FINDINGS'
 else:decision='PASS'
 return {'candidate_head':candidate_head,'review_round':review_round,'minimum_valid_audits':MIN_VALID,'valid_audits':len(audits),'invalid_audits':len(invalid),'expected_audits':recon['expected'],'submitted_audits':recon['submitted'],'omitted_audits':recon['omitted'],'extra_audits':recon['extra'],'excluded_audits':0,'manifest_errors':manifest_errors,'required_acceptance_ids':sorted(set(required_acceptance_ids or [])),'covered_acceptance_ids':sorted(coverage),'missing_acceptance_ids':missing_criteria,'pass_or_minor':good,'critical':critical,'major':major,'minor':minor,'unknown':unknown,'decision':decision,'audits':audits,'invalid':invalid,'transport':'mac_git_mailbox','runtime_authority':'NONE','authority':'Research / R'}

def load_receipts(directory:Path):
 out={}
 for f in sorted(directory.glob('*.json')):
  d=json.loads(f.read_text());job=d.get('job') if isinstance(d,dict) else None
  if isinstance(job,dict) and isinstance(job.get('job_id'),str):out[job['job_id']]=d
 return out

def main():
 p=argparse.ArgumentParser();p.add_argument('audit_dir');p.add_argument('--receipt-dir',required=True);p.add_argument('--population-manifest',required=True);p.add_argument('--candidate-head',required=True);p.add_argument('--review-aggregate',required=True);p.add_argument('--review-round',required=True);p.add_argument('--native-evidence',required=True);p.add_argument('--acceptance-contract',required=True);a=p.parse_args()
 native=json.loads(Path(a.native_evidence).read_text());errs=validate_native_evidence(native,a.candidate_head)
 if errs:print(json.dumps({'decision':'AUDIT_BLOCKED_NATIVE_VALIDATION_REQUIRED','native_errors':errs},sort_keys=True));raise SystemExit(2)
 review=json.loads(Path(a.review_aggregate).read_text())
 if review.get('candidate_head')!=a.candidate_head or review.get('decision') not in PASS or review.get('critical',0) or review.get('major',0) or review.get('unknown',0):print(json.dumps({'decision':'AUDIT_BLOCKED_NONBLOCKING_REVIEW_REQUIRED'}));raise SystemExit(2)
 contract=json.loads(Path(a.acceptance_contract).read_text());required=[c.get('id') for c in contract.get('criteria',[]) if isinstance(c,dict) and c.get('id')];review_jobs=[r.get('execution_job_id') for r in review.get('reviews',[]) if isinstance(r,dict)]
 payloads=[(str(f),json.loads(f.read_text())) for f in sorted(Path(a.audit_dir).glob('auditor-*.json'))];manifest=json.loads(Path(a.population_manifest).read_text())
 out=aggregate_payloads(payloads,candidate_head=a.candidate_head,review_round=a.review_round,receipts=load_receipts(Path(a.receipt_dir)),manifest=manifest,review_job_ids=review_jobs,required_acceptance_ids=required,expected_native_ref=str(Path(a.native_evidence)))
 print(json.dumps(out,indent=2,sort_keys=True));raise SystemExit(0 if out.get('decision') in PASS else 1)
if __name__=='__main__':main()
