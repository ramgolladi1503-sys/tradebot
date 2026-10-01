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

## GSD Review
Execution follows the Hermes boundary: add strict candidate validation, separately summarize telemetry diagnostics with per-file SHA-256, scope report/replay inputs and output paths to the selected session, and add regression coverage. No live runtime wiring is introduced.

## QA / Safety Review
- Analytics-only changes; no broker imports or order actions.
- Malformed candidate rows are excluded and accounted for.
- File discovery errors are surfaced.
- Tests run: `pytest -q tests/analytics` (72 passed); shell syntax and diff whitespace checks passed.
- Actual 2026-10-01 session has 386 strategy observations, 387 trade-truth rows, zero candidate-journal rows, zero malformed rows; resulting candidate event count is zero. The report does not fabricate replay outcomes.

## Acceptance Proof
Candidate conversion requires validated candidate identity, instrument, side, timestamp, and coherent positive entry/target/stop values. Session replay output is isolated by source fingerprint; candidate source changes during replay fail closed. Diagnostics include counts, malformed rows, reason counts, and source hashes.

## Runtime Proof Required After Merge
Run the offline daily-intelligence command against an explicitly selected session directory and verify report source hashes and candidate counts against that session's files. No runtime or live execution validation is implied.

## What This PR Does Not Prove
It does not prove strategy quality, signal health, order eligibility, broker connectivity, live readiness, or candidate presence in sessions that have no candidate journal.

## Human Approval
Human approval is required for merge under repository policy. This change does not authorize order actions, broker access, live mode, or strategy threshold changes.
