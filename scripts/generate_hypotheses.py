import json
import time
from pathlib import Path

from core.hypothesis_engine import generate_hypotheses


def main():
    hypotheses = generate_hypotheses()
    now = time.time()
    out = Path("logs") / f"hypotheses_{time.strftime('%Y-%m-%d')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"as_of_epoch": now, "hypotheses": hypotheses}, indent=2))
    print(f"Hypotheses written: {out}")


if __name__ == "__main__":
    main()
