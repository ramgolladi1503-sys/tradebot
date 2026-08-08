#!/usr/bin/env python3
"""Deterministic, single-writer Git transition engine for MROS automation."""
from __future__ import annotations
import contextlib,fcntl,json,subprocess,time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
AUTHORITY_BRANCH="research/mros-program-v1"
ALLOWED_PREFIXES=("research/program/","research/evidence/","research/decisions/")
FORBIDDEN_TOKENS=("active_milestone: M9","M9: ACTIVE","runtime_authority: LIVE","runtime_authority: EXECUTION")
class TransitionError(RuntimeError):pass
@dataclass(frozen=True)
class TransitionResult:
    parent_sha:str;commit_sha:str;changed_paths:tuple[str,...];message:str

def _git(repo:Path,*args:str,timeout:int=180,check:bool=True)->subprocess.CompletedProcess[str]:
    p=subprocess.run(["git",*args],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout,check=False)
    if check and p.returncode!=0:raise TransitionError(f"GIT_FAILED:{' '.join(args)}:{(p.stderr or p.stdout).strip()}")
    return p
def _head(repo:Path)->str:return _git(repo,"rev-parse","HEAD").stdout.strip()
def _ensure_branch(repo:Path)->None:
    b=_git(repo,"rev-parse","--abbrev-ref","HEAD").stdout.strip()
    if b!=AUTHORITY_BRANCH:raise TransitionError(f"WRONG_AUTHORITY_BRANCH:{b}")
def _status_paths(repo:Path)->set[str]:
    out=set()
    for line in _git(repo,"status","--porcelain").stdout.splitlines():
        if not line.strip():continue
        raw=line[3:] if len(line)>3 else ""
        if " -> " in raw:raw=raw.split(" -> ",1)[1]
        out.add(raw)
    return out
def _ensure_only_declared_dirty(repo:Path,declared:set[str])->None:
    dirty=_status_paths(repo);extra=dirty-declared
    if extra:raise TransitionError("AUTHORITY_WORKTREE_HAS_UNRELATED_DIRT:"+"|".join(sorted(extra)))
def _check_path(path:str)->None:
    if not path or path.startswith("/") or ".." in Path(path).parts:raise TransitionError(f"INVALID_PATH:{path}")
    if not path.startswith(ALLOWED_PREFIXES):raise TransitionError(f"PATH_NOT_ALLOWLISTED:{path}")
def _check_boundary(path:Path)->None:
    if not path.is_file() or path.suffix.lower() not in {".yaml",".yml",".json",".md",".txt"}:return
    text=path.read_text(encoding="utf-8",errors="replace")
    for token in FORBIDDEN_TOKENS:
        if token in text:raise TransitionError(f"M9_OR_RUNTIME_BOUNDARY_VIOLATION:{token}")
@contextlib.contextmanager
def writer_lock(lock_path:Path):
    lock_path.parent.mkdir(parents=True,exist_ok=True)
    with lock_path.open("a+") as h:
        try:fcntl.flock(h.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise TransitionError("ANOTHER_SUPERVISOR_HOLDS_WRITER_LOCK") from exc
        try:yield
        finally:fcntl.flock(h.fileno(),fcntl.LOCK_UN)
def commit_transition(*,repo:Path,lock_path:Path,expected_parent:str,changed_paths:Iterable[str],message:str,push:bool=True)->TransitionResult:
    paths=tuple(dict.fromkeys(str(p) for p in changed_paths))
    if not paths:raise TransitionError("NO_CHANGED_PATHS")
    for p in paths:_check_path(p)
    declared=set(paths)
    with writer_lock(lock_path):
        _ensure_branch(repo);_ensure_only_declared_dirty(repo,declared);_git(repo,"fetch","origin",AUTHORITY_BRANCH)
        local=_head(repo);remote=_git(repo,"rev-parse",f"origin/{AUTHORITY_BRANCH}").stdout.strip()
        if local!=expected_parent or remote!=expected_parent:raise TransitionError(f"EXPECTED_PARENT_MISMATCH:local={local}:remote={remote}:expected={expected_parent}")
        for p in paths:_check_boundary(repo/p)
        _git(repo,"add","--",*paths)
        staged=tuple(x for x in _git(repo,"diff","--cached","--name-only").stdout.splitlines() if x)
        if set(staged)!=declared:
            _git(repo,"reset");raise TransitionError(f"COMMIT_SCOPE_VIOLATION:expected={paths}:staged={staged}")
        _git(repo,"commit","-m",message);commit_sha=_head(repo)
        if push:_git(repo,"push","origin",f"HEAD:{AUTHORITY_BRANCH}")
        return TransitionResult(expected_parent,commit_sha,paths,message)
def write_transition_record(path:Path,result:TransitionResult,transition_id:str)->None:
    payload={"schema_version":1,"transition_id":transition_id,"parent_sha":result.parent_sha,"commit_sha":result.commit_sha,"changed_paths":list(result.changed_paths),"message":result.message,"recorded_at_unix":time.time(),"runtime_authority":"NONE","m9_started":False}
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload,sort_keys=True,indent=2)+"\n",encoding="utf-8")
