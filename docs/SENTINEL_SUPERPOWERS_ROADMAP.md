# Sentinel Engine Architecture Roadmap: Microstructure Superpowers

**Document Version:** 1.0.0  
**Date:** 2026-10-13  
**Status:** Architecture Blueprint / Non-Execution Research Contract  
**Authority:** Hermes Quant Architect & Grill Me Adversarial Review  

---

## Executive Summary

This document establishes the strategic and architectural blueprint for the next evolution of the TradeBot Sentinel Engine. It defines the four proposed **Microstructure Superpowers**, evaluates the adversarial risks of over-engineering ("The Curse of Dimensionality"), and codifies the **Veto-Only Architectural Doctrine** required to prevent dilution of the existing profitable edge.

---

## 1. The Core Philosophy: "Veto Filters, Never Signal Creators"

In institutional quantitative finance, adding complexity often introduces more noise than signal. When an engine scores an $85.7\%$ win rate on live market data, the greatest risk is **analysis paralysis**:
- Spot candle says *BUY PE*.
- Order flow delta says *NEUTRAL*.
- Cross-index correlation says *WAIT*.
- Gamma wall says *CAUTION*.

When indicators conflict, execution latency increases, entries are taken late at the bottom of wicks, and curve-fitting degrades out-of-sample performance.

### The Invariant Principle
> **The Core Engine Never Changes.**  
> The baseline strategy (Opening Range Breakout + Kaufman Efficiency + 1-strike ITM option resolution + monotonic $+8\text{ pt}$ ratchet) remains the primary execution driver.  
> **Superpowers are strictly permitted to act as VETO FILTERS (saying "NO"), never as entry signal creators.**

---

## 2. The Four Proposed Superpowers

### Superpower 1: Live Order Book Imbalance & Delta Flow (Passive Absorption Detection)
* **Hypothesis:** Price breaks of key Opening Range bounds fail when passive institutional limit orders absorb the flow without moving price, or succeed when market orders aggressively sweep the book.
* **Architecture:**
  - Track Cumulative Delta ($\Delta_{\text{vol}} = V_{\text{ask}} - V_{\text{bid}}$) inside the 1-minute bar.
  - Compute Bid/Ask depth ratio at Top-5 book levels ($R_{\text{depth}} = \sum \text{BidQty} / \sum \text{AskQty}$).
* **Veto Contract:**
  - If a downward spot breakdown occurs (`PE` signal), but the Top-5 book shows extreme passive bid absorption ($R_{\text{depth}} > 3.0$) and positive delta divergence, trigger `VETO_PASSIVE_BUY_ABSORPTION`.
  - Otherwise, pass through to the core trigger silently.

---

### Superpower 2: Dynamic Open Interest (OI) & Gamma Exposure (GEX) Mapping
* **Hypothesis:** Market makers dynamically hedge short options. Strikes with massive Open Interest act as physical pinning walls or volatility accelerators depending on net market maker Gamma ($\Gamma_{\text{net}}$).
* **Architecture:**
  - Ingest live NSE Open Interest deltas across strike chains ($\Delta \text{OI}_{\text{CE}}$, $\Delta \text{OI}_{\text{PE}}$).
  - Compute localized Gamma Exposure ($GEX_K = S \times \Gamma_K \times \Delta \text{OI}_K$).
* **Veto Contract:**
  - If an intraday breakdown target directly collides with a massive Call/Put OI Wall within $0.5 \times \text{ATR}$, trigger `VETO_OI_PINNING_WALL`.
  - In positive Gamma regimes (mean-reverting), widen breakout confirmation thresholds. In negative Gamma regimes (explosive), enable runner trailing expansion.

---

### Superpower 3: Execution Simulation with Micro-Queue Latency Modeling
* **Hypothesis:** Paper advisory fills at touch ($P_{\text{fill}} = \text{LTP}$) deviate from real-world broker execution during high-volatility 0-DTE momentum bursts due to queue priority and slippage.
* **Architecture:**
  - Model queue position using FIFO execution assumptions based on top-of-book size and message arrival rate.
  - Apply dynamic adverse selection penalty: $P_{\text{fill}} = \text{Ask} + \max(0.5, \text{Spread} \times 0.25)$ on market order sweeps.
* **Veto Contract:**
  - Reject simulated trades where expected slippage exceeds $25\%$ of the target distance ($E[\text{Slippage}] / \text{Target} > 0.25$).

---

### Superpower 4: Multi-Horizon Cross-Index Correlation (NIFTY vs BANKNIFTY)
* **Hypothesis:** NIFTY breakdowns lack multi-bar continuation if heavyweight banking constituents (HDFC Bank, ICICI Bank, BANKNIFTY) exhibit strong positive divergence.
* **Architecture:**
  - Ingest parallel 1-minute candles for BANKNIFTY.
  - Compute 15-minute rolling directional correlation ($\rho_{\text{NIFTY, BNF}}$).
* **Veto Contract:**
  - If NIFTY triggers a `PE` breakdown, but BANKNIFTY is expanding above its Opening Range High with $\rho < -0.20$, trigger `VETO_CROSS_INDEX_DIVERGENCE`.

---

## 3. Implementation Verification & Graduation Gates

No superpower will be integrated into live execution without passing the standard TradeBot Research Pipeline:

1. **Stage A (Offline Causal Replay):**
   - Replay candidate veto filters across historical session chunks in `core.analytics.outcome_replay`.
   - Must prove higher Profit Factor and reduced maximum drawdown *without* degrading net expectancy.
2. **Stage B (Shadow Sidecar Mode):**
   - Run alongside production as an observational shadow logger (`status: SHADOW_OBSERVATION_ONLY`).
   - Track counterfactual outcomes: *Did the veto save money on a would-be loss, or did it falsely filter a winning runner?*
3. **Stage C (Graduation to Production Veto Gate):**
   - Formal pull request requiring unit test coverage, invariant contracts, and PR evidence locking.

---

## 4. Operational Invariant Safeguards

```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
```
All research, models, and contracts derived from this roadmap must preserve strict boundary isolation between SIM, PAPER, and LIVE execution environments.
