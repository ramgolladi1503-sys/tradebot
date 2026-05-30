# TB EDGE Candidate Unblock — Stabilization Evidence Pack

- Branch: `stabilization/tb-edge-candidate-unblock`
- Purpose: CI validation + evidence/observability pack only (no gate weakening, no LIVE enablement, no broker/order paths touched).
- Market note: market is closed for the next ~2 days; closed-market no-executable is not a production failure.

## Cluster commits (8)

| # | Commit | Cluster | Summary |
|---:|---|---|---|
| 1 | `af5d732` | LIVE quote truth contract propagation | Propagate real quote truth fields into Phase2 candidates without inventing LIVE truth. |
| 2 | `af05ae6` | Phase2 rejection reason evidence artifact | Add per-cycle Phase2 rejection reason counts artifact. |
| 3 | `603c5bf` | Feed freshness truth evidence | Add feed truth snapshot artifact distinguishing connected vs fresh vs closed-market. |
| 4 | `c789202` | Phase2 hard blocker truth evidence | Add hard-blocker source evidence + prevent stale counter reuse across cycles. |
| 5 | `ce684c7` | Candidate handoff / pre-Phase2 drop evidence | Add pre-Phase2 drop/normalization/dedup counters and survival evidence. |
| 6 | `2d0a6d6` | No-trade reason truth evidence | Add per-cycle primary no-trade reason truth (evidence-only; does not alter decisions). |
| 7 | `b867ffc` | Candidate row classification truth | Add operator-facing row classification fields (executable vs advisory vs debug) without changing Phase2. |
| 8 | `bfb1890` | Ranking quality evidence | Add ranking quality/score distribution evidence to detect score compression & sort correctness. |

## Files changed by cluster (high level)

Note: clusters are additive; later commits may touch previously-added evidence wiring.

- Cluster 1 (`af5d732`)
  - `strategies/trade_builder.py`
  - `core/_engine_phase2_adapter_base.py`
  - `tests/test_live_quote_truth_contract_phase2.py`
  - `docs/agent_reviews/live_quote_truth_contract_phase2.md`
- Cluster 2 (`af05ae6`)
  - `core/runtime_phase2_rejection_evidence.py`
  - `core/engine_phase2_adapter.py`
  - `tests/test_phase2_rejection_evidence_artifact.py`
- Cluster 3 (`603c5bf`)
  - `core/runtime_feed_truth_snapshot.py`
  - `core/orchestrator.py`
  - `tests/test_feed_truth_snapshot_evidence.py`
- Cluster 4 (`c789202`)
  - `core/_engine_phase2_adapter_base.py`
  - `core/runtime_phase2_rejection_evidence.py`
  - `tests/test_phase2_rejection_evidence_artifact.py`
- Cluster 5 (`ce684c7`)
  - `core/runtime_candidate_handoff_root_cause.py`
  - `core/orchestrator.py`
  - `tests/test_runtime_candidate_handoff_drop_evidence.py`
- Cluster 6 (`2d0a6d6`)
  - `core/runtime_notrade_reason_truth.py`
  - `core/orchestrator.py`
  - `tests/test_notrade_reason_truth_evidence.py`
- Cluster 7 (`b867ffc`)
  - `core/candidate_row_classification.py`
  - `core/orchestrator.py`
  - `tests/test_candidate_row_classification.py`
  - `tests/test_top_opportunities_row_classification_fields.py`
- Cluster 8 (`bfb1890`)
  - `core/runtime_ranking_quality_evidence.py`
  - `core/orchestrator.py`
  - `tests/test_ranking_quality_evidence.py`

## Artifacts added/extended (latest-per-cycle, machine-readable)

All artifacts are intended to be:
- read-only with respect to trading decisions
- exception-safe (writer failure must not crash decision path)
- non-append (latest snapshot semantics)
- tagged with safety flags:
  - `read_only=true`
  - `append=false`
  - `is_order_action=false`
  - `broker_api_called=false`

Artifacts (paths):
- `logs/candidate_handoff_latest.json`
- `.runtime/candidate_handoff_latest.json`
- `logs/feed_truth_latest.json`
- `.runtime/feed_truth_latest.json`
- `logs/phase2_rejection_latest.json`
- `.runtime/phase2_rejection_latest.json`
- `logs/notrade_reason_truth_latest.json`
- `.runtime/notrade_reason_truth_latest.json`
- `logs/ranking_quality_latest.json`
- `.runtime/ranking_quality_latest.json`
- `logs/top_opportunities_latest.json` (existing; enriched with row classification + cycle reason fields)

## Safety guarantees (explicit)

These commits must NOT:
- weaken Phase2 / NoTrade gates
- bypass stale-feed protections
- make fallback/recovered_fallback executable
- lower ranking thresholds or tune ranking weights
- touch broker/order execution code paths
- attempt LIVE mode enablement

Evidence writers:
- must not mutate candidates in a way that changes decisions
- must not crash the bot if evidence write fails

## Tests run

Local full suite executed on this branch:
- `PYTHONPATH=. python -m pytest -q tests`

Expected outcome:
- CI validates this branch with the same suite (no merges; draft PR only).

## Known limitations / risks

- Closed-market limitation: live tick proof and executable entry behavior cannot be validated during market closed; artifacts should reflect `market_closed_detected=true` and non-executable expectations.
- Evidence completeness: artifacts reflect what the current pipeline exposes; if upstream logic never emits certain fields, the artifacts will correctly report missing/unknown rather than invent values.

## Known flaky test

- Observed historically (pre-existing): `tests/test_live_mode_reconciliation_still_attempts_global_broker_auth.py`
  - If this flakes in CI, rerun once and capture logs; do not “fix” by weakening the test.

## What was not changed

- No changes to:
  - broker adapters / order placement
  - execution/risk kill-switch semantics
  - Phase2 scoring weights or ranking thresholds
  - strategy logic (beyond quote-truth field propagation required to satisfy Phase2 contract)
  - UI redesign (only payload enrichment for clearer row classification)

## Live validation plan (when market reopens)

1. Run a dry-live session (no broker/order calls) and capture the latest artifacts above.
2. Verify:
   - feed connected vs fresh truth separation (`feed_truth_latest.json`)
   - Phase2 rejection reasons match missing data vs hard blockers (`phase2_rejection_latest.json`)
   - row classes are consistent with Phase2 (`top_opportunities_latest.json`)
   - ranking separation and compression flags (`ranking_quality_latest.json`)
3. Only after evidence confirms root-cause, propose the next minimal fix cluster (separate PR).

