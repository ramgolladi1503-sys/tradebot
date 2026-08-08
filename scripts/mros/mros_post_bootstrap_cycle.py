#!/usr/bin/env python3
"""Autonomous MROS program cycle from S004 through M8/S110.

The controller owns routine progression: contract freeze -> implementation -> exact-head
native validation -> independent review -> independent audit -> repair as needed ->
accept -> next sprint. M9/S111+ is a hard stop and runtime authority remains NONE.
"""
from __future__ import annotations
import argparse,datetime,importlib,json,re,subprocess,sys,time
from pathlib import Path
from typing import Any
from mros_program_catalog import sprint_spec,next_sprint,common_acceptance,MILESTONE_LAST_SPRINT
AUTH='research/mros-program-v1';QUEUE='automation/mros-agent-queue-v1';MAIL=Path('research/evidence/sprints/S003/agent_queue');STATE=Path('research/program/MROS_PROGRAM_STATE.yaml');LEDGER=Path('research/program/SPRINT_LEDGER.jsonl')
PASS={'PASS','PASS_WITH_MINOR_FINDINGS'};MAX_REPAIR=5
REVIEW_ROLES=['contract_compliance','negative_control','evidence_provenance','causal_time','denominator_search_integrity','runtime_boundary','qa_verification','architecture_no_drift','adversarial_red_team','reproducibility']
AUDIT_ROLES=['evidence_chain','review_independence','acceptance_criteria','regression','program_state','scope_no_drift','scientific_integrity','reproducibility','authority','adversarial_acceptance']
class CycleError(RuntimeError):pass

def run(cwd:Path,*args:str,timeout:int=5400,check=True):
 p=subprocess.run(list(args),cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout,check=False)
 if check and p.returncode!=0:raise CycleError(f"COMMAND_FAILED:{' '.join(args)}:{(p.stdout or '')[-4000:]}")
 return p
def git(cwd:Path,*args:str,**kw):return run(cwd,'git',*args,**kw)
def read_json(p:Path):return json.loads(p.read_text(encoding='utf-8'))
def load_mod(auth:Path,name:str):
 d=(auth/'scripts/mros').resolve()
 if str(d) not in sys.path:sys.path.insert(0,str(d))
 if name in sys.modules:del sys.modules[name]
 return importlib.import_module(name)
def sync(auth:Path,q:Path):
 git(auth,'fetch','origin',AUTH,QUEUE,timeout=300);git(q,'fetch','origin',QUEUE,AUTH,timeout=300)
 if git(auth,'status','--porcelain').stdout.strip():raise CycleError('AUTHORITY_WORKTREE_NOT_CLEAN')
 if git(q,'status','--porcelain').stdout.strip():raise CycleError('QUEUE_WORKTREE_NOT_CLEAN')
 git(auth,'merge','--ff-only',f'origin/{AUTH}',timeout=300);git(q,'rebase',f'origin/{QUEUE}',timeout=300)
def commit_auth(auth:Path,paths:list[Path],msg:str)->str:
 bridge=Path('/Users/madhuram/.mros-agent-bridge/bridge/scripts/mros').resolve()
 if str(bridge) not in sys.path:sys.path.insert(0,str(bridge))
 from mros_state_transition_engine import commit_transition
 parent=git(auth,'rev-parse','HEAD').stdout.strip();r=commit_transition(repo=auth,lock_path=Path.home()/'.mros-agent-bridge/state/authority-writer.lock',expected_parent=parent,changed_paths=[p.as_posix() for p in paths],message=msg);return r.commit_sha
def commit_queue(q:Path,paths:list[Path],msg:str)->str:
 rel=[p.as_posix() for p in paths];git(q,'add','--',*rel);staged=set(git(q,'diff','--cached','--name-only').stdout.splitlines())
 if staged!=set(rel):git(q,'reset');raise CycleError('QUEUE_COMMIT_SCOPE_MISMATCH')
 git(q,'commit','-m',msg);git(q,'fetch','origin',QUEUE,timeout=300);git(q,'rebase',f'origin/{QUEUE}',timeout=300);git(q,'push','origin',f'HEAD:{QUEUE}',timeout=300);return git(q,'rev-parse','HEAD').stdout.strip()
