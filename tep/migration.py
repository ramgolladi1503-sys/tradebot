"""M10 migration classification and preservation-first planning."""
from dataclasses import dataclass
from enum import Enum
class MigrationDisposition(str,Enum): REUSE_VERIFIED='REUSE_VERIFIED'; REIMPLEMENT_REQUIRED='REIMPLEMENT_REQUIRED'; UNKNOWN_PROVENANCE='UNKNOWN_PROVENANCE'
@dataclass(frozen=True)
class MigrationCandidate:
    candidate_id:str; exact_hash:str|None; provenance:str|None; mapped_contracts:tuple[str,...]; tests_available:bool; unique_local_state:bool=False

def classify(c:MigrationCandidate)->MigrationDisposition:
    if not c.exact_hash or not c.provenance:return MigrationDisposition.UNKNOWN_PROVENANCE
    if c.unique_local_state:return MigrationDisposition.REIMPLEMENT_REQUIRED
    if c.mapped_contracts and c.tests_available:return MigrationDisposition.REUSE_VERIFIED
    return MigrationDisposition.REIMPLEMENT_REQUIRED

def deletion_allowed(disposition:MigrationDisposition,preservation_proven:bool)->bool:
    return disposition is MigrationDisposition.REUSE_VERIFIED and preservation_proven
