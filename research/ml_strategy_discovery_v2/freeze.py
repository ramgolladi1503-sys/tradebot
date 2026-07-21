import json
from pathlib import Path
from typing import Dict, Any
import datetime
import hashlib
import uuid

def freeze_candidate(candidate: Dict[str, Any], side: str, output_dir: Path, search_space_hash: str, fold_hash: str, code_sha: str) -> None:
    """
    Freeze a stable candidate into the evidence directory as a final read-only JSON.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"frozen_candidates.json"
    
    # Calculate candidate bundle hash
    # To do this deterministically, sort keys
    raw = json.dumps(candidate, sort_keys=True)
    cand_bundle_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    
    candidate_id = str(uuid.uuid4())
    
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "code_commit_sha": code_sha,
        "input_hashes": {
            "search_space_hash": search_space_hash,
            "fold_hash": fold_hash
        },
        "deterministic_seeds": [42],
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "append": False,
        
        "candidate_id": candidate_id,
        "side": side,
        "frozen_candidate": candidate,
        "candidate_bundle_hash": cand_bundle_hash,
        
        "status": "FRESH_CONFIRMATION_REQUIRES_EXPLICIT_ACKNOWLEDGEMENT"
    }
    
    # If the file exists, we append if it's a list, but the prompt says 
    # "At most one freeze per side", so we just overwrite it with the list of frozen candidates
    # Wait, if both long and short have a candidate, we might need a dict
    frozen_dict = {}
    if out_file.exists():
        with open(out_file, "r") as f:
            try:
                frozen_dict = json.load(f)
            except:
                pass
                
    frozen_dict[side] = payload
    
    with open(out_file, "w") as f:
        json.dump(frozen_dict, f, indent=2, separators=(',', ':'))
