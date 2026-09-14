# TRADE TRUTH — PROSPECTIVE CURRENT-SHA FAMILY & REGIME CALL PATH

## 1. Architectural Call Path at Candidate 9760ce3e3

```text
[Caller: core.orchestrator.run_cycle (L5410-5416)]
        │
        ▼
[Callee: core.orchestrator._evaluate_c1_c2_for_symbol (L346-435)]
        │
        ▼
[Evaluators: core.candidate_evaluators.evaluate_c1 / evaluate_c2]
        │
        ├─► C1: StrategyFamily.TREND, Subfamily: MOMENTUM_IMPULSE
        └─► C2: StrategyFamily.TREND, Subfamily: OVERNIGHT_TREND
        │
        ▼
[Gatekeeper Admission: core.orchestrator.run_cycle (L5418)]
        self._strategy_gate_for_symbol(market_snapshot)
        │
        ▼
[Pre-gate Decoupling Proof: PR #897 / lines 5551-5570]
        - Evaluators take ONLY MarketMemorySnapshot (pure price/return metrics).
        - Regime is NOT an input to candidate generation.
        - When regime is REGIME_UNSTABLE, candidates are generated and recorded as FILTERED at REGIME_CHECK stage.
        - Therefore, for C1 and C2 candidate evaluation:
          REGIME_STAGE_NOT_APPLICABLE (with CURRENT-SHA proof).
```

## 2. Stage Analysis
1. Candidate Family Origin: Assigned by core.candidate_evaluators (CandidateEmission.strategy_family = "TREND").
2. Allowed Family Set: Decided by runtime gatekeeper / strategy configuration.
3. Compatibility Gate: core.strategy_family_contract.check_strategy_family_compatibility(candidate_family, allowed_families).
4. Governed Authority: core.governed_strategy_authority.validate_execution_candidate(cand).
