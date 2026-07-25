from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def oracle_audit(ledger_content: bytes, evidence: Mapping[str, Any], expected_sha256: str, expected_rows: int) -> dict[str, Any]:
    digest = hashlib.sha256(ledger_content).hexdigest()
    payload = json.loads(ledger_content)
    records = payload["records"]
    owners = sorted({record.get("strategy_or_hypothesis_id") for record in records if record.get("strategy_or_hypothesis_id")})
    implementation = evidence.get("implementation_manifest", {})
    parameters = evidence.get("parameter_manifest", {})
    dataset = evidence.get("dataset_manifest", {})
    freeze = evidence.get("freeze_manifest", {})
    invalidation = evidence.get("historical_invalidation", {})
    timestamps_present = all(record.get("feature_cutoff_ts") and record.get("signal_ts") and record.get("earliest_entry_ts") for record in records)
    folds_present = all(record.get("fold_id") for record in records)
    bindings = {
        "ownership": bool(owners),
        "implementation": implementation.get("ledger_sha256") == digest,
        "parameters": parameters.get("ledger_sha256") == digest and parameters.get("complete") is True and bool(parameters.get("owner")) and bool(parameters.get("parameters")),
        "dataset": dataset.get("ledger_sha256") == digest and str(dataset.get("dataset_family_id", "")).startswith("FAMILY:") and str(dataset.get("dataset_version_id", "")).startswith("VERSION:"),
        "temporal": timestamps_present,
        "split_fold": folds_present and evidence.get("split_manifest", {}).get("ledger_sha256") == digest,
        "freeze": freeze.get("ledger_sha256") == digest,
        "historical_invalidation": invalidation.get("ledger_sha256") == digest,
    }
    contamination = evidence.get("contamination_evidence", {})
    contamination_states = {name: contamination.get(name, "UNRESOLVED") for name in ("outcome", "option_price", "tuning", "holdout")}
    if bindings["historical_invalidation"] or "CONFIRMED" in contamination_states.values():
        verdict = "SIGNAL_LEDGER_INVALIDATED"
    elif not owners:
        verdict = "SIGNAL_LEDGER_PROVENANCE_BLOCKED"
    elif not all(bindings[name] for name in ("implementation", "parameters", "dataset", "temporal", "split_fold", "freeze")) or "UNRESOLVED" in contamination_states.values():
        verdict = "SIGNAL_LEDGER_OWNERSHIP_PROVEN_BUT_PROVENANCE_INCOMPLETE"
    else:
        verdict = "SIGNAL_LEDGER_PROVENANCE_ESTABLISHED_WITH_LIMITATIONS"
    return {
        "physical_hash_matches": digest == expected_sha256,
        "row_count_matches": len(records) == expected_rows,
        "row_count": len(records),
        "canonical_strategy_ids": owners,
        "bindings": bindings,
        "contamination_states": contamination_states,
        "verdict": verdict,
    }
