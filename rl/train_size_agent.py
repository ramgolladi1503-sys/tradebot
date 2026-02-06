from rl.size_agent import SizeRLAgent, ACTIONS
from rl.size_env import SizeEnv
from config import config as cfg


def train(model_path, episodes=1):
    env = SizeEnv()
    agent = SizeRLAgent(model_path=model_path, epsilon=0.1)
    for _ in range(episodes):
        env.reset()
        done = False
        state = None
        while not done:
            # select action
            if state is None:
                action = 1.0
            else:
                action = agent.select_multiplier({"score": 0.5, "regime_prob": 0.5, "fill_prob": 0.7, "exec_q": 0.7,
                                                  "pnl_streak": 0, "drawdown": 0.0, "vol_regime": 5,
                                                  "time_bucket": 1, "delta_pct": 0.0, "gamma_pct": 0.0,
                                                  "vega_pct": 0.0, "corr": 0.0}, explore=True)
            action_idx = agent.action_index(action)
            next_state, reward, done, _ = env.step(action)
            if state is None:
                state = next_state
            if next_state is not None:
                agent.update(state, action_idx, reward, next_state)
                state = next_state
    agent.save()
    return agent


if __name__ == "__main__":
    train(cfg.RL_SIZE_MODEL_PATH, episodes=1)
