---
mode: QA_FINDING
candidate_id: QA-AUTH-001
decision: BLOCK_CERTIFICATION
reason: UNVERIFIED_NETWORK_STATE_CAN_EXIT_AUTH_CHECK_SUCCESSFULLY
timestamp: 2026-07-30T19:55:00Z
is_order_action: false
broker_api_called: false
source: static_consumer_audit_and_behavior_contract
---

# QA-AUTH-001 — Unknown network state can be reported as authenticated

## Severity

`P0 / certification blocker`

## Affected contract

Authentication must be positively verified before live or paper startup can proceed. Missing, expired, invalid, unreachable, or ambiguous authentication evidence must not produce a successful readiness exit.

## Confirmed behavior

`core.auth_manager.validate_token()` currently returns:

```text
ok = true
auth_state = UNKNOWN_NETWORK
```

when the broker profile request fails with a network-classified exception.

`scripts/check_kite_auth.py` reads only `payload["ok"]`. When the value is true, it prints `OK` and returns process exit code `0`; it does not require `auth_state == "OK"` or a non-empty verified `user_id`.

`run_live.sh` invokes this command as a startup guard. A false-success exit can therefore allow startup to continue while broker authentication remains unverified.

## Two concrete failure scenarios

1. The access token expired overnight and the profile endpoint also times out. The check returns `UNKNOWN_NETWORK`, but the script exits successfully and live startup continues.
2. DNS or routing fails before profile verification. The token may be valid or invalid; the system has no proof either way, yet the current boolean contract represents success.

## Required fix

- `validate_token()` must return `ok=false` for `UNKNOWN_NETWORK`.
- `scripts/check_kite_auth.py` must require all of:
  - `ok is true`;
  - `auth_state == "OK"`;
  - non-empty verified `user_id`.
- Ambiguous network state must use a distinct non-zero exit code and operator message.
- Startup callers must not infer authenticated readiness from token presence alone.

## Required tests

- network timeout cannot return success from `validate_token()`;
- network timeout cannot produce `OK` output or exit code `0` from `check_kite_auth.py`;
- verified profile produces exit code `0`;
- `ok=true` with any non-OK state is rejected defensively;
- `auth_state=OK` without `user_id` is rejected defensively;
- lock release remains guaranteed for every return path.

## Non-claims

This finding does not claim the token is invalid during a network outage. It claims the opposite: validity is unknown, so successful authentication cannot be asserted.
