# Causal Pass Invalidation

## Status
`PREVIOUS_CAUSAL_PASS_INVALIDATED`

## Commit
The invalid PASS was claimed in commit: `6e9ac6382648a2c867afd8300d97ff1a8b2c0130`

## Reason Codes
1. `FABRICATED_UNKNOWN_SESSION_IDENTITIES`: The previous session reconciliation explicitly inserted placeholder dates (e.g., `UNKNOWN_PHASE0_DATE_1`) with `UNKNOWN` fields to force the count to equal 500, rather than strictly identifying actual historical sessions.
2. `MINIMUM_HISTORY_CONTRADICTION`: The strategy explicitly requires a minimum of 60 prior sessions of eligible history to calculate a threshold. The previous evidence reported 0 insufficient history counts, which is mathematically impossible for the first 60 sessions.
3. `TERMINAL_COUNT_RECONCILIATION_FAILURE`: The listed terminal categories summed to 302, but the denominator was claimed as 396 (and unexplained count 0). The terminal counts must perfectly sum to the total development sessions.
4. `PYTEST_EVIDENCE_PLACEHOLDER_CONTENT`: `strategy_test_coverage.md` contained literal shell syntax (`$(cat pytest_all.txt)`) rather than actual pytest output due to improper shell string quoting during evidence generation.
5. `NON_REPRODUCIBLE_EVIDENCE_GENERATORS`: The Python scripts used to calculate determinism, partition hashes, and reconciliation were deleted from the worktree before commit, leaving the evidence unverifiable and non-reproducible.

## Resolution
The evidence is being rebuilt from first principles strictly using dated sessions, correctly implemented constraints, and durable reproducible tools. Prior evidence artifacts will be retained in source control history but are explicitly superseded.
