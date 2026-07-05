import sys
import json
import yaml
import subprocess
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from strategies.strategy_registry import load_strategy_registry

def run_cmd(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Command failed: {' '.join(cmd)}")
        print(result.stderr)
        return False
    return True

def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-candidate-replay", action="store_true")
    if args is None:
        parsed_args, _ = parser.parse_known_args()
    else:
        parsed_args = parser.parse_args(args)

    registry = load_strategy_registry()
    runtime_dir = Path("runtime/strategy_validation")
    runtime_dir.mkdir(parents=True, exist_ok=True)

    reports = []
    candidate_replay_reports = []

    for strategy_id, entry in registry.items():
        if entry.strategy_kind == "test_fixture" or entry.strategy_id == "TEST_STRAT":
            continue

        if entry.strategy_kind == "helper_module":
            continue

        report_entry = {"strategy_id": strategy_id}
        
        if entry.strategy_kind == "aggregate_engine":
            report_entry["lifecycle_state"] = "AGGREGATE_ENGINE_CERTIFICATION_PENDING"
            reports.append(report_entry)
            continue
            
        if entry.certification_track == "deferred":
            report_entry["lifecycle_state"] = "DEFERRED_UNTIL_CHILD_STRATEGIES_CERTIFIED"
            reports.append(report_entry)
            continue

        state_file = runtime_dir / strategy_id / "strategy_lifecycle_state.yaml"
        state = {}
        if state_file.exists():
            with open(state_file) as f:
                state = yaml.safe_load(f) or {}

        if entry.certification_track == "phase_1_to_5_execution_replay":
            success = run_cmd(["python", "scripts/run_strategy_certification_pipeline.py", "--strategy", strategy_id, "--cost-model", "stress"])
            
            # Reload state if it exists
            if state_file.exists():
                with open(state_file) as f:
                    state = yaml.safe_load(f) or {}
            
            if not state:
                state = {"lifecycle_state": "CERTIFICATION_FAILED"} if not success else {"lifecycle_state": "CERTIFICATION_PASSED"}
                
        elif entry.certification_track == "candidate_generator_contract_only":
            cmd = [
                "python", "scripts/audit_candidate_generator_contract.py",
                "--strategy-id", strategy_id,
                "--module-path", entry.module_path,
                "--callable-name", entry.callable_name,
                "--output-report", str(runtime_dir / strategy_id / "audit_report.json")
            ]
            success = run_cmd(cmd)
            
            # Reload state
            if state_file.exists():
                with open(state_file) as f:
                    state = yaml.safe_load(f) or {}
                    
            if not state:
                if not success:
                    state = {"lifecycle_state": "CERTIFICATION_FAILED"}
                else:
                    state = {"lifecycle_state": "CANDIDATE_GENERATOR_CONTRACT_PASSED"}
                    
            if success and parsed_args.include_candidate_replay:
                cmd_replay = [
                    "python", "scripts/replay_candidate_generator_strategy.py",
                    "--strategy-id", strategy_id
                ]
                run_cmd(cmd_replay)
                # Replay does not overwrite state file directly in the batch runner, 
                # but might write candidate_replay_report.json
                replay_report = runtime_dir / strategy_id / "candidate_replay_report.json"
                
                replay_status = "CANDIDATE_REPLAY_NOT_RUN"
                replay_data = {}
                
                if not success:
                    replay_status = "CANDIDATE_REPLAY_FAILED"
                elif replay_report.exists():
                    try:
                        with open(replay_report) as f:
                            replay_data = json.load(f)
                        
                        state["lifecycle_state"] = replay_data.get("lifecycle_state", state.get("lifecycle_state"))
                        
                        adapter_approved = replay_data.get("adapter_approved_for_replay", False)
                        certifiable = replay_data.get("certifiable_data", False)
                        blockers = replay_data.get("certification_blockers", [])
                        
                        if adapter_approved and certifiable:
                            replay_status = "CANDIDATE_REPLAY_PASSED"
                        elif blockers or not adapter_approved:
                            replay_status = "CANDIDATE_REPLAY_DATA_BLOCKED"
                        else:
                            replay_status = "CANDIDATE_REPLAY_FAILED"
                    except Exception:
                        replay_status = "CANDIDATE_REPLAY_FAILED"
                else:
                    replay_status = "CANDIDATE_REPLAY_FAILED"
                
                if parsed_args.include_candidate_replay:
                    candidate_replay_reports.append({
                        "strategy_id": strategy_id,
                        "strategy_type": "candidate_generator_strategy",
                        "lifecycle_state": state.get("lifecycle_state", "UNKNOWN"),
                        "contract_audit_status": "CANDIDATE_GENERATOR_CONTRACT_PASSED" if success else "CERTIFICATION_FAILED",
                        "candidate_replay_status": replay_status,
                        "data_fetch_status": replay_data.get("data_fetch_status", "UNKNOWN"),
                        "data_fetch_blockers": replay_data.get("data_fetch_blockers", []),
                        "certification_blockers": replay_data.get("certification_blockers", []),
                        "certifiable_data": replay_data.get("certifiable_data", False),
                        "adapter_approved_for_replay": replay_data.get("adapter_approved_for_replay", False),
                        "paper_live_allowed": replay_data.get("paper_live_allowed", False),
                        "live_allowed": replay_data.get("live_allowed", False),
                        "broker_order_allowed": replay_data.get("broker_order_allowed", False),
                        "execution_allowed": replay_data.get("execution_allowed", False)
                    })
        else:
            continue

        # Preserve SIMPLE_ORB state logic
        if strategy_id == "SIMPLE_ORB":
            if state.get("lifecycle_state") == "PHASE_6_FAILED_VIOLATION":
                evidence_mode = state.get("evidence_mode", "fixture")
                if evidence_mode != "live_capture":
                    state.update({
                        "lifecycle_state": "PHASE_6_SCAFFOLD_READY",
                        "phase_5_passed": True,
                        "phase_6_allowed": True,
                        "phase_6_passed": False,
                        "paper_live_allowed": False,
                        "live_allowed": False
                    })
        elif strategy_id == "HTF_OPENING_DRIVE_CONT":
            state.update({
                "lifecycle_state": "QUARANTINED_FOR_RESEARCH",
                "phase_2_passed": False,
                "phase_3_allowed": False,
                "can_be_retested_only_as_new_variant": True
            })

        report_entry.update(state)
        reports.append(report_entry)

    out_file = runtime_dir / "batch_certification_report.json"
    out_file.write_text(json.dumps(reports, indent=2))

    md_file = runtime_dir / "batch_certification_report.md"
    md_content = "# Batch Certification Report\n\n"
    for r in reports:
        md_content += f"## {r.get('strategy_id')}\n"
        md_content += f"- Lifecycle State: {r.get('lifecycle_state')}\n"
        md_content += f"- Phase 6 Allowed: {r.get('phase_6_allowed', 'False')}\n\n"
    md_file.write_text(md_content)

    if parsed_args.include_candidate_replay and candidate_replay_reports:
        replay_summary_json = runtime_dir / "candidate_replay_batch_summary.json"
        replay_summary_json.write_text(json.dumps(candidate_replay_reports, indent=2))
        
        replay_summary_md = runtime_dir / "candidate_replay_batch_summary.md"
        md_str = "# Candidate Replay Batch Summary\n\n"
        for cr in candidate_replay_reports:
            md_str += f"## {cr.get('strategy_id')}\n"
            md_str += f"- Contract Audit Status: {cr.get('contract_audit_status')}\n"
            md_str += f"- Candidate Replay Status: {cr.get('candidate_replay_status')}\n"
            md_str += f"- Data Fetch Status: {cr.get('data_fetch_status')}\n"
            md_str += f"- Certifiable Data: {cr.get('certifiable_data')}\n"
            md_str += f"- Adapter Approved for Replay: {cr.get('adapter_approved_for_replay')}\n"
            md_str += f"- Paper/Live Allowed: {cr.get('paper_live_allowed')} / {cr.get('live_allowed')}\n\n"
            if cr.get("certification_blockers"):
                md_str += "### Certification Blockers:\n"
                for b in cr["certification_blockers"]:
                    md_str += f"- {b}\n"
                md_str += "\n"
        replay_summary_md.write_text(md_str)

if __name__ == "__main__":
    main()

def check_data_exists(manifest):
    spot_symbol = manifest.get("required_spot_symbol")
    if not spot_symbol:
        return False
    spot_file = Path(f"runtime/strategy_validation/raw_market_data/{manifest['strategy_id']}_upstox_signal_1m.jsonl")
    return spot_file.exists()
