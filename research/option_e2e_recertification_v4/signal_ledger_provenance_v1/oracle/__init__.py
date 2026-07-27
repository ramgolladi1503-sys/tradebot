from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..git_provenance import (
    EXPECTED_INTRODUCTION_COMMIT,
    FORBIDDEN_CONTENT_MARKERS,
    GENERATOR_RELATIVE_PATH,
    TEXT_SUFFIXES,
)
from ..lineage_oracle import oracle_audit as _lineage_oracle_audit
from ..search_policy import is_self_audit_path


def _parent_path_absence(repo_root: Path, first_commits: dict[str, str]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for path, commit in first_commits.items():
        parents = subprocess.run(
            ["git", "rev-list", "--parents", "-n", "1", commit],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()
        if len(parents) < 2:
            result[path] = True
            continue
        exists = subprocess.run(
            ["git", "cat-file", "-e", f"{parents[1]}:{path}"],
            cwd=repo_root,
            check=False,
            capture_output=True,
        ).returncode == 0
        result[path] = not exists
    return result


def _legacy_oracle(ledger_content: bytes, evidence: Mapping[str, Any], expected_sha256: str, expected_rows: int) -> dict[str, Any]:
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
    states = {name: contamination.get(name, "UNRESOLVED") for name in ("outcome", "option_price", "tuning", "holdout")}
    if bindings["historical_invalidation"] or "CONFIRMED" in states.values():
        verdict = "SIGNAL_LEDGER_INVALIDATED"
    elif not owners:
        verdict = "SIGNAL_LEDGER_PROVENANCE_BLOCKED"
    elif not all(bindings[name] for name in ("implementation", "parameters", "dataset", "temporal", "split_fold", "freeze")) or "UNRESOLVED" in states.values():
        verdict = "SIGNAL_LEDGER_OWNERSHIP_PROVEN_BUT_PROVENANCE_INCOMPLETE"
    else:
        verdict = "SIGNAL_LEDGER_PROVENANCE_ESTABLISHED_WITH_LIMITATIONS"
    return {"physical_hash_matches": digest == expected_sha256, "row_count_matches": len(records) == expected_rows, "row_count": len(records), "canonical_strategy_ids": owners, "bindings": bindings, "contamination_states": states, "verdict": verdict}


def _oracle_candidate_paths(root: Path, *, repo_root: Path | None = None) -> list[Path]:
    if repo_root is not None and root == repo_root:
        tracked = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        return [repo_root / path for path in tracked]
    return [path for path in root.rglob("*") if path.is_file()] if root.exists() else []


def _oracle_search(repo_root: Path, external_roots: Iterable[Path], ledger_sha256: str, row_count: int) -> list[dict[str, Any]]:
    terms = [ledger_sha256, f"{ledger_sha256}:{row_count}", GENERATOR_RELATIVE_PATH, EXPECTED_INTRODUCTION_COMMIT]
    roots = [("repository", repo_root, repo_root)] + [
        (f"external_{index}", root, None) for index, root in enumerate(external_roots, start=1)
    ]
    records: list[dict[str, Any]] = []
    for search_id, root, git_root in roots:
        candidate_paths = _oracle_candidate_paths(root, repo_root=git_root)
        inspected_count = 0
        matching_count = 0
        scope_excluded_count = 0
        errors: list[str] = []
        for path in candidate_paths:
            relative = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
            lower = relative.lower()
            if any(marker in lower for marker in FORBIDDEN_CONTENT_MARKERS):
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if is_self_audit_path(relative):
                scope_excluded_count += 1
                continue
            try:
                if path.stat().st_size > 2_000_000:
                    continue
                text = path.read_text(encoding="utf-8", errors="strict")
            except (OSError, UnicodeError) as exc:
                errors.append(f"{relative}:{type(exc).__name__}")
                continue
            inspected_count += 1
            if any(term in text for term in terms):
                matching_count += 1
        records.append(
            {
                "candidate_count": max(0, len(candidate_paths) - scope_excluded_count),
                "inspected_candidate_count": inspected_count,
                "matching_record_count": matching_count,
                "scope_excluded_candidate_count": scope_excluded_count,
                "search_completed": root.exists() and not errors,
            }
        )
    return records


def oracle_audit(subject: Path | bytes, *args: Any) -> dict[str, Any]:
    if isinstance(subject, (bytes, bytearray)):
        evidence, expected_sha256, expected_rows = args
        return _legacy_oracle(bytes(subject), evidence, expected_sha256, expected_rows)
    repo_root = subject
    expected_sha256, expected_rows = args[:2]
    external_roots = args[2] if len(args) > 2 else ()
    result = _lineage_oracle_audit(repo_root, expected_sha256, expected_rows, external_roots)
    first_commits = result.get("first_commits", {})
    result["parent_path_absence"] = _parent_path_absence(repo_root, first_commits) if first_commits else {}
    result["search_records"] = _oracle_search(repo_root, external_roots, expected_sha256, expected_rows)
    return result


__all__ = ["oracle_audit"]
