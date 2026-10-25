# Work Item: FEAT-SENTINEL-STRUCTURAL-GATES-002

## Identity

- Work Item ID: FEAT-SENTINEL-STRUCTURAL-GATES-002
- Type: FEATURE
- Parent Epic: EPIC-SENTINEL-REGIME-SUPERVISORY
- Parent Feature: FEAT-SENTINEL-DIURNAL-SESSION-001
- Title: Sentinel Scale-Invariant Structural Market Gates (Omega_15 Shock Compression, Auction PDH/PDL Traps, Gamma Wall Proximity)
- Current State: PRODUCT_ACCEPTED
- Priority: HIGH

---

## Business Goal

TradeBot execution across index derivatives (Nifty, BankNifty, FinNifty, Sensex) frequently encounters structural market traps when signals rely on raw point moves, fixed stop-loss distances, or static thresholds. Static point parameters fail across varying volatility regimes (e.g., VIX 11 vs VIX 24) and index level re-baselines.

The business goal is to establish three mathematically validated, strictly scale-invariant supervisory structural gates within the Sentinel regime stack:
1. **Opening Shock Volatility Compression Ratio ($\Omega_{15}$)**: Distinguishes true directional expansion days from high-probability mean-reverting chop sessions by standardizing 15-minute Opening Range ($OR_{15}$) by 20-day Daily ATR ($ATR_{20}(T-1)$).
2. **Prior-Day Boundary Auction State (Acceptance vs. Failed Auction Trap)**: Classifies order flow interactions at Prior Day High / Low ($PDH / PDL$) into auction acceptance versus liquidity sweep traps using cumulative delta volume rejection and re-entry velocity.
3. **Normalized Gamma Strike Wall Proximity ($d_{norm}$)**: Computes volatility-normalized, time-decay-adjusted strike distance to dominant Call/Put Open Interest Gamma walls ($K_{wall}$), incorporating an empirical Wall Vulnerability Ratio to prevent blind breakout buying into pin risk or selling into gamma elasticity.

These gates act as pure supervisory filters, protecting capital and eliminating structural adverse selection across all market environments.

---

## Current Behavior

1. **Opening Range Breakout Distortion**: Strategies evaluate early morning moves using unnormalized price ticks or static point thresholds. A 50-point Nifty opening range is treated identically whether daily volatility is 80 points or 250 points, causing repeated stop-outs on low-volatility compression days and late entries on explosive shock days.
2. **Naive Boundary Breakouts**: Breakouts beyond $PDH$ or $PDL$ are evaluated naively on price exceedance without auction order flow confirmation (delta volume exhaustion or absorption), resulting in execution directly into institutional liquidity sweeps (Failed Auction Traps).
3. **Static Gamma / Strike Boundaries**: Derivative strategies do not normalize proximity to dominant options open-interest strike walls by instantaneous implied volatility and time to expiry ($DTE$). A strike 50 points away on 0-DTE represents an insurmountable barrier, whereas 50 points on 7-DTE is negligible noise.
4. **Lack of Scale Invariance**: Code containing hardcoded index point values (`points > 30`, `diff > 50`) breaks when applied across different indices (Nifty vs BankNifty vs Sensex) or across macro volatility shifts.

---

## Expected Behavior

1. **Scale-Invariant Opening Shock Compression Gate ($\Omega_{15}$)**:
   - Evaluates:
     $$\Omega_{15} = \frac{OR_{15}}{ATR_{20}(T-1)} = \frac{\max(H_{09:15-09:30}) - \min(L_{09:15-09:30})}{ATR_{20}(T-1)}$$
   - Classifies structural state into:
     - `COMPRESSED_COIL`: $\Omega_{15} < \theta_{comp}$ (typically $< 0.25$) $\rightarrow$ Extreme energy coil; breakout expansion favored, tight range scalps suppressed.
     - `NORMAL_EQUILIBRIUM`: $\theta_{comp} \le \Omega_{15} \le \theta_{exp}$ (typically $0.25 \le \Omega_{15} \le 0.55$) $\rightarrow$ Standard session auction mechanics.
     - `EXHAUSTION_SHOCK`: $\Omega_{15} > \theta_{exp}$ (typically $> 0.55$) $\rightarrow$ Opening shock has consumed a majority of expected daily range; trend-chasing entries gated, mean-reversion favored.
   - Enforces zero hardcoded points; strictly dimensionless ratio.

