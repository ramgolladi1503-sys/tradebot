#!/usr/bin/env python3
"""Core primitives for GitHub-first engineering loop handoffs.

This module is deliberately standard-library only and has no imports from TradeBot
runtime, broker, execution, risk, feed, or strategy code.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

TASK_ID_RE = re.compile(r"^(?:LOOP-\d{8}-\d{3}|LOOP-EXAMPLE)$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SECRET_RE = re.compile(
    r"(?i)(access[_-]?token|api[_-]?key|authorization|password|secret|session[_-]?token)"
    r"\s*[:=]\s*([^\s,;]+)"
)
SUCCESS_STATES = {
    "OFFLINE_CERTIFIED",
    "READY_FOR_CONFIRMATION",
    "READY_FOR_MERGE_RECOMMENDATION",
    "DONE",
}
TERMINAL_STATES = {"DONE", "FAILED", "CANCELLED"}
HIGH_RISK_PREFIXES = (
    "main.py",
    "run_live.sh",
    "config/",
    "credentials.py",
    "core/execution",
    "core/broker",
    "core/order",
    "core/risk",
    "core/feed",
    "core/option_token_resolver.py",
    "core/runtime_safety_boot_guard.py",
    "strategies/",
)
FRAMEWORK_ROOTS = (".loop/", "scripts/loop/", "tests/loop/", "loop_tasks/", "docs/engineering/")


class LoopValidationError(ValueError):
    """Raised for a malformed or unsupported loop operation."""


def repo_root_from(path: Path | None = None) -> Path:
    if path is not None:
        return path.resolve()
    return Path(__file__).resolve().parents[2]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LoopValidationError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LoopValidationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise LoopValidationError(f"expected JSON object in {path}")
    return payload


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact_text(value: str, *, max_chars: int = 4000) -> str:
    clipped = value[:max_chars]
    return SECRET_RE.sub(lambda match: f"{match.group(1)}=<redacted>", clipped)


def run_git(repo_root: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise LoopValidationError(
            f"git {' '.join(args)} failed ({proc.returncode}): {redact_text(proc.stderr.strip())}"
        )
    return proc.stdout.strip()


def current_head(repo_root: Path) -> str:
    return run_git(repo_root, "rev-parse", "HEAD")


def current_branch(repo_root: Path) -> str:
    return run_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")


def git_is_clean(repo_root: Path) -> bool:
    return not bool(run_git(repo_root, "status", "--porcelain"))


def is_ancestor(repo_root: Path, ancestor: str, descendant: str = "HEAD") -> bool:
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def changed_paths(repo_root: Path, base_sha: str, code_sha: str) -> list[str]:
    output = run_git(repo_root, "diff", "--name-only", f"{base_sha}..{code_sha}")
    return sorted({line.strip() for line in output.splitlines() if line.strip()})


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _gate_ids(contract: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for gate in _list(contract.get("acceptance_gates")):
        if isinstance(gate, str):
            result.append(gate)
        elif isinstance(gate, Mapping) and gate.get("gate_id"):
            result.append(str(gate["gate_id"]))
    return result


def _human_gate_ids(contract: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for gate in _list(contract.get("human_gates")):
        if isinstance(gate, str):
            result.add(gate)
        elif isinstance(gate, Mapping) and gate.get("gate_id"):
            result.add(str(gate["gate_id"]))
    return result


def _pattern_match(path: str, pattern: str) -> bool:
    normalized = pattern.strip().lstrip("./")
    if not normalized:
        return False
    if normalized.endswith("/**"):
        prefix = normalized[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    if normalized.endswith("/"):
        return path.startswith(normalized)
    if any(char in normalized for char in "*?["):
        return fnmatch.fnmatch(path, normalized)
    return path == normalized or path.startswith(normalized.rstrip("/") + "/")


def path_in_scope(path: str, allowed: Sequence[str], forbidden: Sequence[str]) -> tuple[bool, str]:
    if any(_pattern_match(path, pattern) for pattern in forbidden):
        return False, "forbidden"
    if any(_pattern_match(path, pattern) for pattern in allowed):
        return True, "allowed"
    return False, "outside_allowed_paths"


def _is_absolute_or_local_only(reference: str) -> bool:
    return reference.startswith("/") or reference.startswith("~") or bool(re.match(r"^[A-Za-z]:[\\/]", reference))


def load_transitions(repo_root: Path) -> dict[str, list[str]]:
    payload = read_json(repo_root / ".loop" / "policies" / "transitions.json")
    transitions = payload.get("transitions")
    if not isinstance(transitions, dict):
        raise LoopValidationError("transitions policy is missing transitions object")
    return {str(key): [str(item) for item in _list(value)] for key, value in transitions.items()}


def validate_contract(contract: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    required = (
        "schema_version",
        "task_id",
        "title",
        "objective",
        "repository",
        "base_branch",
        "work_branch",
        "allowed_paths",
        "forbidden_paths",
        "acceptance_gates",
        "required_tests",
        "human_gates",
        "stop_conditions",
        "max_implementation_cycles",
        "max_review_cycles",
        "frozen",
    )
    for field in required:
        if field not in contract:
            errors.append(f"contract missing field: {field}")
    task_id = str(contract.get("task_id") or "")
    if not TASK_ID_RE.fullmatch(task_id):
        errors.append(f"invalid task_id: {task_id!r}")
    allowed = _list(contract.get("allowed_paths"))
    if not allowed or not all(isinstance(item, str) and item.strip() for item in allowed):
        errors.append("allowed_paths must contain at least one non-empty path pattern")
    if not isinstance(contract.get("forbidden_paths"), list):
        errors.append("forbidden_paths must be a list")
    if contract.get("frozen") is not True:
        errors.append("contract must be frozen before implementation")
    for field in ("max_implementation_cycles", "max_review_cycles"):
        try:
            if int(contract.get(field, 0)) < 1:
                errors.append(f"{field} must be >= 1")
        except (TypeError, ValueError):
            errors.append(f"{field} must be an integer")
    return errors


def _validate_transition(state: Mapping[str, Any], transitions: Mapping[str, Sequence[str]]) -> list[str]:
    errors: list[str] = []
    current = str(state.get("state") or "")
    previous = state.get("previous_state")
    if current not in transitions:
        errors.append(f"unknown lifecycle state: {current!r}")
        return errors
    if previous in (None, ""):
        if current != "NEW":
            errors.append("only NEW may omit previous_state")
    else:
        previous_text = str(previous)
        if previous_text not in transitions:
            errors.append(f"unknown previous_state: {previous_text!r}")
        elif previous_text != current and current not in transitions[previous_text]:
            errors.append(f"illegal transition: {previous_text} -> {current}")
    return errors


def _validate_evidence(task_dir: Path, evidence: Mapping[str, Any]) -> tuple[list[str], dict[str, Mapping[str, Any]]]:
    errors: list[str] = []
    proof_map: dict[str, Mapping[str, Any]] = {}
    for proof in _list(evidence.get("proofs")):
        if not isinstance(proof, Mapping):
            errors.append("evidence proof must be an object")
            continue
        proof_id = str(proof.get("proof_id") or "")
        if not proof_id:
            errors.append("evidence proof missing proof_id")
            continue
        if proof_id in proof_map:
            errors.append(f"duplicate proof_id: {proof_id}")
            continue
        proof_map[proof_id] = proof
        tier = str(proof.get("tier") or "")
        evidence_class = str(proof.get("evidence_class") or "")
        if tier not in {"A", "B", "C"}:
            errors.append(f"{proof_id}: invalid evidence tier {tier!r}")
        if evidence_class not in {"static", "test", "ci", "review", "live", "replay", "synthetic"}:
            errors.append(f"{proof_id}: invalid evidence_class {evidence_class!r}")
        reference = str(proof.get("reference") or "")
        if _is_absolute_or_local_only(reference):
            errors.append(f"{proof_id}: absolute/local path cannot be authoritative evidence")
        if tier == "C" and proof.get("continuation_critical"):
            errors.append(f"{proof_id}: tier C evidence cannot be continuation-critical")
        if str(proof.get("evidence_type") or "") == "file" and tier == "A":
            if not reference:
                errors.append(f"{proof_id}: file evidence missing reference")
                continue
            path = (task_dir / reference).resolve() if not reference.startswith("loop_tasks/") else (task_dir.parents[1] / reference).resolve()
            # Prefer task-relative references; repo-relative loop_tasks paths are also accepted.
            if not path.is_file():
                alternate = task_dir / reference
                if alternate.is_file():
                    path = alternate
                else:
                    errors.append(f"{proof_id}: evidence file does not exist: {reference}")
                    continue
            claimed = str(proof.get("sha256") or "")
            if not claimed:
                errors.append(f"{proof_id}: immutable file evidence missing sha256")
            elif claimed != sha256_file(path):
                errors.append(f"{proof_id}: evidence sha256 mismatch")
        if proof.get("required") and int(proof.get("exit_code", 0) or 0) != 0:
            errors.append(f"{proof_id}: required evidence command failed")
    return errors, proof_map


def _validate_claims(claims: Mapping[str, Any], proof_map: Mapping[str, Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    claim_ids: set[str] = set()
    for claim in _list(claims.get("claims")):
        if not isinstance(claim, Mapping):
            errors.append("claim must be an object")
            continue
        claim_id = str(claim.get("claim_id") or "")
        if not claim_id:
            errors.append("claim missing claim_id")
            continue
        if claim_id in claim_ids:
            errors.append(f"duplicate claim_id: {claim_id}")
        claim_ids.add(claim_id)
        status = str(claim.get("status") or "")
        proof_ids = [str(item) for item in _list(claim.get("proof_ids"))]
        if status == "PROVEN" and not proof_ids:
            errors.append(f"{claim_id}: PROVEN claim has no proof_ids")
        missing = [proof_id for proof_id in proof_ids if proof_id not in proof_map]
        if missing:
            errors.append(f"{claim_id}: missing proof IDs: {', '.join(missing)}")
        if claim.get("requires_live_evidence") and status == "PROVEN":
            if not any(str(proof_map.get(proof_id, {}).get("evidence_class")) == "live" for proof_id in proof_ids):
                errors.append(f"{claim_id}: live claim lacks live evidence")
    return errors


def validate_task(task_dir: Path, *, repo_root: Path | None = None, check_git: bool = True) -> list[str]:
    root = repo_root_from(repo_root)
    task_dir = task_dir.resolve()
    errors: list[str] = []
    contract = read_json(task_dir / "contract.json")
    state = read_json(task_dir / "state.json")
    handoff = read_json(task_dir / "handoff.json")
    claims = read_json(task_dir / "claims.json")
    evidence = read_json(task_dir / "evidence" / "manifest.json")

    errors.extend(validate_contract(contract))
    if str(state.get("task_id") or "") != str(contract.get("task_id") or ""):
        errors.append("state task_id does not match contract")
    if str(handoff.get("task_id") or "") != str(contract.get("task_id") or ""):
        errors.append("handoff task_id does not match contract")
    transitions = load_transitions(root)
    errors.extend(_validate_transition(state, transitions))

    try:
        cycle = int(state.get("cycle", 0))
        max_cycles = int(contract.get("max_implementation_cycles", 0)) + int(contract.get("max_review_cycles", 0))
        if cycle < 0:
            errors.append("cycle must be non-negative")
        if cycle > max_cycles:
            errors.append(f"cycle budget exhausted: {cycle} > {max_cycles}")
    except (TypeError, ValueError):
        errors.append("state cycle must be an integer")

    blockers = _list(state.get("blockers"))
    current_state = str(state.get("state") or "")
    completed = {str(item) for item in _list(state.get("completed_gate_ids"))}
    failed = {str(item) for item in _list(state.get("failed_gate_ids"))}
    all_gates = set(_gate_ids(contract))
    if current_state in SUCCESS_STATES and blockers:
        errors.append(f"{current_state} cannot have unresolved blockers")
    if current_state == "DONE":
        missing_gates = sorted(all_gates - completed)
        if missing_gates:
            errors.append(f"DONE missing acceptance gates: {', '.join(missing_gates)}")
        if failed:
            errors.append("DONE cannot contain failed gates")
    if current_state == "BLOCKED" and not blockers:
        errors.append("BLOCKED state requires at least one blocker")

    evidence_errors, proof_map = _validate_evidence(task_dir, evidence)
    errors.extend(evidence_errors)
    errors.extend(_validate_claims(claims, proof_map))

    for result in _list(handoff.get("test_results")):
        if isinstance(result, Mapping) and result.get("required") and int(result.get("exit_code", 0) or 0) != 0:
            if current_state in SUCCESS_STATES:
                errors.append(f"success state contains failed required test: {result.get('test_id') or result.get('command')}")

    if handoff.get("all_continuation_critical_artifacts_in_github") is not True:
        errors.append("handoff must confirm all continuation-critical artifacts are in GitHub")

    code_sha = str(state.get("code_sha") or "")
    base_sha = str(state.get("base_sha") or "")
    if code_sha and not SHA_RE.fullmatch(code_sha):
        errors.append("state code_sha must be a 40-character lowercase SHA")
    if base_sha and not SHA_RE.fullmatch(base_sha):
        errors.append("state base_sha must be a 40-character lowercase SHA")

    if check_git and SHA_RE.fullmatch(code_sha) and SHA_RE.fullmatch(base_sha):
        if not is_ancestor(root, code_sha, "HEAD"):
            errors.append("code_sha is not an ancestor of checkpoint HEAD")
        try:
            paths = changed_paths(root, base_sha, code_sha)
        except LoopValidationError as exc:
            errors.append(str(exc))
            paths = []
        allowed = [str(item) for item in _list(contract.get("allowed_paths"))]
        forbidden = [str(item) for item in _list(contract.get("forbidden_paths"))]
        task_prefix = task_dir.relative_to(root).as_posix().rstrip("/") + "/"
        high_risk_changed = False
        for path in paths:
            if path.startswith(task_prefix):
                continue
            ok, reason = path_in_scope(path, allowed, forbidden)
            if not ok:
                errors.append(f"scope violation ({reason}): {path}")
            if any(path == prefix or path.startswith(prefix) for prefix in HIGH_RISK_PREFIXES):
                high_risk_changed = True
        if high_risk_changed and "high_risk_path_change" not in _human_gate_ids(contract):
            errors.append("high-risk path changed without high_risk_path_change human gate")

    return errors


def recommend_next_action(contract: Mapping[str, Any], state: Mapping[str, Any], handoff: Mapping[str, Any]) -> dict[str, str]:
    current = str(state.get("state") or "NEW")
    blockers = _list(state.get("blockers"))
    failed_tests = [
        item
        for item in _list(handoff.get("test_results"))
        if isinstance(item, Mapping) and item.get("required") and int(item.get("exit_code", 0) or 0) != 0
    ]
    unresolved = _list(handoff.get("unresolved_findings"))
    completed = {str(item) for item in _list(state.get("completed_gate_ids"))}
    gate_ids = set(_gate_ids(contract))

    if blockers:
        return {"state": "BLOCKED", "next_action": "Resolve the first recorded blocker without expanding scope."}
    if failed_tests or unresolved:
        return {"state": "REPAIRING", "next_action": "Repair the proven failure, add focused proof, and checkpoint again."}
    if current in {"NEW", "IMPLEMENTING", "REPAIRING"}:
        return {"state": "TESTING", "next_action": "Run the contract's focused required tests and record bounded evidence."}
    if current == "TESTING":
        return {"state": "REVIEWING", "next_action": "Perform independent review against frozen acceptance gates only."}
    if current == "REVIEWING":
        if "start_live_process" in _human_gate_ids(contract):
            return {"state": "WAITING_FOR_HUMAN", "next_action": "Request explicit approval for the governed live-only gate."}
        return {"state": "OFFLINE_CERTIFIED", "next_action": "Record offline certification evidence and prepare the next bounded task."}
    if gate_ids and gate_ids.issubset(completed):
        return {"state": "DONE", "next_action": "No implementation action remains; preserve the checkpoint and await human disposition."}
    return {"state": current, "next_action": str(state.get("next_action") or "Review the contract and perform one bounded state transition.")}


def render_context(task_dir: Path, *, max_bytes: int = 8192) -> str:
    contract = read_json(task_dir / "contract.json")
    state = read_json(task_dir / "state.json")
    handoff = read_json(task_dir / "handoff.json")
    claims = read_json(task_dir / "claims.json")
    unresolved_claims = [
        claim
        for claim in _list(claims.get("claims"))
        if isinstance(claim, Mapping) and str(claim.get("status") or "") not in {"PROVEN", "RETIRED"}
    ]
    lines = [
        f"# Continue {contract.get('task_id')}",
        "",
        "Read root `AGENTS.md` first. GitHub is authoritative; local-only work is not proof.",
        "",
        f"## Objective\n{contract.get('objective', '')}",
        "",
        f"## State\n- State: `{state.get('state')}`\n- Code SHA: `{state.get('code_sha')}`\n- Branch: `{state.get('branch')}`\n- Cycle: `{state.get('cycle')}`",
        "",
        f"## Next action\n{state.get('next_action') or handoff.get('next_action') or ''}",
        "",
        "## Allowed paths\n" + "\n".join(f"- `{item}`" for item in _list(contract.get("allowed_paths"))),
        "",
        "## Forbidden paths\n" + "\n".join(f"- `{item}`" for item in _list(contract.get("forbidden_paths"))),
        "",
        "## Changed paths\n" + "\n".join(f"- `{item}`" for item in _list(handoff.get("changed_paths"))),
        "",
        "## Required tests\n" + "\n".join(f"- `{item if isinstance(item, str) else item.get('command') or item.get('test_id')}`" for item in _list(contract.get("required_tests"))),
        "",
        "## Blockers\n" + ("\n".join(f"- {item}" for item in _list(state.get("blockers"))) or "- None"),
        "",
        "## Unresolved claims/findings\n" + ("\n".join(f"- {item.get('claim_id')}: {item.get('statement')}" for item in unresolved_claims) or "- None"),
        "",
        "## Worker instruction\nPerform only the next action, stay inside scope, run focused tests, checkpoint before stopping, and do not merge.",
    ]
    text = "\n".join(lines).strip() + "\n"
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    suffix = "\n\n[Context truncated at configured size; consult task JSON files for noncritical details.]\n"
    budget = max(0, max_bytes - len(suffix.encode("utf-8")))
    truncated = encoded[:budget].decode("utf-8", errors="ignore")
    return truncated.rstrip() + suffix


def framework_paths_have_merge_actions(repo_root: Path) -> list[str]:
    findings: list[str] = []
    forbidden_tokens = ("merge_pull_request", "enable_auto_merge", "git merge ")
    for root_name in ("scripts/loop", ".github/workflows/loop-handoff-gate.yml"):
        path = repo_root / root_name
        files: Iterable[Path] = [path] if path.is_file() else path.rglob("*") if path.exists() else []
        for file_path in files:
            if not file_path.is_file():
                continue
            try:
                text = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for token in forbidden_tokens:
                if token in text:
                    findings.append(f"{file_path.relative_to(repo_root)} contains forbidden merge action token {token!r}")
    return findings
