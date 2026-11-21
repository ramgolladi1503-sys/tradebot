# Work Item: FEAT-SENTINEL-MICROSTRUCTURE-SUITE-003

## Identity

- Work Item ID: FEAT-SENTINEL-MICROSTRUCTURE-SUITE-003
- Type: FEATURE
- Parent Epic: EPIC-SENTINEL-REGIME-SUPERVISORY
- Parent Feature: FEAT-SENTINEL-STRUCTURAL-GATES-002
- Title: Sentinel Real-Time CVD Absorption & Dealer GEX Regime Engine
- Current State: READY_FOR_ARCHITECTURE
- Priority: HIGH

---

## Business Goal

TradeBot execution algorithms and directional strategy modules across index and equity derivatives frequently suffer adverse selection when entering breakouts or trend continuation trades during hidden institutional passive limit order absorption or hostile dealer gamma regimes.

The business goal is to establish a deterministic, scale-invariant, real-time microstructure supervisory engine within `core/market_structure/sentinel_microstructure.py`:
1. **Cumulative Volume Delta (CVD) Tracking & Passive Absorption Divergence**: Detect when aggressive market orders are absorbed by passive liquidity providers (e.g. spot price making new local highs while cumulative volume delta stagnates or diverges negatively), producing an immediate `ABSORPTION_VETO` to prevent buying into institutional distribution or selling into accumulation.
2. **Dealer Gamma Exposure (GEX) Regime Classification**: Aggregate strike-level open interest and option gamma to determine net dealer gamma positioning:
   - `POSITIVE_GAMMA`: Dealers are long gamma; dynamic hedging requires selling strength and buying weakness, inducing mean-reverting/sticky volatility. Directional breakouts are faded/vetoed.
   - `NEGATIVE_GAMMA`: Dealers are short gamma; dynamic hedging accelerates price movement (buying rallies, selling selloffs), inducing slippery volatility and high-velocity squeeze mechanics. Trend continuation is permitted.
   - `NEUTRAL_GAMMA`: Dealers near gamma flip / neutral threshold; standard auction dynamics apply.
3. **Top-of-Book Bid-Ask Spread Crossing Verification**: Monitor real-time top-of-book bid-ask spread in basis points. If spread exceeds configured risk thresholds (`spread_bps > max_spread_bps`), issue `SPREAD_CROSSING_VETO` to eliminate execution slippage and toxic liquidity crossings.

This feature serves as a purely read-only supervisory filter protecting trade generation from microstructural traps, illiquidity shocks, and adverse gamma friction.

---

## Current Behavior

1. **Blind Breakout Execution into Passive Absorption**: Strategies evaluate price breakout signals without visibility into whether aggressive buy volume is failing to move price due to massive resting ask depth (passive limit absorption). Strategies enter long at top-of-book right before price mean-reverts sharply.
2. **Absence of Dealer Gamma Regime Context**: Strategies execute identical breakout or momentum logic regardless of whether the index is pinned in an ultra-high positive gamma trap (where market makers act as volatility shock absorbers) or in negative gamma (where market makers accelerate trends). This leads to repeated stop-outs in sticky/positive gamma environments.
3. **Unchecked Spread Crossing Costs**: Execution logic frequently evaluates signals during micro-structure liquidity voids where the bid-ask spread widens dramatically, causing adverse execution cost drag and slippage.
4. **Lack of Isolated Microstructure Contracts**: Microstructure logic is either fragmented across ad-hoc scripts or missing formal dataclasses and invariant assertions.

---

## Expected Behavior

1. **Real-Time Cumulative Volume Delta (CVD) & Absorption Detection Engine**:
   - Ingest tick or bar-level traded volume segregated by buy/sell aggressor side (or trade classification via tick rule / quote rule):
     $$\Delta V_t = V_{buy, t} - V_{sell, t}, \quad CVD_t = \sum_{\tau=0}^t \Delta V_\tau$$
   - Evaluate multi-bar price vs. CVD slope and divergence over configurable lookback window $W$:
     - If Spot Price reaches a new local maximum ($S_t \ge \max_{k \in [1, W]} S_{t-k}$) while $CVD_t$ displays negative or stagnant delta ($\Delta CVD_W \le 0$ or significant negative divergence $\frac{d(CVD)}{dt} < 0$), classify as `BULLISH_EXHAUSTION_ABSORPTION` and emit `ABSORPTION_VETO` against long entries.
     - Symmetrically, if Spot Price reaches a new local minimum while $CVD_t$ displays positive or rising delta ($\Delta CVD_W \ge 0$), classify as `BEARISH_EXHAUSTION_ABSORPTION` and emit `ABSORPTION_VETO` against short entries.
