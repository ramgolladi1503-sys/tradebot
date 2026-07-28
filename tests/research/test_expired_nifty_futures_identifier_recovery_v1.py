import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_expired_nifty_futures_identifier_recovery_v1.py"


def run_to(out: Path) -> None:
    subprocess.check_call(["python", str(SCRIPT), "--out-dir", str(out)], cwd=ROOT)


def load(out: Path, name: str):
    with (out / name).open() as f:
        return json.load(f)


def test_no_official_expired_identifiers_blocks_bulk_acquisition():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        verdict = load(out, "final_verdict.json")
        raw = load(out, "raw_acquisition_manifest.json")
        inv = load(out, "local_identifier_inventory.json")

    assert verdict["final_verdict"] == "OFFICIAL_EXPIRED_IDENTIFIERS_UNAVAILABLE"
    assert raw["bulk_acquisition_attempted"] is False
    assert inv["accepted_expired_identifier_count"] == 0


def test_symbol_only_targets_are_not_probeable():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        ledger = load(out, "frozen_expiry_target_ledger.json")
        probes = load(out, "identifier_probe_manifest.json")

    assert len(ledger["targets"]) == 12
    assert {p["classification"] for p in probes["probes"]} == {"IDENTIFIER_UNRESOLVED"}
    assert {p["probe_status"] for p in probes["probes"]} == {"NOT_SENT"}


def test_audit_and_secret_scan_are_fail_closed_and_clean():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        run_to(out)
        audit = load(out, "independent_audit.json")
        secrets = load(out, "secret_scan_result.json")

    assert audit["no_inferred_or_synthetic_identifiers"] is True
    assert audit["no_continuous_stitching"] is True
    assert audit["result"] == "PASS_BLOCKED_NO_IDENTIFIERS"
    assert secrets["status"] == "PASS"
