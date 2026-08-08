#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from validate_audit import validate
PASS={'PASS','PASS_WITH_MINOR_FINDINGS'}
MIN_VALID=10


def aggregate_payloads(payloads, *, candidate_head, review, review_round, native):
 required=['repository','branch','head','validator','python_version','command','checks','passed','failed','exit_code','timestamp']
 if any(k not in native for k in required) or native.get('head')!=candidate_head or native.get('failed')!=0 or native.get('exit_code')!=0 or native.get('passed')!=native.get('checks'):
  return {'decision':'AUDIT_BLOCKED_NATIVE_VALIDATION_REQUIRED'}
 if review.get('candidate_head')!=candidate_head or review.get('decision') not in PASS:
  return {'decision':'AUDIT_BLOCKED_NONBLOCKING_REVIEW_REQUIRED'}
 audits=[];invalid=[]
 for name,d in payloads:
  errs=validate(d,candidate_head,review_round)
  (invalid if errs else audits).append({'file':str(name),'audit':d,'errors':errs} if errs else d)
 critical=sum(x['critical'] for x in audits);major=sum(x['major'] for x in audits);unknown=sum(x['unknown'] for x in audits);minor=sum(x['minor'] for x in audits)
 good=sum(x['verdict'] in PASS for x in audits)
 verdicts={x['verdict'] for x in audits}
 if critical: decision='AUDIT_DISAGREEMENT_REQUIRES_ADJUDICATION'
 elif major: decision='REPAIR_REQUIRED'
 elif unknown: decision='UNKNOWN'
 elif len(audits)<MIN_VALID: decision='INSUFFICIENT_VALID_INDEPENDENT_AUDITS'
 elif good<MIN_VALID: decision='AUDIT_DISAGREEMENT_REQUIRES_ADJUDICATION' if len(verdicts)>1 else 'REPAIR_REQUIRED'
 elif minor: decision='PASS_WITH_MINOR_FINDINGS'
 else: decision='PASS'
 return {'candidate_head':candidate_head,'review_round':review_round,'minimum_valid_audits':MIN_VALID,'valid_audits':len(audits),'invalid_audits':len(invalid),'pass_or_minor':good,'critical':critical,'major':major,'minor':minor,'unknown':unknown,'decision':decision,'audits':audits,'invalid':invalid}


def main():
 p=argparse.ArgumentParser();p.add_argument('audit_dir');p.add_argument('--candidate-head',required=True);p.add_argument('--review-aggregate',required=True);p.add_argument('--review-round',required=True);p.add_argument('--native-evidence',required=True);a=p.parse_args()
 native=json.loads(Path(a.native_evidence).read_text());review=json.loads(Path(a.review_aggregate).read_text())
 payloads=[]
 for f in sorted(Path(a.audit_dir).glob('auditor-*.json')):
  payloads.append((str(f),json.loads(f.read_text())))
 out=aggregate_payloads(payloads,candidate_head=a.candidate_head,review=review,review_round=a.review_round,native=native)
 print(json.dumps(out,indent=2,sort_keys=True))
 raise SystemExit(0 if out.get('decision') in PASS else (2 if out.get('decision','').startswith('AUDIT_BLOCKED_') else 1))
if __name__=='__main__':main()
