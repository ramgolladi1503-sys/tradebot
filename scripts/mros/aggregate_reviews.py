#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from validate_review import validate
PASS={'PASS','PASS_WITH_MINOR_FINDINGS'}
MIN_VALID=10


def aggregate_payloads(payloads, *, candidate_head, native):
 required=['repository','branch','head','validator','python_version','command','checks','passed','failed','exit_code','timestamp']
 if any(k not in native for k in required) or native.get('head')!=candidate_head or native.get('failed')!=0 or native.get('exit_code')!=0 or native.get('passed')!=native.get('checks'):
  return {'decision':'REVIEW_BLOCKED_NATIVE_VALIDATION_REQUIRED'}
 reviews=[];invalid=[]
 for name,d in payloads:
  errs=validate(d,candidate_head)
  (invalid if errs else reviews).append({'file':str(name),'review':d,'errors':errs} if errs else d)
 critical=sum(x['critical'] for x in reviews);major=sum(x['major'] for x in reviews);unknown=sum(x['unknown'] for x in reviews);minor=sum(x['minor'] for x in reviews)
 good=sum(x['verdict'] in PASS for x in reviews)
 verdicts={x['verdict'] for x in reviews}
 if critical: decision='REVIEW_DISAGREEMENT_REQUIRES_ADJUDICATION'
 elif major: decision='REPAIR_REQUIRED'
 elif unknown: decision='UNKNOWN'
 elif len(reviews)<MIN_VALID: decision='INSUFFICIENT_VALID_INDEPENDENT_REVIEWS'
 elif good<MIN_VALID: decision='REVIEW_DISAGREEMENT_REQUIRES_ADJUDICATION' if len(verdicts)>1 else 'REPAIR_REQUIRED'
 elif minor: decision='PASS_WITH_MINOR_FINDINGS'
 else: decision='PASS'
 return {'candidate_head':candidate_head,'native_validation':'PASS','minimum_valid_reviews':MIN_VALID,'valid_reviews':len(reviews),'invalid_reviews':len(invalid),'pass_or_minor':good,'critical':critical,'major':major,'minor':minor,'unknown':unknown,'decision':decision,'reviews':reviews,'invalid':invalid}


def main():
 p=argparse.ArgumentParser();p.add_argument('review_dir');p.add_argument('--candidate-head',required=True);p.add_argument('--native-evidence',required=True);a=p.parse_args()
 n=json.loads(Path(a.native_evidence).read_text())
 payloads=[]
 for f in sorted(Path(a.review_dir).glob('reviewer-*.json')):
  payloads.append((str(f),json.loads(f.read_text())))
 out=aggregate_payloads(payloads,candidate_head=a.candidate_head,native=n)
 print(json.dumps(out,indent=2,sort_keys=True))
 raise SystemExit(0 if out.get('decision') in PASS else (2 if out.get('decision')=='REVIEW_BLOCKED_NATIVE_VALIDATION_REQUIRED' else 1))
if __name__=='__main__':main()
