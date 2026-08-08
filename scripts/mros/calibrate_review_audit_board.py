#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];SCRIPTS=ROOT/'scripts'/'mros';sys.path.insert(0,str(SCRIPTS))
from validate_review import validate as validate_review
from validate_audit import validate as validate_audit
from aggregate_reviews import aggregate_payloads as aggregate_reviews
from aggregate_audits import aggregate_payloads as aggregate_audits
from native_evidence import validate_native_evidence,verify_native_sources
from bridge_receipt import validate_bridge_receipt
from population_manifest import validate_population_manifest
from program_context import validate_acceptance_trace,validate_state_ledger
from advance_program import authorize
CASES=ROOT/'research/review_board/CALIBRATION_CASES.json'
REVIEW_ROLES=['contract_compliance','negative_control','evidence_provenance','authority_promotion','causal_time','denominator_search_integrity','runtime_boundary','qa_verification','architecture_no_drift','adversarial_red_team','reproducibility']
AUDIT_ROLES=['evidence_chain','review_independence','acceptance_criteria','regression','program_state','scope_no_drift','scientific_integrity','reproducibility','authority','adversarial_acceptance','artifact_completeness']

def finding(fid,sev):return {'finding_id':fid,'severity':sev,'requirement':'calibration requirement','evidence':'controlled calibration evidence','falsifier':'controlled opposite behavior','recommended_repair_scope':'calibration only'}
def jobid(i,kind='R'):return hashlib.md5(f'{kind}{i}'.encode()).hexdigest()
def review(i,head,verdict='PASS',fs=None,role=None):
 fs=fs or [];rid=f'R{i:02d}';jid=jobid(i,'R');packet=f'packets/{rid}.md';output=f'reviews/reviewer-{i:02d}.json'
 return {'artifact_id':f'CAL-{rid}','sprint':'S003','round':'R001','candidate_head':head,'role':role or REVIEW_ROLES[i-1],'execution_role_id':rid,'execution_job_id':jid,'transport':'mac_git_mailbox','packet_path':packet,'output_path':output,'runtime_authority':'NONE','broker_actions':'NONE','independent_from_implementation':True,'independent_from_review_aggregation':True,'verdict':verdict,'findings':fs,'critical':sum(x['severity']=='CRITICAL' for x in fs),'major':sum(x['severity']=='MAJOR' for x in fs),'minor':sum(x['severity']=='MINOR' for x in fs),'unknown':sum(x['severity']=='UNKNOWN' for x in fs),'evidence_refs':['CALIBRATION-CONTROL']}
def audit(i,head,verdict='PASS',fs=None,role=None):
 fs=fs or [];rid=f'A{i:02d}';jid=jobid(i,'A');packet=f'packets/{rid}.md';output=f'audits/auditor-{i:02d}.json'
 return {'artifact_id':f'CAL-{rid}','sprint':'S003','round':'A001','candidate_head':head,'role':role or AUDIT_ROLES[i-1],'execution_role_id':rid,'execution_job_id':jid,'transport':'mac_git_mailbox','packet_path':packet,'output_path':output,'runtime_authority':'NONE','broker_actions':'NONE','independent_from_implementation':True,'independent_from_review_aggregation':True,'verdict':verdict,'findings':fs,'critical':sum(x['severity']=='CRITICAL' for x in fs),'major':sum(x['severity']=='MAJOR' for x in fs),'minor':sum(x['severity']=='MINOR' for x in fs),'unknown':sum(x['severity']=='UNKNOWN' for x in fs),'evidence_refs':['CALIBRATION-CONTROL'],'audited_review_round':'R001','audited_native_validation':'CALIBRATION-NATIVE','audited_acceptance_criteria':['S003-AC-001'],'audit_scope':['calibration machinery']}
def receipt(a,head,job_type):
 return {'schema_version':1,'worker_id':'calibration-worker','runtime_authority':'NONE','broker_actions_allowed':False,'request':{'candidate_sha':head,'job_type':job_type,'role_id':a['execution_role_id'],'packet_path':a['packet_path'],'output_path':a['output_path']},'job':{'candidate_sha':head,'job_type':job_type,'role_id':a['execution_role_id'],'job_id':a['execution_job_id'],'packet_path':a['packet_path'],'output_path':a['output_path'],'state':'SUCCEEDED','exit_code':0,'command_hash':'a'*64,'created_at':1.0,'started_at':2.0,'finished_at':3.0}}
