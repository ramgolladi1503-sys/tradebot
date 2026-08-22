"""M3 bounded worker execution. Workers never decide platform truth or authority."""
from __future__ import annotations
from dataclasses import dataclass
import subprocess,time
from .authority import ExecutionEnvelope
from .kernel import WorkerExecution,canonical_hash

@dataclass(frozen=True)
class WorkerResult:
    execution:WorkerExecution; returncode:int; stdout:str; stderr:str; timed_out:bool=False

class SubprocessWorker:
    def run(self,command:list[str],env:ExecutionEnvelope)->WorkerResult:
        if not command: raise ValueError('command required')
        if env.time_budget_seconds<=0: raise ValueError('positive time budget required')
        eid=canonical_hash({'task':env.task_id,'fp':env.task_fingerprint,'cmd':command,'actor':env.actor})[:24]
        try:
            p=subprocess.run(command,capture_output=True,text=True,timeout=env.time_budget_seconds,check=False)
            out,err,rc,to=p.stdout,p.stderr,p.returncode,False
        except subprocess.TimeoutExpired as e:
            out=(e.stdout or '') if isinstance(e.stdout,str) else '';err=(e.stderr or '') if isinstance(e.stderr,str) else '';rc=124;to=True
        payload={'rc':rc,'stdout':out,'stderr':err,'timed_out':to}
        ex=WorkerExecution(eid,env.task_fingerprint,env.actor,f'worker:{eid}',canonical_hash(payload))
        return WorkerResult(ex,rc,out,err,to)
