from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from research.option_e2e_recertification_v4.signal_ledger_provenance_v1 import (
    AuditError,
    ProvenanceError,
    audit_signal_ledger,
    build_historical_binding,
    discover_introduction_history,
    oracle_audit,
    semantic_sha256,
)
from research.option_e2e_recertification_v4.signal_ledger_provenance_v1.git_provenance import (
    GENERATOR_RELATIVE_PATH,
    INVENTORY_RELATIVE_PATH,
    INVALIDATION_RELATIVE_PATH,
    LEDGER_RELATIVE_PATH,
    SIDECAR_RELATIVE_PATH,
    derive_invalidation,
    derive_ownership,
    execute_historical_generator,
    reconstruct_historical_generator_output,
    search_non_outcome_provenance,
)

GENERATOR = '''from __future__ import annotations
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
HISTORICAL_RESEARCH_HYPOTHESES = ("HYPOTHESIS_A",)
@dataclass(frozen=True)
class SignalLedgerRecord:
    strategy_or_hypothesis_id: str
    signal_id: str
    session: str
    feature_cutoff_ts: str
    signal_ts: str
    earliest_entry_ts: str
    direction: str
    signal_strength: str
    params_hash: str
    source_hash: str
    implementation_sha: str
    fold_id: str
    is_holdout: bool
    status: str
    blocker: str
def build_signal_ledgers(inventory_path: Path):
    inventory = json.loads(inventory_path.read_text())
    strategy_ids = [entry["id"] for entry in inventory["entities"] if entry.get("counted_as_strategy")]
    records = [SignalLedgerRecord(strategy_id, f"{strategy_id}:signal_blocked", "frozen", "", "", "", "NA", "0", "", "", "", "", False, "SIGNAL_INPUT_DATA_MISSING", "NO_SIGNAL_LEDGER_SOURCE") for strategy_id in strategy_ids]
    records.extend(SignalLedgerRecord(h, f"{h}:hypothesis_blocked", "frozen", "", "", "", "NA", "0", "", "", "", "", False, "SIGNAL_INPUT_DATA_MISSING", "NO_SIGNAL_LEDGER_SOURCE") for h in HISTORICAL_RESEARCH_HYPOTHESES)
    summary = {"strategy_count": len(strategy_ids), "hypothesis_count": len(HISTORICAL_RESEARCH_HYPOTHESES), "status_counts": {"SIGNAL_INPUT_DATA_MISSING": len(records)}, "blocked_eligibility": len(records)}
    return records, summary
def write_signal_ledgers(records, summary, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "records": [asdict(r) for r in records]}
    ledger = output_dir / "signal_ledgers.json"
    ledger.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\\n")
    (output_dir / "signal_ledgers_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\\n")
    (output_dir / "signal_ledgers.json.sha256").write_text(f"{hashlib.sha256(ledger.read_bytes()).hexdigest()}  signal_ledgers.json\\n")
'''


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _write(root: Path, relative: str, content: bytes | str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content)


