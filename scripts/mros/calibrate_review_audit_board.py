#!/usr/bin/env python3
from __future__ import annotations
import argparse,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];SCRIPTS=ROOT/'scripts'/'mros';sys.path.insert(0,str(SCRIPTS))
from validate_review import validate as validate_review
from validate_audit import validate as validate_audit
from aggregate_reviews import aggregate_payloads as aggregate_reviews
from aggregate_audits import aggregate_payloads as aggregate_audits
from native_evidence import validate_native_evidence
from advance_program import authorize
REVIEW_ROLES=['contract_compliance','negative_control','evidence_provenance','authority_promotion','causal_time','denominator_search_integrity','runtime_boundary','qa_verification','architecture_no_drift','adversarial_red_team','reproducibility']
AUDIT_ROLES=['evidence_chain','review_independence','acceptance_criteria','regression','program_state','scope_no_drift','scientific_integrity','reproducibility','authority','adversarial_acceptance','artifact_completeness']

def finding(fid,sev):return {'finding_id':fid,'severity':sev,'requirement':'calibration requirement','evidence':'controlled calibration evidence','falsifier':'controlled opposite behavior','recommended_repair_scope':'calibration only'}
def review(i,head,verdict='PASS',fs=None,role=None):
 fs=fs or [];return {'artifact_id':f'CAL-R{i:02d}','sprint':'S003','round':'R001','candidate_head':head,'role':role or REVIEW_ROLES[i-1],'independent_from_implementation':True,'independent_from_review_aggregation':True,'verdict':verdict,'findings':fs,'critical':sum(x['severity']=='CRITICAL' for x in fs),'major':sum(x['severity']=='MAJOR' for x in fs),'minor':sum(x['severity']=='MINOR' for x in fs),'unknown':sum(x['severity']=='UNKNOWN' for x in fs),'evidence_refs':['CALIBRATION-CONTROL']}
def audit(i,head,verdict='PASS',fs=None,role=None):
 fs=fs or [];return {'artifact_id':f'CAL-A{i:02d}','sprint':'S003','round':'A001','candidate_head':head,'role':role or AUDIT_ROLES[i-1],'independent_from_implementation':True,'independent_from_review_aggregation':True,'verdict':verdict,'findings':fs,'critical':sum(x['severity']=='CRITICAL' for x in fs),'major':sum(x['severity']=='MAJOR' for x in fs),'minor':sum(x['severity']=='MINOR' for x in fs),'unknown':sum(x['severity']=='UNKNOWN' for x in fs),'evidence_refs':['CALIBRATION-CONTROL'],'audited_review_round':'R001','audited_native_validation':'CALIBRATION-NATIVE','audited_acceptance_criteria':['CAL-AC-001'],'audit_scope':['calibration machinery']}
