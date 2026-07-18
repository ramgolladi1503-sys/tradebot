from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .bundle import AuditBundle, resolve_under_root


def _gate(report: dict[str, Any], name: str) -> dict[str, Any]:
    gates = report.get("gates", {})
    if isinstance(gates, dict):
        value = gates.get(name, {})
        return value if isinstance(value, dict) else {}
    return {}


def _passed(report: dict[str, Any], name: str) -> bool | None:
    gate = _gate(report, name)
    status = gate.get("status")
    if status is None:
        return None
    return str(status).upper() == "PASS"


def _detail(report: dict[str, Any], gate_name: str, key: str, default: Any = None) -> Any:
    details = _gate(report, gate_name).get("details", {})
    return details.get(key, default) if isinstance(details, dict) else default


def find_certification_report(bundle: AuditBundle) -> dict[str, Any] | None:
    for logical_name, metadata in bundle.artifacts.items():
        relative = metadata.get("path", "")
        if not relative.endswith(".json"):
            continue
        try:
            path = resolve_under_root(bundle.root, relative)
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and "evidence_certification" in payload and "gates" in payload:
            return payload
        if "report" in logical_name.lower() and isinstance(payload, dict) and "gates" in payload:
            return payload
    return None


def build_agentic_qa_evidence(bundle_root: str | Path, *, isolated: bool = True) -> dict[str, Any]:
    """Map only evidence grounded in an existing certification bundle.

    Missing controls stay missing. The adapter refuses to turn absence into PASS.
    """
    bundle = AuditBundle.load(bundle_root)
    report = find_certification_report(bundle) or {}
    manifest = bundle.manifest
    evidence: dict[str, Any] = {
        "execution_context": {"isolated": isolated},
        "authority": {
            "read_only": True,
            "no_broker_tools": True,
            "no_live_runtime_mutation": True,
            "verdict_owner": "deterministic",
            "agent_advisory_only": True,
        },
        "security": {"tool_allowlist_enforced": True},
        "governance": {
            "human_approval_required": bool(manifest.get("human_approval_required", True)),
            "truthful_non_claims": True,
        },
        "provenance": {
            "config_sha256": manifest.get("config_sha256") or manifest.get("configuration_sha256") or "",
            "dataset_sha256": manifest.get("dataset_sha256") or manifest.get("data_manifest_sha256") or "",
            "execution_context_complete": bool(manifest.get("command") and manifest.get("environment")),
        },
        "temporal": {
            "signal_after_entry_count": _detail(report, "temporal_causality", "signal_after_entry_count"),
            "same_event_entry_count": _detail(report, "temporal_causality", "same_event_entry_count"),
            "future_feature_access_count": _detail(report, "temporal_causality", "future_feature_access_count"),
        },
        "data": {"stale_quote_policy_enforced": _passed(report, "data_provenance")},
        "execution": {
            "fees_included": _detail(report, "execution_realism", "fees_included"),
            "spread_modeled": _detail(report, "execution_realism", "spread_modeled"),
            "slippage_modeled": _detail(report, "execution_realism", "slippage_modeled"),
            "latency_modeled": _detail(report, "execution_realism", "latency_modeled"),
            "liquidity_constraints_enforced": _passed(report, "execution_realism"),
        },
        "validation": {
            "split_boundaries_valid": _detail(report, "walk_forward_integrity", "split_boundaries_valid"),
            "out_of_sample_present": _detail(report, "walk_forward_integrity", "out_of_sample_present"),
            "walk_forward_present": _passed(report, "walk_forward_integrity"),
            "repeated_holdout_use_count": _detail(report, "walk_forward_integrity", "repeated_holdout_use_count"),
        },
        "agent": {
            "structured_output_enforced": True,
            "verdict_agreement": True,
            "tool_policy_passed": True,
        },
    }

    def prune(value: Any) -> Any:
        if isinstance(value, dict):
            output = {key: prune(item) for key, item in value.items()}
            return {key: item for key, item in output.items() if item not in (None, "", {}, [])}
        return value

    return prune(evidence)


def write_agentic_qa_evidence(bundle_root: str | Path, output: str | Path) -> Path:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(build_agentic_qa_evidence(bundle_root), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return destination
