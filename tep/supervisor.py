"""M2/M3 persistent-supervisor primitives; process manager remains deployment-specific."""
from __future__ import annotations
import os,time
from dataclasses import dataclass
from .kernel import MissionDefinition,TaskState,compute_runnable
from .state import StateStore

@dataclass(frozen=True)
class SupervisorStatus:
    pid:int; heartbeat:float; runnable:tuple[str,...]; waiting:int

class Supervisor:
    def __init__(self,store:StateStore,heartbeat_interval=10.0): self.store=store; self.heartbeat_interval=heartbeat_interval; self.last_heartbeat=0.0
    def heartbeat(self): self.last_heartbeat=time.time(); return self.last_heartbeat
    def derive_runnable(self,definition:MissionDefinition,states:dict[str,TaskState]): return compute_runnable(definition,states)
    def status(self,definition:MissionDefinition,states:dict[str,TaskState]):
        runnable=self.derive_runnable(definition,states); waiting=sum(1 for s in states.values() if s is TaskState.WAITING)
        return SupervisorStatus(os.getpid(),self.heartbeat(),runnable,waiting)
    def recover_expired_leases(self,now=None):
        now=time.time() if now is None else now
        with self.store.tx() as c:
            rows=list(c.execute('SELECT task_instance_id FROM leases WHERE expires<=?',(now,)))
            c.execute('DELETE FROM leases WHERE expires<=?',(now,))
        return tuple(r['task_instance_id'] for r in rows)
