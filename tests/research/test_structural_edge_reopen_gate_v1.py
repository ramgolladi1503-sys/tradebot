import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_structural_edge_reopen_gate_v1.py"


def read(path: Path):
    return json.loads(path.read_text())


def generate(path: Path) -> None:
    subprocess.run(["python3", str(SCRIPT), "--output-dir", str(path)], cwd=ROOT, check=True)


def test_gate_fails_closed_without_selecting_or_testing_a_universe(tmp_path):
    out = tmp_path / "gate"
    generate(out)
    matrix = read(out / "reopen_condition_matrix.json")
    assert len(matrix["conditions"]) == 5
    assert not matrix["gate_passed"]
    assert all(row["pass"] is False for row in matrix["conditions"])
    assert read(out / "selected_universe_decision.json")["decision"] == "NO_UNIVERSE_SELECTED"
    assert read(out / "frozen_research_contract.json")["contract_status"] == "NOT_CREATED_REOPEN_GATE_FAILED"
    assert read(out / "hypothesis_catalogue.json")["hypotheses"] == []


def test_inventory_exposes_exact_capability_blockers(tmp_path):
    out = tmp_path / "gate"
    generate(out)
    inventory = read(out / "local_data_capability_inventory.json")
    assert inventory["so_called_tick_parquet"]["classification"] == "ONE_MINUTE_OHLC_NOT_TICK_DATA"
    assert inventory["price_snapshot_replay"]["sessions"] == 1
    assert "bid" in inventory["price_snapshot_replay"]["missing_fields"]
    assert inventory["banknifty_candidate_replay"]["option_sessions"] == 1
    assert inventory["banknifty_candidate_replay"]["option_expiries"] == 1
    assert inventory["constituent_data"]["files"] == 0
    assert inventory["futures"]["trusted_files"] == 0
    assert inventory["expired_nifty_options"]["unused_non_overlapping_history"] is False


def test_no_pnl_and_two_directory_determinism(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    generate(first)
    generate(second)
    a = read(first / "determinism_report.json")
    b = read(second / "determinism_report.json")
    assert a["semantic_hashes"] == b["semantic_hashes"]
    assert a["status"] == "PASS"
    assert read(first / "independent_audit.json")["status"] == "PASS"
    verdict = read(first / "final_verdict.json")
    assert verdict["final_verdict"] == "REOPEN_CONDITION_NOT_MET"
    assert verdict["outcome_or_pnl_inspected"] is False
    assert verdict["provider_acquisition_performed"] is False
    assert verdict["production_modified"] is False
