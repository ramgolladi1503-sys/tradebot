"""Public facade for the local Tradebot worktree supervisor."""

from core.agent_supervisor_claims import (
    claim_contract,
    get_contract_status,
    release_contract,
)
from core.agent_supervisor_contract import (
    load_contract_file,
    normalize_supervisor_contract,
    preflight_contract,
    validate_contract_shape,
)
from core.agent_supervisor_evidence import (
    record_independent_review,
    verify_contract,
)
from core.agent_supervisor_types import (
    AGENT_SUPERVISOR_SCHEMA_VERSION,
    AcceptanceCommand,
    SupervisorContract,
    SupervisorResult,
    SupervisorState,
)

__all__ = [
    "AGENT_SUPERVISOR_SCHEMA_VERSION",
    "AcceptanceCommand",
    "SupervisorContract",
    "SupervisorResult",
    "SupervisorState",
    "claim_contract",
    "get_contract_status",
    "load_contract_file",
    "normalize_supervisor_contract",
    "preflight_contract",
    "record_independent_review",
    "release_contract",
    "validate_contract_shape",
    "verify_contract",
]