def state_top(text,key):
 m=re.search(rf'(?m)^{re.escape(key)}:\s*["\']?([^\n"\']+)',text);return m.group(1).strip() if m else ''
def set_top(text,key,value):
 pat=rf'(?m)^({re.escape(key)}:\s*).*$'
 if not re.search(pat,text):raise CycleError(f'STATE_KEY_MISSING:{key}')
 return re.sub(pat,rf'\g<1>{value}',text,count=1)
def set_status(text,section,key,value):
 # section is top-level mapping such as milestone_status/work_package_status.
 m=re.search(rf'(?ms)^{re.escape(section)}:\s*\n(?P<body>(?:^[ \t]+.*\n?)*)',text)
 if not m:raise CycleError(f'STATE_SECTION_MISSING:{section}')
 body=m.group('body');pat=rf'(?m)^([ \t]+{re.escape(key)}:\s*).*$'
 if not re.search(pat,body):raise CycleError(f'STATE_SECTION_KEY_MISSING:{section}:{key}')
 new=re.sub(pat,rf'\g<1>{value}',body,count=1);return text[:m.start('body')]+new+text[m.end('body'):]
def active_number(state:str)->int:
 s=state_top(state,'active_sprint')
 if not re.fullmatch(r'S\d{3}',s):raise CycleError(f'ACTIVE_SPRINT_INVALID:{s}')
 n=int(s[1:])
 if n>=111:raise CycleError('M9_HARD_STOP')
 if n<4:raise CycleError('POST_BOOTSTRAP_CYCLE_REQUIRES_S004_PLUS')
 return n
def evidence_dir(sprint:str)->Path:return Path('research/evidence/sprints')/sprint
def contract_path(sprint:str)->Path:return evidence_dir(sprint)/f'{sprint}_ACCEPTANCE_CONTRACT.json'
def native_path(sprint:str,candidate:str)->Path:return evidence_dir(sprint)/f'{sprint}_NATIVE_{candidate[:8]}.json'
def freeze_contract(auth:Path,n:int)->Path:
 s=sprint_spec(n);p=contract_path(s.sprint)
 if (auth/p).is_file():return p
 (auth/p).parent.mkdir(parents=True,exist_ok=True);criteria=[{'id':f'{s.sprint}-AC-{i:03d}','requirement':x} for i,x in enumerate(common_acceptance(),1)]
 data={'schema_version':'mros-controlled-sprint-contract-v1','manual_version':'1.0','manual_sha256':'53350c3f60f2046180726077b0c18fb52222d6826d4d6e10fc746a46ab80cb39','sprint':s.sprint,'milestone':s.milestone,'work_package':s.wp,'phase':s.phase,'objective':s.objective,'product_context':s.product_context,'primary_risk':s.primary_risk,'scope_lock':f'Only work required for {s.wp}; adjacent milestones/WPs are Parking Lot items.','assurance_tier':s.assurance_tier,'criteria':criteria,'runtime_authority':'NONE','m9_status':'NOT_STARTED'}
 (auth/p).write_text(json.dumps(data,sort_keys=True,indent=2)+'\n',encoding='utf-8');commit_auth(auth,[p],f'mros({s.sprint}): freeze controlled sprint contract [skip ci]');return p
def candidate(auth:Path,sprint:str)->str|None:
 d=auth/evidence_dir(sprint);best=(-1,None)
 if d.is_dir():
  for p in d.glob('AUTONOMOUS_REPAIR_G*.json'):
   try:x=read_json(p);g=int(x.get('generation') or 0);c=x.get('candidate_head')
   except Exception:continue
   if isinstance(c,str) and re.fullmatch(r'[0-9a-f]{40}',c) and g>best[0]:best=(g,c)
  if best[1]:return best[1]
  p=d/'AUTONOMOUS_IMPLEMENTATION_EXECUTION.json'
  if p.is_file():
   try:c=read_json(p).get('candidate_head')
   except Exception:c=None
   if isinstance(c,str) and re.fullmatch(r'[0-9a-f]{40}',c):return c
 return None
