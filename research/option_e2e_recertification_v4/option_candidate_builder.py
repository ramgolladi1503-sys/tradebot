from __future__ import annotations

from dataclasses import dataclass

from .point_in_time_contract_universe import OptionContractMetadata
from .signal_contract import CanonicalSignal, Direction, map_direction_to_option_right


@dataclass(frozen=True)
class OptionCandidate:
    signal_id: str
    action: str
    contract: OptionContractMetadata | None
    rejection_reason: str | None


def build_long_option_candidate(signal: CanonicalSignal, contract: OptionContractMetadata | None) -> OptionCandidate:
    right = map_direction_to_option_right(signal.direction)
    if right is None:
        return OptionCandidate(signal_id=signal.signal_id, action="NO_TRADE", contract=None, rejection_reason=None)
    if contract is None:
        return OptionCandidate(
            signal_id=signal.signal_id,
            action="BUY",
            contract=None,
            rejection_reason="NO_RESOLVED_OPTION_CONTRACT",
        )
    if contract.option_right != right:
        raise ValueError("direction_option_type_mismatch")
    contract.validate_at(signal.signal_ts)
    return OptionCandidate(signal_id=signal.signal_id, action="BUY", contract=contract, rejection_reason=None)
