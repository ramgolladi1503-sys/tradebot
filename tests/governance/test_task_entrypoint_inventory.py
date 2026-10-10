from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"
INVENTORY = ROOT / "governance/evidence/ENTRYPOINT_INVENTORY.json"
FREEZE_WORKFLOW = WORKFLOWS / "repo-forensics-pr-gate.yml"
REVIEWED_BASE_DISPATCH_PATHS = frozenset({
    ".github/workflows/agentic-qa-evidence-auditor.yml",
    ".github/workflows/agentic-research-integration.yml",
    ".github/workflows/ai-reliability-pr763-certification.yml",
    ".github/workflows/candidate-ml-v2.yml",
    ".github/workflows/cas-closing-auction-shadow-v1.yml",
    ".github/workflows/code-excellence-gates.yml",
    ".github/workflows/feed-resource-soak.yml",
    ".github/workflows/frozen-head-exact-sha-certification.yml",
    ".github/workflows/loop-handoff-gate.yml",
    ".github/workflows/market_story_engine_v1.yml",
    ".github/workflows/meg-shadow-system-certification.yml",
    ".github/workflows/portfolio-ci.yml",
    ".github/workflows/pr782-remaining-evidence-contracts.yml",
    ".github/workflows/pr818-apply-safe-test-contract-repairs.yml",
    ".github/workflows/prospective-market-evidence-v1.yml",
    ".github/workflows/subscription-reconciliation-postclose-v1.yml",
    ".github/workflows/tradebot-mcp.yml",
    ".github/workflows/upstox_offline_v3_repair.yml",
    ".github/workflows/upstox_v3_depth_capture_contract.yml",
})


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _protected_script() -> str:
    workflow = yaml.safe_load(FREEZE_WORKFLOW.read_text(encoding="utf-8"))
    target = workflow["jobs"]["pr818-live-flow-freeze-target"]
    step = next(step for step in target["steps"]
                if step.get("name") == "Enforce frozen PR818 live-flow production surface")
    return step["run"]


def _has_workflow_dispatch(yaml_text: str) -> bool:
    """Read GitHub event syntax without YAML 1.1 coercing the `on` key."""
    workflow = yaml.load(yaml_text, Loader=yaml.BaseLoader)
    if not isinstance(workflow, dict):
        return False
    events = workflow.get("on")
    if isinstance(events, dict):
        return "workflow_dispatch" in events
    if isinstance(events, (list, tuple)):
        return "workflow_dispatch" in events
    return events == "workflow_dispatch"


def _active_dispatch_workflow_paths(directory: Path) -> set[str]:
    return {
        f".github/workflows/{path.name}"
        for path in directory.iterdir()
        if path.is_file() and path.suffix in {".yml", ".yaml"}
        if _has_workflow_dispatch(path.read_text(encoding="utf-8"))
    }


def _inventory_matches_active(inventory_paths: set[str], scanned_paths: set[str]) -> bool:
    return inventory_paths == scanned_paths


def _run_protected_script(repo: Path, *, base: str, head: str, head_ref: str):
    env = dict(os.environ)
    env.update({
        "PR_HEAD": head,
        "PR_BASE": base,
        "PR_HEAD_REF": head_ref,
        "PR818_FROZEN_LIVE_SHA": "d7dc45e7c5c76247e7d1b8abd40ec7682fac2f9b",
    })
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", _protected_script()],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", message)
    _git(repo, "push", "origin", "main")
    return _git(repo, "rev-parse", "HEAD")


def test_inventory_covers_all_active_dispatch_workflows_and_retired_pr818():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    actual = _active_dispatch_workflow_paths(WORKFLOWS)
    active = {entry["path"] for entry in inventory["active_workflow_dispatch_entrypoints"]}
    retired = inventory["retired_workflow_dispatch_entrypoints"]
    retired_paths = {entry["path"] for entry in retired}
    recorded_base_paths = active | retired_paths

    assert inventory["reviewed_base_sha"] == "32e6d77130b748b6644e93376fe948b3cd7b9eb9"
    assert recorded_base_paths == REVIEWED_BASE_DISPATCH_PATHS
    assert len(REVIEWED_BASE_DISPATCH_PATHS) == 19
    assert active.isdisjoint(retired_paths)
    assert _inventory_matches_active(active, actual)
    assert len(actual) == 18
    assert len(retired) == 1
    assert retired[0]["path"] == ".github/workflows/pr818-apply-safe-test-contract-repairs.yml"
    assert retired[0]["status"] == "RETIRED"
    assert retired[0]["evidence"]["pull_request"].endswith("/pull/823")
    assert not (WORKFLOWS / "pr818-apply-safe-test-contract-repairs.yml").exists()
    assert len(actual) + len(retired) == 19
    assert all(entry["prework_admission"] == "UNSATISFIED" for entry in inventory["active_workflow_dispatch_entrypoints"])
    assert inventory["repository_gaps"]["universal_platform_intake"] == "UNSATISFIED"
    assert inventory["repository_gaps"]["branch_protection_requires_evidence_gate"] == "UNSATISFIED"
    assert inventory["repository_gaps"]["authenticated_human_identity_approval"] == "UNSATISFIED"