2. **Prior-Day Boundary Auction State Gate**:
   - Monitors price excursions beyond $PDH$ and $PDL$:
     $$\Delta_{PDH}(t) = S_t - PDH, \quad \Delta_{PDL}(t) = PDL - S_t$$
   - Evaluates Auction State using Delta Volume Rejection Ratio ($\mathcal{R}_{\delta}$) and Bar Re-entry:
     $$\mathcal{R}_{\delta} = \frac{\Delta V_{breakout}}{\overline{V}_{advancing}}$$
   - Classifies into:
     - `FAILED_AUCTION_TRAP`: Price exceeds boundary by $\le 0.15 \times ATR_{20}$ but volume delta shows divergence/rejection, immediately returning inside prior-day range within $N$ bars $\rightarrow$ Gated against trend continuation; signals liquidity sweep reversal.
     - `AUCTION_ACCEPTANCE`: Price exceeds boundary with sustaining positive delta order flow and bar closes outside prior range for $M \ge 2$ consecutive bars $\rightarrow$ Trend continuation authorized.
     - `IN_VALUE_AUCTION`: Price remains bounded between $PDL$ and $PDH$.

3. **Normalized Gamma Strike Wall Proximity Gate ($d_{norm}$)**:
   - Computes volatility- and expiry-standardized distance:
     $$d_{norm} = \frac{|S_t - K_{wall}|}{\sigma_{imp} \cdot S_t \cdot \sqrt{DTE / 365}}$$
     where $S_t$ is underlying spot, $K_{wall}$ is dominant open-interest strike, $\sigma_{imp}$ is annualized implied volatility (or 20-day realized volatility if IV unavailable), and $DTE$ is days to expiration (continuous trading-day fraction, min bounded to $0.5 / 365$).
   - Calculates Wall Vulnerability Ratio ($WVR$):
     $$WVR = \frac{OI_{decay\_rate} + \Delta OI_{unwind}}{OI_{total\_wall}}$$
   - Classifies proximity:
     - `PIN_RISK_BARRIER`: $d_{norm} < 0.35$ and $WVR < 0.20$ $\rightarrow$ Strike wall acting as hard reflective ceiling/floor; breakouts blocked, pin/reversal authorized.
     - `WALL_BREAKTHROUGH_VULNERABLE`: $d_{norm} < 0.35$ and $WVR \ge 0.50$ $\rightarrow$ Strike wall decaying/unwinding under gamma squeeze; aggressive breakout authorized.
     - `UNCONSTRAINED_FLOW`: $d_{norm} \ge 0.70$ $\rightarrow$ Underlying free from gamma strike pinning effects.

4. **Fail-Closed Safety Invariants**:
   - Zero runtime broker imports or execution side-effects.
   - All evaluators operate purely on read-only immutable input snapshots and output frozen dataclasses.
   - Any missing historical ATR, corrupted feed, or negative volatility instantly fails closed:
     ```python
     read_only = True
     is_order_action = False
     broker_api_called = False
     allowed_for_live_execution = False
     ```

---

## In Scope

- Creation of pure market structure gate modules in `core/market_structure/`:
  - `sentinel_volatility_compression.py`: Implementation of $\Omega_{15}$ Opening Shock Compression evaluator.
  - `sentinel_auction_boundary.py`: Implementation of Prior-Day Boundary Auction State (Acceptance vs Failed Trap) evaluator.
  - `sentinel_gamma_wall.py`: Implementation of Normalized Gamma Strike Wall Proximity ($d_{norm}$) and Vulnerability evaluator.
  - `sentinel_composite_gate.py`: Coordinated composite gate unifying Diurnal, Compression, Auction, and Gamma wall constraints.
- Exhaustive unit tests and property-based test suites in `tests/unit/market_structure/`:
  - Mathematical correctness tests for scale invariance (scaling price from 20,000 to 50,000 yields identical dimensionless ratios).
  - Division-by-zero, extreme volatility ($\sigma \to 0$ or $\sigma \to \infty$), zero $DTE$ edge-case defenses.
  - Boundary rejection volume delta state machine tests.
- Work item and delivery documentation following TradeBot permanent delivery rules.

---

## Out of Scope

- Modifying core strategy signal generation thresholds in `strategies/`.
- Direct broker order routing, placement, modification, or cancellation (`core/execution*`, `core/broker*`, `core/order*`).
- Live trading runtime activation (`run_live.sh`, `main.py`).
- Risk parameter alteration (`core/risk*`).
- Modification of persistent database schemas or credentials.

