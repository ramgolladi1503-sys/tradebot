#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from validate_review import validate
PASS={'PASS','PASS_WITH_MINOR_FINDINGS'}
def main():
 p=argparse.ArgumentParser();p.add_argument('review_dir');p.add_argument('--candidate-head',required=True);p.add_argument('--native-evidence',required=True);a=p.parse_args()
 n=json.loads(Path(a.native_evidence).read_text())
 required=['repository','branch','head','validator','python_version','command','checks','passed','failed','exit_code','timestamp']
 if any(k not in n for k in required) or n.get('head')!=a.candidate_head or n.get('failed')!=0 or n.get('exit_code')!=0:
  print(json.dumps({'decision':'REVIEW_BLOCKED_NATIVE_VALIDATION_REQUIRED'}));raise SystemExit(2)
 reviews=[];invalid=[]
 for f in sorted(Path(a.review_dir).glob('reviewer-*.json')):
  d=json.loads(f.read_text());errs=validate(d,a.candidate_head)
  (invalid if errs else reviews).append({'file':str(f),'review':d,'errors':errs} if errs else d)
 critical=sum(x['critical'] for x in reviews);major=sum(x['major'] for x in reviews);unknown=sum(x['unknown'] for x in reviews);minor=sum(x['minor'] for x in reviews)
 good=sum(x['verdict'] in PASS for x in reviews)
 verdicts={x['verdict'] for x in reviews}
 if critical:decision='REVIEW_DISAGREEMENT_REQUIRES_ADJUDICATION'
 elif major:decision='REPAIR_REQUIRED'
 elif unknown:decision='UNKNOWN'
 elif len(reviews)<8:decision='INSUFFICIENT_VALID_INDEPENDENT_REVIEWS'
 elif good<8:decision='REVIEW_DISAGREEMENT_REQUIRES_ADJUDICATION' if len(verdicts)>1 else 'REPAIR_REQUIRED'
 elif minor:decision='PASS_WITH_MINOR_FINDINGS'
 else:decision='PASS'
 out={'candidate_head':a.candidate_head,'valid_reviews':len(reviews),'invalid_reviews':len(invalid),'pass_or_minor':good,'critical':critical,'major':major,'minor':minor,'unknown':unknown,'decision':decision,'reviews':reviews,'invalid':invalid}
 print(json.dumps(out,indent=2,sort_keys=True))
 raise SystemExit(0 if decision in PASS else 1)
if __name__=='__main__':main()
