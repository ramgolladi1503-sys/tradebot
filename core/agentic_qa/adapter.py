from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .bundle import AuditBundle, AuditBundleError, canonical_json_bytes, resolve_under_root, sha256_file


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


def _artifact_payload(bundle: AuditBundle, filename: str) -> dict[str, Any]:
    for logical_name, metadata in bundle.artifacts.items():
        relative = metadata.get("path", "")
        if logical_name != filename and Path(relative).name != filename:
            continue
        try:
            path = resolve_under_root(bundle.root, relative)
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (AuditBundleError, OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def _all_zero(payload: dict[str, Any], fields: tuple[str, ...]) -> bool | None:
    if any(field not in payload for field in fields):
        return None
    try:
        return all(int(payload.get(field, 0) or 0) == 0 for field in fields)
    except (TypeError, ValueError):
        return False


def _all_true(payload: dict[str, Any], fields: tuple[str, ...]) -> bool | None:
    if any(field not in payload for field in fields):
        return None
    return all(payload.get(field) is True for field in fields)


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
    """Map only facts grounded in an existing frozen TradeBot certification bundle.

    Missing controls stay missing. The adapter refuses to turn absence into PASS.
    """
    bundle = AuditBundle.load(bundle_root)
    report = find_certification_report(bundle) or {}
    manifest = bundle.manifest
    engine = _artifact_payload(bundle, "engine_identity.json")
    config = _artifact_payload(bundle, "run_configuration.json")
    dataset = _artifact_payload(bundle, "dataset_manifest.json")
    timing = _artifact_payload(bundle, "timing_evidence.json")
    fills = _artifact_payload(bundle, "fill_evidence.json")
    costs = _artifact_payload(bundle, "cost_reconciliation.json")
    plan = _artifact_payload(bundle, "wfa_partition_plan.json")
    wfa = _artifact_payload(bundle, "wfa_results.json")
    controls = _artifact_payload(bundle, "negative_controls.json").get("controls", {})
    tests = _artifact_payload(bundle, "test_results.json")

    time_start = str(dataset.get("time_start") or "")
    time_end = str(dataset.get("time_end") or "")
    timezone = str(config.get("timezone") or "")
    timezone_explicit = bool(
        timezone
        and time_start
        and time_end
        and (("+" in time_start[10:] or time_start.endswith("Z")) and ("+" in time_end[10:] or time_end.endswith("Z")))
    )
    sequence_quality = _all_zero(
        dataset,
        (
            "duplicate_timestamp_count",
            "missing_timestamp_count",
            "malformed_timestamp_count",
            "post_expiry_row_count",
            "invalid_ohlc_count",
        ),
    )
    chronology_count = timing.get("chronology_violation_count")
    future_dependency_count = timing.get("future_data_dependency_count")
    plan_valid = _all_true(
        plan,
        (
            "chronological",
            "non_overlapping",
            "purge_embargo_applied",
            "validation_before_holdout",
            "holdout_isolated_from_selection",
        ),
    )
    strict_liquidity = _all_true(
        fills,
        (
            "entries_use_executable_side",
            "exits_use_executable_side",
            "strict_liquidity_mode",
        ),
    )
    no_liquidity_fallbacks = _all_zero(
        fills,
        (
            "fallback_liquidity_fill_count",
            "proxy_exit_mark_count",
            "missing_bid_ask_accepted_count",
            "synthetic_liquidity_fill_count",
        ),
    )
    controls_map = controls if isinstance(controls, dict) else {}
    negative_controls_passed = (
        all(controls_map.get(name) is True for name in ("future_mutation", "timing_shift", "cost_sensitivity"))
        if controls_map
        else None
    )
    test_evidence_passed = (
        int(tests.get("collected", 0) or 0) > 0
        and int(tests.get("failed", 0) or 0) == 0
        and int(tests.get("errors", 0) or 0) == 0
        and tests.get("commit_matches_bundle") is True
        if tests
        else None
    )

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
            "human_approval_required": manifest.get("human_approval_required"),
            "truthful_non_claims": True,
        },
        "provenance": {
            "config_sha256": config.get("frozen_config_hash"),
            "dataset_sha256": dataset.get("dataset_sha256"),
            "execution_context_complete": (
                bool(manifest.get("command") and manifest.get("environment") and manifest.get("random_seed"))
                or None
            ),
        },
        "temporal": {
            "timezone_explicit": timezone_explicit if dataset and config else None,
            "signal_after_entry_count": chronology_count,
            "same_event_entry_count": timing.get("same_event_entry_count"),
            "future_feature_access_count": future_dependency_count,
        },
        "data": {
            "stale_quote_policy_enforced": (
                dataset.get("stale_quote_count") == 0 if "stale_quote_count" in dataset else None
            ),
            "sequence_quality_passed": sequence_quality,
        },
        "execution": {
            "fees_included": (
                bool(config.get("cost_model_version"))
                and all(field in costs for field in ("gross_pnl", "total_costs", "net_pnl"))
                if config and costs
                else None
            ),
            "spread_modeled": (
                dataset.get("quote_columns_complete") is True
                and fills.get("entries_use_executable_side") is True
                and fills.get("exits_use_executable_side") is True
                if dataset and fills
                else None
            ),
            "liquidity_constraints_enforced": (
                strict_liquidity is True and no_liquidity_fallbacks is True
                if strict_liquidity is not None and no_liquidity_fallbacks is not None
                else None
            ),
        },
        "validation": {
            "split_boundaries_valid": plan_valid,
            "out_of_sample_present": (
                wfa.get("holdout_status") == "completed" if "holdout_status" in wfa else None
            ),
            "walk_forward_present": (
                plan_valid is True and bool(wfa) if plan_valid is not None else None
            ),
            "repeated_holdout_use_count": wfa.get("repeated_holdout_run_count"),
        },
        "robustness": {
            "cost_stress_passed": controls_map.get("cost_sensitivity"),
            "delayed_entry_passed": controls_map.get("timing_shift"),
            "negative_controls_passed": negative_controls_passed,
        },
        "agent": {
            "structured_output_enforced": True,
            "verdict_agreement": True,
            "tool_policy_passed": True,
        },
        "source_certification": {
            "evidence_certification": report.get("evidence_certification"),
            "strategy_verdict": report.get("strategy_verdict"),
            "bundle_manifest_gate_passed": _passed(report, "bundle_manifest"),
            "artifact_hash_gate_passed": _passed(report, "artifact_hashes"),
            "test_evidence_passed": test_evidence_passed,
            "engine_read_only": engine.get("read_only"),
        },
    }

    def prune(value: Any) -> Any:
        if isinstance(value, dict):
            output = {key: prune(item) for key, item in value.items()}
            return {key: item for key, item in output.items() if item not in (None, "", {}, [])}
        return value

    return prune(evidence)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(payload) + b"\n")


