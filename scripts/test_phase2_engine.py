from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.engine_phase2_adapter import run_engine_phase2

# Simulated candidates (THIS IS YOUR CONTROLLED INPUT)
dummy_candidates = [
    {
        "symbol": "NIFTY",
        "signal_score": 0.85,
        "execution_score": 0.75,
        "liquidity_score": 0.8,
        "regime_score": 0.7,
        "spread_pct": 0.005,
    },
    {
        "symbol": "BANKNIFTY",
        "signal_score": 0.55,
        "execution_score": 0.45,  # should FAIL filter
        "liquidity_score": 0.6,
        "regime_score": 0.5,
        "spread_pct": 0.02,  # should FAIL filter
    },
]

decision = run_engine_phase2(dummy_candidates)

print("\n=== DECISION OUTPUT ===")
print(decision)
