import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_level_interaction_auction_state_v1.py"


def run_to(out: Path) -> None:
    subprocess.check_call(["python", str(SCRIPT), "--out-dir", str(out)], cwd=ROOT)


def load(out: Path, name: str):
    with (out / name).open() as f:
        return json.load(f)


def test_freezes_two_lanes_and_exactly_six_mechanisms_before_outcomes():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        lanes = load(out, "frozen_evidence_lane_contract.json")
        mechanisms = load(out, "six_frozen_mechanism_contracts.json")

    assert lanes["frozen_before_outcomes"] is True
    assert lanes["lane_a"]["expected_holdout_trades"] == 100
    assert lanes["lane_b"]["expected_holdout_trades"] == 30
    assert mechanisms["count"] == 6
    assert mechanisms["no_extra_mechanisms"] is True


def test_campaign_does_not_use_provider_or_broker_paths():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        pre = load(out, "pre_change_manifest.json")
        final = load(out, "final_verdict.json")

    assert pre["provider_calls"] is False
    assert pre["broker_calls"] is False
    assert final["broker_orders_allowed"] is False
    assert final["production_activation_allowed"] is False


def test_survivor_requires_local_gates_before_algotest_spec():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        survivors = load(out, "survivor_report.json")
        algotest = load(out, "algotest_specs_for_survivors_only.json")
        audit = load(out, "independent_audit.json")

    assert audit["six_mechanisms_frozen_before_pnl"] is True
    if survivors["count"] == 0:
        assert algotest["status"] == "EMPTY"
