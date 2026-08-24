# VWAP Auction State V1 — Research-Only Strategy Family

Status: `FORMULA_IMPLEMENTED_VALIDATION_PENDING`

Safety boundary:

- read_only=true
- is_order_action=false
- broker_api_called=false
- allowed_for_runtime_wiring=false
- allowed_for_live_execution=false

## Why this exists

This family translates the useful mechanism from the Trader Drysdale VWAP/auction framework into a causal NIFTY research design. It does **not** copy a chart setup blindly. The mechanism is reframed as an auction-state machine:

1. balance;
2. accepted price discovery;
3. failed price discovery returning to value;
4. discovery pullback and continuation;
5. balance-extreme rejection and mean reversion.

The implementation deliberately separates **signal formation** from **option execution**.

## Critical data correction

NIFTY spot has no authoritative traded volume. A spot-price "VWAP" built from zero volume or unit weights is not VWAP and must not be used as the signal authority.

Primary signal authority for this candidate is therefore:

- front/active NIFTY futures 1-minute OHLCV;
- strictly positive exchange/futures volume;
- one session at a time, anchored at 09:15 IST;
- completed bars only.

NIFTY options are the execution vehicle only. The strategy is BUY ONLY: `BUY_CALL` / `BUY_PUT`.

## Frozen mathematical core

For each completed 1-minute futures bar `i`:

```text
tp_i = (high_i + low_i + close_i) / 3
VWAP_t = sum(tp_i * volume_i, i<=t) / sum(volume_i, i<=t)
SIGMA_t = sqrt(sum(volume_i * (tp_i - VWAP_t)^2, i<=t) / sum(volume_i, i<=t))
Z_t = (close_t - VWAP_t) / SIGMA_t
ER_t = abs(close_t - close_t-L) / sum(abs(delta_close), t-L..t)
SLOPE_t = (VWAP_t - VWAP_t-L) / ATR_t
```

`SIGMA_t` has only a tiny causal ATR floor to prevent divide-by-zero during the opening warmup. It is not a volatility target or fitted multiplier.

Default V1 parameters:

```text
band_sigma                    = 1.00
extreme_sigma                 = 1.80
acceptance_window             = 5 bars
acceptance_fraction           = 0.80
discovery_efficiency_min      = 0.55
discovery_slope_atr_min       = 0.05
balance_efficiency_max        = 0.35
balance_slope_atr_max         = 0.08
balance_inside_fraction_min   = 0.60
balance_crossings_min         = 2
pullback_tolerance_sigma      = 0.35
failed_reentry_penetration    = 0.25 sigma
rejection_penetration         = 0.25 sigma
minimum structural R:R        = 1.50
continuation target           = 2.00R
cooldown                      = 15 minutes
max signals/session           = 3
last entry                    = 14:45 IST
forced exit                   = 15:15 IST
max hold                      = 30 minutes
```

These are a **predeclared starting formula**, not a claim that the numbers are optimal.

## State classifier

### UP_DISCOVERY

All of the following must hold:

```text
Z_t >= +band_sigma
fraction(last 5 closes outside +band) >= 0.80
ER_t >= 0.55
VWAP_slope / ATR >= +0.05
```

### DOWN_DISCOVERY

Exact mirror of `UP_DISCOVERY`.

### BALANCE

All must hold:

```text
ER_t <= 0.35
abs(VWAP_slope / ATR) <= 0.08
fraction(last 5 closes inside +/- band) >= 0.60
VWAP crossings over the balance window >= 2
```

Everything else is `TRANSITION`; the strategy does not force every minute into a tradeable regime.

## Candidate mechanisms

### 1. `VWAP_FAILED_DISCOVERY_RETURN_TO_VALUE_V1`

Highest-priority mechanism.

Upside example:

```text
UP_DISCOVERY established
-> price later closes at least 0.25 sigma back inside the +1 sigma band
-> structural stop above the post-discovery high + 0.10 ATR
-> frozen target = signal-time VWAP
-> require target distance / stop distance >= 1.50
-> BUY_PUT on next executable option ask
```

Downside is mirrored to `BUY_CALL`.

The failure signal takes priority over continuation because a failed auction invalidates the continuation thesis.

### 2. `VWAP_DISCOVERY_CONTINUATION_V1`

```text
accepted discovery
-> pullback touches the discovery band
-> pullback holds within 0.35 sigma of the band
-> next completed bar reconfirms outside the band
-> structural stop beyond pullback extreme + 0.10 ATR
-> target = 2R
-> next executable option ask
```

