#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

CAMPAIGN_VERSION = "v2"

FULL_FAMILY_QUEUE = [
    "PRE_CLOSE_IMBALANCE_PROXY_FAMILY_V1",
    "VOLATILITY_REGIME_CONDITIONAL_FAMILY_V1",
    "SESSION_GAP_CONTINUATION_REVERSAL_FAMILY_V1",
    "BREADTH_OR_CONSTITUENT_LEAD_LAG_FAMILY_V1",
    "FUTURES_BASIS_OR_PREMIUM_FAMILY_V1",
    "OPTIONS_MICROSTRUCTURE_FAMILY_V1"
]

PARKED_OR_FAILED_FAMILIES = {
    "BDE2_SEQUENCE_FAMILY_V1",
    "BDE2_MORPHOLOGY_CLUSTER_FAMILY_V1",
    "BDE2_TRANSITION_COMMUNITY_FAMILY_V1",
    "TIME_OF_DAY_SESSION_POSITION_FAMILY_V1",
    "OPENING_SESSION_MICROSTRUCTURE_PROXY_FAMILY_V1"
}

MISSING_DATA_FAMILIES = {
    "BREADTH_OR_CONSTITUENT_LEAD_LAG_FAMILY_V1": "BLOCKED_MISSING_CONSTITUENT_DATA",
    "FUTURES_BASIS_OR_PREMIUM_FAMILY_V1": "BLOCKED_MISSING_FUTURES_DATA",
    "OPTIONS_MICROSTRUCTURE_FAMILY_V1": "BLOCKED_MISSING_OPTIONS_MICROSTRUCTURE_DATA"
}

FAMILY_MODULE_MAP = {
    "PRE_CLOSE_IMBALANCE_PROXY_FAMILY_V1": (
        "build_pre_close_imbalance_proxy_candidates_v1.py",
        "run_pre_close_imbalance_proxy_development_v1.py"
    ),
    "VOLATILITY_REGIME_CONDITIONAL_FAMILY_V1": (
        "build_volatility_regime_conditional_candidates_v1.py",
        "run_volatility_regime_conditional_development_v1.py"
    ),
    "SESSION_GAP_CONTINUATION_REVERSAL_FAMILY_V1": (
        "build_session_gap_continuation_reversal_candidates_v1.py",
        "run_session_gap_continuation_reversal_development_v1.py"
    )
}

def verify_git_state(root: Path) -> bool:
    try:
        branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=root).decode("utf-8").strip()
        if branch != "research/strategy-certification-kernel-v0":
            print(f"BLOCKED: Invalid branch {branch}")
            return False
        
        status = subprocess.check_output(["git", "status", "--short", "-uno"], cwd=root).decode("utf-8").strip()
        if status:
            print(f"BLOCKED: Worktree is dirty\n{status}")
            return False
            
        return True
    except Exception as e:
        print(f"BLOCKED: Failed to verify git state: {e}")
        return False

