# PR954 Session Analytics Repair Review

## Agent Work Contract
- source_agent: hermes -> gsd
- action: DESIGN_ARCHITECTURE, DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES, PLAN_PR, GENERATE_TESTS, GENERATE_PATCH
- title: Keep session diagnostics out of replay-eligible candidate events
- scope: offline analytics session discovery, candidate ingestion, daily reporting, and outcome replay.
- requested_paths: core/analytics/, scripts/run_daily_intel.sh, tests/analytics/, docs/agent_reviews/.
- allowed_paths: those requested paths.
- forbidden_paths: broker, order, risk, strategy, live runtime, credentials, and unrelated files.
- expected_tests: analytics test suite plus session-selection and candidate-conversion regression tests.
- acceptance_proof: diagnostics remain separately counted and hashed; malformed/invalid discovery fails closed; only validated candidate-journal rows enter intent replay; session outputs are isolated.

## Scope Guard
Session observations and trade-truth records are diagnostics. They cannot create rejected intents or hypothetical outcomes. Session-scoped runs read only that session's candidate journal and write fingerprint-scoped outcomes. Explicit invalid paths are errors.

## Grill Me Review
- Failure mode: converting non-candidates into rejected intents creates fabricated replay outcomes. Addressed by candidate-journal-only replay.
- Failure mode: invalid or unreadable session paths silently produce empty reports. Addressed by explicit errors and propagated discovery failures.
- Remaining limitation: sessions without a candidate journal correctly report zero intent events; this is not evidence that candidate generation was healthy.

## Hermes Review
Contract: read_only=true; is_order_action=false; broker_api_called=false; allowed_for_live_execution=false; append=false for source evidence. Diagnostics may inform report counts but never trade intent or outcome replay. Acceptance requires exact session provenance and zero fabricated events.

### Hermes Follow-up: Empty Runtime Candidate Artifacts
- `source_agent: hermes`; actions: `DESIGN_ARCHITECTURE`, `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`.
- `title`: Represent empty candidate pool and decision files in session diagnostics.
- `scope`: Add `candidate_pool.jsonl`, `candidate_decisions.jsonl`, and `executable_pool.jsonl` to read-only diagnostic inventory so present-empty sources are distinguishable from absent sources.
- `requested_paths` and `allowed_paths`: `core/analytics/store.py`, `tests/analytics/test_session_store_ingestion.py`, and this review document.
- `forbidden_paths`: converting these artifacts into intent/outcome events, replay-source changes, runtime wiring, broker/order/risk/strategy changes, and unrelated files.
- `expected_tests`: present-empty files appear in `source_files` with zero records and deterministic empty-content hash; diagnostic rows remain excluded from `load_session_events` and intent replay; current diagnostics retain existing counts and safety markers.
- `acceptance_proof`: the October 1 session's four run directories each expose candidate pool/decision/executable-pool files with zero rows, without inventing any candidate event.
- Risk boundary: this improves source-presence observability only. It does not establish candidate generation health or infer events from empty files.

## GSD Review
Execution follows the Hermes boundary: add strict candidate validation, separately summarize telemetry diagnostics with per-file SHA-256, scope report/replay inputs and output paths to the selected session, and add regression coverage. The follow-up GSD patch inventories candidate-pool, candidate-decision, and executable-pool files as diagnostics only; none can be converted to trade intents. No live runtime wiring is introduced.

## QA / Safety Review
- Analytics-only changes; no broker imports or order actions.
- Malformed candidate rows are excluded and accounted for.
- File discovery errors are surfaced.
- Tests run after the follow-up: `pytest -q tests/analytics` (74 passed); diff whitespace check passed.
- The selected 2026-10-01 run has 386 strategy observations and 387 trade-truth rows; its candidate event count is zero. The broader four-run inventory totals 13,129 strategy observations and 13,130 trade-truth rows, with zero malformed rows.
- All four October 1 run directories have empty `candidate_pool.jsonl`, `candidate_decisions.jsonl`, and `executable_pool.jsonl`, and no `candidate_journal.jsonl`. The follow-up summary reports 20 present diagnostic files, 26,259 valid rows, zero malformed rows, and zero candidate events. It does not fabricate replay outcomes.

## Acceptance Proof
Candidate conversion requires validated candidate identity, instrument, side, timestamp, and coherent positive entry/target/stop values. Session replay output is isolated by source fingerprint; candidate source changes during replay fail closed. Diagnostics include counts, malformed rows, reason counts, and source hashes.

## Runtime Proof Required After Merge
Run the offline daily-intelligence command against an explicitly selected session directory and verify report source hashes and candidate counts against that session's files. No runtime or live execution validation is implied.

## What This PR Does Not Prove
It does not prove strategy quality, signal health, order eligibility, broker connectivity, live readiness, or candidate presence in sessions that have no candidate journal.

## Human Approval
Human approval is required for merge under repository policy. This change does not authorize order actions, broker access, live mode, or strategy threshold changes.
