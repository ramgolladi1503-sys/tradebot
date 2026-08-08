#!/usr/bin/env python3
"""Persistent MROS supervisor."""
from __future__ import annotations
import argparse,fcntl,json,os,re,subprocess,sys,time
from dataclasses import dataclass,asdict
from pathlib import Path
from typing import Any
AUTHORITY_BRANCH="research/mros-program-v1"; QUEUE_BRANCH="automation/mros-agent-queue-v1"
QUEUE_ROOT=Path("research/evidence/sprints/S003/agent_queue"); REQUEST_DIR=QUEUE_ROOT/"requests"; RECEIPT_DIR=QUEUE_ROOT/"receipts"
class SupervisorError(RuntimeError):pass
@dataclass
class Health:
    supervisor_status:str="STARTING"; phase:str="UNKNOWN"; authority_head:str=""; queue_head:str=""; milestone:str=""; work_package:str=""; sprint:str=""; pending_requests:int=0; completed_receipts:int=0; failed_receipts:int=0; worker_alive:bool=False; next_action:str="DISCOVER"; last_error:str|None=None; runtime_authority:str="NONE"; m9_started:bool=False; updated_at:float=0.0
def git(repo:Path,*args:str,timeout:int=180,check:bool=True)->subprocess.CompletedProcess[str]:
 p=subprocess.run(["git",*args],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout,check=False)
 if check and p.returncode!=0:raise SupervisorError(f"GIT_FAILED:{' '.join(args)}:{(p.stderr or p.stdout).strip()}")
 return p
def ref(repo:Path,name:str)->str:return git(repo,"rev-parse",name).stdout.strip()
def fetch(repo:Path)->None:git(repo,"fetch","origin",AUTHORITY_BRANCH,QUEUE_BRANCH)
def parse_program_state(text:str)->dict[str,str]:
 keys=("active_milestone","active_work_package","active_sprint","program_status","active_sprint_status");out={}
 for k in keys:
  m=re.search(rf"(?m)^{re.escape(k)}:\s*[\"']?([^\n\"']+)",text);out[k]=m.group(1).strip() if m else ""
 m=re.search(r"(?m)^\s*runtime_authority:\s*[\"']?([^\n\"']+)",text);out["runtime_authority"]=m.group(1).strip() if m else ""
 return out
def read_at_ref(repo:Path,git_ref:str,path:str)->str:return git(repo,"show",f"{git_ref}:{path}").stdout
def queue_inventory(repo:Path)->tuple[list[str],dict[str,dict[str,Any]]]:
 files=git(repo,"ls-tree","-r","--name-only",f"origin/{QUEUE_BRANCH}",str(QUEUE_ROOT)).stdout.splitlines();requests=[];receipts={}
 for p in files:
  if "/requests/" in p and p.endswith(".json"):requests.append(p)
  elif "/receipts/" in p and p.endswith(".json"):
   try:receipts[Path(p).name]=json.loads(read_at_ref(repo,f"origin/{QUEUE_BRANCH}",p))
   except Exception:receipts[Path(p).name]={"_invalid":True}
 return requests,receipts
def derive_phase(state:dict[str,str],requests:list[str],receipts:dict[str,dict[str,Any]])->tuple[str,str]:
 if state.get("active_milestone")=="M9":return "HARD_STOP","M9_BOUNDARY_VIOLATION"
 if state.get("active_sprint")!="S003":return "SPRINT_AUTOMATION","RUN_REPOSITORY_STEP"
 status=state.get("active_sprint_status","")
 if "R95_PENDING" in status:return "BOOTSTRAP_CALIBRATION_COMPLETE_CHECK","RUN_REPOSITORY_STEP"
 if "R002_REVIEW_PREPARATION" in status:return "BOOTSTRAP_R002_PREPARATION","RUN_REPOSITORY_STEP"
 names={Path(x).name for x in requests};done=set(receipts);pending=names-done
 if any("CALIBRATION" in x for x in pending):return "BOOTSTRAP_CALIBRATION_RUNNING","WAIT_FOR_CALIBRATION_RECEIPT"
 if any(re.match(r".*R\d+.*\.json$",x) and "CALIBRATION" not in x for x in pending):return "BOOTSTRAP_REVIEW_RUNNING","WAIT_FOR_REVIEW_QUORUM"
 if any(re.match(r".*A\d+.*\.json$",x) for x in pending):return "BOOTSTRAP_AUDIT_RUNNING","WAIT_FOR_AUDIT_QUORUM"
 return "BOOTSTRAP_TRANSITION_PENDING","RUN_REPOSITORY_STEP"