def run_implementer(auth:Path,state_root:Path,n:int):
 script=Path('/Users/madhuram/.mros-agent-bridge/bridge/scripts/mros/mros_program_sprint_executor.py');p=run(auth,sys.executable,str(script),'--repo',str(auth),'--state-root',str(state_root),'--sprint-number',str(n),timeout=7200,check=False)
 try:o=json.loads((p.stdout or '').splitlines()[-1])
 except Exception:raise CycleError('SPRINT_EXECUTOR_INVALID_OUTPUT')
 if p.returncode!=0 or o.get('status')!='SPRINT_IMPLEMENTATION_PUBLISHED':raise CycleError('SPRINT_IMPLEMENTATION_BLOCKED:'+str(o.get('error')))
 return o
def repair_generation(auth:Path,sprint:str)->int:
 nums=[];d=auth/evidence_dir(sprint)
 for p in d.glob('AUTONOMOUS_REPAIR_G*.json') if d.is_dir() else []:
  m=re.search(r'_G(\d+)_',p.name)
  if m:nums.append(int(m.group(1)))
 return max(nums,default=0)
def repair(auth:Path,state_root:Path,sprint:str,failed:str,source:str,findings:list[dict],extra:dict|None=None):
 g=repair_generation(auth,sprint)+1
 if g>MAX_REPAIR:raise CycleError('ARCHITECTURAL_REVIEW_REQUIRED:REPAIR_GENERATION_LIMIT')
 cp=evidence_dir(sprint)/f'{sprint}_{source}_REPAIR_CONTRACT_G{g}.json';data={'schema_version':'mros-program-repair-contract-v1','sprint':sprint,'failed_head':failed,'generation':g,'source':source,'blocking_findings':findings,'extra_context':extra or {},'instruction':'Repair common root causes once; preserve gates/history and add regressions.','runtime_authority':'NONE','m9_status':'NOT_STARTED'};(auth/cp).write_text(json.dumps(data,sort_keys=True,indent=2)+'\n',encoding='utf-8');commit_auth(auth,[cp],f'mros({sprint}): freeze autonomous repair contract G{g} [skip ci]')
 script=Path('/Users/madhuram/.mros-agent-bridge/bridge/scripts/mros/mros_program_repair_executor.py');p=run(auth,sys.executable,str(script),'--repo',str(auth),'--state-root',str(state_root),'--contract',str(auth/cp),'--generation',str(g),timeout=7200,check=False)
 try:o=json.loads((p.stdout or '').splitlines()[-1])
 except Exception:raise CycleError('REPAIR_EXECUTOR_INVALID_OUTPUT')
 if p.returncode!=0 or o.get('status')!='PROGRAM_REPAIR_PUBLISHED':raise CycleError('PROGRAM_REPAIR_BLOCKED:'+str(o.get('error')))
 return o
def native(auth:Path,state_root:Path,sprint:str,cand:str)->dict:
 p=native_path(sprint,cand)
 if (auth/p).is_file():return read_json(auth/p)
 script=Path('/Users/madhuram/.mros-agent-bridge/bridge/scripts/mros/mros_program_native_validator.py');r=run(auth,sys.executable,str(script),'--repo',str(auth),'--state-root',str(state_root),'--sprint',sprint,'--candidate',cand,timeout=7200,check=False)
 try:o=json.loads((r.stdout or '').splitlines()[-1])
 except Exception:raise CycleError('NATIVE_VALIDATOR_INVALID_OUTPUT')
 if r.returncode!=0:raise CycleError('NATIVE_VALIDATOR_BLOCKED:'+str(o.get('error')))
 (auth/p).write_text(json.dumps(o,sort_keys=True,indent=2)+'\n',encoding='utf-8');commit_auth(auth,[p],f'mros({sprint}): seal exact-head native validation {cand[:8]} [skip ci]');return o
def manifest_files(q:Path,sprint:str,kind:str):
 letter='R' if kind=='reviewer' else 'A';pat=re.compile(rf'{sprint}_{letter}(\d{{3}})_(REVIEW|AUDIT)_POPULATION\.json$');out=[];d=q/MAIL/'manifests'
 for p in d.glob(f'{sprint}_{letter}*_POPULATION.json') if d.is_dir() else []:
  m=pat.fullmatch(p.name)
  if not m:continue
  try:x=read_json(p)
  except Exception:continue
  if x.get('job_type')==kind:out.append((int(m.group(1)),p,x))
 return sorted(out,key=lambda z:z[0])
