import runpy
from pathlib import Path

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
from scripts.ops_summary import main


def _db_exists():
    return Path(cfg.TRADE_DB_PATH).exists()


def verify():
    if not _db_exists():
        raise SystemExit("trades.db not found")
    main()
    print("verify_ops_summary: OK")


if __name__ == "__main__":
    verify()
