"""Opening Range Retest strategy-fidelity audit.

This module is intentionally read-only. It inspects the frozen production
implementation and writes deterministic research artifacts describing whether
the configured strategy parameters are actually wired into runtime semantics.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from core.strategy_parameter_profiles import resolve_required_profile_parameters
from strategies.movement import opening_range_breakout as orb

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "research" / "opening_range_retest_fidelity_audit"
VALIDATED_PRODUCTION_SOURCE = "cf1b63908c779db844ef3534804142a8af26cbac"
HISTORICAL_RESEARCH_COMMIT = "78da75f7a663ab6772c2a453f7bed7ce25abdbc8"
PRIMARY_VERDICT = "PARAMETER_CONTRACT_BROKEN"
EDGE_APPLICABILITY = "VALID_ONLY_FOR_CURRENT_MISWIRED_VARIANT"


def _run_git(*args: str) -> str:
    return subprocess.check_output(("git", *args), cwd=ROOT, text=True).strip()


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(name: str, payload: dict[str, Any]) -> str:
    path = OUT_DIR / name
    data = _json_dumps(payload).encode("utf-8")
    path.write_bytes(data)
    digest = _sha256_bytes(data)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {name}\n", encoding="utf-8")
    return digest


def _write_text(name: str, text: str) -> str:
    path = OUT_DIR / name
    data = text.encode("utf-8")
    path.write_bytes(data)
    digest = _sha256_bytes(data)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {name}\n", encoding="utf-8")
    return digest


def _source_text() -> str:
    return (ROOT / "strategies" / "movement" / "opening_range_breakout.py").read_text(encoding="utf-8")


def _profile_record() -> dict[str, Any]:
    resolution = resolve_required_profile_parameters(orb.STRATEGY_ID, orb.REQUIRED_PROFILE_KEYS)
    return {
        "requested_profile_id": resolution.requested_profile_id,
        "resolved_profile_id": resolution.resolved_profile_id,
        "profile_version": resolution.profile_version,
        "resolution_source": resolution.resolution_source,
        "parameter_hash": resolution.parameter_hash,
        "parameters": dict(resolution.parameters),
        "blocked_reason": resolution.blocked_reason,
        "warnings": list(resolution.warnings),
    }


def _wiring_matrix() -> dict[str, Any]:
    return {
        "MIN_RETEST_MINUTES": {
            "configured_value": 15,
            "runtime_role": "REQUIRED_BUT_INERT",
            "evidence": "Required by profile resolution but not read by temporal scan or candidate build.",
            "impact": "Profile claims a retest-minute bound that cannot affect emitted candidates.",
        },
        "MAX_RETEST_MINUTES": {
            "configured_value": 90,
            "runtime_role": "REQUIRED_BUT_INERT",
            "evidence": "Required by profile resolution but not read by temporal scan or candidate build.",
            "impact": "Profile claims a retest-minute bound that cannot affect emitted candidates.",
        },
        "MAX_RETEST_DISTANCE_PCT": {
            "configured_value": 0.0018,
            "runtime_role": "SCORE_ONLY",
            "evidence": "Read in _build_temporal_candidate as ratio_score full value; no eligibility predicate rejects larger distances.",
            "impact": "Changes raw score but not candidate inclusion.",
        },
        "MIN_BREAKOUT_DISTANCE_PCT": {
            "configured_value": 0.0008,
            "runtime_role": "SCORE_ONLY",
            "evidence": "Read in _build_temporal_candidate as ratio_score start value; _is_breakout only requires close beyond OR boundary.",
            "impact": "Changes raw score but not candidate inclusion.",
        },
        "OPENING_RANGE_BARS": {
            "configured_value": orb.OPENING_RANGE_BARS,
            "runtime_role": "HARD_CODED_TEMPORAL_GATE",
            "evidence": "Used to slice completed history before scanning breakouts.",
            "impact": "Controls opening-range completion independently of profile.",
        },
        "MAX_BREAKOUT_TO_RETEST_AGE": {
            "configured_value": orb.MAX_BREAKOUT_TO_RETEST_AGE,
            "runtime_role": "HARD_CODED_TEMPORAL_GATE",
            "evidence": "Used in _scan_directional_setup expiry check.",
            "impact": "Controls breakout-to-retest max age independently of profile.",
        },
        "MAX_RETEST_TO_CONTINUATION_AGE": {
            "configured_value": orb.MAX_RETEST_TO_CONTINUATION_AGE,
            "runtime_role": "HARD_CODED_TEMPORAL_GATE",
            "evidence": "Used in _scan_directional_setup expiry check.",
            "impact": "Controls retest-to-continuation max age independently of profile.",
        },
        "BREAKOUT_SCORE_FULL_SATURATION": {
            "configured_value": 0.004,
            "runtime_role": "UNOWNED_SCORE_CONSTANT",
            "evidence": "Inline literal in ratio_score(breakout_distance, ..., full=0.004).",
            "impact": "Affects ranking score without profile ownership.",
        },
    }


def build_artifacts() -> dict[str, dict[str, Any]]:
    head = _run_git("rev-parse", "HEAD")
    source_hash = _sha256_bytes(_source_text().encode("utf-8"))
    profile = _profile_record()
    matrix = _wiring_matrix()
    safety = {
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "append": False,
    }
    source_identity = {
        **safety,
        "audit_id": "ORB_SPECIFICATION_FIDELITY_AND_PARAMETER_WIRING_AUDIT",
        "validated_production_source": VALIDATED_PRODUCTION_SOURCE,
        "historical_research_commit": HISTORICAL_RESEARCH_COMMIT,
        "audit_head": head,
        "production_source_path": "strategies/movement/opening_range_breakout.py",
        "production_source_sha256": source_hash,
        "pr_682_modified": False,
    }
    specification_authority = {
        **safety,
        "runtime_strategy_id": orb.STRATEGY_ID,
        "movement_type": orb.MOVEMENT_TYPE,
        "temporal_contract_version": orb.TEMPORAL_CONTRACT_VERSION,
        "profile": profile,
        "authority_status": "AMBIGUOUS_AND_INCOMPLETE",
        "reason": "Profile requires four ORB parameters, but only two are wired and both wired parameters are score-only.",
    }
    intended_strategy_spec = {
        **safety,
        "strategy": "Opening Range Retest v1",
        "implemented_sequence": [
            "first 15 complete 1m bars define OR high and OR low",
            "breakout bar closes beyond OR boundary",
            "later retest touches boundary and closes on breakout side",
            "later continuation closes beyond retest bar extreme",
            "candidate emits only when continuation is the latest completed bar",
        ],
        "not_implemented_as_candidate_gates": [
            "MIN_RETEST_MINUTES",
            "MAX_RETEST_MINUTES",
            "MAX_RETEST_DISTANCE_PCT",
            "MIN_BREAKOUT_DISTANCE_PCT",
            "VWAP alignment",
        ],
    }
    parameter_wiring = {
        **safety,
        "profile_parameters": profile["parameters"],
        "required_profile_keys": list(orb.REQUIRED_PROFILE_KEYS),
        "matrix": matrix,
        "contract_status": "BROKEN",
    }
    temporal_semantics = {
        **safety,
        "opening_range_bars": orb.OPENING_RANGE_BARS,
        "breakout_to_retest_max_age_bars": orb.MAX_BREAKOUT_TO_RETEST_AGE,
        "retest_to_continuation_max_age_bars": orb.MAX_RETEST_TO_CONTINUATION_AGE,
        "same_bar_breakout_retest_allowed": False,
        "continuation_must_be_latest_completed_bar": True,
        "previous_continuation_suppresses_late_reemission": True,
    }
    replay_equivalence = {
        **safety,
        "direct_whole_history_behavior": "LATEST_BAR_ONLY_EMISSION",
        "incremental_prefix_behavior": "LIVE_EQUIVALENT_EMISSION",
        "known_difference": "A completed session containing later bars after the first continuation does not re-emit the original candidate on direct whole-history invocation.",
        "replay_requirement": "Historical replay must call the generator on causal prefixes, not only once on final session history.",
        "status": "REQUIRES_PREFIX_REPLAY",
    }
    candidate_vs_score = {
        **safety,
        "candidate_eligibility_predicates": [
            "valid completed 1m history",
            "recomputed ORB fields match supplied ORB fields if supplied",
            "breakout close beyond OR boundary",
            "retest touches boundary and closes on breakout side",
            "continuation closes beyond retest bar extreme",
            "hardcoded temporal ages not expired",
        ],
        "score_only_inputs": [
            "MAX_RETEST_DISTANCE_PCT",
            "MIN_BREAKOUT_DISTANCE_PCT",
            "VOLATILITY_EXPANSION",
        ],
    }
    label_truth = {
        **safety,
        "confluence_tags": ["orb_retest", "vwap_alignment"],
        "vwap_predicate_in_main_temporal_path": False,
        "status": "LABEL_OVERSTATED",
        "reason": "Candidate evidence includes ctx.vwap and tag vwap_alignment, but emission does not require VWAP relation.",
    }
    score_formula = {
        **safety,
        "formula": "0.45*(1-ratio_score(retest_distance, full=MAX_RETEST_DISTANCE_PCT)) + 0.35*ratio_score(breakout_distance, start=MIN_BREAKOUT_DISTANCE_PCT, full=0.004) + 0.20*VOLATILITY_EXPANSION",
        "weights_sum": 1.0,
        "unowned_constants": {"breakout_full_saturation": 0.004},
        "score_status": "DETERMINISTIC_BUT_PARTLY_UNOWNED",
    }
    profile_generality = {
        **safety,
        "profile_dimensions": {
            "instrument": "ANY",
            "regime_bucket": "ANY",
            "session_bucket": "ANY",
            "expiry_context": "ANY",
            "volatility_bucket": "ANY",
        },
        "status": "BROAD_PROFILE_WITH_NO_SEGMENT_SPECIALIZATION",
        "impact": "Audit found no per-instrument or per-regime ownership for ORB thresholds.",
    }
    implementation_spec_matrix = {
        **safety,
        "rows": matrix,
        "summary": "Timing contract is hardcoded; two required timing parameters are inert; two distance parameters are score-only.",
    }
    final_verdict = {
        **safety,
        "primary_verdict": PRIMARY_VERDICT,
        "edge_applicability": EDGE_APPLICABILITY,
        "historical_verdict_remains_frozen": "UNDERLYING_SIGNAL_WEAK_OR_UNSTABLE",
        "requires_wfa_rerun": False,
        "optimization_performed": False,
        "production_changes_made": False,
        "why": "The measured historical result remains a valid result for the current implemented ORB variant, but the implementation is not a faithful parameterized strategy contract because required profile parameters are inert or score-only.",
    }
    return {
        "source_identity.json": source_identity,
        "specification_authority.json": specification_authority,
        "intended_strategy_spec.json": intended_strategy_spec,
        "parameter_ownership_matrix.json": parameter_wiring,
        "parameter_wiring_results.json": parameter_wiring,
        "temporal_semantics_results.json": temporal_semantics,
        "replay_equivalence_results.json": replay_equivalence,
        "candidate_vs_score_semantics.json": candidate_vs_score,
        "label_truth_audit.json": label_truth,
        "score_formula_audit.json": score_formula,
        "profile_generality_audit.json": profile_generality,
        "implementation_spec_matrix.json": implementation_spec_matrix,
        "final_fidelity_verdict.json": final_verdict,
    }


def write_all() -> dict[str, str]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    digests: dict[str, str] = {}
    artifacts = build_artifacts()
    for name, payload in artifacts.items():
        digests[name] = _write_json(name, payload)
    digests["intended_strategy_spec.md"] = _write_text("intended_strategy_spec.md", _intended_spec_md(artifacts))
    digests["parameter_ownership_matrix.md"] = _write_text("parameter_ownership_matrix.md", _matrix_md(artifacts))
    digests["final_fidelity_report.md"] = _write_text("final_fidelity_report.md", _report_md(artifacts))
    artifact_audit = {
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "append": False,
        "artifact_count": len(digests),
        "artifacts": digests,
        "status": "READY",
    }
    digests["artifact_audit.json"] = _write_json("artifact_audit.json", artifact_audit)
    return digests


def _intended_spec_md(artifacts: dict[str, dict[str, Any]]) -> str:
    spec = artifacts["intended_strategy_spec.json"]
    lines = [
        "# Opening Range Retest Intended Strategy Spec",
        "",
        "Read-only audit artifact. No production code, broker path, or execution path is changed.",
        "",
        "## Implemented Sequence",
    ]
    lines.extend(f"- {item}" for item in spec["implemented_sequence"])
    lines.append("")
    lines.append("## Not Implemented As Candidate Gates")
    lines.extend(f"- {item}" for item in spec["not_implemented_as_candidate_gates"])
    return "\n".join(lines) + "\n"


def _matrix_md(artifacts: dict[str, dict[str, Any]]) -> str:
    rows = artifacts["parameter_ownership_matrix.json"]["matrix"]
    lines = [
        "# ORB Parameter Ownership Matrix",
        "",
        "| Parameter | Value | Runtime Role | Impact |",
        "| --- | ---: | --- | --- |",
    ]
    for name, row in rows.items():
        lines.append(f"| {name} | {row['configured_value']} | {row['runtime_role']} | {row['impact']} |")
    return "\n".join(lines) + "\n"


def _report_md(artifacts: dict[str, dict[str, Any]]) -> str:
    verdict = artifacts["final_fidelity_verdict.json"]
    lines = [
        "# ORB Fidelity Audit Final Report",
        "",
        f"Primary verdict: `{verdict['primary_verdict']}`",
        f"Edge applicability: `{verdict['edge_applicability']}`",
        "",
        "The historical underlying result remains frozen as `UNDERLYING_SIGNAL_WEAK_OR_UNSTABLE` and was not rerun or optimized.",
        "",
        "Finding: the current implementation is internally deterministic, but its parameter contract is broken. `MIN_RETEST_MINUTES` and `MAX_RETEST_MINUTES` are required by the profile but inert. `MAX_RETEST_DISTANCE_PCT` and `MIN_BREAKOUT_DISTANCE_PCT` affect score only, not candidate eligibility. The emitted `vwap_alignment` tag is not backed by a VWAP predicate in the main temporal path.",
        "",
        "Safety flags: `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `append=false`.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(json.dumps(write_all(), sort_keys=True, indent=2))
