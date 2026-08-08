#!/usr/bin/env python3
"""Repository-driven autonomous MROS S003 Board-bootstrap cycle.

Routine repair assurance is adaptive (FAST=3 reviewers). Once a repaired head is
clean, S003 automatically escalates exactly once to FULL=10 reviewers and then
FULL=10 auditors because Board bootstrap final authorization is an explicit
full-board boundary. No human scheduling/continuation step is required.
"""
from __future__ import annotations
import argparse,datetime,importlib,json,re,subprocess,sys,time
from pathlib import Path
AUTH='research/mros-program-v1';QUEUE='automation/mros-agent-queue-v1';SPRINT='S003'
ROOT=Path('research/evidence/sprints/S003/agent_queue');STATE=Path('research/program/MROS_PROGRAM_STATE.yaml');ACCEPTANCE=Path('research/evidence/sprints/S003/S003_ACCEPTANCE_CONTRACT.json')
PASS={'PASS','PASS_WITH_MINOR_FINDINGS'};MAX_REPAIR_GENERATIONS=5
FAST_REVIEW_ROLES={'R01':('contract_compliance','Attack exact contract/schema/invariant/evidence/provenance bindings.'),'R02':('negative_control','Attack malformed inputs, denominator/quorum laundering, stale refs, and fail-open transitions.'),'R03':('adversarial_red_team','Search independently for any remaining material authority bypass or fabricated-evidence path.')}
FULL_REVIEW_SEMANTICS=['contract_compliance','negative_control','evidence_provenance','authority_promotion','causal_time','denominator_search_integrity','runtime_boundary','qa_verification','architecture_no_drift','adversarial_red_team']
FULL_AUDIT_SEMANTICS=['evidence_chain','review_independence','acceptance_criteria','regression','program_state','scope_no_drift','scientific_integrity','reproducibility','authority','adversarial_acceptance']
class CycleError(RuntimeError):pass

def run(cwd:Path,*args:str,timeout:int=1200,check=True):
 p=subprocess.run(list(args),cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout,check=False)
 if check and p.returncode!=0:raise CycleError(f"COMMAND_FAILED:{' '.join(args)}:{(p.stdout or '')[-4000:]}")
 return p
def git(cwd:Path,*args:str,**kw):return run(cwd,'git',*args,**kw)
def read_json(p:Path):return json.loads(p.read_text(encoding='utf-8'))
def sync(auth:Path,q:Path)->None:
 git(auth,'fetch','origin',AUTH,QUEUE,timeout=300);git(q,'fetch','origin',QUEUE,AUTH,timeout=300)
 if git(auth,'status','--porcelain').stdout.strip():raise CycleError('AUTHORITY_WORKTREE_NOT_CLEAN')
 if git(q,'status','--porcelain').stdout.strip():raise CycleError('QUEUE_WORKTREE_NOT_CLEAN')
 git(auth,'merge','--ff-only',f'origin/{AUTH}',timeout=300);git(q,'rebase',f'origin/{QUEUE}',timeout=300)
def load_mod(auth:Path,name:str):
 scripts=(auth/'scripts/mros').resolve()
 if str(scripts) not in sys.path:sys.path.insert(0,str(scripts))
 if name in sys.modules:del sys.modules[name]
 return importlib.import_module(name)
def commit_authority(auth:Path,paths:list[Path],message:str)->str:
 bridge=Path('/Users/madhuram/.mros-agent-bridge/bridge/scripts/mros').resolve()
 if str(bridge) not in sys.path:sys.path.insert(0,str(bridge))
 from mros_state_transition_engine import commit_transition
 parent=git(auth,'rev-parse','HEAD').stdout.strip();r=commit_transition(repo=auth,lock_path=Path.home()/'.mros-agent-bridge/state/authority-writer.lock',expected_parent=parent,changed_paths=[p.as_posix() for p in paths],message=message);return r.commit_sha
