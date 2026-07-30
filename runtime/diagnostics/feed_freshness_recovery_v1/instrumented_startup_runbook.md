# Instrumented Startup Runbook

This runbook does not authorize or perform a restart. PID 70918 remains untouched until an operator verifies every gate.

## Preconditions

Confirm no broker position is managed by PID 70918, no approval is pending, no order request is in progress, Kite authentication is valid, and the rollback command is ready.

## Capture terminal

Start this before the controlled restart. Replace `NEW_PID` after the replacement process starts if its identity is already known; omit `--pid` otherwise.

```bash
cd /Users/madhuram/tradebot-feed-freshness-recovery-v1
python scripts/capture_feed_subscription_startup.py \
  --repo /Users/madhuram/tradebot-feed-freshness-recovery-v1 \
  --watchdog-log /Users/madhuram/tradebot-feed-freshness-recovery-v1/.runtime/logs/depth_ws_watchdog.log \
  --duration-sec 120 \
  --confirm-no-open-position \
  --confirm-no-pending-approval \
  --confirm-no-order-in-progress \
  --confirm-kite-auth-valid \
  --confirm-rollback-ready
```

The collector writes `runtime/diagnostics/feed_subscription_startup_<timestamp>/`, hashes every artifact, removes credential fields, writes `SEALED`, and makes the bundle read-only.

## Operator-controlled restart

Use the repository's existing approved stop/start procedure only after all preconditions pass. Do not use `kill -9`. Record the old and new PID in the incident log. No command in this document places or modifies an order.

## Checks

Require one current `FEED_SOCKET_GENERATION_STARTED`, current-generation connect callbacks, explicit subscribe and `MODE_FULL` requested/applied events, a registry snapshot, and token-level tick/depth evidence. Absence of an event is `UNKNOWN_WITH_EXACT_MISSING_EVIDENCE`, never success.

## Rollback

```bash
cd /Users/madhuram/tradebot-feed-freshness-recovery-v1
git revert --no-edit d2d4425dc9810d61349c6553cdade0c3e873a1cd..HEAD
```

Review the generated revert before restarting. Rollback also requires the same position, approval, order, authentication, and evidence gates.
