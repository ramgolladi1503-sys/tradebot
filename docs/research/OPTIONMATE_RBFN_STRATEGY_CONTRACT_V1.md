# Option Mate RBFN Trend Decider & Slingshot Strike Strategy Contract

**Date**: 2026-11-03  
**Status**: APPROVED_STAGE_1  
**Source Agent**: `hermes`  
**Action**: `DEFINE_CONTRACT`  
**Scope**: `strategies/optionmate_rbfn_strategy.py`, `tests/strategies/test_optionmate_rbfn_strategy.py`  
**Allowed Paths**:  
- `docs/research/OPTIONMATE_RBFN_STRATEGY_CONTRACT_V1.md`  
- `strategies/optionmate_rbfn_strategy.py`  
- `tests/strategies/test_optionmate_rbfn_strategy.py`  

**Forbidden Paths**:  
- `main.py`  
- `run_live.sh`  
- `credentials.py`  
- `.env`  
- `core/broker*`  
- `core/order*`  

---

## 1. Architectural Intent
Formalizes the Option Mate (Damodhar Rao) non-linear Radial Basis Function (RBF) volatility surface and Slingshot strike migration strategy.
The strategy generates:
1. **Trend Decider (TD)**: Central equilibrium price between previous day close and spot open, adjusted for institutional flow.
2. **Reversal Price 1 ($RP_1$) & Reversal Price 2 ($RP_2$)**: Non-linear Gaussian volatility expansion bands at 38.2% and 68.2% dispersion.
3. **Slingshot Strike Selection**: Selects the target strike sitting at $RP_1$, buying the option that converts from OTM to ATM as price expands.

## 2. Invariants & Safety Rules
1. `read_only = True` by default in evaluation mode.
2. `is_order_action = False` (pure signal generation; zero live execution without explicit authorization).
3. `broker_api_called = False`.
4. Decoupled stop loss evaluated strictly on underlying spot price rather than native option LTP decay.
5. Invariant trade gating: No Puts permitted if Spot > Trend Decider; No Calls permitted if Spot < Trend Decider.

## 3. Mathematical Specifications
- **Volatility Scale**: $\text{VolScale} = \sqrt{\max(VIX, 9.0) / 14.0}$
- **Trend Decider**: $TD = 0.5 \times (S_{open} + S_{prev\_close}) + 0.05 \times \text{ATR}_{14} \times \text{sign}(\text{Flow})$
- **Reversal 1**: $RP_1 = TD \pm (0.382 \times \text{ATR}_{14} \times \text{VolScale})$
- **Reversal 2**: $RP_2 = TD \pm (0.682 \times \text{ATR}_{14} \times \text{VolScale})$
- **Target Strike**: $\text{Round}(RP_1 / \text{StepSize}) \times \text{StepSize}$

## 4. Acceptance Criteria
- Unit tests pass with 100% assertions proving:
  1. Correct mathematical barrier calculation.
  2. Directional discipline (Call-only above TD, Put-only below TD).
  3. Dynamic strike selection rounding.
  4. Non-infringement of safety gates (`is_order_action=False`, `broker_api_called=False`).