def test_dispatch_scanner_handles_event_shorthand_and_unlisted_workflow(tmp_path):
    sequence_form = "name: sequence\non: [push, workflow_dispatch]\njobs: {}\n"
    inline_mapping_form = "name: mapping\non: {push: {}, workflow_dispatch: {}}\njobs: {}\n"
    mapping_form = "name: block mapping\non:\n  push:\n  workflow_dispatch:\njobs: {}\n"
    assert _has_workflow_dispatch(sequence_form)
    assert _has_workflow_dispatch(inline_mapping_form)
    assert _has_workflow_dispatch(mapping_form)

    new_workflow = tmp_path / "unlisted.yml"
    new_workflow.write_text(sequence_form, encoding="utf-8")
    scanned_with_new_workflow = _active_dispatch_workflow_paths(WORKFLOWS) | _active_dispatch_workflow_paths(tmp_path)
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    recorded_active = {entry["path"] for entry in inventory["active_workflow_dispatch_entrypoints"]}
    assert not _inventory_matches_active(recorded_active, scanned_with_new_workflow)


def test_protected_freeze_gate_compares_pr_delta_without_failing_on_old_base_drift(tmp_path):
    repo = tmp_path / "repo"
    bare = tmp_path / "remote.git"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "remote", "add", "origin", str(bare))
    (repo / "core/feed").mkdir(parents=True)
    (repo / "core/feed/frozen.py").write_text("VALUE = 0\n", encoding="utf-8")
    old_baseline = _commit(repo, "old baseline")
    (repo / "core/feed/frozen.py").write_text("VALUE = 1\n", encoding="utf-8")
    drifted_base = _commit(repo, "already present on base")

    # Existing protected-path drift between the old baseline and PR base is
    # deliberately ignored; the base-to-head PR delta is empty and passes.
    passed = _run_protected_script(repo, base=drifted_base, head=drifted_base, head_ref="topic")
    assert passed.returncode == 0, passed.stderr + passed.stdout
    assert "PR818_FROZEN_LIVE_FLOW_PRESERVED" in passed.stdout

    (repo / "core/feed/frozen.py").write_text("VALUE = 2\n", encoding="utf-8")
    protected_head = _commit(repo, "protected path changed in PR")
    failed = _run_protected_script(repo, base=drifted_base, head=protected_head, head_ref="topic")
    assert failed.returncode != 0
    assert "PR818_FROZEN_LIVE_FLOW_VIOLATION" in failed.stdout
    assert "core/feed/frozen.py" in failed.stdout

    (repo / ".github/workflows").mkdir(parents=True)
    freeze_file = repo / ".github/workflows/repo-forensics-pr-gate.yml"
    freeze_file.write_text("name: governed workflow edit\n", encoding="utf-8")
    bootstrap_head = _commit(repo, "workflow bootstrap edit")
    bootstrap = _run_protected_script(
        repo,
        base=protected_head,
        head=bootstrap_head,
        head_ref="governance/freeze-pr818-live-flow-finalize-v1",
    )
    assert bootstrap.returncode == 0, bootstrap.stderr + bootstrap.stdout
    assert "PR818_FREEZE_BOOTSTRAP_FINALIZE_ONLY" in bootstrap.stdout

    ordinary_branch = _run_protected_script(
        repo, base=protected_head, head=bootstrap_head, head_ref="topic"
    )
    assert ordinary_branch.returncode != 0
    assert "PR818_FROZEN_LIVE_FLOW_VIOLATION" in ordinary_branch.stdout

    script = _protected_script()
    assert "PR818_FROZEN_MAIN_BASELINE" not in script
    assert "PR818_FROZEN_MAIN_BASELINE_DRIFT" not in script
    assert "git diff --name-only \"$PR_BASE\" \"$PR_HEAD\"" in script
    assert old_baseline != drifted_base
