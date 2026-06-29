# Candidate Lineage Ledger Hardening

mode: PAPER
candidate_id: PR_621_CANDIDATE_LINEAGE_LEDGER_HARDENING
decision: APPROVED_OBSERVABILITY_ONLY
reason: Candidate lineage ledger semantics are hardened without changing gates, thresholds, strategies, broker logic, or order logic.
timestamp: 2026-06-29T03:55:00Z
is_order_action: false
broker_api_called: false
source: Codex

## Agent Work Contract

source_agent: Codex
action: GENERATE_PATCH
title: Harden candidate lineage rejection ledger semantics
scope: Observability-only candidate lineage ledger semantics, analyzer, docs, and tests.
requested_paths: core/candidate_lineage_ledger.py, core/orchestrator.py, scripts/analyze_candidate_lineage.py, tests/test_candidate_lineage_ledger.py, docs/observability/candidate_lineage_rejection_ledger.md
allowed_paths: core/candidate_lineage_ledger.py, core/orchestrator.py, scripts/analyze_candidate_lineage.py, tests/test_candidate_lineage_ledger.py, docs/observability/candidate_lineage_rejection_ledger.md, docs/agent_reviews/pr_621_candidate_lineage_ledger_hardening.md
forbidden_paths: broker, order, execution, risk, strategy thresholds, credentials, environment files, live runtime outputs
expected_tests: candidate lineage tests, top opportunity tests, fallback executable firewall tests, stale candidate hygiene tests
acceptance_proof: Targeted tests pass, diff scope is limited, and CI evidence gate has this document.

## Scope Guard

This PR is observability-only. It does not change strategy generation, scoring thresholds, ranking decisions, broker behavior, order behavior, risk gates, feed gates, kill switches, or live mode behavior.

The PR changes the lineage ledger so selected rows are represented as selected rather than blocked. It also makes entry path and selection bucket semantics explicit so funnel metrics do not imply false rejection or false promotion.

## Grill Me Review

The main risk is misleading analytics, not trade execution. A selected row with a block reason would corrupt the funnel and make the system look like it rejected the same candidate it selected. This PR removes that ambiguity.

This does not prove edge. It only makes rejection and selection accounting auditable enough to stop guessing during live or paper evidence review.

## Hermes Review

The field contract is now explicit:

- `block_reason` is reserved for `stage_status="blocked"`.
- `selection_reason` explains why selected rows were selected.
- `ranking_bucket` remains pre-selection eligibility.
- `selection_bucket` marks final top-opportunity selection.
- `entry_path` distinguishes TradeBuilder, Phase 2 direct, existing ranked candidates, augmented soft rejects, and synthetic/debug rows.

This keeps observability separate from decision logic.

## GSD Review

Implemented:

- Ledger row validation invariants.
- Fail-closed executable truth for fallback, recovered fallback, stale quote, advisory, degraded, and `execution_ok=false` rows.
- Analyzer warnings for semantic violations.
- Documentation of blocked, selected, ranking, and entry path semantics.
- Tests covering selected rows, executable invariants, blocked totals, explicit entry paths, and analyzer warnings.

## QA / Safety Review

Local validation:

```bash
git diff --name-only origin/main...HEAD
git diff --check origin/main...HEAD
python -m pytest -q tests/test_candidate_lineage_ledger.py tests/test_top_opportunity_selector.py tests/test_edge58_top_opportunity_executable_truth.py tests/test_edge59_top_opportunity_truth_reader_wiring.py tests/test_edge41_fallback_execution_firewall.py tests/test_live_truth_06_stale_candidate_hygiene.py
```

Result:

```text
58 passed
```

## High-Risk Path Review

`core/orchestrator.py` is high risk because it is a runtime orchestration file. The change is limited to emitting candidate lineage ledger evidence after ranked pipeline evidence is written and before top opportunity snapshots are written.

The orchestrator change does not alter candidate generation, gate evaluation, ranking, execution permission, broker calls, order routing, risk checks, or thresholds. The write path is wrapped in an exception handler and records failure as a warning so lineage emission cannot promote a candidate or open execution.

## Acceptance Proof

Acceptance criteria satisfied:

- Selected rows have `selection_reason="top_opportunity_selected"` and empty `block_reason`.
- Blocked rows carry block reasons and are counted as blocked.
- Selected rows do not increase `blocked_total`.
- Top opportunities require executable and rankable truth in lineage.
- Fallback, recovered fallback, stale quote, advisory, degraded, and `execution_ok=false` rows cannot be executable in lineage.
- Analyzer flags semantic violations and summarizes block reasons.
- Scope is limited to the approved lineage files plus this mandatory evidence file.

## Runtime Proof Required After Merge

After merge, run a live or paper evidence capture and inspect:

- `runtime/candidate_lineage/candidate_funnel_YYYYMMDD.jsonl`
- `runtime/candidate_lineage/candidate_funnel_summary_YYYYMMDD.jsonl`
- `python scripts/analyze_candidate_lineage.py`

The expected runtime proof is not more trades. The expected proof is a reliable explanation of where candidates are generated, blocked, made rankable, made executable, or selected.

## What This PR Does Not Prove

This PR does not prove:

- strategies have edge
- ranking is calibrated
- feed is stable
- top opportunities are profitable
- Phase 2 is too strict or too loose
- entropy logic is good
- post-cost or post-slippage profitability exists

It improves the ability to diagnose those questions with evidence.

## Human Approval

User requested this observability hardening pass and then requested opening a PR, checking CI until green, and merging after CI is green. The allowed scope is the lineage ledger, analyzer, documentation, tests, and this required evidence file.
