# Work Item: FEAT-SENTINEL-DIURNAL-SESSION-001

## Identity

- Work Item ID: FEAT-SENTINEL-DIURNAL-SESSION-001
- Type: FEATURE
- Parent Epic: EPIC-SENTINEL-REGIME-SUPERVISORY
- Parent Feature: N/A
- Title: Sentinel Diurnal Session Gating (Golden Drive vs Midday Theta Trap)
- Current State: PRODUCT_ACCEPTED
- Priority: HIGH

---

## Business Goal

TradeBot strategies operating intraday on Indian equities and index derivatives (Nifty / BankNifty) frequently suffer severe risk-adjusted performance degradation during the midday liquidity lull (11:30 to 13:30 IST). During this phase, realized volatility collapses, bid-ask spreads widen, and mean-reverting chop or option theta bleed predominates ("Midday Theta Trap" / "Midday Vacuum"). Conversely, the opening session (09:15 to 11:30 IST, "Golden Morning Drive") and late afternoon institutional rebalancing (13:30 to 15:15 IST, "Afternoon Liquidity Expansion") exhibit sustained directional flow and reliable volume expansion.

The business goal is to implement a strict, deterministic, fail-closed supervisory market-structure gate—`SentinelDiurnalSessionGate`—that classifies the intraday session into canonical diurnal regimes and gates strategy trade generation. This prevents toxic midday overtrading, preserves capital for high-expectancy windows, and enforces safety boundaries across all execution modes without modifying core strategy mathematical logic.

---

## Current Behavior

Currently:
1. Active strategies run unconstrained across all market hours (09:15 to 15:30 IST) unless an ad-hoc local time check is embedded.
2. Market structure calculations (`core/market_structure/calculator.py`, `trend_state_analyzer.py`) evaluate price action and trend metrics agnostic of diurnal intraday phase properties.
3. Midday chop leads to adverse option theta decay, false breakout entries, and repeated slippage accumulation.
4. No standardized, centralized supervisory contract exists to signal `MORNING_DRIVE`, `MIDDAY_VACUUM`, `AFTERNOON_EXPANSION`, or `SESSION_CLOSING` states with explicit gating controls.

---

## Expected Behavior

1. `SentinelDiurnalSessionGate` evaluates any bar/tick timestamp against Indian Standard Time (`Asia/Kolkata`) canonical diurnal boundaries.
2. Canonical Diurnal Regimes are strictly recognized:
   - `PRE_OPEN`: 09:00:00 to 09:14:59 IST (Hard gate: NO trades allowed)
   - `MORNING_DRIVE`: 09:15:00 to 11:29:59 IST (Golden Drive: Full trade authorization)
   - `MIDDAY_VACUUM`: 11:30:00 to 13:29:59 IST (Theta Trap: New entries BLOCKED; defensive exits/risk-off managed)
   - `AFTERNOON_EXPANSION`: 13:30:00 to 15:14:59 IST (Institutional Rebalance: Trend-following / breakout trades allowed)
   - `SESSION_CLOSING`: 15:15:00 to 15:29:59 IST (Intraday wind-down: NO new entries; mandatory square-off / exit only)
   - `MARKET_CLOSED`: Outside 09:00:00 - 15:30:00 IST or weekends/holidays (Hard gate: NO trades allowed)
3. Zero Strategy Modification: Core strategy logic remains untouched. Strategies consult or receive gating decisions purely via supervisory market structure contracts.
4. Fail-Closed Freshness: If timestamps are missing, naive, out-of-order, or exceed freshness tolerance (> 180 seconds lag), the gate fails closed (`gating_status=BLOCKED`, `reason="STALE_OR_INVALID_FEED"`).
5. Deterministic, pure evaluation: Evaluates without network side effects, broker API interactions, or state leakage across sessions.

---

## In Scope

