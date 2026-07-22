# Governed Codex + Antigravity Strategy Research

## Purpose

This control plane turns Codex and Antigravity into constrained engineering agents around TradeBot research. It does **not** make either model a trader and it never grants live execution authority.

- **Codex** is the implementer: isolated worktree, exact frozen contract, committed patch, tests, artifacts.
- **Antigravity** is the independent auditor: reproduce commands, verify hashes, attack leakage and fake progress.
- **Deterministic gates** decide whether the evidence is valid.
- **A human** may approve paper-trading eligibility only.
- **TradeBot runtime** remains the sole deterministic signal/risk system.

## State machine

```text
INTAKE
  -> HYPOTHESIS_FROZEN
  -> IMPLEMENTED (Codex)
  -> AUDITED (Antigravity approval)
  -> VALIDATED (all mandatory gates)
  -> PAPER_ELIGIBLE (human approval)
```

Fail-closed states are `REVIEW_REWRITE`, `REVIEW_REJECTED`, and `VALIDATION_FAILED`.

There is deliberately no `LIVE_ELIGIBLE` state.

## Mandatory gates

Every gate must have a real artifact inside the run directory and a matching SHA-256:

1. causal timestamps;
2. true next-bar execution;
3. transaction costs and slippage;
4. deterministic replay;
5. negative controls;
6. walk-forward analysis;
7. untouched holdout;
8. independent oracle;
9. artifact integrity.

A missing gate, failed gate, missing artifact, or mismatched hash blocks promotion.

## CLI workflow

```bash
python scripts/run_governed_strategy_research.py init \
  --run-dir runtime/governed_research/opening_state_v1 \
  --strategy-id opening_state_v1 \
  --title "Opening state continuation" \
  --objective "Test one frozen causal opening-state structure"

python scripts/run_governed_strategy_research.py packet \
  --run-dir runtime/governed_research/opening_state_v1 \
  --agent manual --role explorer

python scripts/run_governed_strategy_research.py freeze \
  --run-dir runtime/governed_research/opening_state_v1 \
  --hypothesis /path/to/hypothesis.json

python scripts/run_governed_strategy_research.py packet \
  --run-dir runtime/governed_research/opening_state_v1 \
  --agent codex --role implementer
```

After Codex commits its isolated worktree patch, record an implementation JSON containing the frozen hypothesis hash, base/head commit, branch, changed paths, passing test results, and artifacts.

Then generate the Antigravity packet:

```bash
python scripts/run_governed_strategy_research.py packet \
  --run-dir runtime/governed_research/opening_state_v1 \
  --agent antigravity --role auditor
```

Record Antigravity's independent review. `APPROVE` advances; `REWRITE` invalidates implementation/review hashes and returns to the freeze boundary; `REJECT` terminates the candidate.

Finally record the nine hash-pinned validation artifacts and require explicit paper approval:

```bash
python scripts/run_governed_strategy_research.py approve-paper \
  --run-dir runtime/governed_research/opening_state_v1 \
  --approved-by Ram
```

## Subscription boundary

Chat subscriptions are not treated as production APIs. The control plane generates structured packets that can be pasted into Codex or Antigravity. A local CLI may consume the same packet, but command invocation is intentionally outside this module and must remain inside the existing worktree supervisor and OS-level credential isolation.

## Safety guarantees

Every manifest and evidence document asserts:

```text
read_only=true
is_order_action=false
broker_api_called=false
live_mode_touched=false
allowed_for_runtime_wiring=false
allowed_for_live_execution=false
```

Implementation evidence is rejected if it changes broker, execution, order, risk, feed, credential, live-runtime, or secret paths.

## What this solves

- prevents post-outcome hypothesis rewriting;
- separates Codex implementation from Antigravity audit;
- ties every stage to hashes and committed evidence;
- blocks persuasive summaries without reproducible commands;
- prevents a backtest pass from silently becoming live authority.

## What this does not solve

It does not manufacture a profitable edge, supply missing historical data, validate unachievable fills, or guarantee future returns. It makes negative results trustworthy and positive results harder to fake.
