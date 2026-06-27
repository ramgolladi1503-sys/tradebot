from enum import Enum


class CandidateSourceStatus(Enum):
    """Status of the candidate loading from telemetry."""
    LOADED = "LOADED"
    MISSING_FIELDS = "MISSING_FIELDS"
    UNPARSABLE = "UNPARSABLE"


class ExecutionEligibility(Enum):
    """Whether the candidate was executable or rejected."""
    EXECUTABLE = "EXECUTABLE"
    REJECTED = "REJECTED"


class OutcomeStatus(Enum):
    """The resolved outcome of a candidate simulation."""
    TARGET_HIT = "TARGET_HIT"
    STOP_HIT = "STOP_HIT"
    AMBIGUOUS_BOTH_HIT = "AMBIGUOUS_BOTH_HIT"
    TIME_STOP = "TIME_STOP"
    NO_TRACE_DATA = "NO_TRACE_DATA"
    INSUFFICIENT_CANDIDATE_FIELDS = "INSUFFICIENT_CANDIDATE_FIELDS"
    OPEN_AT_END = "OPEN_AT_END"
    PENDING = "PENDING"


class ExitReason(Enum):
    """Reason for the exit."""
    TARGET = "TARGET"
    STOP = "STOP"
    TIME_STOP = "TIME_STOP"
    END_OF_WINDOW = "END_OF_WINDOW"
    UNKNOWN = "UNKNOWN"


class EvidenceQuality(Enum):
    """Overall quality of the evidence for a specific candidate."""
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    UNUSABLE = "UNUSABLE"


class ReplayDataReadiness(Enum):
    """Status of data required for replay."""
    READY = "READY"
    MISSING_OPTION_TRACE = "MISSING_OPTION_TRACE"
    MISSING_CANDIDATE_DATA = "MISSING_CANDIDATE_DATA"


class CostModelStatus(Enum):
    """Status of cost modeling data."""
    COMPLETE = "COMPLETE"
    ESTIMATED = "ESTIMATED"
    INCOMPLETE = "INCOMPLETE"


class ReplayRunStatus(Enum):
    """Overall status of a replay run."""
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
