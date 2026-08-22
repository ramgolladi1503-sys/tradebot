"""M10 provenance-first migration planning."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
@dataclass(frozen=True)
class MigrationItem: source:str; sha256:str; disposition:str; target:str|None=None; rollback_ref:str|None=None
class MigrationPlanner:
    VALID={'REUSE_VERIFIED','REIMPLEMENT_REQUIRED','UNKNOWN_PROVENANCE'}
    def inspect(self,path,disposition,target=None,rollback_ref=None):
        if disposition not in self.VALID:raise ValueError('invalid disposition')
        p=Path(path);h=sha256(p.read_bytes()).hexdigest() if p.is_file() else ''
        if disposition=='REUSE_VERIFIED' and (not h or not rollback_ref):raise ValueError('reuse requires hash and rollback')
        return MigrationItem(str(p),h,disposition,target,rollback_ref)