- Creation of `core/market_structure/sentinel_diurnal_regime.py` defining:
  - Canonical enums (`DiurnalRegime`, `DiurnalGatingAction`)
  - Immutable decision dataclass (`DiurnalSessionDecision`)
  - Supervisory gate evaluator (`SentinelDiurnalSessionGate`) with IST timezone enforcement (`Asia/Kolkata`)
- Configurable window definitions (with validated strict defaults)
- Fail-closed validation for timestamps (timezone-aware conversion, freshness check)
- Unit and property-based test coverage in `tests/unit/test_sentinel_diurnal_regime.py`
- Traceable work item and delivery lifecycle documentation in `docs/tradebot_delivery/*`

---

## Out of Scope

- Core strategy mathematical refactoring (no threshold modifications in `strategies/*`).
- Order placement, cancellation, or modification logic (`core/execution*`, `core/order*`, `core/broker*`).
- Broker API calls or credential management.
- Live runtime configuration wiring (`run_live.sh`, `main.py`).
- Risk manager parameter alterations (`core/risk*`).
- Real-time websocket or feed listener infrastructure modifications.

---

## Dependencies

- Python 3.10+ standard library (`dataclasses`, `enum`, `datetime`, `zoneinfo`).
- `core.market_structure.contract` (optional alignment for shared market structure types).
- Pytest test runner (`tests/unit/test_sentinel_diurnal_regime.py`).

---

## Requirement Traceability

| Requirement ID | Requirement Description | Source | Acceptance Criterion |
|---|---|---|---|
| REQ-DIURNAL-001 | Canonical Diurnal Regime Identification | Product Owner / BA | Timestamp correctly maps to `PRE_OPEN`, `MORNING_DRIVE`, `MIDDAY_VACUUM`, `AFTERNOON_EXPANSION`, `SESSION_CLOSING`, `MARKET_CLOSED` under IST (`Asia/Kolkata`). |
| REQ-DIURNAL-002 | Supervisory Entry Gating by Regime | Product Owner | `allow_new_entries=True` strictly during `MORNING_DRIVE` and `AFTERNOON_EXPANSION`. `allow_new_entries=False` during `MIDDAY_VACUUM`, `SESSION_CLOSING`, and `MARKET_CLOSED`. |
| REQ-DIURNAL-003 | Fail-Closed Feed Freshness & Timezone Guard | Repository Safety Rules | Stale data (> 180s lag from reference), naive/invalid timestamps, or inverted clock inputs return `is_valid=False`, `gating_action=BLOCK_ALL`, and descriptive failure reasons. |
| REQ-DIURNAL-004 | Zero Core Strategy Modification | Hermes / GSD Architecture Rule | The gate operates strictly as a supervisory evaluator. Strategy algorithms in `strategies/` are not modified. |
| REQ-DIURNAL-005 | Pure, Stateless, Deterministic Verification | Delivery Lifecycle / QA | Evaluator exposes pure query methods (`evaluate(timestamp, reference_time=None)`) ensuring reproducible backtest, paper, and audit replays. |

---

## Safety / Risk Constraints

- **Broker/order impact**: None (`is_order_action=False`, `broker_api_called=false`).
- **LIVE/PAPER/SIM impact**: Pure supervisory contract usable in SIM, PAPER, and prospective LIVE gating without mode-dependent branching.
- **Risk-gate impact**: Enhances safety by fail-closing when outside authorized trading windows. Does not weaken or disable any existing risk gate.
- **Feed-freshness impact**: Enforces fail-closed behavior on stale timestamps (> 180 seconds).
- **Data/evidence impact**: Evidence and outputs are strictly read-only (`read_only=True`).
- **Required human approval**: Standard delivery workflow gates; no LIVE runtime deployment without human sign-off.

---

## Architecture Impact

- **Components touched**:
  - `core/market_structure/sentinel_diurnal_regime.py` (new)
  - `tests/unit/test_sentinel_diurnal_regime.py` (new)
  - `docs/tradebot_delivery/work_items/FEAT-SENTINEL-DIURNAL-SESSION-001.md` (this specification)
