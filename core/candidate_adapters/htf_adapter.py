from core.candidate_audits.models import Signal, Rejection
from core.candidate_intent import CandidateIntent, INTENT_TYPE_ENTRY, INTENT_TYPE_NO_TRADE, create_candidate_intent
from core.candidate_intent_pool import CandidateIntentPoolReport, build_candidate_intent_pool

def build_htf_candidate_intents(result, execution_mode="PAPER") -> CandidateIntentPoolReport:
    """Adapts HTF legacy output to standard CandidateIntents that can pass through execution gates."""
    
    if isinstance(result, Rejection):
        intent = create_candidate_intent(
            strategy_id=result.setup_name,
            instrument=result.symbol,
            direction="NO_TRADE",
            regime="UNKNOWN",
            family="HTF",
            intent_type=INTENT_TYPE_NO_TRADE,
            trigger="HTF_REJECTED",
            invalidation=result.reason,
            required_evidence_keys=("htf_rejection",),
            blockers=(result.reason,),
            metadata={"execution_mode": execution_mode}
        )
        return build_candidate_intent_pool([intent])
        
    elif isinstance(result, Signal):
        direction = "BUY_CALL" if result.target > result.entry_price else "BUY_PUT"
        intent = create_candidate_intent(
            strategy_id=result.setup_name,
            instrument=result.symbol,
            direction=direction,
            regime=result.regime,
            family="HTF",
            intent_type=INTENT_TYPE_ENTRY,
            trigger="HTF_SIGNAL",
            invalidation="HTF_INVALIDATION",
            required_evidence_keys=("htf_signal",),
            metadata={
                "entry_price": result.entry_price,
                "target": result.target,
                "stop_loss": result.stop_loss,
                "risk_points": result.risk_points,
                "execution_mode": execution_mode
            }
        )
        return build_candidate_intent_pool([intent])
    
    return build_candidate_intent_pool([])
