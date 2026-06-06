# Trade Quality Truth Audit

mode: REVIEW
candidate_id: PR-TRADE-QUALITY-TRUTH-AUDIT
decision: add_trade_quality_truth_audit
reason: Add a read-only audit that explains fallback executability truth, confidence_raw calculation, ranking separation, candidate-pool truth, and UI display truth without changing runtime trading behavior.
timestamp: 2026-06-07T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/trade-quality-truth-audit.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (read-only audit module + CLI + deterministic tests + review doc)
title: Trade Quality Truth Audit
scope: add a code-grounded audit that inspects fallback executability truth, confidence_raw computation, ranking separation, candidate-pool truth, and UI/display truth without changing behavior
requested_paths:
  - core/agents/trade_quality_truth_audit.py
  - scripts/run_trade_quality_truth_audit.py
  - tests/test_trade_quality_truth_audit.py
  - docs/agent_reviews/trade-quality-truth-audit.md
  - docs/agents/trade_quality_truth_audit.md
allowed_paths:
  - core/agents/trade_quality_truth_audit.py
  - scripts/run_trade_quality_truth_audit.py
  - tests/test_trade_quality_truth_audit.py
  - docs/agent_reviews/*
  - docs/agents/*
forbidden_paths:
  - core/broker*
  - core/order*
  - core/risk*
  - core/kite_depth_ws.py
  - strategies/*
  - dashboard/*
  - runtime/live*
  - logs/*
  - any runtime mutation or broker call
expected_tests:
  - PYTHONPATH=. pytest -q tests/test_trade_quality_truth_audit.py -vv
  - PYTHONPATH=. pytest -q tests/test_agent_contracts.py tests/test_agent_readers.py tests/test_agent_command_center.py -vv
  - PYTHONPATH=. python scripts/run_trade_quality_truth_audit.py --repo-root . --runtime-dir .runtime --logs-dir logs --out-dir .runtime/trade_quality_audit --format both
  - cat .runtime/trade_quality_audit/trade_quality_truth_audit_latest.md | sed -n '1,120p'
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/trade_quality_truth_audit_changed_paths.txt
acceptance_proof:
  - the audit is read-only and emits explicit non-action flags
  - fallback/recovered_fallback executable truth is proven or blocked with evidence
  - confidence_raw calculation is tied to code locations and component coverage
  - ranking is classified as true ranking or filter-only with evidence
  - candidate-pool truth is separated from direct emit paths
  - the UI truth distinguishes persisted filtered snapshots from ranked opportunities
```

## Scope Guard

- This PR is evidence-only.
- It must not change trading behavior, ranking behavior, strategy logic, Phase2, broker/order flows, websocket reconnect behavior, or dashboard runtime behavior.
- It must fail closed on missing files and missing runtime artifacts.

## Grill Me Review

- The audit must not invent proof when evidence is missing.
- Runtime evidence should be optional and read-only; code evidence may be used when runtime evidence is absent.
- The next PR recommendation must stay narrow and avoid hidden behavior changes.

## Hermes Review

- The audit should answer concrete truth questions, not merely summarize code names.
- It should distinguish canonical executable truth from filtered or advisory display layers.
- It should keep the output deterministic and easy to review in JSON and Markdown.

## GSD Review

- Keep the patch small: one new audit module, one CLI, one focused test file, and review docs.
- Add tests that prove fallback executability detection, confidence component coverage, ranking classification, candidate-pool detection, and safe report writing.

## QA / Safety Review

- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_allowed=false`
- `runtime_mutation_allowed=false`
- Missing runtime logs do not crash the audit.

## Acceptance Proof

- Fallback and recovered_fallback rows are shown as executable only if the audit can prove a bad row; otherwise they remain blocked/advisory.
- `confidence_raw` locations are reported from source code and component coverage is explicit.
- Ranking is classified as `true_ranking` or `filter_only` with supporting evidence.
- Candidate-pool truth is separated from direct emit paths.
- UI rows are identified as persisted top-opportunity snapshots, not raw runtime mutation.

## Runtime Proof Required After Merge

- Run the CLI against the current workspace with missing runtime logs and confirm the audit still writes JSON and Markdown.
- Confirm the audit remains read-only and does not call brokers or mutate runtime state.

## What This PR Does Not Prove

- It does not prove trading edge or profitability.
- It does not change ranking or scoring behavior.
- It does not change live execution, feed, websocket, or dashboard behavior.
- It does not claim runtime proof when runtime artifacts are absent.

## Human Approval

Human approval required before merge.