def _init_repo(tmp_path: Path, *, split_commits: bool = False, mutate_current: bool = False, mutate_generator: bool = False, invalidation_hash: bool = False, sidecar_mismatch: bool = False) -> tuple[Path, str, bytes]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _write(root, "README.md", "base\n")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "base")

    inventory = {"entities": [{"id": "STRATEGY_A", "counted_as_strategy": True}]}
    inventory_bytes = (json.dumps(inventory, indent=2, sort_keys=True) + "\n").encode()
    generator_bytes = GENERATOR.encode()
    ledger_bytes = execute_historical_generator(generator_bytes, inventory_bytes)
    sidecar_digest = "0" * 64 if sidecar_mismatch else hashlib.sha256(ledger_bytes).hexdigest()
    sidecar = f"{sidecar_digest}  signal_ledgers.json\n"

    files = [
        (GENERATOR_RELATIVE_PATH, generator_bytes),
        (INVENTORY_RELATIVE_PATH, inventory_bytes),
        (LEDGER_RELATIVE_PATH, ledger_bytes),
        (SIDECAR_RELATIVE_PATH, sidecar),
    ]
    if split_commits:
        for index, (path, content) in enumerate(files):
            _write(root, path, content)
            _git(root, "add", path)
            _git(root, "commit", "-m", f"add-{index}")
        intro = _git(root, "log", "--format=%H", "--reverse", "--", LEDGER_RELATIVE_PATH).splitlines()[0]
    else:
        for path, content in files:
            _write(root, path, content)
        _git(root, "add", *[path for path, _ in files])
        _git(root, "commit", "-m", "introduce")
        intro = _git(root, "rev-parse", "HEAD")

    invalidation = {
        "previous_head": intro,
        "decision": "INVALID_INCOMPLETE_EVIDENCE_IMPLEMENTATION_PLACEHOLDER_SIGNAL_AND_RECONSTRUCTION",
        "scope": [GENERATOR_RELATIVE_PATH],
    }
    if invalidation_hash:
        invalidation["ledger_sha256"] = hashlib.sha256(ledger_bytes).hexdigest()
    _write(root, INVALIDATION_RELATIVE_PATH, json.dumps(invalidation, indent=2, sort_keys=True) + "\n")
    _git(root, "add", INVALIDATION_RELATIVE_PATH)
    _git(root, "commit", "-m", "invalidate")

    if mutate_current:
        _write(root, LEDGER_RELATIVE_PATH, ledger_bytes + b" ")
        _git(root, "add", LEDGER_RELATIVE_PATH)
        _git(root, "commit", "-m", "mutate-ledger")
    if mutate_generator:
        _write(root, GENERATOR_RELATIVE_PATH, generator_bytes + b"\n# changed\n")
        _git(root, "add", GENERATOR_RELATIVE_PATH)
        _git(root, "commit", "-m", "mutate-generator")
    return root, intro, ledger_bytes


def test_dynamic_introduction_and_parent_absence(tmp_path: Path) -> None:
    root, intro, _ = _init_repo(tmp_path)
    history = discover_introduction_history(root, [LEDGER_RELATIVE_PATH, SIDECAR_RELATIVE_PATH, GENERATOR_RELATIVE_PATH, INVENTORY_RELATIVE_PATH])
    assert history["introduction_commit"] == intro
    assert history["atomic_introduction_status"] == "PROVEN"
    assert {record["existed_in_parent"] for record in history["paths"].values()} == {False}


def test_split_introduction_is_unresolved(tmp_path: Path) -> None:
    root, _, _ = _init_repo(tmp_path, split_commits=True)
    history = discover_introduction_history(root, [LEDGER_RELATIVE_PATH, SIDECAR_RELATIVE_PATH, GENERATOR_RELATIVE_PATH, INVENTORY_RELATIVE_PATH])
    assert history["atomic_introduction_status"] == "UNRESOLVED"
    with pytest.raises(ProvenanceError, match="ATOMIC_INTRODUCTION_UNRESOLVED"):
        build_historical_binding(root, expected_introduction_commit=None)


def test_expected_commit_mismatch_fails(tmp_path: Path) -> None:
    root, _, _ = _init_repo(tmp_path)
    with pytest.raises(ProvenanceError, match="INTRODUCTION_COMMIT_MISMATCH"):
        build_historical_binding(root, expected_introduction_commit="0" * 40)


def test_historical_generator_reproduces_exact_bytes(tmp_path: Path) -> None:
    root, _, ledger = _init_repo(tmp_path)
    binding = build_historical_binding(root, expected_introduction_commit=None)
    assert binding["generator_output_binding"]["status"] == "PROVEN"
    assert binding["generator_output_binding"]["byte_equality"] is True
    assert binding["historical_blobs"]["historical_sidecar_matches_ledger"] is True
    assert binding["historical_blobs"]["historical_ledger_physical_sha256"] == hashlib.sha256(ledger).hexdigest()


def test_current_ledger_divergence_is_detected(tmp_path: Path) -> None:
    root, _, _ = _init_repo(tmp_path, mutate_current=True)
    binding = build_historical_binding(root, expected_introduction_commit=None)
    assert binding["historical_blobs"]["historical_current_ledger_equality"] is False


def test_primary_and_independent_reconstruction_match() -> None:
    inventory = (json.dumps({"entities": [{"id": "STRATEGY_A", "counted_as_strategy": True}]}, sort_keys=True) + "\n").encode()
    primary = execute_historical_generator(GENERATOR.encode(), inventory)
    oracle = reconstruct_historical_generator_output(GENERATOR.encode(), inventory)
    assert primary == oracle


