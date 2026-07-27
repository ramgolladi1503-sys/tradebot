from __future__ import annotations


def build_lane_status(contract) -> dict[str, object]:
    return {
        "strategy_or_hypothesis_id": contract.strategy_or_hypothesis_id,
        "source_domain": contract.source_domain,
        "discovery_status": contract.discovery_status,
        "directional_eligibility": contract.directional_eligibility,
    }
