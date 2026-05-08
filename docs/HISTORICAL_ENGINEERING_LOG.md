# Tradebot Historical Engineering Log

This document records the major Tradebot issues, pull requests, fixes, and release lessons that already happened.

The purpose is to make the branch-protection policy, PR template, issue templates, CI gates, health gate, and release checklist grounded in real project history instead of generic process text.

---

## Control issues already created

### Issue #25 — Project control workflow

This issue established the need for a repeatable engineering workflow:

```text
issue -> branch -> implementation -> tests -> PR -> review -> documentation
```

Why it mattered:

- Tradebot had many branches and scattered debugging notes.
- Future changes needed clearer ownership, validation, and rollback notes.
- The repo needed categories such as bug, architecture, test-gap, execution-risk, data-quality, dashboard, paper-trading, and live-readiness.

How it shaped the current hardening docs:

- PRs now need purpose, impact area, validation evidence, and safety notes.
- Issue templates now classify the affected subsystem.
- Branch protection now requires PR-based changes before `main` is touched.

---

### Issue #26 — Critical no executable trades investigation

This issue captured the highest-impact runtime problem: the system was not consistently producing executable trades.

Investigation areas recorded:

- Feed freshness.
- Gating readiness classification.
- Candidate scoring vs execution score mismatch.
- Contract-resolution failures.
- Liquidity filters.

Why it mattered:

- A bot that generates rows but no executable trades is not operationally useful.
- The system needed clear blocker reasons and candidate-status transitions.

How it shaped the current hardening docs:

- The release checklist now requires health-gate, stale-feed, and contract-resolution checks.
- The PR template asks whether executable classification can change.
- The bug template asks for affected subsystem and reproduction evidence.

---

## Major past PR themes

### PR #1 — Phase 2 freeze foundation and Phase 3 execution scaffolding

Added the first strict handoff boundary between decision output and execution routing.

Key lesson:

- Execution handoff needs one clear truth boundary.
- A row should not become executable late unless the required execution intent exists.

Current checklist impact:

- Review queue and execution-router changes must validate final decision consistency.

---

### PR #4, #5, and #6 — Execution truth guard and score separation

These PRs dealt with fallback, planning, synthetic, softened, and advisory candidates.

Key lesson:

- Visible candidates are not automatically executable candidates.
- Candidate class, score, and execution permission must be separated.

Current checklist impact:

- Release checks must confirm degraded candidate classes cannot silently enter executable status.
- PRs touching scoring or ranking must explain candidate-class impact.

---

### PR #8 to #14 — Regime, portfolio, capital allocation, and sizing phases

These PRs introduced or planned the next intelligence layers:

- Regime-aware scoring.
- Candidate score caps.
- Symbol clustering.
- Portfolio-aware selection.
- Risk-budget allocation.
- Adaptive sizing and drawdown-aware controls.

Key lesson:

- Ranking alone is weak.
- Tradebot needs regime context, diversification, allocation discipline, and risk-aware sizing.

Current checklist impact:

- Feature templates ask whether a change affects ranking, allocation, sizing, or risk exposure.
- Release checks separate normal docs/UI changes from capital/risk-sensitive changes.

---

### PR #16 and #17 — Fallback execution blocking and fallback score caps

These PRs hardened fallback behavior.

Key lesson:

- Fallback is a data-quality warning, not proof of execution readiness.
- Fallback-derived candidates need strict caps and clear classification.

Current checklist impact:

- Release checks include fallback handling.
- Bug reports involving ranking should include candidate class, score, execution status, and blocker reason.

---

### PR #18 — Execution intent final decision fix

This PR focused on final-decision consistency.

Key lesson:

- Intent, final decision, persisted status, and dashboard status must agree.

Current checklist impact:

- Dashboard and persistence reviews now need field-consistency checks.

---

### PR #20 to #24 — Phase 2 decision-engine hardening and integration

These PRs hardened:

- Soft and hard reject handling.
- Softened candidate lifecycle.
- Critical-failure hard drops.
- Quality-only soft degradation.
- Queue-only caps.
- Strict real-candidate diagnostic mode.
- Decision-engine-backed promotion path.
- Score integrity constraints.

Recorded validation from PR #20:

```bash
pytest -q tests/test_trade_builder.py tests/test_trade_builder_soften_paths.py tests/test_engine_phase2_adapter.py tests/test_review_queue_decision_engine.py tests/test_soft_reject_ranking_integration.py tests/test_decision_engine.py
# 48 passed
```

Key lesson:

- Candidate lifecycle must be explicit.
- Soft-degraded candidates must not become strong executable candidates by accident.

Current checklist impact:

- PRs touching trade builder, decision engine, review queue, or ranking need targeted tests.

