from rl.trading_env import TradingEnv
from stable_baselines3 import PPO, DDPG

def evaluate(model_path, algo="PPO", episodes=3, data_csv="data/ml_features.csv"):
    env = TradingEnv(data_csv=data_csv)
    if algo == "PPO":
        model = PPO.load(model_path)
    else:
        model = DDPG.load(model_path)
    rewards = []
    for _ in range(episodes):
        obs, _ = env.reset()
        done = False
        total = 0
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, done, _, _ = env.step(action)
            total += reward
        rewards.append(total)
    print(f"{algo} avg reward: {sum(rewards)/len(rewards):.2f}")

if __name__ == "__main__":
    evaluate("models/ppo_trading", algo="PPO")
