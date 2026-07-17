from __future__ import annotations

import hashlib
from typing import Protocol

from agentic_research.contracts import CriticReport, HypothesisRecord, ToolResult


class HypothesisProposer(Protocol):
    def propose(self, strategy_id: str, dataset_hash: str, results: dict[str, ToolResult]) -> list[HypothesisRecord]: ...


class BoundedHypothesisProposer:
    """Evidence-linked proposals only. It never edits strategy code or parameters."""

    def propose(self, strategy_id: str, dataset_hash: str, results: dict[str, ToolResult]) -> list[HypothesisRecord]:
        critic_result = results.get("run_adversarial_review")
        if critic_result is None:
            return []
        report = CriticReport.model_validate(critic_result.payload.get("report") or {})
        codes = {finding.code for finding in report.blockers}
        proposals: list[HypothesisRecord] = []
        if any(code in codes for code in {"validation_expectancy_non_positive", "holdout_expectancy_non_positive"}):
            proposals.append(self._record(
                strategy_id,
                dataset_hash,
                "OOS losses indicate continuation signals are admitted outside durable directional conditions.",
                "Trend pullback continuation should require an established directional regime rather than an isolated price pattern.",
                "Test one frozen directional-regime admission gate without changing the temporal contract.",
                ["directional_regime_gate"],
                "Reject if purged OOS expectancy remains non-positive or neighboring gate values reverse the expectancy sign.",
            ))
        if "top_five_trade_concentration" in codes:
            proposals.append(self._record(
                strategy_id,
                dataset_hash,
                "A small number of trades dominate total outcome magnitude.",
                "A durable continuation edge should survive across sessions and volatility regimes rather than depend on isolated events.",
                "Test a frozen session/regime breadth requirement and remove the five best sessions as a negative control.",
                ["minimum_regime_breadth", "session_concentration_guard"],
                "Reject if profitability disappears after removing the five best sessions or remains concentrated in one regime.",
            ))
        if any(code.startswith("legacy_") or code == "volume_claims_not_supported" for code in codes):
            return []
        if codes == {"option_execution_not_certified", "structural_split_not_purged_embargoed_wfa"}:
            return []
        return proposals[:3]

    @staticmethod
    def _record(strategy_id: str, dataset_hash: str, observed_failure: str, economic_reasoning: str, proposed_change: str, changed_fields: list[str], rejection_condition: str) -> HypothesisRecord:
        digest = hashlib.sha256(f"{strategy_id}|{dataset_hash}|{observed_failure}|{proposed_change}".encode()).hexdigest()[:12]
        return HypothesisRecord(
            hypothesis_id=f"TP-HYP-{digest}",
            strategy_id=strategy_id,
            observed_failure=observed_failure,
            economic_reasoning=economic_reasoning,
            proposed_change=proposed_change,
            changed_fields=changed_fields,
            rejection_condition=rejection_condition,
            dataset_hash=dataset_hash or "unknown",
        )
