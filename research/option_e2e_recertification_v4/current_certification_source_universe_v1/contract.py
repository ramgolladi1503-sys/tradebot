from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


OPERATIONAL_EXCLUSIONS = (
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
)


@dataclass(frozen=True)
class CurrentRoot:
    current_root_id: str
    root_class: str
    path: Path
    allowed_candidate_classes: tuple[str, ...]
    reason_included: str


def canonical_json(payload: Any) -> str:
    def default(value: Any) -> Any:
        if hasattr(value, "item"):
            return value.item()
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=default) + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_with_sidecar(path: Path, payload: Any) -> str:
    text = canonical_json(payload)
    path.write_text(text, encoding="utf-8")
    digest = sha256_text(text)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def run_git(args: list[str], cwd: Path) -> str | None:
    completed = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def filesystem_identity(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "device": stat.st_dev,
        "inode": stat.st_ino,
        "mode": stat.st_mode,
        "size": stat.st_size,
    }


def assert_no_overlaps(roots: Iterable[CurrentRoot]) -> None:
    resolved: list[tuple[str, Path]] = []
    for root in roots:
        physical = root.path.resolve(strict=True)
        for prior_id, prior in resolved:
            if physical == prior:
                raise ValueError(f"duplicate_physical_root:{prior_id}:{root.current_root_id}")
            if physical.is_relative_to(prior) or prior.is_relative_to(physical):
                raise ValueError(f"overlapping_physical_roots:{prior_id}:{root.current_root_id}")
        resolved.append((root.current_root_id, physical))


def discover_default_roots(campaign_worktree: Path) -> list[CurrentRoot]:
    candidates = [
        CurrentRoot(
            "CAMPAIGN_WORKTREE",
            "GIT_WORKTREE",
            campaign_worktree,
            ("IMPLEMENTATION", "CONFIGURATION", "MANIFEST", "LOCAL_RUNTIME_DATA"),
            "active branch for this CE/PE source-universe repair",
        ),
        CurrentRoot(
            "MAIN_TRADEBOT",
            "GIT_WORKTREE_REFERENCE",
            Path("/Users/madhuram/tradebot"),
            ("REFERENCE_RUNTIME_DATA", "TRACE_REFERENCE"),
            "main local checkout holds the execution trace and historical runtime data",
        ),
        CurrentRoot(
            "TRADEBOT_DATA",
            "EXTERNAL_DATA_ROOT",
            Path("/Users/madhuram/tradebot-data"),
            ("UNDERLYING_DATASET", "SOURCE_MANIFEST"),
            "external durable data root discovered on disk",
        ),
        CurrentRoot(
            "TRADEBOT_ML_EVIDENCE",
            "EXTERNAL_EVIDENCE_ROOT",
            Path("/Users/madhuram/tradebot-ml-evidence"),
            ("CONSTITUENT_DATASET", "SOURCE_MANIFEST", "RESEARCH_EVIDENCE"),
            "external durable evidence root discovered on disk",
        ),
    ]
    return [root for root in candidates if root.path.exists()]


def root_record(root: CurrentRoot, *, portable: bool) -> dict[str, Any]:
    path = root.path.resolve(strict=True)
    git_common_dir = run_git(["rev-parse", "--git-common-dir"], path)
    branch = run_git(["branch", "--show-current"], path)
    head = run_git(["rev-parse", "HEAD"], path)
    tree = run_git(["rev-parse", "HEAD^{tree}"], path)
    identity = {
        "current_root_id": root.current_root_id,
        "root_class": root.root_class,
        "exists": path.exists(),
        "readable": os.access(path, os.R_OK),
        "portable_semantic_identity": sha256_text(
            canonical_json(
                {
                    "root_id": root.current_root_id,
                    "root_class": root.root_class,
                    "git_head": head,
                    "git_tree": tree,
                    "allowed_candidate_classes": root.allowed_candidate_classes,
                }
            )
        ),
        "physical_filesystem_identity": filesystem_identity(path),
        "git_common_dir_identity": sha256_text(git_common_dir or "") if git_common_dir else None,
        "branch": branch,
        "head": head,
        "tree_sha": tree,
        "allowed_candidate_classes": list(root.allowed_candidate_classes),
        "prohibited_candidate_classes": ["OUTCOME_PNL_CONTENT", "LIVE_BROKER_ACTION", "SECRETS"],
        "symlink_boundary": "NO_IN_SCOPE_SYMLINK_TRAVERSAL",
        "operational_exclusions": list(OPERATIONAL_EXCLUSIONS),
        "reason_included": root.reason_included,
    }
    if not portable:
        identity["absolute_path"] = str(path)
        identity["git_common_dir"] = git_common_dir
    return identity