def main():
    root = Path(__file__).resolve().parent.parent.parent.parent
    if not verify_git_state(root):
        sys.exit(1)
        
    campaign_dir = root / "research" / "evidence" / "autonomous_structural_edge_campaign_v2"
    campaign_dir.mkdir(parents=True, exist_ok=True)
    script_dir = root / "scripts" / "research" / "hypothesis_factory"

    families_attempted = []
    families_failed = []
    families_blocked = []
    results_ledger = []
    failure_entries = []

    # Process all unattempted active families in order
    for family in FULL_FAMILY_QUEUE:
        if family in PARKED_OR_FAILED_FAMILIES:
            continue

        families_attempted.append(family)
        print(f"\n==========================================")
        print(f"CAMPAIGN V2 RUNNING FAMILY: {family}")
        print(f"==========================================")

        if family in MISSING_DATA_FAMILIES:
            status = MISSING_DATA_FAMILIES[family]
            print(f"Status: {status}")
            families_blocked.append({"family": family, "reason": status})
            results_ledger.append({"family": family, "status": status})
            failure_entries.append(f"- **{family}**: {status}")
            continue

        builder_script, dev_script = FAMILY_MODULE_MAP[family]
        builder_path = script_dir / builder_script
        dev_path = script_dir / dev_script

        if not builder_path.exists() or not dev_path.exists():
            status = "BLOCKED_GOVERNANCE_OR_IMPLEMENTATION_DEFECT"
            print(f"Status: {status} (missing scripts)")
            families_blocked.append({"family": family, "reason": status})
            results_ledger.append({"family": family, "status": status})
            failure_entries.append(f"- **{family}**: {status} (missing implementation scripts)")
            continue

        # Step 1: Pre-outcome builder
        print(f"Executing pre-outcome candidate builder for {family}...")
        try:
            subprocess.check_call([sys.executable, str(builder_path)], cwd=root)
        except subprocess.CalledProcessError as e:
            status = "BLOCKED_GOVERNANCE_OR_IMPLEMENTATION_DEFECT"
            print(f"Pre-outcome builder failed: {e}")
            families_blocked.append({"family": family, "reason": status})
            results_ledger.append({"family": family, "status": status})
            failure_entries.append(f"- **{family}**: {status} (builder execution failure)")
            continue

        # Step 2: Development outcome screen
        print(f"Executing development outcome screen for {family}...")
        try:
            out = subprocess.check_output([sys.executable, str(dev_path)], cwd=root).decode("utf-8").strip()
            status = out.split("\n")[-1]
        except subprocess.CalledProcessError as e:
            status = "BLOCKED_GOVERNANCE_OR_IMPLEMENTATION_DEFECT"
            print(f"Development screen failed: {e}")
            families_blocked.append({"family": family, "reason": status})
            results_ledger.append({"family": family, "status": status})
            failure_entries.append(f"- **{family}**: {status} (development runner execution failure)")
            continue

        print(f"Development outcome verdict for {family}: {status}")

        if status == "DEVELOPMENT_STRUCTURE_SUPPORTED":
            # Step 3: Locked validation if supported
            locked_script = script_dir / "run_pre_close_imbalance_proxy_locked_validation_v1.py"
            if locked_script.exists():
                print(f"Executing locked validation for {family}...")
                try:
                    out_locked = subprocess.check_output([sys.executable, str(locked_script)], cwd=root).decode("utf-8").strip()
                    status = out_locked.split("\n")[-1]
                except subprocess.CalledProcessError as e:
                    status = "BLOCKED_GOVERNANCE_OR_IMPLEMENTATION_DEFECT"
                    print(f"Locked validation failed: {e}")

                print(f"Locked validation verdict for {family}: {status}")

                if status == "LOCKED_VALIDATION_SUPPORTED":
                    # Step 4: Certification layers (WFA / Negative Controls / Costs)
                    cert_script = script_dir / "run_tod_session_position_certification_layers_v1.py"
                    if cert_script.exists():
                        print(f"Executing certification layers for {family}...")
                        try:
                            out_cert = subprocess.check_output([sys.executable, str(cert_script)], cwd=root).decode("utf-8").strip()
                            status = out_cert.split("\n")[-1]
                        except subprocess.CalledProcessError as e:
                            status = "BLOCKED_GOVERNANCE_OR_IMPLEMENTATION_DEFECT"

                        print(f"Certification layers verdict for {family}: {status}")

        if "NO_DEVELOPMENT_SUPPORTED" in status or "FAIL" in status or "REJECTED" in status or "NOT_CERTIFIED" in status:
            families_failed.append(family)
            failure_entries.append(f"- **{family}**: {status}")

        results_ledger.append({"family": family, "status": status})

    # Summary calculation
    if len(families_failed) + len(families_blocked) == len(families_attempted):
        campaign_endpoint = "NO_STRUCTURAL_EDGE_FOUND_IN_AVAILABLE_DATA"
    else:
        campaign_endpoint = "STRUCTURAL_EDGE_NOT_CERTIFIED"

    manifest = {
        "campaign_version": CAMPAIGN_VERSION,
        "campaign_endpoint": campaign_endpoint,
        "families_attempted_count": len(families_attempted),
        "families_failed_count": len(families_failed),
        "families_blocked_count": len(families_blocked),
        "historical_candidates_supported_count": 0,
        "structural_edges_certified_count": 0,
        "edge_claimed": False,
        "execution_viable": False,
        "prospective_supported": False,
        "runtime_authority": "NONE",
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False
    }

    with (campaign_dir / "campaign_manifest.json").open("w") as f:
        json.dump(manifest, f, indent=2)

    with (campaign_dir / "family_queue.json").open("w") as f:
        json.dump({
            "full_queue": FULL_FAMILY_QUEUE,
            "parked_or_failed": list(PARKED_OR_FAILED_FAMILIES),
            "completed_in_campaign": families_attempted
        }, f, indent=2)

    with (campaign_dir / "family_results.jsonl").open("w") as f:
        for item in results_ledger:
            f.write(json.dumps(item) + "\n")

    with (campaign_dir / "search_pressure.json").open("w") as f:
        json.dump({
            "total_families_in_catalog": len(PARKED_OR_FAILED_FAMILIES) + len(FULL_FAMILY_QUEUE),
            "parked_prior_to_campaign": len(PARKED_OR_FAILED_FAMILIES),
            "evaluated_in_campaign": len(families_attempted),
            "historical_supported": 0,
            "certified_edges": 0
        }, f, indent=2)

    with (campaign_dir / "failure_registry.md").open("w") as f:
        f.write("# Autonomous Structural Edge Campaign V2 Failure & Block Registry\n\n")
        f.write(f"**Campaign Endpoint**: `{campaign_endpoint}`\n\n")
        f.write("## Evaluated Family Failure Log\n")
        for entry in failure_entries:
            f.write(entry + "\n")

    print(f"\n==========================================")
    print(f"CAMPAIGN V2 COMPLETE. Endpoint: {campaign_endpoint}")
    print(f"==========================================")

if __name__ == "__main__":
    main()
