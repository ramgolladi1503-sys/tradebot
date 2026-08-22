"""M2 persistent supervisor loop over durable state. Heartbeat is liveness, never progress."""
from __future__ import annotations
from dataclasses import dataclass
import os,time
from .kernel import TaskState,compute_runnable
@dataclass(frozen=True)
class TickResult: runnable:tuple[str,...]; expired_leases:int; heartbeat_ns:int
class Supervisor:
    def __init__(self,store,definition,owner,pid=None):self.store=store;self.definition=definition;self.owner=owner;self.pid=pid or os.getpid()
    def tick(self):
        expired=self.store.expire_leases()
        states=self.store.task_states()
        runnable=compute_runnable(self.definition,states)
        now=time.time_ns();self.store.heartbeat(self.owner,self.pid,now)
        return TickResult(runnable,expired,now)
    def run(self,stop,interval=1.0):
        while not stop():self.tick();time.sleep(interval)
