# PR #936 baseline and safety map — 2026-09-27

```yaml
source_agent: hermes_then_gsd
action: MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES, GENERATE_PATCH, GENERATE_TESTS
title: Establish exact PR #936 baseline and safety boundaries
scope: Public Git metadata, prototype source, synthetic tests, and filesystem metadata only
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
append: false
```

## Repository and checkout authority

- Repository remote: `https://github.com/ramgolladi1503-sys/tradebot` (fetch/push URL from local Git config).
- Canonical local checkout: `/Users/madhuram/tradebot`; `HEAD=c5e4ce8e741831dfe4c1b58572a3bb4018a4132d`, branch `main`, ahead of `origin/main` by 5 and behind by 12 commits. It had 2,253 tracked/untracked status entries at inspection. It was not modified.
- Current GitHub base: `origin/main=0f95e60335ddcadbe397e5ca837946ed8b1cdec7` (PR #936 base and merge-base).
- PR #936: [open draft](https://github.com/ramgolladi1503-sys/tradebot/pull/936), branch `research/reuse-first-verification-gateway-v1`, head `35d46108c05ccd11bfd66fdfd4f453f15690c120`, 9 commits ahead of current `origin/main`, 0 behind.
- Dedicated inspection/execution checkout: `/Users/madhuram/.codex/worktrees/pr936-verification-gateway/tradebot`, initially clean at the exact PR head. The Hermes contract and GSD follow-up changes are in this isolated worktree.
- No local `origin/research/reuse-first-verification-gateway-v1` tracking ref existed before a fetch. The fetched PR ref is `ram/pr936-inspection`.

## Local-only work and source authority

The dirty canonical checkout contains the Sep 27 strategy root-cause matrix at `output/edge_hunt_strategy_root_cause_matrix_20260927.md`, its Hermes contract, a repaired `next_eligible_session` boolean column, and focused regression tests. This work is absent from the PR #936 tree and must not be represented as merged or copied into this PR. The matrix is an evidence synthesis, not a newly recomputed result, and says `NO_CERTIFIED_EDGE`; its published baseline is 30 families, with exposure/OOS and sample limitations. The draft PR description independently reports 9 close, 5 reconcile, 15 prospective-only, 1 options-data-blocked, but that count is not a verified canonical readiness denominator. PR #936 does not establish that classification in its code.

No protected outcome values, ledgers, market prices, or quotes were read for this map. Source references for historical failures #1 and #17 are absent from the clean PR tree as source-grounded fixtures; those regressions remain synthetic-only until authoritative originals are made available through an approved evidence path.

## Protected and out-of-scope surfaces

Do not alter or read for this work: broker/order/live behavior; `main.py`, `run_live.sh`, `config/`, credentials/secrets, `core/execution*`, `core/broker*`, `core/order*`, `core/risk*`, `core/feed*`, `strategies/`; `requirements.txt`, `pyproject.toml`; protected outcome ledgers, sealed validation cohorts, canonical research outputs, or runtime artifacts. No test may traverse into an outcome store. Any future OS-level access restriction must be implemented and audited outside the ordinary Python API, with explicit deployment ownership.

Allowed implementation surface is limited to `research/verification_gateway/**`, `tests/research/test_verification_gateway_*.py`, and gateway documentation. The existing root CI workflow does not install the gateway's research-only dependencies. Its current PR run failed collection with `ModuleNotFoundError: No module named 'pydantic'` in all three gateway test modules. The correct dependency/CI repair needs a separate authorized change because dependency manifests and CI workflow are protected by task instructions.

## Safety and authority model

The PR prototype is a fidelity-schema experiment only. EDGE-65 is a metadata registry and EDGE-67 is an existing research contract; neither grants outcome access. A typed spec or report is not source verification. A free-form reviewer string is not reviewer identity. A content digest is integrity evidence only if independently recomputed against authoritative bytes. Python API checks cannot contain arbitrary scripts or a process with direct filesystem permissions.

The initial PR report aggregator accepted caller-supplied booleans and could describe those claims as verified. This patch removes that route: the report remains `BLOCKED` until an independent verifier and governance-backed review artifact exist. It still does not implement the end-to-end readiness gateway requested in the brief.

## Current verified facts

- Focused prototype tests were run in disposable `/tmp/pr936-verification-venv`, Python 3.12.2, with isolated research dependencies; latest run: 20 passed (8 non-failing warnings).
- The clean-checkout/default CI equivalent is still blocked by missing optional dependencies in current CI.
- `core/research_pipeline.py::_monte_carlo()` in current `origin/main` computes the same cyclically ordered sample on every iteration. It was inspected as source only; no outcomes were loaded. Statistics repair and regression tests must be a separate Hermes/GSD-scoped change.
- The normal research entrypoint inventory, protected data permissions, true file read-path enforcement, full ledger boundary, cost/execution parity, source fidelity for historical #1/#17, and independent review are not implemented or verified by this PR.
- Required baseline `NO_CERTIFIED_EDGE` remains in force. No strategy-hunt readiness or strategy certification is claimed.
