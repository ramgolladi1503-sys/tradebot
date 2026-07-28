import json
import subprocess
import tempfile
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_level_auction_failure_decomposition_v1.py"


def run_to(out: Path) -> None:
    subprocess.check_call(["python", str(SCRIPT), "--out-dir", str(out)], cwd=ROOT)


def load(out: Path, name: str):
    with (out / name).open() as f:
        return json.load(f)


def test_reconciles_immutable_campaign_artifacts():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        recon = load(out, "reconciliation_report.json")
        inventory = load(out, "immutable_artifact_inventory.json")

    assert recon["status"] == "PASS"
    assert recon["holdout_rows_reported"] == recon["holdout_rows_observed"] == 11384
    assert recon["final_campaign_verdict"] == "NO_LEVEL_AUCTION_STRATEGY_SURVIVED"
    assert all(item["exists"] for item in inventory["files"].values())


def test_six_row_failure_matrix_has_required_failure_classes():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        matrix = pd.read_csv(out / "six_row_mechanism_failure_matrix.csv")

    assert len(matrix) == 6
    assert set(matrix["mechanism_id"]) == {
        "M1_ACCEPTANCE_BEYOND_KNOWN_LEVEL",
        "M2_FAILED_AUCTION_RECLAIM",
        "M3_REPEATED_TEST_DEPLETION_PROXY",
        "M4_HIGHEST_CLOSE_VERSUS_HIGHEST_WICK",
        "M5_COMPRESSION_NEAR_BOUNDARY",
        "M6_OPTION_CONFIRMATION_NON_CONFIRMATION",
    }
    assert (matrix["option_net_expectancy"] < 0).all()
    assert (matrix["profit_factor"] < 1).all()
    assert matrix["primary_failure_class"].str.startswith("Class ").all()


def test_diagnostic_is_read_only_and_selects_close_data_lane():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        audit = load(out, "independent_audit.json")
        final = load(out, "final_verdict.json")
        direction = load(out, "research_direction_decision.json")

    assert audit["provider_calls"] is False
    assert audit["broker_calls"] is False
    assert audit["algotest_called"] is False
    assert audit["production_changes"] is False
    assert final["final_verdict"] == "FAILURE_DECOMPOSITION_COMPLETE_CLOSE_DATA_LANE"
    assert direction["selected_next_research_direction"] == "Direction 4 - Close This Data Lane"
