from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


import argparse
from core.model_registry import activate_model

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", required=True, help="xgb/deep/micro")
    parser.add_argument("--path", required=True)
    args = parser.parse_args()

    active = activate_model(args.type, args.path)
    print(active)
