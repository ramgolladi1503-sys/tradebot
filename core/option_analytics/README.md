# Option Analytics V1

Production-quality, calculation-only analytics for European options.

## Capabilities

- Black–Scholes–Merton pricing with continuous dividend yield.
- Black–76 pricing on explicit forward/futures inputs.
- Analytic delta, gamma, theta, vega and rho with explicit units.
- Deterministic bracketed implied-volatility inversion.
- Strict quote provenance and freshness enforcement.
- Same-expiry, same-option-type local IV-surface diagnostics.
- Immutable candidate enrichment.
- Discrete pathwise Greek P&L attribution.

## Non-goals

The package does not generate entries, exits, contract selections, rankings or
profitability claims. A model residual is not automatically mispricing or
arbitrage. Live wiring requires a separate reviewed integration change.
