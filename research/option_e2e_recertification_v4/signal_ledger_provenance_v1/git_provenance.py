from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

LEDGER_RELATIVE_PATH = "research/option_e2e_recertification_v4/signal_ledgers_v4_2/signal_ledgers.json"
SIDECAR_RELATIVE_PATH = f"{LEDGER_RELATIVE_PATH}.sha256"
GENERATOR_RELATIVE_PATH = "research/option_e2e_recertification_v4/signal_ledgers_v4_2/build_signal_ledgers.py"
INVENTORY_RELATIVE_PATH = "research/option_e2e_recertification_v4/inventory_v4_1/historical_strategy_inventory_v4_1.json"
INVALIDATION_RELATIVE_PATH = "research/option_e2e_recertification_v4/v4_3_supersession/v4_2_evidence_implementation_invalidation.json"
EXPECTED_LEDGER_SHA256 = "b9736aa6af68a07c32a01dbc2bc60220acf8337181e3878940abfab540398bed"
EXPECTED_ROW_COUNT = 24
EXPECTED_INTRODUCTION_COMMIT = "686af0feff7a4485ebe4e249cb498b33d649a5cd"

TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".txt", ".yaml", ".yml", ".toml", ".csv"}
FORBIDDEN_CONTENT_MARKERS = ("outcome", "pnl", "profit", "returns", "option_price", "holdout_outcome")


class ProvenanceError(ValueError):
    pass


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def run_git(repo_root: Path, *args: str, check: bool = True, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=text,
    )
    if check and result.returncode != 0:
        stderr = result.stderr if text else result.stderr.decode(errors="replace")
        raise ProvenanceError(f"GIT_COMMAND_FAILED:{' '.join(args)}:{stderr.strip()}")
    return result.stdout


def git_object_bytes(repo_root: Path, object_spec: str) -> bytes:
    return run_git(repo_root, "show", object_spec, text=False)  # type: ignore[return-value]


def git_blob_sha(repo_root: Path, commit: str, path: str) -> str:
    return str(run_git(repo_root, "rev-parse", f"{commit}:{path}")).strip()


def path_exists(repo_root: Path, commit: str, path: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}:{path}"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def discover_path_history(repo_root: Path, path: str) -> dict[str, Any]:
    raw = str(run_git(repo_root, "log", "--follow", "--format=%H", "--reverse", "--", path))
    commits = [line.strip() for line in raw.splitlines() if line.strip()]
    if not commits:
        raise ProvenanceError(f"PATH_HISTORY_MISSING:{path}")
    first_commit = commits[0]
    parent_output = str(run_git(repo_root, "rev-list", "--parents", "-n", "1", first_commit)).split()
    parent_commit = parent_output[1] if len(parent_output) > 1 else None
    existed_in_parent = bool(parent_commit and path_exists(repo_root, parent_commit, path))
    return {
        "path": path,
        "first_add_commit": first_commit,
        "all_touch_commits": commits,
        "parent_commit": parent_commit,
        "existed_in_parent": existed_in_parent,
        "first_add_blob_sha": git_blob_sha(repo_root, first_commit, path),
    }


def discover_introduction_history(repo_root: Path, paths: Sequence[str]) -> dict[str, Any]:
    records = {path: discover_path_history(repo_root, path) for path in paths}
    first_commits = {record["first_add_commit"] for record in records.values()}
    if len(first_commits) != 1:
        status = "UNRESOLVED"
        introduction_commit = None
    else:
        introduction_commit = next(iter(first_commits))
        status = "PROVEN" if all(not record["existed_in_parent"] for record in records.values()) else "PROVEN_WITH_PRIOR_LINEAGE"
    return {
        "atomic_introduction_status": status,
        "introduction_commit": introduction_commit,
        "paths": records,
        "configured_expected_commit": EXPECTED_INTRODUCTION_COMMIT,
        "configured_commit_matches_discovery": introduction_commit == EXPECTED_INTRODUCTION_COMMIT,
    }


