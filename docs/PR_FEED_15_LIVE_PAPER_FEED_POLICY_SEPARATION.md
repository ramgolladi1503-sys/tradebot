# PR-FEED-15 — Live/Paper Feed Policy Separation

## Purpose

PR-FEED-15 separates feed-health policy by runtime mode.

Before this PR, canonical feed truth had one threshold set for all callers. That is unsafe because LIVE, PAPER, and SIM do not have the same tolerance:

- LIVE must be strict and fail closed quickly.
- PAPER may observe slightly more latency but must still block clearly stale feed.
- SIM/BACKTEST may use wider observation thresholds without pretending to be live feed truth.
- Invalid/unknown mode must fail closed.

## Scope

In scope:

- Add `core/feed_policy.py`.
- Add explicit policy thresholds for LIVE, PAPER, and SIM.
- Add a read-only `FeedPolicyDecision` evidence contract.
- Delegate actual health classification to existing canonical `classify_feed_health_truth(...)`.
- Add tests proving LIVE/PAPER/SIM separation and invalid-mode fail-closed behavior.

Out of scope:

- No websocket lifecycle changes.
- No reconnect logic.
- No resubscribe logic.
- No token resolver changes.
- No ranking changes.
- No strategy changes.
- No dashboard UI changes.
- No broker calls.
- No order creation.

## Policy contract

### LIVE_STRICT

- `max_option_tick_age_sec=2.0`
- `max_ltp_age_sec=2.0`
- `max_depth_age_sec=4.0`
- websocket truth required
- symbol truth required

### PAPER_OBSERVATION

- `max_option_tick_age_sec=5.0`
- `max_ltp_age_sec=5.0`
- `max_depth_age_sec=10.0`
- websocket truth required
- symbol truth required

### SIM_OBSERVATION

- `max_option_tick_age_sec=60.0`
- `max_ltp_age_sec=60.0`
- `max_depth_age_sec=120.0`
- websocket truth not required
- symbol truth not required

### INVALID_MODE_FAIL_CLOSED

Unknown mode returns:

- `feed_ok=false`
- `reason_code=invalid_feed_policy_mode`
- `blockers=[feed_policy_invalid_mode]`
- `is_order_action=false`

## Acceptance proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_pr_feed_15_live_paper_feed_policy.py
```

Required proof:

- Same feed age can pass PAPER but fail LIVE.
- PAPER still blocks clearly stale feed.
- Invalid mode fails closed and remains non-action.
- LIVE requires explicit websocket truth.
- SIM can observe without websocket requirement.
- Policy decision JSON includes `is_order_action=false`.

## Runtime proof required after merge

When this is later wired into runtime callers, capture evidence showing:

- LIVE uses `LIVE_STRICT`.
- PAPER uses `PAPER_OBSERVATION`.
- SIM/BACKTEST uses `SIM_OBSERVATION`.
- Unknown mode cannot silently fall back to PAPER or SIM.

## Next PR

After this PR is merged and CI is green, continue only to PR-FEED-16 — Feed Config Hardening.
