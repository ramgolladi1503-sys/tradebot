"""CandidateIntent generator for Pairs Trading."""

from __future__ import annotations

import time
from typing import Any, Mapping
from dataclasses import dataclass, field

from core.candidate_intent import CandidateIntent, INTENT_TYPE_ENTRY, INTENT_TYPE_NO_TRADE, create_candidate_intent
from core.candidate_intent_pool import CandidateIntentPoolReport, build_candidate_intent_pool
from config import config as cfg

PAIRS_CANDIDATE_GENERATOR_SCHEMA_VERSION = 1
PAIRS_CANDIDATE_GENERATOR_SOURCE = "pairs_candidate_generator_v1"

@dataclass(frozen=True)
class PairsCandidateGenerationReport:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    generated_intents: tuple[CandidateIntent, ...]
    pool_report: CandidateIntentPoolReport
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def valid(self) -> bool:
        return not self.blockers and self.pool_report.valid

    @property
    def pool_ready(self) -> bool:
        return self.valid and self.pool_report.pool_ready

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "valid": self.valid,
            "pool_ready": self.pool_ready,
            "generated_count": len(self.generated_intents),
            "candidate_intent_ids": [intent.candidate_intent_id for intent in self.generated_intents],
            "generated_intents": [intent.to_payload() for intent in self.generated_intents],
            "pool_report": self.pool_report.to_payload(),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
            "is_order_action": False,
            "broker_api_called": False,
        }
        return payload

def build_pairs_candidate_intents(
    cross_asset_data: Mapping[str, Any],
    min_zscore: float = 2.0,
    strategy_id: str = "pairs_arbitrage_v1"
) -> PairsCandidateGenerationReport:
    """Build pairs trading intents based on spread z-scores."""
    intents = []
    blockers = []
    warnings = []
    
    features = cross_asset_data.get("features", {})
    pairs_universe = getattr(cfg, "PAIRS_TRADING_UNIVERSE", {})
    
    for pair_name, pair_cfg in pairs_universe.items():
        leg_a = pair_cfg.get("leg_a")
        leg_b = pair_cfg.get("leg_b")
        hedge_ratio = pair_cfg.get("hedge_ratio", 1.0)
        
        prices = cross_asset_data.get("prices", {})
        price_a = prices.get(leg_a)
        price_b = prices.get(leg_b)
        
        if not price_a or not price_b:
            warnings.append(f"Missing prices for {pair_name}")
            continue
            
        # Use true rolling spread z-score and beta if available from cross_asset
        spread_z = features.get(f"x_{pair_name.lower()}_spread_z")
        beta = features.get(f"x_{pair_name.lower()}_beta", hedge_ratio)
        
        # Fallback to proxy if true spread isn't ready
        if spread_z is None:
            z_a = features.get(f"x_{leg_a.lower()}_z")
            z_b = features.get(f"x_{leg_b.lower()}_z")
            
            if z_a is None or z_b is None:
                warnings.append(f"Missing z-scores for {pair_name}")
                continue
                
            spread_z = z_a - (beta * z_b)
        
        direction = "NO_TRADE"
        intent_type = INTENT_TYPE_NO_TRADE
        
        if spread_z > min_zscore:
            direction = "SHORT"
            intent_type = INTENT_TYPE_ENTRY
        elif spread_z < -min_zscore:
            direction = "LONG"
            intent_type = INTENT_TYPE_ENTRY
            
        cointegrated = features.get(f"x_{pair_name.lower()}_cointegrated", False)
        adf_pvalue = features.get(f"x_{pair_name.lower()}_adf_pvalue", 1.0)
        
        if not cointegrated and intent_type != INTENT_TYPE_NO_TRADE:
            blockers.append("cointegration_broken")
            
        if adf_pvalue > 0.05 and intent_type != INTENT_TYPE_NO_TRADE:
            blockers.append("spread_not_cointegrated_adf_strict")
            
        if intent_type != INTENT_TYPE_NO_TRADE:
            intent = create_candidate_intent(
                strategy_id=strategy_id,
                instrument=pair_name,
                direction=direction,
                regime="RANGE",
                family="statistical_arbitrage",
                intent_type=intent_type,
                trigger="spread_zscore_extended",
                invalidation="spread_zscore_mean_reverted",
                required_evidence_keys=("cross_asset_health",),
                blockers=(),
                warnings=(),
                metadata={
                    "spread_z": spread_z,
                    "z_a": features.get(f"x_{leg_a.lower()}_z"),
                    "z_b": features.get(f"x_{leg_b.lower()}_z"),
                    "leg_a": leg_a,
                    "leg_b": leg_b,
                    "beta": beta,
                    "does_not_rank_candidates": True,
                    "does_not_score_edge": True,
                }
            )
            intents.append(intent)

    pool_report = build_candidate_intent_pool(tuple(intents))
    return PairsCandidateGenerationReport(
        schema_version=PAIRS_CANDIDATE_GENERATOR_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=PAIRS_CANDIDATE_GENERATOR_SOURCE,
        generated_intents=tuple(intents),
        pool_report=pool_report,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )
