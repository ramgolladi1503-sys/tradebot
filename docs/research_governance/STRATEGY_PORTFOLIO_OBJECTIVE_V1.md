# TradeBot Strategy Portfolio Objective V1

Status: **DRAFT GOVERNANCE PROPOSAL**

This document is the canonical statement of **what TradeBot strategy research is trying to build**.

It exists to prevent research drift. Future prompts, campaigns, agents, backtests, Atlas work, Edge Factory work, option-translation work, and live signal orchestration must not reinterpret the objective into a narrower problem.

The governing principle is:

> **Build a portfolio of independently defensible intraday strategies. Strategy frequency is a property of the evidence, not a requirement.**

This document is subordinate to the scientific safeguards in `EDGE_FACTORY_TRUTH_LAYER_V1.md`; it does not weaken any research gate.

## 1. Canonical objective

TradeBot is not searching for one universal strategy.

It is not searching for a strategy that must trade every day.

It is not searching only for rare setups.

It is not searching only for high-frequency setups.

It is not restricted to 5–15 minute holding periods.

The objective is to discover, validate, and accumulate **multiple independently defensible intraday strategies** whose eligibility conditions are observable causally before entry.

A valid strategy may be:

- frequent;
- moderately frequent;
- rare.

Frequency alone is neither a reason to accept nor reject a strategy.

A rare setup is acceptable if it has sufficient support and unusually strong, robust conditional evidence.

A frequent setup is equally acceptable if it survives the same standards.

## 2. Intraday means intraday, not short-horizon scalp

The hard temporal boundary is:

```text
entry = during the trading session
exit = during the same trading session
overnight holding = forbidden
```

There is no universal fixed maximum hold such as 5, 15, or 30 minutes.

A certified strategy may legitimately hold for:

```text
5 minutes
20 minutes
75 minutes
multiple hours
most of the trading session
```

when that duration follows from the pre-registered mechanism and causal exit logic.

Each strategy must define its own:

- eligibility state;
- entry rule;
- exit rule;
- invalidation rule;
- risk rule;
- required data authority.

Exit logic must be causal and frozen before protected evaluation. Holding time may not be optimized after seeing protected outcomes.

## 3. Live portfolio behavior

The eventual live architecture evaluates **all certified strategies** against the current market state.

```text
                    LIVE MARKET
                        |
                 STATE DETECTION
                        |
        +---------------+---------------+
        |               |               |
   Strategy A       Strategy B      Strategy C ...
   eligible?        eligible?       eligible?
        |               |               |
      yes/no           yes/no          yes/no
        +---------------+---------------+
                        |
                CANDIDATE SIGNALS
                        |
        overlap / independence / risk
                 portfolio arbitration
                        |
                 manual approval
                        |
                 TRADE / NO TRADE
```

Possible outcomes on any session include:

```text
0 candidate strategies -> NO TRADE
1 candidate strategy   -> one candidate trade
multiple strategies    -> portfolio/risk arbitration
```

`NO TRADE` is a valid and expected result.

TradeBot must never create a strategy merely to fill a day with no qualifying setup.

## 4. Portfolio size is discovered, not predeclared

There is no fixed required number of final strategies.

Numbers such as 3, 10, or 12 may be useful planning references, but they are not certification targets.

If six genuinely independent strategies survive, the portfolio has six.

If fourteen genuinely independent strategies survive, the portfolio may have fourteen.

If only two survive, the system must report two rather than weaken standards to reach a quota.

The research program may continue with future outcome-blind campaigns when scientifically justified, but search pressure and prior trials remain cumulative.

## 5. Frequency is descriptive, not prescriptive

Do not impose a universal annual trade-count target.

Examples that can all be acceptable:

```text
Strategy A: 100 eligible sessions/year
Strategy B: 55 eligible sessions/year
Strategy C: 27 eligible sessions/year
Strategy D: 20 eligible sessions/year
```

What matters is whether each setup has enough effective observations to support the claim being made.

Minimum support must be justified and predeclared from:

- historical coverage;
- effect size;
- statistical power;
- data quality;
- chronological independence;
- multiplicity/search pressure.

Do not invent a fixed minimum such as `25 sessions/year` simply because it sounds reasonable.

## 6. Conditional opportunity discovery

The primary research question is:

> **What observable market state changes the conditional future distribution enough to create a robust intraday opportunity?**

The system should search for conditional opportunity, not universal prediction.

Examples of mechanism classes may include, when supported by authoritative data:

- participation / breadth;
- concentration / equal-weight divergence;
- volatility transition;
- opening dislocation;
- failed trend / reversal;
- sector leadership or concentration;
- cross-sectional dispersion;
- afternoon state transition;
- event-conditioned structures;
- option microstructure and tradability.

These are examples, not a permanent family list.

The truth layer freezes the scientific process, not the mechanisms that future outcome-blind discovery may propose.

## 7. Strength, not rarity

Research must not prefer a strategy because it is rare.

Research must not prefer a strategy because it is frequent.

The required question is:

```text
Does the causally observable eligibility state produce
a sufficiently strong, stable, incremental and tradable
conditional effect after appropriate costs and delays?
```

