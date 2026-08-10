# V3 Batch Evidence Invalidation Report

CONTROLLED_VERDICT: V3_BATCH_INVALIDATED_IMPLEMENTATION_DEFECT
INVALIDATED_COMMIT: f985a446836d5a4a14b0ece55b9df08bd1ce48b6
REASON_1: evaluator did not enforce all grammar fields (e.g., window, vol_regime, gap_direction, preclose_state)
REASON_2: placeholder candidates were counted as valid specs
REASON_3: window constraints were not consistently enforced across episode timestamps
EDGE_CLAIMED: false
STRUCTURAL_EDGE_CERTIFIED: false
EXECUTION_VIABLE: false
LOCKED_OUTCOMES_ACCESSED: false
NEXT_ACTION: REPAIR_V3_GRAMMAR_AND_EVALUATOR

## Explanation
An independent review of commit `f985a4468` identified that the candidate evaluator failed to evaluate specific grammar fields (`window`, `opening_state`, `preclose_state`, `vol_regime`, `gap_direction`, etc.), defaulting to broad state matching. Additionally, generic placeholder specifications (`MASSIVE_GRAMMAR_CATEGORY_*`) were counted towards the 1,000 spec threshold without evaluating concrete pre-outcome predicates.

Per repository governance rules, this batch is invalidated. History is preserved and repaired forward.