def queue_commit(q:Path,paths:list[Path],message:str)->str:
 rel=[p.as_posix() for p in paths];git(q,'add','--',*rel);staged=set(git(q,'diff','--cached','--name-only').stdout.splitlines())
 if staged!=set(rel):git(q,'reset');raise CycleError('QUEUE_COMMIT_SCOPE_MISMATCH')
 git(q,'commit','-m',message);git(q,'fetch','origin',QUEUE,timeout=300);git(q,'rebase',f'origin/{QUEUE}',timeout=300);git(q,'push','origin',f'HEAD:{QUEUE}',timeout=300);return git(q,'rev-parse','HEAD').stdout.strip()
def set_top(text,key,value):
 pat=rf'(?m)^({re.escape(key)}:\s*).*$';return re.sub(pat,rf'\g<1>{value}',text,count=1) if re.search(pat,text) else text
def set_indented(text,key,value):
 pat=rf'(?m)^(\s+{re.escape(key)}:\s*).*$';return re.sub(pat,rf'\g<1>{value}',text,count=1) if re.search(pat,text) else text

def manifests(q:Path,job_type:str):
 d=q/ROOT/'manifests';out=[];pat=re.compile(r'S003_([RA])(\d{3})_(REVIEW|AUDIT)_POPULATION\.json$')
 if not d.is_dir():return out
 for p in d.glob('S003_*_POPULATION.json'):
  m=pat.fullmatch(p.name)
  if not m:continue
  want='reviewer' if m.group(1)=='R' else 'auditor'
  if want!=job_type:continue
  try:data=read_json(p)
  except Exception:continue
  if data.get('job_type')==job_type:out.append((int(m.group(2)),p,data))
 return sorted(out,key=lambda x:x[0])
def exact_population(q:Path,manifest:dict):
 payloads=[];receipts={}
 for m in manifest.get('members',[]):
  if not isinstance(m,dict):return False,[],{}
  op=m.get('output_path');rp=m.get('receipt_path')
  if not isinstance(op,str) or not isinstance(rp,str):return False,[],{}
  out=q/op;rec=q/rp
  if not out.is_file() or not rec.is_file():return False,[],{}
  try:d=read_json(out);r=read_json(rec)
  except Exception:return False,[],{}
  job=r.get('job') if isinstance(r,dict) else None
  if not isinstance(job,dict) or job.get('state')!='SUCCEEDED' or job.get('exit_code')!=0:return False,[],{}
  payloads.append((op,d))
  if isinstance(job.get('job_id'),str):receipts[job['job_id']]=r
 return True,payloads,receipts
def blocking_findings(aggregate:dict,kind:str):
 out=[];plural='reviews' if kind=='review' else 'audits'
 for item in aggregate.get(plural,[]):
  if isinstance(item,dict):out.extend(f for f in item.get('findings',[]) if isinstance(f,dict) and f.get('severity') in {'CRITICAL','MAJOR','UNKNOWN'})
 for bad in aggregate.get('invalid',[]):
  if isinstance(bad,dict):
   item=bad.get('review') if kind=='review' else bad.get('audit')
   if isinstance(item,dict):out.extend(f for f in item.get('findings',[]) if isinstance(f,dict) and f.get('severity') in {'CRITICAL','MAJOR','UNKNOWN'})
 seen=set();ded=[]
 for f in out:
  key=(f.get('requirement'),f.get('evidence'),f.get('severity'))
  if key not in seen:seen.add(key);ded.append(f)
 return ded
def repair_generation(auth:Path)->int:
 nums=[];d=auth/'research/evidence/sprints/S003'
 if d.is_dir():
  for p in d.glob('AUTONOMOUS_REPAIR_G*_*.json'):
   m=re.search(r'_G(\d+)_',p.name)
   if m:nums.append(int(m.group(1)))
 return max(nums,default=0)
def repair_evidence_for_failed(auth:Path,failed:str):
 d=auth/'research/evidence/sprints/S003';found=[]
 if not d.is_dir():return None
 for p in d.glob('AUTONOMOUS_REPAIR_G*_*.json'):
  try:x=read_json(p)
  except Exception:continue
  if x.get('failed_head')==failed:found.append((int(x.get('generation') or 0),x))
 return sorted(found,key=lambda z:z[0])[-1][1] if found else None
