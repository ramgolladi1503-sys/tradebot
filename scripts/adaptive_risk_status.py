import time
from pathlib import Path

from core.adaptive_risk import compute_multiplier, write_status


def main():
    payload = {
        "as_of_epoch": time.time(),
        "multiplier": compute_multiplier(
            base=1.0,
            drawdown_pct=-0.01,
            vol_proxy=0.5,
            exec_quality=0.9,
            decay_prob=0.2,
            regime_entropy=1.0,
        ),
    }
    out = write_status(Path("logs/adaptive_risk_status.json"), payload)
    print(f"Adaptive risk status: {out}")


if __name__ == "__main__":
    main()
