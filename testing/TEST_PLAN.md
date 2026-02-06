**Test Plan Overview**
This plan targets real trading failures and operational breakpoints. It prioritizes live data correctness, strategy logic correctness, and order safety. The focus is on NIFTY, BANKNIFTY, and SENSEX. Modes are Intraday, Scalp, and Zero‑Hero, and trades are manual approval only.

**Coverage Buckets**
Market data ingestion
Feature engineering
Strategy logic and scoring
Risk and position sizing
Order lifecycle
State and persistence
Performance and reliability
Security and compliance
Observability

**What Most People Miss**
Data gaps and tick ordering
Threshold edge behavior
Regime flip‑flops
Sizing under volatility spikes
Stale quotes and partial fills
Restart recovery and idempotency
Websocket reconnect loops
Secrets leakage in logs
Traceability for why a trade was suggested

**Test Types**
Functional
Boundary
Property‑based
Chaos
Adhoc charters

**Exit Criteria**
All P0 and P1 cases pass
No critical data ingestion errors
No duplicate trade emissions on restart
All trade decisions traceable with reason codes

**Artifacts**
`testing/TEST_CASES.csv` contains 315 structured cases
`testing/CHARTERS.md` contains manual exploratory charters

**How To Run**
1. Generate or refresh cases
2. Execute automated tests
3. Run chaos scripts during market replay
4. Log findings and retest

**Commands**
Generate cases
`python testing/generate_test_cases.py`

Run unit tests
`pytest -q tests`

Target a bucket
`pytest -q tests/test_risk_engine.py`
