from pathlib import Path
import json
import pandas as pd

from core.stress_generator import SyntheticStressGenerator


def _load_returns():
    # Use NIFTY csv if available
    candidates = sorted(Path("data").glob("NIFTY_*.csv"))
    if not candidates:
        return [0.001] * 300, 25000.0
    df = pd.read_csv(candidates[-1])
    if "close" not in df:
        return [0.001] * 300, 25000.0
    close = df["close"].astype(float).values
    rets = []
    for i in range(1, len(close)):
        if close[i - 1] == 0:
            continue
        rets.append((close[i] - close[i - 1]) / close[i - 1])
    start = float(close[-1]) if len(close) else 25000.0
    return rets, start


def main():
    returns, start_price = _load_returns()
    gen = SyntheticStressGenerator()
    report = gen.run(returns=returns, start_price=start_price, n_steps=240, n_paths=200)
    Path("data").mkdir(exist_ok=True)
    Path("data/stress_scenarios.json").write_text(json.dumps(report, indent=2))
    print(report)


if __name__ == "__main__":
    main()
