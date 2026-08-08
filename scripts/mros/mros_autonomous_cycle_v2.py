#!/usr/bin/env python3
"""Safe S003 launcher with deterministic controller-owned review transport identity."""
from __future__ import annotations
import json,subprocess,time
from pathlib import Path
import mros_autonomous_cycle as cycle
from mros_review_transport import canonicalize_artifact, invalid_roles, member_for_output

_ORIG_EXACT_POPULATION=cycle.exact_population;_ORIG_RECORD_AGGREGATE=cycle.record_aggregate;_ORIG_QUEUE_AUDIT=cycle.queue_audit
CANONICAL_NATIVE=Path('research/evidence/sprints/S003/S003_AUTONOMOUS_NATIVE_EVIDENCE.json')

def safe_run(cwd,*args:str,timeout:int=1200,check:bool=True):
 p=subprocess.run(list(args),cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout,check=False)
 if check and p.returncode!=0:raise cycle.CycleError(f"COMMAND_FAILED:{' '.join(args)}:{(p.stderr or p.stdout or '')[-4000:]}")
 return p

def exact_population_v2(q:Path,manifest:dict):
 complete,payloads,receipts=_ORIG_EXACT_POPULATION(q,manifest)
 if not complete:return complete,payloads,receipts
 canonical=[]
 for output_path,artifact in payloads:
  member=member_for_output(manifest,output_path,q)
  if not member:return False,[],{}
  receipt_path=member.get('receipt_path')
  if not isinstance(receipt_path,str):return False,[],{}
  try:receipt=cycle.read_json(q/receipt_path)
  except Exception:return False,[],{}
  canonical.append((member['output_path'],canonicalize_artifact(artifact,member=member,manifest=manifest,receipt=receipt,queue_repo=q)))
 return True,canonical,receipts

def blocking_findings_v2(aggregate:dict,kind:str):
 out=[];plural='reviews' if kind=='review' else 'audits'
 for item in aggregate.get(plural,[]):
  if isinstance(item,dict):out.extend(f for f in item.get('findings',[]) if isinstance(f,dict) and f.get('severity') in {'CRITICAL','MAJOR','UNKNOWN'})
 seen=set();ded=[]
 for f in out:
  key=(f.get('requirement'),f.get('evidence'),f.get('severity'))
  if key not in seen:seen.add(key);ded.append(f)
 return ded

def _transport_invalid_old(old:dict,kind:str)->bool:
 valid_key='valid_reviews' if kind=='review' else 'valid_audits'
 return str(old.get('decision')) in {'INCOMPLETE_OR_UNDECLARED_REVIEW_POPULATION','INCOMPLETE_OR_UNDECLARED_AUDIT_POPULATION'} and int(old.get(valid_key) or 0)==0 and bool(old.get('invalid'))

def record_aggregate_v2(auth:Path,aggregate:dict,kind:str,round_id:str,candidate:str):
 ap=cycle.aggregate_path(kind,round_id);cp=cycle.contract_path(kind,round_id);current=auth/ap
 if current.is_file():
  old=cycle.read_json(current)
  if _transport_invalid_old(old,kind) and not aggregate.get('invalid'):
   archive=ap.with_name(ap.stem+'_TRANSPORT_INVALID_ARCHIVE.json');changed=[];archive_file=auth/archive
   if not archive_file.is_file():archive_file.write_text(json.dumps(old,sort_keys=True,indent=2)+'\n',encoding='utf-8');changed.append(archive)
   current.write_text(json.dumps(aggregate,sort_keys=True,indent=2)+'\n',encoding='utf-8');changed.append(ap);decision=str(aggregate.get('decision'));state_path=auth/cycle.STATE;original_state=state_path.read_text(encoding='utf-8');state=original_state
   if decision not in cycle.PASS:
    contract={'schema_version':'mros-repair-contract-v2','sprint':'S003','failed_head':candidate,'source_kind':kind,'source_round':round_id,'aggregate_decision':decision,'blocking_findings':blocking_findings_v2(aggregate,kind),'invalid_artifacts':[],'superseded_transport_invalid_artifacts':old.get('invalid',[]),'root_cause_instruction':'Repair only findings from valid independent artifacts. Transport-invalid artifacts are historical evidence and cannot contribute implementation findings.','repair_scope':{'allowed':['scripts/mros/','tests/mros/','research/review_board/','research/audit_board/'],'forbidden':['research/program/','runtime/strategy/risk/execution/broker code','weaken fixtures or acceptance criteria','begin M9','create runtime authority']},'runtime_authority':'NONE','m9_status':'NOT_STARTED'}
    (auth/cp).write_text(json.dumps(contract,sort_keys=True,indent=2)+'\n',encoding='utf-8');changed.append(cp);state=cycle.set_top(state,'active_sprint_status',f'BOARD_AUTONOMOUS_{round_id}_{kind.upper()}_REPAIR_REQUIRED')
   else:state=cycle.set_top(state,'active_sprint_status',f'BOARD_AUTONOMOUS_{round_id}_{kind.upper()}_PASS')
   if state!=original_state:
    state_path.write_text(state,encoding='utf-8');changed.append(cycle.STATE)
   cycle.commit_authority(auth,changed,f'mros(S003): supersede {round_id} transport-invalid {kind} aggregate with controller-normalized evidence [skip ci]');return decision,(cp if decision not in cycle.PASS else None)
 return _ORIG_RECORD_AGGREGATE(auth,aggregate,kind,round_id,candidate)

