# 70-Point Implementation Matrix

Scores below rate implementation maturity, not trading profitability or live readiness.

| Control | Domain | Implementation score | Evidence |
|---|---|---:|---|
| AQ-01 — Isolated execution context | isolation_authority | 10/10 | deterministic code + focused tests + CI gate |
| AQ-02 — Read-only evidence access | isolation_authority | 10/10 | deterministic code + focused tests + CI gate |
| AQ-03 — No broker or order authority | isolation_authority | 10/10 | deterministic code + focused tests + CI gate |
| AQ-04 — No live runtime mutation | isolation_authority | 10/10 | deterministic code + focused tests + CI gate |
| AQ-05 — Deterministic verdict ownership | isolation_authority | 10/10 | deterministic code + focused tests + CI gate |
| AQ-06 — Agent advisory boundary | isolation_authority | 10/10 | deterministic code + focused tests + CI gate |
| AQ-07 — Human approval boundary | isolation_authority | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-08 — Least-privilege tool allowlist | isolation_authority | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-09 — Secret redaction | isolation_authority | 10/10 | deterministic code + focused tests + CI gate |
| AQ-10 — Immutable audit ledger | isolation_authority | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-11 — Manifest present | evidence_integrity | 10/10 | deterministic code + focused tests + CI gate |
| AQ-12 — Manifest schema valid | evidence_integrity | 10/10 | deterministic code + focused tests + CI gate |
| AQ-13 — Artifact paths contained | evidence_integrity | 10/10 | deterministic code + focused tests + CI gate |
| AQ-14 — Required artifacts exist | evidence_integrity | 10/10 | deterministic code + focused tests + CI gate |
| AQ-15 — Artifact hashes verified | evidence_integrity | 10/10 | deterministic code + focused tests + CI gate |
| AQ-16 — Repository commit captured | evidence_integrity | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-17 — Configuration digest captured | evidence_integrity | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-18 — Dataset digest captured | evidence_integrity | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-19 — Command and environment captured | evidence_integrity | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-20 — Bundle digest reproducible | evidence_integrity | 10/10 | deterministic code + focused tests + CI gate |
| AQ-21 — Timezone explicit | temporal_data | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-22 — Signal precedes entry | temporal_data | 10/10 | deterministic code + focused tests + CI gate |
| AQ-23 — No same-event entry | temporal_data | 10/10 | deterministic code + focused tests + CI gate |
| AQ-24 — No future feature access | temporal_data | 10/10 | deterministic code + focused tests + CI gate |
| AQ-25 — Split boundaries valid | temporal_data | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-26 — Preprocessing fit on train only | temporal_data | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-27 — Point-in-time universe | temporal_data | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-28 — Corporate actions handled | temporal_data | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-29 — Stale quote policy | temporal_data | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-30 — Sequence quality checks | temporal_data | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-31 — Fees included | execution_risk | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-32 — Spread modeled | execution_risk | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-33 — Slippage modeled | execution_risk | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-34 — Latency modeled | execution_risk | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-35 — Partial fills modeled | execution_risk | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-36 — Liquidity constraints | execution_risk | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-37 — Position sizing deterministic | execution_risk | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-38 — Exposure limits | execution_risk | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-39 — Loss limits and kill switch | execution_risk | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-40 — Rejected and missed orders | execution_risk | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-41 — Out-of-sample evidence | robustness_validation | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-42 — Walk-forward analysis | robustness_validation | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-43 — Holdout reuse controlled | robustness_validation | 10/10 | deterministic code + focused tests + CI gate |
| AQ-44 — Parameter perturbation | robustness_validation | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-45 — Cost stress | robustness_validation | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-46 — Delayed-entry stress | robustness_validation | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-47 — Regime segmentation | robustness_validation | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-48 — Instrument generalization | robustness_validation | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-49 — Best-trade dependence | robustness_validation | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-50 — Negative controls and resampling | robustness_validation | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-51 — Structured agent output | agent_quality_security | 10/10 | deterministic code + focused tests + CI gate |
| AQ-52 — Evidence citation accuracy | agent_quality_security | 10/10 | deterministic code + focused tests + CI gate |
| AQ-53 — No fabricated metrics | agent_quality_security | 10/10 | deterministic code + focused tests + CI gate |
| AQ-54 — Verdict agreement | agent_quality_security | 10/10 | deterministic code + focused tests + CI gate |
| AQ-55 — Uncertainty disclosure | agent_quality_security | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-56 — Prompt-injection resistance | agent_quality_security | 10/10 | deterministic code + focused tests + CI gate |
| AQ-57 — Tool-call policy | agent_quality_security | 10/10 | deterministic code + focused tests + CI gate |
| AQ-58 — Model and prompt provenance | agent_quality_security | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-59 — Prompt regression suite | agent_quality_security | 10/10 | deterministic code + focused tests + CI gate |
| AQ-60 — Agent scorecard thresholds | agent_quality_security | 10/10 | deterministic code + focused tests + CI gate |
| AQ-61 — Run and trace identity | governance_operations | 10/10 | deterministic code + focused tests + CI gate |
| AQ-62 — Restart-safe checkpointing | governance_operations | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-63 — Manual promotion approval | governance_operations | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-64 — Role separation | governance_operations | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-65 — Policy version pinned | governance_operations | 10/10 | deterministic code + focused tests + CI gate |
| AQ-66 — Failure taxonomy | governance_operations | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-67 — Audit report completeness | governance_operations | 10/10 | deterministic code + focused tests + CI gate |
| AQ-68 — CI enforcement | governance_operations | 10/10 | deterministic code + focused tests + CI gate |
| AQ-69 — Reproducible CLI and runbook | governance_operations | 9/10 | deterministic control implemented; real bundle/online/soak evidence still required |
| AQ-70 — Truthful non-claims | governance_operations | 10/10 | deterministic code + focused tests + CI gate |
