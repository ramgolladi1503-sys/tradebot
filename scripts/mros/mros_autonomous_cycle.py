#!/usr/bin/env python3
"""Repository-driven autonomous MROS S003 Board-bootstrap cycle.

The cycle deliberately contains no fixed R002/R003/A001 names. It discovers the
latest frozen populations and exact candidate from repository evidence, waits for
a frozen population to finish, aggregates it, repairs blocking findings as one
repair generation, calibrates the new exact head, launches a fresh small review,
then a single audit. Human attention is reserved for bounded/unsafe failures.
"""
from __future__ import annotations
import argparse,datetime,hashlib,importlib,json,re,subprocess,sys,time
from pathlib import Path
from typing import Any

AUTH='research/mros-program-v1';QUEUE='automation/mros-agent-queue-v1';SPRINT='S003'
ROOT=Path('research/evidence/sprints/S003/agent_queue');STATE=Path('research/program/MROS_PROGRAM_STATE.yaml')
ACCEPTANCE=Path('research/evidence/sprints/S003/S003_ACCEPTANCE_CONTRACT.json')
PASS={'PASS','PASS_WITH_MINOR_FINDINGS'};MAX_REPAIR_GENERATIONS=5
REVIEW_ROLES={'R01':('contract_compliance','Attack exact contract/schema/invariant/evidence/provenance bindings.'),'R02':('negative_control','Attack malformed inputs, denominator/quorum laundering, stale refs, and fail-open transitions.'),'R03':('adversarial_red_team','Search independently for any remaining material authority bypass or fabricated-evidence path.')}
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
def load_authority_module(auth:Path,name:str):
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
 pat=rf'(?m)^({re.escape(key)}:\s*).*$'
 return re.sub(pat,rf'\g<1>{value}',text,count=1) if re.search(pat,text) else text
def set_indented(text,key,value):
 pat=rf'(?m)^(\s+{re.escape(key)}:\s*).*$'
 return re.sub(pat,rf'\g<1>{value}',text,count=1) if re.search(pat,text) else text

def manifests(q:Path,job_type:str)->list[tuple[int,Path,dict]]:
 d=q/ROOT/'manifests';out=[]
 if not d.is_dir():return out
 pat=re.compile(r'S003_([RA])(\d{3})_(REVIEW|AUDIT)_POPULATION\.json$')
 for p in d.glob('S003_*_POPULATION.json'):
  m=pat.fullmatch(p.name)
  if not m:continue
  want='reviewer' if m.group(1)=='R' else 'auditor'
  if want!=job_type:continue
  try:data=read_json(p)
  except Exception:continue
  if data.get('job_type')==job_type:out.append((int(m.group(2)),p,data))
 return sorted(out,key=lambda x:x[0])
def exact_population(q:Path,manifest:dict)->tuple[bool,list[tuple[str,dict]],dict[str,dict]]]:
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
def blocking_findings(aggregate:dict,kind:str)->list[dict]:
 out=[];plural='reviews' if kind=='review' else 'audits'
 for item in aggregate.get(plural,[]):
  if isinstance(item,dict):out.extend(f for f in item.get('findings',[]) if isinstance(f,dict) and f.get('severity') in {'CRITICAL','MAJOR','UNKNOWN'})
 for bad in aggregate.get('invalid',[]):
  if isinstance(bad,dict):
   item=bad.get('review') if kind=='review' else bad.get('audit')
   if isinstance(item,dict):out.extend(f for f in item.get('findings',[]) if isinstance(f,dict) and f.get('severity') in {'CRITICAL','MAJOR','UNKNOWN'})
 # Deduplicate without hiding independent evidence.
 seen=set();ded=[]
 for f in out:
  key=(f.get('requirement'),f.get('evidence'),f.get('severity'))
  if key not in seen:seen.add(key);ded.append(f)
 return ded
def repair_generation(auth:Path)->int:
 d=auth/'research/evidence/sprints/S003'
 nums=[]
 if d.is_dir():
  for p in d.glob('AUTONOMOUS_REPAIR_G*_*.json'):
   m=re.search(r'_G(\d+)_',p.name)
   if m:nums.append(int(m.group(1)))
 return max(nums,default=0)
