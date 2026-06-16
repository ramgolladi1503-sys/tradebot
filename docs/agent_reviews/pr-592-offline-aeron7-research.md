# Agent Work Contract
Add offline Aeron7 ML research pipeline and regime evaluation.

# Scope Guard
Only offline analytical scripts in `scripts/` and `tests/` are added. Live trading logic remains untouched.

# Grill Me
The changes were heavily reviewed for live safety. This only introduces offline logic.

# Hermes
We structured the pipeline logically: canonicalize -> label -> evaluate models per regime.

# GSD
Files created and integrated efficiently with zero runtime impact.

# QA/Safety
Tests were added and executed for the offline research module. No live feed components were touched.

# Acceptance Proof
```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
append=false
```

# Runtime Proof Required After Merge
None, as this only affects offline ML workflows.

# What This PR Does Not Prove
This PR does not prove that the ML model will be profitable in live trading.

# Human Approval
The user requested this PR to be opened manually.
