from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CertificationPolicy:
    version: str = "backtest-certification-v1"
    allowed_engine: str = "core.option_backtest.engine.OptionBacktestEngine"
    allowed_wfa_engine: str = "core.option_backtest.wfa.run_option_replay_wfa"
    required_execution_mode: str = "REAL_EXECUTABLE_RESEARCH"
    required_bundle_schema: str = "1.0"
    minimum_trades: int = 100
    minimum_profit_factor: float = 1.0
    minimum_holdout_fraction: float = 0.20
    maximum_ambiguity_count: int = 0
    maximum_contamination_count: int = 0
    require_negative_controls: bool = True
    required_negative_controls: tuple[str, ...] = (
        "future_mutation",
        "timing_shift",
        "cost_sensitivity",
    )
    required_artifacts: tuple[str, ...] = (
        "dataset_manifest.json",
        "engine_identity.json",
        "run_configuration.json",
        "timing_evidence.json",
        "fill_evidence.json",
        "cost_reconciliation.json",
        "wfa_partition_plan.json",
        "wfa_results.json",
        "negative_controls.json",
        "test_results.json",
        "strategy_result.json",
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_policy() -> CertificationPolicy:
    return CertificationPolicy()