def aggregate_path(kind:str,round_id:str)->Path:return Path(f'research/evidence/sprints/S003/S003_{round_id}_{kind.upper()}_AGGREGATE.json')
def contract_path(kind:str,round_id:str)->Path:return Path(f'research/evidence/sprints/S003/S003_{round_id}_{kind.upper()}_REPAIR_CONTRACT.json')

def record_aggregate(auth:Path,aggregate:dict,kind:str,round_id:str,candidate:str)->tuple[str,Path|None]:
 ap=aggregate_path(kind,round_id)
 if (auth/ap).is_file():return str(aggregate.get('decision')), (contract_path(kind,round_id) if (auth/contract_path(kind,round_id)).is_file() else None)
 (auth/ap).parent.mkdir(parents=True,exist_ok=True);(auth/ap).write_text(json.dumps(aggregate,sort_keys=True,indent=2)+'\n',encoding='utf-8');changed=[ap];decision=str(aggregate.get('decision'))
 cp=None;state=(auth/STATE).read_text(encoding='utf-8')
 if decision not in PASS:
  cp=contract_path(kind,round_id);findings=blocking_findings(aggregate,kind)
  contract={'schema_version':'mros-repair-contract-v2','sprint':'S003','failed_head':candidate,'source_kind':kind,'source_round':round_id,'aggregate_decision':decision,'blocking_findings':findings,'invalid_artifacts':aggregate.get('invalid',[]),'root_cause_instruction':'Cluster related findings and repair common causes once; do not weaken gates.','repair_scope':{'allowed':['scripts/mros/','tests/mros/','research/review_board/','research/audit_board/'],'forbidden':['research/program/','runtime/strategy/risk/execution/broker code','weaken fixtures or acceptance criteria','begin M9','create runtime authority']},'runtime_authority':'NONE','m9_status':'NOT_STARTED'}
  (auth/cp).write_text(json.dumps(contract,sort_keys=True,indent=2)+'\n',encoding='utf-8');changed.append(cp);state=set_top(state,'active_sprint_status',f'BOARD_AUTONOMOUS_{round_id}_{kind.upper()}_REPAIR_REQUIRED')
 else:state=set_top(state,'active_sprint_status',f'BOARD_AUTONOMOUS_{round_id}_{kind.upper()}_PASS')
 (auth/STATE).write_text(state,encoding='utf-8');changed.append(STATE)
 sha=commit_authority(auth,changed,f'mros(S003): autonomously consume {round_id} {kind} aggregate {decision} [skip ci]');return decision,cp

def run_repair(auth:Path,state_root:Path,cp:Path)->dict:
 gen=repair_generation(auth)+1
 if gen>MAX_REPAIR_GENERATIONS:raise CycleError('ARCHITECTURAL_REVIEW_REQUIRED:REPAIR_GENERATION_LIMIT_EXCEEDED')
 script=Path('/Users/madhuram/.mros-agent-bridge/bridge/scripts/mros/mros_autonomous_repair_executor.py')
 p=run(auth,sys.executable,str(script),'--repo',str(auth),'--state-root',str(state_root),'--repair-contract',str(auth/cp),'--generation',str(gen),timeout=5400,check=False)
 try:out=json.loads((p.stdout or '').splitlines()[-1])
 except Exception:raise CycleError(f'REPAIR_EXECUTOR_INVALID_OUTPUT:{(p.stdout or "")[-2000:]}')
 if p.returncode!=0 or out.get('status')!='REPAIR_PUBLISHED':raise CycleError(f"REPAIR_EXECUTOR_BLOCKED:{out.get('error')}")
 return out

def next_calibration_role(q:Path)->str:
 nums=[]
 d=q/ROOT/'requests'
 if d.is_dir():
  for p in d.glob('*CALIBRATION*.json'):
   try:r=read_json(p);rid=str(r.get('role_id',''))
   except Exception:continue
   m=re.fullmatch(r'R(\d{2,3})',rid)
   if m:nums.append(int(m.group(1)))
 n=max(nums+[90])+1
 if n>999:raise CycleError('CALIBRATION_ROLE_SPACE_EXHAUSTED')
 return f'R{n:02d}' if n<100 else f'R{n:03d}'
def calibration_requests(q:Path,candidate:str)->list[tuple[Path,dict]]:
 out=[];d=q/ROOT/'requests'
 if not d.is_dir():return out
 for p in sorted(d.glob('*CALIBRATION*.json')):
  try:r=read_json(p)
  except Exception:continue
  if r.get('candidate_sha')==candidate:out.append((p,r))
 return out
