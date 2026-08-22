"""M3 capability registry and fail-closed authority evaluation."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping, Iterable
from .kernel import AuthorityDecision, canonical_hash

READ_CAPABILITIES={'READ_REPOSITORY','READ_GITHUB','READ_CI','READ_EVIDENCE','QUERY_KNOWLEDGE'}
MUTATION_CAPABILITIES={'CREATE_BRANCH','PUSH_BRANCH','UPDATE_PR_METADATA','CREATE_PR','MERGE_PR','CLOSE_PR','DELETE_LOCAL_PATH','SEAL_EVIDENCE','START_READ_ONLY_OBSERVER','ACCESS_PROTECTED_HOLDOUT','CERTIFY_STRUCTURAL_EDGE'}
TRADING_CAPABILITIES={'BROKER_WRITE','ORDER_ACTION','PAPER_EXECUTION','LIVE_EXECUTION'}
ALL_CAPABILITIES=READ_CAPABILITIES|MUTATION_CAPABILITIES|TRADING_CAPABILITIES

@dataclass(frozen=True)
class AuthorityContext:
    mission_id:str; task_id:str; actor:str; target_fingerprint:str; grants:frozenset[str]=frozenset(); constraints:Mapping[str,object]|None=None

class AuthorityEvaluator:
    def evaluate(self,capability:str,ctx:AuthorityContext)->AuthorityDecision:
        known=capability in ALL_CAPABILITIES
        allowed=known and capability in ctx.grants
        # trading never piggybacks on another grant
        if capability in TRADING_CAPABILITIES and capability not in ctx.grants: allowed=False
        did=canonical_hash({'capability':capability,'mission':ctx.mission_id,'task':ctx.task_id,'actor':ctx.actor,'target':ctx.target_fingerprint,'grants':sorted(ctx.grants)})[:24]
        return AuthorityDecision(did,capability,allowed,ctx.target_fingerprint,dict(ctx.constraints or {}))

def require_authority(decision:AuthorityDecision,capability:str,target_fingerprint:str)->None:
    if decision.capability!=capability or not decision.allowed or decision.target_fingerprint!=target_fingerprint: raise PermissionError(f'authority denied/stale: {capability}')

@dataclass(frozen=True)
class ExecutionEnvelope:
    task_id:str; task_fingerprint:str; capability:str; actor:str; allowed_paths:tuple[str,...]=(); prohibited_paths:tuple[str,...]=(); token_budget:int=0; time_budget_seconds:int=0
    def validate_path(self,path:str)->None:
        import os
        p=os.path.realpath(path)
        if any(p==os.path.realpath(x) or p.startswith(os.path.realpath(x)+os.sep) for x in self.prohibited_paths): raise PermissionError('protected path')
        if self.allowed_paths and not any(p==os.path.realpath(x) or p.startswith(os.path.realpath(x)+os.sep) for x in self.allowed_paths): raise PermissionError('out of scope')