def manifest(items,head,job_type,round_id):
 return {'schema_version':'mros-agent-population-v1','job_type':job_type,'candidate_head':head,'sprint':'S003','round':round_id,'frozen_before_execution':True,'expected_count':len(items),'members':[{'execution_role_id':a['execution_role_id'],'semantic_role':a['role'],'packet_path':a['packet_path'],'output_path':a['output_path'],'receipt_path':f"receipts/{a['execution_role_id']}.json"} for a in items]}
def bundle(items,head,job_type,round_id):return [(a['output_path'],a) for a in items],{a['execution_job_id']:receipt(a,head,job_type) for a in items},manifest(items,head,job_type,round_id)
def native(head):
 source='CALIBRATION_NATIVE_OUTPUT';jid=jobid(96,'R')
 d={'schema_version':'mros-native-evidence-v2','evidence_kind':'native_validation','repository':'ramgolladi1503-sys/tradebot','branch':'research/mros-program-v1','head':head,'validator':'scripts/mros/calibrate_review_audit_board.py','python_version':f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}','command':f'python3 scripts/mros/calibrate_review_audit_board.py --candidate-head {head}','checks':32,'passed':32,'failed':0,'exit_code':0,'timestamp':'2026-08-08T00:00:00Z','transport':'mac_git_mailbox','execution_job_id':jid,'execution_receipt_ref':'receipts/R96.json','source_output_ref':'results/R96.txt','source_output_sha256':hashlib.sha256(source.encode()).hexdigest(),'runtime_authority':'NONE','broker_actions':'NONE'}
 r={'runtime_authority':'NONE','broker_actions_allowed':False,'request':{'candidate_sha':head},'job':{'candidate_sha':head,'job_id':jid,'state':'SUCCEEDED','exit_code':0}}
 return d,source,r
