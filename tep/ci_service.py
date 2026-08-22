"""M4 CI reconciliation: polling is read-only, waits are passive, repair requires terminal classification."""
from dataclasses import dataclass
import time
from .ci import CIObservation,CIClass,classify_ci,worker_required
@dataclass(frozen=True)
class CIResult: classification:CIClass; polls:int; terminal:bool
class CIReconciler:
 def __init__(self,reader,sleep=time.sleep):self.reader=reader;self.sleep=sleep
 def wait_terminal(self,head,baseline=None,interval=30,max_polls=60):
  for n in range(1,max_polls+1):
   raw=self.reader(head);obs=CIObservation(raw['state'],raw.get('baseline_state'),raw.get('external',False),raw.get('environment',False),raw.get('policy',False));cl=classify_ci(obs)
   if cl!=CIClass.WAITING:return CIResult(cl,n,True)
   if n<max_polls:self.sleep(interval)
  return CIResult(CIClass.UNKNOWN,max_polls,False)
 def repair_allowed(self,result):return result.terminal and worker_required(result.classification)
