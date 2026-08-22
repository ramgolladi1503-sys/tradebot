"""M7 read-only live-observation planning/lifecycle contracts. No broker adapter is implemented here."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,time as dtime
from pathlib import Path
from typing import Iterable

@dataclass(frozen=True)
class LaunchPlan:
    session_date:str; source_sha:str; observation_tokens:tuple[int,...]; runtime_tokens:tuple[int,...]; runtime_root:str
    @property
    def union_tokens(self):return tuple(sorted(set(self.observation_tokens)|set(self.runtime_tokens)))
    @property
    def overlap_tokens(self):return tuple(sorted(set(self.observation_tokens)&set(self.runtime_tokens)))
    def validate(self):
        if not self.session_date or len(self.source_sha)<7:raise ValueError('dated plan/source SHA required')
        if not Path(self.runtime_root).is_absolute():raise ValueError('runtime root must be external/absolute')

@dataclass
class DurabilityCounters:
    accepted_depth:int=0; rejected_depth:int=0; accepted_runtime:int=0; rejected_runtime:int=0
    @property
    def degraded(self):return self.rejected_depth>0 or self.rejected_runtime>0
    def verdict(self):return 'SEALED_WITH_DURABILITY_CAVEATS' if self.degraded else 'SEALED'

def market_should_shutdown(now:datetime,close_time=dtime(15,30),drain_minutes=10)->bool:
    cutoff=now.replace(hour=close_time.hour,minute=close_time.minute,second=0,microsecond=0)
    return now>=cutoff
