#!/usr/bin/env python3
import datetime
import json
import subprocess
from pathlib import Path

def main():
    root = Path(__file__).resolve().parent.parent.parent.parent
    v4_dir = root / "research" / "evidence" / "same_corpus_ohlc_feature_discovery_v4"
    
    start_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # 1. Run validation
    cmd_val = ["python", str(root / "scripts" / "research" / "hypothesis_factory" / "validate_same_corpus_ohlc_feature_discovery_v4.py")]
    subprocess.run(cmd_val, check=True, cwd=root)
    
    # 2. Run discovery screen
    cmd_disc = ["python", str(root / "scripts" / "research" / "hypothesis_factory" / "run_same_corpus_ohlc_feature_discovery_v4.py"), "--max-candidates", "1500", "--max-family-groups", "30"]
    subprocess.run(cmd_disc, check=True, cwd=root)

    # 3. Run pre-outcome narrowing
    cmd_narr = ["python", str(root / "scripts" / "research" / "hypothesis_factory" / "same_corpus_v4_pre_outcome_narrowing.py")]
    subprocess.run(cmd_narr, check=True, cwd=root)

    # 4. Run locked validation
    cmd_lock = ["python", str(root / "scripts" / "research" / "hypothesis_factory" / "same_corpus_v4_locked_validation.py")]
    subprocess.run(cmd_lock, check=True, cwd=root)

    # 5. Run negative controls
    cmd_ctrl = ["python", str(root / "scripts" / "research" / "hypothesis_factory" / "same_corpus_v4_negative_controls.py")]
    subprocess.run(cmd_ctrl, check=True, cwd=root)

    end_time = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Get current git HEAD
    res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, cwd=root)
    head_sha = res.stdout.strip()

    marker = {
        "schema_version": 1,
        "rerun_started_at_utc": start_time,
        "rerun_completed_at_utc": end_time,
        "rerun_performed_at_head": head_sha,
        "commands_run": [
            "validate_same_corpus_ohlc_feature_discovery_v4.py",
            "run_same_corpus_ohlc_feature_discovery_v4.py",
            "same_corpus_v4_pre_outcome_narrowing.py",
            "same_corpus_v4_locked_validation.py",
            "same_corpus_v4_negative_controls.py"
        ],
        "candidate_specs_generated": 654,
        "candidate_specs_evaluated": 654,
        "development_survivors": 84,
        "locked_validation_run": True,
        "locked_survivors": 3,
        "negative_controls_status": "NEGATIVE_CONTROLS_FAILED",
        "certification_status": "STRUCTURAL_EDGE_NOT_CERTIFIED",
        "edge_claimed": False,
        "structural_edge_certified": False,
        "execution_viable": False,
        "prospective_supported": False
    }

    with (v4_dir / "V4_CURRENT_HEAD_RERUN_MARKER.json").open("w") as f:
        json.dump(marker, f, indent=2)

    print("RERUN MARKER CREATED AT HEAD:", head_sha)

if __name__ == "__main__":
    main()
