# Agent Review Evidence — Upstox Offline V3 Authority Repair

## Agent Work Contract

Repair only the offline Upstox data-authority path required to validate an already sealed market-data corpus:

- normalized frame-sequence validation;
- IST continuous-market interval classification;
- causal latest-row identity;
- point-in-time future selection;
- deterministic nearest-expiry ATM CE/PE panel selection.

The deliverable is a fail-closed validator/generator pair with focused tests and no trading authority.

## Scope Guard

Allowed paths are limited to:

```text
.github/workflows/upstox_offline_v3_repair.yml
core/upstox_capture/schemas.py
scripts/upstox_capture/generate_offline_datasets_v3.py
scripts/upstox_capture/validate_upstox_capture_v1.py
tests/upstox_capture/test_capture_validation_sequence.py
tests/upstox_capture/test_offline_datasets_v3_session_clock.py
docs/agent_reviews/upstox_offline_v3_time_sequence_repair.md
```

Excluded:

- strategy registration or strategy code;
- candidate-pool, ranking, TradeBuilder or risk behavior;
- broker, order or execution paths;
- live feed configuration or subscriptions;
- dashboard behavior;
- edge or profitability claims.

The pre-cleanup PR head is preserved on `archive/pr796-pre-scope-cleanup-20260806`. The active PR was rebuilt from current `main` with only the seven allowed files.

## Grill Me Review

The retained evidence initially looked valid because hashes and causality checks passed, but those checks were insufficient:

- 6,781 equality-only sequence findings were mislabeled as corruption;
- UTC boundaries were compared with an IST market-open literal;
- post-close intervals could be admitted as live research rows;
- `groupby().last()` could create synthetic column-wise rows;
- future and option contracts were selected by input/key order rather than point-in-time authority;
- the retained option outcomes were LTP-only and could not prove executable fills.

A passing checksum does not repair semantic defects. The old validation report and 75-row V3 output remain superseded until regenerated.

## Hermes Review

The implementation now:

- treats `local_sequence` as a websocket-frame identity shared by multiple instrument rows;
- accepts equal sequence ties across distinct instruments;
- rejects backward regressions;
- requires deterministic handling of exact duplicate event identities;
- rejects conflicting duplicate identities;
- converts UTC boundaries to `Asia/Kolkata` before session classification;
- admits only 09:15–15:30 IST continuous-market intervals;
- preserves the known 07:29–07:31 UTC stale-gap override;
- records UTC and IST boundaries;
- uses stable ordering plus `groupby().tail(1)` to retain actual source rows;
- parses ISO and epoch-millisecond expiries;
- selects the nearest non-expired future independently of instrument-key order;
- selects the nearest non-expired option expiry at each causal boundary;
- selects up to five CE and five PE contracts nearest causal spot;
- records selection policy, expiry, key, rank and moneyness.

## GSD Review

The repair is constrained to deterministic evidence authority. It does not attempt strategy discovery or architecture expansion.

The implementation sequence was:

1. identify the equality-only validator defect;
2. freeze the frame-identity contract;
3. repair and test sequence semantics;
4. identify the UTC/IST and post-close defects;
5. freeze the 09:15–15:30 IST window;
6. replace synthetic latest-row aggregation;
7. freeze point-in-time future and option selection;
8. remove unrelated runtime/strategy changes from the PR;
9. run repository and focused CI;
10. revalidate/regenerate the sealed corpus before any data-admission claim.

## QA / Safety Review

Focused tests cover:

### Sequence identity — 4 tests

1. equal sequence across distinct instruments is valid;
2. backward sequence is rejected;
3. exact duplicate identity requires deterministic dedupe;
4. conflicting duplicate identity is rejected.

### Time, row and contract authority — 10 tests

1. 07:30 UTC is 13:00 IST and is the known stale gap;
2. 07:32 UTC is 13:02 IST and is continuous-market time;
3. 09:15 UTC is 14:45 IST, not Indian market open;
4. 10:01 UTC is 15:31 IST and is excluded;
5. latest-row selection preserves one actual source row;
6. expiry parsing accepts ISO and epoch milliseconds;
7. front future uses nearest valid expiry, not key order;
8. expired futures are excluded;
9. option selection is nearest-expiry, balanced and ATM-centered;
10. selection degrades deterministically when contracts are sparse.

Safety assertions:

```text
NO_ORDER_ACTIONS
NO_EXECUTION_AUTHORITY
NO_STRATEGY_PATH_CHANGED
NO_RISK_PATH_CHANGED
NO_BROKER_PATH_CHANGED
```

The connected Drive manifest proves a sealed corpus of 11,347 files and 667,730,913 bytes. The normalized chunk manifest reconciles 11,250 files and 1,315,840 rows with no missing sealed paths or hash mismatches. The 459,107,210-byte archive exceeds the connector's 100 MB transfer ceiling, so full regeneration must not be claimed until executed in an environment that can materialize the archive.

## Acceptance Proof

Required final-head evidence:

- focused module compilation;
- 14 focused regression tests;
- repository tests and deterministic health gate;
- Code Excellence, Repo Forensics, CodeQL and agent-review gates;
- seven-file scope confirmation;
- mergeability against current `main`;
- real-corpus validator rerun;
- V3 regeneration and checksum/join/contract reconciliation;
- actual bid/ask value coverage audit before executable replay.

## Runtime Proof Required After Merge

This repair has no production runtime behavior. After merge, the required operation is offline only:

1. materialize the sealed August 5 archive;
2. rerun `validate_upstox_capture_v1.py`;
3. regenerate V3 using `generate_offline_datasets_v3.py`;
4. persist hashes, row counts, seam classifications and selected contract identities;
5. compare regenerated output with the superseded archive;
6. keep `DATA_READY_FOR_DORL_ONLY=NO` and `DATA_READY_FOR_PSILOR_PROXY_VALIDATION=NO` unless their separate session-count and authority gates pass.

No broker or live TradeBot process is required.

## What This PR Does Not Prove

This PR does not prove:

- that the full sealed corpus is error-free before rerun;
- that the regenerated dataset has enough sessions;
- that option bid/ask values are sufficiently populated or fresh;
- that an executable ask-entry/bid-exit replay is possible;
- that DORL or PSILOR has structural edge;
- that any strategy is profitable;
- that production trading should be enabled.

## Human Approval

The user explicitly requested that PR #796 be completed first, followed by PR #795, and that both be closed only in that order. This is approval to repair, validate and merge the data-authority changes after their gates pass. It is not approval to alter strategies, risk, broker behavior, place orders or claim an edge.

## Final Review Verdict

```text
PR_SCOPE_NARROWED_TO_SEVEN_DATA_AUTHORITY_FILES
SEQUENCE_VALIDATOR_IMPLEMENTATION=REPAIRED
V3_TIMEZONE_WINDOW_IMPLEMENTATION=REPAIRED
LATEST_ROW_IDENTITY=REPAIRED
POINT_IN_TIME_FUTURE_SELECTION=REPAIRED
BALANCED_ATM_OPTION_SELECTION=REPAIRED
FOCUSED_REGRESSION_TESTS_ADDED=14
OLD_VALIDATION_REPORT=SUPERSEDED
OLD_V3_DATASET=SUPERSEDED
REAL_CORPUS_REVALIDATION=PENDING
REAL_CORPUS_REGENERATION=PENDING
DATA_READY_FOR_DORL_ONLY=NO
DATA_READY_FOR_PSILOR_PROXY_VALIDATION=NO
EDGE_VALIDATION_ALLOWED=NO
MERGE_ALLOWED=ONLY_AFTER_ALL_REQUIRED_CHECKS_PASS
```
