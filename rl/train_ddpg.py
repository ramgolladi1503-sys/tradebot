from stable_baselines3 import DDPG
from rl.trading_env import TradingEnv

if __name__ == "__main__":
    env = TradingEnv()
    model = DDPG("MlpPolicy", env, verbose=1)
    model.learn(total_timesteps=10000)
    model.save("models/ddpg_trading")
