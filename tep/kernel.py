"""TEP M1 pure kernel contracts bound to Phase-0 freeze 9cdc21b2270d924daaf860443e57f39df4b0cc93."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

PHASE0_FREEZE_SHA = "9cdc21b2270d924daaf860443e57f39df4b0cc93"
SCHEMA_VERSION = "tep.m1.v1"

class TruthValue(str, Enum):
    UNKNOWN = "UNKNOWN"
    MISSING = "MISSING"
    ZERO = "ZERO"
    PASS = "PASS"

class TaskState(str, Enum):
    PENDING="PENDING"; RUNNABLE="RUNNABLE"; LEASED="LEASED"; EXECUTING="EXECUTING"
    VALIDATING="VALIDATING"; WAITING="WAITING"; REPAIRABLE="REPAIRABLE"
    BLOCKED_HUMAN="BLOCKED_HUMAN"; BLOCKED_LIVE_EVIDENCE="BLOCKED_LIVE_EVIDENCE"
    SUCCEEDED="SUCCEEDED"; INVALIDATED="INVALIDATED"; FAILED_TERMINAL="FAILED_TERMINAL"

class MissionState(str, Enum):
    CREATED="CREATED"; VALIDATING="VALIDATING"; READY="READY"; RUNNING="RUNNING"
    WAITING="WAITING"; BLOCKED="BLOCKED"; COMPLETED="COMPLETED"; FAILED="FAILED"; CANCELLED="CANCELLED"

TASK_TRANSITIONS = {
    TaskState.PENDING:{TaskState.RUNNABLE,TaskState.INVALIDATED},
    TaskState.RUNNABLE:{TaskState.LEASED,TaskState.INVALIDATED,TaskState.BLOCKED_HUMAN,TaskState.BLOCKED_LIVE_EVIDENCE},
    TaskState.LEASED:{TaskState.EXECUTING,TaskState.RUNNABLE,TaskState.INVALIDATED},
    TaskState.EXECUTING:{TaskState.VALIDATING,TaskState.WAITING,TaskState.REPAIRABLE,TaskState.FAILED_TERMINAL},
    TaskState.VALIDATING:{TaskState.SUCCEEDED,TaskState.WAITING,TaskState.REPAIRABLE,TaskState.BLOCKED_HUMAN,TaskState.BLOCKED_LIVE_EVIDENCE,TaskState.FAILED_TERMINAL,TaskState.INVALIDATED},
    TaskState.WAITING:{TaskState.RUNNABLE,TaskState.VALIDATING,TaskState.INVALIDATED,TaskState.FAILED_TERMINAL},
    TaskState.REPAIRABLE:{TaskState.RUNNABLE,TaskState.WAITING,TaskState.BLOCKED_HUMAN,TaskState.FAILED_TERMINAL,TaskState.INVALIDATED},
    TaskState.BLOCKED_HUMAN:{TaskState.RUNNABLE,TaskState.INVALIDATED,TaskState.FAILED_TERMINAL},
    TaskState.BLOCKED_LIVE_EVIDENCE:{TaskState.RUNNABLE,TaskState.WAITING,TaskState.INVALIDATED},
    TaskState.SUCCEEDED:{TaskState.INVALIDATED}, TaskState.INVALIDATED:{TaskState.PENDING,TaskState.RUNNABLE},
    TaskState.FAILED_TERMINAL:set(),
}
MISSION_TRANSITIONS = {
    MissionState.CREATED:{MissionState.VALIDATING,MissionState.CANCELLED},
    MissionState.VALIDATING:{MissionState.READY,MissionState.FAILED,MissionState.CANCELLED},
    MissionState.READY:{MissionState.RUNNING,MissionState.CANCELLED},
    MissionState.RUNNING:{MissionState.WAITING,MissionState.BLOCKED,MissionState.COMPLETED,MissionState.FAILED,MissionState.CANCELLED},
    MissionState.WAITING:{MissionState.RUNNING,MissionState.BLOCKED,MissionState.FAILED,MissionState.CANCELLED},
    MissionState.BLOCKED:{MissionState.RUNNING,MissionState.FAILED,MissionState.CANCELLED},
    MissionState.COMPLETED:set(), MissionState.FAILED:set(), MissionState.CANCELLED:set(),
}

def transition_allowed(current: Enum, target: Enum) -> bool:
    table = TASK_TRANSITIONS if isinstance(current, TaskState) else MISSION_TRANSITIONS
    return target in table.get(current, set())

def require_transition(current: Enum, target: Enum) -> None:
    if not transition_allowed(current, target):
        raise ValueError(f"illegal transition: {current.value}->{target.value}")

def canonical_hash(value: Any) -> str:
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return sha256(raw).hexdigest()

@dataclass(frozen=True)
class TaskDefinition:
    task_id: str
    capability: str
    owner: str
    dependencies: tuple[str,...]=()
    retry_policy: Mapping[str,Any]=field(default_factory=dict)
    wait_policy: Mapping[str,Any]=field(default_factory=dict)
    terminal_contract: Mapping[str,Any]=field(default_factory=dict)

@dataclass(frozen=True)
class MissionDefinition:
    mission_id: str
    version: str
    tasks: tuple[TaskDefinition,...]
    completion_contract: Mapping[str,Any]
    schema_version: str=SCHEMA_VERSION

    @property
    def fingerprint(self)->str:
        return canonical_hash({"mission_id":self.mission_id,"version":self.version,"schema_version":self.schema_version,
            "tasks":[{"task_id":t.task_id,"capability":t.capability,"owner":t.owner,"dependencies":list(t.dependencies),"retry_policy":dict(t.retry_policy),"wait_policy":dict(t.wait_policy),"terminal_contract":dict(t.terminal_contract)} for t in self.tasks],"completion_contract":dict(self.completion_contract)})

@dataclass(frozen=True)
class MissionInstance:
    instance_id:str; definition_hash:str; state:MissionState=MissionState.CREATED; configuration_refs:tuple[str,...]=()
@dataclass(frozen=True)
class TaskInstance:
    instance_id:str; task_id:str; fingerprint:str; state:TaskState=TaskState.PENDING; attempt:int=0
@dataclass(frozen=True)
class WorkerExecution:
    execution_id:str; task_fingerprint:str; actor:str; result_ref:str; output_hash:str
@dataclass(frozen=True)
class AuthorityDecision:
    decision_id:str; capability:str; allowed:bool; target_fingerprint:str; constraints:Mapping[str,Any]=field(default_factory=dict); expiry:str|None=None
@dataclass(frozen=True)
class EventRecord:
    event_id:str; idempotency_key:str; event_type:str; subject:str; causal_refs:tuple[str,...]=(); payload:Mapping[str,Any]=field(default_factory=dict); schema_version:str=SCHEMA_VERSION
@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id:str; claim:str; producer:str; validator:str; source_authority:str; artifact_ref:str; artifact_hash:str; limitations:tuple[str,...]=()

def validate_mission(defn: MissionDefinition) -> None:
    if defn.schema_version != SCHEMA_VERSION: raise ValueError("unsupported schema version")
    if not defn.mission_id or not defn.version: raise ValueError("mission identity/version required")
    ids=[t.task_id for t in defn.tasks]
    if len(ids)!=len(set(ids)): raise ValueError("duplicate task id")
    known=set(ids)
    for t in defn.tasks:
        if not t.task_id or not t.capability or not t.owner: raise ValueError("task id/capability/owner required")
        unknown=set(t.dependencies)-known
        if unknown: raise ValueError(f"unknown dependencies for {t.task_id}: {sorted(unknown)}")
        if t.task_id in t.dependencies: raise ValueError(f"self dependency: {t.task_id}")
    # deterministic cycle detection
    visiting:set[str]=set(); visited:set[str]=set(); by_id={t.task_id:t for t in defn.tasks}
    def visit(node:str)->None:
        if node in visiting: raise ValueError("dependency cycle")
        if node in visited:return
        visiting.add(node)
        for dep in sorted(by_id[node].dependencies): visit(dep)
        visiting.remove(node); visited.add(node)
    for node in sorted(known): visit(node)

def compute_runnable(defn: MissionDefinition, states: Mapping[str,TaskState]) -> tuple[str,...]:
    validate_mission(defn)
    result=[]
    for task in sorted(defn.tasks,key=lambda t:t.task_id):
        state=states.get(task.task_id,TaskState.PENDING)
        if state not in {TaskState.PENDING,TaskState.RUNNABLE}: continue
        if all(states.get(dep) is TaskState.SUCCEEDED for dep in task.dependencies): result.append(task.task_id)
    return tuple(result)