def calibration_status(q:Path,candidate:str)->tuple[str,str|None]:
 reqs=calibration_requests(q,candidate)
 if not reqs:return 'MISSING',None
 for rp,r in reversed(reqs):
  rec=q/ROOT/'receipts'/rp.name;out=q/str(r.get('output_path',''))
  if not rec.is_file():return 'PENDING',None
  try:rr=read_json(rec);job=rr.get('job',{})
  except Exception:continue
  if job.get('state')=='SUCCEEDED' and job.get('exit_code')==0 and out.is_file():
   text=out.read_text(encoding='utf-8',errors='replace')
   if 'S003_BOARD_DETERMINISTIC_CALIBRATION_PASS' in text and 'CALIBRATION_EXECUTION_RESULT=PASS' in text:return 'PASS',str(out.relative_to(q))
 return 'FAILED',None
def queue_calibration(q:Path,candidate:str)->str:
 if calibration_requests(q,candidate):return 'EXISTS'
 rid=next_calibration_role(q);tag=f'S003_CALIBRATION_{rid}_{candidate[:8].upper()}';packet=ROOT/'packets'/f'{tag}.md';output=ROOT/'results'/f'{tag}.md';request=ROOT/'requests'/f'{tag}.json'
 (q/packet).parent.mkdir(parents=True,exist_ok=True)
 (q/packet).write_text(f'''# S003 autonomous exact-head Board calibration {rid}\n\nExact candidate: `{candidate}`\n\nThis is non-certifying native execution. Do not repair or review. Run:\n1. `git rev-parse HEAD`\n2. `python3 --version`\n3. `python3 scripts/mros/calibrate_review_audit_board_v2.py --candidate-head {candidate}`\nCapture complete stdout and exact exit code. Return Markdown containing CANDIDATE_HEAD, PYTHON_VERSION, COMMAND, COMPLETE STDOUT, EXIT_CODE, RUNTIME_AUTHORITY=NONE, BROKER_ACTIONS=NONE, CALIBRATION_EXECUTION_RESULT=PASS|FAIL. PASS requires exact HEAD, every declared case executed, zero failures, denominator conservation, all declared metrics satisfied, terminal S003_BOARD_DETERMINISTIC_CALIBRATION_PASS, exit 0.\n''',encoding='utf-8')
 req={'schema_version':1,'request_id':f'{tag}-{int(time.time())}','created_by':'mros-autonomous-cycle','created_at':datetime.date.today().isoformat(),'job_type':'reviewer','role_id':rid,'candidate_sha':candidate,'packet_path':packet.as_posix(),'output_path':output.as_posix(),'backend':'codex'};(q/request).write_text(json.dumps(req,sort_keys=True,indent=2)+'\n',encoding='utf-8')
 queue_commit(q,[packet,request],f'mros(S003): queue autonomous exact-head calibration {rid} {candidate[:8]} [skip ci]');return rid