def aggregate_path(kind,round_id):return Path(f'research/evidence/sprints/S003/S003_{round_id}_{kind.upper()}_AGGREGATE.json')
def contract_path(kind,round_id):return Path(f'research/evidence/sprints/S003/S003_{round_id}_{kind.upper()}_REPAIR_CONTRACT.json')
def record_aggregate(auth:Path,aggregate:dict,kind:str,round_id:str,candidate:str):
 ap=aggregate_path(kind,round_id);cp=contract_path(kind,round_id)
 if (auth/ap).is_file():return str(read_json(auth/ap).get('decision')),(cp if (auth/cp).is_file() else None)
 (auth/ap).parent.mkdir(parents=True,exist_ok=True);(auth/ap).write_text(json.dumps(aggregate,sort_keys=True,indent=2)+'\n',encoding='utf-8');changed=[ap];decision=str(aggregate.get('decision'));state=(auth/STATE).read_text(encoding='utf-8');repair=False
 if decision not in PASS:
  contract={'schema_version':'mros-repair-contract-v2','sprint':'S003','failed_head':candidate,'source_kind':kind,'source_round':round_id,'aggregate_decision':decision,'blocking_findings':blocking_findings(aggregate,kind),'invalid_artifacts':aggregate.get('invalid',[]),'root_cause_instruction':'Cluster related findings and repair common causes once; preserve adaptive routine assurance and explicit full-board authority boundaries.','repair_scope':{'allowed':['scripts/mros/','tests/mros/','research/review_board/','research/audit_board/'],'forbidden':['research/program/','runtime/strategy/risk/execution/broker code','weaken fixtures or acceptance criteria','begin M9','create runtime authority']},'runtime_authority':'NONE','m9_status':'NOT_STARTED'};(auth/cp).write_text(json.dumps(contract,sort_keys=True,indent=2)+'\n',encoding='utf-8');changed.append(cp);repair=True;state=set_top(state,'active_sprint_status',f'BOARD_AUTONOMOUS_{round_id}_{kind.upper()}_REPAIR_REQUIRED')
 else:state=set_top(state,'active_sprint_status',f'BOARD_AUTONOMOUS_{round_id}_{kind.upper()}_PASS')
 (auth/STATE).write_text(state,encoding='utf-8');changed.append(STATE);commit_authority(auth,changed,f'mros(S003): autonomously consume {round_id} {kind} aggregate {decision} [skip ci]');return decision,(cp if repair else None)
def run_repair(auth:Path,state_root:Path,cp:Path):
 gen=repair_generation(auth)+1
 if gen>MAX_REPAIR_GENERATIONS:raise CycleError('ARCHITECTURAL_REVIEW_REQUIRED:REPAIR_GENERATION_LIMIT_EXCEEDED')
 script=Path('/Users/madhuram/.mros-agent-bridge/bridge/scripts/mros/mros_autonomous_repair_executor.py');p=run(auth,sys.executable,str(script),'--repo',str(auth),'--state-root',str(state_root),'--repair-contract',str(auth/cp),'--generation',str(gen),timeout=5400,check=False)
 try:out=json.loads((p.stdout or '').splitlines()[-1])
 except Exception:raise CycleError(f'REPAIR_EXECUTOR_INVALID_OUTPUT:{(p.stdout or "")[-2000:]}')
 if p.returncode!=0 or out.get('status')!='REPAIR_PUBLISHED':raise CycleError(f"REPAIR_EXECUTOR_BLOCKED:{out.get('error')}")
 return out

def calibration_requests(q:Path,candidate:str):
 out=[];d=q/ROOT/'requests'
 if not d.is_dir():return out
 for p in sorted(d.glob('*CALIBRATION*.json')):
  try:r=read_json(p)
  except Exception:continue
  if r.get('candidate_sha')==candidate:out.append((p,r))
 return out
def calibration_status(q:Path,candidate:str):
 reqs=calibration_requests(q,candidate)
 if not reqs:return 'MISSING',None
 pending=False;infra=False
 for rp,r in reversed(reqs):
  rec=q/ROOT/'receipts'/rp.name;out=q/str(r.get('output_path',''))
  if not rec.is_file():pending=True;continue
  try:job=read_json(rec).get('job',{})
  except Exception:infra=True;continue
  if out.is_file():
   text=out.read_text(encoding='utf-8',errors='replace')
   if job.get('state')=='SUCCEEDED' and job.get('exit_code')==0 and 'S003_BOARD_DETERMINISTIC_CALIBRATION_PASS' in text and 'CALIBRATION_EXECUTION_RESULT=PASS' in text:return 'PASS',str(out.relative_to(q))
   if 'CALIBRATION_EXECUTION_RESULT=FAIL' in text:return 'VALIDATION_FAILED',str(out.relative_to(q))
  if job.get('state')!='SUCCEEDED' or job.get('exit_code')!=0:infra=True
 if pending:return 'PENDING',None
 return ('INFRA_FAILED',None) if infra else ('VALIDATION_FAILED',None)
