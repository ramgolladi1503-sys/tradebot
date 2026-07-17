from __future__ import annotations

from typing import Any

from agentic_research.contracts import CertificationDecision, ToolResult


class DeterministicCertificationJudge:
    """Non-LLM authority. The manager and critic cannot override this decision."""

    def __init__(self, gates: dict[str, Any]):
        self.gates = dict(gates)

    def decide(self, results: dict[str, ToolResult]) -> CertificationDecision:
        hashes = {name: result.result_hash or "" for name, result in results.items()}

        contract = results.get("get_strategy_contract")
        if contract is None or contract.status != "SUCCESS":
            return self._decision("REJECTED_CONTRACT_MISMATCH", ["strategy_contract_not_proven"], hashes)

        dataset = results.get("validate_dataset")
        if dataset is None or dataset.status != "SUCCESS" or dataset.blockers:
            reasons = dataset.blockers if dataset else ["dataset_evidence_missing"]
            return self._decision("REJECTED_DATA_INELIGIBLE", reasons, hashes)

        temporal = results.get("run_temporal_semantics_tests")
        if temporal is None or temporal.status != "SUCCESS":
            return self._decision("REJECTED_CAUSAL_VIOLATION", ["temporal_semantics_not_proven"], hashes)
        violations = int(temporal.payload.get("causality_violations", 0))
        if violations > int(self.gates.get("maximum_causality_violations", 0)):
            return self._decision("REJECTED_CAUSAL_VIOLATION", [f"causality_violations:{violations}"], hashes)

        baseline = results.get("run_structural_backtest")
        if baseline is None or baseline.status != "SUCCESS":
            return self._decision("REJECTED_NO_EDGE", ["baseline_not_completed"], hashes)
        total_trades = int(baseline.payload.get("trades", 0))
        if total_trades < int(self.gates.get("minimum_total_trades", 0)):
            return self._decision("REJECTED_NO_EDGE", [f"insufficient_total_trades:{total_trades}"], hashes)

        wfa = results.get("run_wfa")
        if wfa is None or wfa.status != "SUCCESS":
            return self._decision("REJECTED_OVERFIT", ["wfa_not_completed"], hashes)
        holdout = dict(wfa.payload.get("holdout") or {})
        oos_trades = int(holdout.get("trades", 0))
        expectancy = holdout.get("net_expectancy_bps")
        profit_factor = holdout.get("profit_factor")
        positive_fraction = float(wfa.payload.get("positive_oos_partition_fraction", 0.0))

        reasons: list[str] = []
        if oos_trades < int(self.gates.get("minimum_oos_trades", 0)):
            reasons.append(f"insufficient_oos_trades:{oos_trades}")
        if expectancy is None or float(expectancy) <= float(self.gates.get("minimum_oos_net_expectancy_bps", 0.0)):
            reasons.append(f"oos_expectancy_not_positive:{expectancy}")
        if profit_factor is None or float(profit_factor) < float(self.gates.get("minimum_oos_profit_factor", 1.0)):
            reasons.append(f"oos_profit_factor_below_gate:{profit_factor}")
        if positive_fraction < float(self.gates.get("minimum_positive_oos_partition_fraction", 1.0)):
            reasons.append(f"positive_oos_partition_fraction_below_gate:{positive_fraction}")
        if reasons:
            return self._decision("REJECTED_OVERFIT", reasons, hashes)

        return CertificationDecision(
            verdict="READY_FOR_OPTION_REPLAY",
            passed=True,
            reasons=["structural_baseline_and_wfa_passed", "option_execution_not_yet_certified"],
            evidence_hashes=hashes,
            promotion_ceiling=str(self.gates.get("promotion_ceiling", "READY_FOR_OPTION_REPLAY")),
        )

    def _decision(self, verdict: str, reasons: list[str], hashes: dict[str, str]) -> CertificationDecision:
        return CertificationDecision(
            verdict=verdict,  # type: ignore[arg-type]
            passed=False,
            reasons=reasons,
            evidence_hashes=hashes,
            promotion_ceiling=str(self.gates.get("promotion_ceiling", "READY_FOR_OPTION_REPLAY")),
        )
