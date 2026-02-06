import json
from pathlib import Path
from config import config as cfg


def promote_if_better(challenger_path: str, champion_path: str, metric_path: str, min_diff: float = 0.02):
    mpath = Path(metric_path)
    if not mpath.exists():
        return False, "metrics_missing"
    metrics = json.loads(mpath.read_text())
    champ = metrics.get("champion_avg_reward")
    chall = metrics.get("challenger_avg_reward")
    if champ is None or chall is None:
        return False, "metrics_invalid"
    if chall > champ + min_diff:
        Path(challenger_path).replace(champion_path)
        return True, "promoted"
    return False, "not_better"


if __name__ == "__main__":
    ok, reason = promote_if_better(
        cfg.RL_SIZE_CHALLENGER_PATH,
        cfg.RL_SIZE_MODEL_PATH,
        cfg.RL_SIZE_EVAL_PATH,
        min_diff=cfg.RL_SIZE_PROMOTE_DIFF,
    )
    print({"promoted": ok, "reason": reason})
