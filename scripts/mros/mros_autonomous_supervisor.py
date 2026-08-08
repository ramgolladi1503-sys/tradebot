#!/usr/bin/env python3
"""Persistent MROS supervisor that executes repository steps autonomously."""
from __future__ import annotations
import argparse,fcntl,json,os,re,subprocess,sys,time
from dataclasses import dataclass,asdict
from pathlib import Path
from typing import Any
AUTHORITY_BRANCH='research/mros-program-v1';QUEUE_BRANCH='automation/mros-agent-queue-v1'
QUEUE_ROOT=Path('research/evidence/sprints/S003/agent_queue');BRIDGE_ROOT=Path('/Users/madhuram/.mros-agent-bridge/bridge');QUEUE_WT=Path('/Users/madhuram/.mros-agent-bridge/queue')
class SupervisorError(RuntimeError):pass
@dataclass
class Health:
 supervisor_status:str='STARTING';phase:str='UNKNOWN';authority_head:str='';queue_head:str='';milestone:str='';work_package:str='';sprint:str='';pending_requests:int=0;completed_receipts:int=0;failed_receipts:int=0;worker_alive:bool=False;worker_status:str='UNKNOWN';worker_last_error:str|None=None;next_action:str='DISCOVER';last_error:str|None=None;runtime_authority:str='NONE';m9_started:bool=False;updated_at:float=0.0

def git(repo:Path,*args:str,timeout:int=180,check:bool=True)->subprocess.CompletedProcess[str]:
 p=subprocess.run(['git',*args],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout,check=False)
 if check and p.returncode!=0:raise SupervisorError(f"GIT_FAILED:{' '.join(args)}:{(p.stderr or p.stdout).strip()}")
 return p
def ref(repo:Path,name:str)->str:return git(repo,'rev-parse',name).stdout.strip()
def fetch(repo:Path)->None:git(repo,'fetch','origin',AUTHORITY_BRANCH,QUEUE_BRANCH)
def parse_program_state(text:str)->dict[str,str]:
 keys=('active_milestone','active_work_package','active_sprint','program_status','active_sprint_status');out={}
 for k in keys:
  m=re.search(rf"(?m)^{re.escape(k)}:\s*[\"']?([^\n\"']+)",text);out[k]=m.group(1).strip() if m else ''
 m=re.search(r"(?m)^\s*runtime_authority:\s*[\"']?([^\n\"']+)",text);out['runtime_authority']=m.group(1).strip() if m else ''
 return out
def read_at_ref(repo:Path,git_ref:str,path:str)->str:return git(repo,'show',f'{git_ref}:{path}').stdout
def queue_inventory(repo:Path)->tuple[list[str],dict[str,dict[str,Any]]]:
 files=git(repo,'ls-tree','-r','--name-only',f'origin/{QUEUE_BRANCH}',str(QUEUE_ROOT)).stdout.splitlines();requests=[];receipts={}
 for p in files:
  if '/requests/' in p and p.endswith('.json'):requests.append(p)
  elif '/receipts/' in p and p.endswith('.json'):
   try:receipts[Path(p).name]=json.loads(read_at_ref(repo,f'origin/{QUEUE_BRANCH}',p))
   except Exception:receipts[Path(p).name]={'_invalid':True}
 return requests,receipts
def _is_review_request(name:str)->bool:
 u=name.upper()
 if 'CALIBRATION' in u:return False
 if re.search(r'(?:^|[_-])A\d{2,3}(?:[_\.-]|$)',u):return False
 return bool(re.search(r'(?:^|[_-])R\d{2,3}(?:[_\.-]|$)',u))
def _is_audit_request(name:str)->bool:return bool(re.search(r'(?:^|[_-])A\d{2,3}(?:[_\.-]|$)',name.upper()))
def derive_phase(state:dict[str,str],requests:list[str],receipts:dict[str,dict[str,Any]])->tuple[str,str]:
 if state.get('active_milestone')=='M9':return 'HARD_STOP','M9_BOUNDARY_VIOLATION'
 names={Path(x).name for x in requests};pending=names-set(receipts)
 if any('CALIBRATION' in x.upper() for x in pending):return 'NATIVE_CALIBRATION_RUNNING','WAIT_AUTOMATICALLY'
 if any(_is_audit_request(x) for x in pending):return 'AUDIT_RUNNING','WAIT_AUTOMATICALLY'
 if any(_is_review_request(x) for x in pending):return 'REVIEW_RUNNING','WAIT_AUTOMATICALLY'
 return ('AUTONOMOUS_S003_CYCLE','RUN_AUTONOMOUS_CYCLE') if state.get('active_sprint')=='S003' else ('SPRINT_AUTOMATION','RUN_AUTONOMOUS_CYCLE')
def receipt_stats(receipts):
 ok=bad=0
 for d in receipts.values():
  job=d.get('job') if isinstance(d,dict) else None
  if isinstance(job,dict) and job.get('state')=='SUCCEEDED' and job.get('exit_code')==0:ok+=1
  else:bad+=1
 return ok,bad
