# PR-FEED-16 — Feed Config Hardening

## Purpose

PR-FEED-16 hardens feed-policy configuration so unsafe or malformed thresholds cannot be silently trusted.

PR-FEED-15 introduced explicit LIVE/PAPER/SIM feed policy thresholds. PR-FEED-16 adds a read-only validation contract around those thresholds.

## Scope

In scope:

- Validate feed-policy config structure.
- Require LIVE, PAPER, and SIM modes.
- Require positive finite age thresholds.
- Require policy names to match their mode.
- Require LIVE thresholds to be less than or equal to PAPER thresholds.
- Require PAPER thresholds to be less than or equal to SIM thresholds.
- Require LIVE and PAPER to require websocket truth and symbol truth.
- Fail closed when invalid config is supplied to `classify_feed_with_policy(...)`.

Out of scope:

- No websocket lifecycle changes.
- No reconnect logic.
- No resubscribe logic.
- No token resolver changes.
- No dashboard changes.
- No strategy changes.
- No broker calls.
- No order behavior.

## New contract

`validate_feed_policy_config(...)` returns `FeedPolicyConfigAudit`:

- `read_only=true`
- `is_order_action=false`
- `append=false`
- `config_ok=true|false`
- `issues=[]`
- `thresholds=[]`

Invalid config produces:

- `reason_code=feed_policy_config_invalid`
- structured issues with `field`, `reason`, and `value`

## Fail-closed behavior

When invalid config is passed into `classify_feed_with_policy(...)`, the decision returns:

- `feed_ok=false`
- `policy_name=INVALID_MODE_FAIL_CLOSED`
- `reason_code=feed_policy_config_invalid`
- `blockers=[feed_policy_config_invalid]`
- `is_order_action=false`

## Acceptance proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_pr_feed_16_feed_config_hardening.py tests/test_pr_feed_15_live_paper_feed_policy.py
```

Required proof:

- Default config is valid.
- Valid custom config is accepted.
- Missing required mode is rejected.
- Non-positive/non-finite thresholds are rejected.
- LIVE cannot be looser than PAPER.
- PAPER cannot be looser than SIM.
- LIVE/PAPER cannot disable websocket or symbol truth requirements.
- Invalid config makes feed policy decision fail closed.
- Audit JSON includes non-action evidence.

## Risk

This PR keeps existing defaults behavior-compatible. It only adds config validation and optional `policy_config` support. Existing callers that do not pass custom config continue to use validated defaults.

## Next PR

After this PR is merged and CI is green, continue only to PR-FEED-20 — Feed Runtime Evidence Bundle.