def next_calibration_role(q:Path):
 nums=[];d=q/ROOT/'requests'
 if d.is_dir():
  for p in d.glob('*CALIBRATION*.json'):
   try:rid=str(read_json(p).get('role_id',''))
   except Exception:continue
   m=re.fullmatch(r'R(\d{2,3})',rid)
   if m:nums.append(int(m.group(1)))
 n=max(nums+[90])+1
 if n>999:raise CycleError('CALIBRATION_ROLE_SPACE_EXHAUSTED')
 return f'R{n:02d}' if n<100 else f'R{n:03d}'
def queue_calibration(q:Path,candidate:str,force_retry=False):
 if calibration_requests(q,candidate) and not force_retry:return 'EXISTS'
 rid=next_calibration_role(q);tag=f'S003_CALIBRATION_{rid}_{candidate[:8].upper()}';packet=ROOT/'packets'/f'{tag}.md';output=ROOT/'results'/f'{tag}.md';request=ROOT/'requests'/f'{tag}.json';(q/packet).parent.mkdir(parents=True,exist_ok=True)
 (q/packet).write_text(f'''# S003 autonomous exact-head Board calibration {rid}\n\nExact candidate: `{candidate}`\n\nNon-certifying native execution. Do not repair or review. Run `git rev-parse HEAD`, `python3 --version`, then `python3 scripts/mros/calibrate_review_audit_board_v2.py --candidate-head {candidate}`. Return Markdown containing CANDIDATE_HEAD, PYTHON_VERSION, COMMAND, COMPLETE STDOUT, EXIT_CODE, RUNTIME_AUTHORITY=NONE, BROKER_ACTIONS=NONE, CALIBRATION_EXECUTION_RESULT=PASS|FAIL. PASS requires exact HEAD, every declared case executed, zero failures, denominator conservation, all declared metrics satisfied, terminal S003_BOARD_DETERMINISTIC_CALIBRATION_PASS, exit 0.\n''',encoding='utf-8')
 req={'schema_version':1,'request_id':f'{tag}-{int(time.time())}','created_by':'mros-autonomous-cycle','created_at':datetime.date.today().isoformat(),'job_type':'reviewer','role_id':rid,'candidate_sha':candidate,'packet_path':packet.as_posix(),'output_path':output.as_posix(),'backend':'codex'};(q/request).write_text(json.dumps(req,sort_keys=True,indent=2)+'\n',encoding='utf-8');queue_commit(q,[packet,request],f'mros(S003): queue autonomous exact-head calibration {rid} {candidate[:8]} [skip ci]');return rid
