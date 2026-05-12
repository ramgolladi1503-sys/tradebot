# DECISION_LOG.md

# Aixion Quant Console / Tradebot Decision Log

**Purpose:** Record major product and engineering decisions so the project stops drifting.

---

## Decision format

```markdown
## YYYY-MM-DD — Decision title

Status: Proposed | Accepted | Rejected | Superseded

Decision:

Why:

Alternatives considered:

Impact:

Validation required:
```

---

## 2026-05-12 — Product docs live under docs/product

Status: Accepted

Decision:

Store the product bible pack under:

```text
docs/product/
```

Why:

Repo root already contains README and operational docs. Product docs should be grouped clearly without polluting root.

Impact:

- Easier navigation.
- Cleaner PR.
- Can link from README later.

Validation required:

- Files exist in branch.
- PR opened against main.

---

## 2026-05-12 — Tradebot must become an opportunity engine, not a table viewer

Status: Accepted

Decision:

The product architecture must route strategy output through candidate pool, scoring, ranking, execution gates, and risk before dashboard display.

Why:

Visible rows do not prove opportunity quality. A dashboard that only filters emitted rows is not enough.

Alternatives considered:

- Keep adding UI filters.
- Patch confidence values directly.
- Add ML ranking immediately.

Rejected because those hide the real problem.

Impact:

- Candidate pool becomes required.
- Ranking engine becomes required.
- Dashboard must show top opportunities first.

Validation required:

- Candidate schema tests.
- Ranking tests.
- Dashboard row tests.

---

## 2026-05-12 — Fallback data must not be executable

Status: Accepted

Decision:

Any fallback/recovered quote must be demoted to advisory/watchlist or blocked.

Why:

Fallback data can create fake precision and unsafe execution readiness.

Impact:

Required invariant:

```text
fallback_used == true -> execution_allowed == false
```

Validation required:

- Execution gate test.
- Dashboard test showing fallback as non-executable.

---

## 2026-05-12 — Dashboard is a reader, not the source of trading truth

Status: Accepted

Decision:

Dashboard must display persisted/runtime truth. It must not silently recompute final execution decisions.

Why:

When UI recomputes truth, logs and display can diverge.

Impact:

- Persist ranking/execution readiness.
- Dashboard must show blockers from source artifacts.

Validation required:

- Dashboard model tests.
- Artifact schema tests.

---

## 2026-05-12 — Score separation is a product requirement

Status: Accepted

Decision:

Top opportunities must be materially separated from weaker candidates, or score compression must be flagged.

Why:

A top trade with score 0.46 beside another at 0.45 is not a strong ranking signal.

Impact:

- Score breakdown required.
- Score-compression warning required.

Validation required:

- Scoring unit tests.
- Rank distribution tests.

---

## 2026-05-12 — BUY-only output must be treated as suspicious

Status: Accepted

Decision:

If candidate output is mostly one-directional, the system must expose a directional-bias diagnostic.

Why:

Markets are not always bullish. BUY-only output may reveal strategy bias, filter bias, or broken bearish logic.

Impact:

- Add directional summary.
- Add regime comparison.

Validation required:

- Bias diagnostic test.

---

## 2026-05-12 — Risk fields are required for executable trades

Status: Accepted

Decision:

Every executable candidate must have stop, target, max loss, and suggested size.

Why:

Execution without risk definition is incomplete.

Impact:

Required fields:

```text
position_size
max_loss
stop_loss
target
risk_reward
```

Validation required:

- Execution gate or risk-layer tests.

---

## Pending decisions

- Exact scoring formula weights.
- Exact candidate schema path and module name.
- Whether ranking snapshots are JSONL, SQLite, or both.
- Whether risk allocation starts fixed-fractional or volatility-adjusted.
- Whether ML ranking is deferred until paper outcome data exists.
