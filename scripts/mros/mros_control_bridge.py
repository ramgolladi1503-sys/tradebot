#!/usr/bin/env python3
"""Non-certifying MROS control-job runner.

Separate from reviewer/auditor bridge by design. Jobs created here can propose,
build, repair, or validate, but can NEVER count as independent review/audit
quorum and can NEVER directly advance MROS authority.
"""
from __future__ import annotations
import hashlib,json,os,re,shutil,subprocess,time,uuid
from dataclasses import asdict,dataclass,field
from pathlib import Path
from typing import Any

SHA40=re.compile(r"^[0-9a-f]{40}$")
CONTROL_TYPES={"controller","builder","repairer","validator"}

class ControlJobError(RuntimeError): pass

@dataclass
class ControlJob:
    job_id:str; job_type:str; candidate_sha:str; packet_path:str; output_path:str
    state:str="QUEUED"; created_at:float=field(default_factory=time.time); started_at:float|None=None
    finished_at:float|None=None; exit_code:int|None=None; error_code:str|None=None; command_hash:str|None=None
    worktree_path:str|None=None
    def payload(self)->dict[str,Any]: return asdict(self)

class ControlBridge:
    def __init__(self,repo:Path,worktree_root:Path,state_root:Path,codex_bin:str="codex"):
        self.repo=repo.resolve(); self.worktree_root=worktree_root.resolve(); self.state_root=state_root.resolve(); self.codex_bin=codex_bin
        self.state_root.mkdir(parents=True,exist_ok=True); self.worktree_root.mkdir(parents=True,exist_ok=True)
        if not (self.repo/".git").exists(): raise ControlJobError("REPO_GIT_MARKER_MISSING")
        if shutil.which(codex_bin) is None: raise ControlJobError("CODEX_NOT_AVAILABLE")
    def _git(self,*args:str,timeout:int=180)->subprocess.CompletedProcess[str]:
        p=subprocess.run(["git",*args],cwd=self.repo,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout,check=False)
        if p.returncode!=0: raise ControlJobError(f"GIT_FAILED:{' '.join(args)}:{(p.stderr or p.stdout).strip()}")
        return p
    def _resolve(self,relative:str,must_exist:bool)->Path:
        p=(self.repo/relative).resolve()
        try:p.relative_to(self.repo)
        except ValueError as exc: raise ControlJobError("PATH_ESCAPE") from exc
        if must_exist and not p.is_file(): raise ControlJobError("PACKET_MISSING")
        if not must_exist:p.parent.mkdir(parents=True,exist_ok=True)
        return p
    def run(self,request:dict[str,Any])->ControlJob:
        typ=str(request.get("job_type") or ""); sha=str(request.get("candidate_sha") or "").lower(); packet=str(request.get("packet_path") or ""); output=str(request.get("output_path") or "")
        if typ not in CONTROL_TYPES: raise ControlJobError("CONTROL_JOB_TYPE_INVALID")
        if not SHA40.fullmatch(sha): raise ControlJobError("CANDIDATE_SHA_INVALID")
        packet_path=self._resolve(packet,True); output_path=self._resolve(output,False)
        if output_path.exists(): raise ControlJobError("OUTPUT_ALREADY_EXISTS")
        self._git("cat-file","-e",f"{sha}^{{commit}}")
        job=ControlJob(uuid.uuid4().hex,typ,sha,packet,output,state="RUNNING",started_at=time.time())
        wt=self.worktree_root/f"mros-{typ}-{job.job_id[:8]}"; job.worktree_path=str(wt)
        try:
            self._git("worktree","add","--detach",str(wt),sha)
            prompt=packet_path.read_text(encoding="utf-8")
            argv=[self.codex_bin,"exec","--ephemeral","--sandbox","workspace-write","-C",str(wt),"-o",str(output_path),prompt]
            job.command_hash=hashlib.sha256("\0".join(argv[:-1]).encode()).hexdigest()
            env={k:v for k,v in os.environ.items() if k in {"HOME","PATH","LANG","LC_ALL","TMPDIR","USER","LOGNAME","SHELL","TERM"}}
            env.update({"MROS_CONTROL_JOB":"1","MROS_JOB_TYPE":typ,"MROS_CANDIDATE_SHA":sha,"MROS_RUNTIME_AUTHORITY":"NONE","MROS_BROKER_ACTIONS_ALLOWED":"0"})
            p=subprocess.run(argv,cwd=wt,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=int(request.get("timeout_seconds") or 3600),check=False)
            (self.state_root/f"{job.job_id}.log").write_text(p.stdout or "",encoding="utf-8"); job.exit_code=p.returncode
            if p.returncode!=0: job.state="FAILED"; job.error_code="BACKEND_EXIT_NONZERO"
            elif not output_path.is_file() or output_path.stat().st_size==0: job.state="FAILED"; job.error_code="OUTPUT_MISSING"
            else: job.state="SUCCEEDED"
        except subprocess.TimeoutExpired:
            job.state="FAILED"; job.error_code="BACKEND_TIMEOUT"
        finally:
            subprocess.run(["git","worktree","remove","--force",str(wt)],cwd=self.repo,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
            shutil.rmtree(wt,ignore_errors=True); subprocess.run(["git","worktree","prune"],cwd=self.repo,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
            job.finished_at=time.time(); (self.state_root/f"{job.job_id}.json").write_text(json.dumps(job.payload(),sort_keys=True,indent=2)+"\n",encoding="utf-8")
        return job
