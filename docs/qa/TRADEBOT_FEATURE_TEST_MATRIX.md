# Tradebot Feature Test Matrix

This matrix maps product behavior to edge purpose, risk, and required tests.

## Priority 0: Safety and Edge Truth

| Feature / Contract | Edge Purpose | Risk If Missing | Required Behavior Tests | Suite |
|---|---|---|---|---|
| Fallback quote cannot become executable | Prevents fake edge from non-live quote data | Fake executable trades, false confidence, bad fills | fallback_used true blocked; quote_source REST_FALLBACK blocked; recovered_fallback blocked; clean live quote still executable | behavior, sa-fety, regression, edge |
| Stale feed blocks execution | Prevents trading from old market state | Entries on dead prices | stale LTP blocked; stale option quote blocked; stale depth blocked; fresh feed allows | behavior, safety, edge |
| Missing depth blocks selected option leg | Protects execution quality and fill realism | Slippage, bad entry, fake RR | missing depth blocks execution-grade entry; index-only depth relaxation does not apply to option leg | behavior, safety, edge |
| Missing option proof blocks execution | Prevents unknown option tradability | Wrong token/illiquid option execution | missing token blocked; stale option chain blocked; fallback option chain blocked | behavior, safety, edge |
| Manual approval boundary | Protects capital | Unapproved order action | no order path before approval; approval does not bypass stale/fallback/risk gates | safety, edge |
| Broker/network firewall in tests | Protects test determinism and live account | Real broker/API usage during QA | direct broker client blocked; websocket/network blocked unless fake | safety, broker_firewall |

## Priority 1: Candidate and Ranking Edge

| Feature / Contract | Edge Purpose | Risk If Missing | Required Behavior Tests | Suite |
|---|---|---|---|---|
| Candidate pool preserves all candidates | Enables diagnosis of lost edge | Hidden rejected candidates, no RCA | executable/advisory/rejected/debug buckets preserved | behavior, edge |
| Candidate pool quality detects concentration | Avoids overtrading same theme | Correlated losses | duplicate pool penalized; diverse pool preferred | behavior, edge |
| Directional balance | Avoids bullish-only bias | Missing PE/bearish opportunities | CE/PE both represented when evidence supports; skew warns not invents opposite side | behavior, edge |
| Ranking score separation | Prevents fake top opportunity | Weak top candidate shown as best | close scores not promoted as strong; separated score promoted if safe | behavior, edge |
| Expectancy-aware ranking | Selects profitable setups | Cosmetic confidence outranks real expectancy | positive net expectancy outranks unproven high confidence | behavior, edge |
| Regime-aware ranking | Prevents wrong-strategy-in-wrong-market | Breakout in chop/range losses | regime-aligned candidate outranks mismatch; mismatch cannot override safety | behavior, edge |

## Priority 2: No-Trade and Profitability Truth

| Feature / Contract | Edge Purpose | Risk If Missing | Required Behavior Tests | Suite |
|---|---|---|---|---|
| No-trade is valid decision | Stops bad trades | Forced trading in poor conditions | stale feed, chop, conflicts, weak confirmation trigger no-trade | behavior, edge |
| No-trade evidence | Speeds debugging and improvement | Unknown no-candidate sessions | primary reason, blockers, candidate counts, feed evidence | observability, edge |
| Cost-adjusted profitability | Prevents fake returns | Gross edge hides slippage/cost | net R below gross R; high costs can flip positive gross to negative net | behavior, edge |
| Baseline comparison | Prevents strategy self-deception | Strategy appears good without benchmark | high bucket must outperform mid/baseline | regression, edge |
| Paper truth journal | Preserves learning truth | Tampered or fake paper outcomes | hash chain, sequence integrity, reducer truth | replay, edge |

## Priority 3: Dashboard / Read-Model Truth

| Feature / Contract | Edge Purpose | Risk If Missing | Required Behavior Tests | Suite |
|---|---|---|---|---|
| Top opportunities use ranked snapshot | Prevents UI from lying | Raw rows shown as real opportunities | dashboard reads top opportunity snapshot for ranked views | ui_read_model, edge |
| Exec-only table filters correctly | Protects manual decision quality | Advisory rows shown as executable | fallback/advisory/debug rows excluded | ui_read_model, edge |
| Stale snapshot visibility | Prevents acting on old evidence | User trusts stale UI | stale artifacts shown stale, not fresh | ui_read_model, edge |
| Raw rows stay debug-only | Preserves evidence without fake promotion | Debug rows become trade ideas | raw rows visible only in all-candidates/debug view | ui_read_model, edge |

## Priority 4: Replay and Chaos

| Feature / Contract | Edge Purpose | Risk If Missing | Required Behavior Tests | Suite |
|---|---|---|---|---|
| Replay no future leak | Prevents fake backtest edge | Unrealistic profitability | future snapshot/candle access blocked | replay, edge |
| Replay read-only | Protects runtime and live state | Replay mutates live evidence | no broker/order/live append flags | replay, safety |
| Corrupt runtime artifacts | Prevents false OK state | Broken files silently accepted | invalid JSON/missing keys fail closed | chaos, safety |
| Bad market data | Prevents invalid signal generation | NaN/negative/impossible prices | ask below bid, negative LTP, missing timestamps blocked | chaos, edge |

## Matrix Rule

Every new PR must add or update at least one row in this matrix when it changes product behavior.
