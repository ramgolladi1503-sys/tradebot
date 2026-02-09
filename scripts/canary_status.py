import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import config as cfg
from core.feature_flags import canary_allowed


def main():
    percent = int(getattr(cfg, "CANARY_PERCENT", 0))
    trace = "demo-trace"
    allowed = canary_allowed(trace, percent)
    print(f"CANARY_PERCENT={percent} trace={trace} allowed={allowed}")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
