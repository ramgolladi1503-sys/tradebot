from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class RankedCandidate:
    candidate_id: str
    symbol: str
    score: float
    execution_score: float
    regime_score: float
    confidence: float
    score_breakdown: dict = field(default_factory=dict)

def build_opportunity_book(candidates: List[dict]) -> List[RankedCandidate]:
    ranked=[]
    for c in candidates:
        ranked.append(RankedCandidate(str(c.get("trade_id")),str(c.get("symbol")),float(c.get("final_score",0.0)),float(c.get("execution_score",0.0)),float(c.get("regime_alignment",0.0)),float(c.get("gating_final_confidence",0.0)),c.get("score_breakdown",{})))
    ranked.sort(key=lambda x:x.score,reverse=True)
    return ranked