def next_review_round(q:Path):return max([n for n,_,_ in manifests(q,'reviewer')]+[0])+1
def queue_review(q:Path,candidate:str,full:bool=False):
 tier='FULL' if full else 'FAST'
 for n,_,m in manifests(q,'reviewer'):
  if m.get('candidate_head')==candidate and m.get('assurance_tier')==tier:return f'R{n:03d}'
 n=next_review_round(q);round_id=f'R{n:03d}';roles=({f'R{i:02d}':(semantic,f'Full-board final authorization attack from {semantic} perspective.') for i,semantic in enumerate(FULL_REVIEW_SEMANTICS,1)} if full else FAST_REVIEW_ROLES);members=[];paths=[]
 for role_id,(semantic,obj) in roles.items():
  packet=ROOT/'packets'/f'S003_{round_id}_{role_id}.md';output=ROOT/'results'/f'S003_{round_id}_{role_id}.json';receipt=ROOT/'receipts'/f'S003_{round_id}_{role_id}.json';request=ROOT/'requests'/f'S003_{round_id}_{role_id}.json';members.append({'execution_role_id':role_id,'semantic_role':semantic,'packet_path':packet.as_posix(),'output_path':output.as_posix(),'receipt_path':receipt.as_posix()});(q/packet).parent.mkdir(parents=True,exist_ok=True)
  (q/packet).write_text(f'''# MROS S003 {tier} review {round_id} — {role_id}\n\nCandidate head: `{candidate}`\nRound: `{round_id}`\nSemantic role: `{semantic}`\nObjective: {obj}\n\nReview independently. Do not modify candidate or read peer conclusions. Return ONLY one JSON object conforming to research/review_board/REVIEW_SCHEMA.json with exact sprint=S003, round={round_id}, candidate_head={candidate}, role={semantic}, execution_role_id={role_id}, execution_job_id=MROS_JOB_ID, transport=mac_git_mailbox, packet_path={packet.as_posix()}, output_path={output.as_posix()}, runtime_authority=NONE, broker_actions=NONE, independence booleans=true. Any CRITICAL/MAJOR/UNKNOWN blocks and cannot be outvoted.\n''',encoding='utf-8')
  req={'schema_version':1,'request_id':f'S003-{round_id}-{role_id}-{candidate[:8]}','created_by':'mros-autonomous-cycle','created_at':datetime.date.today().isoformat(),'job_type':'reviewer','role_id':role_id,'candidate_sha':candidate,'packet_path':packet.as_posix(),'output_path':output.as_posix(),'backend':'codex'};(q/request).write_text(json.dumps(req,sort_keys=True,indent=2)+'\n',encoding='utf-8');paths.extend([packet,request])
 manifest=ROOT/'manifests'/f'S003_{round_id}_REVIEW_POPULATION.json';(q/manifest).parent.mkdir(parents=True,exist_ok=True);(q/manifest).write_text(json.dumps({'schema_version':'mros-agent-population-v1','job_type':'reviewer','candidate_head':candidate,'sprint':'S003','round':round_id,'frozen_before_execution':True,'expected_count':len(roles),'assurance_tier':tier,'members':members,'created_by':'mros-autonomous-cycle','runtime_authority':'NONE'},sort_keys=True,indent=2)+'\n',encoding='utf-8');paths.insert(0,manifest);queue_commit(q,paths,f'mros(S003): freeze and queue {tier} {round_id} review population {candidate[:8]} [skip ci]');return round_id
def native_ref(q:Path,candidate:str):
 s,p=calibration_status(q,candidate);return p if s=='PASS' else None
def queue_audit(q:Path,auth:Path,candidate:str,review_round:str,review_aggregate:dict,full:bool=True):
 n=int(review_round[1:]);audit_round=f'A{n:03d}';tier='FULL' if full else 'FAST'
 for _,_,m in manifests(q,'auditor'):
  if m.get('candidate_head')==candidate and m.get('review_round')==review_round and m.get('assurance_tier')==tier:return audit_round
 nref=native_ref(q,candidate)
 if not nref:raise CycleError('AUDIT_NATIVE_REFERENCE_MISSING')
 criteria=[c.get('id') for c in read_json(auth/ACCEPTANCE).get('criteria',[]) if isinstance(c,dict) and isinstance(c.get('id'),str)];semantics=FULL_AUDIT_SEMANTICS if full else ['acceptance_criteria'];members=[];paths=[]
 for i,semantic in enumerate(semantics,1):
  role_id=f'A{i:02d}';packet=ROOT/'packets'/f'S003_{audit_round}_{role_id}.md';output=ROOT/'results'/f'S003_{audit_round}_{role_id}.json';receipt=ROOT/'receipts'/f'S003_{audit_round}_{role_id}.json';request=ROOT/'requests'/f'S003_{audit_round}_{role_id}.json';members.append({'execution_role_id':role_id,'semantic_role':semantic,'packet_path':packet.as_posix(),'output_path':output.as_posix(),'receipt_path':receipt.as_posix()});(q/packet).parent.mkdir(parents=True,exist_ok=True)
  (q/packet).write_text(f'''# MROS S003 {tier} audit {audit_round} — {role_id}\n\nExact candidate: `{candidate}`\nReviewed round: `{review_round}`\nSemantic role: `{semantic}`\nRequired acceptance IDs: {json.dumps(criteria)}\nAudited native validation reference: `{nref}`\nFrozen review aggregate:\n```json\n{json.dumps(review_aggregate,sort_keys=True,indent=2)}\n```\nAudit independently against research/review_board/AUDIT_SCHEMA.json and S003 acceptance contract. Return ONLY one JSON object with exact sprint=S003, round={audit_round}, audited_review_round={review_round}, candidate_head={candidate}, role={semantic}, execution_role_id={role_id}, execution_job_id=MROS_JOB_ID, transport=mac_git_mailbox, packet_path={packet.as_posix()}, output_path={output.as_posix()}, runtime_authority=NONE, broker_actions=NONE, independence booleans=true, audited_native_validation={nref}, audited_acceptance_criteria covering every required ID exactly, and nonempty audit_scope. Any CRITICAL/MAJOR/UNKNOWN blocks and cannot be outvoted.\n''',encoding='utf-8')
  req={'schema_version':1,'request_id':f'S003-{audit_round}-{role_id}-{candidate[:8]}','created_by':'mros-autonomous-cycle','created_at':datetime.date.today().isoformat(),'job_type':'auditor','role_id':role_id,'candidate_sha':candidate,'packet_path':packet.as_posix(),'output_path':output.as_posix(),'backend':'codex'};(q/request).write_text(json.dumps(req,sort_keys=True,indent=2)+'\n',encoding='utf-8');paths.extend([packet,request])
 manifest=ROOT/'manifests'/f'S003_{audit_round}_AUDIT_POPULATION.json';(q/manifest).parent.mkdir(parents=True,exist_ok=True);(q/manifest).write_text(json.dumps({'schema_version':'mros-agent-population-v1','job_type':'auditor','candidate_head':candidate,'sprint':'S003','round':audit_round,'review_round':review_round,'frozen_before_execution':True,'expected_count':len(semantics),'assurance_tier':tier,'members':members,'created_by':'mros-autonomous-cycle','runtime_authority':'NONE'},sort_keys=True,indent=2)+'\n',encoding='utf-8');paths.insert(0,manifest);queue_commit(q,paths,f'mros(S003): freeze and queue {tier} {audit_round} audit population {candidate[:8]} [skip ci]');return audit_round

def process_review(auth:Path,q:Path,state_root:Path,row):
 n,mp,m=row;round_id=f'R{n:03d}';candidate=m.get('candidate_head');tier=str(m.get('assurance_tier') or 'FAST')
 if not isinstance(candidate,str):raise CycleError('LATEST_REVIEW_CANDIDATE_INVALID')
 complete,payloads,receipts=exact_population(q,m)
 if not complete:return {'action':'WAIT_REVIEW','round':round_id,'candidate':candidate,'tier':tier}
 aggregate=load_mod(auth,'aggregate_reviews').aggregate_payloads(payloads,candidate_head=candidate,receipts=receipts,manifest=m);aggregate.update({'review_round':round_id,'population_manifest':str(mp.relative_to(q)),'assurance_tier':tier,'runtime_authority':'NONE'});decision,cp=record_aggregate(auth,aggregate,'review',round_id,candidate);sync(auth,q)
 if decision not in PASS:
  prior=repair_evidence_for_failed(auth,candidate)
  if prior:
   new=git(auth,'rev-parse',f'origin/{AUTH}').stdout.strip();cs,_=calibration_status(q,new)
   if cs=='MISSING':queue_calibration(q,new)
   return {'action':'REPAIR_ALREADY_PUBLISHED','round':round_id,'new_candidate':new,'calibration':cs}
  if cp is None:raise CycleError('REPAIR_CONTRACT_MISSING')
  repair=run_repair(auth,state_root,cp);sync(auth,q);queue_calibration(q,repair['candidate_head']);return {'action':'REPAIR_AND_CALIBRATE','round':round_id,'decision':decision,'new_candidate':repair['candidate_head'],'generation':repair['generation']}
 if tier!='FULL':
  fr=queue_review(q,candidate,full=True);return {'action':'FINAL_FULL_REVIEW_QUEUED','from_round':round_id,'round':fr,'candidate':candidate}
 queue_audit(q,auth,candidate,round_id,aggregate,full=True);return {'action':'FINAL_FULL_AUDIT_QUEUED','round':round_id,'candidate':candidate,'decision':decision}
