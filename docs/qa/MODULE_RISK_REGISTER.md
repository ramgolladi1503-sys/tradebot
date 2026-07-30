# TradeBot Module Risk Register

Status: initial inventory; Phase 0 must replace broad groups with a generated file-by-file inventory.

## Risk model

- **Tier A:** failure can place an unintended order, exceed risk, accept false live truth, expose credentials, lose execution auditability, or misrepresent authority.
- **Tier B:** failure can materially alter candidate quality, operational decisions, persisted state, replay truth, or operator understanding.
- **Tier C:** failure is contained to tooling, research convenience, documentation generation, or non-authoritative output.

## Initial ownership and certification matrix

| Area | Representative modules | Tier | Primary QA owner | Mandatory automation | Coverage target |
|---|---|---:|---|---|---|
| Authentication and credential authority | `core/auth.py`, `core/auth_manager.py`, `core/kite_client.py`, `core/security_guard.py`, runtime auth freshness | A | QA 1 | behavior, negative, state, security, concurrency, logging, startup integration | 100% line/branch |
| Feed connection and websocket lifecycle | `core/kite_depth_ws.py`, `core/feed/*`, feed supervisor/recovery/coordinator | A | QA 2 | model/state transition, chaos, reconnect, auth block, soak, broker firewall | 100% line/branch |
| Market-data ingestion and freshness | market data, tick/depth persistence, subscription truth, freshness/readiness | A | QA 2 | ordering, dedupe, gap, stale, outlier, replay, property, load | 100% line/branch |
| Feature engineering and causality | indicators, feature builders, completed-bar/window logic | B | QA 3 | boundary, property, metamorphic, NaN, no-future-leak, replay parity | 95% line / 90% branch |
| Strategy implementations | ORB/VWAP/compression/pullback/event-graph and other active strategies | B | QA 3 | behavior contract, sequence oracle, regime, conflict, timing, negative controls | 95% line / 90% branch |
| Candidate pool, scoring and ranking | candidate collection, confidence/opportunity score, ranking/read model | B | QA 3 | monotonicity, tie-breaking, stale/fallback authority, determinism, load | 95% line / 90% branch |
| Trade builder and contract resolution | trade builder, option selection, instrument resolver, quote binding | A | QA 4 | decision tables, boundary, stale/mismatch, expiry/strike, idempotency, integration | 100% line/branch |
| Risk engine and sizing | limits, sizing, daily halt, stop/target constraints, kill thresholds | A | QA 4 | exact boundaries, property invariants, concurrency, restart, destructive inputs | 100% line/branch |
| Review queue and manual approval | queue persistence, approval validity, expiry, revalidation | A | QA 4 | state model, duplicate approval, stale approval, quote downgrade, restart | 100% line/branch |
| Execution routing and broker boundary | execution intent, mode gates, broker calls, retries, partial fills | A | QA 5 | broker firewall, exactly-once intent, retry/idempotency, timeout, partial fill | 100% line/branch |
| Trade log, persistence and recovery | SQLite/files, journals, hashes, startup recovery | A | QA 5 | atomicity, corruption, migration, crash/restart, concurrency, audit lineage | 100% line/branch |
| Reconciliation and outcome truth | fill sync, reconciliation, outcome reducer, position truth | A | QA 5 | mismatch tables, duplicate fills, late fills, partials, restart, invariants | 100% line/branch |
| Governance, readiness and kill switch | governance gate, health gate, pre-live readiness, halt/reset | A | QA Lead + QA 5 | fail-closed integration, state transition, evidence completeness, abuse | 100% line/branch |
| Dashboard and UI read models | Streamlit pages, read models, filters, status/ranking views | B | QA 6 | source-of-truth parity, stale state, empty/error states, accessibility, UI regression | 95% line / 90% branch |
| Observability, reporting and alerts | logs, traces, metrics, reports, Telegram/email adapters | B | QA 6 | reason-code completeness, secret redaction, schema, delivery failure, replay | 95% line / 90% branch |
| ML model lifecycle | dataset build, training, registry, activation, inference | B | QA 3 | lineage, schema, leakage, deterministic seed, drift, version compatibility | 95% line / 90% branch |
| Backtest and replay | option replay engine, backtest, WFA, certification | B | QA 3 + QA 5 | timing causality, fill/cost model, deterministic replay, negative controls | 95% line / 90% branch |
| Agentic/AI supervision | agent supervisor, live RCA agent, evidence generation | B | QA 6 | authority boundary, hallucination containment, read-only proof, timeout, audit | 95% line / 90% branch |
| Operational scripts | startup, shutdown, token generation, data download, maintenance | B/C | owning QA | CLI contract, destructive confirmation, path safety, exit code, idempotency | 85–95% by risk |
| Research-only utilities | isolated discovery and audit runners | C unless promoted | QA 3 | provenance, deterministic output, leakage guards, independent audit | 85% line / 80% branch |

## Highest-priority cross-module contracts

### C1 — Live truth authority

No connection flag, fallback quote, cached quote, reconstructed quote, stale quote, UI row, or strategy confidence may grant execution authority without the canonical freshness and quote-authority gates.

### C2 — Exactly-once trade intent

Retries, duplicate callbacks, concurrent approvals, websocket reconnects and process restarts must not create more than one execution intent for one approved opportunity.

### C3 — Risk revalidation

Risk must be revalidated at the final irreversible boundary. A previously passing candidate or approval cannot bypass a later halt, exposure change, price change, expiry change, or stale-data transition.

### C4 — Persist-before-side-effect

An irreversible external action must not occur unless the required local intent/audit record can be durably persisted or the design explicitly proves compensating recovery.

### C5 — Auth fail-closed

Missing, invalid, expired, drifted or unauthorized credentials must stop live connectivity and order reachability. Network ambiguity must remain distinguishable from proven authentication success.

### C6 — Replay/live causal parity

Research and replay must use information that was available at the decision timestamp and must not silently use completed future bars, later option-chain state, revised labels, or post-event constituents.

### C7 — Operator truth

Dashboard, logs, reports and alerts must agree on whether an item is executable, queue-only, advisory-only or blocked, including the same reason codes and authoritative timestamps.

## Phase 0 inventory outputs still required

1. Enumerate every production Python module, shell script, workflow, schema and dashboard page.
2. Map every test file and test ID to owning modules and behavior requirements.
3. Identify modules with no direct tests, only import tests, or only mock-interaction tests.
4. Record all skips and xfails with owner, reason and expiry.
5. Detect `assert True`, empty tests, broad exception assertions and tests that patch the unit under test.
6. Produce current line/branch coverage and mutation baselines.
7. Measure suite runtime, flaky rerun rate and top slow tests.
8. Create a blocking defect for every uncovered Tier A behavior.
