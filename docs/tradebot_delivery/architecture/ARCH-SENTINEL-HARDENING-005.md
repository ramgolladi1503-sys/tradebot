# Architecture Specification: ARCH-SENTINEL-HARDENING-005

**Component**: `core/sentinel_live_stream_advisor.py`  
**Test Suite**: `tests/unit/test_sentinel_advisor_hardening_005.py`  
**Parent Epic**: `EPIC-SENTINEL-REGIME-SUPERVISORY`  
**Author**: Hermes Architect (Quant Architect and Invariant Designer)  
**Delivery Stage**: Stage 1 (Architecture, Contracts & Acceptance Gates)  
**Status**: APPROVED_FOR_GSD_EXECUTION  

---

## 1. Executive Summary & Root Cause Diagnosis

### 1.1 The Operational Incident & Failure Mechanism
During live session execution at `09:45:00 IST`, the opening shock lock period terminates, and `core/sentinel_live_stream_advisor.py` transitions `self.trade_lock_active` from `True` to `False`. At this exact instant:
```python
if self.trade_lock_active:
    self.trade_lock_active = False
    self._seed_or_bounds_from_api_if_late_boot(session_day=tick_day)
```
The method `_seed_or_bounds_from_api_if_late_boot` queries the Upstox v2 REST candle API (`/v2/historical-candle/intraday/{instrument}/1minute`) to retrieve and verify exact 30-bar opening range coverage (09:15:00 through 09:44:00 bucket).

However, the 30th 1-minute candle (09:44:00 to 09:44:59.999) closes at exactly `09:45:00.000 IST`. Broker REST endpoints exhibit upstream aggregation and ingestion latency: Upstox typically requires a 15–45 second propagation window before the 30th bar is published and returned in intraday historical candle queries.

### 1.2 The One-Shot Invalidation Trap
Because `_seed_or_bounds_from_api_if_late_boot` was executed as a **one-shot attempt**:
1. At 09:45:38, the Upstox API returned 29 candles (or an incomplete set missing the 09:44 candle).
2. `self._parse_complete_v2_or_candles` returned `None`.
3. Lines 1525–1535 latched the index evidence status:
   ```python
   invalid.update({
       "session_date": expected_day.isoformat(),
       "status": "INVALID",
       "source": "UPSTOX_V2_1M",
   })
   self.or_evidence[index_name] = invalid
   ```
4. `self.trade_lock_active` was already set to `False`. Consequently, the advisor **never retried** OR candle reconciliation for the remainder of the trading day.
5. At all subsequent 5-minute bar closes (09:50, 09:55, 10:00, etc.), whenever OptionMate or Mode 5 setups evaluated candidate entries, `_validate_mode5_or_evidence` found `status == "INVALID"` and rejected valid setups with:
   `MODE5_TARGET_OR_COMPLETE_REQUIRED` or `MODE5_COMPANION_OR_COMPLETE_REQUIRED`.
6. Even though all 30/30 candles were available on Upstox from 09:45:50 onward, the engine remained permanently poisoned and starved for the entire session.

### 1.3 Sub-Second Timestamp Jitter & Causal Skew Hazard
In addition to REST propagation delay, multi-index causal cross-validation (`_validate_mode5_or_evidence`) enforces:
```python
if source_timestamp_ms <= 0 or source_timestamp_ms > decision_timestamp_ms:
    return False, "OR_SOURCE_NONCAUSAL", details
```
When evaluating companion or target index timestamps at bar close boundaries (e.g. nominal 09:30:00.000 bar close or 09:45:00 OR closure), sub-second tick arrival jitter (e.g., companion tick arriving at `09:29:59.907` while target is at `09:30:00.000`, or OR coverage end at `09:44:00.000` evaluated against a tick arriving fractions of a second early) can trigger false `OR_SOURCE_NONCAUSAL` rejections if microsecond/millisecond network skew is not bounded with a strict point-in-time tolerance window.

---

## 2. Invariant Contracts & Architectural Principles

