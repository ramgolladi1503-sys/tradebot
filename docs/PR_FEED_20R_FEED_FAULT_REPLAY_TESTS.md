# PR-FEED-20R — End-to-End Feed Fault Replay Tests

## Purpose

This PR corrects the roadmap gap after PR #253. The canonical roadmap item for PR-FEED-20 is **End-to-End Feed Fault Replay Tests**. PR #253 added a useful read-only feed runtime evidence bundle, but it did not complete the replay-test acceptance proof.

PR-FEED-20R adds focused replay tests that prove feed faults flow through the canonical feed evidence, policy, hold, and ranking contracts.

## Scope

In scope:

- Add feed fault replay tests only.
- Replay healthy → stale → recovered feed states.
- Replay websocket disconnect → reconnect.
- Replay option subscription failure.
- Prove the same payload can pass PAPER policy and fail LIVE policy.
- Prove feed faults produce zero executable rankings while recovered feed restores ranking.
- Prove evidence remains read-only and non-action.

Out of scope:

- No websocket lifecycle changes.
- No reconnect implementation.
- No resubscribe implementation.
- No token resolver changes.
- No runtime file writing.
- No dashboard work.
- No strategy changes.
- No broker calls.
- No order behavior.

## Acceptance proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_pr_feed_20r_feed_fault_replay_tests.py tests/test_pr_feed_20_feed_runtime_evidence_bundle.py tests/test_pr_feed_16_feed_config_hardening.py tests/test_pr_feed_15_live_paper_feed_policy.py
```

Required proof:

- Healthy feed allows executable ranking.
- Stale feed activates hold and produces zero executable ranking.
- Recovered feed clears hold and restores executable ranking.
- Websocket disconnect blocks until reconnect.
- Subscription failure blocks symbol-level feed.
- LIVE is stricter than PAPER for the same payload.
- Replay bundle and ranking evidence are read-only and non-action.

## Risk

Low. This PR adds tests only. It does not change production runtime, feed transport, ranking implementation, strategy behavior, dashboard behavior, broker behavior, or order behavior.

## Next PR

After this PR is merged and CI is green, the feed hardening phase can move to Phase B: EDGE-63 — MarketState Model.
