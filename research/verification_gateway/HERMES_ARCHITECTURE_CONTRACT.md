# Hermes architecture contract — PR #936 verification gateway

```yaml
source_agent: hermes
action: DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
title: Convert PR #936 prototype into an evidence-bound, isolated research-verification pipeline
scope: Research-only tooling and synthetic acceptance evidence; no broker, order, live, or protected-outcome access
requested_paths:
  - research/verification_gateway/**
  - tests/research/test_verification_gateway_*.py
  - docs/research/verification_gateway/**
  - .github/workflows/ci.yml only for explicit installation of the optional isolated verification requirements, with no gate weakening
allowed_paths:
  - research/verification_gateway/**
  - tests/research/test_verification_gateway_*.py
  - docs/research/verification_gateway/**
forbidden_paths:
  - main.py
  - run_live.sh
  - config/**
  - credentials.py
  - core/execution*
  - core/broker*
  - core/order*
  - core/risk*
  - core/feed*
  - strategies/**
  - requirements.txt
  - pyproject.toml
  - protected ledgers, sealed outcomes, canonical market data, runtime artifacts
expected_tests:
  - pytest -q tests/research/test_verification_gateway_contracts.py
  - pytest -q tests/research/test_verification_gateway_data.py
  - pytest -q tests/research/test_verification_gateway_registry_bridge.py
  - deterministic adversarial synthetic tests for forged flags, stale hashes, future-data mutation, timestamp ordering, and registry action boundaries
acceptance_proof:
  - Exact PR SHA and current main base identified; local dirty checkout preserved and excluded
  - Optional dependencies resolve from exact pinned versions outside production dependency surfaces
  - CI installs the optional verification dependency set or the verification suite is isolated into an equivalent explicit workflow
  - Verifier computes content-bound results from allowed synthetic/exposed inputs; caller booleans and self-asserted review strings do not grant readiness
  - Source review evidence binds spec/source digest and independent reviewer identity; missing source or material ambiguity blocks
  - Synthetic #1 post-close gap and #17 rolling-20 discrepancy fixtures do not claim historical source fidelity absent authoritative references
  - Normal official research entry points and API bypass attempts are enumerated; direct filesystem access threat is explicit
  - Existing Monte Carlo defect is independently reproduced on synthetic inputs; any repair retains deterministic, distinct resampling and does not access outcome files
  - No protected outcome data, broker API, order action, strategy/runtime threshold, or live boundary is accessed or changed
  - Independent review and clean-checkout reproducibility are recorded against exact hashes
```

## Architecture and invariants

The gateway supplements EDGE-65/EDGE-67 metadata. It does not authorize discovery, outcome access, execution, certification, or trading. Evidence has explicit states (`NOT_RUN`, `PASS`, `BLOCK`, `NOT_VERIFIED`) and binds the frozen spec digest, source digest, verifier implementation digest, fixture/data digest, and allowed read paths. A caller-provided boolean, free-form artifact path, or `reviewed=true` field is never sufficient authority.

The evidence chain is monotonic and fail-closed: source provenance and independent review → frozen specification → independent mathematical/event oracle → temporal-causality and data shape/authority → synthetic execution/cost parity → registered trial/access state → permitted evaluation. A missing predecessor blocks successors. Historical exposure remains exposure; repairs do not create unseen OOS.

All CI fixtures are synthetic and physically separate from protected outcomes. Verification dependencies remain in the research-only dependency surface; if CI runs these tests, the workflow explicitly installs the isolated set rather than silently relying on root requirements. This does not change production runtime dependencies.

### Hypotheses and failure modes

- Hypothesis: an immutable source contract plus independently computed, content-bound evidence can prevent accidental mis-translation and stale/forged gate reuse in ordinary official APIs.
- It cannot prevent a user/process with raw filesystem access from opening data or bypassing code. That threat requires OS/container permissions, not a Python API claim.
- Known #1 and #17 defects receive synthetic regression fixtures. Authentic-source claims remain blocked until original authoritative references are provided and hashed.
- Existing Monte Carlo sampling appears to repeat the same ordered sample for every iteration. Verify only on a synthetic vector first; any correction must distinguish sampling semantics and report uncertainty limits.

## Workflow

Node A inventory is complete only for the PR checkout and public/current Git metadata. B audits dependencies and existing components. C-E build and test source, translation, and causal/data evidence. F validates a small independent synthetic event simulator against pinned tapes. G audits statistics with synthetic fixtures and repairs only reproduced defects. H identifies official entrypoints and applies a mandatory evidence chain without touching execution/runtime. I exercises positive and negative mutations in a disposable test environment. J records independent audit, exact SHA/test evidence, and unresolved authority blockers. Upstream content changes invalidate dependent evidence.

## Hermes -> GSD execution handoff

`source_agent: gsd`; allowed actions: `PLAN_PR`, `GENERATE_TESTS`, `GENERATE_PATCH`, `FIX_TEST_FAILURE`, `UPDATE_DOCS`.

First execution task: reproduce PR CI collection failures from exact PR SHA in isolated research dependencies, fix only this verification suite's dependency integration, and add deterministic behavior tests that reveal whether evidence aggregation accepts fabricated caller pass flags. Then continue earliest incomplete DAG prerequisite. Keep the PR draft and readiness verdict blocked until all applicable gates are independently evidenced.

```text
read_only=true
append=false
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
```