def next_review_round(q:Path)->int:return max([n for n,_,_ in manifests(q,'reviewer')]+[0])+1
def queue_review(q:Path,candidate:str)->str:
 # Never launch a second population for the same exact candidate.
 for n,p,m in manifests(q,'reviewer'):
  if m.get('candidate_head')==candidate:return f'R{n:03d}'
 n=next_review_round(q);rid_round=f'R{n:03d}';members=[];paths=[]
 for role_id,(semantic,obj) in REVIEW_ROLES.items():
  packet=ROOT/'packets'/f'S003_{rid_round}_{role_id}.md';output=ROOT/'results'/f'S003_{rid_round}_{role_id}.json';receipt=ROOT/'receipts'/f'S003_{rid_round}_{role_id}.json';request=ROOT/'requests'/f'S003_{rid_round}_{role_id}.json'
  members.append({'execution_role_id':role_id,'semantic_role':semantic,'packet_path':packet.as_posix(),'output_path':output.as_posix(),'receipt_path':receipt.as_posix()})
  (q/packet).parent.mkdir(parents=True,exist_ok=True);(q/packet).write_text(f'''# MROS S003 autonomous review {rid_round} — {role_id}\n\nCandidate head: `{candidate}`\nRound: `{rid_round}`\nSemantic role: `{semantic}`\nObjective: {obj}\n\nReview the exact candidate independently. Do not modify it and do not read peer conclusions. Return ONLY one JSON object conforming to research/review_board/REVIEW_SCHEMA.json. Required exact bindings: sprint=S003, round={rid_round}, candidate_head={candidate}, role={semantic}, execution_role_id={role_id}, execution_job_id=MROS_JOB_ID, transport=mac_git_mailbox, packet_path={packet.as_posix()}, output_path={output.as_posix()}, runtime_authority=NONE, broker_actions=NONE, independence booleans=true. Any CRITICAL/MAJOR/UNKNOWN blocks.\n''',encoding='utf-8')
  req={'schema_version':1,'request_id':f'S003-{rid_round}-{role_id}-{candidate[:8]}','created_by':'mros-autonomous-cycle','created_at':datetime.date.today().isoformat(),'job_type':'reviewer','role_id':role_id,'candidate_sha':candidate,'packet_path':packet.as_posix(),'output_path':output.as_posix(),'backend':'codex'};(q/request).write_text(json.dumps(req,sort_keys=True,indent=2)+'\n',encoding='utf-8');paths.extend([packet,request])
 manifest=ROOT/'manifests'/f'S003_{rid_round}_REVIEW_POPULATION.json';(q/manifest).parent.mkdir(parents=True,exist_ok=True);(q/manifest).write_text(json.dumps({'schema_version':'mros-agent-population-v1','job_type':'reviewer','candidate_head':candidate,'sprint':'S003','round':rid_round,'frozen_before_execution':True,'expected_count':3,'assurance_tier':'FAST','members':members,'created_by':'mros-autonomous-cycle','runtime_authority':'NONE'},sort_keys=True,indent=2)+'\n',encoding='utf-8');paths.insert(0,manifest)
 queue_commit(q,paths,f'mros(S003): freeze and queue autonomous {rid_round} review population {candidate[:8]} [skip ci]');return rid_round

def native_ref_for_candidate(q:Path,candidate:str)->str|None:
 status,path=calibration_status(q,candidate);return path if status=='PASS' else None
def queue_audit(q:Path,auth:Path,candidate:str,review_round:str,review_aggregate:dict)->str:
 n=int(review_round[1:]);audit_round=f'A{n:03d}'
 for x,p,m in manifests(q,'auditor'):
  if m.get('candidate_head')==candidate and m.get('round')==audit_round:return audit_round
 native_ref=native_ref_for_candidate(q,candidate)
 if not native_ref:raise CycleError('AUDIT_NATIVE_REFERENCE_MISSING')
 contract=read_json(auth/ACCEPTANCE);criteria=[c.get('id') for c in contract.get('criteria',[]) if isinstance(c,dict) and isinstance(c.get('id'),str)]
 role_id='A01';semantic='acceptance_integrity';packet=ROOT/'packets'/f'S003_{audit_round}_{role_id}.md';output=ROOT/'results'/f'S003_{audit_round}_{role_id}.json';receipt=ROOT/'receipts'/f'S003_{audit_round}_{role_id}.json';request=ROOT/'requests'/f'S003_{audit_round}_{role_id}.json';manifest=ROOT/'manifests'/f'S003_{audit_round}_AUDIT_POPULATION.json'
 (q/packet).parent.mkdir(parents=True,exist_ok=True);(q/packet).write_text(f'''# MROS S003 autonomous audit {audit_round} — {role_id}\n\nExact candidate: `{candidate}`\nReviewed round: `{review_round}`\nRequired acceptance IDs: {json.dumps(criteria)}\nAudited native validation reference: `{native_ref}`\nReview aggregate (frozen input):\n```json\n{json.dumps(review_aggregate,sort_keys=True,indent=2)}\n```\n\nAudit independently against research/audit_board/AUDIT_SCHEMA.json and the S003 acceptance contract. Return ONLY one JSON object with sprint=S003, round={audit_round}, review_round={review_round}, candidate_head={candidate}, role={semantic}, execution_role_id={role_id}, execution_job_id=MROS_JOB_ID, transport=mac_git_mailbox, packet_path={packet.as_posix()}, output_path={output.as_posix()}, runtime_authority=NONE, broker_actions=NONE, independence booleans=true, audited_native_validation={native_ref}, and audited_acceptance_criteria covering every required ID exactly. Any CRITICAL/MAJOR/UNKNOWN blocks.\n''',encoding='utf-8')
 req={'schema_version':1,'request_id':f'S003-{audit_round}-{role_id}-{candidate[:8]}','created_by':'mros-autonomous-cycle','created_at':datetime.date.today().isoformat(),'job_type':'auditor','role_id':role_id,'candidate_sha':candidate,'packet_path':packet.as_posix(),'output_path':output.as_posix(),'backend':'codex'};(q/request).write_text(json.dumps(req,sort_keys=True,indent=2)+'\n',encoding='utf-8')
 (q/manifest).parent.mkdir(parents=True,exist_ok=True);(q/manifest).write_text(json.dumps({'schema_version':'mros-agent-population-v1','job_type':'auditor','candidate_head':candidate,'sprint':'S003','round':audit_round,'frozen_before_execution':True,'expected_count':1,'assurance_tier':'FAST','members':[{'execution_role_id':role_id,'semantic_role':semantic,'packet_path':packet.as_posix(),'output_path':output.as_posix(),'receipt_path':receipt.as_posix()}],'created_by':'mros-autonomous-cycle','runtime_authority':'NONE'},sort_keys=True,indent=2)+'\n',encoding='utf-8')
 queue_commit(q,[manifest,packet,request],f'mros(S003): freeze and queue autonomous {audit_round} audit {candidate[:8]} [skip ci]');return audit_round