- **Interfaces/contracts affected**: Pure supervisory market structure contract.
- **Existing infrastructure reused**: Standard library `zoneinfo`, dataclass patterns from `core/market_structure/contract.py`.
- **New infrastructure required**: None.
- **High-risk paths touched**: None (`forbidden_paths` strictly enforced).

---

## Acceptance Criteria

- [ ] `SentinelDiurnalSessionGate` is defined with immutable dataclasses and strict typing.
- [ ] Correct classification of IST timestamps into regimes:
  - 09:00:00 -> `PRE_OPEN` (`allow_new_entries=False`)
  - 09:15:00 -> `MORNING_DRIVE` (`allow_new_entries=True`)
  - 11:29:59 -> `MORNING_DRIVE` (`allow_new_entries=True`)
  - 11:30:00 -> `MIDDAY_VACUUM` (`allow_new_entries=False`)
  - 13:29:59 -> `MIDDAY_VACUUM` (`allow_new_entries=False`)
  - 13:30:00 -> `AFTERNOON_EXPANSION` (`allow_new_entries=True`)
  - 15:14:59 -> `AFTERNOON_EXPANSION` (`allow_new_entries=True`)
  - 15:15:00 -> `SESSION_CLOSING` (`allow_new_entries=False`)
  - 15:30:00 -> `MARKET_CLOSED` (`allow_new_entries=False`)
- [ ] Timezone safety: Explicitly handles naive datetimes by asserting or defaulting to IST, and converts UTC datetimes accurately to IST.
- [ ] Stale data (> 180s lag between bar/tick timestamp and reference time) fails closed with `gating_action=BLOCK_ALL` and `is_fresh=False`.
- [ ] Zero strategy files altered; zero broker calls; zero execution layer changes.
- [ ] 100% test pass rate on unit suite `tests/unit/test_sentinel_diurnal_regime.py`.

---

## Development Plan

- **Allowed paths**:
  - `core/market_structure/sentinel_diurnal_regime.py`
  - `docs/tradebot_delivery/*`
- **Forbidden paths**:
  - `main.py`
  - `run_live.sh`
  - `core/execution*`
  - `core/broker*`
  - `core/order*`
  - `core/risk*`
  - `config/*`
  - `strategies/*`
- **Expected implementation**:
  - Implementation deferred to GSD following Hermes architectural specification.
- **Required developer tests**:
  - Boundary tests at exact second transitions (09:14:59 -> 09:15:00, 11:29:59 -> 11:30:00, etc.).
  - UTC vs IST timezone normalization tests.
  - Fail-closed staleness tests.
  - Weekend and holiday date checks.

---

## QA Attack Plan

- **Happy path**: Verify regime transition and gating flag across a synthesized 1-minute intraday session profile.
- **Negative path**: Invalid timestamp formats, negative timestamps, future-dated timestamps (> max clock skew).
- **Boundary conditions**: Sub-second and millisecond timestamps right at transition edges (e.g. 11:29:59.999 vs 11:30:00.000).
- **Stale/missing/corrupt data**: None timestamp, stale timestamps with age > 180s, backward-jumping timestamps.
- **State-transition failures**: In-flight trades entering midday boundary (verify entry blocked while exits permitted).
- **Regression targets**: Existing market structure calculators remain unaffected.

---

## Release Gates

- [x] Requirements traceable (REQ-DIURNAL-001 through REQ-DIURNAL-005)
- [x] Architecture approved (Hermes Stage 1)
- [x] DEV_VERIFIED (GSD Stage 2)
- [x] QA_PASSED
- [x] SENIOR_QA passed
- [x] UAT passed
- [x] PRODUCT_ACCEPTED
- [x] CI_GREEN
- [x] Rollback/limitations documented

---

## Rollback Plan

If `SentinelDiurnalSessionGate` exhibits unintended gating or calculation bottlenecks:
1. Revert `core/market_structure/sentinel_diurnal_regime.py` and test file additions.
2. Because this is purely supervisory and un-wired to runtime order execution, rollback entails zero risk to live trading state or database schemas.
