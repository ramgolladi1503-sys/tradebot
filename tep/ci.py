"""M4 pure CI classification and worker-free wait policy."""
from enum import Enum
from dataclasses import dataclass
class CIClass(str,Enum): WAITING='WAITING'; PASS='PASS'; CANDIDATE_FAILURE='CANDIDATE_FAILURE'; BASELINE_FAILURE='BASELINE_FAILURE'; ENVIRONMENT_FAILURE='ENVIRONMENT_FAILURE'; EXTERNAL_FAILURE='EXTERNAL_FAILURE'; POLICY_FAILURE='POLICY_FAILURE'; UNKNOWN='UNKNOWN'
@dataclass(frozen=True)
class CIObservation:
    candidate_state:str; baseline_state:str|None=None; external:bool=False; environment:bool=False; policy:bool=False

def classify_ci(o:CIObservation)->CIClass:
    s=o.candidate_state.upper()
    if s in {'QUEUED','PENDING','IN_PROGRESS','WAITING'}: return CIClass.WAITING
    if s in {'SUCCESS','PASS','PASSED'}: return CIClass.PASS
    if o.policy:return CIClass.POLICY_FAILURE
    if o.external:return CIClass.EXTERNAL_FAILURE
    if o.environment:return CIClass.ENVIRONMENT_FAILURE
    if o.baseline_state and o.baseline_state.upper() in {'FAIL','FAILED','FAILURE'}: return CIClass.BASELINE_FAILURE
    if s in {'FAIL','FAILED','FAILURE','ERROR'}: return CIClass.CANDIDATE_FAILURE
    return CIClass.UNKNOWN

def worker_required(classification:CIClass)->bool: return classification in {CIClass.CANDIDATE_FAILURE,CIClass.POLICY_FAILURE}
