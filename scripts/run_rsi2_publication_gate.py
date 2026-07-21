from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).with_name("bootstrap.py")))

from research.rsi2_mean_reversion.publication_gate import main


if __name__ == "__main__":
    raise SystemExit(main())

