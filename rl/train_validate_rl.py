from pathlib import Path
import sys
import pandas as pd
from stable_baselines3 import PPO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rl.trading_env import TradingEnv

DATA_FILE = Path("data/ml_features.csv")
TRAIN_FILE = Path("data/rl_train.csv")
VAL_FILE = Path("data/rl_val.csv")

def split_data():
    df = pd.read_csv(DATA_FILE).dropna().reset_index(drop=True)
    split = int(len(df) * 0.8)
    df.iloc[:split].to_csv(TRAIN_FILE, index=False)
    df.iloc[split:].to_csv(VAL_FILE, index=False)

def train_and_validate():
    split_data()
    train_env = TradingEnv(data_csv=str(TRAIN_FILE))
    model = PPO("MlpPolicy", train_env, verbose=1)
    model.learn(total_timesteps=10000)
    model.save("models/ppo_trading")

    # Evaluate on validation set
    val_env = TradingEnv(data_csv=str(VAL_FILE))
    obs, _ = val_env.reset()
    done = False
    total = 0
    steps = 0
    pnl_series = []
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, done, _, _ = val_env.step(action)
        total += reward
        steps += 1
        pnl_series.append(reward)
    # Metrics
    import statistics as stats
    mean = stats.mean(pnl_series) if pnl_series else 0
    stdev = stats.pstdev(pnl_series) if len(pnl_series) > 1 else 0
    sharpe = mean / stdev if stdev else 0
    equity = 0
    peak = 0
    max_dd = 0
    for r in pnl_series:
        equity += r
        if equity > peak:
            peak = equity
        dd = equity - peak
        if dd < max_dd:
            max_dd = dd
    print(f"Validation total reward: {total:.2f}, steps: {steps}")
    print(f"Sharpe: {sharpe:.3f}, Max Drawdown: {max_dd:.2f}")

    # Log metrics to CSV
    import csv
    from datetime import datetime
    from pathlib import Path
    import json
    out = Path("logs/rl_metrics.csv")
    out.parent.mkdir(exist_ok=True)
    is_new = not out.exists()
    with open(out, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp", "total_reward", "steps", "sharpe", "max_drawdown"])
        writer.writerow([datetime.now().isoformat(), round(total, 2), steps, round(sharpe, 3), round(max_dd, 2)])

    # Log metrics to JSON for dashboard
    json_path = Path("logs/rl_metrics.json")
    data = []
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text())
        except Exception:
            data = []
    data.append({
        "timestamp": datetime.now().isoformat(),
        "total_reward": round(total, 2),
        "steps": steps,
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(max_dd, 2)
    })
    json_path.write_text(json.dumps(data[-500:], indent=2))

    # Telegram notify + deterioration alert
    try:
        from core.telegram_alerts import send_telegram_message
        send_telegram_message(f"RL Metrics | Reward: {round(total,2)} | Sharpe: {round(sharpe,3)} | DD: {round(max_dd,2)}")
        from config import config as cfg
        if sharpe < cfg.RL_SHARPE_ALERT or max_dd < cfg.RL_DD_ALERT:
            send_telegram_message(f"RL Alert: Sharpe {round(sharpe,3)} or Drawdown {round(max_dd,2)} below threshold")
    except Exception:
        pass

if __name__ == "__main__":
    train_and_validate()