def _retry_invalid_roles(q:Path,manifest:dict,roles:list[str],round_id:str,candidate:str):
 changed=[];members={str(m.get('execution_role_id')):m for m in manifest.get('members',[]) if isinstance(m,dict) and isinstance(m.get('execution_role_id'),str)}
 for role in roles:
  member=members.get(role)
  if not member:raise cycle.CycleError(f'TRANSPORT_RETRY_MEMBER_MISSING:{role}')
  output=Path(str(member['output_path']));receipt=Path(str(member['receipt_path']));request=cycle.ROOT/'requests'/output.name;request_file=q/request
  if not request_file.is_file():raise cycle.CycleError(f'TRANSPORT_RETRY_REQUEST_MISSING:{role}')
  req=cycle.read_json(request_file);retry=int(req.get('transport_retry') or 0)+1
  if retry>3:raise cycle.CycleError(f'TRANSPORT_RETRY_LIMIT_EXCEEDED:{round_id}:{role}')
  req['transport_retry']=retry;req['request_id']=f'S003-{round_id}-{role}-{candidate[:8]}-transport-retry{retry}';req['controller_transport']={'candidate_head':candidate,'sprint':manifest.get('sprint'),'round':manifest.get('round'),'execution_role_id':role,'packet_path':member.get('packet_path'),'output_path':member.get('output_path'),'receipt_path':member.get('receipt_path')};request_file.write_text(json.dumps(req,sort_keys=True,indent=2)+'\n',encoding='utf-8');changed.append(request)
  for rel in (output,receipt):
   path=q/rel
   if path.exists():path.unlink();changed.append(rel)
 cycle.queue_commit(q,changed,f"mros(S003): retry transport-invalid {round_id} roles {','.join(roles)} [skip ci]")

def _ensure_native_evidence(auth:Path,q:Path,candidate:str)->str:
 from mros_s003_autonomous_finalizer import build_native
 path,data,source_ref,receipt_ref,receipt,source_text=build_native(auth,q,candidate)
 native_mod=cycle.load_mod(auth,'native_evidence');errs=native_mod.verify_native_sources(data,source_output_text=source_text,receipt=receipt,candidate_head=candidate,source_output_ref=source_ref,execution_receipt_ref=receipt_ref)
 if errs:raise cycle.CycleError('CANONICAL_NATIVE_SOURCE_VERIFICATION_FAILED:'+','.join(errs))
 existing=cycle.git(auth,'show',f'HEAD:{path.as_posix()}',check=False)
 if existing.returncode!=0 or existing.stdout!=(auth/path).read_text(encoding='utf-8'):
  cycle.commit_authority(auth,[path],f'mros(S003): publish canonical native evidence {candidate[:8]} before audit [skip ci]');cycle.sync(auth,q)
 return path.as_posix()

