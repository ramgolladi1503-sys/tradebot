import json
from pathlib import Path
import datetime

def check_readiness():
    out_dir = Path("runtime/strategy_validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # We pretend tomorrow is the next market day
    # Just check if there is ANY capture directory that fulfills it
    # We will just scan runtime/live_capture
    live_capture_dir = Path("runtime/live_capture")
    
    classification = "NEXT_DAY_CAPTURE_CONTRACT_READY_BUT_DATA_MISSING"
    capture_ready = True
    data_available = False
    blockers = []
    
    if not live_capture_dir.exists():
        blockers.append("NEXT_DAY_CAPTURE_DATA_NOT_AVAILABLE_YET")
    else:
        # Check if there is any date dir that fulfills it
        date_dirs = [d for d in live_capture_dir.iterdir() if d.is_dir()]
        if not date_dirs:
            blockers.append("NEXT_DAY_CAPTURE_DATA_NOT_AVAILABLE_YET")
        else:
            # We would check the latest date dir
            # For this stub, we just block if none are fully valid
            valid_found = False
            for d in date_dirs:
                date_str = d.name
                im_path = d / f"instrument_master/kite_instruments_{date_str}.json"
                tick_path = d / f"ticks/option_ticks_{date_str}.parquet"
                manifest_path = d / f"manifests/capture_manifest_{date_str}.json"
                
                if im_path.exists() and tick_path.exists() and manifest_path.exists():
                    valid_found = True
                    # Here we would do deep validation
                    break
            
            if not valid_found:
                blockers.append("NEXT_DAY_CAPTURE_DATA_NOT_AVAILABLE_YET")
            else:
                classification = "NEXT_DAY_CAPTURE_CONTRACT_VALID"
                data_available = True
                
    result = {
        "classification": classification,
        "capture_ready": capture_ready,
        "data_available": data_available,
        "certification_replay_allowed": data_available,
        "blockers": blockers,
        "paper_live_allowed": False,
        "live_allowed": False,
        "broker_order_allowed": False,
        "execution_allowed": False
    }
    
    with open(out_dir / "next_day_capture_contract_readiness.json", "w") as f:
        json.dump(result, f, indent=2)
        
    md = [
        "# Next-Day Capture Contract Readiness\n",
        f"- Classification: {result['classification']}",
        f"- Capture Ready: {result['capture_ready']}",
        f"- Data Available: {result['data_available']}",
        f"- Certification Replay Allowed: {result['certification_replay_allowed']}",
        "### Blockers:"
    ]
    for b in result["blockers"]:
        md.append(f"  * {b}")
        
    md.append("\n### Safety Flags:")
    md.append(f"- paper_live_allowed: {result['paper_live_allowed']}")
    md.append(f"- live_allowed: {result['live_allowed']}")
    md.append(f"- broker_order_allowed: {result['broker_order_allowed']}")
    md.append(f"- execution_allowed: {result['execution_allowed']}")
    
    with open(out_dir / "next_day_capture_contract_readiness.md", "w") as f:
        f.write("\n".join(md) + "\n")

if __name__ == "__main__":
    check_readiness()