def test_ownership_separates_raw_and_canonical() -> None:
    inventory = {"entities": [{"id": "STRATEGY_A", "counted_as_strategy": True}]}
    ledger = execute_historical_generator(GENERATOR.encode(), (json.dumps(inventory) + "\n").encode())
    result = derive_ownership(ledger, inventory)
    assert result["embedded_row_owner_ids"] == ["HYPOTHESIS_A", "STRATEGY_A"]
    assert result["canonical_strategy_ids"] == ["STRATEGY_A"]
    assert result["unmapped_historical_owner_labels"] == ["HYPOTHESIS_A"]
    assert result["aggregate_canonical_strategy_id"] is None


def test_derived_invalidation_requires_generator_binding(tmp_path: Path) -> None:
    root, _, _ = _init_repo(tmp_path)
    binding = build_historical_binding(root, expected_introduction_commit=None)
    invalidation = derive_invalidation(root, binding, expected_ledger_sha256=binding["historical_blobs"]["historical_ledger_physical_sha256"])
    assert invalidation["direct_ledger_invalidation_authority"] == "UNRESOLVED"
    assert invalidation["implementation_invalidation_authority"] == "CONFIRMED"
    assert invalidation["derived_ledger_invalidation_authority"] == "CONFIRMED"
    binding["generator_output_binding"]["status"] = "CONFLICTING"
    invalidation = derive_invalidation(root, binding, expected_ledger_sha256=binding["historical_blobs"]["historical_ledger_physical_sha256"])
    assert invalidation["derived_ledger_invalidation_authority"] == "UNRESOLVED"


def test_direct_invalidation_requires_ledger_hash(tmp_path: Path) -> None:
    root, _, _ = _init_repo(tmp_path, invalidation_hash=True)
    binding = build_historical_binding(root, expected_introduction_commit=None)
    result = derive_invalidation(root, binding, expected_ledger_sha256=binding["historical_blobs"]["historical_ledger_physical_sha256"])
    assert result["direct_ledger_invalidation_authority"] == "CONFIRMED"


def test_real_search_records_queries_candidates_and_exclusions(tmp_path: Path) -> None:
    root, _, ledger = _init_repo(tmp_path)
    _write(root, "metadata/freeze_manifest.json", json.dumps({"ledger": hashlib.sha256(ledger).hexdigest()}))
    _write(root, "outcomes/profit.json", json.dumps({"ledger": hashlib.sha256(ledger).hexdigest()}))
    _git(root, "add", "metadata/freeze_manifest.json", "outcomes/profit.json")
    _git(root, "commit", "-m", "search-files")
    records = search_non_outcome_provenance(root, ledger_sha256=hashlib.sha256(ledger).hexdigest(), row_count=2)
    repo = records[0]
    assert repo["search_completed"] is True
    assert repo["candidate_count"] >= repo["inspected_candidate_count"]
    assert any(match["semantic_path"] == "metadata/freeze_manifest.json" for match in repo["matching_records"])
    assert "outcomes/profit.json" not in repo["inspected_candidate_paths"]
    assert repo["file_exclusion_markers"]


def test_missing_external_root_cannot_be_negative_proof(tmp_path: Path) -> None:
    root, _, _ = _init_repo(tmp_path)
    records = search_non_outcome_provenance(root, [tmp_path / "missing"])
    external = records[1]
    assert external["root_exists"] is False
    assert external["search_completed"] is False


def test_physical_hash_mismatch_fails_closed() -> None:
    with pytest.raises(AuditError, match="LEDGER_PHYSICAL_HASH_MISMATCH"):
        audit_signal_ledger(b"{}", {}, expected_sha256="0" * 64, expected_row_count=0)


