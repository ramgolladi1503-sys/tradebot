#!/usr/bin/env python3
from __future__ import annotations
import subprocess,sys
from validate_review import validate as validate_review
from validate_audit import validate as validate_audit
from aggregate_reviews import aggregate_payloads as aggregate_reviews
from aggregate_audits import aggregate_payloads as aggregate_audits
from advance_program import authorize

ROOT=__import__('pathlib').Path(__file__).resolve().parents[2]
CANDIDATE=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
ROUND='R001'

def finding(fid,severity):
 return {'finding_id':fid,'severity':severity,'requirement':'calibration requirement','evidence':'controlled calibration evidence','falsifier':'controlled opposite behavior','recommended_repair_scope':'calibration only'}

def review(role,verdict='PASS',findings=None,head=None,independent=True):
 fs=findings or []
 return {'artifact_id':f'CAL-{role}','sprint':'S003','round':ROUND,'candidate_head':head or CANDIDATE,'role':role,'independent_from_implementation':independent,'independent_from_review_aggregation':True,'verdict':verdict,'findings':fs,'critical':sum(x['severity']=='CRITICAL' for x in fs),'major':sum(x['severity']=='MAJOR' for x in fs),'minor':sum(x['severity']=='MINOR' for x in fs),'unknown':sum(x['severity']=='UNKNOWN' for x in fs),'evidence_refs':['CALIBRATION-CONTROL']}

def audit(role,verdict='PASS',findings=None,head=None,independent=True):
 fs=findings or []
 return {'artifact_id':f'CAL-{role}','sprint':'S003','round':'A001','candidate_head':head or CANDIDATE,'role':role,'independent_from_implementation':independent,'independent_from_review_aggregation':True,'verdict':verdict,'findings':fs,'critical':sum(x['severity']=='CRITICAL' for x in fs),'major':sum(x['severity']=='MAJOR' for x in fs),'minor':sum(x['severity']=='MINOR' for x in fs),'unknown':sum(x['severity']=='UNKNOWN' for x in fs),'evidence_refs':['CALIBRATION-CONTROL'],'audited_review_round':ROUND,'audited_native_validation':'CALIBRATION-NATIVE','audited_acceptance_criteria':['CAL-AC-001'],'audit_scope':['calibration machinery']}

def native(head=None):
 return {'repository':'ramgolladi1503-sys/tradebot','branch':'research/mros-program-v1','head':head or CANDIDATE,'validator':'scripts/mros/calibrate_review_audit_board.py','python_version':f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}','command':'python3 scripts/mros/calibrate_review_audit_board.py','checks':1,'passed':1,'failed':0,'exit_code':0,'timestamp':'2026-08-08T00:00:00Z'}

def reviews(defect=None,count=10):
 roles=['contract_compliance','negative_control','evidence_provenance','authority_promotion','causal_time','denominator_search_integrity','runtime_boundary','qa_verification','architecture_no_drift','adversarial_red_team'][:count]
 out=[]
 for i,r in enumerate(roles,1):
  fs=[];v='PASS'
  if i==1 and defect:
   sev={'major':'MAJOR','critical':'CRITICAL','unknown':'UNKNOWN','minor':'MINOR'}[defect];fs=[finding('CAL-'+sev,sev)];v={'major':'REPAIR_REQUIRED','critical':'FAIL','unknown':'UNKNOWN','minor':'PASS_WITH_MINOR_FINDINGS'}[defect]
  out.append((f'reviewer-{i:02d}.json',review(r,v,fs)))
 return out

def audits(defect=None,count=10):
 roles=['evidence_chain','review_independence','acceptance_criteria','regression','program_state','scope_no_drift','scientific_integrity','reproducibility','authority','adversarial_acceptance'][:count]
 out=[]
 for i,r in enumerate(roles,1):
  fs=[];v='PASS'
  if i==1 and defect:
   sev={'major':'MAJOR','critical':'CRITICAL','unknown':'UNKNOWN','minor':'MINOR'}[defect];fs=[finding('CAL-A-'+sev,sev)];v={'major':'REPAIR_REQUIRED','critical':'FAIL','unknown':'UNKNOWN','minor':'PASS_WITH_MINOR_FINDINGS'}[defect]
  out.append((f'auditor-{i:02d}.json',audit(r,v,fs)))
 return out

