"""M4 GitHub CLI driver with JIT target/head/base guards. No ambient authority."""
from __future__ import annotations
import json,subprocess
from .authority import AuthorityContext,AuthorityEvaluator,require_authority
class GitHubError(RuntimeError):pass
class GitHubService:
    def __init__(self,repo:str,evaluator=None):self.repo=repo;self.evaluator=evaluator or AuthorityEvaluator()
    def _run(self,*args):
        p=subprocess.run(['gh',*args,'--repo',self.repo],capture_output=True,text=True,check=False)
        if p.returncode:raise GitHubError(p.stderr.strip() or p.stdout.strip())
        return p.stdout.strip()
    def pr(self,n:int):return json.loads(self._run('pr','view',str(n),'--json','number,state,isDraft,headRefOid,baseRefOid,mergeable,reviewDecision,statusCheckRollup'))
    def _jit(self,n,head,base):
        p=self.pr(n)
        if p['state']!='OPEN' or p['headRefOid']!=head or p['baseRefOid']!=base:raise GitHubError('PR authority drift')
        return p
    def merge(self,n:int,head:str,base:str,ctx:AuthorityContext):
        p=self._jit(n,head,base);d=self.evaluator.evaluate('MERGE_PR',ctx);require_authority(d,'MERGE_PR',ctx.target_fingerprint)
        self._run('pr','merge',str(n),'--merge','--match-head-commit',head);return d
    def close(self,n:int,head:str,base:str,ctx:AuthorityContext):
        self._jit(n,head,base);d=self.evaluator.evaluate('CLOSE_PR',ctx);require_authority(d,'CLOSE_PR',ctx.target_fingerprint)
        self._run('pr','close',str(n));return d
