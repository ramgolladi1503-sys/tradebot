# BUG-PR987-RBFN-CANDIDATE-TELEMETRY-SHADOW-INTEGRITY

## Identity

- Work Item ID: BUG-PR987-RBFN-CANDIDATE-TELEMETRY-SHADOW-INTEGRITY
- Type: BUG
- Parent Epic: EPIC-SENTINEL-REGIME-SUPERVISORY
- Parent Feature: FEAT-SENTINEL-STRUCTURAL-GATES-002
- Title: Add non-authoritative Mode 5 candidate lifecycle summaries and fail closed on unit-ambiguous legacy shadow outcomes
- Current State: PRODUCT_ACCEPTED
- Priority: HIGH

## Business Goal

Make Mode 5 candidate evaluation, quote qualification, veto, and terminal disposition traceable by stable identifiers, while preventing shadow reports from assigning option PnL or INR labels to inputs whose units are not declared.

## Current Behavior

- Existing Mode 5 traces cover selected decision and quote-suppression paths; they do not provide a bounded, joined summary for every completed-bar evaluation and candidate lifecycle.
- Trace persistence uses a bounded asynchronous writer, but records can be dropped when it is unavailable or full.
- Legacy veto records carry spot and option prices plus target/stop points without unit provenance. The shadow evaluator applies those values in both spot and option spaces and emits simulated PnL/capital-saved/missed-alpha labels.

## Expected Behavior

- Emit immutable, bounded Mode 5 evaluation and candidate lifecycle summaries through the existing trace writer. Evaluation IDs bind run, India session date, index, and 5-minute epoch. Candidate IDs bind run, session, index, and generation.
- A missing setup is represented as `NO_SIGNAL` / `NOT_EMITTED`; telemetry does not invent a strategy reason.
- Candidate trace drops mark telemetry incomplete/degraded and never alter qualification, veto, strike selection, dispatch, or order state.
- Unit-ambiguous legacy shadow outcomes remain `UNKNOWN` / `UNAVAILABLE`; they receive no PnL, capital-saved, missed-alpha, or neutral-outcome classification. Existing serialized field names remain available for legacy readers.

## In Scope

- Add bounded, non-authoritative evaluation and candidate lifecycle telemetry to the existing Mode 5 trace path.
- Include stable candidate identity across quote and terminal lifecycle records.
- Ensure stale, out-of-order, future, missing, and invalid quote events do not produce falsely authorized candidate-lifecycle claims.
- Fail closed on untyped legacy shadow inputs and prevent unavailable rows from entering outcome/PnL summary aggregates.
- Add focused tests for queue/schema failure isolation, bounded state, candidate lifecycle, shadow unavailability, and legacy record compatibility.

## Out of Scope

- Any change to strategy setup rules, levels, thresholds, displacement, veto semantics, strike selection, risk sizing, APM, dispatch, broker behavior, credentials, dashboard, or live configuration.
- Any assertion of strategy performance, missed alpha, saved capital, execution quality, or live readiness.
- New telemetry persistence systems, new configuration keys, CI changes, deployment, or live-process actions.

## Operational Limitations and Separate Findings

- The JSONL trace is append-only. Disk budget, headroom monitoring, and retention/rotation are an operational gate and require separate scoped work; this patch does not prune or rewrite trace files.
- Veto and shadow availability counters are process-lifetime aggregates. Daily CLI reconstruction from persisted records remains open, so these in-memory summary counters must not be presented as a reconstructed daily truth.
- A possible dispatch-after-local-APM-rejection path was identified where an accepted dispatcher reservation may still be dispatched after `arm_and_enter` returns false. It is intentionally unchanged here because correcting it changes high-risk execution behavior and requires separate human approval.
- `APM_ENTRY_RECORDED` means the local APM accepted/recorded its state only. It is not evidence of broker submission, exchange acceptance, or a fill.

## Dependencies

- Existing `Mode5TraceQueueItem`, bounded Mode 5 trace queue/writer, and trace health snapshot.
- Existing Product Owner scope acceptance and Hermes DESIGN_READY contract for this bounded behavior-neutral observability task.

## Requirement Traceability

| Requirement ID | Requirement | Source | Acceptance criterion |
|---|---|---|---|
| RBFN-OBS-1 | Every valid completed-bar evaluation is explainable, including no-signal outcomes. | User request / Hermes contract | Summary has stable evaluation ID and explicit `NO_SIGNAL` / `NOT_EMITTED` when no candidate exists. |
| RBFN-OBS-2 | Candidate lifecycle can be joined across quotes and terminal states. | Hermes contract | Tests assert one candidate ID across issued, quote suppression, reservation stage, and local APM terminal; lifecycle slots remain fixed at three supported indexes after 100 generation updates. |
| RBFN-OBS-3 | Telemetry failure cannot authorize or suppress a candidate. | TradeBot safety rules | Tests show queue, serialization, and writer failures do not change candidate or dispatch outputs. |
| RBFN-SHADOW-1 | Ambiguous point units cannot be labeled as PnL or capital saved/missed. | Hermes contract | Legacy shadow rows are `UNAVAILABLE`; daily summaries exclude them from TP/FP/neutral and PnL aggregates. |

## Safety / Risk Constraints

- Broker/order impact: None; no broker call or order action.
- LIVE/PAPER/SIM impact: No execution-mode change; telemetry is non-authoritative.
- Risk-gate impact: None; no gate condition or threshold changes.
- Feed-freshness impact: None; existing quote validation remains authoritative.
- Data/evidence impact: Explicitly mark shadow outcome unavailability and trace-health degradation; never infer a trade or outcome from missing telemetry.
- Required human approval: Scoped implementation authorization received through coordinator after the user accepted the bounded follow-up.

