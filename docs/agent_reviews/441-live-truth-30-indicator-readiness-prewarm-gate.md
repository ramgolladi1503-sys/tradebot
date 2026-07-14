# Agent Review Evidence — Issue #441 (LIVE-TRUTH-30)

mode: LIVE
candidate_id: issue-441
decision: block_executable_when_indicators_missing
reason: INDICATORS_UNREADY
timestamp: 2026-05-29
is_order_action: false
broker_api_called: false
source: agent_review_evidence_v1

## Agent Work Contract
- source_agent: Codex (GPT-5.2)
- action: GENERATE_PATCH + GENERATE_TESTS
- title: LIVE-TRUTH-30 — Indicator Readiness Prewarm Gate
- scope: Gate executable candidate generation when required indicators are unavailable; keep feed blockers as primary when feed is stale/dead.
- requested_paths:
  - core/decision_dag.py
  - tests/test_live_indicator_readiness.py
  - docs/agent_reviews/441-live-truth-30-indicator-readiness-prewarm-gate.md
- allowed_paths:
  - core/decision_dag.py
  - core/live_indicator_readiness.py (read-only)
  - tests/test_live_indicator_readiness.py
  - docs/agent_reviews/*
- forbidden_paths:
  - core/broker*, core/order*, core/execution*, credentials.py, config/*
  - any `.env` / secrets / live runtime scripts
- expected_tests:
  - PYTHONPATH=. python -m pytest -q tests/test_live_indicator_readiness.py
  - python -m py_compile core/decision_dag.py
- acceptance_proof:
  - Deterministic tests prove `INDICATORS_MISSING` blocks executability and that feed-stale remains primary when feed is dead.

## Scope Guard
- No ranking/scoring weight changes.
- No broker calls and no order behavior changes.
- No UI/dashboard work.
- Changes are limited to strict indicator readiness evaluation inside the decision DAG warmup gate and deterministic tests.

## Grill Me Review
- Risk: Over-blocking due to missing indicator values in runtime payload.
  - Mitigation: Gate is restricted to required indicators; failure to compute readiness fails closed (explicit `INDICATORS_MISSING`).
- Risk: Changing decision DAG outputs could affect candidate counts.
  - Mitigation: Only affects executability truth when indicator values are missing/stale; feed gate precedence remains earlier in DAG ordering.

## Hermes Review
- Canonical rule: executable candidates require required indicators present + fresh enough (vwap/rsi/ema/atr and indicator last update within `INDICATOR_STALE_SEC`).
- Precedence: feed stale/dead remains primary blocker because it is evaluated earlier in the DAG (`N2_FEED_FRESH` before `N3_WARMUP_DONE`).
- Observability: Missing indicator fields are exposed via `N3_WARMUP_DONE` facts (`indicator_missing_inputs`, `indicator_readiness_blockers`) for per-symbol runtime/debug inspection.

## GSD Review
- Implemented strict readiness check using `core.live_indicator_readiness.build_live_indicator_readiness_report` inside `core/decision_dag.py::_node_warmup_done`.
- Fail-closed behavior: any exception or inability to compute a per-symbol readiness decision produces `INDICATORS_MISSING`.
- Backward compatibility: existing coarse `indicators_ok`/`indicators_age_sec` checks remain as additional fail-closed safeguards.

## QA / Safety Review
- Tests added are deterministic and do not require LIVE mode, broker access, or network calls.
- No changes to broker/execution modules; no new external side effects.

## Acceptance Proof
- `tests/test_live_indicator_readiness.py` covers:
  - feed live + missing indicator => `primary_blocker=INDICATORS_MISSING` and missing fields visible.
  - feed dead + missing indicator => `primary_blocker=FEED_STALE` (feed wins).
  - indicators recover => decision becomes allowed without restart.

## Runtime Proof Required After Merge
- During a live session warmup, validate the runtime/debug explain facts include `indicator_missing_inputs` when blocked:
  - Grep: `grep -R "INDICATORS_MISSING\\|indicator_missing_inputs\\|indicator_readiness" logs .runtime 2>/dev/null | tail -80`
- Confirm the bot does not produce executable candidates until indicators are present and fresh.

## What This PR Does Not Prove
- Does not prove indicator computation correctness (only readiness gating).
- Does not prove strategy profitability or ranking behavior.
- Does not validate broker/execution behavior (explicitly out of scope).

## Human Approval
- Required before enabling LIVE operation.
- Review required if expanding required-indicator set or changing freshness thresholds for executability.


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