def population_complete(q:Path,m:dict):
 payloads=[];receipts={}
 for x in m.get('members',[]):
  op=q/str(x.get('output_path',''));rp=q/str(x.get('receipt_path',''))
  if not op.is_file() or not rp.is_file():return False,[],{}
  try:d=read_json(op);r=read_json(rp);job=r.get('job',{})
  except Exception:return False,[],{}
  if job.get('state')!='SUCCEEDED' or job.get('exit_code')!=0:return False,[],{}
  payloads.append((str(op),d));receipts[job.get('job_id')]=r
 return True,payloads,receipts
def next_round(q:Path,sprint:str,kind:str):return max([n for n,_,_ in manifest_files(q,sprint,kind)]+[0])+1
def queue_review(q:Path,sprint:str,cand:str,tier:str):
 for n,p,m in manifest_files(q,sprint,'reviewer'):
  if m.get('candidate_head')==cand:return f'R{n:03d}',p,m
 n=next_round(q,sprint,'reviewer');rr=f'R{n:03d}';count=10 if tier=='FULL' else 3;roles=REVIEW_ROLES[:count];members=[];packets=[];requests=[]
 for i,role in enumerate(roles,1):
  rid=f'R{i:02d}';base=f'{sprint}_{rr}_{rid}';packet=MAIL/'packets'/f'{base}.md';output=MAIL/'results'/f'{base}.json';receipt=MAIL/'receipts'/f'{base}.json';request=MAIL/'requests'/f'{base}.json';members.append({'execution_role_id':rid,'semantic_role':role,'packet_path':packet.as_posix(),'output_path':output.as_posix(),'receipt_path':receipt.as_posix()});(q/packet).parent.mkdir(parents=True,exist_ok=True);(q/packet).write_text(f'''# {sprint} independent review {rr} {rid}\nExact candidate: `{cand}`\nRole: `{role}`\nReview the exact candidate against its frozen sprint contract, prior accepted contracts, no-drift, provenance, fail-closed behavior, causal-time/denominator rules where applicable, and runtime_authority=NONE. Do not modify candidate or read peers. Return ONLY one JSON object conforming to research/review_board/REVIEW_SCHEMA.json with sprint={sprint}, round={rr}, candidate_head={cand}, role={role}, execution_role_id={rid}, execution_job_id=MROS_JOB_ID, transport=mac_git_mailbox, packet_path={packet.as_posix()}, output_path={output.as_posix()}, runtime_authority=NONE, broker_actions=NONE, both independence booleans=true. CRITICAL/MAJOR/UNKNOWN block.\n''',encoding='utf-8');packets.append(packet);req={'schema_version':1,'request_id':f'{base}-{cand[:8]}','created_by':'mros-post-bootstrap-cycle','created_at':datetime.date.today().isoformat(),'job_type':'reviewer','role_id':rid,'candidate_sha':cand,'packet_path':packet.as_posix(),'output_path':output.as_posix(),'backend':'codex'};(q/request).write_text(json.dumps(req,sort_keys=True,indent=2)+'\n',encoding='utf-8');requests.append(request)
 mp=MAIL/'manifests'/f'{sprint}_{rr}_REVIEW_POPULATION.json';(q/mp).parent.mkdir(parents=True,exist_ok=True);manifest={'schema_version':'mros-agent-population-v1','job_type':'reviewer','candidate_head':cand,'sprint':sprint,'round':rr,'frozen_before_execution':True,'expected_count':count,'assurance_tier':tier,'created_by':'mros-post-bootstrap-cycle','runtime_authority':'NONE','members':members};(q/mp).write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n',encoding='utf-8');commit_queue(q,[mp,*packets],f'mros({sprint}): freeze {rr} {tier} review population [skip ci]');commit_queue(q,requests,f'mros({sprint}): queue {rr} review population [skip ci]');return rr,mp,manifest
def findings(agg:dict,kind:str):
 out=[];key='reviews' if kind=='review' else 'audits'
 for x in agg.get(key,[]):
  if isinstance(x,dict):out += [f for f in x.get('findings',[]) if isinstance(f,dict) and f.get('severity') in {'CRITICAL','MAJOR','UNKNOWN'}]
 for x in agg.get('invalid',[]):
  a=x.get('review' if kind=='review' else 'audit') if isinstance(x,dict) else None
  if isinstance(a,dict):out += [f for f in a.get('findings',[]) if isinstance(f,dict) and f.get('severity') in {'CRITICAL','MAJOR','UNKNOWN'}]
 return out