To eliminate the one-shot invalidation trap while maintaining absolute point-in-time causality, ARCH-SENTINEL-HARDENING-005 establishes the following mandatory contracts.

```python
SAFETY_DECLARATIONS = {
    "read_only": True,
    "is_order_action": False,
    "broker_api_called": False,
    "allowed_for_live_execution": False,
    "runtime_wiring_modified": False,
    "fail_closed_mode": True,
}
```

### Contract 1: `RETRY_OR_RECONCILIATION_UNTIL_COMPLETE` (GATE-SENTINEL-15)

1. **State Preservation & Invalidation Decoupling**:
   - An incomplete or delayed candle response from the broker REST API prior to successful reconciliation must **not** permanently latch the index status to `INVALID`.
   - The status for an index awaiting complete 30-bar coverage remains `PENDING_RECONCILIATION` (or retains existing valid `PARTIAL` live stream state) with `reconciliation_attempts` tracked.
   - Only an unrecoverable structural violation (e.g. non-contiguous timestamps within completed range, session date mismatch, corrupted price bounds) after the retry window has fully elapsed may mark the index as unresolvable.

2. **Bounded Periodic Retry Protocol**:
   - When `now >= 09:45:00 IST` and any required index (`NIFTY`, `BANKNIFTY`, `SENSEX`) does **not** have `status == "COMPLETE"`:
     - The advisor evaluates reconciliation retries on:
       - Every discrete 5-minute bar close (09:45:00, 09:50:00, 09:55:00, etc.), **OR**
       - An explicit rate-limited backoff throttle: minimum `60.0` seconds interval between REST calls per index (`min_retry_interval_seconds = 60.0`).
     - Hard retry cap: Maximum 10 retry cycles (or until `10:30:00 IST`), preventing infinite or runaway API calls.
   - Zero API Spamming: Under no circumstances may high-frequency ticks trigger REST queries. The retry check must be gated by `(now_ms - last_reconcile_attempt_ms) >= 60000`.

3. **Permanent Freeze Upon Verification**:
   - Once an index achieves `status == "COMPLETE"` with verified exact 30-candle coverage (`source == "UPSTOX_V2_1M_EXACT_30"`), its `or_bounds` and `or_evidence` **freeze permanently** for the remainder of the session day.
   - Once all required indices verify `status == "COMPLETE"`, all background reconciliation polling terminates immediately (`or_reconciliation_frozen = True`). No further network requests are dispatched for OR reconciliation.

4. **Strict Fail-Closed Invariant**:
   - Until `or_evidence[target]["status"] == "COMPLETE"` AND `or_evidence[companion]["status"] == "COMPLETE"`, all Mode 5 and OptionMate candidate entries **must fail closed and abstain**.
   - No speculative or unproven bounds may ever be used to authorize live or paper trade entries.

### Contract 2: Millisecond Causal Skew Tolerance Boundary

1. **Microstructure Jitter Definition**:
   - Intraday index ticks across heterogeneous exchanges (NSE for NIFTY, BSE for SENSEX) or candle close timestamps versus tick arrivals exhibit small transport and queue latencies (typically 50–500ms).
   - In `_validate_mode5_or_evidence`:
     ```python
     # Strict nominal check:
     source_timestamp_ms <= decision_timestamp_ms
     ```
     For a completed OR, `source_timestamp_ms` represents the bar timestamp of the 30th 1m candle: `09:44:00.000 IST` (or coverage end ms `09:44:00.000` / `09:44:59.999`).
2. **Causal Tolerance Rule**:
   - The decision timestamp `decision_timestamp_ms` must be strictly after the completion of the opening range:
     `decision_dt.time() >= 09:45:00 IST`.
   - To account for sub-second clock drift or companion tick arrival skew between NSE and BSE feeds at bar boundaries:
     - A maximum permissible causal clock skew tolerance of `skew_tolerance_ms = 1000` (1 second) is permitted **only** when comparing companion feed timestamps against the local decision boundary, provided both events fall within the same discrete 5-minute bar window.
     - `source_timestamp_ms <= (decision_timestamp_ms + skew_tolerance_ms)` is strictly forbidden from looking forward into unclosed bars. The skew tolerance applies only to boundary latching of already completed historical bars.
     - If `decision_timestamp_ms < expected_or_close_ms` (09:45:00.000 IST), skew tolerance is 0; it must unconditionally reject.

