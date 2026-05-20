# PR103 — Runtime Truth Consistency + Regime Diagnostics

## Scope

This PR adds runtime truth diagnostics for candidate traces and adds explicit regime-unstable diagnostic evidence.

## Why

Live validation showed the engine can be feed-connected and still repeatedly emit `REGIME_UNSTABLE`. That is not automatically a bug, but the runtime was too vague. It did not show enough threshold context to prove whether the block came from probability, entropy, debounce, stale feed, or strategy gate interaction.

## Changes

- Candidate trace payload now includes runtime truth fields:
  - `visibility_bucket`
  - `reportable_executable`
  - `synthetic_candidate`
  - `runtime_truth_consistent`
  - `runtime_truth_reasons`
  - `executable_signals`

- Regime unstable gate blocks now emit `REGIME_UNSTABLE_DIAGNOSTIC` with:
  - symbol
  - execution mode
  - regime probability max
  - configured probability threshold
  - entropy
  - configured entropy threshold
  - unstable reasons
  - debounce streak and block-after values
  - feed and quote health snapshots

## Out of scope

- No broker calls
- No live order placement
- No order routing changes
- No strategy rewrite
- No relaxation of regime gates
- No dashboard change

## Grill Me Review

PASS with one condition: this PR must not loosen `REGIME_UNSTABLE`. It only explains it. A vague block reason in live mode is operationally weak because the operator cannot know whether to fix feed, thresholds, regime model, or strategy data.

## Hermes Review

PASS. This is read-only diagnostic enrichment. It does not mutate execution decisions, broker state, order payloads, or live/paper boundaries.

## GSD Review

PASS. This is a narrow observability PR tied to a real live-run confusion point. It improves evidence quality without adding fake strategy confidence.
