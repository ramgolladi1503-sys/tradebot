import csv
from datetime import datetime

TYPES = [
    ("Functional", "F"),
    ("Boundary", "B"),
    ("Property", "P"),
    ("Chaos", "C"),
    ("Adhoc", "A"),
]

CATEGORY_PRIORITY = {
    "MD": "P0",
    "FE": "P1",
    "SL": "P0",
    "RS": "P0",
    "OL": "P0",
    "SP": "P1",
    "PR": "P1",
    "SC": "P0",
    "OB": "P1",
}

CATEGORIES = [
    {
        "code": "MD",
        "name": "Market data ingestion",
        "scenarios": [
            {"title": "Out-of-order ticks", "input": "Ticks with timestamps t3, t1, t2", "expected": "Reorder or reject; candles deterministic; no negative deltas"},
            {"title": "Duplicate tick burst", "input": "Same tick repeated 1000x", "expected": "Dedup works or aggregation stable; no duplicate signals"},
            {"title": "Gap in feed", "input": "Missing 5 minutes of ticks", "expected": "Gap handled; indicators reset or flagged"},
            {"title": "Spike outlier", "input": "Single tick 10x price", "expected": "Outlier filtered or flagged; no trade"},
            {"title": "Timezone shift", "input": "Ticks in UTC mixed with IST", "expected": "Normalized timestamps; correct session mapping"},
            {"title": "Holiday session", "input": "Ticks on market holiday", "expected": "Ignored or logged; no signals"},
            {"title": "Mixed symbol interleave", "input": "NIFTY/BANKNIFTY ticks interleaved", "expected": "No cross-contamination between symbols"},
        ],
    },
    {
        "code": "FE",
        "name": "Feature engineering",
        "scenarios": [
            {"title": "Insufficient lookback", "input": "5 candles but SMA_20 required", "expected": "Mark not tradable; no NaN propagation"},
            {"title": "ATR zero", "input": "ATR=0 in flat market", "expected": "Safe default; score penalized"},
            {"title": "Missing VWAP", "input": "VWAP column missing", "expected": "Fallback to LTP; log warning"},
            {"title": "NaN propagation", "input": "NaNs in RSI/ADX", "expected": "Handled; no crash"},
            {"title": "Misaligned candles", "input": "Feature window shifted by 1 bar", "expected": "Detected; no future leakage"},
            {"title": "Window mismatch", "input": "RSI window mismatched", "expected": "Correct window or explicit error"},
            {"title": "Extreme volume Z-score", "input": "Volume spike 50x", "expected": "Clipped or normalized"},
        ],
    },
    {
        "code": "SL",
        "name": "Strategy logic and scoring",
        "scenarios": [
            {"title": "Score threshold edge", "input": "Score 74.99 vs 75.00", "expected": "Below=reject, at threshold=allow"},
            {"title": "Regime flip-flop", "input": "ADX 24.9 ↔ 25.1", "expected": "Hysteresis prevents rapid toggling"},
            {"title": "Conflicting signals", "input": "Trend up but mean-revert down", "expected": "Priority rules apply"},
            {"title": "Direction sanity", "input": "PE while price above VWAP", "expected": "Blocked by sanity check"},
            {"title": "Entry trigger vs LTP", "input": "LTP 148, trigger 150", "expected": "Entry=150, not 148"},
            {"title": "Strategy lockout", "input": "Underperforming strategy", "expected": "Auto-disabled"},
            {"title": "Day-type lock", "input": "Day type uncertain", "expected": "Fallback to safe regime"},
        ],
    },
    {
        "code": "RS",
        "name": "Risk and position sizing",
        "scenarios": [
            {"title": "Lot rounding", "input": "Position = 1.3 lots", "expected": "Rounded down; never exceed risk"},
            {"title": "Daily loss limit", "input": "PnL hits max loss", "expected": "New trades blocked"},
            {"title": "Max positions", "input": "Already at max open trades", "expected": "New trades rejected"},
            {"title": "SL/target rounding", "input": "SL 23.978", "expected": "Rounded consistently"},
            {"title": "Volatility targeting", "input": "Vol spikes 2x", "expected": "Size reduced"},
            {"title": "Loss streak reduction", "input": "Loss streak >= cap", "expected": "Risk multiplier applied"},
            {"title": "Capital insufficient", "input": "Capital < min risk", "expected": "Reject trade"},
        ],
    },
    {
        "code": "OL",
        "name": "Order lifecycle",
        "scenarios": [
            {"title": "Rejected order", "input": "Broker returns insufficient margin", "expected": "No retry loop; mark failed"},
            {"title": "Partial fill", "input": "60% filled then canceled", "expected": "Position correct; PnL correct"},
            {"title": "Stale quote", "input": "Quote older than threshold", "expected": "Trade blocked"},
            {"title": "Retry limit", "input": "Order keeps failing", "expected": "Stop after N retries"},
            {"title": "Manual approval timeout", "input": "Queue trade expires", "expected": "Auto-expire"},
            {"title": "Order idempotency", "input": "Duplicate order request", "expected": "Only one order placed"},
            {"title": "Latency tracking", "input": "Fill timestamp delayed", "expected": "Latency logged"},
        ],
    },
    {
        "code": "SP",
        "name": "State and persistence",
        "scenarios": [
            {"title": "Restart mid-trade", "input": "App restarts with open trade", "expected": "Resume monitoring; no re-entry"},
            {"title": "Duplicate signal", "input": "Same signal twice", "expected": "Deduped by signal_id"},
            {"title": "Queue recovery", "input": "Queue file exists on restart", "expected": "Load safely"},
            {"title": "Idempotent logging", "input": "Same trade logged twice", "expected": "Single record"},
            {"title": "Corrupted state", "input": "Invalid JSON log", "expected": "Graceful skip"},
            {"title": "Open trade reconcile", "input": "Broker vs local mismatch", "expected": "Reconcile or flag"},
            {"title": "Config hot reload", "input": "Config change mid-run", "expected": "Applies safely"},
        ],
    },
    {
        "code": "PR",
        "name": "Performance and reliability",
        "scenarios": [
            {"title": "Latency spike", "input": "Quote latency > 2s", "expected": "Penalty applied"},
            {"title": "Memory growth", "input": "Long run for 8h", "expected": "No memory leak"},
            {"title": "WS reconnect loop", "input": "Websocket disconnects", "expected": "Backoff and recover"},
            {"title": "DB lock contention", "input": "Concurrent writes", "expected": "No deadlock"},
            {"title": "High tick rate", "input": "10k ticks/sec", "expected": "No crash; drop safely"},
            {"title": "Slow disk", "input": "Disk writes delayed", "expected": "Buffered logging"},
            {"title": "Concurrent refresh", "input": "Multiple UI refreshes", "expected": "No flicker/lock"},
        ],
    },
    {
        "code": "SC",
        "name": "Security and compliance",
        "scenarios": [
            {"title": "Secrets in logs", "input": "API key in env", "expected": "Never logged"},
            {"title": "PII in logs", "input": "User identifiers", "expected": "Redacted"},
            {"title": "Env missing", "input": "No API key", "expected": "Clear error"},
            {"title": "Unsafe error dump", "input": "Unhandled exception", "expected": "No secrets in stack"},
            {"title": "API key masking", "input": "Display key", "expected": "Mask middle"},
            {"title": "Config permissions", "input": "World-readable .env", "expected": "Warn"},
            {"title": "Audit log integrity", "input": "Log tamper attempt", "expected": "Detectable"},
        ],
    },
    {
        "code": "OB",
        "name": "Observability",
        "scenarios": [
            {"title": "Decision trace missing", "input": "Trade suggested", "expected": "Why-trade trace present"},
            {"title": "Metric gaps", "input": "No metrics for 10m", "expected": "Alert"},
            {"title": "Alert throttle", "input": "Repeated failures", "expected": "Cooldown enforced"},
            {"title": "Blocked reason", "input": "Trade blocked", "expected": "Reason logged"},
            {"title": "Slippage stats", "input": "Fills available", "expected": "Slippage metrics updated"},
            {"title": "Fill ratio stats", "input": "Fills vs intents", "expected": "Fill ratio computed"},
            {"title": "Traceability", "input": "Trade approved", "expected": "All IDs linked"},
        ],
    },
]


