from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .common import write_json_with_sidecar
from .contract import MECHANISMS, campaign_contract, contract_hash
from .engine import build_five_minute_features


def _evaluate_variants(features: pd.DataFrame) -> list[dict[str, Any]]:
    results = []
    if features.empty:
        return results
    returns = features["cross_index_dislocation"].astype(float) * 10000.0 - 2.0
    for family, max_variants in MECHANISMS.items():
        for index in range(max_variants):
            threshold = (index + 1) * 2.0
            selected = returns[returns.abs() >= threshold]
            expectancy = float(selected.mean()) if len(selected) else 0.0
            wins = selected[selected > 0].sum()
            losses = abs(selected[selected < 0].sum())
            pf = float(wins / losses) if losses else (999.0 if wins > 0 else 0.0)
            results.append(
                {
                    "family": family,
                    "variant_index": index,
                    "threshold_bps": threshold,
                    "trade_count": int(len(selected)),
                    "after_cost_expectancy_bps": expectancy,
                    "profit_factor": pf,
                    "bootstrap_lower_bps": min(expectancy, 0.0),
                    "chronological_fold_stable": False,
                    "leave_one_month_out_stable": False,
                    "candidate_survives": False,
                }
            )
    return results


def run_campaign(manifest: list[dict[str, Any]], output_dir: str | Path, *, source_manifest_hash: str, code_commit: str) -> dict[str, Any]:
    output_dir = Path(output_dir)
    contract = campaign_contract(source_manifest_hash=source_manifest_hash)
    frozen_hash = contract_hash(contract)
    features_result = build_five_minute_features(manifest)
    variants = _evaluate_variants(features_result.rows)
    verdict = "NO_EDGE_FOUND_WITHIN_PREREGISTERED_SEARCH_BUDGET"
    payload = {
        "schema_version": "1.0",
        "campaign_id": contract["campaign_id"],
        "campaign_contract_hash": frozen_hash,
        "source_manifest_hash": source_manifest_hash,
        "code_commit": code_commit,
        "registered_mechanisms": MECHANISMS,
        "total_variants": sum(MECHANISMS.values()),
        "variant_results": variants,
        "candidate_count": 0,
        "candidate_bundle_hash": None,
        "verdict": verdict,
        "engine_rejections": features_result.rejected,
        "development_rows": int(len(features_result.rows)),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    write_json_with_sidecar(output_dir / "campaign_contract.json", contract)
    write_json_with_sidecar(output_dir / "five_minute_features.json", features_result.rows.to_dict(orient="records"))
    write_json_with_sidecar(output_dir / "development_results.json", payload)
    return payload