---

## 3. Detailed Component Specification

### 3.1 State Tracking Additions in `SentinelLiveStreamAdvisor`
In `SentinelLiveStreamAdvisor.__init__`:
```python
# Opening Range reconciliation state machine
self.or_reconciliation_complete: bool = False
self.or_last_reconcile_attempt_ms: dict[str, int] = {
    "NIFTY": 0,
    "BANKNIFTY": 0,
    "SENSEX": 0,
}
self.or_reconcile_retry_count: dict[str, int] = {
    "NIFTY": 0,
    "BANKNIFTY": 0,
    "SENSEX": 0,
}
self.OR_MAX_RETRY_ATTEMPTS: int = 10
self.OR_MIN_RETRY_INTERVAL_MS: int = 60_000  # 60s throttle
self.CAUSAL_SKEW_TOLERANCE_MS: int = 1_000   # 1s arrival jitter buffer
```

### 3.2 Idempotent Periodic Reconciliation Method
Refactor `_seed_or_bounds_from_api_if_late_boot` -> `_reconcile_or_bounds_from_api`:
```python
def _reconcile_or_bounds_from_api(
    self,
    session_day: Optional[date] = None,
    current_time_ms: Optional[int] = None,
    force: bool = False,
) -> bool:
    """
    Idempotently reconcile Opening Range bounds from official v2 1m candles.
    Retries until all indices achieve status == COMPLETE or retry budget is exhausted.
    """
```
Key algorithmic rules:
1. If `self.or_reconciliation_complete` is `True`, return `True` immediately without lock contention or network calls.
2. Determine current time in `Asia/Kolkata`. If `now_dt.time() < self.opening_shock_end_time` (09:45:00), return `False`.
3. Check token availability. If missing, fail closed.
4. Iterate over indices `("NIFTY", "BANKNIFTY", "SENSEX")`:
   - Check if index is already `COMPLETE`. If so, skip network call.
   - Enforce throttle: if `not force` and `(current_time_ms - self.or_last_reconcile_attempt_ms[idx]) < self.OR_MIN_RETRY_INTERVAL_MS`, skip index for this cycle.
   - Enforce max attempts: if `self.or_reconcile_retry_count[idx] >= self.OR_MAX_RETRY_ATTEMPTS`, log warning and do not spam.
   - Execute HTTP GET with `timeout=4`.
   - Update `self.or_last_reconcile_attempt_ms[idx] = current_time_ms`.
   - Increment `self.or_reconcile_retry_count[idx] += 1`.
   - Parse candles via `self._parse_complete_v2_or_candles`.
   - If parsed successfully:
     - Update `or_bounds` and latch `or_evidence` with `status = "COMPLETE"`, `source = "UPSTOX_V2_1M_EXACT_30"`.
   - If parsed is `None`:
     - If index was not already `COMPLETE`, set `status = "PENDING_RECONCILIATION"` (or retain current evidence with note), **do not latch terminal "INVALID"**.
5. If all required indices are `COMPLETE`:
   - Set `self.or_reconciliation_complete = True`.
   - Log reconciliation freeze.

### 3.3 Hooking into Advisor Execution Loop
1. **On Shock End Transition (`09:45:00 IST`)**:
   - Initial reconciliation attempt dispatched.
2. **On Every 5-Minute Bar Evaluation / Spot Tick (`now >= 09:45:00 IST`)**:
   - In `_evaluate_spot_tick` and `_evaluate_5m_bar_close`:
     - If `not self.or_reconciliation_complete`:
       - Check throttle and invoke `_reconcile_or_bounds_from_api(session_day=tick_day, current_time_ms=timestamp_ms)`.
