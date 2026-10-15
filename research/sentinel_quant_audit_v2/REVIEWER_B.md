# REVIEWER B: DATA & CAUSAL FORENSICS REPORT

**Reviewer Role:** Data & Causal Forensics Auditor (Reviewer B)  
**Mandate:** Audit input availability, bar-label conventions, capture-vs-exchange timestamps, lookahead, replays, missing ticks, session coverage, and reproducibility.  
**Branch:** `research/sentinel-quant-audit-20261015`  
**Evaluation Scope:** Causal data flow, timestamp synchronization, and replay reproducibility.

---

## 1. Causal Pipeline & Timestamp Synchronization Audit

Reviewer B audited the live feed ingestion engine (`scripts/run_live_feed_advisor.py`) and capture architecture (`scripts/upstox_daily_live_capture_and_stitch.py`).

### Key Invariants Verified:
1. **Exchange vs Capture Clock:**
   - Feeds arrive via Upstox WebSocket market stream.
   - Live advisor timestamps each bar at bar close: `10:00:00` represents the completed $[09:59:00, 10:00:00)$ interval.
   - In live paper runs, decisions are emitted at $T_{close} + \Delta t_{proc}$ where $\Delta t_{proc} \approx 45-85 \text{ ms}$. No future bar information leaked into the live signal.
2. **Opening Range Causal Barrier:**
   - Commit `461e2a061` ("require complete causal opening range") enforces that no signals are evaluated prior to 09:30:00 IST. The 15 bars from $[09:15, 09:30)$ are strictly frozen as input context.

---

## 2. Adversarial Causal Defects Unmasked

### Finding B.1: The "Seven Consecutive Winning Sessions" Data Claim Falsification
- **Claim Under Audit:** User prompt and initial reports stated the Sentinels generated positive paper-shadow outcomes across *seven consecutive trading sessions*.
- **Forensic Audit Result:** **FALSIFIED.**
  - Examination of checked-in WAL files (`runtime/sentinel_apm_wal.json` and `runtime/sentinel_apm_wal_sensex.json`) reveals:
    - Only **3 distinct live dates** are preserved in machine-readable WAL history: `2026-10-13`, `2026-10-14`, and `2026-10-15`.
    - Earlier October sessions (`2026-10-08`, `2026-10-09`) exist only as un-replayed preflight scripts or crash recovery snapshots with 0 closed trades in history. Commit `11d616a1b` explicitly retracted synthetic Oct 8 replay claims because quote feeds were missing.
    - Most crucially: **The sequence is NOT an unbroken winning streak.** On `2026-10-14`, NIFTY suffered **-102.35 spot points (-62.80 gross option points, -Rs 2,052.36 net)** across 9 trades.

### Finding B.2: DEF-01 Causal Lookahead in Walk-Forward Optimizer
- **Defect Location:** `scripts/run_walk_forward_optimizer.py:119`:
  ```python
  hit_sl = (curr_bar['high'] <= pos['sl_spot'])  # PE trade
  ```
- **Forensic Impact:**
  - In PE trades, when the market drops in our favor, `curr_bar['high']` is lower than the initial stop. The buggy optimizer evaluated this as `True`, immediately liquidating winning short positions at false stop losses.
  - This corrupted all historical PE parameter optimizations in offline research, causing the optimizer to severely underestimate PE profitability and skewing recommended parameter sets toward CE-favoring bias.

### Finding B.3: Missing Tick Parquets on Remote CI
- Canonical parquet data in `/Volumes/TradeBotData/...` is unavailable on hosted CI runners. Previous commits attempted to paper over this with mock scalers (`scaler.npz` containing all zeros). PR #968 hardening rightly rejected these mock scalers, but an immutable portable fixture remains missing for continuous integration.

---

## 3. Reviewer B Recommendation & Verdict
- **Verdict:** **DATA AUDIT PASSED FOR LIVE OCT 13-15 WAL EVIDENCE; 7-DAY UNBROKEN STREAK HYPOTHESIS REJECTED.**
- Live paper trades on Oct 13, 14, 15 are causally valid, timestamp-accurate, and non-lookahead. The claim of 7 unbroken winning days must be formally struck from strategy performance documentation.
