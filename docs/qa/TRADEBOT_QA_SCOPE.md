# Tradebot QA Scope

## Scope

This QA program covers behavior, safety, edge validation, profitability truth, read-model truth, replay truth, and regression protection for Tradebot.

It does not aim to maximize test count. It aims to maximize confidence that the product is safe, honest, and capable of improving trading edge.

## In Scope

### Feed and Market Data Truth

- WebSocket connection state
- underlying LTP freshness
- option quote freshness
- option depth freshness
- subscription coverage
- recovery and restart state
- market-open versus market-closed behavior
- stale or fallback data blocking execution

### Candidate Generation and Classification

- valid setup creates visible candidate
- weak setup becomes advisory, blocked, or rejected
- wrong regime downgrades or blocks candidate
- bullish, bearish, and range candidates are supported
- raw candidates are preserved but not promoted without proof

### Candidate Pool Quality

- duplicate concentration
- directional imbalance
- fallback contamination
- thin pool quality
- strategy-family concentration
- pool-level no-trade triggers

### Scoring and Ranking

- score separation
- expectancy-aware ranking
- regime-aware ranking
- execution-quality-aware ranking
- no high-score override for unsafe candidates
- deterministic tie-breakers

### No-Trade Evidence

- stale feed no-trade
- fallback data no-trade
- chop regime no-trade
- conflicting signal no-trade
- weak option confirmation no-trade
- pool concentration no-trade
- baseline weakness no-trade

### Execution Safety

- manual approval boundary
- risk gate boundary
- broker call impossibility in tests
- order action flags false unless deliberately tested with safe fakes
- dry-run evidence cannot become real order evidence

### Dashboard and Read Model Truth

- top opportunities read ranked snapshot
- raw rows remain debug/all-candidates evidence
- fallback rows visible but non-executable
- stale snapshots shown as stale
- dashboard does not create trading truth

### Replay, Backtest, and Paper Truth

- replay is deterministic
- replay is read-only
- future data is blocked
- paper journal integrity
- outcome reducer truth
- cost-adjusted profitability truth

### QA Governance

- PR test evidence
- edge-purpose explanation
- negative/fail-closed tests
- focused test command proof
- relevant regression command proof

## Out of Scope

- Real broker order placement inside tests
- Live market dependency for deterministic QA
- Test-only bypasses that weaken safety
- Blessing current buggy behavior as expected behavior
- Cosmetic coverage-only tests
- Dashboard UI pixel-perfect testing unless it protects trading truth

## Test Types Required by Change Area

| Change Area | Required Tests |
|---|---|
| Feed | fresh path, stale path, recovery/warmup path, missing proof path |
| Candidate/Strategy | valid setup, weak setup, wrong regime, bad quote quality |
| Scoring/Ranking | strong-vs-weak separation, unsafe high-score block, deterministic tie |
| No-Trade | blocking evidence, primary reason, no executable promotion |
| Execution | manual approval, risk block, broker/order firewall |
| Dashboard | ranked snapshot source, stale/fallback visibility, raw-row separation |
| Replay/Backtest | no future data, deterministic output, read-only evidence |
| Bug Fix | failing regression, fixed behavior proof, negative no-return test |

## Merge Readiness

A PR is not QA-ready until:

- behavior is documented
- edge purpose is clear
- focused tests pass
- negative tests exist for unsafe paths
- relevant regression suite passes
- broker/network/order boundaries remain protected
- QA gate passes