3. **In `_validate_mode5_or_evidence`**:
   - Support `skew_tolerance_ms`:
     ```python
     # Allow up to 1000ms clock skew only if source is completed historical bar
     if source_timestamp_ms <= 0 or source_timestamp_ms > (decision_timestamp_ms + self.CAUSAL_SKEW_TOLERANCE_MS):
         return False, "OR_SOURCE_NONCAUSAL", details
     ```

---

## 4. Scope Discipline & Non-Negotiable Invariants

### 4.1 What Does NOT Change
1. **No Strategy Threshold Alterations**:
   - Zero changes to OptionMate RBFN levels, ATR multipliers, volume ratios, or SL/target calculation rules.
2. **Zero Modifications to Risk Gates**:
   - Daily loss limits, drawdown limits, max open positions, and cooldown periods remain unaltered.
3. **Zero Broker API or Live Ordering Modifications**:
   - All tests must maintain:
     ```python
     read_only = True
     is_order_action = False
     broker_api_called = False
     ```
4. **Fail-Closed Guarantee Maintained**:
   - Until `COMPLETE` status is cryptographically/structurally proven by 30 timestamped candles, Mode 5 entries continue to abstain with `MODE5_TARGET_OR_COMPLETE_REQUIRED`.

---

## 5. Test Acceptance Criteria (`tests/unit/test_sentinel_advisor_hardening_005.py`)

A new, dedicated test suite `tests/unit/test_sentinel_advisor_hardening_005.py` must verify the following scenarios deterministically:

1. **Test Case 1: Delayed 30th Bar Eventual Reconciliation**:
   - Simulate 09:45:00 tick where REST API returns 29 candles (09:15 to 09:43).
   - Verify status is `PENDING_RECONCILIATION` (not latched `INVALID`).
   - Verify Mode 5 entries at 09:45:00 abstain with `OR_COMPLETE_REQUIRED`.
   - Advance clock to 09:46:05 (beyond 60s throttle). REST API now returns all 30 candles.
   - Verify advisor reconciles successfully, latches `status == "COMPLETE"`, and updates `or_bounds`.
   - Verify subsequent Mode 5 evaluation at 09:50:00 passes OR evidence check.

2. **Test Case 2: Throttle & Zero API Spamming**:
   - Fire 100 ticks between 09:45:01 and 09:45:30 while REST API has 29 candles.
   - Verify only 1 REST API call was dispatched (throttle of 60s strictly enforced).

3. **Test Case 3: Permanent Freeze Once Complete**:
   - Once all indices reach `COMPLETE`, fire ticks at 09:50, 09:55, 10:00.
   - Verify zero additional REST API calls are dispatched (`or_reconciliation_complete` short-circuits).

4. **Test Case 4: Causal Skew Tolerance Boundary**:
   - Decision timestamp at `09:45:00.000 IST`. Source timestamp of 30th candle at `09:44:00.000 IST` (with coverage end `09:44:00.000` / `09:44:59.999`).
   - Companion tick arriving with 500ms arrival jitter (`09:44:59.500 IST`) vs decision time.
   - Verify skew tolerance accepts valid causal timestamps and rejects timestamps exceeding +1000ms.

5. **Test Case 5: Maximum Retry Exhaustion Fail-Closed**:
   - If REST API continuously returns 404 or incomplete candles past 10 retries, verify advisor stops retrying and continues to fail closed (abstain from trading).

---

## 6. Architecture Acceptance Sign-Off

- **Contract GATE-SENTINEL-15**: `RETRY_OR_RECONCILIATION_UNTIL_COMPLETE` strictly defined.
- **Microstructure Alignment**: Propagation latency accommodated, causal skew bounded.
- **Safety Proof**: Fail-closed until verified; zero runtime risk changes; read-only verification.
- **Ready for Stage 2 (GSD Execution)**.
