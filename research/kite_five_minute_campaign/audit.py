from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import canonical_hash, write_json_with_sidecar
from .contract import MECHANISMS


def audit_campaign(input_dir: str | Path, campaign_dir: str | Path, output: str | Path) -> dict[str, Any]:
    input_dir = Path(input_dir)
    campaign_dir = Path(campaign_dir)
    accepted = json.loads((input_dir / "accepted_underlying_manifest.json").read_text())
    summary = json.loads((input_dir / "corpus_summary.json").read_text())
    results = json.loads((campaign_dir / "development_results.json").read_text())
    candidate_hashes = [
        item.get("candidate_bundle_hash")
        for item in results.get("variant_results", [])
        if item.get("candidate_survives")
    ]
    recomputed_verdict = (
        "CANDIDATE_FROZEN" if candidate_hashes else "NO_EDGE_FOUND_WITHIN_PREREGISTERED_SEARCH_BUDGET"
    )
    payload = {
        "schema_version": "1.0",
        "accepted_file_counts": summary["accepted_counts_by_instrument"],
        "date_range": summary["date_coverage"],
        "session_counts_by_instrument": {
            instrument: len({row["trading_date"] for row in accepted if row["instrument"] == instrument})
            for instrument in ("NIFTY", "BANKNIFTY", "SENSEX")
        },
        "variant_counts": results["registered_mechanisms"],
        "candidate_count": len(candidate_hashes),
        "candidate_hashes": candidate_hashes,
        "final_campaign_verdict": recomputed_verdict,
        "matches_primary_verdict": recomputed_verdict == results["verdict"],
        "audit_hash": canonical_hash(results),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    write_json_with_sidecar(Path(output), payload)
    return payload
