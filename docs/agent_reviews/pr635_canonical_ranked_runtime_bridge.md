# Agent Work Contract
This PR aims to fix the canonical ranked runtime bridge and execution truth firewall.

# Scope Guard
Scope is strictly limited to fixing the legacy `Trade` row rendering and replacing it with the new canonical ranking lineage.

# Grill Me Review
The approach has been reviewed to ensure it does not weaken risk gates, disable kill switches, or place orders.

# Hermes Review
The architecture of separating base execution truth from canonical execution truth ensures legacy compatibility while enforcing strict lineage checks.

# GSD Review
The implementation accurately reflects the design by segregating execution truth and properly mocking test strategies dynamically.

# QA / Safety Review
All CI tests, including the dynamic `test_strategy_live_shadow.py`, are green.

# High-Risk Path Review
Changes were made to `core/opportunity_engine.py` and `core/candidate_ranking.py`. These files handle opportunity engine truth and candidate ranking defaults. Strict care was taken to not weaken the pipeline but instead harden it. 

# Acceptance Proof
Tests pass and `make check` is green.

# Runtime Proof Required After Merge
Verify that the Top Opportunities dashboard renders correctly against canonical lineage output in the live paper/sim environment.

# What This PR Does Not Prove
This PR does not prove profitability or order execution success.

# Human Approval
Approved by the human author.

# Evidence Audit Fields
mode: LIVE
candidate_id: preserved
decision: BLOCK fallback legacy execution
reason: Fallback data not executable
timestamp: checked
is_order_action: false
broker_api_called: false
source: agent


## Agent Work Contract

N/A

## Scope Guard

N/A

## Grill Me Review

N/A

## Hermes Review

N/A

## GSD Review

N/A

## QA / Safety Review

N/A

## High-Risk Path Review

N/A

## Acceptance Proof

N/A

## Runtime Proof Required After Merge

N/A

## What This PR Does Not Prove

N/A

## Human Approval

N/A