def review_aggregate(auth:Path,q:Path,sprint:str,cand:str,rr:str,mp:Path,m:dict):
 ap=evidence_dir(sprint)/f'{sprint}_{rr}_REVIEW_AGGREGATE.json'
 if (auth/ap).is_file():return read_json(auth/ap)
 done,payloads,receipts=population_complete(q,m)
 if not done:return None
 mod=load_mod(auth,'aggregate_reviews');agg=mod.aggregate_payloads(payloads,candidate_head=cand,receipts=receipts,manifest=m);(auth/ap).write_text(json.dumps(agg,sort_keys=True,indent=2)+'\n',encoding='utf-8');commit_auth(auth,[ap],f'mros({sprint}): consume {rr} review aggregate {agg.get("decision")} [skip ci]');return agg
def queue_audit(q:Path,sprint:str,cand:str,review_round:str,tier:str,native_ref:str,criteria:list[str]):
 for n,p,m in manifest_files(q,sprint,'auditor'):
  if m.get('candidate_head')==cand and m.get('review_round')==review_round:return f'A{n:03d}',p,m
 n=next_round(q,sprint,'auditor');ar=f'A{n:03d}';count=10 if tier=='FULL' else 1;roles=AUDIT_ROLES[:count];members=[];packets=[];requests=[]
 for i,role in enumerate(roles,1):
  rid=f'A{i:02d}';base=f'{sprint}_{ar}_{rid}';packet=MAIL/'packets'/f'{base}.md';output=MAIL/'results'/f'{base}.json';receipt=MAIL/'receipts'/f'{base}.json';members.append({'execution_role_id':rid,'semantic_role':role,'packet_path':packet.as_posix(),'output_path':output.as_posix(),'receipt_path':receipt.as_posix()});(q/packet).parent.mkdir(parents=True,exist_ok=True);(q/packet).write_text(f'''# {sprint} independent audit {ar} {rid}\nExact candidate: `{cand}`\nAudited review round: `{review_round}`\nNative evidence: `{native_ref}`\nRequired acceptance IDs: {json.dumps(criteria)}\nRole: `{role}`\nAudit the evidence chain independently, including review legality/provenance, candidate binding, acceptance coverage, state/scope, no hidden authority promotion, and runtime_authority=NONE. Return ONLY one JSON object conforming to research/review_board/AUDIT_SCHEMA.json with sprint={sprint}, round={ar}, candidate_head={cand}, role={role}, execution_role_id={rid}, execution_job_id=MROS_JOB_ID, transport=mac_git_mailbox, packet_path={packet.as_posix()}, output_path={output.as_posix()}, runtime_authority=NONE, broker_actions=NONE, both independence booleans=true, audited_review_round={review_round}, audited_native_validation={native_ref}, audited_acceptance_criteria={json.dumps(criteria)}, audit_scope=["evidence_chain","review_legality","acceptance_coverage","state_scope_authority"]. CRITICAL/MAJOR/UNKNOWN block.\n''',encoding='utf-8');packets.append(packet);req={'schema_version':1,'request_id':f'{base}-{cand[:8]}','created_by':'mros-post-bootstrap-cycle','created_at':datetime.date.today().isoformat(),'job_type':'auditor','role_id':rid,'candidate_sha':cand,'packet_path':packet.as_posix(),'output_path':output.as_posix(),'backend':'codex'};(q/request).write_text(json.dumps(req,sort_keys=True,indent=2)+'\n',encoding='utf-8');requests.append(request)
 mp=MAIL/'manifests'/f'{sprint}_{ar}_AUDIT_POPULATION.json';(q/mp).parent.mkdir(parents=True,exist_ok=True);m={'schema_version':'mros-agent-population-v1','job_type':'auditor','candidate_head':cand,'sprint':sprint,'round':ar,'review_round':review_round,'frozen_before_execution':True,'expected_count':count,'assurance_tier':tier,'created_by':'mros-post-bootstrap-cycle','runtime_authority':'NONE','members':members};(q/mp).write_text(json.dumps(m,sort_keys=True,indent=2)+'\n',encoding='utf-8');commit_queue(q,[mp,*packets],f'mros({sprint}): freeze {ar} {tier} audit population [skip ci]');commit_queue(q,requests,f'mros({sprint}): queue {ar} audit population [skip ci]');return ar,mp,m