def _load_historical_generator(generator_bytes: bytes, directory: Path):
    generator_path = directory / "historical_generator.py"
    generator_path.write_bytes(generator_bytes)
    module_name = "_historical_signal_ledger_generator"
    spec = importlib.util.spec_from_file_location(module_name, generator_path)
    if spec is None or spec.loader is None:
        raise ProvenanceError("HISTORICAL_GENERATOR_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def execute_historical_generator(generator_bytes: bytes, inventory_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory(prefix="signal-ledger-primary-") as tmp:
        root = Path(tmp)
        inventory_path = root / "inventory.json"
        inventory_path.write_bytes(inventory_bytes)
        module = _load_historical_generator(generator_bytes, root)
        if not hasattr(module, "build_signal_ledgers") or not hasattr(module, "write_signal_ledgers"):
            raise ProvenanceError("HISTORICAL_GENERATOR_INTERFACE_MISSING")
        records, summary = module.build_signal_ledgers(inventory_path)
        output = root / "output"
        module.write_signal_ledgers(records, summary, output)
        return (output / "signal_ledgers.json").read_bytes()


def _extract_hypotheses(generator_bytes: bytes) -> list[str]:
    tree = ast.parse(generator_bytes.decode("utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "HISTORICAL_RESEARCH_HYPOTHESES" for target in node.targets):
                value = ast.literal_eval(node.value)
                if not isinstance(value, (tuple, list)) or not all(isinstance(item, str) for item in value):
                    raise ProvenanceError("HYPOTHESIS_LITERAL_INVALID")
                return list(value)
    raise ProvenanceError("HYPOTHESIS_LITERAL_MISSING")


def reconstruct_historical_generator_output(generator_bytes: bytes, inventory_bytes: bytes) -> bytes:
    inventory = json.loads(inventory_bytes)
    strategy_ids = [entry["id"] for entry in inventory["entities"] if entry.get("counted_as_strategy")]
    hypotheses = _extract_hypotheses(generator_bytes)
    records: list[dict[str, Any]] = []
    for owner, suffix in [(owner, "signal_blocked") for owner in strategy_ids] + [(owner, "hypothesis_blocked") for owner in hypotheses]:
        records.append(
            {
                "strategy_or_hypothesis_id": owner,
                "signal_id": f"{owner}:{suffix}",
                "session": "frozen",
                "feature_cutoff_ts": "",
                "signal_ts": "",
                "earliest_entry_ts": "",
                "direction": "NA",
                "signal_strength": "0",
                "params_hash": "",
                "source_hash": "",
                "implementation_sha": "",
                "fold_id": "",
                "is_holdout": False,
                "status": "SIGNAL_INPUT_DATA_MISSING",
                "blocker": "NO_SIGNAL_LEDGER_SOURCE",
            }
        )
    payload = {
        "summary": {
            "strategy_count": len(strategy_ids),
            "hypothesis_count": len(hypotheses),
            "status_counts": {"SIGNAL_INPUT_DATA_MISSING": len(records)},
            "blocked_eligibility": len(records),
        },
        "records": records,
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def build_historical_binding(repo_root: Path, expected_introduction_commit: str | None = EXPECTED_INTRODUCTION_COMMIT) -> dict[str, Any]:
    paths = [LEDGER_RELATIVE_PATH, SIDECAR_RELATIVE_PATH, GENERATOR_RELATIVE_PATH, INVENTORY_RELATIVE_PATH]
    history = discover_introduction_history(repo_root, paths)
    introduction_commit = history["introduction_commit"]
    if introduction_commit is None:
        raise ProvenanceError("ATOMIC_INTRODUCTION_UNRESOLVED")
    if expected_introduction_commit is not None and introduction_commit != expected_introduction_commit:
        raise ProvenanceError("INTRODUCTION_COMMIT_MISMATCH")
    historical_ledger = git_object_bytes(repo_root, f"{introduction_commit}:{LEDGER_RELATIVE_PATH}")
    historical_sidecar = git_object_bytes(repo_root, f"{introduction_commit}:{SIDECAR_RELATIVE_PATH}")
    historical_generator = git_object_bytes(repo_root, f"{introduction_commit}:{GENERATOR_RELATIVE_PATH}")
    historical_inventory = git_object_bytes(repo_root, f"{introduction_commit}:{INVENTORY_RELATIVE_PATH}")
    current_ledger = (repo_root / LEDGER_RELATIVE_PATH).read_bytes()
    current_generator = (repo_root / GENERATOR_RELATIVE_PATH).read_bytes()
    sidecar_token = historical_sidecar.decode("utf-8").strip().split()[0] if historical_sidecar.strip() else ""
    primary_regenerated = execute_historical_generator(historical_generator, historical_inventory)
    independently_reconstructed = reconstruct_historical_generator_output(historical_generator, historical_inventory)
    historical_sha = sha256_bytes(historical_ledger)
    primary_sha = sha256_bytes(primary_regenerated)
    reconstruction_sha = sha256_bytes(independently_reconstructed)
    generator_binding_status = "PROVEN" if historical_ledger == primary_regenerated == independently_reconstructed else "CONFLICTING"
    return {
        "history": history,
        "historical_blobs": {
            "ledger_git_blob_sha": git_blob_sha(repo_root, introduction_commit, LEDGER_RELATIVE_PATH),
            "sidecar_git_blob_sha": git_blob_sha(repo_root, introduction_commit, SIDECAR_RELATIVE_PATH),
            "generator_git_blob_sha": git_blob_sha(repo_root, introduction_commit, GENERATOR_RELATIVE_PATH),
            "inventory_git_blob_sha": git_blob_sha(repo_root, introduction_commit, INVENTORY_RELATIVE_PATH),
            "historical_ledger_physical_sha256": historical_sha,
            "historical_generator_content_sha256": sha256_bytes(historical_generator),
            "current_ledger_git_blob_sha": str(run_git(repo_root, "rev-parse", f"HEAD:{LEDGER_RELATIVE_PATH}")).strip(),
            "current_generator_git_blob_sha": str(run_git(repo_root, "rev-parse", f"HEAD:{GENERATOR_RELATIVE_PATH}")).strip(),
            "current_ledger_physical_sha256": sha256_bytes(current_ledger),
            "current_generator_content_sha256": sha256_bytes(current_generator),
            "historical_current_ledger_equality": historical_ledger == current_ledger,
            "historical_current_generator_equality": historical_generator == current_generator,
            "historical_sidecar_matches_ledger": sidecar_token == historical_sha,
        },
        "generator_output_binding": {
            "status": generator_binding_status,
            "historical_committed_sha256": historical_sha,
            "primary_regenerated_sha256": primary_sha,
            "independent_reconstruction_sha256": reconstruction_sha,
            "byte_equality": historical_ledger == primary_regenerated == independently_reconstructed,
            "semantic_equality": json.loads(historical_ledger) == json.loads(primary_regenerated) == json.loads(independently_reconstructed),
        },
        "historical_inventory": json.loads(historical_inventory),
    }


def derive_ownership(ledger_bytes: bytes, historical_inventory: Mapping[str, Any]) -> dict[str, Any]:
    payload = json.loads(ledger_bytes)
    embedded = sorted({str(record.get("strategy_or_hypothesis_id") or "") for record in payload.get("records", []) if record.get("strategy_or_hypothesis_id")})
    canonical_inventory_ids = {
        str(entry.get("id"))
        for entry in historical_inventory.get("entities", [])
        if entry.get("counted_as_strategy") and entry.get("id")
    }
    mapping = {owner: owner if owner in canonical_inventory_ids else None for owner in embedded}
    return {
        "embedded_row_owner_ids": embedded,
        "embedded_row_owner_field_authority": "PROVEN" if embedded else "UNRESOLVED",
        "canonical_strategy_mapping": mapping,
        "canonical_strategy_mapping_authority": "PROVEN_WITH_LIMITATIONS" if any(value for value in mapping.values()) else "UNRESOLVED",
        "canonical_strategy_ids": sorted(value for value in mapping.values() if value),
        "unmapped_historical_owner_labels": sorted(owner for owner, value in mapping.items() if value is None),
        "aggregate_ledger_owner_model": "MULTI_OWNER_PLACEHOLDER_INVENTORY",
        "aggregate_canonical_strategy_id": None,
    }


def derive_invalidation(repo_root: Path, historical_binding: Mapping[str, Any], *, expected_ledger_sha256: str = EXPECTED_LEDGER_SHA256) -> dict[str, Any]:
    path = repo_root / INVALIDATION_RELATIVE_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    history = historical_binding["history"]
    introduction_commit = history.get("introduction_commit")
    direct = "CONFIRMED" if payload.get("ledger_sha256") == expected_ledger_sha256 else "UNRESOLVED"
    implementation = (
        "CONFIRMED"
        if payload.get("previous_head") == introduction_commit and GENERATOR_RELATIVE_PATH in payload.get("scope", [])
        else "UNRESOLVED"
    )
    binding = historical_binding["generator_output_binding"]
    blobs = historical_binding["historical_blobs"]
    derived = (
        "CONFIRMED"
        if implementation == "CONFIRMED"
        and binding.get("status") == "PROVEN"
        and blobs.get("historical_current_ledger_equality") is True
        and blobs.get("historical_ledger_physical_sha256") == expected_ledger_sha256
        else "UNRESOLVED"
    )
    return {
        "invalidation_path": INVALIDATION_RELATIVE_PATH,
        "invalidation_sha256": sha256_bytes(path.read_bytes()),
        "decision": payload.get("decision"),
        "direct_ledger_invalidation_authority": direct,
        "implementation_invalidation_authority": implementation,
        "derived_ledger_invalidation_authority": derived,
        "derived_reason_code": "DERIVED_THROUGH_PROVEN_INVALIDATED_GENERATOR_BINDING" if derived == "CONFIRMED" else None,
        "immutable_payload": payload,
    }


def _candidate_files(root: Path, *, repo_root: Path | None = None) -> list[Path]:
    if repo_root is not None and root == repo_root:
        tracked = str(run_git(repo_root, "ls-files")).splitlines()
        return [repo_root / path for path in tracked]
    candidates: list[Path] = []
    if not root.exists():
        return candidates
    for path in root.rglob("*"):
        if path.is_file():
            candidates.append(path)
    return candidates


def search_non_outcome_provenance(
    repo_root: Path,
    external_roots: Iterable[Path] = (),
    *,
    max_bytes: int = 2_000_000,
    ledger_sha256: str = EXPECTED_LEDGER_SHA256,
    row_count: int = EXPECTED_ROW_COUNT,
) -> list[dict[str, Any]]:
    terms = [ledger_sha256, f"{ledger_sha256}:{row_count}", GENERATOR_RELATIVE_PATH, EXPECTED_INTRODUCTION_COMMIT]
    records: list[dict[str, Any]] = []
    roots = [("repository", repo_root, repo_root)] + [(f"external_{index}", root, None) for index, root in enumerate(external_roots, start=1)]
    for search_id, root, git_root in roots:
        candidate_paths = _candidate_files(root, repo_root=git_root)
        inspected: list[str] = []
        matches: list[dict[str, Any]] = []
        errors: list[str] = []
        excluded: list[str] = []
        for path in candidate_paths:
            relative = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
            lower = relative.lower()
            if any(marker in lower for marker in FORBIDDEN_CONTENT_MARKERS):
                excluded.append(relative)
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                size = path.stat().st_size
                if size > max_bytes:
                    excluded.append(relative)
                    continue
                text = path.read_text(encoding="utf-8", errors="strict")
            except (OSError, UnicodeError) as exc:
                errors.append(f"{relative}:{type(exc).__name__}")
                continue
            inspected.append(relative)
            hit_terms = [term for term in terms if term in text]
            if hit_terms:
                matches.append({"semantic_path": relative, "matched_terms": hit_terms, "sha256": sha256_bytes(text.encode("utf-8"))})
        records.append(
            {
                "search_id": search_id,
                "root_identity": root.name if search_id != "repository" else "repository",
                "root_exists": root.exists(),
                "query_terms": terms,
                "file_inclusion_rules": sorted(TEXT_SUFFIXES),
                "file_exclusion_markers": list(FORBIDDEN_CONTENT_MARKERS),
                "candidate_count": len(candidate_paths),
                "inspected_candidate_count": len(inspected),
                "inspected_candidate_paths": inspected,
                "excluded_candidate_count": len(excluded),
                "matching_records": matches,
                "errors": errors,
                "search_completed": root.exists() and not errors,
            }
        )
    return records