def native(head):return {'repository':'ramgolladi1503-sys/tradebot','branch':'research/mros-program-v1','head':head,'validator':'scripts/mros/calibrate_review_audit_board.py','python_version':f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}','command':f'python3 scripts/mros/calibrate_review_audit_board.py --candidate-head {head}','checks':1,'passed':1,'failed':0,'exit_code':0,'timestamp':'2026-08-08T00:00:00Z'}
def named(xs,prefix):return [(f'{prefix}-{i:02d}.json',x) for i,x in enumerate(xs,1)]
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate-head',required=True);a=p.parse_args();observed=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 checks=[]
 def ck(name,ok,detail=''):checks.append((name,bool(ok),detail))
 ck('exact_candidate_head_binding',observed==a.candidate_head,f'observed={observed}')
 head=a.candidate_head
 # schema controls
 r=review(1,head);ck('known_good_review_schema',not validate_review(r,head))
 for field,value in [('role','not_a_role'),('verdict','MAYBE'),('round','BAD')]:
  x=dict(r);x[field]=value;ck(f'invalid_review_{field}_rejected',bool(validate_review(x,head)))
 x=dict(r);x['candidate_head']='0'*40;ck('stale_head_review_rejected',bool(validate_review(x,head)))
 x=dict(r);x['independent_from_implementation']=False;ck('fake_independent_review_rejected',bool(validate_review(x,head)))
 x=dict(r);x.pop('evidence_refs');ck('malformed_review_rejected',bool(validate_review(x,head)))
 au=audit(1,head);ck('known_good_audit_schema',not validate_audit(au,head,'R001'))
 for field,value in [('role','not_a_role'),('verdict','MAYBE'),('round','BAD')]:
  x=dict(au);x[field]=value;ck(f'invalid_audit_{field}_rejected',bool(validate_audit(x,head,'R001')))
 x=dict(au);x['candidate_head']='0'*40;ck('stale_head_audit_rejected',bool(validate_audit(x,head,'R001')))
 x=dict(au);x['independent_from_implementation']=False;ck('fake_independent_audit_rejected',bool(validate_audit(x,head,'R001')))
 # strict native evidence controls; these are synthetic calibration fixtures, never certifying evidence
 n=native(head);ck('native_good_fixture_valid',not validate_native_evidence(n,head))
 for name,mut in [('wrong_head',{'head':'0'*40}),('wrong_repo',{'repository':'x/y'}),('wrong_branch',{'branch':'main'}),('bad_counts',{'checks':2,'passed':1,'failed':0}),('bool_count',{'checks':True}),('validator_command_mismatch',{'command':'python3 other.py'}),('bad_timestamp',{'timestamp':'not-time'})]:
  x=dict(n);x.update(mut);ck(f'native_{name}_rejected',bool(validate_native_evidence(x,head)))
 # review aggregation
 base=[review(i,head) for i in range(1,11)];ck('review_aggregate_good',aggregate_reviews(named(base,'r'),candidate_head=head)['decision']=='PASS')
 x=[review(i,head) for i in range(1,10)];ck('review_quorum_10_enforced',aggregate_reviews(named(x,'r'),candidate_head=head)['decision']=='INSUFFICIENT_VALID_INDEPENDENT_REVIEWS')
 x=list(base);x[0]=review(1,head,'PASS_WITH_MINOR_FINDINGS',[finding('MIN','MINOR')]);ck('review_minor',aggregate_reviews(named(x,'r'),candidate_head=head)['decision']=='PASS_WITH_MINOR_FINDINGS')
 x=list(base);x[0]=review(1,head,'REPAIR_REQUIRED',[finding('MAJ','MAJOR')]);ck('review_major_blocks',aggregate_reviews(named(x,'r'),candidate_head=head)['decision']=='REPAIR_REQUIRED')
 x=list(base);x[0]=review(1,head,'FAIL',[finding('CRI','CRITICAL')]);ck('review_critical_not_outvoted',aggregate_reviews(named(x,'r'),candidate_head=head)['decision']=='REVIEW_DISAGREEMENT_REQUIRES_ADJUDICATION')
 x=list(base)+[review(11,head,'UNKNOWN',[])];ck('review_verdict_only_unknown_blocks',aggregate_reviews(named(x,'r'),candidate_head=head)['decision']=='UNKNOWN')
 x=list(base)+[review(11,head,'FAIL',[])];ck('review_fail_cannot_be_majority_masked',aggregate_reviews(named(x,'r'),candidate_head=head)['decision']=='REVIEW_DISAGREEMENT_REQUIRES_ADJUDICATION')
 x=list(base);x[9]=review(10,head,role=REVIEW_ROLES[0]);ck('review_duplicate_role_not_quorum',aggregate_reviews(named(x,'r'),candidate_head=head)['decision']=='INSUFFICIENT_VALID_INDEPENDENT_REVIEWS')
 # audit aggregation
 abase=[audit(i,head) for i in range(1,11)];ck('audit_aggregate_good',aggregate_audits(named(abase,'a'),candidate_head=head,review_round='R001')['decision']=='PASS')
 x=list(abase);x[0]=audit(1,head,'PASS_WITH_MINOR_FINDINGS',[finding('AMIN','MINOR')]);ck('audit_minor',aggregate_audits(named(x,'a'),candidate_head=head,review_round='R001')['decision']=='PASS_WITH_MINOR_FINDINGS')
 x=list(abase);x[0]=audit(1,head,'REPAIR_REQUIRED',[finding('AMAJ','MAJOR')]);ck('audit_major_blocks',aggregate_audits(named(x,'a'),candidate_head=head,review_round='R001')['decision']=='REPAIR_REQUIRED')
 x=list(abase);x[0]=audit(1,head,'FAIL',[finding('ACRI','CRITICAL')]);ck('audit_critical_not_outvoted',aggregate_audits(named(x,'a'),candidate_head=head,review_round='R001')['decision']=='AUDIT_DISAGREEMENT_REQUIRES_ADJUDICATION')
 x=list(abase)+[audit(11,head,'UNKNOWN',[])];ck('audit_verdict_only_unknown_blocks',aggregate_audits(named(x,'a'),candidate_head=head,review_round='R001')['decision']=='UNKNOWN')
 x=list(abase)+[audit(11,head,'FAIL',[])];ck('audit_fail_cannot_be_majority_masked',aggregate_audits(named(x,'a'),candidate_head=head,review_round='R001')['decision']=='AUDIT_DISAGREEMENT_REQUIRES_ADJUDICATION')
 x=list(abase);x[9]=audit(10,head,role=AUDIT_ROLES[0]);ck('audit_duplicate_role_not_quorum',aggregate_audits(named(x,'a'),candidate_head=head,review_round='R001')['decision']=='INSUFFICIENT_VALID_INDEPENDENT_AUDITS')
 # advancement
 rev=aggregate_reviews(named(base,'r'),candidate_head=head);aud=aggregate_audits(named(abase,'a'),candidate_head=head,review_round='R001')
 ck('legal_advancement_authorization',authorize(sprint='S003',next_sprint='S004',candidate_head=head,review=rev,audit=aud,native=n,acceptance_criteria_satisfied=True,state_consistent=True)['advance'])
 ck('state_consistency_required',not authorize(sprint='S003',next_sprint='S004',candidate_head=head,review=rev,audit=aud,native=n,acceptance_criteria_satisfied=True,state_consistent=False)['advance'])
 ck('m9_hard_stop',not authorize(sprint='S110',next_sprint='S111',candidate_head=head,review=rev,audit=aud,native=n,acceptance_criteria_satisfied=True,state_consistent=True)['advance'])
 ck('runtime_authority_boundary',authorize(sprint='S003',next_sprint='S004',candidate_head=head,review=rev,audit=aud,native=n,acceptance_criteria_satisfied=True,state_consistent=True).get('runtime_authority')=='NONE')
 passed=sum(ok for _,ok,_ in checks);failed=len(checks)-passed
 for name,ok,detail in checks:print(f"{'PASS' if ok else 'FAIL'} | {name}"+(f' | {detail}' if detail and not ok else ''))
 print(f'SUMMARY | checks={len(checks)} pass={passed} fail={failed}')
 print('S003_BOARD_DETERMINISTIC_CALIBRATION_PASS' if not failed else 'S003_BOARD_DETERMINISTIC_CALIBRATION_FAIL')
 return 0 if not failed else 1
if __name__=='__main__':raise SystemExit(main())