def native_ref_v2(q:Path,candidate:str):
 auth=Path('/Users/madhuram/.mros-agent-bridge/authority')
 p=auth/CANONICAL_NATIVE
 if p.is_file():
  try:
   d=cycle.read_json(p)
   if d.get('head')==candidate:return CANONICAL_NATIVE.as_posix()
  except Exception:pass
 return None

def queue_audit_v2(q:Path,auth:Path,candidate:str,review_round:str,review_aggregate:dict,full:bool=True):
 _ensure_native_evidence(auth,q,candidate);return _ORIG_QUEUE_AUDIT(q,auth,candidate,review_round,review_aggregate,full=full)

def _tempdir_infrastructure_failure(text:str)->bool:
 t=text.lower()
 return (
  'no usable temporary directory found' in t
  or ('filenotfounderror' in t and 'tempfile.py' in t)
  or ('operation not permitted' in t and ('.mros_tmp' in t or 'mkdir' in t))
 )

def calibration_status_v2(q:Path,candidate:str):
 reqs=cycle.calibration_requests(q,candidate)
 if not reqs:return 'MISSING',None
 rp,r=reqs[-1]
 rec=q/cycle.ROOT/'receipts'/rp.name;out=q/str(r.get('output_path',''))
 if not rec.is_file():return 'PENDING',None
 try:job=cycle.read_json(rec).get('job',{})
 except Exception:return 'INFRA_FAILED',None
 if job.get('state')!='SUCCEEDED' or job.get('exit_code')!=0:return 'INFRA_FAILED',None
 if not out.is_file():return 'INFRA_FAILED',None
 text=out.read_text(encoding='utf-8',errors='replace')
 if 'S003_BOARD_DETERMINISTIC_CALIBRATION_PASS' in text and 'CALIBRATION_EXECUTION_RESULT=PASS' in text:return 'PASS',str(out.relative_to(q))
 if _tempdir_infrastructure_failure(text):return 'INFRA_FAILED',str(out.relative_to(q))
 if 'CALIBRATION_EXECUTION_RESULT=FAIL' in text:return 'VALIDATION_FAILED',str(out.relative_to(q))
 return 'VALIDATION_FAILED',str(out.relative_to(q))

def queue_calibration_v2(q:Path,candidate:str,force_retry=False):
 if cycle.calibration_requests(q,candidate) and not force_retry:return 'EXISTS'
 rid=cycle.next_calibration_role(q);tag=f'S003_CALIBRATION_{rid}_{candidate[:8].upper()}';packet=cycle.ROOT/'packets'/f'{tag}.md';output=cycle.ROOT/'results'/f'{tag}.md';request=cycle.ROOT/'requests'/f'{tag}.json';(q/packet).parent.mkdir(parents=True,exist_ok=True)
 command=f'python3 scripts/mros/calibrate_review_audit_board_v2.py --candidate-head {candidate}'
 (q/packet).write_text(f'''# S003 autonomous exact-head Board calibration {rid}\n\nExact candidate: `{candidate}`\n\nNon-certifying deterministic native execution. Do not repair or review. This packet is executed by the bridge's fixed allowlisted native calibration path, not by the read-only model sandbox.\n\nRequired command semantics:\n1. `git rev-parse HEAD`\n2. `python3 --version`\n3. `{command}`\n\nReturn Markdown containing CANDIDATE_HEAD, PYTHON_VERSION, COMMAND, COMPLETE STDOUT, EXIT_CODE, RUNTIME_AUTHORITY=NONE, BROKER_ACTIONS=NONE, CALIBRATION_EXECUTION_RESULT=PASS|FAIL. PASS requires exact HEAD, every declared calibration case executed, zero failures, denominator conservation, all declared metrics satisfied, terminal `S003_BOARD_DETERMINISTIC_CALIBRATION_PASS`, and exit 0.\n''',encoding='utf-8')
 req={'schema_version':1,'request_id':f'{tag}-{int(time.time())}','created_by':'mros-autonomous-cycle-v2','created_at':cycle.datetime.date.today().isoformat(),'job_type':'reviewer','role_id':rid,'candidate_sha':candidate,'packet_path':packet.as_posix(),'output_path':output.as_posix(),'backend':'codex'};(q/request).write_text(json.dumps(req,sort_keys=True,indent=2)+'\n',encoding='utf-8');cycle.queue_commit(q,[packet,request],f'mros(S003): queue native exact-head calibration {rid} {candidate[:8]} [skip ci]');return rid

