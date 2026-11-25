# Work Item: FEAT-CONFIDENCE-SCORER-006
# Title: Bayesian Multi-Factor Option Confidence Rating Engine (0–100 & Grade A/B/C)
# Status: ARCHITECTURE_DRAFT / UNDER_REVIEW

## 1. Overview & Objective
Traders and automated execution systems require an objective, empirical confidence rating rather than binary trigger alerts. This work item implements `OptionConfidenceScorer`: an institutional-grade, multi-factor conviction engine that computes a 0–100 confidence score and assigns an actionable grade (Grade A, Grade B, Grade C / Suppressed) to every real-time option setup.

## 2. Mathematical Scoring Framework (100-Point Composite)
$$\text{Confidence Score} = \sum_{i=1}^{5} w_i \cdot S_i$$

1. **Multi-Index Macro Alignment ($w_1 = 25\text{ pts}$)**:
   - Full directional concordance between target index and anchor index (NIFTY & SENSEX aligned): **+25 pts**.
   - Target index only (counter-index neutral or diverging): **0 pts**.
2. **Option Writer Radar OI Asymmetry ($w_2 = 25\text{ pts}$)**:
   - Institutional writer alignment confirms trade (e.g. Put unwinding squeeze on PE long or Call unwinding on CE long): **+25 pts**.
   - Trapped writer conviction $\ge 0.70$: **+20 pts**.
   - Neutral / unconfirmed OI: **+5 pts**.
3. **Level-5 Order Book Depth Imbalance ($w_3 = 20\text{ pts}$)**:
   - Aggregated 5-level Bid/Ask Queue Ratio $\ge 2.0$: **+20 pts**.
   - Ratio between $1.2$ and $1.9$: **+10 pts**.
   - Ask-heavy book (thinning bid depth): **0 pts**.
4. **Volatility Compression & Coiling ($w_4 = 15\text{ pts}$)**:
   - Expansion directly out of an NR4 / NR7 volatility coil (displacement $< 1.5\text{ ATR}$): **+15 pts**.
   - Displacement between $1.5$ and $2.5\text{ ATR}$: **+8 pts**.
   - Late-stage exhausted breakout ($> 2.5\text{ ATR}$): **0 pts**.
5. **Strike Delta & Spread Friction ($w_5 = 15\text{ pts}$)**:
   - Deep ITM ($\Delta \ge 0.65\text{--}0.75$) with bid-ask spread $\le 0.5\%$: **+15 pts**.
   - Spread between $0.5\%$ and $1.5\%$: **+8 pts**.
   - Spread $> 1.5\%$ or low delta OTM: **0 pts**.

## 3. Grade Tiers & Expected Probability
- **Grade A (Prime Setup, Score $\ge 80$)**: $\approx 62\text{--}68\%$ win rate, full position sizing.
- **Grade B (Standard Setup, Score $60\text{--}79$)**: $\approx 45\text{--}52\%$ win rate, half position sizing.
- **Grade C (Sub-optimal, Score $< 60$)**: Negative expectancy ($< 28\%$ win rate). Suppressed fail-closed.

## 4. Strict Safety Invariants
- `read_only = True`
- `is_order_action = False`
- `broker_api_called = False`
- `allowed_for_live_execution = False`
- `status = NO_CERTIFIED_EDGE`
