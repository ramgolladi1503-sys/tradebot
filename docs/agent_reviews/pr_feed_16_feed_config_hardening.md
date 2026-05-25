# Agent Review Evidence — PR-FEED-16 Feed Config Hardening

## Agent Work Contract

### Goal

Add read-only validation for feed-policy config so invalid LIVE/PAPER/SIM threshold configuration cannot be silently trusted.

### Files changed

- `core/feed_policy.py`
- `tests/test_pr_feed_16_feed_config_hardening.py`
- `docs/PR_FEED_16_FEED_CONFIG_HARDENING.md`
- `docs/agent_reviews/pr_feed_16_feed_config_hardening.md`

### Evidence Contract Fields

mode: PAPER
candidate_id: PR_FEED_16_FEED_CONFIG_HARDENING
message_decision: READ_ONLY_FEED_CONFIG_HARDENING
decision: READ_ONLY_FEED_CONFIG_HARDENING
reason: Feed policy config now validates mode coverage, finite thresholds, strictness ordering, and required LIVE/PAPER truth gates.
timestamp: 2026-05-25T10:02:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr_feed_16_feed_config_hardening.md

### Non-goals

- No websocket lifecycle changes.
- No reconnect logic.
- No resubscribe logic.
- No token resolver changes.
- No dashboard changes.
- No strategy changes.
- No broker calls.
- No order creation.

## Grill Me Review

### Pushback

Policy separation is not enough if bad thresholds can be passed later and accepted silently. Config must be audited and must fail closed when unsafe.

### Required proof

- Missing LIVE/PAPER/SIM mode is rejected.
- Non-positive or non-finite thresholds are rejected.
- LIVE cannot be looser than PAPER.
- PAPER cannot be looser than SIM.
- LIVE/PAPER cannot disable websocket or symbol truth requirements.
- Invalid config blocks decisions.

## Hermes Review

### Contract clarity

`FeedPolicyConfigAudit` is a read-only evidence contract and emits `is_order_action=false`.

### Safety boundary

`classify_feed_with_policy(...)` accepts optional `policy_config`. If validation fails, it returns `feed_ok=false` with `feed_policy_config_invalid` and does not classify the supplied payload as healthy.

## GSD Review

### Minimality

The PR only hardens config validation inside the existing feed-policy seam. It does not wire runtime callers or modify transport behavior.

### Determinism

Validation is deterministic and pure over supplied config values.

## QA / Safety Review

Tests assert:

- Default policy config is valid.
- Valid custom policy config is accepted.
- Missing mode fails validation.
- Invalid thresholds fail validation.
- Unsafe threshold ordering fails validation.
- Missing required LIVE/PAPER truth gates fail validation.
- Decision-level invalid config fails closed.
- Audit serialization includes non-action evidence.

## Scope Guard

Confirmed not touched:

- Feed lifecycle.
- Reconnect/resubscribe behavior.
- Token resolution.
- Ranking behavior.
- Strategy code.
- Dashboard UI.
- Broker/order execution paths.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_pr_feed_16_feed_config_hardening.py tests/test_pr_feed_15_live_paper_feed_policy.py
```

Expected:

- config hardening tests pass.
- previous feed policy tests remain green.
- invalid config fails closed.

## What This PR Does Not Prove

- It does not prove websocket recovery.
- It does not prove runtime feed evidence bundling.
- It does not wire config into runtime yet.
- It does not prove strategy edge or profitability.

## Human Approval

Proceed only if CI is green and the PR remains limited to read-only feed config hardening.
