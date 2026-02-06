from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))


import argparse
from core.model_registry import register_model

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", required=True, help="xgb/deep/micro")
    parser.add_argument("--path", required=True)
    parser.add_argument("--metric", action="append", default=[], help="key=value pairs")
    args = parser.parse_args()

    metrics = {}
    for kv in args.metric:
        if "=" in kv:
            k, v = kv.split("=", 1)
            try:
                v = float(v)
            except Exception:
                pass
            metrics[k] = v
    entry = register_model(args.type, args.path, metrics=metrics)
    print(entry)
