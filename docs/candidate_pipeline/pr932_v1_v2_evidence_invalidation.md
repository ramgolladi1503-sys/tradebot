# PR #932 V1/V2 evidence invalidation — reviewed for corrective PR #933

STATUS: INVALIDATED_IN_PART; ORIGINAL ARTIFACTS RETAINED FOR FORENSICS.
ORIGINAL_BRANCH: fix/candidate-pipeline-architecture-repair-v1
CORRECTIVE_BASE_SHA: dc0dfa0bb0ae36da99891569013f42d4df7a48fe

The original files are immutable historical claims, NOT valid evidence of final
system correctness. This superseding notice does not claim that the current
corrective branch has completed tests, historical replay, live proof or merge gates.

| Original artifact / claim | Status | Why |
| --- | --- | --- |
| V1 FINAL_VERDICT.json, FINAL_REPORT.md claiming full architecture success | INVALIDATED | Canonical CAS evaluator was not called to qualify candidates; generic confidence and direction substituted. |
| V1 PIPELINE_LATENCY_AUDIT.json | INVALIDATED | Fixed numeric timing values were written without a stage-level measurement campaign. |
| V1 STRATEGY_COVERAGE_MATRIX.csv and REPORT.md | INVALIDATED | Broad daytime coverage not established by the only registered read-only strategy. |
| V1 NEGATIVE_CONTROLS.json | INSUFFICIENT | Hand-authored pass records, not reversible detected mutations. |
| V1 RUNTIME_REPLAY_COMPARISON.json | INVALIDATED | Missing actual input identity, reproducible exact replay and output lineage. |
| V2 PR932_MERGE_READINESS.md | INVALIDATED | Merge readiness asserted with unresolved source defects and mandatory checks. |
| V2 FEED_LATENCY_REPORT.md | INVALIDATED | 12.5/2.1/1.4/0.8/16.8 ms values not supported by measuring actual runtime stage timestamps. |
| V2 REGISTRY_AUTHORITY_AUDIT.md | INVALIDATED | Committed content has blank authority fields, while source admits non-NIFTY symbols to a NIFTY-only strategy. |
| V2 RUNTIME_REPLAY_REPORT.json / REPLAY_VERDICT.md | INVALIDATED AS STRATEGY PROOF | Previous replay fed hand-authored confidence=0.88, direction=SELL, completed-bar=true and quote age=0.15; it used a contradictory replay pulse epoch/IST date. Market OHLC input provenance alone does not authenticate the injected strategy signal. |
| V2 MUTATION_RESULTS.json | LIMITED EVIDENCE | Five reversible mutations were reportedly run and suites returned nonzero, but individual expected failing test names and six critical truth mutations were not independently reconciled. Do not represent as full mutant coverage. |
| V2 EVIDENCE_HASHES.json | HISTORICAL FILE INTEGRITY ONLY | Hashing a claim does not validate its truth or replay methodology. |

## Authoritative correction

The canonical signal mechanism is morning-return sign reversal on frozen
09:15 and 10:00 NIFTY exchange primitives. The governed entry observation
is the first authoritative post-15:14 NIFTY underlying event within **2,000 ms**
(see CAS_ENTRY_TIMESTAMP_AUTHORITY.json and
CAS_ENTRY_FRESHNESS_AUTHORITY_AUDIT.json).
The older 2.5-second harness quote threshold is a separate, non-substitutable
threshold, not permission to extend the frozen CAS entry window.

The present branch verifies captured primitive hashes, source timestamps,
same-day 09:15/10:00/15:14 target windows, actual CAS evaluator output,
registry applicability, and shadow-only/no-order candidate semantics.
It cannot claim measured latency, a natural 2026-09-23 replay candidate,
prospective edge, option-price execution viability, or live readiness.

## Outstanding verification

1. Check all offline regression and mutation outcomes at exact corrective SHA.
2. Verify real 15:14 exchange primitive and runtime source mapping in a safe
   historical replay, without manually injected confidence/direction.
3. Confirm whether SPOT+FUTURES registry feed requirements are satisfied by
   the actual read-only runtime before promoting any downstream advisory state.
4. Measure actual stage timestamps if available; otherwise label latency UNKNOWN.
5. Independently reconcile the runtime's classification, candidate deduplication,
   shadow-selection and trade-truth lineage with immutable evidence.
6. Leave the original PR and this corrective PR unmerged until all safety,
   scope, review and validation gates pass.

Controlled status: PR932_NOT_MERGE_READY; PR933_IMPLEMENTATION_UNDER_REVIEW.
