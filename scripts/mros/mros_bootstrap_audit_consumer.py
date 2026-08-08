#!/usr/bin/env python3
"""Consume the frozen S003 A001 audit population and commit its aggregate.

A frozen audit role may have multiple transport attempts. Failed attempts remain
committed; only a successful exact-candidate attempt can satisfy quorum.
"""
from __future__ import annotations
import argparse, importlib, json, re, subprocess, sys
from pathlib import Path
from typing import Any
AUTH='research/mros-program-v1';QUEUE='automation/mros-agent-queue-v1'
STATE=Path('research/program/MROS_PROGRAM_STATE.yaml');ROOT=Path('research/evidence/sprints/S003/agent_queue')
MANIFEST=ROOT/'manifests/S003_A001_AUDIT_POPULATION.json'
REVIEW_AGG=Path('research/evidence/sprints/S003/S003_BOARD_BOOTSTRAP_R002_REVIEW_AGGREGATE.json')
AUDIT_AGG=Path('research/evidence/sprints/S003/S003_BOARD_BOOTSTRAP_A001_AUDIT_AGGREGATE.json')
REPAIR=Path('research/evidence/sprints/S003/S003_BOARD_BOOTSTRAP_A001_REPAIR_CONTRACT.json')
ACCEPTANCE=Path('research/evidence/sprints/S003/S003_ACCEPTANCE_CONTRACT.json')
NATIVE_REF='research/evidence/sprints/S003/S003_BOARD_CALIBRATION_NATIVE_EVIDENCE_SUPERVISOR.md'
PASS={'PASS','PASS_WITH_MINOR_FINDINGS'}
class ConsumeError(RuntimeError):pass

