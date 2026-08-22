"""M4 serial refreshed-main merge planning. Pure policy; mutation remains in GitHubService."""
from dataclasses import dataclass
@dataclass(frozen=True)
class MergeCandidate: pr:int; head:str; base:str; ci_green:bool; review_green:bool; draft:bool=False; do_not_merge:bool=False

def ready(c:MergeCandidate,current_main:str)->bool:return c.base==current_main and c.ci_green and c.review_green and not c.draft and not c.do_not_merge
class SerialMergeQueue:
    def __init__(self):self._ready={}
    def admit(self,c,current_main):
        if not ready(c,current_main):raise ValueError('candidate not merge-ready')
        self._ready[c.pr]=c
    def next(self):return self._ready[min(self._ready)] if self._ready else None
    def main_advanced(self,new_main):
        stale=tuple(sorted(self._ready));self._ready.clear();return stale
