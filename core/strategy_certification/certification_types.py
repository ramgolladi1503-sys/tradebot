from enum import Enum, auto

class CertificationState(Enum):
    REJECTED = auto()
    RESEARCH_ONLY = auto()
    PAPER_ONLY = auto()
    SHADOW_ONLY = auto()
    PRODUCTION_CANDIDATE = auto()
    SUSPENDED = auto()
    REVOKED = auto()
    INSUFFICIENT_EVIDENCE = auto()

class GateStatus(Enum):
    PASS = auto()
    FAIL = auto()
    WARNING = auto()
    SKIP = auto()