def audit_aggregate(auth:Path,q:Path,sprint:str,cand:str,ar:str,mp:Path,m:dict,review_round:str,review:dict,criteria:list[str],native_ref:str):
 ap=evidence_dir(sprint)/f'{sprint}_{ar}_AUDIT_AGGREGATE.json'
 if (auth/ap).is_file():return read_json(auth/ap)
 done,payloads,receipts=population_complete(q,m)
 if not done:return None
 review_jobs=[x.get('execution_job_id') for x in review.get('reviews',[]) if isinstance(x,dict)];mod=load_mod(auth,'aggregate_audits');agg=mod.aggregate_payloads(payloads,candidate_head=cand,review_round=review_round,receipts=receipts,manifest=m,review_job_ids=review_jobs,required_acceptance_ids=criteria,expected_native_ref=native_ref);(auth/ap).write_text(json.dumps(agg,sort_keys=True,indent=2)+'\n',encoding='utf-8');commit_auth(auth,[ap],f'mros({sprint}): consume {ar} audit aggregate {agg.get("decision")} [skip ci]');return agg
def finalize(auth:Path,n:int,cand:str,rr:str,review:dict,ar:str,audit:dict,native_ref:str):
 s=sprint_spec(n);state=(auth/STATE).read_text(encoding='utf-8')
 if state_top(state,'active_sprint')!=s.sprint:raise CycleError('FINALIZE_ACTIVE_SPRINT_MISMATCH')
 if any((review.get(k,0) or audit.get(k,0)) for k in ('critical','major','unknown')) or review.get('decision') not in PASS or audit.get('decision') not in PASS:raise CycleError('FINALIZE_BLOCKING_BOARD_RESULT')
 decision=evidence_dir(s.sprint)/f'{s.sprint}_AUTONOMOUS_ACCEPTANCE_DECISION.json';data={'schema_version':'mros-controlled-sprint-decision-v1','sprint':s.sprint,'milestone':s.milestone,'work_package':s.wp,'candidate_head':cand,'decision':'ACCEPTED','native_evidence':native_ref,'review_round':rr,'review_decision':review.get('decision'),'audit_round':ar,'audit_decision':audit.get('decision'),'runtime_authority':'NONE','m9_status':'NOT_STARTED'};(auth/decision).write_text(json.dumps(data,sort_keys=True,indent=2)+'\n',encoding='utf-8')
 state=set_top(state,'last_completed_sprint',s.sprint)
 paths=[decision,STATE,LEDGER]
 ledger=(auth/LEDGER).read_text(encoding='utf-8').rstrip()+'\n'+json.dumps({'sprint_id':s.sprint,'milestone':s.milestone,'work_package':s.wp,'status':'ACCEPTED','branch':AUTH,'authority_grade':'Research / R','decision':'ACCEPTED','candidate_head':cand,'native_evidence':native_ref,'review_round':rr,'audit_round':ar,'m9':'NOT_STARTED','runtime_authority':'NONE'},sort_keys=True)+'\n'
 if n%5==0:state=set_status(state,'work_package_status',s.wp,'ACCEPTED')
 if n in MILESTONE_LAST_SPRINT.values():state=set_status(state,'milestone_status',s.milestone,'ACCEPTED')
 nxt=next_sprint(n)
 if nxt is None:
  state=set_top(state,'active_sprint_status','M8_COMPLETE_M9_NOT_STARTED');state=set_top(state,'program_status','M8_COMPLETE_M9_HARD_STOP');state=set_status(state,'milestone_status','M9','NOT_STARTED');ledger+=json.dumps({'program':'MROS','status':'M8_COMPLETE_M9_HARD_STOP','last_completed_sprint':'S110','m9':'NOT_STARTED','runtime_authority':'NONE'},sort_keys=True)+'\n'
 else:
  ns=sprint_spec(n+1);state=set_top(state,'active_sprint',nxt);state=set_top(state,'active_sprint_status','ACTIVE');state=set_top(state,'active_work_package',ns.wp);state=set_top(state,'active_milestone',ns.milestone)
  if n%5==0:state=set_status(state,'work_package_status',ns.wp,'ACTIVE')
  if n in MILESTONE_LAST_SPRINT.values():state=set_status(state,'milestone_status',ns.milestone,'ACTIVE')
  ledger+=json.dumps({'sprint_id':nxt,'milestone':ns.milestone,'work_package':ns.wp,'status':'ACTIVE','branch':AUTH,'authority_grade':'Research / R','decision':'ACTIVE','m9':'NOT_STARTED','runtime_authority':'NONE'},sort_keys=True)+'\n'
 (auth/STATE).write_text(state,encoding='utf-8');(auth/LEDGER).write_text(ledger,encoding='utf-8');sha=commit_auth(auth,paths,f'mros({s.sprint}): accept sprint and advance safely [skip ci]');return {'status':'M8_COMPLETE_M9_HARD_STOP' if nxt is None else 'SPRINT_ACCEPTED_NEXT_ACTIVE','accepted':s.sprint,'next':nxt,'commit':sha,'runtime_authority':'NONE'}
