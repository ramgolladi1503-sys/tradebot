"""M7 read-only observer lifecycle. Adapter must expose subscribe/read/close and no order methods."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json,time
from .live import LaunchPlan,derive_subscriptions
class LiveObserverError(RuntimeError):pass
@dataclass(frozen=True)
class ObserverResult: session_id:str; messages:int; output_path:str; graceful:bool
class ReadOnlyObserver:
    def __init__(self,adapter):
        forbidden={'place_order','modify_order','cancel_order','orders_write'}
        if any(hasattr(adapter,x) for x in forbidden):raise LiveObserverError('adapter exposes trading mutation')
        self.adapter=adapter
    def run(self,plan:LaunchPlan,candidates,output_root:str,stop):
        subs=derive_subscriptions(plan,candidates);root=Path(output_root);root.mkdir(parents=True,exist_ok=True)
        path=root/f'{plan.session_id}.jsonl';count=0;graceful=False
        self.adapter.subscribe(subs)
        try:
            with path.open('a',encoding='utf-8') as f:
                while not stop():
                    msg=self.adapter.read();
                    if msg is None:continue
                    f.write(json.dumps({'ts_ns':time.time_ns(),'payload':msg},sort_keys=True)+'\n');f.flush();count+=1
            graceful=True
        finally:self.adapter.close()
        return ObserverResult(plan.session_id,count,str(path),graceful)
