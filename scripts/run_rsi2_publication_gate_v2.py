from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).with_name("bootstrap.py")))

from research.rsi2_mean_reversion.independent_publication_oracle_v2 import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
