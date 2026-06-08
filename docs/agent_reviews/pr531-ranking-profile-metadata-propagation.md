# PR #531 — Ranking Profile Metadata Propagation

mode: PAPER
candidate_id: pr531-ranking-profile-metadata-propagation
signal_id: pr531-ranking-profile-metadata-propagation
strategy_id: ranking_profile_metadata_propagation
decision: REVIEW_ONLY
reason: read_only_profile_scoring_metadata_propagated_to_ranking_report
timestamp: 2026-06-08T17:15:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr531-ranking-profile-metadata-propagation.md

## Agent Work Contract

This PR propagates regime/profile scoring metadata from `OpportunityScoreReport` into `CandidateRankingReport`.

It does not change ranking order, ranking eligibility, feed-risk suppression, directional-balance behavior, runtime wiring, broker calls, order actions, dashboard behavior, or strategy generation.

## Scope Guard

In scope:

- Copy scorer profile metadata into ranking report metadata.
- Add explicit evidence that ranking sort still uses `opportunity_final_score`.
- Add explicit evidence that profile sort cutover is disabled.
- Add focused tests proving metadata propagation and default behavior.

Out of scope:

- No ranking-order change.
- No profile-adjusted sort cutover.
- No runtime wiring.
- No broker calls.
- No order actions.
- No feed/depth subscription changes.
- No dashboard/UI changes.
- No strategy changes.

## Grill Me Review

The main risk is accidentally changing candidate order while adding metadata. This PR avoids that by leaving `_sort_key(...)` untouched and adding a test that ranking order still follows existing `final_score` order.

The second risk is spreading profile metadata into plain iterable ranking inputs. This PR defaults profile fields to safe empty/null/false values when the input is not an `OpportunityScoreReport`.

The third risk is implying trading edge. This PR does not prove edge. It only improves ranking evidence visibility.

## Hermes Review

Changed files:

- `core/candidate_ranking.py`
- `tests/test_candidate_ranking_profile_metadata.py`
- `docs/agent_reviews/pr531-ranking-profile-metadata-propagation.md`

The PR intentionally avoids orchestrator, runtime, strategy, feed, execution, broker, risk, and dashboard modules.

## GSD Review

This PR is useful because after PR #530, profile-aware scoring may exist in the score report, but ranking evidence did not yet preserve whether profile scoring was applied. This PR keeps that metadata visible at the ranking boundary.

This supports later offline comparison without changing production ranking behavior.

## QA / Safety Review

Safety properties covered:

- Ranking remains read-only.
- Ranking does not mutate source score records.
- Ranking sort source is explicitly reported as `opportunity_final_score`.
- `profile_sort_cutover_enabled` is explicitly false.
- Profile metadata is copied only from source report metadata.
- Plain iterable inputs default profile metadata to false/null/empty dictionaries.
- Existing feed-risk and directional-balance logic remains untouched.

## Acceptance Proof

Focused commands:

```bash
PYTHONPATH=. pytest tests/test_candidate_ranking.py
PYTHONPATH=. pytest tests/test_candidate_ranking_profile_metadata.py
```

Expected proof:

- Existing ranking tests remain green.
- Profile metadata propagates into ranking metadata.
- Ranking order does not change.
- Plain iterable input remains safe and does not invent profile metadata.

## Runtime Proof Required After Merge

No runtime proof is required because this PR does not wire profile metadata into runtime execution, broker calls, feed subscriptions, dashboard rendering, or order paths.

## What This PR Does Not Prove

This PR does not prove trading edge.

It does not prove profile-aware ranking is better.

It does not enable profile sorting.

It does not wire profile scoring into PAPER runtime.

It only preserves profile scoring evidence at the ranking report boundary.

## Human Approval

Human approval is required before merge.

Do not merge only because the PR is green. Confirm that `_sort_key(...)` behavior remains unchanged and profile sort cutover is still false.
