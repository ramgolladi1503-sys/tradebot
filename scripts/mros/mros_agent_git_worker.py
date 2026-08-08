#!/usr/bin/env python3
"""Mac-side Git mailbox worker for MROS isolated reviewer/auditor jobs."""
from __future__ import annotations
import argparse,fcntl,json,os,shutil,subprocess,sys,time
from pathlib import Path
from typing import Any
from mros_agent_bridge import BridgeError,MrosAgentBridge,load_config
QUEUE_ROOT=Path("research/evidence/sprints/S003/agent_queue"); REQUEST_DIR=QUEUE_ROOT/"requests"; RECEIPT_DIR=QUEUE_ROOT/"receipts"
MANIFEST_DIR=QUEUE_ROOT/"manifests"; MAX_INFRA_ATTEMPTS=3
ALLOWED_JOB_TYPES={"reviewer","auditor"}; DEFAULT_QUEUE_BRANCH="automation/mros-agent-queue-v1"; AUTHORITY_BRANCH="research/mros-program-v1"
CONTROLLER_RETRY_FIELDS={"transport_retry","controller_transport"}
class WorkerError(RuntimeError): pass

def run_git(repo:Path,*args:str,timeout:int=120,check:bool=True)->subprocess.CompletedProcess[str]:
    result=subprocess.run(["git",*args],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout,check=False)
    if check and result.returncode!=0: raise WorkerError(f"GIT_COMMAND_FAILED:{' '.join(args)}:{(result.stderr or result.stdout).strip()}")
    return result

def _declared_transport_paths(repo:Path)->set[str]:
    allowed=set(); d=repo/REQUEST_DIR
    if not d.exists(): return allowed
    for f in d.glob("*.json"):
        try: p=json.loads(f.read_text(encoding="utf-8"))
        except Exception: continue
        o=p.get("output_path")
        if isinstance(o,str) and o.strip(): allowed.add(o.strip())
        allowed.add((RECEIPT_DIR/f.name).as_posix())
    return allowed

def _status(repo:Path)->list[tuple[str,str]]:
    out=[]
    for line in run_git(repo,"status","--porcelain").stdout.splitlines():
        if not line.strip(): continue
        out.append((line[:2],line[3:] if len(line)>3 else ""))
    return out

def _write_worker_health(state_root:Path,*,status:str,error:str|None=None,processed:int=0)->None:
    path=state_root/"worker_health.json"; path.parent.mkdir(parents=True,exist_ok=True)
    payload={"status":status,"operational":status=="RUNNING","last_error":error,"processed_last_poll":processed,"updated_at":time.time(),"runtime_authority":"NONE","broker_actions_allowed":False}
    tmp=path.with_suffix(".tmp"); tmp.write_text(json.dumps(payload,sort_keys=True,indent=2)+"\n",encoding="utf-8"); os.replace(tmp,path)

def _single_instance(lock_path:Path):
    lock_path.parent.mkdir(parents=True,exist_ok=True); handle=lock_path.open("a+")
    try: fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close(); raise WorkerError("WORKER_ALREADY_RUNNING") from exc
    return handle