---

## Dependencies

- Python 3.10+ (`dataclasses`, `enum`, `math`, `datetime`, `typing`).
- `core.market_structure.sentinel_diurnal_regime` (from `FEAT-SENTINEL-DIURNAL-SESSION-001`).
- Pytest testing framework.

---

## Requirement Traceability

| Requirement ID | Requirement Description | Source | Acceptance Criterion |
|---|---|---|---|
| REQ-SENTINEL-002-1 | Scale-invariant Opening Shock Compression Ratio ($\Omega_{15} = OR_{15} / ATR_{20}(T-1)$) with zero hardcoded point thresholds. | PO / User Specification | AC-002-1 |
| REQ-SENTINEL-002-2 | Opening Shock regime classification (`COMPRESSED_COIL`, `NORMAL_EQUILIBRIUM`, `EXHAUSTION_SHOCK`) with fail-closed missing ATR handling. | PO / User Specification | AC-002-2 |
| REQ-SENTINEL-002-3 | Prior-Day Boundary Auction State detection classifying excursions beyond $PDH$/$PDL$ into `FAILED_AUCTION_TRAP` vs `AUCTION_ACCEPTANCE`. | PO / User Specification | AC-002-3 |
| REQ-SENTINEL-002-4 | Volume delta rejection confirmation ($\mathcal{R}_{\delta}$) preventing breakout false entries at boundary liquidity pools. | PO / User Specification | AC-002-4 |
| REQ-SENTINEL-002-5 | Normalized Gamma Strike Wall Proximity ($d_{norm} = |S_t - K| / (\sigma S_t \sqrt{DTE/365})$) standardizing distance across indices, IVs, and expirations. | PO / User Specification | AC-002-5 |
| REQ-SENTINEL-002-6 | Wall Vulnerability Ratio ($WVR$) distinguishing resilient gamma pin barriers from unwinding gamma squeeze breakouts. | PO / User Specification | AC-002-6 |
| REQ-SENTINEL-002-7 | Fail-closed immutable supervisory decision contracts guaranteeing `read_only=True`, `is_order_action=False`, `broker_api_called=False`, `allowed_for_live_execution=False`. | AGENTS.md / TradeBot Safety Rules | AC-002-7 |
| REQ-SENTINEL-002-8 | Zero runtime side-effects, zero order actions, complete mathematical test coverage under extreme/adversarial inputs. | TradeBot QA Playbook & Release Gates | AC-002-8 |

---

## Safety / Risk Constraints

- **Broker/order impact**: `is_order_action=False`, `broker_api_called=False`. No broker APIs imported or executed.
- **LIVE/PAPER/SIM impact**: `allowed_for_live_execution=False`. Gate operates purely as a supervisory calculation module.
- **Risk-gate impact**: `read_only=True`. Does not weaken, bypass, or alter existing risk gates or kill switches.
- **Feed-freshness impact**: Strict staleness checks; missing or stale market feeds immediately yield `BLOCKED` / `FAIL_CLOSED`.
- **Data/evidence impact**: Pure in-memory calculations; no unverified writes to disk or external persistence.
- **Required human approval**: Explicit human authorization required before any runtime wiring in live execution runners.

---

## Architecture Impact

- **Components touched**:
  - `core/market_structure/` (new modular gate contracts and evaluators).
- **Interfaces/contracts affected**:
  - Exposes `SentinelCompositeGateDecision`, `VolatilityCompressionDecision`, `AuctionBoundaryDecision`, `GammaWallDecision`.
- **Existing infrastructure reused**:
  - Reuses diurnal session concepts from `core.market_structure.sentinel_diurnal_regime`.
- **New infrastructure required and why**:
  - Mathematical scale-invariant helper functions to eliminate point-based heuristics across all indices.
- **High-risk paths touched**:
  - None. Zero files in `core/execution*`, `core/broker*`, `core/order*`, `core/risk*`, `strategies/`, or `main.py` are modified.

---

## Acceptance Criteria

