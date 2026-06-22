# Probability Semantics Audit

Generic "chance %" or "confidence %" from heuristics is unsafe because it implies probability without an outcome contract. 

## Requirements for Real Probability
A real probability requires:
- A predefined event (e.g., `TARGET_BEFORE_STOP`).
- A specific horizon (e.g., 30 minutes).
- A cost model.

When candidates lack this, the UI must fallback to a generic `Setup score: X/100`. Fallback and stale candidates are fundamentally untrustworthy for execution and must never show executable probability.
