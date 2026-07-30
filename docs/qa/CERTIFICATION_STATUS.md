# TradeBot QA Certification Status

## Current verdict

`NOT_CERTIFIED`

This status is deliberately fail-closed. A green regression suite, a stable live observation, or a large test count does not override an unresolved certification blocker.

## Evidence snapshot

Evidence captured during PR #761 work:

- Full deterministic paper/offline pytest lane: `6,774 passed`, `9 skipped`, `28 deselected`.
- Runtime emitted `2,379 warnings` during that run.
- The deterministic suite did not report repository line coverage, branch coverage, or mutation score.
- Gitleaks passed on the inspected head.
- CodeQL, Portfolio CI, Code Excellence, Strategy Registry, and ordinary CI passed on the inspected foundation head.
- The baseline-aware repo-forensics gate was green only because existing debt did not materially regress. Its underlying report remained `UNKNOWN` rather than certified.

Latest inspected static forensics debt:

- hard failures: `115`;
- unknowns: `177`;
- warnings: `99`;
- fake-confidence tests: `98`;
- critical callers visible only from tests: `4`;
- critical callers unreferenced: `1`;
- safety-critical findings: `23`;
- safety-high findings: `161`;
- evidence-high findings: `88`.

## Active certification blockers

### QA-CERT-BLOCK-001 — Automatic behavior patches

`sitecustomize.py` automatically installs multiple TradeBot compatibility/contract modules and replaces at least one third-party attribute. Some hooks rewrite candidate ranking, selection, orchestrator, market-data warmup, long-run stability, review-queue, and depth behavior.

Certification rule:

> Critical tests must pass against the real owner modules without automatic import-time behavior replacement.

Required evidence:

- runtime-shim audit reports zero active TradeBot-owned behavior patches;
- selected critical tests pass after physically removing `sitecustomize.py` from the CI checkout;
- eventually, the full deterministic suite passes without the automatic compatibility layer.

### QA-CERT-BLOCK-002 — Known vulnerable broker dependency

The declared dependency graph resolves to `autobahn==19.11.2` through the Zerodha Kite client. Dependency audit reports a known redirect-header-injection vulnerability fixed in Autobahn `20.12.3` and later.

The official Kite client pins the older Autobahn release exactly, so an untested direct override is not an acceptable fix.

Required evidence:

- a compatible, reproducible broker-client dependency strategy;
- websocket and REST authentication compatibility tests;
- reconnect, subscription, and credential-boundary tests;
- clean dependency vulnerability audit with no unapproved finding.

### QA-CERT-BLOCK-003 — Repo-forensics hard findings

The existing baseline-aware PR gate prevents regressions but permits inherited hard failures and unknowns. That is a maintenance control, not certification.

Required evidence:

- zero missing required entrypoints;
- zero missing critical modules;
- zero runtime-flow failures;
- zero critical callers missing or test-only;
- zero safety-critical findings;
- zero evidence-high findings;
- zero architecture-drift-high findings;
- every unknown either resolved or explicitly converted into a bounded, reviewed non-blocker.

### QA-CERT-BLOCK-004 — Test strength not measured

The existing suite has no enforced branch-coverage or mutation-quality threshold. Generated skipped skeletons and legacy fake-confidence patterns exist in the repository.

Required evidence:

- no new skipped, empty, unconditional-true, or unparseable tests;
- Tier A modules at `100%` line and branch coverage;
- Tier A mutation score at or above the approved threshold;
- every surviving mutant reviewed or eliminated;
- test-to-behavior traceability for critical boundaries.

### QA-CERT-BLOCK-005 — Auth ambiguity

`validate_token()` can represent a network-verification failure as `ok=True` with `auth_state=UNKNOWN_NETWORK`. A consumer checking only the boolean could treat an unverified credential as authenticated.

Required evidence:

- all consumers audited;
- only the canonical verified state can grant live readiness;
- network ambiguity cannot grant feed, candidate, approval, or execution authority;
- regression and mutation evidence prove the fail-closed rule.

### QA-CERT-BLOCK-006 — Non-functional evidence incomplete

The repository has feed smoke/soak and certification concepts, but there is not yet one consolidated, current certification pack proving load, stress, endurance, resource stability, restart recovery, concurrency, and controlled-live safety for the final integrated build.

Required evidence:

- deterministic load and stress budgets;
- sustained feed soak with resource-leak assertions;
- reconnect and restart torture tests;
- persistence and reconciliation recovery;
- controlled-live no-order or manual-approval-only proof;
- immutable artifacts tied to the exact certified commit.

## Certification gate hierarchy

A commit is `QA_CERTIFIED` only when all of the following are green on the same immutable commit:

1. test-integrity gate;
2. Tier A behavior and safety suites;
3. unpatched owner-module truth suite;
4. full deterministic suite;
5. line and branch coverage gates;
6. mutation-testing gates;
7. static security and secret scanning;
8. dependency vulnerability audit;
9. zero-debt repo-forensics certification;
10. replay and integration suites;
11. load, stress, endurance, and chaos suites;
12. controlled-live/manual-approval safety evidence;
13. independent evidence audit;
14. human QA lead approval.

A failure, cancellation, missing artifact, skipped mandatory lane, or unreviewed unknown keeps the verdict `NOT_CERTIFIED`.

## What a future certificate must contain

The certificate must identify:

- repository and commit SHA;
- dependency lock/hash;
- test counts by type and risk tier;
- skipped, xfailed, deselected, flaky, and quarantined counts;
- line and branch coverage by Tier A module;
- mutation score and surviving mutants;
- security and dependency findings;
- performance and soak metrics;
- replay data hashes;
- controlled-live evidence hashes;
- known limitations and approved residual risks;
- independent reviewer and human approval.

Until that evidence exists on one exact commit, TradeBot remains `NOT_CERTIFIED`.