def _latest_repair_candidate(auth:Path)->str:
 evidence=[];root=auth/'research/evidence/sprints/S003'
 if root.is_dir():
  for p in root.glob('AUTONOMOUS_REPAIR_G*_*.json'):
   try:d=cycle.read_json(p);generation=int(d.get('generation') or 0)
   except Exception:continue
   evidence.append((generation,p))
 if evidence:
  _,path=sorted(evidence,key=lambda x:x[0])[-1]
  rel=path.relative_to(auth).as_posix();r=cycle.git(auth,'log','-1','--format=%H','--',rel,check=False);candidate=(r.stdout or '').strip()
  if len(candidate)==40:
   try:int(candidate,16);return candidate
   except ValueError:pass
 return cycle.git(auth,'rev-parse',f'origin/{cycle.AUTH}').stdout.strip()

def process_review_v2(auth:Path,q:Path,state_root:Path,row):
 n,mp,manifest=row;round_id=f'R{n:03d}';candidate=manifest.get('candidate_head');tier=str(manifest.get('assurance_tier') or 'FAST')
 if not isinstance(candidate,str):raise cycle.CycleError('LATEST_REVIEW_CANDIDATE_INVALID')
 complete,payloads,receipts=exact_population_v2(q,manifest)
 if not complete:return {'action':'WAIT_REVIEW','round':round_id,'candidate':candidate,'tier':tier}
 aggregate=cycle.load_mod(auth,'aggregate_reviews').aggregate_payloads(payloads,candidate_head=candidate,receipts=receipts,manifest=manifest);aggregate.update({'review_round':round_id,'population_manifest':str(mp.relative_to(q)),'assurance_tier':tier,'runtime_authority':'NONE'})
 if aggregate.get('invalid'):
  roles=invalid_roles(aggregate,manifest,q)
  if not roles:raise cycle.CycleError(f'TRANSPORT_INVALID_ROLES_UNRESOLVED:{round_id}')
  _retry_invalid_roles(q,manifest,roles,round_id,candidate);return {'action':'REVIEW_TRANSPORT_RETRY_QUEUED','round':round_id,'candidate':candidate,'roles':roles}
 decision,cp=record_aggregate_v2(auth,aggregate,'review',round_id,candidate);cycle.sync(auth,q)
 if decision not in cycle.PASS:
  prior=cycle.repair_evidence_for_failed(auth,candidate)
  if prior:
   new=_latest_repair_candidate(auth);cs,_=calibration_status_v2(q,new)
   if cs=='MISSING':queue_calibration_v2(q,new)
   elif cs=='INFRA_FAILED':queue_calibration_v2(q,new,force_retry=True)
   return {'action':'REPAIR_ALREADY_PUBLISHED','round':round_id,'new_candidate':new,'calibration':cs}
  if cp is None:raise cycle.CycleError('REPAIR_CONTRACT_MISSING')
  repair=cycle.run_repair(auth,state_root,cp);cycle.sync(auth,q);queue_calibration_v2(q,repair['candidate_head']);return {'action':'REPAIR_AND_CALIBRATE','round':round_id,'decision':decision,'new_candidate':repair['candidate_head'],'generation':repair['generation']}
 if tier!='FULL':fr=cycle.queue_review(q,candidate,full=True);return {'action':'FINAL_FULL_REVIEW_QUEUED','from_round':round_id,'round':fr,'candidate':candidate}
 cycle.queue_audit(q,auth,candidate,round_id,aggregate,full=True);return {'action':'FINAL_FULL_AUDIT_QUEUED','round':round_id,'candidate':candidate,'decision':decision}

