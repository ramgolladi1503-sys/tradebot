"""Machine-verifiable certification for the supervised MEG shadow system.

The module separates deterministic same-SHA contract proof from real market
proof.  Passing tests alone can produce only the offline contract verdict.  A
final read-only system certificate additionally requires a fresh passing
post-market certificate generated from PR #763 evidence by PR #772.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


OFFLINE_PASS_VERDICT = "PASS_OFFLINE_MEG_SHADOW_CONTRACTS"
CERTIFIED_VERDICT = "MEG_SHADOW_SYSTEM_CERTIFIED_READ_ONLY"
PENDING_VERDICT = "IMPLEMENTATION_COMPLETE_LIVE_EVIDENCE_PENDING"
FAILED_VERDICT = "FAILED_CLOSED"
POST_MARKET_PASS_VERDICT = "PASS_READ_ONLY_POST_MARKET_RELIABILITY"

REQUIRED_OFFLINE_GATES = (
    "AUTHENTICATION_AND_STARTUP",
    "FEED_AND_SUBSCRIPTION_TRUTH",
    "PERSISTENCE_AND_SHUTDOWN",
    "MARKET_EVENT_GRAPH_OBSERVATION",
    "AUTHORITY_RANKING_AND_UI",
    "MANUAL_APPROVAL_AND_BROKER_FIREWALL",
    "RESTART_AND_RECONCILIATION",
    "AI_RELIABILITY_AND_EVIDENCE_INTEGRITY",
)


def _canonical_sha(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("json_root_must_be_object")
    return dict(value)


def _gate_semantic(gate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "gate_id": str(gate.get("gate_id") or ""),
        "passed": gate.get("passed") is True,
        "return_code": int(gate.get("return_code") or 0),
        "timed_out": gate.get("timed_out") is True,
        "command": [str(part) for part in (gate.get("command") or [])],
        "test_file_sha256": dict(sorted((gate.get("test_file_sha256") or {}).items())),
    }


def build_offline_report(
    *,
    head_sha: str,
    gate_results: Sequence[Mapping[str, Any]],
    generated_at: str | None = None,
) -> dict[str, Any]:
    normalized = [_gate_semantic(gate) | {
        "duration_seconds": float(gate.get("duration_seconds") or 0.0),
        "stdout_tail": str(gate.get("stdout_tail") or ""),
        "stderr_tail": str(gate.get("stderr_tail") or ""),
    } for gate in gate_results]
    by_id = {gate["gate_id"]: gate for gate in normalized if gate["gate_id"]}
    missing = [gate_id for gate_id in REQUIRED_OFFLINE_GATES if gate_id not in by_id]
    extras = sorted(set(by_id) - set(REQUIRED_OFFLINE_GATES))
    duplicate_ids = sorted(
        gate_id
        for gate_id in set(gate["gate_id"] for gate in normalized if gate["gate_id"])
        if sum(1 for gate in normalized if gate["gate_id"] == gate_id) > 1
    )
    failed = [
        gate_id
        for gate_id in REQUIRED_OFFLINE_GATES
        if gate_id in by_id
        and (
            by_id[gate_id]["passed"] is not True
            or by_id[gate_id]["return_code"] != 0
            or by_id[gate_id]["timed_out"] is True
        )
    ]
    passed = bool(head_sha) and not missing and not extras and not duplicate_ids and not failed
    semantic = {
        "schema_version": 1,
        "head_sha": str(head_sha),
        "verdict": OFFLINE_PASS_VERDICT if passed else FAILED_VERDICT,
        "read_only": True,
        "order_authority": False,
        "broker_write_authority": False,
        "required_gate_ids": list(REQUIRED_OFFLINE_GATES),
        "missing_gate_ids": missing,
        "extra_gate_ids": extras,
        "duplicate_gate_ids": duplicate_ids,
        "failed_gate_ids": failed,
        "gates": [_gate_semantic(by_id[gate_id]) for gate_id in REQUIRED_OFFLINE_GATES if gate_id in by_id],
        "claim_boundary": {
            "strategy_profitability_certified": False,
            "structural_edge_certified": False,
            "broker_connectivity_certified": False,
            "paper_or_live_execution_authorized": False,
            "target": "SUPERVISED_READ_ONLY_MEG_SHADOW",
        },
    }
    return {
        **semantic,
        "generated_at": generated_at or datetime.now(tz=timezone.utc).isoformat(),
        "semantic_sha256": _canonical_sha(semantic),
        "gate_details": normalized,
    }


def validate_offline_report(report: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if report.get("verdict") != OFFLINE_PASS_VERDICT:
        errors.append("offline_verdict_not_pass")
    if not str(report.get("head_sha") or "").strip():
        errors.append("offline_head_sha_missing")
    if report.get("read_only") is not True:
        errors.append("offline_read_only_not_true")
    if report.get("order_authority") is not False:
        errors.append("offline_order_authority_not_false")
    if report.get("broker_write_authority") is not False:
        errors.append("offline_broker_write_authority_not_false")
    gates = report.get("gates")
    if not isinstance(gates, list):
        errors.append("offline_gates_missing")
        gates = []
    by_id: dict[str, Mapping[str, Any]] = {}
    for gate in gates:
        if not isinstance(gate, Mapping):
            errors.append("offline_gate_invalid")
            continue
        gate_id = str(gate.get("gate_id") or "")
        if gate_id in by_id:
            errors.append(f"offline_gate_duplicate:{gate_id}")
        by_id[gate_id] = gate
    for gate_id in REQUIRED_OFFLINE_GATES:
        gate = by_id.get(gate_id)
        if gate is None:
            errors.append(f"offline_gate_missing:{gate_id}")
            continue
        if gate.get("passed") is not True:
            errors.append(f"offline_gate_not_passed:{gate_id}")
        if int(gate.get("return_code") or 0) != 0:
            errors.append(f"offline_gate_nonzero:{gate_id}")
        if gate.get("timed_out") is True:
            errors.append(f"offline_gate_timeout:{gate_id}")
    extras = sorted(set(by_id) - set(REQUIRED_OFFLINE_GATES))
    for gate_id in extras:
        errors.append(f"offline_gate_unexpected:{gate_id}")

    semantic = {
        key: report.get(key)
        for key in (
            "schema_version",
            "head_sha",
            "verdict",
            "read_only",
            "order_authority",
            "broker_write_authority",
            "required_gate_ids",
            "missing_gate_ids",
            "extra_gate_ids",
            "duplicate_gate_ids",
            "failed_gate_ids",
            "gates",
            "claim_boundary",
        )
    }
    expected_semantic_sha = _canonical_sha(semantic)
    if str(report.get("semantic_sha256") or "") != expected_semantic_sha:
        errors.append("offline_semantic_sha_mismatch")
    return {
        "passed": not errors,
        "errors": errors,
        "head_sha": str(report.get("head_sha") or ""),
        "semantic_sha256": expected_semantic_sha,
    }


def validate_post_market_certificate(report: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    verdict = str(report.get("verdict") or "")
    if report.get("read_only") is not True:
        errors.append("post_market_read_only_not_true")
    if report.get("order_authority") is not False:
        errors.append("post_market_order_authority_not_false")
    if report.get("broker_write_authority") is not False:
        errors.append("post_market_broker_write_authority_not_false")
    if not str(report.get("semantic_sha256") or ""):
        errors.append("post_market_semantic_sha_missing")
    if verdict == FAILED_VERDICT:
        errors.append("post_market_failed_closed")
    elif verdict not in {POST_MARKET_PASS_VERDICT, PENDING_VERDICT}:
        errors.append(f"post_market_unknown_verdict:{verdict}")
    if verdict == POST_MARKET_PASS_VERDICT:
        if report.get("implementation_complete") is not True:
            errors.append("post_market_implementation_not_complete")
        if report.get("live_evidence_complete") is not True:
            errors.append("post_market_live_evidence_not_complete")
    return {
        "valid": not errors,
        "passed": not errors and verdict == POST_MARKET_PASS_VERDICT,
        "pending": not errors and verdict == PENDING_VERDICT,
        "verdict": verdict,
        "errors": errors,
        "semantic_sha256": str(report.get("semantic_sha256") or ""),
    }


def assemble_system_certificate(
    *,
    offline_report: Mapping[str, Any] | str | Path,
    post_market_certificate: Mapping[str, Any] | str | Path | None,
    output_dir: str | Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    offline = _load_json(offline_report) if isinstance(offline_report, (str, Path)) else dict(offline_report)
    offline_check = validate_offline_report(offline)
    post: dict[str, Any] | None
    if post_market_certificate is None:
        post = None
        post_check = {
            "valid": True,
            "passed": False,
            "pending": True,
            "verdict": "MISSING",
            "errors": [],
            "semantic_sha256": "",
        }
    else:
        post = (
            _load_json(post_market_certificate)
            if isinstance(post_market_certificate, (str, Path))
            else dict(post_market_certificate)
        )
        post_check = validate_post_market_certificate(post)

    if not offline_check["passed"] or not post_check["valid"]:
        verdict = FAILED_VERDICT
    elif post_check["passed"]:
        verdict = CERTIFIED_VERDICT
    else:
        verdict = PENDING_VERDICT

    semantic = {
        "schema_version": 1,
        "verdict": verdict,
        "target": "SUPERVISED_READ_ONLY_MEG_SHADOW",
        "head_sha": offline_check["head_sha"],
        "offline_contracts_passed": offline_check["passed"],
        "post_market_reliability_passed": post_check["passed"],
        "read_only": True,
        "order_authority": False,
        "broker_write_authority": False,
        "allowed_for_live_execution": False,
        "allowed_for_paper_execution": False,
        "offline_report_semantic_sha256": str(offline.get("semantic_sha256") or ""),
        "post_market_semantic_sha256": post_check["semantic_sha256"],
        "errors": [
            *[f"offline:{error}" for error in offline_check["errors"]],
            *[f"post_market:{error}" for error in post_check["errors"]],
        ],
        "remaining_gate": None if verdict in {CERTIFIED_VERDICT, FAILED_VERDICT} else "FRESH_PR763_MARKET_SESSION",
        "claim_boundary": {
            "strategy_profitability_certified": False,
            "structural_edge_certified": False,
            "broker_connectivity_certified": False,
            "real_fill_quality_certified": False,
            "paper_or_live_execution_authorized": False,
            "unattended_autonomy_authorized": False,
        },
    }
    certificate = {
        **semantic,
        "generated_at": generated_at or datetime.now(tz=timezone.utc).isoformat(),
        "semantic_sha256": _canonical_sha(semantic),
        "offline_validation": offline_check,
        "post_market_validation": post_check,
    }
    if output_dir is not None:
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        json_path = target / "meg_shadow_system_certificate.json"
        md_path = target / "meg_shadow_system_certificate.md"
        json_path.write_text(json.dumps(certificate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        md_path.write_text(render_certificate_markdown(certificate), encoding="utf-8")
        certificate["json_path"] = str(json_path)
        certificate["markdown_path"] = str(md_path)
    return certificate


def render_certificate_markdown(certificate: Mapping[str, Any]) -> str:
    lines = [
        "# TradeBot MEG Shadow System Certificate",
        "",
        f"- Verdict: `{certificate.get('verdict')}`",
        f"- Target: `{certificate.get('target')}`",
        f"- Repository SHA: `{certificate.get('head_sha')}`",
        f"- Offline contracts passed: `{certificate.get('offline_contracts_passed')}`",
        f"- Post-market reliability passed: `{certificate.get('post_market_reliability_passed')}`",
        f"- Order authority: `{certificate.get('order_authority')}`",
        f"- Semantic SHA-256: `{certificate.get('semantic_sha256')}`",
        "",
    ]
    if certificate.get("remaining_gate"):
        lines.extend(["## Remaining gate", "", f"- `{certificate.get('remaining_gate')}`", ""])
    if certificate.get("errors"):
        lines.extend(["## Errors", ""])
        for error in certificate.get("errors") or []:
            lines.append(f"- `{error}`")
        lines.append("")
    lines.extend(
        [
            "## Claim boundary",
            "",
            "This certificate covers supervised, read-only Market Event Graph shadow operation only. It does not certify profitability, structural edge, broker connectivity, real fills, paper/live execution, or unattended autonomy.",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "CERTIFIED_VERDICT",
    "FAILED_VERDICT",
    "OFFLINE_PASS_VERDICT",
    "PENDING_VERDICT",
    "REQUIRED_OFFLINE_GATES",
    "assemble_system_certificate",
    "build_offline_report",
    "render_certificate_markdown",
    "validate_offline_report",
    "validate_post_market_certificate",
]
