from __future__ import annotations

from dataclasses import dataclass

from .composite_contract_authority import QuoteContractEvidence
from .signal_contract import OptionRight


@dataclass(frozen=True)
class ObservedUniverse:
    decision_ts: str
    option_right: OptionRight
    contracts: tuple[QuoteContractEvidence, ...]
    completeness_score: float
    universe_label: str

    def validate(self, *, min_completeness: float) -> None:
        if not self.contracts:
            raise ValueError("observed_universe_empty")
        if any(contract.option_right != self.option_right for contract in self.contracts):
            raise ValueError("observed_universe_wrong_option_right")
        if not (0.0 <= self.completeness_score <= 1.0):
            raise ValueError("invalid_universe_completeness_score")
        if self.completeness_score < min_completeness:
            raise ValueError("observed_universe_incomplete")
