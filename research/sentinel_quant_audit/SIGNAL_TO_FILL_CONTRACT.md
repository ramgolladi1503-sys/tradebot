# Signal-to-Fill Formal Contract Specification

## Invariants & Clock Boundaries
1. **Signal Availability**: A signal triggered on candle $B_t$ is emitted at or after $t_{\text{close}}$.
2. **Earliest Eligible Fill**:
   - Limit Fill Model: Next bar open price $O_{t+1}$ or observed tick quote arriving at $t \ge t_{\text{close}}$.
   - No same-bar close execution using future knowledge.
3. **Attainable Option Fill Price**:
   - Buy Orders (Long CE / Long PE): Executed at lowest available **Ask** ($P_{\text{fill}} = P_{\text{ask}}$).
   - Sell Orders (Exits / Stop Losses): Liquidated at highest available **Bid** ($P_{\text{exit}} = P_{\text{bid}}$).
   - If spread exceeds 4.0%, trade is aborted under `VETO_SPREAD_EXPANDED`.
4. **Collision Precedence**:
   - If both Target and Stop Loss conditions are satisfied within the same 1-minute candle, the fill engine **fails closed** and awards the outcome to Stop Loss.
