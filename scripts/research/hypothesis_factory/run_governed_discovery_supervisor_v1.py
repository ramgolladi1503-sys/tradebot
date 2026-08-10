#!/usr/bin/env python3
import sys
from pathlib import Path
import subprocess

def main():
    root = Path(__file__).resolve().parent.parent.parent.parent
    driver_script = root / "scripts" / "research" / "hypothesis_factory" / "run_autonomous_structural_edge_campaign_v2.py"
    subprocess.check_call([sys.executable, str(driver_script)], cwd=root)

if __name__ == "__main__":
    main()
