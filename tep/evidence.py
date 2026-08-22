"""M5 evidence, provenance, failure and relationship models."""
from __future__ import annotations
from dataclasses import dataclass,asdict
from hashlib import sha256
from pathlib import Path
import json
from .kernel import EvidenceRecord

class EvidenceError(RuntimeError):pass
class EvidenceIndex:
    def __init__(self):self._records={}
    def seal(self,r:EvidenceRecord,artifact_bytes:bytes|None=None):
        if not r.validator or r.validator==r.producer: raise EvidenceError('independent validator required')
        if artifact_bytes is not None and sha256(artifact_bytes).hexdigest()!=r.artifact_hash: raise EvidenceError('artifact hash mismatch')
        if r.evidence_id in self._records and self._records[r.evidence_id]!=r: raise EvidenceError('immutable evidence collision')
        self._records[r.evidence_id]=r; return r
    def get(self,id):return self._records[id]

@dataclass(frozen=True)
class FailureRecord:
    failure_id:str; subject:str; classification:str; mechanism:str; evidence_refs:tuple[str,...]; retryable:bool
@dataclass(frozen=True)
class Relationship:
    predecessor:str; successor:str; verdict:str; evidence_refs:tuple[str,...]
    def __post_init__(self):
        if self.verdict not in {'PROVEN_SUPERSEDES','PARTIAL_OVERLAP','PREDECESSOR_STILL_REQUIRED','UNKNOWN'}: raise ValueError('invalid relationship verdict')

class BlockerRouter:
    HUMAN={'TRUE_HUMAN_APPROVAL_REQUIRED'}
    def route(self,kind:str)->str:
        if kind in self.HUMAN:return 'HUMAN'
        if kind in {'CI_WAIT','TIMER_WAIT','EXTERNAL_RETRY'}:return 'WAIT'
        if kind in {'CANDIDATE_FAILURE','CONFLICT','STALE_BASE'}:return 'REPAIR'
        if kind in {'LIVE_EVIDENCE_REQUIRED'}:return 'LIVE_GATE'
        return 'PRESERVE_BLOCKED'