def test_audit_uses_derived_not_direct_invalidation(tmp_path: Path) -> None:
    root, _, ledger = _init_repo(tmp_path)
    binding = build_historical_binding(root, expected_introduction_commit=None)
    ownership = derive_ownership(ledger, binding["historical_inventory"])
    invalidation = derive_invalidation(root, binding, expected_ledger_sha256=hashlib.sha256(ledger).hexdigest())
    result = audit_signal_ledger(ledger, {"historical_binding": binding, "ownership": ownership, "invalidation": invalidation}, expected_sha256=hashlib.sha256(ledger).hexdigest(), expected_row_count=2)
    assert result["freeze_contamination"]["direct_ledger_invalidation_authority"] == "UNRESOLVED"
    assert result["freeze_contamination"]["derived_ledger_invalidation_authority"] == "CONFIRMED"
    assert result["verdict"] == "SIGNAL_LEDGER_INVALIDATED"


def test_without_invalidation_provenance_is_incomplete() -> None:
    ledger = execute_historical_generator(GENERATOR.encode(), (json.dumps({"entities": [{"id": "STRATEGY_A", "counted_as_strategy": True}]}) + "\n").encode())
    ownership = derive_ownership(ledger, {"entities": [{"id": "STRATEGY_A", "counted_as_strategy": True}]})
    result = audit_signal_ledger(ledger, {"historical_binding": {"generator_output_binding": {"status": "PROVEN"}}, "ownership": ownership, "invalidation": {}}, expected_sha256=hashlib.sha256(ledger).hexdigest(), expected_row_count=2)
    assert result["verdict"] == "SIGNAL_LEDGER_OWNERSHIP_PROVEN_BUT_PROVENANCE_INCOMPLETE"


def test_semantic_hash_is_order_independent() -> None:
    assert semantic_sha256({"a": 1, "b": 2}) == semantic_sha256({"b": 2, "a": 1})


def test_historical_sidecar_mismatch_is_detected(tmp_path: Path) -> None:
    root, _, _ = _init_repo(tmp_path, sidecar_mismatch=True)
    binding = build_historical_binding(root, expected_introduction_commit=None)
    assert binding["historical_blobs"]["historical_sidecar_matches_ledger"] is False


def test_current_generator_divergence_is_detected(tmp_path: Path) -> None:
    root, _, _ = _init_repo(tmp_path, mutate_generator=True)
    binding = build_historical_binding(root, expected_introduction_commit=None)
    assert binding["historical_blobs"]["historical_current_generator_equality"] is False


def test_independent_oracle_derives_same_invalidation_chain(tmp_path: Path) -> None:
    root, _, ledger = _init_repo(tmp_path)
    result = oracle_audit(root, hashlib.sha256(ledger).hexdigest(), 2)
    assert result["generator_output_binding"] is True
    assert result["direct_ledger_invalidation_authority"] == "UNRESOLVED"
    assert result["derived_ledger_invalidation_authority"] == "CONFIRMED"
    assert result["verdict"] == "SIGNAL_LEDGER_INVALIDATED"


def test_missing_embedded_owners_blocks_provenance() -> None:
    ledger = (json.dumps({"records": [{"strategy_or_hypothesis_id": ""}]}, sort_keys=True) + "\n").encode()
    result = audit_signal_ledger(ledger, {"ownership": {}, "invalidation": {}}, expected_sha256=hashlib.sha256(ledger).hexdigest(), expected_row_count=1)
    assert result["verdict"] == "SIGNAL_LEDGER_PROVENANCE_BLOCKED"


def test_invalid_causal_ordering_invalidates() -> None:
    record = {"strategy_or_hypothesis_id": "STRATEGY_A", "feature_cutoff_ts": "2026-01-01T09:20:00+05:30", "signal_ts": "2026-01-01T09:21:00+05:30", "earliest_entry_ts": "2026-01-01T09:19:00+05:30", "fold_id": ""}
    ledger = (json.dumps({"records": [record]}, sort_keys=True) + "\n").encode()
    ownership = {"embedded_row_owner_field_authority": "PROVEN", "embedded_row_owner_ids": ["STRATEGY_A"]}
    result = audit_signal_ledger(ledger, {"ownership": ownership, "invalidation": {}}, expected_sha256=hashlib.sha256(ledger).hexdigest(), expected_row_count=1)
    assert result["temporal_split"]["causal_ordering_result"] == "INVALID_CAUSAL_ORDERING"
    assert result["verdict"] == "SIGNAL_LEDGER_INVALIDATED"
