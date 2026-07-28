# opening_range_retest_v1

Verdict: `ORB_OBJECTIVE_DEFECTS_REQUIRE_REPAIR`

Actual thesis: Production is a single completed-context breakout-near-boundary snapshot gated by minutes_since_open, spot, vwap, orb_high/orb_low; it does not encode prior breakout event, later retest event, hold event, or resume event as separate temporal stages.

Reachability: The current snapshot gate is theoretically reachable; true temporal retest reachability cannot be assessed because stages are not represented.

Objective defects: 1

Design ambiguities:
- Approved Level-1 temporal ORB retest contract absent; ORB duration and retest confirmation details require human approval if not already accepted elsewhere.
