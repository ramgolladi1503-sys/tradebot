#!/usr/bin/env python3
"""Persistent MROS supervisor: autonomous through M8, hard-stop before M9."""
from __future__ import annotations
import argparse,fcntl,json,os,re,subprocess,sys,time
from dataclasses import dataclass,asdict
from pathlib import Path
from typing import Any
AUTHORITY_BRANCH='research/mros-program-v1';QUEUE_BRANCH='automation/mros-agent-queue-v1';QUEUE_ROOT=Path('research/evidence/sprints/S003/agent_queue');STATE=Path('research/program/MROS_PROGRAM_STATE.yaml');BRIDGE_ROOT=Path('/Users/madhuram/.mros-agent-bridge/bridge');AUTHORITY_WT=Path('/Users/madhuram/.mros-agent-bridge/authority');QUEUE_WT=Path('/Users/madhuram/.mros-agent-bridge/queue');CHECKPOINT_SECONDS=900
class SupervisorError(RuntimeError):pass
@dataclass
class Health:
 supervisor_status:str='STARTING';phase:str='UNKNOWN';authority_head:str='';queue_head:str='';milestone:str='';work_package:str='';sprint:str='';pending_requests:int=0;completed_receipts:int=0;failed_receipts:int=0;worker_alive:bool=False;worker_status:str='UNKNOWN';worker_last_error:str|None=None;next_action:str='DISCOVER';last_error:str|None=None;runtime_authority:str='NONE';m9_started:bool=False;updated_at:float=0.0

def git(repo:Path,*args:str,timeout:int=180,check=True):
 p=subprocess.run(['git',*args],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout,check=False)
 if check and p.returncode!=0:raise SupervisorError(f"GIT_FAILED:{' '.join(args)}:{(p.stderr or p.stdout).strip()}")
 return p
def ref(repo:Path,name:str):return git(repo,'rev-parse',name).stdout.strip()
def fetch(repo:Path):git(repo,'fetch','origin',AUTHORITY_BRANCH,QUEUE_BRANCH)
def parse_program_state(text:str)->dict[str,str]:
 out={}
 for k in ('active_milestone','active_work_package','active_sprint','program_status','active_sprint_status'):
  m=re.search(rf"(?m)^{re.escape(k)}:\s*[\"']?([^\n\"']+)",text);out[k]=m.group(1).strip() if m else ''
 m=re.search(r"(?m)^\s*runtime_authority:\s*[\"']?([^\n\"']+)",text);out['runtime_authority']=m.group(1).strip() if m else ''
 return out
def read_at_ref(repo:Path,git_ref:str,path:str):return git(repo,'show',f'{git_ref}:{path}').stdout
def queue_inventory(repo:Path):
 files=git(repo,'ls-tree','-r','--name-only',f'origin/{QUEUE_BRANCH}',str(QUEUE_ROOT)).stdout.splitlines();requests=[];receipts={}
 for p in files:
  if '/requests/' in p and p.endswith('.json'):requests.append(p)
  elif '/receipts/' in p and p.endswith('.json'):
   try:receipts[Path(p).name]=json.loads(read_at_ref(repo,f'origin/{QUEUE_BRANCH}',p))
   except Exception:receipts[Path(p).name]={'_invalid':True}
 return requests,receipts
def _is_review_request(name):
 u=name.upper()
 if 'CALIBRATION' in u:return False
 if re.search(r'(?:^|[_-])A\d{2,3}(?:[_\.-]|$)',u):return False
 return bool(re.search(r'(?:^|[_-])R\d{2,3}(?:[_\.-]|$)',u))
def _is_audit_request(name):return bool(re.search(r'(?:^|[_-])A\d{2,3}(?:[_\.-]|$)',name.upper()))
def derive_phase(state:dict[str,str],requests:list[str],receipts:dict[str,dict[str,Any]]):
 if state.get('active_milestone')=='M9' or state.get('program_status')=='M8_COMPLETE_M9_HARD_STOP':return 'HARD_STOP','M9_BOUNDARY_PRESERVED'
 if state.get('active_sprint_status')=='BOARD_BOOTSTRAP_AUTHORIZATION_PENDING':return 'S003_AUTHORIZATION','FINALIZE_AUTOMATICALLY'
 names={Path(x).name for x in requests};pending=names-set(receipts)
 if any('CALIBRATION' in x.upper() for x in pending):return 'NATIVE_CALIBRATION_RUNNING','WAIT_AUTOMATICALLY'
 if any(_is_audit_request(x) for x in pending):return 'AUDIT_RUNNING','WAIT_AUTOMATICALLY'
 if any(_is_review_request(x) for x in pending):return 'REVIEW_RUNNING','WAIT_AUTOMATICALLY'
 s=state.get('active_sprint','')
 if s=='S003':return 'AUTONOMOUS_S003_CYCLE','RUN_AUTONOMOUS_CYCLE'
 if re.fullmatch(r'S\d{3}',s) and 4<=int(s[1:])<=110:return 'AUTONOMOUS_PROGRAM_CYCLE','RUN_AUTONOMOUS_CYCLE'
 return 'HARD_STOP','UNSUPPORTED_PROGRAM_STATE'
