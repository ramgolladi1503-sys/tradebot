import json
import hashlib
from typing import Dict, List, Set, Any
from dataclasses import dataclass
from pathlib import Path

CONTRACT_ID = "OPENING_STATE_MOMENTUM_DEVELOPMENT_WFA_V1"
STRATEGY_ID = "REGIME_CONDITIONED_OPENING_STATE_MOMENTUM_V1"
STRATEGY_VERSION = "1.0.0"
OUTCOME_CONTRACT_ID = "OPENING_STATE_MOMENTUM_FIXED_30M_OUTCOME_V1"
OUTCOME_CONTRACT_HASH = "b5fe38367d9795386f6913a7240cb6ac2bbf4f1796415e80d9a9188207fc8c42"

FROZEN_INPUT_HASHES = {
    "development_outcome_labels.json": "e5e048da8e402b6464eb2c49753475f20e0bde5350d3b3053537403eb68de80c",
    "development_outcome_reconciliation.json": "a48485c0d6c1aba0b07efd36d6d46701aba3313f13e202d9b9fe4105d7417bee",
    "outcome_contract.json": "b5fe38367d9795386f6913a7240cb6ac2bbf4f1796415e80d9a9188207fc8c42",
    "outcome_oracle_comparison.json": "87fcf59f1d1a31d6166eafdf54ee7764d85c0950fe73eb6703ae6aba004dbdc5",
    "outcome_fingerprint_aggregate.json": "ecbbdb6b1a357f244c600e0cb97f6af9c6d4c12bd0024ee6604d572d7c911b55",
    "outcome_evidence_summary.json": "4805217ed43b057aa8e542e12e8e696b36147545e873331dc8d4564701bdf507"
}

PARTITION_HASH = "ee6ffbdc428c81c1edbd7444544dade9c233b72eccef62e8de65fcff3a572cf8"

# WFA Configuration
NUM_FOLDS = 5
FRICTION_SCENARIOS = [0.0, 0.0002, 0.0005, 0.0010]  # 0, 2, 5, 10 bps
BOOTSTRAP_RESAMPLES = 20000

@dataclass
class WFAContract:
    contract_id: str = CONTRACT_ID
    strategy_id: str = STRATEGY_ID
    strategy_version: str = STRATEGY_VERSION
    outcome_contract_id: str = OUTCOME_CONTRACT_ID
    outcome_contract_hash: str = OUTCOME_CONTRACT_HASH
    frozen_input_hashes: Dict[str, str] = None
    partition_hash: str = PARTITION_HASH
    development_only_assertion: bool = True
    holdout_access_prohibition: bool = True
    fold_construction_algorithm: str = "Deterministic chronological equal-count partitioning (base, remainder = divmod(N, 5))"
    friction_scenarios: List[float] = None
    metric_definitions: List[str] = None
    confidence_interval_method: str = "Deterministic non-parametric bootstrap (20000 resamples)"
    negative_control_definitions: List[str] = None
    classification_gates: Dict[str, str] = None
    deterministic_seeds: Dict[str, int] = None
    numerical_tolerances: Dict[str, float] = None
    artifact_schema_versions: Dict[str, str] = None

    def __post_init__(self):
        if self.frozen_input_hashes is None:
            self.frozen_input_hashes = FROZEN_INPUT_HASHES
        if self.friction_scenarios is None:
            self.friction_scenarios = FRICTION_SCENARIOS
        if self.metric_definitions is None:
            self.metric_definitions = [
                "trade_count", "positive_return_count", "negative_return_count", "zero_return_count",
                "mean_return", "median_return", "standard_deviation", "standard_error",
                "minimum", "maximum", "25th_percentile", "75th_percentile",
                "win_rate", "wilson_95_win_rate_interval", "average_winner", "average_loser",
                "payoff_ratio", "profit_factor", "expectancy",
                "cumulative_arithmetic_return", "cumulative_compounded_return",
                "maximum_drawdown", "longest_winning_streak", "longest_losing_streak"
            ]
        if self.negative_control_definitions is None:
            self.negative_control_definitions = [
                "Direction inversion (LONG <-> SHORT) at 0, 2, 5, 10 bps",
                "Direction randomization null (preserve counts, random permute, 20000 iterations)",
                "Chronological concentration control (random permute path, 20000 iterations)"
            ]
        if self.classification_gates is None:
            self.classification_gates = {
                "DEVELOPMENT_EDGE_CANDIDATE": "total_outcomes=32 AND mean>0 AND median>0 AND profit_factor>1 AND (>=3 folds positive) AND (>=4 folds with >=4 trades) AND (top_1_contrib < 40%) AND (top_3_contrib < 70%) AND (actual_mean > inverted_mean) AND (p_value <= 0.10) [at 5 bps]",
                "DEVELOPMENT_EDGE_NOT_SUPPORTED": "Sample sufficient but edge conditions fail",
                "DEVELOPMENT_SAMPLE_TOO_SPARSE": "< 4 folds with >=4 outcomes OR total_outcomes < 30",
                "WFA_EVIDENCE_WITH_GAPS": "Artifacts do not reconcile OR determinism fails OR oracle mismatch OR holdout access OR verifier fails"
            }
        
        # We need a stable base for seeds. We use the contract ID string hash.
        base_hash = hashlib.sha256(self.contract_id.encode('utf-8')).hexdigest()
        base_seed = int(base_hash[:8], 16)
        
        if self.deterministic_seeds is None:
            self.deterministic_seeds = {
                "bootstrap": base_seed + 1,
                "direction_randomization": base_seed + 2,
                "chronological_permutation": base_seed + 3
            }
        if self.numerical_tolerances is None:
            self.numerical_tolerances = {
                "general": 1e-9
            }
        if self.artifact_schema_versions is None:
            self.artifact_schema_versions = {
                "development_wfa_contract": "1.0.0",
                "development_wfa_fold_assignments": "1.0.0",
                "development_wfa_metrics": "1.0.0",
                "development_wfa_temporal_stability": "1.0.0",
                "development_wfa_negative_controls": "1.0.0",
                "development_wfa_bootstrap": "1.0.0"
            }

def build_contract() -> Dict[str, Any]:
    c = WFAContract()
    # serialize dataclass
    import dataclasses
    return dataclasses.asdict(c)

def assign_folds(development_session_dates: List[str]) -> Dict[str, int]:
    """
    Sorts dates chronologically and assigns to 5 folds.
    Returns mapping from date string to fold ID (0-4).
    """
    sorted_dates = sorted(development_session_dates)
    total = len(sorted_dates)
    base, remainder = divmod(total, NUM_FOLDS)
    
    mapping = {}
    current_idx = 0
    for fold in range(NUM_FOLDS):
        size = base + (1 if fold < remainder else 0)
        for _ in range(size):
            mapping[sorted_dates[current_idx]] = fold
            current_idx += 1
    return mapping

if __name__ == "__main__":
    print(json.dumps(build_contract(), indent=2))