### 3. `VWAP_BALANCE_EXTREME_REVERSION_V1`

Only eligible when a recent bar is classified `BALANCE`.

```text
upper/lower excursion reaches >= 1.80 sigma
-> completed bar rejects at least 0.25 sigma back toward value
-> target = frozen signal-time VWAP
-> stop beyond rejection extreme + 0.10 ATR
-> require structural R:R >= 1.50
```

This setup is explicitly disabled outside a balance context.

## Option-expression layer

Contract selection is causal and BUY ONLY.

Primary stratum:

- correct side: CE for `BUY_CALL`, PE for `BUY_PUT`;
- signal-time quote only; no future-chain knowledge;
- nearest eligible expiry with 1–7 calendar DTE;
- 0DTE is **not mixed into the primary test** and is disabled by default;
- nearest ATM strike after DTE filtering;
- positive bid/ask, volume and OI;
- spread <= 2% of mid;
- stale quote >90 seconds rejected.

Entry:

```text
signal created only after completed futures bar
contract selected using information timestamped <= signal timestamp
fill = first eligible quote after signal timestamp
entry price = ask
```

Exit:

```text
structural stop / target / 30-minute time stop / 15:15 forced exit
exit price = first eligible bid at/after structural exit timestamp
```

If stop and target are both touched in one 1-minute bar, V1 resolves the ambiguity **against** the strategy (stop first). A later tick-level evaluator may replace this with exact event order, but may not retroactively rewrite the frozen V1 result.

## Risk layer

For sizing, long-option maximum loss is treated conservatively as the entire premium paid. Therefore:

```text
max_rupee_loss = account_equity * 0.05
premium_risk_per_lot = option_ask * lot_size
lots = floor(max_rupee_loss / premium_risk_per_lot)
```

This makes the 5% cap survive stop failure because long-option loss cannot exceed paid premium. A zero-lot result means **no trade**.

## Formula-search rule: plateau, not optimizer winner

The implementation exposes exactly nine predeclared DEV variants:

1. base;
2. band -0.1 sigma;
3. band +0.1 sigma;
4. acceptance fraction -0.2;
5. acceptance fraction +0.2;
6. discovery efficiency -0.05;
7. discovery efficiency +0.05;
8. VWAP slope threshold -0.02 ATR;
9. VWAP slope threshold +0.03 ATR.

This is intentionally a small one-factor-at-a-time neighborhood. It is **not** a Cartesian grid.

The formula is not "right" because one cell has the highest PnL. It becomes eligible for freezing only when the base formula sits on a robust plateau:

- base net expectancy positive after executable bid/ask costs;
- directionally consistent results across the small neighborhood;
- no single parameter perturbation creates the entire edge;
- adequate trade count and chronological coverage;
- no single month/regime dominates the result;
- cost sensitivity does not kill the result immediately;
- negative controls fail to reproduce the edge;
- corrected multiple-testing result survives;
- walk-forward and independent oracle agree on signal timestamps;
- only then may untouched holdout be opened.

If the base formula fails, the failure is preserved. A new formula family must be frozen as a new version before any new outcome access. We do not tune against the holdout.

## Governed kernel mapping

The repository's governed research lifecycle requires these gates before paper eligibility:

1. causal timestamps;
2. true next-bar execution;
3. transaction costs and slippage;
4. deterministic replay;
5. negative controls;
6. walk-forward analysis;
7. untouched holdout;
8. independent oracle;
9. artifact integrity.

V1 adds explicit checks for:

- futures-volume authority;
- buy-only option expression;
- option bid/ask executability;
- formula-family multiple-testing control;
- parameter-plateau robustness;
- era/month/regime concentration;
- cost sensitivity;
- 0DTE separation.

## Current evidence boundary

The formula and execution semantics are implemented and unit-tested. No historical profitability claim is made here. The historical corpus used for the economic run must be the existing kernel-authoritative corpus on the TradeBot data volume, with its DEV/OOS/HOLDOUT boundaries preserved.

Do not substitute the old one-day zero-volume spot proxy: that corpus already demonstrated why naive VWAP logic is unreliable and cannot certify this strategy.

## Focused engineering validation

```bash
python -m py_compile \
  research/vwap_auction_state_v1/model.py \
  research/vwap_auction_state_v1/backtest.py

python -m pytest -q -o addopts='' \
  tests/research/test_vwap_auction_state_v1.py \
  tests/research/test_vwap_auction_state_backtest_v1.py
```

The focused suite proves formula invariants and safety semantics only. Economic certification still requires the governed historical run.