---

### PR #27 — No executable trades diagnostics and option-token fallback

Linked issue:

- Issue #26.

What it added:

- Diagnostic parser for no-executable-trades investigations.
- No-executable-trades runbook.
- Project-control manual.
- Diagnostic regression tests.
- Conservative option-token fallback when exact contract lookup misses.

Recorded validation:

```bash
python -m pytest tests/test_diagnose_no_executable_trades.py -q
# 2 passed

python -m pytest tests/test_option_token_resolver.py -q
# 3 passed
```

Known broader-test blocker recorded at the time:

```text
ModuleNotFoundError: No module named 'core.regime_detector'
```

Key lesson:

- Diagnostics should be deterministic and safe to run without live dependencies.
- Contract fallback needs strict guardrails and honest test reporting.

Current checklist impact:

- Release checks include diagnostic evidence when executable trades disappear.
- PR template asks whether contract resolution or fallback behavior changed.

---

### PR #28 — Freshness, tick-store latency, and strategy-family preservation

What it fixed:

- Freshness SLA uses tick-store memory first.
- DB reads avoid flush-boundary timing issues.
- Tick store added no-flush helper paths and safer defaults.
- Strategy layer preserves `strategy_family`.
- Kite depth websocket import path was cleaned up.
- Historical-data path received cooldown suppression and injected-stub support.

Recorded validation guidance:

```bash
./run_live.sh
```

Runtime evidence to watch:

```text
.runtime/logs/feed_runtime_latest.json
decision stream
```

Key lesson:

- Feed freshness is not only a database problem.
- Runtime memory path, DB flush timing, and decision-stream evidence all matter.

Current checklist impact:

- Release checks include feed freshness and runtime-log review for feed-related changes.

---

## Current CI and health gates already present

### `ci / unit_tests`

Purpose:

- Install dependencies.
- Run the full pytest suite in a paper/offline-safe environment.

Command represented by the workflow:

```bash
PYTHONPATH=. pytest -q
```

---

### `ci / health_gate`

Purpose:

- Run deterministic offline health validation.

Command represented by the workflow:

```bash
PYTHONPATH=. python -m core.health_gate --desk DEFAULT --strict
```

Failure artifacts:

```text
.runtime/logs/health_gate_report.json
.runtime/logs/health_gate_report.md
.runtime/logs/events.jsonl
.runtime/logs/recon.json
```

Key lesson:

- Health-gate artifacts are release evidence, not optional logs.

---

### `Portfolio CI`

Purpose:

- Validate portfolio-facing files.
- Validate runtime-health, contract-resolution guard, and stale-feed simulator tests.

Focused tests:

```bash
pytest -q tests/test_runtime_health_eval.py tests/test_contract_resolution_guard.py tests/test_stale_feed_simulator.py
```

Key lesson:

- Portfolio quality and runtime safety overlap in this repo.
- Stale-feed and contract-resolution checks are core quality gates.

---

## Historical rules now enforced by docs and templates

These rules come directly from past Tradebot work:

1. Fallback, planning, synthetic, softened, and advisory candidates need explicit separation from executable candidates.
2. Candidate score, execution score, persisted state, and dashboard state must not drift silently.
3. Contract-resolution failures must remain visible.
4. Stale feed and stale option LTP must not be treated as normal executable data.
5. Dashboard rows must show enough context to explain the trade state.
6. Risk and sizing changes require stronger validation than simple docs changes.
7. Runtime-sensitive PRs need targeted tests, not only broad claims.
8. Health-gate failure artifacts must be reviewed when the health gate fails.
9. Known test blockers must be recorded honestly.
10. Infrastructure hardening improves safety and credibility, but it does not create trading edge by itself.

---

## Historical release evidence checklist

Use this checklist when documenting a past PR, release, or major fix.

- [ ] Issue or PR number recorded.
- [ ] Problem statement recorded.
- [ ] Subsystem touched.
- [ ] Runtime risk classified.
- [ ] Validation commands recorded.
- [ ] Known skipped or failed checks recorded honestly.
- [ ] Rollback path recorded when applicable.
- [ ] Health-gate status recorded when relevant.
- [ ] CI status recorded when relevant.
- [ ] Paper/live validation notes recorded when relevant.
- [ ] Remaining risk recorded.

---

## Bottom line

The current branch-protection policy, release checklist, PR template, and issue templates are now tied to actual Tradebot history.

The highest-risk historical areas are:

- Execution truth.
- Fallback execution.
- Contract resolution.
- Feed freshness.
- Candidate scoring and ranking integrity.
- Review queue and dashboard persistence.
- Risk gates and execution lifecycle.
- Health-gate and CI evidence.