2. **Dealer Gamma Exposure (GEX) Regime Classifier**:
   - Ingest option chain strike metrics (Call OI, Put OI, Spot Price, Implied Volatility, DTE) and compute aggregate net dealer gamma exposure:
     $$GEX = \sum_i \Gamma_i \times S^2 \times (OI_{call, i} - OI_{put, i}) \times \text{multiplier}$$
   - Classify regime based on normalized GEX ratio relative to daily volume/notional baseline:
     - `POSITIVE_GAMMA`: Net dealer gamma above positive threshold ($\theta_{gex}^+$). Price expected to be mean-reverting, pinned, and sticky. Momentum continuation signals are gated/vetoed.
     - `NEGATIVE_GAMMA`: Net dealer gamma below negative threshold ($\theta_{gex}^-$). Dealers amplify moves through pro-cyclical hedging. Trend continuation and volatility breakout strategies authorized.
     - `NEUTRAL_GAMMA`: GEX within $[-\theta_{gex}^-, \theta_{gex}^+]$. Unconstrained order flow dynamics.
3. **Top-of-Book Spread Threshold Verification**:
   - Ingest instantaneous best bid ($P_{bid}$) and best ask ($P_{ask}$):
     $$Spread_{bps} = \frac{P_{ask} - P_{bid}}{(P_{ask} + P_{bid}) / 2} \times 10,000$$
   - If $Spread_{bps} > max\_spread\_bps$, immediately trigger `SPREAD_CROSSING_VETO`, halting new entry generation and protecting against crossing toxic/wide spreads.
4. **Deterministic Supervisory Output Contract**:
   - Returns immutable frozen dataclass `SentinelMicrostructureDecision` containing:
     - `cvd_state`: `CVDState` (e.g. `NORMAL`, `BULLISH_ABSORPTION`, `BEARISH_ABSORPTION`)
     - `gex_regime`: `GEXRegime` (`POSITIVE_GAMMA`, `NEGATIVE_GAMMA`, `NEUTRAL_GAMMA`)
     - `spread_bps`: float
     - `is_absorption_vetoed`: bool
     - `is_spread_vetoed`: bool
     - `is_entry_permitted`: bool
     - `audit_metadata`: dict
   - Fully fails closed on missing, invalid, or corrupted input feeds.

---

## In Scope

- `core/market_structure/sentinel_microstructure.py`:
  - Core dataclasses: `MicrostructureSnapshot`, `CVDState`, `GEXRegime`, `SentinelMicrostructureDecision`.
  - Microstructure evaluation engine: `SentinelMicrostructureEngine`.
  - Strict input validation, zero-division guards, scale invariance, and fail-closed error handling.
- `tests/unit/test_sentinel_microstructure.py`:
  - Unit tests covering happy path, absorption divergence, positive/negative/neutral GEX, wide spread veto, boundary cases, corrupt inputs, and safety invariant declarations.

---

## Out of Scope

- Order placement, order routing, broker APIs, live network sockets, or execution pipeline modifications.
- Modifications to core execution engines, strategies, or risk management modules.
- Runtime wiring in `main.py` or `run_live.sh`.
- Live websocket streaming connections (evaluation operates purely on injected snapshot data).

---

## Dependencies

- Python standard library (`dataclasses`, `typing`, `math`, `enum`).
- `pytest` for test execution.
- Existing core market structure conventions if applicable.

---

## Requirement Traceability

| Requirement ID | Requirement | Source | Acceptance Criterion |
|---|---|---|---|
| REQ-MICRO-001 | Real-time CVD tracking and passive absorption detection | Business Analysis / Quant | AC-001, AC-002 |
| REQ-MICRO-002 | Net Dealer Gamma Exposure (GEX) regime classification | Business Analysis / Quant | AC-003, AC-004 |
| REQ-MICRO-003 | Top-of-book bid-ask spread threshold verification | Business Analysis / Execution Risk | AC-005 |
| REQ-MICRO-004 | Comprehensive supervisory veto aggregation and decision contract | Architecture / Safety | AC-006 |
| REQ-MICRO-005 | Strict fail-closed safety invariants and pure read-only semantics | TradeBot Agent Rules | AC-007 |

