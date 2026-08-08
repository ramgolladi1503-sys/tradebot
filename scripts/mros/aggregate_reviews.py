#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from validate_review import validate
from native_evidence import validate_native_evidence
PASS={'PASS','PASS_WITH_MINOR_FINDINGS'}
MIN_VALID=10


def aggregate_payloads(payloads, *, candidate_head):
 reviews=[];invalid=[]
 for name,d in payloads:
  errs=validate(d,candidate_head)
  (invalid if errs else reviews).append({'file':str(name),'review':d,'errors':errs} if errs else d)
 critical=sum(x['critical'] for x in reviews);major=sum(x['major'] for x in reviews);unknown=sum(x['unknown'] for x in reviews);minor=sum(x['minor'] for x in reviews)
 verdicts=[x['verdict'] for x in reviews]
 good=sum(v in PASS for v in verdicts)
 nonpass=[v for v in verdicts if v not in PASS]
 if critical:
  decision='REVIEW_DISAGREEMENT_REQUIRES_ADJUDICATION'
 elif major:
  decision='REPAIR_REQUIRED'
 elif unknown or 'UNKNOWN' in verdicts:
  decision='UNKNOWN'
 elif len(reviews)<MIN_VALID:
  decision='INSUFFICIENT_VALID_INDEPENDENT_REVIEWS'
 elif nonpass:
  decision='REPAIR_REQUIRED' if set(nonpass)=={'REPAIR_REQUIRED'} else 'REVIEW_DISAGREEMENT_REQUIRES_ADJUDICATION'
 elif minor:
  decision='PASS_WITH_MINOR_FINDINGS'
 else:
  decision='PASS'
 return {'candidate_head':candidate_head,'minimum_valid_reviews':MIN_VALID,'valid_reviews':len(reviews),'invalid_reviews':len(invalid),'pass_or_minor':good,'critical':critical,'major':major,'minor':minor,'unknown':unknown,'decision':decision,'reviews':reviews,'invalid':invalid}


def main():
 p=argparse.ArgumentParser();p.add_argument('review_dir');p.add_argument('--candidate-head',required=True);p.add_argument('--native-evidence',required=True);a=p.parse_args()
 n=json.loads(Path(a.native_evidence).read_text())
 native_errors=validate_native_evidence(n,a.candidate_head)
 if native_errors:
  print(json.dumps({'decision':'REVIEW_BLOCKED_NATIVE_VALIDATION_REQUIRED','native_errors':native_errors},sort_keys=True));raise SystemExit(2)
 payloads=[]
 for f in sorted(Path(a.review_dir).glob('reviewer-*.json')):
  payloads.append((str(f),json.loads(f.read_text())))
 out=aggregate_payloads(payloads,candidate_head=a.candidate_head)
 out['native_validation']='PASS'
 print(json.dumps(out,indent=2,sort_keys=True))
 raise SystemExit(0 if out.get('decision') in PASS else 1)
if __name__=='__main__':main()