## Architecture Impact

- Components touched: `core/sentinel_live_stream_advisor.py`, `core/sentinel_realtime_journal.py`.
- Interfaces/contracts affected: Additive JSONL event fields and explicit unavailable shadow classification; preserve legacy serialized field names.
- Existing infrastructure reused: Existing bounded Mode 5 trace queue/writer and health reporting.
- New infrastructure required: None.
- High-risk paths touched: Advisor source contains signal/dispatch code, but approved edits are restricted to telemetry snapshots and must not change decision outputs.

## Acceptance Criteria

- [x] Bar evaluation summaries distinguish candidate emitted, abstained, no signal, and rejected/invalid events without inventing a setup reason.
- [x] Evaluation and candidate IDs remain stable across all telemetry records for their lifecycle; per-index lifecycle memory is bounded.
- [x] Queue/schema/writer failure marks telemetry incomplete and has no candidate/dispatch effect.
- [x] Stale, out-of-order, missing, invalid, and future option events are not represented as valid candidate authorization.
- [x] Legacy unit-ambiguous shadow outcomes use unavailable status and no outcome/PnL/capital-saved/missed-alpha classification.
- [x] Existing legacy journal rows remain readable; new fields are additive.
- [x] Focused tests pass and `git diff --check` is clean; CI is not run under the current instruction.

## Development Plan

- Allowed paths: `core/sentinel_live_stream_advisor.py`; `core/sentinel_realtime_journal.py`; `tests/unit/test_sentinel_optionmate_execution_hardening.py`; `tests/unit/test_sentinel_realtime_journal.py`; this work-item file.
- Forbidden paths: All other files; strategy levels/thresholds, risk/veto semantics, strike selection, APM, dispatcher/broker/order configuration, credentials, dashboard, live action, CI.
- Expected implementation: Reuse bounded trace queue; record immutable summaries after advisor state locks; add typed candidate lifecycle status; mark ambiguous shadow data unavailable and exclude from summary aggregates.
- Required developer tests: Focused tests for every evaluation outcome, stable identity, terminal transitions, telemetry failure isolation, state bounds, invalid quote handling, shadow unavailability, and legacy record parsing.

## QA Attack Plan

- Verify no-signal and abstention are not conflated or assigned fabricated reasons.
- Force trace queue full, writer unavailable, serialization error, and stale/out-of-order/future quotes; compare candidate and dispatch outcomes.
- Verify candidate replacement, expiration, invalidation, and consumption emit at most one typed terminal status per generation.
- Terminal de-duplication includes `DISPATCH_UNKNOWN` and legacy `ENTRY_SUCCEEDED`; later invalidation cannot emit a second terminal record for the same candidate.
- If local `arm_and_enter` raises, emit `APM_ENTRY_UNKNOWN`, flush staged lifecycle snapshots after releasing advisor state, and re-raise the same exception; do not create an execution record or alter dispatcher behavior.
- Production entry tests confirm stale, future, zero/missing source or ingress clocks, zero/missing sequence values, and out-of-order quotes cannot reserve or dispatch and leave the valid candidate available.
- Reading an expired candidate flushes its `EXPIRED` terminal record immediately after lock release.
- Verify unavailable shadow records do not affect TP/FP/neutral counts or INR aggregates.
- Verify pre-existing JSONL records lacking additive fields remain readable.

## UAT Criteria

- A reviewer can follow one completed-bar evaluation through candidate quote/veto or terminal disposition by stable IDs; absence of a candidate is explicit.
- The daily forensic summary does not call ambiguous legacy shadow inputs saved capital or missed alpha.

## Release Gates

- [x] Requirements traceable
- [x] Architecture approved
- [x] DEV_VERIFIED
- [x] QA_PASSED
- [x] SENIOR_QA passed
- [x] UAT passed
- [x] PRODUCT_ACCEPTED
- [ ] CI_GREEN (not run; explicitly outside this task instruction)
- [x] rollback/limitations documented

## Rollback Plan

Revert the scoped commit. JSONL readers should ignore additive event types/fields; existing record fields remain. Rollback restores prior shadow labels, so do not use those labels as reliable PnL or capital estimates.

## Evidence

- Tests: `python3 -m py_compile core/sentinel_live_stream_advisor.py tests/unit/test_sentinel_optionmate_execution_hardening.py` passed; `python3 -m pytest -q tests/unit/test_sentinel_optionmate_execution_hardening.py` passed (123 tests, including lifecycle-chain identity, bounded slots, malformed quote non-authorization, immediate expiry flush, dispatch-unknown de-duplication, and APM-exception telemetry); `git diff --check` passed. CI not run.
- Logs/reports: Existing PR #987 Mode 5 trace queue health only; new capture completeness remains limited by its bounded queue and writer health.
- Agent review evidence: BA requirements, Product Owner ACCEPTED, Grill Me risk review, Hermes DESIGN_READY and post-development answers, GSD implementation, QA PASS, Senior QA PASS, Technical & Quant ACCEPTED AS A LIMITATION, and UAT PASS recorded by the coordinator.
- PR: PR #987; update only after separate QA and acceptance gates.

## Claim-level Evidence Standard

This work changes evidence integrity and observability only. It does not certify that every market setup is captured, that any veto was incorrect, or that any trade would be profitable.