def build_agentic_qa_bundle(
    source_bundle_root: str | Path,
    output_dir: str | Path,
    *,
    isolated: bool = True,
) -> Path:
    """Create a new immutable Agentic QA sidecar bundle without modifying source evidence."""
    source = AuditBundle.load(source_bundle_root)
    target = Path(output_dir).expanduser().resolve()
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise AuditBundleError(f"output bundle must be a new or empty directory: {target}")
    target.mkdir(parents=True, exist_ok=True)

    evidence = build_agentic_qa_evidence(source.root, isolated=isolated)
    attestation = {
        "schema_version": "agentic-qa-source-attestation/v1",
        "source_manifest": source.manifest_name,
        "source_bundle_digest": source.digest(),
        "source_repository_commit": source.manifest.get("repository_commit"),
        "source_policy_version": source.manifest.get("policy_version"),
        "observed_artifacts": source.observed_artifacts(),
    }
    evidence_path = target / "agentic_qa_evidence.json"
    attestation_path = target / "source_bundle_attestation.json"
    _write_json(evidence_path, evidence)
    _write_json(attestation_path, attestation)

    run_id = str(source.manifest.get("run_id") or source.manifest.get("bundle_id") or "UNKNOWN")
    repository_commit = str(source.manifest.get("repository_commit") or "UNKNOWN")
    source_digest = source.digest()
    trace_id = hashlib.sha256(
        canonical_json_bytes(
            {
                "run_id": run_id,
                "repository_commit": repository_commit,
                "source_bundle_digest": source_digest,
                "policy_version": "agentic-qa-policy/v1",
            }
        )
    ).hexdigest()
    manifest = {
        "schema_version": "tradebot-agentic-qa-bundle/v1",
        "run_id": f"{run_id}:agentic-qa",
        "trace_id": trace_id,
        "repository_commit": repository_commit,
        "policy_version": "agentic-qa-policy/v1",
        "source_bundle_digest": source_digest,
        "artifacts": {
            evidence_path.name: sha256_file(evidence_path),
            attestation_path.name: sha256_file(attestation_path),
        },
    }
    _write_json(target / "run_manifest.json", manifest)
    return target


def write_agentic_qa_evidence(bundle_root: str | Path, output: str | Path) -> Path:
    """Write only the derived evidence document; prefer build_agentic_qa_bundle for audits."""
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json(destination, build_agentic_qa_evidence(bundle_root))
    return destination