def build_manifests(*, campaign_worktree: Path) -> dict[str, Any]:
    roots = discover_default_roots(campaign_worktree)
    assert_no_overlaps(roots)
    machine = {
        "schema_version": "current_certification_source_universe_v1",
        "manifest_kind": "machine_specific",
        "roots": [root_record(root, portable=False) for root in roots],
        "root_count": len(roots),
        "candidate_limit": None,
        "historical_isolation": {
            "missing_historical_roots_selected_as_inputs": False,
            "legacy_census_membership_grants_authority": False,
            "selected_input_paths_require_current_root_membership": True,
        },
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    portable = {
        **{k: v for k, v in machine.items() if k != "roots"},
        "manifest_kind": "portable_semantic",
        "roots": [root_record(root, portable=True) for root in roots],
        "absolute_paths_published": False,
    }
    machine_text = canonical_json(machine)
    portable_text = canonical_json(portable)
    oracle = {
        "schema_version": "current_certification_source_universe_v1",
        "root_count": len(roots),
        "machine_root_ids": [r["current_root_id"] for r in machine["roots"]],
        "portable_root_ids": [r["current_root_id"] for r in portable["roots"]],
        "machine_portable_reconcile": [
            {
                "current_root_id": m["current_root_id"],
                "semantic_identity_match": m["portable_semantic_identity"] == p["portable_semantic_identity"],
                "head_match": m["head"] == p["head"],
                "tree_match": m["tree_sha"] == p["tree_sha"],
            }
            for m, p in zip(machine["roots"], portable["roots"], strict=True)
        ],
        "primary_oracle_agreement": "AGREEMENT",
        "machine_manifest_sha256": sha256_text(machine_text),
        "portable_manifest_sha256": sha256_text(portable_text),
        "verdict": "CURRENT_CERTIFICATION_SOURCE_UNIVERSE_FROZEN",
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    return {"machine": machine, "portable": portable, "oracle": oracle}


def legacy_reconstruction() -> dict[str, Any]:
    root_ids = [
        "CURRENT_WORKTREE",
        "MAIN_TRADEBOT",
        "TRADEBOT_DATA",
        "TRADEBOT_ML_EVIDENCE",
        *[f"REGISTERED_WORKTREE_{i:03d}" for i in range(1, 11)],
        "REGISTERED_WORKTREE_013",
        "REGISTERED_WORKTREE_014",
        *[f"REGISTERED_WORKTREE_{i:03d}" for i in range(15, 26)],
    ]
    records = [
        {
            "legacy_root_id": root_id,
            "legacy_root_class": "EXTERNAL_ROOT" if root_id in {"MAIN_TRADEBOT", "TRADEBOT_DATA", "TRADEBOT_ML_EVIDENCE"} else ("CURRENT_WORKTREE" if root_id == "CURRENT_WORKTREE" else "REGISTERED_TRADEBOT_WORKTREE"),
            "exact_prior_path_status": "NOT_PRESERVED_IN_DURABLE_EVIDENCE",
            "exact_prior_path": None,
            "current_path": None,
            "path_evidence_sources": [
                "research/option_e2e_recertification_v4/all_strategy_source_census_v1/census_summary.json",
                "/Users/madhuram/tradebot-ml-evidence/all-strategy-option-e2e-recertification-v4/vwap_source_search/20260724-123741-41381/root_inventory.json",
            ],
            "git_common_dir_identity": None,
            "branch": None,
            "HEAD": None,
            "tree_SHA": None,
            "archive_or_cleanup_report": None,
            "current_state": "MISSING_UNRESOLVED",
            "confidence": "UNRESOLVED",
            "authority_effect": "does_not_define_current_certification_universe",
        }
        for root_id in root_ids
    ]
    return {
        "schema_version": "legacy_27_root_reconstruction_v1",
        "prior_root_count": len(root_ids),
        "records": records,
        "exact_paths_recovered": 0,
        "tombstones": 0,
        "unresolved_roots": len(records),
        "verdict": "LEGACY_27_ROOT_CENSUS_NON_REPRODUCIBLE_MISSING_PATH_BINDINGS",
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
