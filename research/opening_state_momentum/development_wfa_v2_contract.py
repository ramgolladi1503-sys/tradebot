import json
import hashlib
from typing import Dict, List, Any
from dataclasses import dataclass
from pathlib import Path

CONTRACT_ID = "OPENING_STATE_MOMENTUM_DEVELOPMENT_WFA_V2"

FROZEN_INPUT_HASHES = {
    "development_outcome_labels.json": "e5e048da8e402b6464eb2c49753475f20e0bde5350d3b3053537403eb68de80c",
    "development_outcome_reconciliation.json": "a48485c0d6c1aba0b07efd36d6d46701aba3313f13e202d9b9fe4105d7417bee",
    "outcome_contract.json": "b5fe38367d9795386f6913a7240cb6ac2bbf4f1796415e80d9a9188207fc8c42",
    "outcome_oracle_comparison.json": "87fcf59f1d1a31d6166eafdf54ee7764d85c0950fe73eb6703ae6aba004dbdc5",
    "outcome_fingerprint_aggregate.json": "ecbbdb6b1a357f244c600e0cb97f6af9c6d4c12bd0024ee6604d572d7c911b55",
    "outcome_evidence_summary.json": "4805217ed43b057aa8e542e12e8e696b36147545e873331dc8d4564701bdf507"
}

PARTITION_HASH = "a129740a65d6e7d4046231a927ca0d211babb347538f2985d74c09b3ecb5cadc"

@dataclass
class WFAContractV2:
    contract_id: str = CONTRACT_ID
    frozen_input_hashes: Dict[str, str] = None
    partition_hash: str = PARTITION_HASH
    fold_algorithm: str = "Deterministic chronological equal-count partitioning (base, remainder = divmod(N, 5))"
    primary_scenario_bps: float = 0.0005  # 5 bps
    frozen_outcome_return_authority: str = "Use frozen fields: net_return_0bps, net_return_2bps, net_return_5bps, net_return_10bps. Gross must match."
    short_return_formula: str = "entry_price / exit_price - 1.0"
    long_return_formula: str = "exit_price / entry_price - 1.0"
    concentration_metrics_scenario: str = "Calculated exclusively at the primary scenario (5 bps)"
    deterministic_seeds: Dict[str, int] = None
    bootstrap_counts: int = 20000
    permutation_counts: int = 20000
    oracle_scope: str = "Independently recomputes fold assignment, outcomes, metrics, randomization controls with 0 mismatches"
    determinism_scope: str = "Parallel directory test verifying exact semantic hash matching for all 11 generated artifacts"
    verifier_requirements: str = "Strict read-only verification of all classification gates on the 5-bps scenario."
    holdout_prohibition: str = "Execution must abort if any holdout session or date is loaded"
    undefined_metric_representation: Dict[str, Any] = None
    numerical_tolerance: float = 1e-15
    classification_gates: Dict[str, str] = None

    def __post_init__(self):
        if self.frozen_input_hashes is None:
            self.frozen_input_hashes = FROZEN_INPUT_HASHES
        
        # Base seed is derived from the contract ID string
        base_hash = hashlib.sha256(self.contract_id.encode('utf-8')).hexdigest()
        base_seed = int(base_hash[:8], 16)
        
        if self.deterministic_seeds is None:
            self.deterministic_seeds = {
                "bootstrap": base_seed + 1,
                "direction_randomization": base_seed + 2,
                "chronological_permutation": base_seed + 3
            }
            
        if self.undefined_metric_representation is None:
            self.undefined_metric_representation = {"value": None, "reason": "undefined"}
            
        if self.classification_gates is None:
            self.classification_gates = {
                "DEVELOPMENT_EDGE_CANDIDATE": "total_outcomes=32 AND mean>0 AND median>0 AND profit_factor>1 AND (>=3 folds positive) AND (>=4 folds with >=4 trades) AND (top_1_contrib < 40%) AND (top_3_contrib < 70%) AND (actual_mean > inverted_mean) AND (p_value <= 0.10) [at 5 bps]",
                "DEVELOPMENT_EDGE_NOT_SUPPORTED": "Sample sufficient but edge conditions fail",
                "DEVELOPMENT_SAMPLE_TOO_SPARSE": "< 4 folds with >=4 outcomes OR total_outcomes < 30",
                "WFA_EVIDENCE_WITH_GAPS": "Artifacts do not reconcile OR determinism fails OR oracle mismatch OR holdout access OR verifier fails"
            }

def build_contract() -> Dict[str, Any]:
    import dataclasses
    return dataclasses.asdict(WFAContractV2())

def assign_folds(development_session_dates: List[str]) -> Dict[str, int]:
    sorted_dates = sorted(development_session_dates)
    total = len(sorted_dates)
    base, remainder = divmod(total, 5)
    
    mapping = {}
    current_idx = 0
    for fold in range(5):
        size = base + (1 if fold < remainder else 0)
        for _ in range(size):
            mapping[sorted_dates[current_idx]] = fold
            current_idx += 1
    return mapping

if __name__ == "__main__":
    print(json.dumps(build_contract(), indent=2))