def matching_audit(q:Path,candidate:str,review_round:str):
 rows=[r for r in manifests(q,'auditor') if r[2].get('candidate_head')==candidate and r[2].get('review_round')==review_round];return rows[-1] if rows else None
def process_audit(auth:Path,q:Path,state_root:Path,row):
 n,mp,m=row;audit_round=f'A{n:03d}';review_round=str(m.get('review_round') or '');candidate=m.get('candidate_head');tier=str(m.get('assurance_tier') or 'FAST')
 if not re.fullmatch(r'R\d{3}',review_round):raise CycleError('AUDIT_REVIEW_ROUND_BINDING_MISSING')
 if not isinstance(candidate,str):raise CycleError('LATEST_AUDIT_CANDIDATE_INVALID')
 complete,payloads,receipts=exact_population(q,m)
 if not complete:return {'action':'WAIT_AUDIT','round':audit_round,'candidate':candidate,'tier':tier}
 rap=aggregate_path('review',review_round)
 if not (auth/rap).is_file():raise CycleError('AUDIT_REVIEW_AGGREGATE_MISSING')
 review=read_json(auth/rap);contract=read_json(auth/ACCEPTANCE);required=[c.get('id') for c in contract.get('criteria',[]) if isinstance(c,dict) and isinstance(c.get('id'),str)];review_jobs=[r.get('execution_job_id') for r in review.get('reviews',[]) if isinstance(r,dict)];nref=native_ref(q,candidate);aggregate=load_mod(auth,'aggregate_audits').aggregate_payloads(payloads,candidate_head=candidate,review_round=review_round,receipts=receipts,manifest=m,review_job_ids=review_jobs,required_acceptance_ids=required,expected_native_ref=nref);aggregate.update({'audit_round':audit_round,'population_manifest':str(mp.relative_to(q)),'review_aggregate':rap.as_posix(),'assurance_tier':tier,'runtime_authority':'NONE'});decision,cp=record_aggregate(auth,aggregate,'audit',audit_round,candidate);sync(auth,q)
 if decision not in PASS:
  prior=repair_evidence_for_failed(auth,candidate)
  if prior:
   new=git(auth,'rev-parse',f'origin/{AUTH}').stdout.strip();cs,_=calibration_status(q,new)
   if cs=='MISSING':queue_calibration(q,new)
   return {'action':'AUDIT_REPAIR_ALREADY_PUBLISHED','round':audit_round,'new_candidate':new,'calibration':cs}
  if cp is None:raise CycleError('AUDIT_REPAIR_CONTRACT_MISSING')
  repair=run_repair(auth,state_root,cp);sync(auth,q);queue_calibration(q,repair['candidate_head']);return {'action':'AUDIT_REPAIR_AND_CALIBRATE','round':audit_round,'new_candidate':repair['candidate_head'],'generation':repair['generation']}
 if tier!='FULL' or int(m.get('expected_count') or 0)<10:raise CycleError('FINAL_AUTHORIZATION_REQUIRES_FULL_AUDIT_POPULATION')
 state=(auth/STATE).read_text(encoding='utf-8')
 if 'active_sprint_status: BOARD_BOOTSTRAP_AUTHORIZATION_PENDING' in state:return {'action':'AUTHORIZATION_READY','round':audit_round,'candidate':candidate,'decision':decision}
 state=set_top(state,'active_sprint_status','BOARD_BOOTSTRAP_AUTHORIZATION_PENDING');state=set_indented(state,'bootstrap_independent_audit_status',decision);(auth/STATE).write_text(state,encoding='utf-8');sha=commit_authority(auth,[STATE],f'mros(S003): autonomous full-board audit ready for authorization {candidate[:8]} [skip ci]');return {'action':'AUTHORIZATION_READY','round':audit_round,'candidate':candidate,'decision':decision,'commit':sha}
