import json
from pathlib import Path

def mark_blocked():
    out_dir = Path("runtime/strategy_validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    data = {
        "dataset_id": "resolved_option_ticks_20260702",
        "dataset_path": "runtime/strategy_validation/resolved_option_ticks_20260702.parquet",
        "status": "BLOCKED_FOR_CERTIFICATION",
        "allowed_use": "RESEARCH_DEBUG_ONLY",
        "certification_allowed": False,
        "candidate_replay_allowed": False,
        "paper_live_allowed": False,
        "live_allowed": False,
        "broker_order_allowed": False,
        "execution_allowed": False,
        "blockers": [
            "FILTERED_DATASET_INSTRUMENT_MASTER_DATE_UNKNOWN",
            "FILTERED_DATASET_SPREAD_OUTLIER_RATE_TOO_HIGH"
        ],
        "reason": "Token-index lineage is blocked because instrument-master date is unknown, and quote spread outlier rate is too high.",
        "next_action": "Capture a fresh date-aligned instrument master and option tick/depth dataset on the next market day."
    }
    
    with open(out_dir / "blocked_datasets.json", "w") as f:
        json.dump([data], f, indent=2)
        
    md = [
        "# Blocked Certification Datasets\n",
        f"## {data['dataset_id']}",
        f"- Path: {data['dataset_path']}",
        f"- Status: {data['status']}",
        f"- Allowed Use: {data['allowed_use']}",
        f"- Reason: {data['reason']}",
        f"- Next Action: {data['next_action']}",
        "### Blockers:",
    ]
    for b in data["blockers"]:
        md.append(f"  * {b}")
        
    md.append("\n### Safety Flags:")
    md.append(f"- certification_allowed: {data['certification_allowed']}")
    md.append(f"- candidate_replay_allowed: {data['candidate_replay_allowed']}")
    md.append(f"- paper_live_allowed: {data['paper_live_allowed']}")
    md.append(f"- live_allowed: {data['live_allowed']}")
    md.append(f"- broker_order_allowed: {data['broker_order_allowed']}")
    md.append(f"- execution_allowed: {data['execution_allowed']}")
    
    with open(out_dir / "blocked_datasets.md", "w") as f:
        f.write("\n".join(md) + "\n")

if __name__ == "__main__":
    mark_blocked()