def git(repo:Path,*args:str,check=True)->str:
 p=subprocess.run(['git',*args],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
 if check and p.returncode!=0:raise ConsumeError(f"GIT_FAILED:{' '.join(args)}:{(p.stderr or p.stdout).strip()}")
 return p.stdout.strip()
def replace_scalar(text,key,value):
 pat=rf'(?m)^({re.escape(key)}:\s*).*$'
 if not re.search(pat,text):raise ConsumeError(f'STATE_KEY_MISSING:{key}')
 return re.sub(pat,rf'\g<1>{value}',text,count=1)
def replace_indented(text,key,value):
 pat=rf'(?m)^(\s+{re.escape(key)}:\s*).*$'
 if not re.search(pat,text):raise ConsumeError(f'STATE_KEY_MISSING:{key}')
 return re.sub(pat,rf'\g<1>{value}',text,count=1)
def read_json(p:Path):return json.loads(p.read_text(encoding='utf-8'))
def load_mod(auth:Path):
 scripts=(auth/'scripts/mros').resolve()
 if str(scripts) not in sys.path:sys.path.insert(0,str(scripts))
 return importlib.import_module('aggregate_audits')
def commit(auth:Path,paths:list[Path],message:str)->str:
 bridge=Path('/Users/madhuram/.mros-agent-bridge/bridge/scripts/mros').resolve()
 if str(bridge) not in sys.path:sys.path.insert(0,str(bridge))
 from mros_state_transition_engine import commit_transition
 parent=git(auth,'rev-parse','HEAD');r=commit_transition(repo=auth,lock_path=Path.home()/'.mros-agent-bridge/state/authority-writer.lock',expected_parent=parent,changed_paths=[p.as_posix() for p in paths],message=message);return r.commit_sha

def successful_attempts(q:Path,*,role_id:str,candidate:str)->list[tuple[str,dict[str,Any],dict[str,Any]]]:
 found=[];request_dir=q/ROOT/'requests'
 if not request_dir.is_dir():return found
 for req_path in sorted(request_dir.glob('*.json')):
  try:req=read_json(req_path)
  except Exception:continue
  if not isinstance(req,dict):continue
  if req.get('job_type')!='auditor' or req.get('role_id')!=role_id or req.get('candidate_sha')!=candidate:continue
  rec=q/ROOT/'receipts'/req_path.name;out_rel=req.get('output_path');out=q/str(out_rel) if isinstance(out_rel,str) else None
  if not rec.is_file() or out is None or not out.is_file() or out.stat().st_size==0:continue
  try:r=read_json(rec);d=read_json(out)
  except Exception:continue
  job=r.get('job') if isinstance(r,dict) else None
  if not (isinstance(job,dict) and job.get('state')=='SUCCEEDED' and job.get('exit_code')==0):continue
  if job.get('candidate_sha')!=candidate or job.get('role_id')!=role_id:continue
  found.append((str(out.relative_to(q)),d,r))
 return found

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--authority-repo',required=True,type=Path);ap.add_argument('--queue-repo',required=True,type=Path);ns=ap.parse_args();auth=ns.authority_repo.resolve();q=ns.queue_repo.resolve()
 git(auth,'fetch','origin',AUTH,QUEUE);git(q,'fetch','origin',QUEUE,AUTH);git(auth,'merge','--ff-only',f'origin/{AUTH}');git(q,'rebase',f'origin/{QUEUE}')
 state=(auth/STATE).read_text(encoding='utf-8')
 if 'active_sprint: S003' not in state:return 3
 if 'BOARD_BOOTSTRAP_R002_REVIEW_PASS_A001_AUDIT_PREPARATION' not in state and 'BOARD_BOOTSTRAP_A001_AUDIT_RUNNING' not in state:return 3
 mp=q/MANIFEST
 if not mp.is_file():return 3
 manifest=read_json(mp);candidate=manifest.get('candidate_head')
 if not isinstance(candidate,str) or not re.fullmatch(r'[0-9a-f]{40}',candidate):raise ConsumeError('A001_MANIFEST_CANDIDATE_INVALID')
 payloads=[];receipts={};missing=[];attempt_selection={}
 for m in manifest.get('members',[]):
  role=m.get('execution_role_id');attempts=successful_attempts(q,role_id=role,candidate=candidate) if isinstance(role,str) else []
  if not attempts:missing.append(role);continue
  out_rel,d,r=attempts[0];payloads.append((out_rel,d));job=r.get('job') if isinstance(r,dict) else None
  if isinstance(job,dict) and isinstance(job.get('job_id'),str):receipts[job['job_id']]=r
  attempt_selection[str(role)]={'output_path':out_rel,'job_id':job.get('job_id') if isinstance(job,dict) else None,'successful_attempts_seen':len(attempts)}
 if missing:return 3
 review=read_json(auth/REVIEW_AGG);contract=read_json(auth/ACCEPTANCE);required=[c.get('id') for c in contract.get('criteria',[]) if isinstance(c,dict) and c.get('id')];review_jobs=[r.get('execution_job_id') for r in review.get('reviews',[]) if isinstance(r,dict)]
 mod=load_mod(auth);aggregate=mod.aggregate_payloads(payloads,candidate_head=candidate,review_round='R002',receipts=receipts,manifest=manifest,review_job_ids=review_jobs,required_acceptance_ids=required,expected_native_ref=NATIVE_REF)
 aggregate['audit_round']='A001';aggregate['population_manifest']=MANIFEST.as_posix();aggregate['review_aggregate']=REVIEW_AGG.as_posix();aggregate['attempt_selection']=attempt_selection;aggregate['runtime_authority']='NONE';aggregate['m9_started']=False
 (auth/AUDIT_AGG).write_text(json.dumps(aggregate,sort_keys=True,indent=2)+'\n',encoding='utf-8');changed=[AUDIT_AGG];decision=aggregate.get('decision')
 if decision in PASS:
  state=replace_scalar(state,'active_sprint_status','BOARD_BOOTSTRAP_AUTHORIZATION_PENDING');state=replace_indented(state,'bootstrap_independent_audit_status',str(decision))
 else:
  findings=[]
  for a in aggregate.get('audits',[]):findings.extend(f for f in a.get('findings',[]) if f.get('severity') in {'CRITICAL','MAJOR','UNKNOWN'})
  repair={'schema_version':'mros-repair-contract-v1','sprint':'S003','failed_head':candidate,'audit_round':'A001','aggregate_decision':decision,'blocking_findings':findings,'repair_scope':{'allowed':['minimum changes required to resolve listed blocking findings'],'forbidden':['weaken_fixture','change_acceptance_criteria','reuse_prior_head_reviews','reuse_prior_head_audits','begin_next_sprint','begin_M2','begin_M9','create_runtime_authority']},'runtime_authority':'NONE'}
  (auth/REPAIR).write_text(json.dumps(repair,sort_keys=True,indent=2)+'\n',encoding='utf-8');changed.append(REPAIR)
  state=replace_scalar(state,'active_sprint_status','BOARD_BOOTSTRAP_A001_AUDIT_REPAIR_REQUIRED');state=replace_indented(state,'bootstrap_independent_audit_status',str(decision))
 (auth/STATE).write_text(state,encoding='utf-8');changed.append(STATE)
 sha=commit(auth,changed,f'mros(S003): autonomously consume A001 audit aggregate {decision} [skip ci]')
 print(json.dumps({'status':'A001_AUDIT_AGGREGATED','candidate':candidate,'decision':decision,'valid_audits':aggregate.get('valid_audits'),'critical':aggregate.get('critical'),'major':aggregate.get('major'),'minor':aggregate.get('minor'),'unknown':aggregate.get('unknown'),'commit':sha},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
