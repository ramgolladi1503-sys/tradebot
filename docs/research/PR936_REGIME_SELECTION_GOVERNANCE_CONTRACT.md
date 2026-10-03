# PR #936 node G — post-hoc regime selection governance contract

```text
source_agent: hermes
action: DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES, UPDATE_DOCS
title: Prevent post-hoc regime filtering from being presented as confirmation
scope: Research playbook, deep-dive checklist and historical HTF regime narrative
requested_paths: docs/research/strategy_research_playbook.md, docs/research/strategy_deepdive_checklist.md, docs/research/htf_range_expansion_deepdive_timeline.md
allowed_paths: Those three documents and this contract
forbidden_paths: Strategy/runtime code, broker/order/risk/feed paths, protected outcomes, ledgers, credentials, CI, dependencies
expected_tests: Static source review of guidance; no outcome files or strategy execution
acceptance_proof: Documents preserve original all-regime trial, explicitly label outcome-selected regime restrictions as new exposed hypotheses, prohibit clean OOS promotion, and preserve negative trial evidence
```

## Invariants

- A regime restriction selected after inspecting outcome-stratified results is a new, exposed hypothesis and a new trial-family child.
- The original all-regime candidate, its negative results, the complete search/selection denominator, and the selection rationale remain preserved.
- Post-hoc regime filtering cannot produce independent confirmation, untouched OOS status, or readiness promotion from the same outcomes.
- A future filtered candidate requires a frozen ex-ante rule, prospective or otherwise untouched evaluation cohort, complete trial registration, costs, and independent review before any separate readiness decision.

## Acceptance review

The three scoped documents will be checked for language that treats outcome-informed filtering as a valid confirmation or automatic advancement. No runtime behavior or market evidence is changed or asserted.
