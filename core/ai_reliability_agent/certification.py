from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent import AssertionVerifier, ToolRegistry
from .analytics import build_candidate_autopsy, derive_session_verdict, observed_contributors
from .contracts import (
    AgentMode,
    Assertion,
    CertificationLevel,
    ClaimKind,
    DecisionOutcomeClass,
    FindingProposal,
    FindingStatus,
    OutcomeKind,
    OutcomeScope,
    Severity,
    SessionVerdict,
    ToolRequest,
)
from .evidence import EvidenceLedger


@dataclass(frozen=True)
class CertificationGate:
    gate_id: str
    passed: bool
    evidence: dict[str, Any]



def run_component_certification(output_dir: str | Path) -> dict[str, Any]:
    gates: list[CertificationGate] = []
    with tempfile.TemporaryDirectory(prefix="tradebot-agent-cert-") as tmp:
        root = Path(tmp)
        ledger = EvidenceLedger(root / "evidence.jsonl")
        secret_ref = ledger.append(
            "redaction_probe", {"api_key": "secret", "message": "safe"}, session_id="CERT"
        )
        gates.append(CertificationGate(
            "EVIDENCE_REDACTION",
            ledger.payload(secret_ref.evidence_id).get("api_key") == "[REDACTED]",
            {"evidence_id": secret_ref.evidence_id},
        ))
        first = ledger.append("first", {"value": 1}, session_id="CERT")
        second = ledger.append("second", {"value": 2}, session_id="CERT")
        chain = ledger.verify()
        gates.append(CertificationGate(
            "IMMUTABLE_HASH_CHAIN", chain.valid and chain.row_count == 3,
            {"row_count": chain.row_count, "errors": list(chain.errors), "last_sha256": second.sha256},
        ))
        registry = ToolRegistry()
        registry.register("read", lambda args: {"ok": True}, read_only=True)
        registry.register("write", lambda args: {"ok": True}, read_only=False)
        read_result = registry.execute(
            ToolRequest("read"), mode=AgentMode.LIVE_OBSERVE, ledger=ledger, session_id="CERT"
        )
        write_result = registry.execute(
            ToolRequest("write"), mode=AgentMode.LIVE_OBSERVE, ledger=ledger, session_id="CERT"
        )
        gates.append(CertificationGate(
            "LIVE_READ_ONLY_BOUNDARY",
            read_result.success and write_result.error_code == "LIVE_MODE_WRITE_TOOL_BLOCKED",
            {"read_success": read_result.success, "write_error_code": write_result.error_code},
        ))
        fact_ref = ledger.append("fact", {"payload": {"stale": True}}, session_id="CERT")
        true_proposal = FindingProposal(
            title="stale", stage="feed", severity=Severity.P1,
            claim_kind=ClaimKind.DETERMINISTIC_FACT, narrative="stale",
            assertions=(Assertion(fact_ref.evidence_id, "payload.stale", "eq", True),),
            evidence_ids=(fact_ref.evidence_id,), confidence=1.0,
        )
        false_proposal = FindingProposal(
            title="fresh", stage="feed", severity=Severity.P1,
            claim_kind=ClaimKind.DETERMINISTIC_FACT, narrative="fresh",
            assertions=(Assertion(fact_ref.evidence_id, "payload.stale", "eq", False),),
            evidence_ids=(fact_ref.evidence_id,), confidence=1.0,
        )
        verifier = AssertionVerifier()
        true_result = verifier.verify(true_proposal, ledger)
        false_result = verifier.verify(false_proposal, ledger)
        gates.append(CertificationGate(
            "SUPPORTED_FINDING_CONFIRMED",
            true_result.status == FindingStatus.CONFIRMED,
            true_result.to_dict(),
        ))
        gates.append(CertificationGate(
            "UNSUPPORTED_FINDING_REJECTED",
            false_result.status == FindingStatus.REJECTED,
            false_result.to_dict(),
        ))
        good_loss = build_candidate_autopsy("GOOD-LOSS", [
            {"candidate_id": "GOOD-LOSS", "stage": "selected", "stage_status": "selected", "execution_ok": True, "spread_pct": 0.5},
            {"candidate_id": "GOOD-LOSS", "stage": "closed", "outcome": "stop", "breakout_held": False},
        ])
        bad_win = build_candidate_autopsy("BAD-WIN", [
            {"candidate_id": "BAD-WIN", "stage": "selected", "stage_status": "selected", "fallback_used": True},
            {"candidate_id": "BAD-WIN", "stage": "closed", "outcome": "target"},
        ])
        gates.append(CertificationGate(
            "DECISION_OUTCOME_SEPARATION",
            good_loss.decision_outcome_class == DecisionOutcomeClass.GOOD_DECISION_BAD_OUTCOME
            and bad_win.decision_outcome_class == DecisionOutcomeClass.BAD_DECISION_GOOD_OUTCOME,
            {
                "good_loss": good_loss.decision_outcome_class.value,
                "bad_win": bad_win.decision_outcome_class.value,
            },
        ))
        verdict = derive_session_verdict(
            session_data_valid=True, emitted_untrustworthy=1,
            unexplained_disappearances=0, observability_gaps=0, materially_missed_candidates=0,
        )
        gates.append(CertificationGate(
            "UNTRUSTWORTHY_EMISSION_FAILS_CLOSED",
            verdict == SessionVerdict.PIPELINE_EMITTED_UNTRUSTWORTHY_CANDIDATES,
            {"verdict": verdict.value},
        ))
        actual = build_candidate_autopsy("ACTUAL", [
            {"candidate_id": "ACTUAL", "stage_status": "selected", "execution_ok": True, "spread_pct": 0.2},
            {"candidate_id": "ACTUAL", "stage_status": "closed", "evidence_source": "trade_log", "outcome": "target"},
        ])
        counterfactual = build_candidate_autopsy("COUNTERFACTUAL", [
            {"candidate_id": "COUNTERFACTUAL", "stage_status": "blocked", "block_reason": "WIDE_SPREAD"},
            {"candidate_id": "COUNTERFACTUAL", "outcome": "target"},
        ])
        gates.append(CertificationGate(
            "OUTCOME_SCOPE_SEPARATION",
            actual.outcome_scope == OutcomeScope.ACTUAL
            and counterfactual.outcome_scope == OutcomeScope.COUNTERFACTUAL,
            {"actual": actual.outcome_scope.value, "counterfactual": counterfactual.outcome_scope.value},
        ))
        gates.append(CertificationGate(
            "REJECTED_TARGET_NOT_AUTOMATIC_MISSED_OPPORTUNITY",
            counterfactual.rejection_verdict is not None
            and counterfactual.rejection_verdict.value == "UNVERIFIABLE",
            {"rejection_verdict": counterfactual.rejection_verdict.value if counterfactual.rejection_verdict else None},
        ))
        ce_wrong = observed_contributors(
            {"option_type": "CE"},
            {"underlying_move": -20, "option_move": -2, "iv_change": -0.05},
            OutcomeKind.STOP,
        )
        pe_right = observed_contributors(
            {"option_type": "PE"},
            {"underlying_move": -20, "option_move": -2, "iv_change": -0.05},
            OutcomeKind.STOP,
        )
        gates.append(CertificationGate(
            "DIRECTION_AWARE_OPTION_ATTRIBUTION",
            "IV_CONTRACTION" not in {item.factor.value for item in ce_wrong}
            and "IV_CONTRACTION" in {item.factor.value for item in pe_right},
            {
                "ce_wrong_factors": sorted(item.factor.value for item in ce_wrong),
                "pe_right_factors": sorted(item.factor.value for item in pe_right),
            },
        ))

    passed = all(gate.passed for gate in gates)
    certification_level = CertificationLevel.SIMULATION_CERTIFIED if passed else CertificationLevel.NOT_CERTIFIED
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "certification_level": certification_level.value,
        "live_certification": CertificationLevel.LIVE_CERTIFICATION_PENDING.value,
        "passed": passed,
        "gate_count": len(gates),
        "passed_gate_count": sum(gate.passed for gate in gates),
        "gates": [asdict(gate) for gate in gates],
        "scope": [
            "component contracts",
            "evidence redaction and integrity",
            "live read-only boundary",
            "machine-verifiable finding acceptance/rejection",
            "decision-quality versus outcome separation",
            "fail-closed session verdict",
            "actual versus counterfactual outcome separation",
            "rejected-target hindsight protection",
            "direction-aware option attribution",
        ],
        "not_certified_by_this_report": [
            "live-market operability",
            "broker connectivity",
            "strategy profitability",
            "causal market explanations",
            "production deployment readiness",
        ],
    }
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "ai_reliability_agent_component_certification.json"
    md_path = target / "ai_reliability_agent_component_certification.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_certification_markdown(report), encoding="utf-8")
    return {**report, "json_path": str(json_path), "markdown_path": str(md_path)}


def render_certification_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# TradeBot AI Reliability Agent — Component Certification",
        "",
        f"- Certification: `{report['certification_level']}`",
        f"- Live certification: `{report['live_certification']}`",
        f"- Gates: `{report['passed_gate_count']}/{report['gate_count']}` passed",
        "",
        "## Gates",
        "",
    ]
    for gate in report["gates"]:
        lines.append(f"- {'PASS' if gate['passed'] else 'FAIL'} `{gate['gate_id']}`")
    lines.extend(["", "## Explicit exclusions", ""])
    for item in report["not_certified_by_this_report"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"