---

## Safety / Risk Constraints

- **Broker/order impact**: Zero. No orders placed, modified, or canceled.
- **LIVE/PAPER/SIM impact**: Completely isolated read-only evaluation. No execution side effects.
- **Risk-gate impact**: Does not weaken any risk gate; provides additional supervisory vetoes.
- **Feed-freshness impact**: Fails closed if feed timestamps or metrics are stale, negative, or NaN.
- **Data/evidence impact**: Frozen immutable output dataclasses with reproducible audit metadata.
- **Required human approval**: N/A for pure read-only module implementation; explicit human approval required prior to any future live runtime wiring.

Explicit Safety Declarations:
```python
read_only = True
is_order_action = False
broker_api_called = False
allowed_for_live_execution = False
```

---

## Architecture Impact

- **Components touched**:
  - `core/market_structure/sentinel_microstructure.py` (New component)
  - `tests/unit/test_sentinel_microstructure.py` (New component)
- **Interfaces/contracts affected**: None modified. Introduces `SentinelMicrostructureDecision` contract.
- **Existing infrastructure reused**: Follows `core/market_structure` conventions established in `sentinel_structural_gates.py`.
- **New infrastructure required and why**: Real-time CVD and GEX regime classifier required to provide supervisory microstructure vetoes to TradeBot strategies.
- **High-risk paths touched**: None. Strict prohibition on all high-risk paths.

---

## Acceptance Criteria

### Scenario 1: Cumulative Volume Delta Absorption Veto (Bullish Exhaustion)
```gherkin
Given a series of market bars over lookback window W
When the spot price achieves a new local high (price_current >= max_window_price)
And cumulative volume delta exhibits stagnation or negative divergence (cvd_delta <= 0)
Then the engine shall classify cvd_state as BULLISH_ABSORPTION
And set is_absorption_vetoed to True
And set is_entry_permitted to False for bullish entries
And populate audit_metadata with divergence metrics
```

### Scenario 2: Cumulative Volume Delta Absorption Veto (Bearish Exhaustion)
```gherkin
Given a series of market bars over lookback window W
When the spot price achieves a new local low (price_current <= min_window_price)
And cumulative volume delta exhibits positive accumulation divergence (cvd_delta >= 0)
Then the engine shall classify cvd_state as BEARISH_ABSORPTION
And set is_absorption_vetoed to True
And set is_entry_permitted to False for bearish entries
And populate audit_metadata with divergence metrics
```

### Scenario 3: Dealer GEX Regime Classification - Positive Gamma (Mean-Reverting)
```gherkin
Given an option chain snapshot with aggregate Call OI, Put OI, and strike gammas
When aggregate Net Dealer GEX exceeds positive threshold (gex_value >= positive_gex_threshold)
Then the engine shall classify gex_regime as POSITIVE_GAMMA
And flag directional breakout strategies as high-friction/vetoed
And record the GEX ratio in the decision metadata
```

### Scenario 4: Dealer GEX Regime Classification - Negative Gamma (High Volatility Squeeze)
```gherkin
Given an option chain snapshot with aggregate Call OI, Put OI, and strike gammas
When aggregate Net Dealer GEX drops below negative threshold (gex_value <= negative_gex_threshold)
Then the engine shall classify gex_regime as NEGATIVE_GAMMA
And permit trend continuation / momentum breakout signals
And record the GEX ratio in the decision metadata
```

### Scenario 5: Top-of-Book Bid-Ask Spread Crossing Veto
```gherkin
Given a top-of-book market quote with best_bid and best_ask
When the calculated spread in basis points exceeds max_spread_bps (e.g. 5.0 bps)
Then the engine shall set is_spread_vetoed to True
And set is_entry_permitted to False
And declare SPREAD_CROSSING_VETO in the decision reasons
```