def handle_review(auth:Path,q:Path,state_root:Path)->dict|None:
 rows=manifests(q,'reviewer')
 if not rows:return None
 n,mp,m=rows[-1];round_id=f'R{n:03d}';candidate=m.get('candidate_head')
 if not isinstance(candidate,str):raise CycleError('LATEST_REVIEW_CANDIDATE_INVALID')
 complete,payloads,receipts=exact_population(q,m)
 if not complete:return {'action':'WAIT_REVIEW','round':round_id,'candidate':candidate}
 mod=load_authority_module(auth,'aggregate_reviews');aggregate=mod.aggregate_payloads(payloads,candidate_head=candidate,receipts=receipts,manifest=m);aggregate.update({'review_round':round_id,'population_manifest':str(mp.relative_to(q)),'runtime_authority':'NONE'})
 decision,cp=record_aggregate(auth,aggregate,'review',round_id,candidate);sync(auth,q)
 if decision not in PASS:
  if cp is None:raise CycleError('REPAIR_CONTRACT_MISSING')
  repair=run_repair(auth,state_root,cp);sync(auth,q);new=repair['candidate_head'];queue_calibration(q,new);return {'action':'REPAIR_AND_CALIBRATE','round':round_id,'decision':decision,'new_candidate':new,'generation':repair['generation']}
 # Clean review: launch audit if none exists for this candidate/round.
 queue_audit(q,auth,candidate,round_id,aggregate);return {'action':'AUDIT_QUEUED','round':round_id,'candidate':candidate,'decision':decision}
def handle_audit(auth:Path,q:Path,state_root:Path)->dict|None:
 rows=manifests(q,'auditor')
 if not rows:return None
 n,mp,m=rows[-1];audit_round=f'A{n:03d}';review_round=f'R{n:03d}';candidate=m.get('candidate_head')
 if not isinstance(candidate,str):raise CycleError('LATEST_AUDIT_CANDIDATE_INVALID')
 complete,payloads,receipts=exact_population(q,m)
 if not complete:return {'action':'WAIT_AUDIT','round':audit_round,'candidate':candidate}
 rap=aggregate_path('review',review_round)
 if not (auth/rap).is_file():raise CycleError('AUDIT_REVIEW_AGGREGATE_MISSING')
 review=read_json(auth/rap);contract=read_json(auth/ACCEPTANCE);required=[c.get('id') for c in contract.get('criteria',[]) if isinstance(c,dict) and isinstance(c.get('id'),str)];review_jobs=[r.get('execution_job_id') for r in review.get('reviews',[]) if isinstance(r,dict)];native_ref=native_ref_for_candidate(q,candidate)
 mod=load_authority_module(auth,'aggregate_audits');aggregate=mod.aggregate_payloads(payloads,candidate_head=candidate,review_round=review_round,receipts=receipts,manifest=m,review_job_ids=review_jobs,required_acceptance_ids=required,expected_native_ref=native_ref);aggregate.update({'audit_round':audit_round,'population_manifest':str(mp.relative_to(q)),'review_aggregate':rap.as_posix(),'runtime_authority':'NONE'})
 decision,cp=record_aggregate(auth,aggregate,'audit',audit_round,candidate);sync(auth,q)
 if decision not in PASS:
  if cp is None:raise CycleError('AUDIT_REPAIR_CONTRACT_MISSING')
  repair=run_repair(auth,state_root,cp);sync(auth,q);new=repair['candidate_head'];queue_calibration(q,new);return {'action':'AUDIT_REPAIR_AND_CALIBRATE','round':audit_round,'decision':decision,'new_candidate':new,'generation':repair['generation']}
 # Authorization is a separate deterministic repository step; mark ready without asking a human.
 state=(auth/STATE).read_text(encoding='utf-8');state=set_top(state,'active_sprint_status','BOARD_BOOTSTRAP_AUTHORIZATION_PENDING');state=set_indented(state,'bootstrap_independent_audit_status',decision);(auth/STATE).write_text(state,encoding='utf-8');sha=commit_authority(auth,[STATE],f'mros(S003): autonomous clean audit ready for authorization {candidate[:8]} [skip ci]')
 return {'action':'AUTHORIZATION_READY','round':audit_round,'candidate':candidate,'decision':decision,'commit':sha}