def current_head(auth:Path):return git(auth,'rev-parse',f'origin/{AUTH}').stdout.strip()
def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--authority-repo',required=True,type=Path);ap.add_argument('--queue-repo',required=True,type=Path);ap.add_argument('--state-root',required=True,type=Path);a=ap.parse_args();auth=a.authority_repo.resolve();q=a.queue_repo.resolve();root=a.state_root.resolve()
 try:
  sync(auth,q);state=(auth/STATE).read_text(encoding='utf-8')
  if not re.search(r'(?m)^active_sprint:\s*S003\s*$',state):print(json.dumps({'status':'NOOP_NOT_S003'}));return 3
  if re.search(r'(?m)^active_milestone:\s*M9\s*$',state):raise CycleError('M9_START_FORBIDDEN')
  reviews=manifests(q,'reviewer');latest=reviews[-1] if reviews else None
  if latest and repair_evidence_for_failed(auth,str(latest[2].get('candidate_head',''))):
   cur=current_head(auth)
   if not any(m.get('candidate_head')==cur for _,_,m in reviews):
    cs,nref=calibration_status(q,cur)
    if cs=='MISSING':rid=queue_calibration(q,cur);print(json.dumps({'action':'CALIBRATION_QUEUED','candidate':cur,'role':rid},sort_keys=True));return 0
    if cs=='PENDING':print(json.dumps({'action':'WAIT_CALIBRATION','candidate':cur},sort_keys=True));return 3
    if cs=='INFRA_FAILED':rid=queue_calibration(q,cur,force_retry=True);print(json.dumps({'action':'CALIBRATION_RETRY_QUEUED','candidate':cur,'role':rid},sort_keys=True));return 0
    if cs=='VALIDATION_FAILED':raise CycleError('CALIBRATION_VALIDATION_FAILED')
    rr=queue_review(q,cur,full=False);print(json.dumps({'action':'FAST_REVIEW_QUEUED','candidate':cur,'round':rr,'native_ref':nref},sort_keys=True));return 0
  if latest:
   n,_,m=latest;round_id=f'R{n:03d}';candidate=str(m.get('candidate_head',''));rap=aggregate_path('review',round_id)
   if (auth/rap).is_file() and read_json(auth/rap).get('decision') in PASS:
    if str(m.get('assurance_tier') or 'FAST')!='FULL':
     fr=queue_review(q,candidate,full=True);print(json.dumps({'action':'FINAL_FULL_REVIEW_QUEUED','candidate':candidate,'round':fr},sort_keys=True));return 0
    audit=matching_audit(q,candidate,round_id)
    if audit:
     result=process_audit(auth,q,root,audit);print(json.dumps(result,sort_keys=True));return 3 if result['action'] in {'WAIT_AUDIT','AUTHORIZATION_READY'} else 0
    queue_audit(q,auth,candidate,round_id,read_json(auth/rap),full=True);print(json.dumps({'action':'FINAL_FULL_AUDIT_QUEUED','candidate':candidate,'review_round':round_id},sort_keys=True));return 0
   result=process_review(auth,q,root,latest);print(json.dumps(result,sort_keys=True));return 3 if result['action']=='WAIT_REVIEW' else 0
  cur=current_head(auth);cs,nref=calibration_status(q,cur)
  if cs=='MISSING':rid=queue_calibration(q,cur);print(json.dumps({'action':'CALIBRATION_QUEUED','candidate':cur,'role':rid},sort_keys=True));return 0
  if cs=='PENDING':print(json.dumps({'action':'WAIT_CALIBRATION','candidate':cur},sort_keys=True));return 3
  if cs=='INFRA_FAILED':rid=queue_calibration(q,cur,force_retry=True);print(json.dumps({'action':'CALIBRATION_RETRY_QUEUED','candidate':cur,'role':rid},sort_keys=True));return 0
  if cs=='VALIDATION_FAILED':raise CycleError('CALIBRATION_VALIDATION_FAILED')
  rr=queue_review(q,cur,full=False);print(json.dumps({'action':'FAST_REVIEW_QUEUED','candidate':cur,'round':rr,'native_ref':nref},sort_keys=True));return 0
 except Exception as exc:
  print(json.dumps({'status':'AUTONOMOUS_CYCLE_BLOCKED','error':f'{type(exc).__name__}:{exc}','runtime_authority':'NONE'},sort_keys=True));return 2
if __name__=='__main__':raise SystemExit(main())