def receipt_stats(receipts):
 ok=bad=0
 for d in receipts.values():
  job=d.get('job') if isinstance(d,dict) else None
  if isinstance(job,dict) and job.get('state')=='SUCCEEDED' and job.get('exit_code')==0:ok+=1
  else:bad+=1
 return ok,bad
def worker_alive_from_launchd():
 try:
  p=subprocess.run(['launchctl','print',f'gui/{os.getuid()}/com.aixion.mros-agent-worker'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=10,check=False);return p.returncode==0 and ('state = running' in p.stdout or 'state = active' in p.stdout)
 except Exception:return False
def worker_operational_health(root:Path):
 p=root/'worker_health.json'
 if not p.is_file():return worker_alive_from_launchd(),'UNKNOWN',None
 try:d=json.loads(p.read_text(encoding='utf-8'))
 except Exception:return False,'INVALID_HEALTH','WORKER_HEALTH_UNREADABLE'
 age=time.time()-float(d.get('updated_at') or 0);status=str(d.get('status') or 'UNKNOWN');err=d.get('last_error')
 if age>120:return False,'STALE',f'WORKER_HEALTH_STALE:{int(age)}s'
 return bool(d.get('operational')) and status=='RUNNING' and worker_alive_from_launchd(),status,err
def write_health(path:Path,h:Health):
 h.updated_at=time.time();path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(asdict(h),sort_keys=True,indent=2)+'\n',encoding='utf-8');os.replace(tmp,path)