def main():
 checks=[]
 def ck(name,cond): checks.append((name,bool(cond)))
 ck('known_good_review_schema',not validate_review(review('contract_compliance'),CANDIDATE))
 ck('stale_head_review_rejected',bool(validate_review(review('contract_compliance',head='0'*40),CANDIDATE)))
 ck('fake_independent_review_rejected',bool(validate_review(review('contract_compliance',independent=False),CANDIDATE)))
 malformed=review('contract_compliance');malformed.pop('evidence_refs');ck('malformed_review_rejected',bool(validate_review(malformed,CANDIDATE)))
 ck('known_good_audit_schema',not validate_audit(audit('evidence_chain'),CANDIDATE,ROUND))
 ck('stale_head_audit_rejected',bool(validate_audit(audit('evidence_chain',head='0'*40),CANDIDATE,ROUND)))
 ck('fake_independent_audit_rejected',bool(validate_audit(audit('evidence_chain',independent=False),CANDIDATE,ROUND)))
 n=native()
 for defect,expected in [(None,'PASS'),('minor','PASS_WITH_MINOR_FINDINGS'),('major','REPAIR_REQUIRED'),('unknown','UNKNOWN'),('critical','REVIEW_DISAGREEMENT_REQUIRES_ADJUDICATION')]: ck('review_aggregate_'+(defect or 'good'),aggregate_reviews(reviews(defect),candidate_head=CANDIDATE,native=n)['decision']==expected)
 ck('review_quorum_10_enforced',aggregate_reviews(reviews(count=9),candidate_head=CANDIDATE,native=n)['decision']=='INSUFFICIENT_VALID_INDEPENDENT_REVIEWS')
 rg=aggregate_reviews(reviews(),candidate_head=CANDIDATE,native=n)
 for defect,expected in [(None,'PASS'),('minor','PASS_WITH_MINOR_FINDINGS'),('major','REPAIR_REQUIRED'),('unknown','UNKNOWN'),('critical','AUDIT_DISAGREEMENT_REQUIRES_ADJUDICATION')]: ck('audit_aggregate_'+(defect or 'good'),aggregate_audits(audits(defect),candidate_head=CANDIDATE,review=rg,review_round=ROUND,native=n)['decision']==expected)
 ck('audit_quorum_10_enforced',aggregate_audits(audits(count=9),candidate_head=CANDIDATE,review=rg,review_round=ROUND,native=n)['decision']=='INSUFFICIENT_VALID_INDEPENDENT_AUDITS')
 ck('wrong_native_head_blocks_review',aggregate_reviews(reviews(),candidate_head=CANDIDATE,native=native('0'*40))['decision']=='REVIEW_BLOCKED_NATIVE_VALIDATION_REQUIRED')
 ag=aggregate_audits(audits(),candidate_head=CANDIDATE,review=rg,review_round=ROUND,native=n)
 ck('legal_advancement_authorization',authorize(sprint='S003',next_sprint='S004',candidate_head=CANDIDATE,review=rg,audit=ag,native=n,acceptance_criteria_satisfied=True,state_consistent=True)['advance'] is True)
 ck('state_consistency_required',authorize(sprint='S003',next_sprint='S004',candidate_head=CANDIDATE,review=rg,audit=ag,native=n,acceptance_criteria_satisfied=True,state_consistent=False)['advance'] is False)
 m9=authorize(sprint='S110',next_sprint='S111',candidate_head=CANDIDATE,review=rg,audit=ag,native=n,acceptance_criteria_satisfied=True,state_consistent=True);ck('m9_hard_stop',not m9['advance'] and 'M9_HARD_STOP' in m9['errors'])
 ck('runtime_authority_boundary',authorize(sprint='S003',next_sprint='S004',candidate_head=CANDIDATE,review=rg,audit=ag,native=n,acceptance_criteria_satisfied=True,state_consistent=True).get('runtime_authority')=='NONE')
 passed=sum(ok for _,ok in checks);failed=len(checks)-passed
 for name,ok in checks: print(f"{'PASS' if ok else 'FAIL'} | {name}")
 print(f'SUMMARY | checks={len(checks)} pass={passed} fail={failed}')
 print('S003_BOARD_DETERMINISTIC_CALIBRATION_PASS' if failed==0 else 'S003_BOARD_DETERMINISTIC_CALIBRATION_FAIL')
 return 0 if failed==0 else 1
if __name__=='__main__': raise SystemExit(main())
