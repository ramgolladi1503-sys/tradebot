from rl.trading_env import TradingEnv
import numpy as np

if __name__ == "__main__":
    env = TradingEnv()
    obs, _ = env.reset()
    total_reward = 0.0
    done = False
    while not done:
        action = env.action_space.sample()
        obs, reward, done, _, _ = env.step(action)
        total_reward += reward
    print(f"Random policy reward: {total_reward:.2f}")
