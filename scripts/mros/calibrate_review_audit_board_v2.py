#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];SCRIPTS=ROOT/'scripts'/'mros';sys.path.insert(0,str(SCRIPTS))
from validate_review import validate as vr
from validate_audit import validate as va
from aggregate_reviews import aggregate_payloads as ar
from aggregate_audits import aggregate_payloads as aa
from native_evidence import validate_native_evidence,verify_native_sources
from bridge_receipt import validate_bridge_receipt
from program_context import validate_acceptance_trace,validate_state_ledger
from advance_program import authorize
from board_calibration_fixtures import review,audit,receipt,bundle,finding,native,accept_trace,state_text,ledger_text
PASS={'PASS','PASS_WITH_MINOR_FINDINGS'}

def accepted(decision):return decision in PASS

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate-head',required=True);a=p.parse_args();head=a.candidate_head
 observed=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 if observed!=head:
  print(f'FAIL | EXACT_HEAD | expected={head} observed={observed}');return 1
 registry=json.loads((ROOT/'research/review_board/CALIBRATION_CASES.json').read_text());cases=registry['cases'];out={}
 def seto(cid,value):out[cid]=bool(value)
 r1=review(1,head);seto('CAL-001',not vr(r1,head) and not validate_bridge_receipt(receipt(r1,head,'reviewer'),r1,candidate_head=head,job_type='reviewer'))
 x=dict(r1);x['candidate_head']='0'*40;seto('CAL-002',not bool(vr(x,head)))
 x=dict(r1);x['independent_from_implementation']=False;seto('CAL-003',not bool(vr(x,head)))
 x=dict(r1);x['verdict']='MAYBE';seto('CAL-004',not bool(vr(x,head)))
 a1=audit(1,head);seto('CAL-005',not va(a1,head,'R001') and not validate_bridge_receipt(receipt(a1,head,'auditor'),a1,candidate_head=head,job_type='auditor'))
 x=dict(a1);x['candidate_head']='0'*40;seto('CAL-006',not bool(va(x,head,'R001')))
 x=dict(a1);x['independent_from_implementation']=False;seto('CAL-007',not bool(va(x,head,'R001')))
 x=dict(a1);x['role']='bad';seto('CAL-008',not bool(va(x,head,'R001')))
 reviews=[review(i,head) for i in range(1,11)];rpl,rrc,rm=bundle(reviews,head,'reviewer','R001');rg=ar(rpl,candidate_head=head,receipts=rrc,manifest=rm);seto('CAL-009',accepted(rg['decision']))
 seto('CAL-010',accepted(ar(rpl[:9],candidate_head=head,receipts={k:v for k,v in list(rrc.items())[:9]},manifest=rm)['decision']))
 dups=list(reviews);dups[-1]=dict(dups[-1]);dups[-1]['role']=dups[0]['role'];pl,rc,m=bundle(dups,head,'reviewer','R001');seto('CAL-011',accepted(ar(pl,candidate_head=head,receipts=rc,manifest=m)['decision']))
 extra=review(11,head);pl=list(rpl)+[(extra['output_path'],extra)];rc=dict(rrc);rc[extra['execution_job_id']]=receipt(extra,head,'reviewer');seto('CAL-012',accepted(ar(pl,candidate_head=head,receipts=rc,manifest=rm)['decision']))
 for cid,verdict,fs in [('CAL-013','REPAIR_REQUIRED',[finding('M','MAJOR')]),('CAL-014','FAIL',[finding('C','CRITICAL')]),('CAL-015','UNKNOWN',[]),('CAL-016','FAIL',[])]:
  arr=list(reviews);arr[0]=review(1,head,verdict,fs);pl,rc,m=bundle(arr,head,'reviewer','R001');seto(cid,accepted(ar(pl,candidate_head=head,receipts=rc,manifest=m)['decision']))
 audits=[audit(i,head) for i in range(1,11)];apl,arc,am=bundle(audits,head,'auditor','A001');ag=aa(apl,candidate_head=head,review_round='R001',receipts=arc,manifest=am);seto('CAL-017',accepted(ag['decision']))
 seto('CAL-018',accepted(aa(apl[:9],candidate_head=head,review_round='R001',receipts={k:v for k,v in list(arc.items())[:9]},manifest=am)['decision']))
 dups=list(audits);dups[-1]=dict(dups[-1]);dups[-1]['role']=dups[0]['role'];pl,rc,m=bundle(dups,head,'auditor','A001');seto('CAL-019',accepted(aa(pl,candidate_head=head,review_round='R001',receipts=rc,manifest=m)['decision']))
 extra=audit(11,head);pl=list(apl)+[(extra['output_path'],extra)];rc=dict(arc);rc[extra['execution_job_id']]=receipt(extra,head,'auditor');seto('CAL-020',accepted(aa(pl,candidate_head=head,review_round='R001',receipts=rc,manifest=am)['decision']))
 for cid,verdict,fs in [('CAL-021','REPAIR_REQUIRED',[finding('M','MAJOR')]),('CAL-022','FAIL',[finding('C','CRITICAL')]),('CAL-023','UNKNOWN',[]),('CAL-024','FAIL',[])]:
  arr=list(audits);arr[0]=audit(1,head,verdict,fs);pl,rc,m=bundle(arr,head,'auditor','A001');seto(cid,accepted(aa(pl,candidate_head=head,review_round='R001',receipts=rc,manifest=m)['decision']))
 n,src,nr=native(head);bad=dict(n);bad['head']='0'*40;seto('CAL-025',not bool(validate_native_evidence(bad,head)))
 bad=dict(n);bad['source_output_sha256']='0'*64;seto('CAL-026',not bool(verify_native_sources(bad,source_output_text=src,receipt=nr,candidate_head=head,source_output_ref=n['source_output_ref'],execution_receipt_ref=n['execution_receipt_ref'])))
 old='0'*40;oldr=dict(rg);oldr['candidate_head']=old;olda=dict(ag);olda['candidate_head']=old;oldn=dict(n);oldn['head']=old;seto('CAL-027',authorize(sprint='S003',next_sprint='S004',candidate_head=head,review=oldr,audit=olda,native=oldn,context_errors=[],review_manifest=rm,audit_manifest=am,review_receipts=rrc,audit_receipts=arc)['advance'])
 seto('CAL-028',not bool(validate_acceptance_trace(accept_trace(head,False),sprint='S003',candidate_head=head)))
 seto('CAL-029',not bool(validate_state_ledger(state_text(active='S004'),ledger_text(),sprint='S003',next_sprint='S004')))
 seto('CAL-030',not bool(validate_state_ledger(state_text(),ledger_text(),sprint='S003',next_sprint='S111')))
 br=receipt(r1,head,'reviewer');br['runtime_authority']='LIVE';seto('CAL-031',not bool(validate_bridge_receipt(br,r1,candidate_head=head,job_type='reviewer')))
 ctx=validate_acceptance_trace(accept_trace(head,True),sprint='S003',candidate_head=head)+validate_state_ledger(state_text(),ledger_text(),sprint='S003',next_sprint='S004');seto('CAL-032',authorize(sprint='S003',next_sprint='S004',candidate_head=head,review=rg,audit=ag,native=n,context_errors=ctx,review_manifest=rm,audit_manifest=am,review_receipts=rrc,audit_receipts=arc)['advance'])
 x=dict(r1);x['unexpected_field']='forbidden';seto('CAL-033',not bool(vr(x,head,'S003','R001')))
 x=dict(r1);x['critical']=True;seto('CAL-034',not bool(vr(x,head,'S003','R001')))
 x=dict(r1);x['sprint']='S999';seto('CAL-035',not bool(vr(x,head,'S003','R001')))
 seto('CAL-036',not bool(verify_native_sources(n,source_output_text=src,receipt=nr,candidate_head=head,source_output_ref='results/WRONG.txt',execution_receipt_ref=n['execution_receipt_ref'])))
 br=receipt(r1,head,'reviewer');br['request']['job_type']='auditor';seto('CAL-037',not bool(validate_bridge_receipt(br,r1,candidate_head=head,job_type='reviewer')))
 br=receipt(r1,head,'reviewer');br['job'].pop('finished_at',None);seto('CAL-038',not bool(validate_bridge_receipt(br,r1,candidate_head=head,job_type='reviewer')))
 fake_review={'candidate_head':head,'decision':'PASS','critical':0,'major':0,'minor':0,'unknown':0,'runtime_authority':'NONE','authority':'Research / R','transport':'mac_git_mailbox','valid_reviews':0,'invalid_reviews':0,'expected_reviews':0,'submitted_reviews':0,'minimum_valid_reviews':0,'omitted_reviews':[],'extra_reviews':[],'manifest_errors':[],'reviews':[]};fake_audit={'candidate_head':head,'decision':'PASS','critical':0,'major':0,'minor':0,'unknown':0,'runtime_authority':'NONE','authority':'Research / R','transport':'mac_git_mailbox','valid_audits':0,'invalid_audits':0,'expected_audits':0,'submitted_audits':0,'minimum_valid_audits':0,'omitted_audits':[],'extra_audits':[],'manifest_errors':[],'audits':[],'review_round':'R001','missing_acceptance_ids':[],'unknown_acceptance_ids':[]};seto('CAL-039',authorize(sprint='S003',next_sprint='S004',candidate_head=head,review=fake_review,audit=fake_audit,native=n,context_errors=[],review_manifest=rm,audit_manifest=am,review_receipts=rrc,audit_receipts=arc)['advance'])
 blocking=list(reviews);blocking[0]=review(1,head,'REPAIR_REQUIRED',[finding('AUTH-MAJOR','MAJOR')]);forged=dict(rg);forged['reviews']=blocking;forged['critical']=0;forged['major']=0;forged['minor']=0;forged['unknown']=0;forged['decision']='PASS';seto('CAL-040',authorize(sprint='S003',next_sprint='S004',candidate_head=head,review=forged,audit=ag,native=n,context_errors=[],review_manifest=rm,audit_manifest=am,review_receipts=rrc,audit_receipts=arc)['advance'])
 small=dict(rg);small.update({'valid_reviews':1,'expected_reviews':1,'submitted_reviews':1,'minimum_valid_reviews':1,'omitted_reviews':[],'extra_reviews':[],'manifest_errors':[],'reviews':[reviews[0]],'critical':0,'major':0,'minor':0,'unknown':0,'decision':'PASS'});seto('CAL-041',authorize(sprint='S003',next_sprint='S004',candidate_head=head,review=small,audit=ag,native=n,context_errors=[],review_manifest=rm,audit_manifest=am,review_receipts=rrc,audit_receipts=arc)['advance'])
 declared={c['id']:c for c in cases};missing=sorted(set(declared)-set(out));extra_ids=sorted(set(out)-set(declared));fail=[]
 for cid,c in declared.items():
  expected=c['expected']=='ACCEPT';actual=out.get(cid);ok=(actual is expected);print(f"{'PASS' if ok else 'FAIL'} | {cid} | expected={c['expected']} observed={'ACCEPT' if actual else 'REJECT'}")
  if not ok:fail.append(cid)
 good=[c for c in cases if c['class']=='GOOD'];bad=[c for c in cases if c['class']=='BAD'];fa=sum(out.get(c['id']) is True for c in bad);fr=sum(out.get(c['id']) is False for c in good);bd=sum(out.get(c['id']) is False for c in bad);ga=sum(out.get(c['id']) is True for c in good)
 metrics={'known_bad_detection_rate':bd/len(bad),'false_acceptance_rate':fa/len(bad),'known_good_acceptance_rate':ga/len(good),'false_rejection_rate':fr/len(good),'declared_cases':len(cases),'executed_cases':len(out),'missing_cases':missing,'extra_cases':extra_ids};print('METRICS | '+json.dumps(metrics,sort_keys=True))
 ok=not fail and not missing and not extra_ids and metrics['known_bad_detection_rate']==1.0 and metrics['false_acceptance_rate']==0.0 and metrics['known_good_acceptance_rate']==1.0 and metrics['false_rejection_rate']==0.0
 print(f"SUMMARY | cases={len(cases)} pass={len(cases)-len(fail)} fail={len(fail)} denominator_conserved={str(not missing and not extra_ids).lower()}");print('S003_BOARD_DETERMINISTIC_CALIBRATION_PASS' if ok else 'S003_BOARD_DETERMINISTIC_CALIBRATION_FAIL');return 0 if ok else 1
if __name__=='__main__':raise SystemExit(main())
