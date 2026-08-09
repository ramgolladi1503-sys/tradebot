# Research Certification Kernel V1 — Seal

## Controlled status

`RESEARCH_CERTIFICATION_KERNEL_V1_SEALED`

This is a governance/evidence seal only. It does not grant runtime or broker authority and does not modify the certified kernel identity.

## Certified kernel identity

- Repository: `ramgolladi1503-sys/tradebot`
- Branch used for certification: `research/strategy-certification-kernel-v0`
- Exact certified kernel commit: `46dd4f7df9b63486eb633a12baf25412cd4f761d`
- Runner: `scripts/research/hypothesis_factory/run_pairs_arbitrage_successor_v1_certification.py`
- Runner SHA-256: `b27ac20068aa399ca1bc2ba9b56d9192089b9cc02f52903fa758b2ef00bf9c91`
- Frozen passport SHA-256 used by the adversarial audit: `d8b15688e4d2dad9a3cd5de1e176e5c387afeec6a6c3c1369e759e65221db53e`
- V1 adversarial-validator SHA-256: `4f59c29d4b90a4672a78025231c7c159d1abd82d005deed660634358004c3443`
- Runtime authority: `NONE`
- Broker actions permitted: `FALSE`
- Platform-wide bug-free claim: `FALSE`

## Native adversarial evidence

The exact repaired kernel state above was executed natively and produced:

- V1: `RESEARCH_CERTIFICATION_KERNEL_ADVERSARIAL_PASS`
  - checks: `8/8 PASS`
  - failed checks: `0`
- V2: `RESEARCH_CERTIFICATION_KERNEL_ADVERSARIAL_V2_PASS`
  - checks: `9/9 PASS`
  - failed checks: `0`

V1 demonstrated:

1. chronological split isolation;
2. no same-bar entry fill;
3. monotonic cost stress;
4. corrupted dataset hash fails closed;
5. passport identity tamper fails closed;
6. parent implementation commit tamper fails closed;
7. holdout is excluded from parameter selection;
8. research authority remains `NONE`.

V2 demonstrated:

1. future-feature access protection;
2. next-bar exit decision timing;
3. development/validation/holdout contamination protection;
4. denominator-laundering protection;
5. cost sign cannot manufacture alpha;
6. synthetic option economics are excluded from this underlying-spread kernel;
7. mandatory negative controls gate any future `CERTIFIED` verdict;
8. mutation sabotage is detectable for same-bar entry, future history, authority escalation, and negative costs;
9. audit byte bindings were captured.

## Certification policy from this seal forward

A strategy result may use the label `CERTIFIED` only when all of the following are true:

- the certification runner and all certification-critical code are byte-bound to an approved sealed kernel identity;
- dataset identity/hash and strategy/passport identity are frozen and verified;
- implementation/behavioral integrity is already closed;
- causal timing and next-bar execution rules pass;
- chronological OOS/holdout isolation passes;
- mandatory negative controls are actually executed and pass;
- cost/slippage stress passes;
- required robustness and sufficient-evidence gates pass;
- no holdout result was used to alter the frozen passport;
- runtime authority remains `NONE` unless separately governed outside this research kernel.

Any modification to certification-critical runner logic, split logic, timing, PnL/denominator logic, cost logic, authority logic, negative-control gating, or validator logic invalidates this seal for the changed bytes and requires adversarial re-certification before a new `CERTIFIED` strategy verdict may be issued.

## Scope boundary

This seal means the listed V1 and V2 adversarial properties passed for the exact byte-bound kernel above. It does **not** prove that the complete research platform is bug-free, that any strategy has edge, or that broker/live behavior is safe.

## Existing pairs result

`PAIRS_ARBITRAGE_SUCCESSOR_V1` remains `REJECTED`. The kernel seal does not reopen, tune, or alter that frozen experiment.