A strong rare strategy and a strong frequent strategy are both desirable.

## 8. Independent strategies, not cosmetic variants

A portfolio is not diversified merely because strategies have different names.

The research stack must measure:

- eligible-session overlap;
- signal overlap;
- direction overlap;
- return/P&L correlation where legitimate;
- loss correlation;
- mechanism overlap;
- shared feature dependence;
- shared regime dependence.

Two variants such as:

```text
MACD-12
MACD-14
```

must not be counted as independent simply because parameter values differ.

Likewise, two strategies firing on the same sessions for the same economic mechanism must be clustered unless independence is demonstrated.

## 9. Unique opportunity coverage

Portfolio coverage is measured using the **union of qualifying sessions**, not the sum of strategy counts.

If:

```text
A = 60 eligible sessions
B = 55
C = 40
D = 35
```

then `190` is not automatically `190` distinct trading opportunities.

The system must calculate:

```text
unique qualifying sessions
pairwise and higher-order overlap
simultaneous-candidate frequency
```

Coverage is useful, but it is secondary to robustness.

The objective is:

> **maximize coverage of defendable opportunities**

not:

> maximize the number of days on which TradeBot emits any trade.

## 10. No coverage pressure

The following behavior is forbidden:

```text
"Too many no-trade days remain, so invent another strategy."
```

A blank day contains no obligation to trade.

New research must originate from an independently justified mechanism and a fresh outcome-blind catalog, not dissatisfaction with portfolio coverage.

## 11. Required strategy evidence

Before a strategy can enter the certified portfolio, it must satisfy all applicable truth-layer controls, including:

- causal data availability;
- explicit mechanism;
- pre-registered eligibility and hypotheses;
- chronological formation/validation;
- same-metric baseline comparison;
- effect-size requirement;
- multiplicity/global search accounting;
- WFA or equivalent chronological stability analysis;
- delay/actionability;
- negative controls;
- concentration checks;
- protected confirmation where authorized;
- independent verification/oracle where applicable;
- realistic cost/execution evidence appropriate to the instrument;
- portfolio-independence assessment.

A research survivor is not automatically execution authority.

## 12. Underlying edge vs option trade

TradeBot must keep separate:

```text
MARKET PHENOMENON
        |
PREDICTIVE / CONDITIONAL INFORMATION
        |
STRATEGY LOGIC
        |
OPTION TRANSLATION
        |
EXECUTION VIABILITY
```

A useful underlying-market signal can still fail as an option strategy because of spread, slippage, IV behavior, decay, or insufficient move magnitude.

Do not promote underlying predictability into an execution-grade option strategy without supporting evidence.

## 13. Portfolio success dimensions

TradeBot portfolio quality is judged by:

```text
ROBUSTNESS
NET EXPECTANCY
MECHANISM INDEPENDENCE
UNIQUE OPPORTUNITY COVERAGE
REGIME DIVERSITY
EXECUTION VIABILITY
```

It is **not** judged by:

```text
trades every day
a fixed strategy count
rarity
frequency alone
maximum backtest win rate
maximum in-sample Sharpe
```

## 14. Runtime authority boundary

The eventual live system may evaluate certified strategies and emit candidate trades, but the current governance boundary remains:

```text
read_only_market_research=true
broker_write_authority=false
order_authority=false
allowed_for_live_execution=false
manual_approval_required=true
buy_only=true
intraday_only=true
overnight_positions_allowed=false
```

Multiple strategies may qualify simultaneously.

A portfolio/risk arbitration layer must decide which candidate exposure is admissible before manual approval.

## 15. Anti-drift interpretations

Future agents must not reinterpret this objective as any of the following:

```text
"User wants only rare strategies."
"User wants a strategy every day."
"Every strategy must trade 20–30 times per year."
"Every strategy must trade at least 25 sessions per year."
"Every strategy must hold 5–15 minutes."
"Every strategy must hold <=30 minutes."
"We need exactly 3 survivors."
"We need exactly 10–12 strategies."
"We should add strategies until every trading day is covered."
```

All of those are incorrect.

The correct interpretation is:

> **Find strong, independently defensible intraday strategies wherever they exist; allow frequent, moderate, or rare eligibility; accumulate independent survivors into a portfolio; evaluate every certified strategy against the live market state; emit candidate trades only when eligibility is satisfied; and accept NO TRADE whenever none qualifies.**

## 16. Relationship to the Edge Factory truth layer

`EDGE_FACTORY_TRUTH_LAYER_V1.md` governs **how** evidence is generated and protected.

This document governs **what portfolio objective** that process serves.

Neither may be weakened merely because:

- too few strategies survive;
- too many sessions produce no trade;
- a desired annual opportunity count is not reached;
- a promising backtest fails protected validation.

Research standards remain stronger than portfolio coverage goals.

## 17. Change control

This objective is a governance artifact.

Semantic changes require:

1. explicit rationale unrelated to a specific strategy's performance;
2. governance review;
3. corresponding machine-readable contract update;
4. updated pinned checker/tests;
5. preservation of prior search history.

Ordinary strategy PRs may not silently redefine the portfolio objective.