def process_audit_v2(auth:Path,q:Path,state_root:Path,row):
 n,mp,m=row;audit_round=f'A{n:03d}';review_round=str(m.get('review_round') or '');candidate=m.get('candidate_head');tier=str(m.get('assurance_tier') or 'FAST')
 if not isinstance(candidate,str):raise cycle.CycleError('LATEST_AUDIT_CANDIDATE_INVALID')
 complete,payloads,receipts=exact_population_v2(q,m)
 if not complete:return {'action':'WAIT_AUDIT','round':audit_round,'candidate':candidate,'tier':tier}
 rap=cycle.aggregate_path('review',review_round)
 if not (auth/rap).is_file():raise cycle.CycleError('AUDIT_REVIEW_AGGREGATE_MISSING')
 review=cycle.read_json(auth/rap);contract=cycle.read_json(auth/cycle.ACCEPTANCE);required=[c.get('id') for c in contract.get('criteria',[]) if isinstance(c,dict) and isinstance(c.get('id'),str)];review_jobs=[r.get('execution_job_id') for r in review.get('reviews',[]) if isinstance(r,dict)];nref=native_ref_v2(q,candidate);aggregate=cycle.load_mod(auth,'aggregate_audits').aggregate_payloads(payloads,candidate_head=candidate,review_round=review_round,receipts=receipts,manifest=m,review_job_ids=review_jobs,required_acceptance_ids=required,expected_native_ref=nref);aggregate.update({'audit_round':audit_round,'population_manifest':str(mp.relative_to(q)),'review_aggregate':rap.as_posix(),'assurance_tier':tier,'runtime_authority':'NONE'});decision,cp=record_aggregate_v2(auth,aggregate,'audit',audit_round,candidate);cycle.sync(auth,q)
 if decision not in cycle.PASS:
  prior=cycle.repair_evidence_for_failed(auth,candidate)
  if prior:
   new=_latest_repair_candidate(auth);cs,_=calibration_status_v2(q,new)
   if cs=='MISSING':queue_calibration_v2(q,new)
   elif cs=='INFRA_FAILED':queue_calibration_v2(q,new,force_retry=True)
   return {'action':'AUDIT_REPAIR_ALREADY_PUBLISHED','round':audit_round,'new_candidate':new,'calibration':cs}
  if cp is None:raise cycle.CycleError('AUDIT_REPAIR_CONTRACT_MISSING')
  repair=cycle.run_repair(auth,state_root,cp);cycle.sync(auth,q);queue_calibration_v2(q,repair['candidate_head']);return {'action':'AUDIT_REPAIR_AND_CALIBRATE','round':audit_round,'new_candidate':repair['candidate_head'],'generation':repair['generation']}
 if tier!='FULL' or int(m.get('expected_count') or 0)<10:raise cycle.CycleError('FINAL_AUTHORIZATION_REQUIRES_FULL_AUDIT_POPULATION')
 state=(auth/cycle.STATE).read_text(encoding='utf-8')
 if 'active_sprint_status: BOARD_BOOTSTRAP_AUTHORIZATION_PENDING' in state:return {'action':'AUTHORIZATION_READY','round':audit_round,'candidate':candidate,'decision':decision}
 state=cycle.set_top(state,'active_sprint_status','BOARD_BOOTSTRAP_AUTHORIZATION_PENDING');state=cycle.set_indented(state,'bootstrap_independent_audit_status',decision);(auth/cycle.STATE).write_text(state,encoding='utf-8');sha=cycle.commit_authority(auth,[cycle.STATE],f'mros(S003): autonomous full-board audit ready for authorization {candidate[:8]} [skip ci]');return {'action':'AUTHORIZATION_READY','round':audit_round,'candidate':candidate,'decision':decision,'commit':sha}

def main()->int:
 cycle.run=safe_run;cycle.exact_population=exact_population_v2;cycle.blocking_findings=blocking_findings_v2;cycle.record_aggregate=record_aggregate_v2;cycle.process_review=process_review_v2;cycle.process_audit=process_audit_v2;cycle.current_head=_latest_repair_candidate;cycle.native_ref=native_ref_v2;cycle.queue_audit=queue_audit_v2;cycle.calibration_status=calibration_status_v2;cycle.queue_calibration=queue_calibration_v2
 result=cycle.main();return 0 if result is None else int(result)
if __name__=='__main__':raise SystemExit(main())
