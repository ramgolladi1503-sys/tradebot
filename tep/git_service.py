"""M4 bounded local Git driver; all mutations require a validated authority decision."""
from __future__ import annotations
from dataclasses import dataclass
import subprocess
from .authority import AuthorityContext,AuthorityEvaluator,ExecutionEnvelope,require_authority

class GitError(RuntimeError):pass
@dataclass(frozen=True)
class GitSnapshot:
    head:str; branch:str; porcelain:str
    @property
    def clean(self):return not bool(self.porcelain.strip())

class GitService:
    def __init__(self,repo:str,evaluator=None):self.repo=repo;self.evaluator=evaluator or AuthorityEvaluator()
    def _run(self,*args):
        p=subprocess.run(['git','-C',self.repo,*args],capture_output=True,text=True,check=False)
        if p.returncode:raise GitError(p.stderr.strip() or p.stdout.strip())
        return p.stdout.strip()
    def snapshot(self):return GitSnapshot(self._run('rev-parse','HEAD'),self._run('branch','--show-current'),self._run('status','--porcelain=v1'))
    def create_branch(self,name:str,ctx:AuthorityContext,expected_head:str):
        snap=self.snapshot()
        if snap.head!=expected_head:raise GitError('head drift')
        d=self.evaluator.evaluate('CREATE_BRANCH',ctx);require_authority(d,'CREATE_BRANCH',ctx.target_fingerprint)
        self._run('switch','-c',name);return self.snapshot(),d
    def push_branch(self,remote:str,branch:str,ctx:AuthorityContext,expected_head:str):
        if branch in {'main','master'}:raise GitError('protected branch push denied')
        snap=self.snapshot()
        if snap.head!=expected_head or snap.branch!=branch:raise GitError('branch/head drift')
        d=self.evaluator.evaluate('PUSH_BRANCH',ctx);require_authority(d,'PUSH_BRANCH',ctx.target_fingerprint)
        self._run('push',remote,f'{branch}:{branch}');return d
