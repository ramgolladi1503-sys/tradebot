# TradeBot Enterprise QA Master Plan

Status: MEG shadow certification program

## Purpose

The QA program certifies one authoritative TradeBot operating mode: supervised, read-only Market Event Graph shadow observation. It proves system behavior and authority boundaries; it does not certify strategy profitability.

## Core principles

- Missing, stale, fallback, synthetic, unknown, contradictory, or unverifiable truth fails closed.
- Advisory evidence may remain visible but cannot become executable authority or capital allocation.
- Every critical decision is traceable to immutable evidence and one repository SHA.
- Tests, replay, paper, live observation, and broker authority remain separate.
- A green offline suite cannot replace a fresh governed market session.
- Test count is not evidence; every required test needs an executable oracle.

## Risk tiers

### Tier A — authority or irreversible side effects

Authentication, feed/subscription truth, persistence durability, manual approval, broker firewall, execution routing, restart/reconciliation, and evidence sealing.

Required behavior:

- fail closed on unknown state;
- complete negative, boundary, restart, and mutation proof;
- no unintended broker/network/order path in deterministic tests;
- exact reason codes and durable evidence.

### Tier B — operational and decision correctness

MEG observation, candidate authority, ranking, UI projection, reliability analytics, and post-market reporting.

Required behavior:

- causal completed-bar semantics;
- deterministic replay and prefix invariance where applicable;
- executable/advisory/blocked separation;
- stale/fallback rows excluded from selection and capital;
- displayed state agrees with authoritative state.

### Tier C — supporting tooling

Certification runners, evidence renderers, and test-integrity utilities.

Required behavior:

- deterministic parsing;
- explicit malformed-input handling;
- artifact hashes and reproducible reports;
- no hidden side effects.

## Required certification lanes

1. Authentication and startup.
2. Feed and subscription truth.
3. Persistence and shutdown.
4. Market Event Graph observation.
5. Authority, ranking, and UI truth.
6. Manual approval and broker/order firewall.
7. Restart and reconciliation.
8. AI reliability and evidence integrity.
9. Fresh controlled market observation.

The first eight run offline on one immutable SHA. The ninth is supplied by PR #763 and independently verified by PR #772.

## Test quality rules

Blocking defects in changed certification tests include:

- unconditional `assert True`;
- empty tests;
- skipped or skip-if tests presented as evidence;
- unparseable test modules;
- missing required gate files;
- timeout or nonzero gate command;
- semantic-hash mismatch;
- test suppression or global runtime-changing shims.

Helper-based assertions may be reviewed, but they do not silently count as strong local evidence.

## Evidence contract

Every offline gate records:

- repository SHA;
- command and exact test files;
- return code and timeout state;
- duration;
- test-file SHA-256 values;
- bounded stdout/stderr evidence.

The final system certificate additionally binds the semantic hashes of:

- the offline gate report;
- the sealed PR #763 post-market reliability certificate.

## Passing boundary

The final passing verdict is:

`MEG_SHADOW_SYSTEM_CERTIFIED_READ_ONLY`

It means only that the supervised advisory-only MEG shadow system satisfies the defined engineering and live-observation contracts. It does not authorize paper/live execution or claim a profitable edge.

## Defect policy

A concrete failure produces:

1. a minimal reproducer;
2. a failing behavioral test;
3. the smallest owning-module repair;
4. a negative control where practical;
5. updated evidence on one final SHA.

Passed gates are not repeatedly reopened unless contradictory evidence appears.