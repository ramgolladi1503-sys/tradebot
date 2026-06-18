import pandas as pd
import os
import json

def run_summary():
    log_path = "runtime/real_paper_signal_log.csv"
    out_dir = "runtime/candidate_audits"
    os.makedirs(out_dir, exist_ok=True)
    
    print("--- HTF_RANGE_EXPANSION Paper Observation Dashboard ---")
    
    if not os.path.exists(log_path):
        print(f"Log not found at {log_path}. Generating baseline empty report.")
        df = pd.DataFrame(columns=['timestamp', 'regime', 'nifty_spot', 'chosen_option', 'strike', 'expiry', 'bid', 'ask', 'spread', 'theoretical_entry', 'theoretical_stop', 'theoretical_target', 'realized_r', 'mfe', 'mae', 'status'])
    else:
        df = pd.read_csv(log_path)
        
    total_signals = len(df)
    
    if total_signals == 0:
        open_trades = 0
        closed_trades = 0
        win_rate = 0.0
        realized_r = 0.0
        median_spread = 0.0
        mfe_avg = 0.0
        mae_avg = 0.0
    else:
        open_trades = len(df[df['status'] == 'OPEN'])
        closed_df = df[df['status'] == 'CLOSED']
        closed_trades = len(closed_df)
        
        if closed_trades > 0:
            win_rate = len(closed_df[closed_df['realized_r'] > 0]) / closed_trades
            realized_r = closed_df['realized_r'].sum()
            median_spread = df['spread'].median() if 'spread' in df.columns else 0.0
            mfe_avg = closed_df['mfe'].mean() if 'mfe' in closed_df.columns else 0.0
            mae_avg = closed_df['mae'].mean() if 'mae' in closed_df.columns else 0.0
        else:
            win_rate = 0.0
            realized_r = 0.0
            median_spread = df['spread'].median() if 'spread' in df.columns else 0.0
            mfe_avg = 0.0
            mae_avg = 0.0
            
    # Check daemon status
    daemon_status = "UNKNOWN"
    feed_age = "N/A"
    if os.path.exists("runtime/daemon_health.json"):
        try:
            with open("runtime/daemon_health.json", "r") as f:
                health = json.load(f)
                daemon_status = health.get("status", "UNKNOWN")
                feed_age = health.get("feed_age_seconds", "N/A")
        except:
            pass
            
    print(f"Daemon Status: {daemon_status}")
    print(f"Feed Age: {feed_age}")
    print(f"Total Signals: {total_signals}")
    print(f"Open Trades: {open_trades}")
    print(f"Closed Trades: {closed_trades}")
    if closed_trades > 0:
        print(f"Win Rate: {win_rate*100:.1f}%")
        print(f"Realized Expectancy: {realized_r:.2f}R")
        print(f"Median Spread: {median_spread}")
        
    report_content = f"""# Weekly Paper Report: HTF_RANGE_EXPANSION

## Observation Dashboard
- **Daemon Status**: `{daemon_status}`
- **Feed Age**: `{feed_age}`
- **Total Cumulative Signals**: `{total_signals}`
- **Currently Open Paper Trades**: `{open_trades}`
- **Closed Paper Trades**: `{closed_trades}`

## Execution Metrics
- **Win Rate**: `{win_rate*100:.1f}%`
- **Cumulative Realized Expectancy**: `{realized_r:.2f}R`
- **Average MFE**: `{mfe_avg:.2f}R`
- **Average MAE**: `{mae_avg:.2f}R`
- **Median Option Spread**: `{median_spread}`

## Divergence Audit
- **Execution Degradation vs Backtest**: {"No degradation to report (empty baseline)." if closed_trades == 0 else "Pending sufficient sample size (>30 trades) to calculate statistical divergence from backtest expectancy."}

> [!NOTE]
> The strategy operates strictly in Observation Mode. No execution routing exists.
"""

    with open(f"{out_dir}/weekly_paper_report.md", "w") as f:
        f.write(report_content)
        
    print(f"\nReport generated at {out_dir}/weekly_paper_report.md")

if __name__ == "__main__":
    run_summary()