- [ ] **AC-002-1**: $\Omega_{15}$ calculation strictly computed as $OR_{15} / ATR_{20}(T-1)$. Rescaling underlying price and ATR by any constant factor $k > 0$ yields identical $\Omega_{15}$ within $10^{-9}$ floating point precision.
- [ ] **AC-002-2**: When $ATR_{20}(T-1) \le 0$ or is unavailable, the compression evaluator fails closed with `state=UNKNOWN`, `gating_action=BLOCK_ALL_ENTRIES`, `is_valid=False`.
- [ ] **AC-002-3**: Excursions beyond $PDH$ or $PDL$ without volume delta absorption and closing back inside the boundary within $N$ bars are classified as `FAILED_AUCTION_TRAP`, blocking trend continuation.
- [ ] **AC-002-4**: Sustained boundary penetration with positive volume delta expansion and $M \ge 2$ consecutive closes beyond boundary is classified as `AUCTION_ACCEPTANCE`, authorizing trend breakout.
- [ ] **AC-002-5**: $d_{norm}$ formula verified against theoretical Black-Scholes diffusion standard deviation $\sigma \sqrt{\tau}$. Edge cases with $DTE \to 0$ are bounded safely by $\min\_dte = 0.5 / 365$, preventing division-by-zero.
- [ ] **AC-002-6**: Gamma wall evaluation accurately combines $d_{norm}$ and $WVR$ into `PIN_RISK_BARRIER` (blocks breakout buying) vs `WALL_BREAKTHROUGH_VULNERABLE` (authorizes squeeze momentum).
- [ ] **AC-002-7**: All decision dataclasses explicitly verify:
  ```python
  decision.read_only is True
  decision.is_order_action is False
  decision.broker_api_called is False
  decision.allowed_for_live_execution is False
  ```
- [ ] **AC-002-8**: 100% test pass rate across unit tests and adversarial edge cases (zero volume, NaN prices, negative volatility, inverted high/low).

---

## Development Plan

- **Allowed paths**:
  - `core/market_structure/sentinel_volatility_compression.py`
  - `core/market_structure/sentinel_auction_boundary.py`
  - `core/market_structure/sentinel_gamma_wall.py`
  - `core/market_structure/sentinel_composite_gate.py`
  - `tests/unit/market_structure/test_sentinel_volatility_compression.py`
  - `tests/unit/market_structure/test_sentinel_auction_boundary.py`
  - `tests/unit/market_structure/test_sentinel_gamma_wall.py`
  - `tests/unit/market_structure/test_sentinel_composite_gate.py`
  - `docs/tradebot_delivery/work_items/FEAT-SENTINEL-STRUCTURAL-GATES-002.md`
- **Forbidden paths**:
  - `core/execution*`
  - `core/broker*`
  - `core/order*`
  - `core/risk*`
  - `strategies/*`
  - `credentials*`
  - `main.py`
  - `run_live.sh`
  - `.env*`
- **Expected implementation**:
  - Two-stage Hermes $\to$ GSD workflow. Hermes defines contracts and acceptance criteria; GSD implements pure mathematical logic and tests.
- **Required developer tests**:
  - Unit tests validating scale invariance, mathematical correctness, error handling, and immutability.

---

## QA Attack Plan

- **Happy path**:
  - Normal market data: Nifty at 24,500, $ATR_{20} = 220$, $OR_{15} = 88$ $\to$ $\Omega_{15} = 0.40$ (`NORMAL_EQUILIBRIUM`).
  - Clear failed auction: Spot spikes 15 pts above $PDH$, negative delta volume, closes back below $PDH$ within 2 bars $\to$ `FAILED_AUCTION_TRAP`.
  - Normal gamma wall: Spot within 30 pts of 24,500 Call wall, $\sigma = 0.14$, $DTE = 2$ $\to$ $d_{norm} \approx 0.42$ (`PIN_RISK_BARRIER`).
- **Negative path**:
  - Null/None prices, negative $ATR$, zero volume delta, missing options open interest table.
  - Inverted bars (low > high).
- **Boundary conditions**:
  - Price exactly on $PDH$/$PDL$ ($S_t = PDH$).
  - Spot exactly on strike ($S_t = K_{wall} \implies d_{norm} = 0$).
  - $DTE = 0$ (expiry day final minutes).
  - Extremely low volatility ($\sigma = 0.0001$) and high volatility ($\sigma = 2.50$).
- **Stale/missing/corrupt data**:
  - Stale timestamp feed ($> 180$s lag) $\to$ Fails closed (`BLOCKED`).
  - Corrupt or missing prior day history $\to$ Fails closed (`BLOCKED`).
- **State-transition failures**:
  - Rapid oscillation across $PDH$ without sustained volume absorption.
- **Concurrency/order failures**:
  - Pure stateless functional evaluators ensuring thread safety and zero re-entrancy bugs.
