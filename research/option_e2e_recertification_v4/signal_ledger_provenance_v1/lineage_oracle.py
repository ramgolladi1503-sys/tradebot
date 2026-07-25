from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .git_provenance import (
    EXPECTED_INTRODUCTION_COMMIT,
    EXPECTED_LEDGER_SHA256,
    EXPECTED_ROW_COUNT,
    GENERATOR_RELATIVE_PATH,
    INVENTORY_RELATIVE_PATH,
    INVALIDATION_RELATIVE_PATH,
    LEDGER_RELATIVE_PATH,
    SIDECAR_RELATIVE_PATH,
)


def _git(repo_root: Path, *args: str, text: bool = True) -> str | bytes:
    result = subprocess.run(["git", *args], cwd=repo_root, check=False, capture_output=True, text=text)
    if result.returncode != 0:
        raise ValueError(f"ORACLE_GIT_FAILED:{' '.join(args)}")
    return result.stdout


def _first_commit(repo_root: Path, path: str) -> str:
    raw = str(_git(repo_root, "log", "--follow", "--format=%H", "--reverse", "--", path))
    commits = [line.strip() for line in raw.splitlines() if line.strip()]
    if not commits:
        raise ValueError(f"ORACLE_HISTORY_MISSING:{path}")
    return commits[0]


def _blob(repo_root: Path, commit: str, path: str) -> bytes:
    return _git(repo_root, "show", f"{commit}:{path}", text=False)  # type: ignore[return-value]


def _hypotheses(generator_bytes: bytes) -> list[str]:
    tree = ast.parse(generator_bytes.decode("utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "HISTORICAL_RESEARCH_HYPOTHESES"
            for target in node.targets
        ):
            return list(ast.literal_eval(node.value))
    raise ValueError("ORACLE_HYPOTHESES_MISSING")


def _reconstruct(generator_bytes: bytes, inventory_bytes: bytes) -> bytes:
    inventory = json.loads(inventory_bytes)
    strategies = [entry["id"] for entry in inventory["entities"] if entry.get("counted_as_strategy")]
    hypotheses = _hypotheses(generator_bytes)
    records = []
    for owner, suffix in [(owner, "signal_blocked") for owner in strategies] + [
        (owner, "hypothesis_blocked") for owner in hypotheses
    ]:
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
            "strategy_count": len(strategies),
            "hypothesis_count": len(hypotheses),
            "status_counts": {"SIGNAL_INPUT_DATA_MISSING": len(records)},
            "blocked_eligibility": len(records),
        },
        "records": records,
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def oracle_audit(
    repo_root: Path,
    expected_sha256: str = EXPECTED_LEDGER_SHA256,
    expected_rows: int = EXPECTED_ROW_COUNT,
    external_roots: Iterable[Path] = (),
) -> dict[str, Any]:
    first_commits = {
        path: _first_commit(repo_root, path)
        for path in [LEDGER_RELATIVE_PATH, SIDECAR_RELATIVE_PATH, GENERATOR_RELATIVE_PATH, INVENTORY_RELATIVE_PATH]
    }
    introduction = (
        first_commits[LEDGER_RELATIVE_PATH]
        if first_commits[LEDGER_RELATIVE_PATH] == first_commits[SIDECAR_RELATIVE_PATH]
        else None
    )
    support_present = bool(
        introduction
        and subprocess.run(
            ["git", "cat-file", "-e", f"{introduction}:{GENERATOR_RELATIVE_PATH}"],
            cwd=repo_root,
            check=False,
            capture_output=True,
        ).returncode
        == 0
        and subprocess.run(
            ["git", "cat-file", "-e", f"{introduction}:{INVENTORY_RELATIVE_PATH}"],
            cwd=repo_root,
            check=False,
            capture_output=True,
        ).returncode
        == 0
    )
    if introduction is None or not support_present:
        return {
            "verdict": "SIGNAL_LEDGER_PROVENANCE_BLOCKED",
            "introduction_commit": None,
            "first_commits": first_commits,
        }

    ledger = _blob(repo_root, introduction, LEDGER_RELATIVE_PATH)
    sidecar = _blob(repo_root, introduction, SIDECAR_RELATIVE_PATH)
    generator = _blob(repo_root, introduction, GENERATOR_RELATIVE_PATH)
    inventory = _blob(repo_root, introduction, INVENTORY_RELATIVE_PATH)
    reconstructed = _reconstruct(generator, inventory)
    current = (repo_root / LEDGER_RELATIVE_PATH).read_bytes()
    invalidation = json.loads((repo_root / INVALIDATION_RELATIVE_PATH).read_text(encoding="utf-8"))
    implementation_invalidated = (
        invalidation.get("previous_head") == introduction
        and GENERATOR_RELATIVE_PATH in invalidation.get("scope", [])
    )
    generator_binding = ledger == reconstructed
    historical_hash = hashlib.sha256(ledger).hexdigest()
    derived_invalidation = (
        implementation_invalidated
        and generator_binding
        and ledger == current
        and historical_hash == expected_sha256
    )
    payload = json.loads(current)
    owners = sorted(
        {
            record.get("strategy_or_hypothesis_id")
            for record in payload.get("records", [])
            if record.get("strategy_or_hypothesis_id")
        }
    )
    verdict = (
        "SIGNAL_LEDGER_INVALIDATED"
        if derived_invalidation
        else "SIGNAL_LEDGER_OWNERSHIP_PROVEN_BUT_PROVENANCE_INCOMPLETE"
        if owners
        else "SIGNAL_LEDGER_PROVENANCE_BLOCKED"
    )
    return {
        "introduction_commit": introduction,
        "configured_commit_matches_discovery": introduction == EXPECTED_INTRODUCTION_COMMIT,
        "first_commits": first_commits,
        "historical_ledger_sha256": historical_hash,
        "historical_sidecar_matches": sidecar.decode("utf-8").strip().split()[0] == historical_hash,
        "historical_generator_blob_sha": str(
            _git(repo_root, "rev-parse", f"{introduction}:{GENERATOR_RELATIVE_PATH}")
        ).strip(),
        "generator_output_binding": generator_binding,
        "current_historical_ledger_equality": current == ledger,
        "embedded_row_owner_ids": owners,
        "direct_ledger_invalidation_authority": (
            "CONFIRMED" if invalidation.get("ledger_sha256") == expected_sha256 else "UNRESOLVED"
        ),
        "implementation_invalidation_authority": (
            "CONFIRMED" if implementation_invalidated else "UNRESOLVED"
        ),
        "derived_ledger_invalidation_authority": (
            "CONFIRMED" if derived_invalidation else "UNRESOLVED"
        ),
        "search_records": [],
        "physical_hash_matches": hashlib.sha256(current).hexdigest() == expected_sha256,
        "row_count_matches": len(payload.get("records", [])) == expected_rows,
        "verdict": verdict,
    }