def receipt_stats(receipts:dict[str,dict[str,Any]])->tuple[int,int]:
 ok=bad=0
 for d in receipts.values():
  job=d.get("job") if isinstance(d,dict) else None
  if isinstance(job,dict) and job.get("state")=="SUCCEEDED" and job.get("exit_code")==0:ok+=1
  else:bad+=1
 return ok,bad
def worker_alive_from_launchd()->bool:
 try:
  p=subprocess.run(["launchctl","print",f"gui/{os.getuid()}/com.aixion.mros-agent-worker"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=10,check=False)
  return p.returncode==0 and ("state = running" in p.stdout or "state = active" in p.stdout)
 except Exception:return False
def write_health(path:Path,h:Health)->None:
 h.updated_at=time.time();path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(".tmp");tmp.write_text(json.dumps(asdict(h),sort_keys=True,indent=2)+"\n",encoding="utf-8");os.replace(tmp,path)
def run_step(repo:Path,step_script:Path,health_path:Path)->int:
 if not step_script.is_file():return 0
 p=subprocess.run([sys.executable,str(step_script),"--repo",str(repo),"--health",str(health_path),"--once"],cwd=repo,timeout=900,check=False);return p.returncode
def run_launcher(repo:Path)->int:
 script=Path('/Users/madhuram/.mros-agent-bridge/bridge/scripts/mros/mros_bootstrap_review_launcher.py');queue=Path('/Users/madhuram/.mros-agent-bridge/queue')
 if not script.is_file():return 0
 p=subprocess.run([sys.executable,str(script),"--authority-repo",str(repo),"--queue-repo",str(queue)],cwd=repo,timeout=900,check=False);return p.returncode
def single_instance(lock_path:Path):
 lock_path.parent.mkdir(parents=True,exist_ok=True);h=lock_path.open("a+")
 try:fcntl.flock(h.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError as exc:h.close();raise SupervisorError("SUPERVISOR_ALREADY_RUNNING") from exc
 return h
def parse_args():
 p=argparse.ArgumentParser();p.add_argument("--repo",type=Path,default=Path("/Users/madhuram/tradebot"));p.add_argument("--state-root",type=Path,default=Path("/Users/madhuram/.mros-agent-bridge/state"));p.add_argument("--poll-seconds",type=int,default=15);p.add_argument("--once",action="store_true");return p.parse_args()
def main()->int:
 a=parse_args();repo=a.repo.resolve();root=a.state_root.resolve();health_path=root/"supervisor_health.json";lock=single_instance(root/"supervisor.lock");h=Health()
 try:
  while True:
   try:
    fetch(repo);h.authority_head=ref(repo,f"origin/{AUTHORITY_BRANCH}");h.queue_head=ref(repo,f"origin/{QUEUE_BRANCH}")
    state=parse_program_state(read_at_ref(repo,f"origin/{AUTHORITY_BRANCH}","research/program/MROS_PROGRAM_STATE.yaml"));h.milestone=state.get("active_milestone","");h.work_package=state.get("active_work_package","");h.sprint=state.get("active_sprint","");h.runtime_authority=state.get("runtime_authority") or "NONE";h.m9_started=h.milestone=="M9"
    req,rec=queue_inventory(repo);names={Path(x).name for x in req};h.pending_requests=len(names-set(rec));h.completed_receipts,h.failed_receipts=receipt_stats(rec);h.worker_alive=worker_alive_from_launchd();h.phase,h.next_action=derive_phase(state,req,rec)
    if h.m9_started:raise SupervisorError("M9_START_FORBIDDEN")
    h.supervisor_status="RUNNING";h.last_error=None;write_health(health_path,h)
    if h.next_action=="RUN_REPOSITORY_STEP":
     rc=run_step(repo,repo/"scripts/mros/mros_supervisor_step.py",health_path)
     if rc not in (0,3):raise SupervisorError(f"SUPERVISOR_STEP_FAILED:{rc}")
     fetch(repo);state=parse_program_state(read_at_ref(repo,f"origin/{AUTHORITY_BRANCH}","research/program/MROS_PROGRAM_STATE.yaml"))
     if "R002_REVIEW_PREPARATION" in state.get("active_sprint_status",""):
      lrc=run_launcher(repo)
      if lrc not in (0,3):raise SupervisorError(f"R002_LAUNCH_FAILED:{lrc}")
   except Exception as exc:
    h.supervisor_status="HARD_STOP";h.last_error=f"{type(exc).__name__}:{exc}";h.next_action="OPERATOR_ATTENTION";write_health(health_path,h)
    if a.once:return 2
    time.sleep(max(30,a.poll_seconds));continue
   if a.once:return 0
   time.sleep(max(5,a.poll_seconds))
 finally:
  fcntl.flock(lock.fileno(),fcntl.LOCK_UN);lock.close()
if __name__=="__main__":raise SystemExit(main())