- **Regression targets**:
  - Ensure existing `SentinelDiurnalSessionGate` remains backwards compatible and cleanly composable.

---

## Agile Sprint Backlog & User Stories

### Story 1: Sentinel-US-001 - Opening Shock Volatility Compression Ratio
- **User Story**: As an automated trader, I want to evaluate morning opening ranges relative to daily expected volatility so that the system suppresses trend breakouts during high-shock exhaustion days and focuses on coil breakouts during low-volatility compression.
- **Points**: 3
- **Sprint**: Sprint 1

### Story 2: Sentinel-US-002 - Prior-Day Boundary Auction State
- **User Story**: As a risk supervisor, I want to distinguish between genuine prior-day boundary breakouts and failed auction liquidity traps using volume delta confirmation, so that strategies do not enter long into institutional sell traps at PDH or short into buy sweeps at PDL.
- **Points**: 5
- **Sprint**: Sprint 1

### Story 3: Sentinel-US-003 - Normalized Gamma Strike Wall Proximity
- **User Story**: As a derivatives trader, I want to normalize distance to open interest strike walls using implied volatility and time to expiry, so that strategies dynamically recognize gamma pin barriers versus unwinding squeeze breakouts across all expiry horizons.
- **Points**: 5
- **Sprint**: Sprint 1

### Story 4: Sentinel-US-004 - Sentinel Composite Structural Gate
- **User Story**: As an institutional risk officer, I want a unified composite supervisor combining diurnal session, volatility compression, auction boundaries, and gamma proximity into an immutable decision matrix, ensuring fail-closed protection across all strategy signals.
- **Points**: 3
- **Sprint**: Sprint 2

---

## Definition of Done (DoD)

1. Formal work item (`FEAT-SENTINEL-STRUCTURAL-GATES-002.md`) published and accepted by Product Owner.
2. Architecture design and invariant contracts specified and signed off by Hermes.
3. Code implementation executed strictly by GSD within designated allowed paths.
4. Scale-invariance mathematically proven across synthetic pricing regimes ($k \times S$).
5. Safety invariants (`read_only=True`, `is_order_action=False`, `broker_api_called=False`, `allowed_for_live_execution=False`) verified in code and asserted in tests.
6. 100% test pass rate in Pytest with zero warnings or flake.
7. Independent QA and Senior QA sign-off confirming attack vectors were tested and defended.
8. Delivery evidence recorded and registered in claim registry.

---

## UAT Criteria

- Strategy backtest/replay against historical volatile shock days (e.g. Budget Day, Election Day) confirms `EXHAUSTION_SHOCK` prevents false breakout entries.
- Replay against historical range-bound chop days confirms `COMPRESSED_COIL` and `FAILED_AUCTION_TRAP` filter out $> 80\%$ of boundary whipsaw trades.
- Expiry day 0-DTE replay confirms gamma wall proximity accurately flags pin risks at dominant strikes.
- Memory and CPU profiling verify sub-millisecond evaluation latency per tick.

---

## Release Gates

- [x] Requirements traceable
- [ ] Architecture approved (Hermes)
- [ ] DEV_VERIFIED (GSD)
- [ ] QA_PASSED (QA)
- [ ] SENIOR_QA passed (Senior QA)
- [ ] UAT passed
- [ ] PRODUCT_ACCEPTED (Product Owner)
- [ ] CI_GREEN
- [ ] rollback/limitations documented

---

## Rollback Plan

All code is added as standalone, non-intrusive modular evaluators under `core/market_structure/`. In the event of an issue, strategies simply omit referencing `SentinelCompositeGate` and revert to existing behavior. No database migrations, runtime configurations, or live orders are affected.

---

## Evidence

- Tests: Pending GSD execution
- Logs/reports: Pending QA review
- Agent review evidence: Pending role review cycle
- PR: Pending branch creation

---

## Claim-level Evidence Standard

- Status: `UNVERIFIED` (pending Hermes contract formulation and GSD verification)
- Claims to be registered:
  - `CLAIM-SENTINEL-002-SCALE-INVARIANCE`: Mathematical scale-invariance of $\Omega_{15}$ and $d_{norm}$.
  - `CLAIM-SENTINEL-002-FAIL-CLOSED`: Guaranteed fail-closed behavior on missing or corrupted volatility/feed data.
  - `CLAIM-SENTINEL-002-ZERO-ORDER-SIDE-EFFECT`: Zero broker calls or live order actions verified.
