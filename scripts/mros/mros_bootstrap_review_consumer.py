#!/usr/bin/env python3
"""Consume the frozen S003 R002 review population and commit its aggregate.

This runs on the Mac supervisor. It never invents reviewer findings: it imports
and executes the authoritative MROS review validator/aggregator from the current
authority worktree, requires the entire frozen population to have receipts and
outputs, and commits only the aggregate/state/repair-contract transition.
"""
from __future__ import annotations
import argparse, importlib, json, re, subprocess, sys
from pathlib import Path

AUTH='research/mros-program-v1'; QUEUE='automation/mros-agent-queue-v1'
STATE=Path('research/program/MROS_PROGRAM_STATE.yaml')
ROOT=Path('research/evidence/sprints/S003/agent_queue')
MANIFEST=ROOT/'manifests/S003_R002_REVIEW_POPULATION.json'
AGG=Path('research/evidence/sprints/S003/S003_BOARD_BOOTSTRAP_R002_REVIEW_AGGREGATE.json')
REPAIR=Path('research/evidence/sprints/S003/S003_BOARD_BOOTSTRAP_R002_REPAIR_CONTRACT.json')
PASS={'PASS','PASS_WITH_MINOR_FINDINGS'}

class ConsumeError(RuntimeError): pass

def git(repo:Path,*args:str,check:bool=True)->str:
 p=subprocess.run(['git',*args],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
 if check and p.returncode!=0: raise ConsumeError(f"GIT_FAILED:{' '.join(args)}:{(p.stderr or p.stdout).strip()}")
 return p.stdout.strip()

def replace_scalar(text:str,key:str,value:str)->str:
 pat=rf'(?m)^({re.escape(key)}:\s*).*$'
 if not re.search(pat,text): raise ConsumeError(f'STATE_KEY_MISSING:{key}')
 return re.sub(pat,rf'\g<1>{value}',text,count=1)

def replace_indented(text:str,key:str,value:str)->str:
 pat=rf'(?m)^(\s+{re.escape(key)}:\s*).*$'
 if not re.search(pat,text): raise ConsumeError(f'STATE_KEY_MISSING:{key}')
 return re.sub(pat,rf'\g<1>{value}',text,count=1)

def load_authority_modules(auth:Path):
 scripts=(auth/'scripts/mros').resolve()
 if str(scripts) not in sys.path: sys.path.insert(0,str(scripts))
 return importlib.import_module('aggregate_reviews')

def read_json(path:Path): return json.loads(path.read_text(encoding='utf-8'))

def commit_authority(auth:Path,paths:list[Path],message:str)->str:
 # Import transition engine from the bridge checkout, not authority branch.
 bridge=Path('/Users/madhuram/.mros-agent-bridge/bridge/scripts/mros').resolve()
 if str(bridge) not in sys.path: sys.path.insert(0,str(bridge))
 from mros_state_transition_engine import commit_transition
 parent=git(auth,'rev-parse','HEAD')
 result=commit_transition(repo=auth,lock_path=Path.home()/'.mros-agent-bridge/state/authority-writer.lock',expected_parent=parent,changed_paths=[p.as_posix() for p in paths],message=message)
 return result.commit_sha

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--authority-repo',required=True,type=Path);ap.add_argument('--queue-repo',required=True,type=Path);ns=ap.parse_args()
 auth=ns.authority_repo.resolve();q=ns.queue_repo.resolve()
 git(auth,'fetch','origin',AUTH,QUEUE);git(q,'fetch','origin',QUEUE,AUTH)
 git(auth,'merge','--ff-only',f'origin/{AUTH}');git(q,'rebase',f'origin/{QUEUE}')
 state=(auth/STATE).read_text(encoding='utf-8')
 if 'active_sprint: S003' not in state: return 3
 if 'BOARD_BOOTSTRAP_R002_REVIEW_PREPARATION' not in state and 'BOARD_BOOTSTRAP_R002_REVIEW_RUNNING' not in state: return 3
 manifest_path=q/MANIFEST
 if not manifest_path.is_file(): return 3
 manifest=read_json(manifest_path);candidate=manifest.get('candidate_head')
 if not isinstance(candidate,str) or not re.fullmatch(r'[0-9a-f]{40}',candidate): raise ConsumeError('R002_MANIFEST_CANDIDATE_INVALID')
 payloads=[];receipts={};missing=[]
 for m in manifest.get('members',[]):
  out=q/m['output_path'];rec=q/m['receipt_path']
  if not out.is_file() or not rec.is_file(): missing.append(m.get('execution_role_id'));continue
  try:d=read_json(out);r=read_json(rec)
  except Exception as exc: raise ConsumeError(f'R002_RESULT_PARSE_FAILED:{m.get("execution_role_id")}:{exc}')
  payloads.append((m['output_path'],d));job=r.get('job') if isinstance(r,dict) else None
  if isinstance(job,dict) and isinstance(job.get('job_id'),str): receipts[job['job_id']]=r
 if missing: return 3
 aggmod=load_authority_modules(auth)
 aggregate=aggmod.aggregate_payloads(payloads,candidate_head=candidate,receipts=receipts,manifest=manifest)
 aggregate['review_round']='R002';aggregate['population_manifest']=MANIFEST.as_posix();aggregate['runtime_authority']='NONE';aggregate['m9_started']=False
 AGG.parent.mkdir(parents=True,exist_ok=True);(auth/AGG).write_text(json.dumps(aggregate,sort_keys=True,indent=2)+'\n',encoding='utf-8')
 changed=[AGG]
 decision=aggregate.get('decision')
 if decision in PASS:
  state=replace_scalar(state,'active_sprint_status','BOARD_BOOTSTRAP_R002_REVIEW_PASS_A001_AUDIT_PREPARATION')
  state=replace_indented(state,'bootstrap_independent_review_status',decision)
  state=replace_indented(state,'bootstrap_independent_audit_status','READY_TO_FREEZE_AND_LAUNCH_A001')
 else:
  findings=[]
  for r in aggregate.get('reviews',[]):
   findings.extend(f for f in r.get('findings',[]) if f.get('severity') in {'CRITICAL','MAJOR','UNKNOWN'})
  repair={'schema_version':'mros-repair-contract-v1','sprint':'S003','failed_head':candidate,'review_round':'R002','aggregate_decision':decision,'blocking_findings':findings,'repair_scope':{'allowed':['minimum changes required to resolve listed blocking findings'],'forbidden':['weaken_fixture','change_acceptance_criteria','reuse_prior_head_reviews','begin_next_sprint','begin_M2','begin_M9','create_runtime_authority']},'runtime_authority':'NONE'}
  (auth/REPAIR).write_text(json.dumps(repair,sort_keys=True,indent=2)+'\n',encoding='utf-8');changed.append(REPAIR)
  state=replace_scalar(state,'active_sprint_status','BOARD_BOOTSTRAP_R002_REVIEW_REPAIR_REQUIRED')
  state=replace_indented(state,'bootstrap_independent_review_status',str(decision))
  state=replace_indented(state,'bootstrap_independent_audit_status','BLOCKED_UNTIL_REPAIRED_REVIEW_PASS')
 (auth/STATE).write_text(state,encoding='utf-8');changed.append(STATE)
 sha=commit_authority(auth,changed,f'mros(S003): autonomously consume R002 review aggregate {decision} [skip ci]')
 print(json.dumps({'status':'R002_REVIEW_AGGREGATED','candidate':candidate,'decision':decision,'valid_reviews':aggregate.get('valid_reviews'),'critical':aggregate.get('critical'),'major':aggregate.get('major'),'minor':aggregate.get('minor'),'unknown':aggregate.get('unknown'),'commit':sha},sort_keys=True))
 return 0
if __name__=='__main__': raise SystemExit(main())
