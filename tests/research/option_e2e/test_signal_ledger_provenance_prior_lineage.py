from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from research.option_e2e_recertification_v4.signal_ledger_provenance_v1.git_provenance import (
    GENERATOR_RELATIVE_PATH,
    INVENTORY_RELATIVE_PATH,
    LEDGER_RELATIVE_PATH,
    SIDECAR_RELATIVE_PATH,
    execute_historical_generator,
)
from research.option_e2e_recertification_v4.signal_ledger_provenance_v1.lineage import (
    build_historical_binding,
    discover_introduction_history,
)

GENERATOR = '''from __future__ import annotations
import hashlib, json
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
    ids = [e["id"] for e in inventory["entities"] if e.get("counted_as_strategy")]
    records = [SignalLedgerRecord(i, f"{i}:signal_blocked", "frozen", "", "", "", "NA", "0", "", "", "", "", False, "SIGNAL_INPUT_DATA_MISSING", "NO_SIGNAL_LEDGER_SOURCE") for i in ids]
    records.extend(SignalLedgerRecord(h, f"{h}:hypothesis_blocked", "frozen", "", "", "", "NA", "0", "", "", "", "", False, "SIGNAL_INPUT_DATA_MISSING", "NO_SIGNAL_LEDGER_SOURCE") for h in HISTORICAL_RESEARCH_HYPOTHESES)
    return records, {"strategy_count": len(ids), "hypothesis_count": 1, "status_counts": {"SIGNAL_INPUT_DATA_MISSING": len(records)}, "blocked_eligibility": len(records)}
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


def _write(root: Path, relative: str, content: str | bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content) if isinstance(content, bytes) else path.write_text(content)


def test_prior_generator_lineage_is_proven(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    inventory = (json.dumps({"entities": [{"id": "STRATEGY_A", "counted_as_strategy": True}]}, indent=2, sort_keys=True) + "\n").encode()
    _write(root, GENERATOR_RELATIVE_PATH, GENERATOR)
    _write(root, INVENTORY_RELATIVE_PATH, inventory)
    _git(root, "add", GENERATOR_RELATIVE_PATH, INVENTORY_RELATIVE_PATH)
    _git(root, "commit", "-m", "generator-lineage")
    ledger = execute_historical_generator(GENERATOR.encode(), inventory)
    _write(root, LEDGER_RELATIVE_PATH, ledger)
    _write(root, SIDECAR_RELATIVE_PATH, f"{hashlib.sha256(ledger).hexdigest()}  signal_ledgers.json\n")
    _git(root, "add", LEDGER_RELATIVE_PATH, SIDECAR_RELATIVE_PATH)
    _git(root, "commit", "-m", "ledger-introduction")
    intro = _git(root, "rev-parse", "HEAD")
    history = discover_introduction_history(root, [LEDGER_RELATIVE_PATH, SIDECAR_RELATIVE_PATH, GENERATOR_RELATIVE_PATH, INVENTORY_RELATIVE_PATH])
    assert history["introduction_commit"] == intro
    assert history["atomic_introduction_status"] == "PROVEN_WITH_PRIOR_LINEAGE"
    binding = build_historical_binding(root, expected_introduction_commit=None)
    assert binding["generator_output_binding"]["status"] == "PROVEN"
    assert binding["historical_blobs"]["historical_sidecar_matches_ledger"] is True