def accept_trace(head,ok=True):return {'schema_version':'mros-sprint-acceptance-trace-v1','sprint':'S003','candidate_head':head,'authority':'Research / R','runtime_authority':'NONE','m9_status':'NOT_STARTED','criteria':[{'id':'S003-AC-001','status':'PASS' if ok else 'FAIL','evidence_refs':['CAL-OUT']}]}
def state_text(active='S003',runtime='NONE',m9='NOT_STARTED'):return f'active_sprint: {active}\nmilestone_status:\n  M9: {m9}\nauthority:\n  runtime_authority: {runtime}\n'
def ledger_text():return json.dumps({'sprint_id':'S003','decision':'ACTIVE'})+'\n'
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate-head',required=True);a=p.parse_args();observed=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();head=a.candidate_head
 registry=json.loads(CASES.read_text());declared=registry.get('cases',[]);outcomes={}
 def record(cid,accept):outcomes[cid]=bool(accept)
 if observed!=head:print(f'FAIL | exact_candidate_head_binding | observed={observed}');return 1
 # 001-008 schema/receipt controls
 r=review(1,head);record('CAL-001',not validate_review(r,head) and not validate_bridge_receipt(receipt(r,head,'reviewer'),r,candidate_head=head,job_type='reviewer'))
 x=dict(r);x['candidate_head']='0'*40;record('CAL-002',not bool(validate_review(x,head)))
 x=dict(r);x['independent_from_implementation']=False;record('CAL-003',not bool(validate_review(x,head)))
 x=dict(r);x['verdict']='MAYBE';record('CAL-004',not bool(validate_review(x,head)))
 au=audit(1,head);record('CAL-005',not validate_audit(au,head,'R001') and not validate_bridge_receipt(receipt(au,head,'auditor'),au,candidate_head=head,job_type='auditor'))
 x=dict(au);x['candidate_head']='0'*40;record('CAL-006',not bool(validate_audit(x,head,'R001')))
 x=dict(au);x['independent_from_implementation']=False;record('CAL-007',not bool(validate_audit(x,head,'R001')))
 x=dict(au);x['role']='bad';record('CAL-008',not bool(validate_audit(x,head,'R001')))
 # 009-016 review aggregation
 base=[review(i,head) for i in range(1,11)];pl,rc,mf=bundle(base,head,'reviewer','R001');record('CAL-009',aggregate_reviews(pl,candidate_head=head,receipts=rc,manifest=mf)['decision']=='PASS')
 pl9,rc9,mf10=bundle(base,head,'reviewer','R001');pl9=pl9[:9];rc9={k:v for k,v in list(rc9.items())[:9]};record('CAL-010',aggregate_reviews(pl9,candidate_head=head,receipts=rc9,manifest=mf10)['decision']!='PASS')
 dup=list(base);dup[-1]=dict(dup[-1]);dup[-1]['role']=dup[0]['role'];pld,rcd,mfd=bundle(dup,head,'reviewer','R001');record('CAL-011',aggregate_reviews(pld,candidate_head=head,receipts=rcd,manifest=mfd)['decision']!='PASS')
 extra=review(11,head);ple,rce,mfe=bundle(base,head,'reviewer','R001');ple.append((extra['output_path'],extra));rce[extra['execution_job_id']]=receipt(extra,head,'reviewer');record('CAL-012',aggregate_reviews(ple,candidate_head=head,receipts=rce,manifest=mfe)['decision']!='PASS')
 for cid,verdict,fs in [('CAL-013','REPAIR_REQUIRED',[finding('M','MAJOR')]),('CAL-014','FAIL',[finding('C','CRITICAL')]),('CAL-015','UNKNOWN',[]),('CAL-016','FAIL',[])]:
  arr=list(base);arr[0]=review(1,head,verdict,fs);plx,rcx,mfx=bundle(arr,head,'reviewer','R001');record(cid,aggregate_reviews(plx,candidate_head=head,receipts=rcx,manifest=mfx)['decision']!='PASS')
 # 017-024 audit aggregation
 abase=[audit(i,head) for i in range(1,11)];apl,arc,amf=bundle(abase,head,'auditor','A001');record('CAL-017',aggregate_audits(apl,candidate_head=head,review_round='R001',receipts=arc,manifest=amf)['decision']=='PASS')
 apl9,arc9,amf10=bundle(abase,head,'auditor','A001');apl9=apl9[:9];arc9={k:v for k,v in list(arc9.items())[:9]};record('CAL-018',aggregate_audits(apl9,candidate_head=head,review_round='R001',receipts=arc9,manifest=amf10)['decision']!='PASS')
 dup=list(abase);dup[-1]=dict(dup[-1]);dup[-1]['role']=dup[0]['role'];pld,rcd,mfd=bundle(dup,head,'auditor','A001');record('CAL-019',aggregate_audits(pld,candidate_head=head,review_round='R001',receipts=rcd,manifest=mfd)['decision']!='PASS')
 extra=audit(11,head);ple,rce,mfe=bundle(abase,head,'auditor','A001');ple.append((extra['output_path'],extra));rce[extra['execution_job_id']]=receipt(extra,head,'auditor');record('CAL-020',aggregate_audits(ple,candidate_head=head,review_round='R001',receipts=rce,manifest=mfe)['decision']!='PASS')
 for cid,verdict,fs in [('CAL-021','REPAIR_REQUIRED',[finding('M','MAJOR')]),('CAL-022','FAIL',[finding('C','CRITICAL')]),('CAL-023','UNKNOWN',[]),('CAL-024','FAIL',[])]:
  arr=list(abase);arr[0]=audit(1,head,verdict,fs);plx,rcx,mfx=bundle(arr,head,'auditor','A001');record(cid,aggregate_audits(plx,candidate_head=head,review_round='R001',receipts=rcx,manifest=mfx)['decision']!='PASS')
 # 025-031 provenance/context attacks
 n,src,nr=native(head);bad=dict(n);bad['head']='0'*40;record('CAL-025',not not validate_native_evidence(bad,head))
 bad=dict(n);bad['source_output_sha256']='0'*64;record('CAL-026',not not verify_native_sources(bad,source_output_text=src,receipt=nr,candidate_head=head))
 old='0'*40;rev=aggregate_reviews(*bundle(base,head,'reviewer','R001')[:1],candidate_head=head) if False else aggregate_reviews(pl,candidate_head=head,receipts=rc,manifest=mf);aud=aggregate_audits(apl,candidate_head=head,review_round='R001',receipts=arc,manifest=amf);oldrev=dict(rev);oldrev['candidate_head']=old;olda=dict(aud);olda['candidate_head']=old;oldn=dict(n);oldn['head']=old;record('CAL-027',not authorize(sprint='S003',next_sprint='S004',candidate_head=head,review=oldrev,audit=olda,native=oldn,context_errors=[] )['advance'])
 record('CAL-028',bool(validate_acceptance_trace(accept_trace(head,False),sprint='S003',candidate_head=head)) is True)
 record('CAL-029',bool(validate_state_ledger(state_text(active='S004'),ledger_text(),sprint='S003',next_sprint='S004')) is True)
 record('CAL-030',bool(validate_state_ledger(state_text(),ledger_text(),sprint='S003',next_sprint='S111')) is True)
 badr=receipt(r,head,'reviewer');badr['runtime_authority']='LIVE';record('CAL-031',bool(validate_bridge_receipt(badr,r,candidate_head=head,job_type='reviewer')) is True)
 # 032 clean advancement
 rev=aggregate_reviews(pl,candidate_head=head,receipts=rc,manifest=mf);aud=aggregate_audits(apl,candidate_head=head,review_round='R001',receipts=arc,manifest=amf);context_errors=validate_acceptance_trace(accept_trace(head,True),sprint='S003',candidate_head=head)+validate_state_ledger(state_text(),ledger_text(),sprint='S003',next_sprint='S004');record('CAL-032',authorize(sprint='S003',next_sprint='S004',candidate_head=head,review=rev,audit=aud,native=n,context_errors=context_errors)['advance'])
 declared_ids=[c['id'] for c in declared];missing=sorted(set(declared_ids)-set(outcomes));extra_ids=sorted(set(outcomes)-set(declared_ids));good=[c for c in declared if c['class']=='GOOD'];badcases=[c for c in declared if c['class']=='BAD']
 false_accept=sum(1 for c in badcases if outcomes.get(c['id']) is True);false_reject=sum(1 for c in good if outcomes.get(c['id']) is False);bad_detect=sum(1 for c in badcases if outcomes.get(c['id']) is False);good_accept=sum(1 for c in good if outcomes.get(c['id']) is True)
 failures=[]
 for c in declared:
  expected=c['expected']=='ACCEPT';observed_accept=outcomes.get(c['id']);ok=observed_accept is expected;print(f"{'PASS' if ok else 'FAIL'} | {c['id']} | expected={c['expected']} observed={'ACCEPT' if observed_accept else 'REJECT'}");
  if not ok:failures.append(c['id'])
 metrics={'known_bad_detection_rate':bad_detect/len(badcases),'false_acceptance_rate':false_accept/len(badcases),'known_good_acceptance_rate':good_accept/len(good),'false_rejection_rate':false_reject/len(good),'declared_cases':len(declared),'executed_cases':len(outcomes),'missing_cases':missing,'extra_cases':extra_ids}
 print('METRICS | '+json.dumps(metrics,sort_keys=True));denom_ok=not missing and not extra_ids and len(outcomes)==len(declared);metrics_ok=metrics['known_bad_detection_rate']==1.0 and metrics['false_acceptance_rate']==0.0 and metrics['known_good_acceptance_rate']==1.0 and metrics['false_rejection_rate']==0.0 and denom_ok
 print(f"SUMMARY | cases={len(declared)} pass={len(declared)-len(failures)} fail={len(failures)} denominator_conserved={str(denom_ok).lower()}");print('S003_BOARD_DETERMINISTIC_CALIBRATION_PASS' if metrics_ok and not failures else 'S003_BOARD_DETERMINISTIC_CALIBRATION_FAIL');return 0 if metrics_ok and not failures else 1
if __name__=='__main__':raise SystemExit(main())
