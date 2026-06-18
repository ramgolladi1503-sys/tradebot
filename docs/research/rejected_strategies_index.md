# Rejected Strategies Index

This document serves as the permanent graveyard for strategies that have failed the rigorous Deep-Dive Audit Pipeline. 

Strategies listed here must **not** be re-researched, tweaked, or promoted to any paper or live trading environment unless a fundamental flaw in the mathematical testing framework itself is discovered.

## REJECTED: ORB_BREAKOUT
- **Date Rejected**: 2026-06-18
- **Classification**: `REJECTED_REGIME_PASSENGER`
- **Reason**: Subjected to the Edge Attribution Matrix, `ORB_BREAKOUT` demonstrated 0 independent alpha. While it possessed a +0.22R net expectancy exclusively inside the `VOL_EXPANSION` regime, a naive regime-baseline entry (just blindly buying during the regime) yielded mathematically superior edge. The ORB gating structure actively subtracts expectancy compared to the naive regime drift. 
- **Documentation Reference**: [orb_final_verdict.md](../../runtime/strategy_deepdives/orb_final_verdict.md)

## REJECTED: HTF_OPENING_DRIVE_CONT
- **Date Rejected**: 2026-06-18
- **Classification**: `A. Dead signal`
- **Reason**: 0 signals generated under rigorous mathematical constraints.

## REJECTED: HTF_15M_TREND_CONT
- **Date Rejected**: 2026-06-18
- **Classification**: `A. Dead signal`
- **Reason**: 0 signals generated.

## REJECTED: HTF_15M_VWAP_PULLBACK
- **Date Rejected**: 2026-06-18
- **Classification**: `A. Dead signal`
- **Reason**: 0 signals generated.

---

**Note**: `HTF_RANGE_EXPANSION` remains completely quarantined from modifications and continues its passive real-paper observation phase.
