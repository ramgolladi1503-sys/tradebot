# NIFTY MEG Multi-Session Capture Plan V1

This document outlines the systematic plan to capture and register a diverse multi-session corpus of Upstox V3 tick data (10-20 sessions) across various market regimes to discover and validate robust Market Event Graph (MEG) models.

---

## 1. Targeted Market Regimes

To ensure MEG models are regime-robust and not overfitted to single-day behaviors, the corpus will span the following categories:

1. **Trend Up (Bullish Continuity)**: Constituents drive a steady upward move with low volatility and clear leadership rotation.
2. **Trend Down (Bearish Liquidation)**: High-volume selling across heavyweights, leading to sector-wide propagation and index futures pressure.
3. **High Volatility / Gap Days**: Large opening dislocations (gaps) driven by macro events, prompting fast option repricing.
4. **Range Bound / Mean Reverting**: Low volume, lack of leadership, indices oscillating within tight bounds.
5. **Expiry Day Rotations**: Dynamic strike pinned dynamics, high volume options activity, and rapid delta-gamma shifts.

---

## 2. Session Capture Protocol

For each registered session, the system must execute:
1. **Premarket Setup**: Resolve option strikes, futures, and sector indices based on index spot.
2. **Identity Sealing**: Write dated constituent membership, neutral weights, and instrument key maps.
3. **Full continuous capture**: Continuous recording of raw frames and normalized tick streams from 09:00 to 15:35 IST.
4. **Post-Market Validation**: Replay raw zstd files, check checksums, build 1-minute OHLCV bars, and verify no data drops.
5. **Outcome Blind Metrics**: Compile precursor tables and target outcomes separately.

---

## 3. Planned Session Registry (10-20 Target Sessions)

We target registering sessions from late June 2026 to August 2026 to capture a mixture of regimes:

| Date | Regime Label | Rationale | Status |
| :--- | :--- | :--- | :--- |
| **2026-08-04** | Expiry Day Rotations | Standard session with weekly options expiry build-up | Target (Active) |
| **2026-08-03** | Trend Up | Bullish expansion led by financials | Captured (Immutable) |
| **2026-07-30** | Trend Down | Sharp sell-off in IT and Auto constituents | Registered |
| **2026-07-27** | Range Bound | Low-activity consolidation session | Registered |
| **2026-07-23** | High Volatility | Post-event gap up and intraday reversal | Registered |
| **2026-07-16** | Trend Up | Financials and energy heavyweights leading index higher | Registered |
| **2026-07-09** | Expiry Day Rotations | Highly active option-pinning dynamics near ATM | Registered |
| **2026-07-02** | Range Bound | Tight consolidation ahead of weekly expiry | Registered |
| **2026-06-25** | Trend Down | Sectoral liquidation across metal and FMCG | Registered |
| **2026-06-18** | High Volatility | Major opening gap down followed by recovery | Registered |

---

## 4. Disclaimers

- **NO_STRUCTURAL_EDGE_CLAIM**: This multi-session plan does not assert any structural edge or predictive edge.
- **NO_PROFITABILITY_CLAIM**: Rehearsing these sessions does not guarantee strategy profitability.
- **NOT_A_KITE_LIVE_CERTIFICATION**: This layout is for offline testing and does not certify any live trading systems.
