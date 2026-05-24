# Agent Review Evidence — EDGE-57 Fallback Advisory-Only Entry Contract

mode: PAPER
candidate_id: EDGE-57-FALLBACK-ADVISORY-ONLY-ENTRY-CONTRACT
decision: MAKE_FALLBACK_REFERENCES_NON_EXECUTABLE
reason: Recovered/fallback quote references must not create executable entries or fake confidence. They may remain display/advisory references only.
timestamp: 2026-05-24T12:55:17Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/EDGE_57_FALLBACK_ADVISORY_ONLY_ENTRY_CONTRACT.md and tests/test_entry_semantics.py

## Agent Work Contract

Enforce that recovered/fallback quote references cannot become execution-grade entries.

Allowed work:

- harden entry semantics fallback classification
- add negative tests proving fallback is non-executable
- add docs and evidence

Not allowed:

- broker imports or calls
- order placement behavior
- strategy or threshold changes
- dashboard rewrite
- runtime decision gating beyond entry semantics

## Grill Me Review

Risk: fallback rows can look executable and produce fake confidence.

Decision: fallback sources are advisory-only and cannot produce executable entries.

Risk: removing fallback execution can reduce executable count.

Decision: that is correct. A lower executable count is safer than fake executable rows.

Risk: display context might disappear.

Decision: fallback data can still produce display/reference context when a valid mark/mid/last exists.

## Hermes Review

This PR is safety/entry semantics only. It does not create, submit, modify, cancel, or exit orders. It does not call a broker API. It does not change live trading behavior.

Required safety fields:

- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false

## GSD Review

This is the correct next step after the UI critique: fix execution truth before improving ranking UI. Ranking bad fallback rows only makes fake precision look better.

## Scope Guard

- in_scope_list: entry semantics fallback advisory-only contract, tests, docs, evidence
- out_of_scope_list: strategy tuning, confidence scoring rewrite, ranked UI rewrite, broker behavior, artifact writers
- files_changed_list: core/entry_semantics.py, tests/test_entry_semantics.py, docs/EDGE_57_FALLBACK_ADVISORY_ONLY_ENTRY_CONTRACT.md, docs/agent_reviews/edge_57_fallback_advisory_only_entry_contract.md
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- dashboard_changed: false
- strategy_changed: false
- thresholds_changed: false

## QA / Safety Review

Tests prove:

- recovered fallback can be displayable but not executable
- last/current LTP fallback does not become execution-grade
- rest fallback recovery returns non-executable reference evidence

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_entry_semantics.py
```

Expected: all entry semantics tests pass.

## Runtime Proof Required After Merge

After merge, inspect a runtime candidate row with `option_ltp_source=rest_fallback` or `quote_source=recovered_fallback`. It must not show `execution_entry_status=executable`; it should remain advisory/non-executable reference evidence.

## What This PR Does Not Prove

- full confidence/ranking rebuild
- strategy profitability
- capital allocation
- candidate pool redesign
- screenshot-level dashboard proof

## Human Approval

Approved for EDGE-57 scope only: fallback entry references are advisory-only with no live behavior change.
