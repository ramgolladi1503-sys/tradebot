# TOD Session Position Family Parking Report

CONTROLLED_VERDICT: STRUCTURAL_EDGE_NOT_CERTIFIED
REASON: NEGATIVE_CONTROLS_FAILED
DEVELOPMENT_SUPPORTED: true
LOCKED_SUPPORTED: true
WFA_ROBUSTNESS_SUPPORTED: true
COST_SLIPPAGE_SUPPORTED_INDEX_ONLY: true
EXECUTION_VIABLE: false
PROSPECTIVE_SUPPORTED: false
STRUCTURAL_EDGE_CERTIFIED: false
EDGE_CLAIMED: false
NEXT_ACTION: CONTINUE_TO_NEXT_MATERIALLY_DISTINCT_FAMILY

## Diagnosis & Explanation
Candidate `TIME_OF_DAY_SESSION_POSITION_FAMILY_V1_PRE_CLOSE_30_UPSIDE_ESCAPE` passed development, locked out-of-sample, WFA robustness, and index-bps cost tests. However, it **failed negative specificity controls** (`NEGATIVE_CONTROLS_FAILED`).

Specifically, control tests showed that the observed return/excursion characteristics are not specific to the `PRE_CLOSE_30_UPSIDE_ESCAPE` state/time combination, as comparable control permutations (such as wrong state or wrong time window) also passed edge gates. This indicates that the phenomenon represents a broad session-close upward drift or general state effect rather than a certified, isolated structural edge.

Options execution data or execution-level tuning cannot rescue a signal that fails specificity controls. Therefore, `TIME_OF_DAY_SESSION_POSITION_FAMILY_V1` is formally parked, and discovery proceeds to the next materially distinct family.