### Scenario 6: Combined Supervisory Decision Hierarchy
```gherkin
Given incoming market microstructure snapshot
When both CVD and spread thresholds are within permissible bounds and GEX is NEUTRAL_GAMMA or NEGATIVE_GAMMA
Then the engine shall return is_entry_permitted as True
And set is_absorption_vetoed to False and is_spread_vetoed to False
```

### Scenario 7: Fail-Closed on Corrupt or Missing Data
```gherkin
Given an invalid snapshot (e.g. negative prices, NaN spread, best_bid >= best_ask, or empty history)
When the microstructure engine evaluates the snapshot
Then the engine shall fail closed by setting is_entry_permitted to False
And record the validation error in audit_metadata without raising unhandled exceptions
And declare safety properties: read_only=True, is_order_action=False, broker_api_called=False, allowed_for_live_execution=False
```

---

## Development Plan

- **Allowed paths**:
  - `core/market_structure/sentinel_microstructure.py`
  - `tests/unit/test_sentinel_microstructure.py`
  - `docs/tradebot_delivery/work_items/FEAT-SENTINEL-MICROSTRUCTURE-SUITE-003.md`
- **Forbidden paths**:
  - `main.py`
  - `run_live.sh`
  - `core/execution*`
  - `core/broker*`
  - `core/order*`
  - `core/risk*`
  - `config/`
  - `credentials.py`
  - `.env`
- **Expected implementation**:
  - Pure Python, zero-side-effect immutable classes and functions.
  - Scale-invariant calculations (basis points, standardized z-scores, percentage ratios).
  - Explicit enum definitions for `CVDState` and `GEXRegime`.
  - Comprehensive logging and defensive bounds checking.
- **Required developer tests**:
  - `test_cvd_bullish_absorption_divergence`
  - `test_cvd_bearish_absorption_divergence`
  - `test_cvd_normal_flow_permitted`
  - `test_gex_regime_classification_positive_gamma`
  - `test_gex_regime_classification_negative_gamma`
  - `test_gex_regime_classification_neutral_gamma`
  - `test_spread_threshold_veto`
  - `test_spread_within_limits_permitted`
  - `test_fail_closed_on_corrupt_or_inverted_book`
  - `test_fail_closed_on_empty_or_nan_data`
  - `test_safety_declarations_and_immutability`

---

## QA Attack Plan

- **Happy path**:
  - Valid orderly market with normal CVD, neutral GEX, tight 1.5 bps spread -> `is_entry_permitted=True`.
- **Negative path**:
  - Price new high with plunging CVD -> `ABSORPTION_VETO` issued.
  - Bid-ask spread at 12 bps (exceeding 5 bps threshold) -> `SPREAD_CROSSING_VETO` issued.
- **Boundary conditions**:
  - Price exactly at window max with zero delta change ($\Delta CVD = 0$).
  - Spread exactly equal to `max_spread_bps`.
  - GEX exactly on threshold boundary $\theta_{gex}^+$.
- **Stale/missing/corrupt data**:
  - Inverted book (`best_bid > best_ask`).
  - Zero or negative prices.
  - Empty CVD history or insufficient lookback bars.
  - NaNs, infinite values, or null fields in option chain / quotes.
- **State-transition failures**:
  - Transitions between Positive Gamma and Negative Gamma regimes across consecutive snapshots.
- **Regression targets**:
  - Verify that no existing imports or modules in `core/` are disrupted.
  - Verify zero broker/order dependencies.

---

## UAT Criteria

- Verified that `SentinelMicrostructureEngine` correctly filters simulated adverse order flow snapshots.
- Verified that all unit tests in `tests/unit/test_sentinel_microstructure.py` pass with 100% assertions green.
- Confirmed that output dataclasses are frozen and immutable.
- Confirmed that no forbidden files are modified.

---

## Release Gates

- [x] Requirements traceable
- [ ] Architecture approved
- [ ] DEV_VERIFIED
- [ ] QA_PASSED
- [ ] SENIOR_QA passed
- [ ] UAT passed
- [ ] PRODUCT_ACCEPTED
- [ ] CI_GREEN
- [x] Rollback/limitations documented

---

## Rollback Plan

If regressions or numerical anomalies are detected:
1. Revert `core/market_structure/sentinel_microstructure.py` and `tests/unit/test_sentinel_microstructure.py`.
2. As the module is pure supervisory and not yet wired into live execution, deletion or rollback has zero runtime broker impact.