def cycle(auth:Path,q:Path,state_root:Path):
 sync(auth,q);state=(auth/STATE).read_text(encoding='utf-8');n=active_number(state);s=sprint_spec(n);freeze_contract(auth,n);sync(auth,q);cand=candidate(auth,s.sprint)
 if cand is None:return run_implementer(auth,state_root,n)
 nv=native(auth,state_root,s.sprint,cand);sync(auth,q)
 if nv.get('result')!='PASS':return repair(auth,state_root,s.sprint,cand,'NATIVE_VALIDATION',[{'severity':'MAJOR','requirement':'Exact-head native validation must pass','evidence':nv.get('output','')[-4000:],'falsifier':'A fresh exact-head native run passes all required commands.','recommended_repair_scope':'Repair implementation/tests without weakening gates.'}],{'native':nv})
 rr,rmp,rm=queue_review(q,s.sprint,cand,s.assurance_tier);rev=review_aggregate(auth,q,s.sprint,cand,rr,rmp,rm)
 if rev is None:return {'status':'WAIT_REVIEW_POPULATION','sprint':s.sprint,'round':rr}
 if rev.get('decision') not in PASS:return repair(auth,state_root,s.sprint,cand,f'{rr}_REVIEW',findings(rev,'review'),{'aggregate_decision':rev.get('decision'),'invalid':rev.get('invalid',[])})
 contract=read_json(auth/contract_path(s.sprint));criteria=[x['id'] for x in contract.get('criteria',[]) if isinstance(x,dict) and isinstance(x.get('id'),str)];nref=native_path(s.sprint,cand).as_posix();ar,amp,am=queue_audit(q,s.sprint,cand,rr,s.assurance_tier,nref,criteria);aud=audit_aggregate(auth,q,s.sprint,cand,ar,amp,am,rr,rev,criteria,nref)
 if aud is None:return {'status':'WAIT_AUDIT_POPULATION','sprint':s.sprint,'round':ar}
 if aud.get('decision') not in PASS:return repair(auth,state_root,s.sprint,cand,f'{ar}_AUDIT',findings(aud,'audit'),{'aggregate_decision':aud.get('decision'),'invalid':aud.get('invalid',[])})
 return finalize(auth,n,cand,rr,rev,ar,aud,nref)
def main():
 p=argparse.ArgumentParser();p.add_argument('--authority-repo',required=True,type=Path);p.add_argument('--queue-repo',required=True,type=Path);p.add_argument('--state-root',required=True,type=Path);a=p.parse_args()
 try:print(json.dumps(cycle(a.authority_repo.resolve(),a.queue_repo.resolve(),a.state_root.resolve()),sort_keys=True));return 0
 except Exception as exc:print(json.dumps({'status':'POST_BOOTSTRAP_CYCLE_BLOCKED','error':f'{type(exc).__name__}:{exc}','runtime_authority':'NONE'},sort_keys=True));return 2
if __name__=='__main__':raise SystemExit(main())
