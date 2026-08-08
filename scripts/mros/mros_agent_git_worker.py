#!/usr/bin/env python3
"""Mac-side Git mailbox worker for MROS isolated reviewer/auditor jobs."""
from __future__ import annotations
import argparse,json,os,subprocess,sys,time
from pathlib import Path
from typing import Any
from mros_agent_bridge import BridgeError,MrosAgentBridge,load_config
QUEUE_ROOT=Path("research/evidence/sprints/S003/agent_queue"); REQUEST_DIR=QUEUE_ROOT/"requests"; RECEIPT_DIR=QUEUE_ROOT/"receipts"
ALLOWED_JOB_TYPES={"reviewer","auditor"}; DEFAULT_QUEUE_BRANCH="automation/mros-agent-queue-v1"; AUTHORITY_BRANCH="research/mros-program-v1"
class WorkerError(RuntimeError): pass
def run_git(repo:Path,*args:str,timeout:int=120,check:bool=True)->subprocess.CompletedProcess[str]:
    # stderr must stay separate: some local Git integrations emit benign warnings
    # (for example "Empty last update token") on stderr even when status succeeds.
    result=subprocess.run(["git",*args],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout,check=False)
    if check and result.returncode!=0: raise WorkerError(f"GIT_COMMAND_FAILED:{' '.join(args)}:{(result.stderr or result.stdout).strip()}")
    return result
def _declared_untracked_paths(repo:Path)->set[str]:
    allowed=set(); d=repo/REQUEST_DIR
    if not d.exists(): return allowed
    for f in d.glob("*.json"):
        try: p=json.loads(f.read_text(encoding="utf-8"))
        except Exception: continue
        o=p.get("output_path")
        if isinstance(o,str) and o.strip(): allowed.add(o.strip())
        allowed.add((RECEIPT_DIR/f.name).as_posix())
    return allowed
def ensure_clean(repo:Path)->None:
    lines=[x for x in run_git(repo,"status","--porcelain").stdout.splitlines() if x.strip()]
    allowed=_declared_untracked_paths(repo); blockers=[]
    for line in lines:
        status=line[:2]; path=line[3:] if len(line)>3 else ""
        if status=="??" and path in allowed: continue
        blockers.append(line)
    if blockers: raise WorkerError("QUEUE_WORKTREE_NOT_CLEAN:"+"|".join(blockers))
def sync_queue(repo:Path,remote_branch:str)->None:
    ensure_clean(repo); run_git(repo,"fetch","origin",remote_branch,AUTHORITY_BRANCH,timeout=180); run_git(repo,"rebase",f"origin/{remote_branch}",timeout=180)
def list_requests(repo:Path)->list[Path]:
    d=repo/REQUEST_DIR; return [] if not d.exists() else sorted(p for p in d.glob("*.json") if p.is_file())
def receipt_path(repo:Path,request:Path)->Path: return repo/RECEIPT_DIR/request.name
def validate_request_payload(payload:Any)->dict[str,Any]:
    if not isinstance(payload,dict): raise WorkerError("REQUEST_OBJECT_REQUIRED")
    required={"job_type","role_id","candidate_sha","packet_path","output_path","backend"}; missing=sorted(required-set(payload))
    if missing: raise WorkerError("REQUEST_FIELDS_MISSING:"+",".join(missing))
    if payload.get("job_type") not in ALLOWED_JOB_TYPES: raise WorkerError("REQUEST_JOB_TYPE_INVALID")
    extras=sorted(set(payload)-(required|{"schema_version","request_id","created_by","created_at"}))
    if extras: raise WorkerError("REQUEST_FIELDS_UNKNOWN:"+",".join(extras))
    return payload