def _archive_transport_residue(repo:Path,state_root:Path,entries:list[tuple[str,str]])->Path:
    stamp=time.strftime("%Y%m%dT%H%M%S",time.gmtime()); root=state_root/"transport_recovery"/stamp
    for _,rel in entries:
        src=repo/rel
        if src.is_file():
            dst=root/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
    manifest=root/"MANIFEST.json"; manifest.parent.mkdir(parents=True,exist_ok=True)
    manifest.write_text(json.dumps({"archived_at":time.time(),"entries":[{"status":s,"path":p} for s,p in entries]},sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return root

def _recover_declared_transport_residue(repo:Path,state_root:Path,remote_branch:str)->None:
    allowed=_declared_transport_paths(repo); entries=_status(repo)
    if not entries:return
    blockers=[f"{s} {p}" for s,p in entries if p not in allowed]
    if blockers:raise WorkerError("QUEUE_WORKTREE_NOT_CLEAN:"+"|".join(blockers))
    _archive_transport_residue(repo,state_root,entries)
    for status,rel in entries:
        if status=="??":
            p=repo/rel
            if p.is_dir():shutil.rmtree(p)
            elif p.exists():p.unlink()
        else:run_git(repo,"restore","--staged","--worktree","--",rel,check=False)
    remaining=_status(repo)
    if remaining:raise WorkerError("QUEUE_TRANSPORT_RECOVERY_FAILED:"+"|".join(f"{s} {p}" for s,p in remaining))
    run_git(repo,"rebase",f"origin/{remote_branch}",timeout=180)
    local=run_git(repo,"rev-parse","HEAD").stdout.strip();remote=run_git(repo,"rev-parse",f"origin/{remote_branch}").stdout.strip()
    if local!=remote:
        run_git(repo,"push","origin",f"HEAD:{remote_branch}",timeout=180);run_git(repo,"fetch","origin",remote_branch,timeout=180)

def ensure_clean(repo:Path)->None:
    blockers=[f"{s} {p}" for s,p in _status(repo)]
    if blockers:raise WorkerError("QUEUE_WORKTREE_NOT_CLEAN:"+"|".join(blockers))

def sync_queue(repo:Path,state_root:Path,remote_branch:str)->None:
    run_git(repo,"fetch","origin",remote_branch,AUTHORITY_BRANCH,timeout=180)
    _recover_declared_transport_residue(repo,state_root,remote_branch);ensure_clean(repo);run_git(repo,"rebase",f"origin/{remote_branch}",timeout=180)

def list_requests(repo:Path)->list[Path]:
    d=repo/REQUEST_DIR;return [] if not d.exists() else sorted(p for p in d.glob("*.json") if p.is_file())
def receipt_path(repo:Path,request:Path)->Path:return repo/RECEIPT_DIR/request.name

def validate_request_payload(payload:Any)->dict[str,Any]:
    if not isinstance(payload,dict):raise WorkerError("REQUEST_OBJECT_REQUIRED")
    required={"job_type","role_id","candidate_sha","packet_path","output_path","backend"};missing=sorted(required-set(payload))
    if missing:raise WorkerError("REQUEST_FIELDS_MISSING:"+",".join(missing))
    if payload.get("job_type") not in ALLOWED_JOB_TYPES:raise WorkerError("REQUEST_JOB_TYPE_INVALID")
    allowed_meta={"schema_version","request_id","created_by","created_at"}|CONTROLLER_RETRY_FIELDS
    extras=sorted(set(payload)-(required|allowed_meta))
    if extras:raise WorkerError("REQUEST_FIELDS_UNKNOWN:"+",".join(extras))
    if "transport_retry" in payload:
        retry=payload.get("transport_retry")
        if not isinstance(retry,int) or isinstance(retry,bool) or retry<1 or retry>3:raise WorkerError("REQUEST_TRANSPORT_RETRY_INVALID")
    if "controller_transport" in payload:
        ctl=payload.get("controller_transport")
        if not isinstance(ctl,dict):raise WorkerError("REQUEST_CONTROLLER_TRANSPORT_INVALID")
        expected={"candidate_head","sprint","round","execution_role_id","packet_path","output_path","receipt_path"}
        if set(ctl)!=expected:raise WorkerError("REQUEST_CONTROLLER_TRANSPORT_FIELDS_INVALID")
        if ctl.get("candidate_head")!=payload.get("candidate_sha"):raise WorkerError("REQUEST_CONTROLLER_CANDIDATE_MISMATCH")
        if ctl.get("execution_role_id")!=payload.get("role_id"):raise WorkerError("REQUEST_CONTROLLER_ROLE_MISMATCH")
        if ctl.get("packet_path")!=payload.get("packet_path"):raise WorkerError("REQUEST_CONTROLLER_PACKET_MISMATCH")
        if ctl.get("output_path")!=payload.get("output_path"):raise WorkerError("REQUEST_CONTROLLER_OUTPUT_MISMATCH")
    return payload

def _read_json(path:Path)->dict[str,Any]|None:
    try:
        value=json.loads(path.read_text(encoding="utf-8"));return value if isinstance(value,dict) else None
    except Exception:return None

def _attempt_succeeded(repo:Path,request_path:Path,payload:dict[str,Any])->bool:
    rec=_read_json(receipt_path(repo,request_path));out=repo/str(payload.get("output_path", ""))
    if rec is None or not out.is_file() or out.stat().st_size==0:return False
    job=rec.get("job");return isinstance(job,dict) and job.get("state")=="SUCCEEDED" and job.get("exit_code")==0

def _frozen_roles(repo:Path)->list[tuple[str,str,str]]:
    roles=[]
    if not (repo/MANIFEST_DIR).is_dir():return roles
    for mp in sorted((repo/MANIFEST_DIR).glob("*.json")):
        m=_read_json(mp)
        if not m or m.get("job_type") not in ALLOWED_JOB_TYPES:continue
        candidate=m.get("candidate_head");job_type=m.get("job_type")
        if not isinstance(candidate,str):continue
        for member in m.get("members",[]):
            if isinstance(member,dict) and isinstance(member.get("execution_role_id"),str):roles.append((job_type,member["execution_role_id"],candidate))
    return roles

def _attempts(repo:Path,job_type:str,role_id:str,candidate:str)->list[tuple[Path,dict[str,Any]]]:
    found=[]
    for path in list_requests(repo):
        p=_read_json(path)
        if p and p.get("job_type")==job_type and p.get("role_id")==role_id and p.get("candidate_sha")==candidate:found.append((path,p))
    return found

def _enqueue_retry_for_role(repo:Path,remote_branch:str,job_type:str,role_id:str,candidate:str)->bool:
    attempts=_attempts(repo,job_type,role_id,candidate)
    if not attempts:return False
    if any(_attempt_succeeded(repo,path,p) for path,p in attempts):return False
    if any(not receipt_path(repo,path).is_file() for path,_ in attempts):return False
    if len(attempts)>=MAX_INFRA_ATTEMPTS:raise WorkerError(f"INFRA_RETRY_EXHAUSTED:{job_type}:{role_id}:{candidate[:8]}")
    original_path,original=attempts[0];original_packet=repo/str(original.get("packet_path",""))
    if not original_packet.is_file():raise WorkerError(f"RETRY_PACKET_MISSING:{role_id}")
    retry_no=len(attempts);stem=Path(str(original.get("output_path"))).stem;suffix=f"{stem}_RETRY{retry_no}"
    packet_rel=(QUEUE_ROOT/"packets"/f"{suffix}.md").as_posix();output_rel=(QUEUE_ROOT/"results"/f"{suffix}.json").as_posix();request_rel=(REQUEST_DIR/f"{suffix}.json").as_posix();receipt_rel=(RECEIPT_DIR/f"{suffix}.json").as_posix()
    packet=repo/packet_rel;request_path=repo/request_rel
    if packet.exists() or request_path.exists():return False
    packet.parent.mkdir(parents=True,exist_ok=True);packet.write_text(original_packet.read_text(encoding="utf-8")+f"\n\n## Infrastructure retry {retry_no}\nSame frozen role and candidate. Fresh isolated execution. Failed prior attempts are preserved and must not be treated as peer conclusions.\n",encoding="utf-8")
    retry=dict(original);retry["request_id"]=f"{original.get('request_id','mros')}-retry{retry_no}";retry["created_by"]="mros-agent-worker-retry";retry["packet_path"]=packet_rel;retry["output_path"]=output_rel
    ctl=retry.get("controller_transport")
    if isinstance(ctl,dict):
        ctl=dict(ctl);ctl["packet_path"]=packet_rel;ctl["output_path"]=output_rel;ctl["receipt_path"]=receipt_rel;retry["controller_transport"]=ctl
    request_path.parent.mkdir(parents=True,exist_ok=True);request_path.write_text(json.dumps(retry,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    files=[packet_rel,request_rel];run_git(repo,"add","--",*files);staged=set(run_git(repo,"diff","--cached","--name-only").stdout.splitlines())
    if staged!=set(files):run_git(repo,"reset");raise WorkerError("RETRY_COMMIT_SCOPE_VIOLATION")
    run_git(repo,"commit","-m",f"mros(S003): retry isolated {role_id} infrastructure failure [skip ci]")
    run_git(repo,"fetch","origin",remote_branch,timeout=180);run_git(repo,"rebase",f"origin/{remote_branch}",timeout=180);run_git(repo,"push","origin",f"HEAD:{remote_branch}",timeout=180)
    return True

def enqueue_needed_retries(repo:Path,remote_branch:str)->int:
    count=0
    for job_type,role_id,candidate in _frozen_roles(repo):
        if _enqueue_retry_for_role(repo,remote_branch,job_type,role_id,candidate):count+=1
    return count

def write_receipt(path:Path,*,request:dict[str,Any],record:dict[str,Any],worker_id:str)->None:
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps({"schema_version":1,"worker_id":worker_id,"request":request,"job":record,"runtime_authority":"NONE","broker_actions_allowed":False},sort_keys=True,indent=2)+"\n",encoding="utf-8")

def commit_and_push(repo:Path,remote_branch:str,paths:list[Path],message:str)->str:
    relative=[str(p.relative_to(repo)) for p in paths];run_git(repo,"add","--",*relative);staged=run_git(repo,"diff","--cached","--name-only").stdout.splitlines()
    if set(staged)!=set(relative):run_git(repo,"reset");raise WorkerError("COMMIT_SCOPE_VIOLATION")
    run_git(repo,"commit","-m",message);run_git(repo,"fetch","origin",remote_branch,timeout=180);run_git(repo,"rebase",f"origin/{remote_branch}",timeout=180);run_git(repo,"push","origin",f"HEAD:{remote_branch}",timeout=180);return run_git(repo,"rev-parse","HEAD").stdout.strip()

def process_one(repo:Path,remote_branch:str,bridge:MrosAgentBridge,request_file:Path,worker_id:str)->dict[str,Any]:
    receipt=receipt_path(repo,request_file)
    if receipt.exists():return {"request":request_file.name,"status":"ALREADY_RECEIPTED"}
    request=validate_request_payload(json.loads(request_file.read_text(encoding="utf-8")));record=bridge.submit(request)
    while True:
        current=bridge.get(record.job_id)
        if current.state in {"SUCCEEDED","FAILED","BLOCKED","CANCELLED"}:break
        time.sleep(2)
    write_receipt(receipt,request=request,record=current.public_dict(),worker_id=worker_id)
    if current.state!="SUCCEEDED":
        sha=commit_and_push(repo,remote_branch,[receipt],f"mros(S003): record failed isolated {request['role_id']} job [skip ci]");return {"request":request_file.name,"status":current.state,"job_id":current.job_id,"commit_sha":sha}
    output=repo/request["output_path"]
    if not output.is_file() or output.stat().st_size==0:raise WorkerError("OUTPUT_ARTIFACT_MISSING_BEFORE_COMMIT")
    sha=commit_and_push(repo,remote_branch,[output,receipt],f"mros(S003): record isolated {request['role_id']} job output [skip ci]");return {"request":request_file.name,"status":"SUCCEEDED","job_id":current.job_id,"commit_sha":sha}

def parse_args()->argparse.Namespace:
    p=argparse.ArgumentParser();p.add_argument("--config",required=True,type=Path);p.add_argument("--queue-branch",default=DEFAULT_QUEUE_BRANCH);p.add_argument("--poll-seconds",type=int,default=15);p.add_argument("--once",action="store_true");p.add_argument("--worker-id",default=os.environ.get("HOSTNAME") or "mros-mac-worker");return p.parse_args()

def main()->int:
    a=parse_args();c=load_config(a.config);repo=c.repo_root;lock=None
    try:lock=_single_instance(c.state_root/"worker.lock")
    except WorkerError as exc:
        _write_worker_health(c.state_root,status="BLOCKED",error=str(exc));print(json.dumps({"status":"WORKER_BLOCKED","error":f"WorkerError:{exc}"}),file=sys.stderr,flush=True);return 4
    bridge=MrosAgentBridge(c);_write_worker_health(c.state_root,status="RUNNING")
    print(json.dumps({"status":"WORKER_STARTING","queue_branch":a.queue_branch,"authority_branch":AUTHORITY_BRANCH,"worker_id":a.worker_id,"health":bridge.health()}),flush=True)
    try:
        while True:
            try:
                sync_queue(repo,c.state_root,a.queue_branch);retry_count=enqueue_needed_retries(repo,a.queue_branch)
                if retry_count:sync_queue(repo,c.state_root,a.queue_branch)
                processed=[]
                for r in list_requests(repo):
                    if receipt_path(repo,r).exists():
                        continue
                    try:
                        processed.append(process_one(repo,a.queue_branch,bridge,r,a.worker_id))
                    except (BridgeError,WorkerError,subprocess.TimeoutExpired,OSError,ValueError,json.JSONDecodeError) as exc:
                        processed.append({"request":r.name,"status":"REQUEST_REJECTED","error":f"{type(exc).__name__}:{exc}"})
                        print(json.dumps({"status":"REQUEST_REJECTED","request":r.name,"error":f"{type(exc).__name__}:{exc}"},sort_keys=True),file=sys.stderr,flush=True)
                _write_worker_health(c.state_root,status="RUNNING",processed=len(processed));print(json.dumps({"status":"POLL_COMPLETE","processed":processed,"retries_enqueued":retry_count},sort_keys=True),flush=True)
            except (BridgeError,WorkerError,subprocess.TimeoutExpired,OSError,ValueError,json.JSONDecodeError) as exc:
                _write_worker_health(c.state_root,status="BLOCKED",error=f"{type(exc).__name__}:{exc}");print(json.dumps({"status":"WORKER_BLOCKED","error":f"{type(exc).__name__}:{exc}"}),file=sys.stderr,flush=True)
                if a.once:return 2
            if a.once:return 0
            time.sleep(max(5,a.poll_seconds))
    finally:
        if lock is not None:fcntl.flock(lock.fileno(),fcntl.LOCK_UN);lock.close()
if __name__=="__main__":raise SystemExit(main())
