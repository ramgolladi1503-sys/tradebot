import pandas as pd
from core.walk_forward import walk_forward
from core.backtest_report import analyze_results, risk_summary

def run_backtest(file_path: str, train_size: float = 0.6, step: int = 200):
    """
    Loads historical data and runs walk-forward backtest.
    """
    historical = pd.read_csv(file_path)
    results_df = walk_forward(historical, train_size=train_size, step=step)
    report = analyze_results(results_df)
    summary = risk_summary(results_df)
    results_df.to_csv("logs/backtest_results.csv", index=False)
    pd.DataFrame([report]).to_json("logs/backtest_report.json", orient="records")
    pd.DataFrame([summary.get("overall", {})]).to_json("logs/walk_forward_risk_summary.json", orient="records")
    pd.DataFrame(summary.get("strategies", [])).to_csv("logs/walk_forward_strategy_summary.csv", index=False)
    return results_df, report

if __name__ == "__main__":
    run_backtest("data/NIFTY_20260123.csv", train_size=0.6, step=200)