def write_receipt(path:Path,*,request:dict[str,Any],record:dict[str,Any],worker_id:str)->None:
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps({"schema_version":1,"worker_id":worker_id,"request":request,"job":record,"runtime_authority":"NONE","broker_actions_allowed":False},sort_keys=True,indent=2)+"\n",encoding="utf-8")
def commit_and_push(repo:Path,remote_branch:str,paths:list[Path],message:str)->str:
    relative=[str(p.relative_to(repo)) for p in paths]; run_git(repo,"add","--",*relative); staged=run_git(repo,"diff","--cached","--name-only").stdout.splitlines()
    if set(staged)!=set(relative): run_git(repo,"reset"); raise WorkerError("COMMIT_SCOPE_VIOLATION")
    run_git(repo,"commit","-m",message); run_git(repo,"fetch","origin",remote_branch,timeout=180); run_git(repo,"rebase",f"origin/{remote_branch}",timeout=180); run_git(repo,"push","origin",f"HEAD:{remote_branch}",timeout=180); return run_git(repo,"rev-parse","HEAD").stdout.strip()
def process_one(repo:Path,remote_branch:str,bridge:MrosAgentBridge,request_file:Path,worker_id:str)->dict[str,Any]:
    receipt=receipt_path(repo,request_file)
    if receipt.exists(): return {"request":request_file.name,"status":"ALREADY_RECEIPTED"}
    request=validate_request_payload(json.loads(request_file.read_text(encoding="utf-8"))); record=bridge.submit(request)
    while True:
        current=bridge.get(record.job_id)
        if current.state in {"SUCCEEDED","FAILED","BLOCKED","CANCELLED"}: break
        time.sleep(2)
    write_receipt(receipt,request=request,record=current.public_dict(),worker_id=worker_id)
    if current.state!="SUCCEEDED":
        sha=commit_and_push(repo,remote_branch,[receipt],f"mros(S003): record failed isolated {request['role_id']} job [skip ci]"); return {"request":request_file.name,"status":current.state,"job_id":current.job_id,"commit_sha":sha}
    output=repo/request["output_path"]
    if not output.is_file() or output.stat().st_size==0: raise WorkerError("OUTPUT_ARTIFACT_MISSING_BEFORE_COMMIT")
    sha=commit_and_push(repo,remote_branch,[output,receipt],f"mros(S003): record isolated {request['role_id']} job output [skip ci]"); return {"request":request_file.name,"status":"SUCCEEDED","job_id":current.job_id,"commit_sha":sha}
def parse_args()->argparse.Namespace:
    p=argparse.ArgumentParser(); p.add_argument("--config",required=True,type=Path); p.add_argument("--queue-branch",default=DEFAULT_QUEUE_BRANCH); p.add_argument("--poll-seconds",type=int,default=15); p.add_argument("--once",action="store_true"); p.add_argument("--worker-id",default=os.environ.get("HOSTNAME") or "mros-mac-worker"); return p.parse_args()
def main()->int:
    a=parse_args(); c=load_config(a.config); repo=c.repo_root; bridge=MrosAgentBridge(c); print(json.dumps({"status":"WORKER_STARTING","queue_branch":a.queue_branch,"authority_branch":AUTHORITY_BRANCH,"worker_id":a.worker_id,"health":bridge.health()}),flush=True)
    while True:
        try:
            sync_queue(repo,a.queue_branch); processed=[]
            for r in list_requests(repo):
                if not receipt_path(repo,r).exists(): processed.append(process_one(repo,a.queue_branch,bridge,r,a.worker_id))
            print(json.dumps({"status":"POLL_COMPLETE","processed":processed},sort_keys=True),flush=True)
        except (BridgeError,WorkerError,subprocess.TimeoutExpired,OSError,ValueError,json.JSONDecodeError) as exc:
            print(json.dumps({"status":"WORKER_BLOCKED","error":f"{type(exc).__name__}:{exc}"}),file=sys.stderr,flush=True)
            if a.once:return 2
        if a.once:return 0
        time.sleep(max(5,a.poll_seconds))
if __name__=="__main__": raise SystemExit(main())