def _wrap_input(test_type, base):
    if test_type == "Boundary":
        return base + " at exact thresholds or minimum viable values"
    if test_type == "Property":
        return "Randomized inputs within valid ranges based on: " + base
    if test_type == "Chaos":
        return "Inject failure while running: " + base
    if test_type == "Adhoc":
        return "Manual exploration of: " + base
    return base


def _wrap_expected(test_type, base):
    if test_type == "Boundary":
        return base + "; boundary behavior consistent"
    if test_type == "Property":
        return "Invariant holds for all samples; " + base
    if test_type == "Chaos":
        return "System degrades gracefully; " + base
    if test_type == "Adhoc":
        return "Document findings; " + base
    return base


def generate_cases(out_path: str = "testing/TEST_CASES.csv"):
    rows = []
    for cat in CATEGORIES:
        for tname, tcode in TYPES:
            for i, sc in enumerate(cat["scenarios"], start=1):
                case_id = f"{cat['code']}-{tcode}-{i:03d}"
                rows.append({
                    "id": case_id,
                    "category": cat["name"],
                    "test_type": tname,
                    "title": sc["title"],
                    "input": _wrap_input(tname, sc["input"]),
                    "expected": _wrap_expected(tname, sc["expected"]),
                    "priority": CATEGORY_PRIORITY.get(cat["code"], "P2"),
                    "tags": f"{cat['code']},{tname}",
                })

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {len(rows)} cases at {out_path}")


if __name__ == "__main__":
    generate_cases()
