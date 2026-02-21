import argparse

from config import config as cfg
from ml.trade_predictor import TradePredictor
from core.auto_retrain import AutoRetrain


def main():
    parser = argparse.ArgumentParser(description="Run ML retrain with gating and promotion rules.")
    parser.add_argument(
        "--trade-log",
        default=str(getattr(cfg, "TRADE_LOG_PATH", "logs/trade_log.jsonl")),
        help="Path to trade log JSON/JSONL.",
    )
    args = parser.parse_args()

    predictor = TradePredictor()
    retrainer = AutoRetrain(predictor)
    retrainer.update_model(trade_log_path=args.trade_log)


if __name__ == "__main__":
    main()