def worker_alive_from_launchd()->bool:
 try:
  p=subprocess.run(['launchctl','print',f'gui/{os.getuid()}/com.aixion.mros-agent-worker'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=10,check=False);return p.returncode==0 and ('state = running' in p.stdout or 'state = active' in p.stdout)
 except Exception:return False
def worker_operational_health(state_root:Path)->tuple[bool,str,str|None]:
 path=state_root/'worker_health.json'
 if not path.is_file():return worker_alive_from_launchd(),'UNKNOWN',None
 try:d=json.loads(path.read_text(encoding='utf-8'))
 except Exception:return False,'INVALID_HEALTH','WORKER_HEALTH_UNREADABLE'
 age=time.time()-float(d.get('updated_at') or 0);status=str(d.get('status') or 'UNKNOWN');err=d.get('last_error')
 if age>120:return False,'STALE',f'WORKER_HEALTH_STALE:{int(age)}s'
 launchd=worker_alive_from_launchd();return bool(d.get('operational')) and status=='RUNNING' and launchd,status,err
def write_health(path:Path,h:Health)->None:
 h.updated_at=time.time();path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(asdict(h),sort_keys=True,indent=2)+'\n',encoding='utf-8');os.replace(tmp,path)
def run_cycle(repo:Path,state_root:Path)->tuple[int,str]:
 script=BRIDGE_ROOT/'scripts/mros/mros_autonomous_cycle.py'
 if not script.is_file():raise SupervisorError(f'SCRIPT_MISSING:{script}')
 p=subprocess.run([sys.executable,str(script),'--authority-repo',str(repo),'--queue-repo',str(QUEUE_WT),'--state-root',str(state_root)],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=7200,check=False)
 detail=(p.stdout or p.stderr or '').strip().splitlines()[-1:] or ['']
 if p.returncode not in (0,3):raise SupervisorError(f'AUTONOMOUS_CYCLE_FAILED:{p.returncode}:{detail[0]}')
 return p.returncode,detail[0]
def single_instance(lock_path:Path):
 lock_path.parent.mkdir(parents=True,exist_ok=True);h=lock_path.open('a+')
 try:fcntl.flock(h.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError as exc:h.close();raise SupervisorError('SUPERVISOR_ALREADY_RUNNING') from exc
 return h
def parse_args():
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,default=Path('/Users/madhuram/tradebot'));p.add_argument('--state-root',type=Path,default=Path('/Users/madhuram/.mros-agent-bridge/state'));p.add_argument('--poll-seconds',type=int,default=15);p.add_argument('--once',action='store_true');return p.parse_args()
def main()->int:
 a=parse_args();repo=a.repo.resolve();root=a.state_root.resolve();health_path=root/'supervisor_health.json';lock=single_instance(root/'supervisor.lock');h=Health()
 try:
  while True:
   try:
    fetch(repo);h.authority_head=ref(repo,f'origin/{AUTHORITY_BRANCH}');h.queue_head=ref(repo,f'origin/{QUEUE_BRANCH}')
    state=parse_program_state(read_at_ref(repo,f'origin/{AUTHORITY_BRANCH}','research/program/MROS_PROGRAM_STATE.yaml'));h.milestone=state.get('active_milestone','');h.work_package=state.get('active_work_package','');h.sprint=state.get('active_sprint','');h.runtime_authority=state.get('runtime_authority') or 'NONE';h.m9_started=h.milestone=='M9'
    req,rec=queue_inventory(repo);names={Path(x).name for x in req};h.pending_requests=len(names-set(rec));h.completed_receipts,h.failed_receipts=receipt_stats(rec);h.worker_alive,h.worker_status,h.worker_last_error=worker_operational_health(root);h.phase,h.next_action=derive_phase(state,req,rec)
    if h.m9_started:raise SupervisorError('M9_START_FORBIDDEN')
    if h.runtime_authority!='NONE':raise SupervisorError(f'RUNTIME_AUTHORITY_FORBIDDEN:{h.runtime_authority}')
    if not h.worker_alive and h.pending_requests>0:
     h.supervisor_status='HARD_STOP';h.phase='WORKER_BLOCKED';h.next_action='OPERATOR_ATTENTION';h.last_error=h.worker_last_error or f'WORKER_NOT_OPERATIONAL:{h.worker_status}';write_health(health_path,h)
    else:
     h.supervisor_status='RUNNING';h.last_error=None;write_health(health_path,h)
     # The controller owns repository progression. Pending jobs cause a benign
     # no-op/wait; completed populations are consumed without operator prompts.
     rc,detail=run_cycle(repo,root)
     h.next_action='WAIT_AUTOMATICALLY' if rc==3 else 'AUTONOMOUS_CYCLE_CONTINUE';h.last_error=None;write_health(health_path,h)
   except Exception as exc:
    h.supervisor_status='HARD_STOP';h.last_error=f'{type(exc).__name__}:{exc}';h.next_action='OPERATOR_ATTENTION';write_health(health_path,h)
    if a.once:return 2
    time.sleep(max(30,a.poll_seconds));continue
   if a.once:return 0
   time.sleep(max(5,a.poll_seconds))
 finally:
  fcntl.flock(lock.fileno(),fcntl.LOCK_UN);lock.close()
if __name__=='__main__':raise SystemExit(main())
