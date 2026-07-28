# vwap_reclaim_rejection_v1

Verdict: `VWAP_RECLAIM_STRATEGY_INTENT_AMBIGUOUS`

Actual thesis: Production checks current distance from ctx.vwap and confirmation metadata or immediate previous_spot_ltp crossing VWAP. It does not itself validate completed-history establishment, hold, duplicate/order/session/symbol integrity, or distinguish rejection from reclaim beyond metadata flags.

Reachability: The distance gate is theoretically reachable for FRACTION units between 0.00035 and 0.0035; edge testing readiness depends on freezing a history/VWAP owner and temporal sequence.

Objective defects: 0

Design ambiguities:
- Intended VWAP owner and whether metadata flags are authoritative are unresolved because test support/provenance files are absent. Rejection sequence semantics require design approval.
