# PR987 Round 2 Controlled Remediation — Final Verdict

## Verdict: HOLD_VERIFIED_BLOCKERS

The scoped P0/P1 behavior changes passed the required targeted regression batch. The verdict remains HOLD because there is no authoritative fill/position source for confirming partial fills, no cross-process APM WAL writer lock, and no in-scope operator reconciliation path to clear `RECOVERY_BLOCKED` positions. No merge or release readiness is claimed.

## Identity and final evidence

- Worktree: `/Volumes/TradeBotFast/worktrees/pr987-egm-remediation`
- Branch: `ram/pr987-egm-remediation`
- HEAD remains `94ab77b554d7540adee68746d8b5016e92ff7d34`.
- Source and tests are dirty and uncommitted; no new commit SHA exists.
- Final regression command and output are in `PR987_R2_RED_GREEN_REPRODUCTIONS.md`: `274 passed in 17.57s`, no failures, no skips.
- The original seven reported suites are all included, plus the focused controlled-remediation module and the requested existing OR-history test.
- `git diff --check` passed for scoped tracked source/test paths.

## Changed paths and final SHA-256

| Path | Final status | SHA-256 |
|---|---|---|
| `core/active_position_manager.py` | modified | `5339b473754da954569a3ec52d1ef9a4f69134f2a2855bc0a95c654233a4a6bf` |
| `core/sentinel_live_stream_advisor.py` | modified | `1c66ba31964fc5401572a7ec4ff28294d7cd7c46fa5a2ab992f2f6adc5ae3aaa` |
| `tests/unit/test_apm_runner_trailing_regression.py` | untracked/new in target | `04623fb3620d83bfa79497da2b1acc509ee2be970023608ae8e233d5cd6a567b` |
| `tests/unit/test_sentinel_optionmate_rbfn_auction.py` | modified | `633f3f9f0b4071cb1933c5b770dbdc7f2ff81f6efdf50eb5bddf79cb8741a245` |
| `tests/unit/test_pr987_r2_controlled_remediation.py` | untracked/new | `57685a6c973c93022d1fe4d539d2343d27d3467af1a71ea1857b1554b7326110` |
| `tests/unit/test_sentinel_advisor_hardening_003.py` | modified | `7227f2961acd1b0162b20f2b75a19caa0c958fa0e7203e7141b1f3f269e9b712` |
| `tests/unit/test_sentinel_rbfn_scenarios_s2_s4_s7.py` | modified fixtures only | `47cd858a6db1a3a197b500f4b84c02bc32f67b7db6036897f7a5f3bb9facb977` |
| `tests/unit/test_sentinel_optionmate_execution_hardening.py` | modified fixtures only | `a9e78d982999c06c8b7bd1e51e29aac52f58839bd3b979477b653fd2e762294b` |

Tracked diff summary: 6 tracked files, 415 insertions, 119 deletions. The two new test modules are untracked, so they are not included in that tracked diff statistic. Scoped status lists only the eight paths above plus this controlled evidence directory. The initial repository status scan timed out as recorded in the preflight manifest; the global untracked inventory is therefore not certified complete.

## What changed

- A bounded capacity-one OR reconciliation worker now performs network and ledger work outside the streaming lock. Spot-update and five-minute close paths enqueue immutable request context. Session generations, request identity, freshness, and shutdown are checked before applying responses. Same-session duplicates are suppressed and retry caps remain bounded.
- Replay rejects automated/live flags before dispatcher construction and never calls either injected or default transport.
- Test/replay seeding always carries synthetic provenance. Live eligibility requires a trusted marker established only by validated candle ingestion or restored durable proof.
- APM target touch now marks an advisory runner milestone and preserves trailing mechanics without inventing fills, remaining quantities, tranche prices, or realized tranche PnL. Legacy `half_booked` payloads migrate to this advisory state.
- APM WAL writers serialize within one manager instance; forced durability failures are surfaced. Corrupt, active, inconsistent, and interrupted recovery enters `RECOVERY_BLOCKED` and rejects new entry.
- Raw observed bars and strategy-eligible bars are separate. Only OR/ground-truth-qualified observations feed patterns and range calculations. Market-path fixture prices and expected setup assertions were preserved while the fixture list was corrected.

## Residual blockers and limits

1. **No fill source:** no scoped read-only broker fill or position reconciliation source was found. `remaining_lots` and `remaining_quantity` stay unknown; actual partial-fill behavior cannot be verified and is `NOT_APPLICABLE` here. Do not infer realized PnL from price marks.
2. **Cross-process WAL:** APM write serialization is in-process only. Multiple processes writing one APM WAL are unsupported and unverified. No exactly-once claim is made.
3. **Recovery operations:** `RECOVERY_BLOCKED` correctly rejects entry, but an operator-controlled position-reconciliation/re-arm workflow is outside scope. An uncertain position may remain blocked until separately reconciled.
4. **Deployment readiness:** all work remains uncommitted in the isolated worktree. No PR update, push, merge, deployment, broker call, live process change, or production verification occurred.

## Not changed

No strategy equations, TD/RP levels, thresholds, setup geometry, broker adapters, credentials, order code, risk gates, live flags, or production processes were changed. No fills, exchange actions, or market-edge claims were fabricated.

## Supersession note — latest APM WAL leg identity follow-on

The [terminal WAL recovery addendum](PR987_R2_TERMINAL_WAL_RECOVERY_ADDENDUM.md) is the authoritative latest source identity for the scoped APM follow-on. Latest hashes: `core/active_position_manager.py` `93bc703c83b2662a944e9dac751a1223f73cbdb954d28ba736ecdefe7cc13c5a`; `tests/unit/test_apm_runner_trailing_regression.py` `ed1c4b800a4f3cdbecbcbb815f46a6335d39672b2f9d80777154a94279d4f918`.

The focused `21 passed` result was run by the implementer and is not independent QA. The previously reported 274-test suite predates this latest follow-on. Overall verdict remains **HOLD_VERIFIED_BLOCKERS**: no fill source, cross-process WAL writers remain unsupported, and operator re-arm remains unavailable.