def write_checkpoint(root:Path,h:Health,force:bool=False):
 now=time.time();bucket=int(now//CHECKPOINT_SECONDS);marker=root/'checkpoint_bucket';log=root/'supervisor_checkpoints.jsonl'
 try:last=int(marker.read_text(encoding='utf-8').strip()) if marker.is_file() else -1
 except Exception:last=-1
 if not force and last==bucket:return
 record=asdict(h);record['checkpointed_at']=now;record['checkpoint_bucket']=bucket
 root.mkdir(parents=True,exist_ok=True)
 with log.open('a',encoding='utf-8') as fh:fh.write(json.dumps(record,sort_keys=True,separators=(',',':'))+'\n')
 tmp=marker.with_suffix('.tmp');tmp.write_text(str(bucket)+'\n',encoding='utf-8');os.replace(tmp,marker)
def recover_authority_checkout(repo:Path,root:Path):
 status=git(repo,'status','--porcelain').stdout.strip()
 if not status:return None
 local=ref(repo,'HEAD');remote=ref(repo,f'origin/{AUTHORITY_BRANCH}')
 if git(repo,'merge-base','--is-ancestor',local,remote,check=False).returncode!=0:raise SupervisorError(f'AUTHORITY_DIRTY_AND_DIVERGED:local={local}:remote={remote}')
 label=f'MROS_AUTONOMOUS_RECOVERY_{int(time.time())}_{local[:8]}'
 p=git(repo,'stash','push','--include-untracked','-m',label,timeout=300,check=False)
 if p.returncode!=0:raise SupervisorError(f'AUTHORITY_RECOVERY_STASH_FAILED:{p.stderr or p.stdout}')
 if git(repo,'status','--porcelain').stdout.strip():raise SupervisorError('AUTHORITY_RECOVERY_DID_NOT_CLEAN_WORKTREE')
 stash=git(repo,'stash','list','-1','--format=%gd:%H:%s',check=False).stdout.strip();log=root/'authority_recovery.log';log.parent.mkdir(parents=True,exist_ok=True)
 with log.open('a',encoding='utf-8') as fh:fh.write(f'{time.time()} local={local} remote={remote} stash={stash} status={status!r}\n')
 git(repo,'merge','--ff-only',f'origin/{AUTHORITY_BRANCH}',timeout=300);return stash
def invoke(repo:Path,name:str,args:list[str],timeout=7200):
 script=BRIDGE_ROOT/'scripts/mros'/name
 if not script.is_file():raise SupervisorError(f'SCRIPT_MISSING:{script}')
 p=subprocess.run([sys.executable,str(script),*args],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout,check=False);detail=((p.stdout or p.stderr or '').strip().splitlines() or [''])[-1];return p.returncode,detail
def run_s003(repo:Path,root:Path):
 rc,d=invoke(repo,'mros_autonomous_cycle_v2.py',['--authority-repo',str(repo),'--queue-repo',str(QUEUE_WT),'--state-root',str(root)])
 if rc==2 and 'CALIBRATION_VALIDATION_FAILED' in d:rc,d=invoke(repo,'mros_calibration_failure_repair.py',['--authority-repo',str(repo),'--queue-repo',str(QUEUE_WT),'--state-root',str(root)])
 if rc not in (0,3):raise SupervisorError(f'S003_CYCLE_FAILED:{rc}:{d}')
 return rc,d
def run_finalizer(repo:Path):
 rc,d=invoke(repo,'mros_s003_autonomous_finalizer.py',['--authority-repo',str(repo),'--queue-repo',str(QUEUE_WT)])
 if rc not in (0,3):raise SupervisorError(f'S003_FINALIZER_FAILED:{rc}:{d}')
 return rc,d
def run_program(repo:Path,root:Path):
 rc,d=invoke(repo,'mros_post_bootstrap_cycle_v2.py',['--authority-repo',str(repo),'--queue-repo',str(QUEUE_WT),'--state-root',str(root)],timeout=10800)
 if rc not in (0,3):raise SupervisorError(f'PROGRAM_CYCLE_FAILED:{rc}:{d}')
 return rc,d
def single_instance(lock_path:Path):
 lock_path.parent.mkdir(parents=True,exist_ok=True);h=lock_path.open('a+')
 try:fcntl.flock(h.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError as exc:h.close();raise SupervisorError('SUPERVISOR_ALREADY_RUNNING') from exc
 return h
def parse_args():
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,default=AUTHORITY_WT);p.add_argument('--state-root',type=Path,default=Path('/Users/madhuram/.mros-agent-bridge/state'));p.add_argument('--poll-seconds',type=int,default=15);p.add_argument('--once',action='store_true');return p.parse_args()
def main():
 a=parse_args();repo=a.repo.resolve();root=a.state_root.resolve();hp=root/'supervisor_health.json';lock=single_instance(root/'supervisor.lock');h=Health()
 try:
  while True:
   try:
    fetch(repo);recover_authority_checkout(repo,root);h.authority_head=ref(repo,f'origin/{AUTHORITY_BRANCH}');h.queue_head=ref(repo,f'origin/{QUEUE_BRANCH}');st=parse_program_state(read_at_ref(repo,f'origin/{AUTHORITY_BRANCH}',str(STATE)));h.milestone=st.get('active_milestone','');h.work_package=st.get('active_work_package','');h.sprint=st.get('active_sprint','');h.runtime_authority=st.get('runtime_authority') or 'NONE';h.m9_started=h.milestone=='M9';req,rec=queue_inventory(repo);names={Path(x).name for x in req};h.pending_requests=len(names-set(rec));h.completed_receipts,h.failed_receipts=receipt_stats(rec);h.worker_alive,h.worker_status,h.worker_last_error=worker_operational_health(root);h.phase,h.next_action=derive_phase(st,req,rec)
    if h.runtime_authority!='NONE':raise SupervisorError(f'RUNTIME_AUTHORITY_FORBIDDEN:{h.runtime_authority}')
    if h.m9_started:raise SupervisorError('M9_START_FORBIDDEN')
    if h.phase=='HARD_STOP' and st.get('program_status')=='M8_COMPLETE_M9_HARD_STOP':h.supervisor_status='RUNNING';h.next_action='M8_COMPLETE_WAIT';h.last_error=None;write_health(hp,h);write_checkpoint(root,h)
    elif not h.worker_alive and h.pending_requests>0:h.supervisor_status='HARD_STOP';h.phase='WORKER_BLOCKED';h.next_action='OPERATOR_ATTENTION';h.last_error=h.worker_last_error or f'WORKER_NOT_OPERATIONAL:{h.worker_status}';write_health(hp,h);write_checkpoint(root,h,force=True)
    else:
     h.supervisor_status='RUNNING';h.last_error=None;write_health(hp,h);write_checkpoint(root,h)
     if st.get('active_sprint_status')=='BOARD_BOOTSTRAP_AUTHORIZATION_PENDING':rc,d=run_finalizer(repo)
     elif st.get('active_sprint')=='S003':rc,d=run_s003(repo,root)
     elif re.fullmatch(r'S\d{3}',st.get('active_sprint','')) and 4<=int(st['active_sprint'][1:])<=110:rc,d=run_program(repo,root)
     else:rc,d=3,'NO_AUTONOMOUS_ACTION'
     h.next_action='WAIT_AUTOMATICALLY' if rc==3 else 'AUTONOMOUS_CYCLE_CONTINUE';write_health(hp,h)
   except Exception as exc:
    h.supervisor_status='HARD_STOP';h.last_error=f'{type(exc).__name__}:{exc}';h.next_action='OPERATOR_ATTENTION';write_health(hp,h);write_checkpoint(root,h,force=True)
    if a.once:return 2
    time.sleep(max(30,a.poll_seconds));continue
   if a.once:return 0
   time.sleep(max(5,a.poll_seconds))
 finally:
  fcntl.flock(lock.fileno(),fcntl.LOCK_UN);lock.close()
if __name__=='__main__':raise SystemExit(main())