def current_candidate(auth:Path)->str:return git(auth,'rev-parse',f'origin/{AUTH}').stdout.strip()
def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--authority-repo',required=True,type=Path);ap.add_argument('--queue-repo',required=True,type=Path);ap.add_argument('--state-root',required=True,type=Path);a=ap.parse_args();auth=a.authority_repo.resolve();q=a.queue_repo.resolve();state_root=a.state_root.resolve()
 try:
  sync(auth,q);state=(auth/STATE).read_text(encoding='utf-8')
  if not re.search(r'(?m)^active_sprint:\s*S003\s*$',state):print(json.dumps({'status':'NOOP_NOT_S003'}));return 3
  if re.search(r'(?m)^active_milestone:\s*M9\s*$',state):raise CycleError('M9_START_FORBIDDEN')
  # Audit gets priority because it is downstream of a clean review.
  audits=manifests(q,'auditor')
  if audits:
   result=handle_audit(auth,q,state_root)
   if result and result.get('action') not in {'WAIT_AUDIT'}:print(json.dumps(result,sort_keys=True));return 0
   if result and result.get('action')=='WAIT_AUDIT':print(json.dumps(result,sort_keys=True));return 3
  reviews=manifests(q,'reviewer')
  if reviews:
   n,_,m=reviews[-1];candidate=str(m.get('candidate_head',''))
   # If latest review has already been cleanly consumed, audit would have been queued above/on prior pass.
   rap=aggregate_path('review',f'R{n:03d}')
   if (auth/rap).is_file() and read_json(auth/rap).get('decision') in PASS:
    aggregate=read_json(auth/rap);queue_audit(q,auth,candidate,f'R{n:03d}',aggregate);print(json.dumps({'action':'AUDIT_QUEUED','candidate':candidate},sort_keys=True));return 0
   result=handle_review(auth,q,state_root)
   if result:print(json.dumps(result,sort_keys=True));return 0 if not result['action'].startswith('WAIT_') else 3
  # No population for the current post-repair head: require exact-head calibration, then fresh review.
  candidate=current_candidate(auth);cs,nref=calibration_status(q,candidate)
  if cs=='MISSING':rid=queue_calibration(q,candidate);print(json.dumps({'action':'CALIBRATION_QUEUED','candidate':candidate,'role':rid},sort_keys=True));return 0
  if cs=='PENDING':print(json.dumps({'action':'WAIT_CALIBRATION','candidate':candidate},sort_keys=True));return 3
  if cs=='FAILED':raise CycleError('CALIBRATION_FAILED_REPAIR_REQUIRED')
  rr=queue_review(q,candidate);print(json.dumps({'action':'REVIEW_QUEUED','candidate':candidate,'round':rr,'native_ref':nref},sort_keys=True));return 0
 except Exception as exc:
  print(json.dumps({'status':'AUTONOMOUS_CYCLE_BLOCKED','error':f'{type(exc).__name__}:{exc}','runtime_authority':'NONE'},sort_keys=True));return 2
if __name__=='__main__':raise SystemExit(main())
